# Auth + User Attribution — Design

**Date:** 2026-04-22
**Status:** Approved

## Goal

Gate the whole app behind Supabase Auth login. Admins create rep accounts (no self-signup). Every mutating action stamps `last_touched_by` + `last_touched_at` on the affected practice, so the team can answer "who touched this lead last?"

## Non-goals

- No self-signup / public registration. Admin creates accounts.
- No password-reset email flow yet (admin resets by regenerating a temp password). Supabase supports it out of the box — layer in later.
- No owner assignment, no per-rep access restrictions. Every authenticated user sees every practice (free-for-all).
- No fine-grained activity log. Scalar `last_touched_*` on practices + `user_id` on `email_messages`. Full activity history is feature A (future phase).
- No OAuth / SSO.
- No MFA.

## Data model

Two schema changes on top of Supabase's built-in `auth.users`:

```sql
-- Profile table tied 1:1 to auth.users. Holds app-specific role + display name.
create table if not exists profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  name text,
  role text not null default 'rep' check (role in ('admin', 'rep')),
  created_at timestamptz default now()
);

-- DB trigger: when a new auth.users row is inserted, create a matching profile.
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer as $$
begin
  insert into public.profiles (id, email, name, role)
  values (new.id, new.email, new.raw_user_meta_data->>'name', 'rep')
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Attribution on practices.
alter table practices add column if not exists last_touched_by uuid references profiles(id);
alter table practices add column if not exists last_touched_at timestamptz;

create index if not exists idx_profiles_role on profiles (role);
```

### Why these choices

- **`profiles` table** — Supabase `auth.users` is credentials-only. App-specific fields (role, display name) in a 1:1 profile table is the recommended pattern. DB trigger keeps it in sync automatically.
- **`uuid` keys** — match `auth.users.id`.
- **Scalar `last_touched_*` columns** — one round-trip for sidebar rendering. Full event history is future feature A, intentionally out of scope.
- **Admin role trigger default `rep`** — admins are explicitly promoted by updating `profiles.role`; bootstrap does this for the first admin.

### Email messages

The email-outreach spec (separate doc) adds `email_messages.user_id uuid references profiles(id)`. This spec does NOT introduce that table.

## Backend integration (FastAPI)

### Auth flow

Supabase issues a JWT on login. Frontend stores it via Supabase's SSR helpers (httpOnly cookies). FastAPI verifies the JWT on every `/api/*` request and resolves it to a `profiles` row.

### New module: `src/auth.py`

```python
from fastapi import Depends, HTTPException, Request
from supabase import create_client
from src.settings import settings

_admin_client = None

def get_admin_client():
    """Supabase client authenticated with the service-role key."""
    global _admin_client
    if _admin_client is None:
        _admin_client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return _admin_client

async def get_current_user(request: Request) -> dict:
    """Resolve JWT from cookie → profiles row. 401 if missing/invalid.

    The cookie name is whatever `@supabase/ssr` sets on the browser — typically
    `sb-<project-ref>-auth-token` (sometimes chunked into `.0` / `.1`). Helper
    reads all `sb-*-auth-token*` cookies and reassembles the access token.
    """
    token = _read_supabase_token(request)
    if not token:
        raise HTTPException(401, "Not authenticated")
    client = get_admin_client()
    try:
        user_resp = client.auth.get_user(token)
    except Exception:
        raise HTTPException(401, "Invalid token")
    auth_user = user_resp.user
    profile = (
        client.table("profiles").select("*")
        .eq("id", auth_user.id).single().execute()
    )
    if not profile.data:
        raise HTTPException(403, "No profile for this user")
    return profile.data

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return user
```

### Route protection

- Every existing `/api/practices/*` endpoint adds `user: dict = Depends(get_current_user)`.
- Mutating endpoints pass `user["id"]` to storage helpers so they write `last_touched_by` and `last_touched_at` alongside their normal fields.
- `GET /api/health` stays public.
- `GET /api/me` returns the current profile — used by the frontend to hydrate auth state.

### New admin endpoints (all `require_admin`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/admin/users` | List profiles |
| POST | `/api/admin/users` | Create a rep account (body: `{ email, name, password, role? }`). Uses service-role client to create the auth user; the trigger creates the profile; if `role='admin'` the handler updates the profile after. |
| DELETE | `/api/admin/users/{id}` | Delete auth user (cascades to profile). Blocked if id == current user. |
| POST | `/api/admin/users/{id}/reset-password` | Regenerate temp password (returns it once — admin shares with rep). |

### Storage changes

[src/storage.py](src/storage.py) — `update_practice_fields`, `update_practice_analysis`, `upsert_practices` gain an optional `touched_by: str | None = None` arg. When set, writes `last_touched_by` + `last_touched_at=now()` alongside the supplied fields. When `None`, no attribution fields are written (used for system actions and read paths).

### New env vars

```
SUPABASE_SERVICE_ROLE_KEY=      # REQUIRED when auth is active. Admin client for token verification + user creation.
BOOTSTRAP_ADMIN_EMAIL=          # seeds first admin if profiles has zero admins
BOOTSTRAP_ADMIN_PASSWORD=       # paired with above; logged-out warning if set but blank
```

### Bootstrap

On startup, if:
- Supabase is configured AND
- `profiles` has zero rows with `role='admin'` AND
- `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` are set

...then create the auth user via the service-role client, update their profile to `role='admin'`, log the email (never the password). Idempotent — on re-run with an admin already present, it's a no-op.

## Frontend integration (Next.js)

### Dependencies

- `@supabase/supabase-js`
- `@supabase/ssr` (official Next.js cookie helpers)

### New env vars

```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

### New files

```
web/
├── lib/
│   ├── supabase-client.ts      createBrowserClient()
│   ├── supabase-server.ts      createServerClient() — reads cookies
│   └── auth.ts                 AuthProvider + useAuth() hook
├── middleware.ts               Next.js middleware; redirects unauthed → /login
├── app/
│   ├── login/page.tsx          Login form
│   └── admin/users/page.tsx    Admin: list + create reps (admin-only)
└── components/
    └── user-menu.tsx           Avatar in top-bar with name + sign-out
```

### Flow

1. `middleware.ts` runs on every request. If no Supabase session and path is not `/login`, redirect to `/login?redirect=<current>`.
2. Login page calls `supabase.auth.signInWithPassword`. On success, redirect to `?redirect` or `/`.
3. Root layout wraps the app in `<AuthProvider>`, which calls `/api/me` once to hydrate the user into React context.
4. Every call in `web/lib/api.ts` runs with `credentials: "include"` so the Supabase cookie is sent to FastAPI.
5. Top-bar renders `<UserMenu>` showing name + role + sign-out. Admins see an extra "Users" link → `/admin/users`.

### Admin UI (`/admin/users`)

- Client-side role check + backend `require_admin` enforcement.
- Table: email, name, role, created_at, delete.
- Create-rep form: email, name, password. POST `/api/admin/users`.
- Shows per-user "practices touched" count (derived via groupby query on `/api/admin/users` response).

### Sign-out

Call `supabase.auth.signOut()`; SSR helper clears cookie; redirect to `/login`.

## Attribution surfacing

### What gets stamped

| Action | Endpoint | Stamp |
| --- | --- | --- |
| Search (upsert) | `POST /api/practices/search` | each upserted row |
| Analyze | `POST /api/practices/{id}/analyze` | target |
| Rescan | `POST /api/practices/{id}/rescan` | target |
| Script (gen or regen) | `GET\|POST /api/practices/{id}/script` | target |
| PATCH status / notes | `PATCH /api/practices/{id}` | target |

Read endpoints (`GET /practices`, `GET /practices/{id}`) do NOT stamp.

### Surfacing in the UI

- **Practice card** (sidebar): muted line `Last touched by {name} · {timeAgo}` below the status/score row. Rendered only when `last_touched_by` is not null.
- **Call Prep page header**: same line next to the status badge.
- **Admin Users page**: count of practices per rep.

### Type changes

Backend `Practice` model + frontend `lib/types.ts` gain:

```ts
last_touched_by: string | null              // profiles.id (uuid)
last_touched_by_name: string | null         // joined on read
last_touched_at: string | null              // ISO timestamp
```

Backend joins `profiles` when returning practices, e.g.:

```
.select("*, last_touched_by_profile:profiles!last_touched_by(name)")
```

Response handler flattens `last_touched_by_profile.name` → `last_touched_by_name`.

### `timeAgo` helper

Add to `web/lib/utils.ts`:

```ts
export function timeAgo(iso: string | null): string {
  if (!iso) return ""
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diffMs / 60_000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  if (hrs < 48) return "yesterday"
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" })
}
```

No external date library.

## Error handling

| Case | Backend | Frontend |
| --- | --- | --- |
| No session / expired JWT | 401 | `apiFetch` catches 401, clears auth state, redirects to `/login?redirect=<current>` |
| Profile row missing for valid auth user | 403 "No profile for this user" | Toast + sign-out |
| Non-admin hits `/api/admin/*` | 403 | `/admin/users` renders "Admin only" placeholder |
| Admin tries to delete self | 400 "Cannot delete self" | Error toast |
| Bootstrap env set but Supabase not configured | Startup warning, skip | N/A (mock mode) |
| Service-role key missing | Startup error if any auth endpoint hit | N/A |

Service-role key is backend-only. Never sent to the frontend. `.env` stays out of git.

## Testing

- **Backend unit tests** for `get_current_user` and `require_admin` with a mocked Supabase client: valid token, expired, no profile, admin vs rep.
- **Storage tests** verify `last_touched_by`/`last_touched_at` get written iff `touched_by` arg is passed.
- **One integration test** against a dev Supabase project: login → call protected endpoint → verify attribution stamped.
- **Frontend** — manual smoke (login, protected-route redirect, admin user creation, sign-out). No E2E harness exists yet; not adding one for this feature alone.

## Rollout plan (local-first)

1. Apply the migration locally; bootstrap creates first admin.
2. Verify login → admin UI → create a rep → login as rep → call protected endpoint → confirm attribution in DB.
3. Commit. No prod gate — this is a demo/internal tool.

## Decisions log

- **Supabase Auth** over hand-rolled — free password reset, email verification, RLS; one less system to babysit.
- **`profiles` table** over `auth.users.raw_user_meta_data` — joins and queries are cleaner; standard Supabase pattern.
- **Cookie session via `@supabase/ssr`** over localStorage tokens — SSR helpers handle CSRF/refresh; FastAPI just reads a cookie.
- **Free-for-all + attribution** over owner assignment (Q10 a) — matches the stated goal "know who touched the lead," minimal schema, upgradable later without data migration.
- **Scalar `last_touched_*` columns** over event log — today's need is a single recent-touch indicator; full activity history is feature A, separate spec.
- **No self-signup** — admin-created only, per requirement.
- **Bootstrap admin via env** over manual SQL — reproducible, works on fresh Supabase projects.
