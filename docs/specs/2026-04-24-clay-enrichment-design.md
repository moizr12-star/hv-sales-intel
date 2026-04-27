# Clay Owner Enrichment — Design Spec

**Date:** 2026-04-24 (revised 2026-04-27 with field-mechanic notes)
**Status:** Backend implemented; Clay-side table setup in progress, see "Clay setup gotchas" below.

## Goal

Let reps enrich a practice on demand with the owner's name, title, email, phone, and LinkedIn by clicking an "Enrich owner" button. The enrichment runs asynchronously through a Clay table (their waterfall does the work), and our app updates the practice row when Clay posts the result back via webhook. While Clay is working, the card shows a pending state and polls for the result.

## Scope

### In scope
- Single primary owner per practice (flat columns on `practices`).
- On-demand trigger from the practice card; no auto-enrichment, no bulk.
- Outbound: POST practice data to a Clay HTTP API source.
- Inbound: authenticated webhook endpoint that Clay POSTs enriched data to.
- Frontend polling of practice status while `enrichment_status === 'pending'`, cap 3 minutes.
- Re-enrichment allowed (warns about credit cost).
- Read-only display of owner fields on the Call Prep page.
- Mock mode: feature works end-to-end without Clay credentials — the trigger endpoint no-ops with `skipped: "clay_not_configured"`.

### Out of scope (future)
- Multiple contacts per practice (separate `contacts` table, v2).
- HMAC-signed webhooks (shared secret is sufficient for v1).
- Auto-enrichment when a practice is analyzed or scored above a threshold.
- Bulk "Enrich all visible" action.
- SSE / Supabase Realtime (v1 uses HTTP polling).
- Editing / correcting owner fields from the UI (read-only for now).
- Email send / click-to-call specifically to owner email (reuses existing UI).
- Tracking Clay credit spend from the app.

## Architecture

```
[Rep clicks Enrich on card]
          │
          ▼
[POST /api/practices/{id}/enrich]
          │  1. loads practice, sets enrichment_status = 'pending'
          │  2. POSTs {place_id, practice_name, website, city, state, phone}
          │     to CLAY_TABLE_WEBHOOK_URL with Bearer CLAY_TABLE_API_KEY
          │  3. returns practice immediately (non-blocking)
          ▼
[Frontend polls GET /api/practices/{id} every 5s while pending]

              ...meanwhile in Clay...
              [HTTP API source receives row]
                      │
                      ▼
              [Find people at company → pick top-ranked owner-ish title]
                      │
                      ▼
              [Email waterfall + phone waterfall + LinkedIn URL]
                      │
                      ▼
              [Send Webhook → POST our backend]

[POST /api/webhooks/clay]
          │  1. verify X-Clay-Secret header
          │  2. upsert owner_* fields by place_id
          │  3. status = 'enriched' (or 'failed' if no owner fields)
          │  4. stamp enriched_at
          │
          ▼
[Next poll from frontend sees new status → stops polling, renders owner card]
```

Three touch points on our side: one outbound call (`src/clay.py`), two FastAPI endpoints (trigger + webhook), one frontend component (`EnrichButton`) plus card/sidebar tweaks. Mirrors the fail-soft, polling-based conventions already used elsewhere (email outreach, analysis).

## Data model

### Supabase: extend `practices`

```sql
alter table practices
  add column if not exists owner_name         text,
  add column if not exists owner_email        text,
  add column if not exists owner_phone        text,
  add column if not exists owner_title        text,
  add column if not exists owner_linkedin     text,
  add column if not exists enrichment_status  text,        -- null | 'pending' | 'enriched' | 'failed'
  add column if not exists enriched_at        timestamptz;
```

Status semantics:
- `null` — never enriched.
- `'pending'` — trigger fired, waiting on Clay webhook.
- `'enriched'` — webhook received and at least one of `owner_name`/`owner_email`/`owner_phone` was populated.
- `'failed'` — webhook received but no useful fields returned (Clay couldn't find an owner).

Re-enrichment flips status back to `'pending'` and clears nothing (prior values stay visible until Clay overwrites them — avoids flicker).

### Practice model (Python)

`src/models.py` — add:
```python
owner_name: str | None = None
owner_email: str | None = None
owner_phone: str | None = None
owner_title: str | None = None
owner_linkedin: str | None = None
enrichment_status: str | None = None
enriched_at: str | None = None
```

Upsert preserve set (`src/storage.upsert_practices`) gains these fields so search/rescan doesn't clobber enrichment.

## Clay setup (one-time, user does this)

1. Create a new Clay table, name it **"HV Owner Enrichment"**.
2. **Add source → HTTP API**. Clay gives you a POST URL and an API key — save both. Define the input schema as these columns (exact names, Clay auto-maps by key):
   - `place_id` (text, required — used as the dedupe key / join back)
   - `practice_name` (text)
   - `website` (text)
   - `city` (text)
   - `state` (text)
   - `phone` (text)
3. **Enrichment columns** (add each and configure):
   - **Find People at Company** — input: `website` (fall back to `practice_name`). Filter: `title contains Owner OR Founder OR CEO OR Practice Manager OR Dentist Owner OR Principal OR Managing Partner`. Limit: 1. Rank by: most senior.
   - **Find Work Email** — input: person from step above. Use waterfall: Findymail → Apollo → Datagma (or whatever you prefer).
   - **Find Mobile Phone** — input: person. Waterfall of your choice.
   - **Find LinkedIn URL** — input: person.
4. **Output mapping columns** (rename the enrichment outputs to these exact keys — the inbound webhook reads them verbatim):
   - `owner_name`
   - `owner_title`
   - `owner_email`
   - `owner_phone`
   - `owner_linkedin`
5. **Send Webhook action** at the end of the table. Configure:
   - URL: `{OUR_BACKEND}/api/webhooks/clay`
   - Method: POST
   - Headers: `X-Clay-Secret: <paste the value of CLAY_INBOUND_SECRET>`, `Content-Type: application/json`
   - Body (JSON): pass `place_id`, `owner_name`, `owner_title`, `owner_email`, `owner_phone`, `owner_linkedin` — whatever's non-empty.
   - Trigger: fire when all enrichment columns are populated (or on timeout, with whatever was found).

That's the whole Clay config. Once saved, the table is live — any POST to its HTTP API source will run the pipeline and call our webhook when done.

## Outbound: `src/clay.py`

```python
async def trigger_enrichment(practice: Practice) -> dict:
    """POST the practice to Clay's HTTP API source. Returns
    {'status': 'pending'} on success or {'skipped': True, 'reason': ...}
    when Clay is not configured."""
```

Contract:
- If `CLAY_TABLE_WEBHOOK_URL` or `CLAY_TABLE_API_KEY` is empty → return `{"skipped": True, "reason": "clay_not_configured"}`.
- Otherwise, POST:
  ```http
  POST {CLAY_TABLE_WEBHOOK_URL}
  Authorization: Bearer {CLAY_TABLE_API_KEY}
  Content-Type: application/json

  {
    "place_id": "real_dental_houston_001",
    "practice_name": "Houston Family Dental",
    "website": "https://hfd.com",
    "city": "Houston",
    "state": "TX",
    "phone": "+17135551234"
  }
  ```
- 2xx → `{"status": "pending"}`. Non-2xx → raise. Caller handles.
- Timeout: 15s. Clay's HTTP API ingest is fast; this is just the row-accept call, not the full pipeline.

## API surface

### `POST /api/practices/{place_id}/enrich`

**Auth:** `get_current_user`.

**Request:** empty body.

Every response shape is identical — `{practice, clay_warning}` where `clay_warning` is always present (`null` on success).

**Response (success):**
```json
{
  "practice": { /* full Practice with enrichment_status='pending' */ },
  "clay_warning": null
}
```

**Response (Clay not configured — mock mode):**
```json
{
  "practice": { /* full Practice, enrichment_status stays whatever it was */ },
  "clay_warning": "Clay not configured. Enrichment skipped."
}
```

**Response (Clay POST failed):**
```json
{
  "practice": { /* full Practice, enrichment_status='failed' */ },
  "clay_warning": "Enrichment trigger failed: ..."
}
```

Errors: 401 (not auth), 404 (practice not found), 500 (storage fails).

Behavior: sets `enrichment_status='pending'` BEFORE calling Clay. If Clay call raises, flips status to `'failed'` and returns warning. Always returns 200 — fail-soft, frontend treats warning as a toast.

### `POST /api/webhooks/clay`

**Auth:** `X-Clay-Secret` header must equal `settings.clay_inbound_secret`. Mismatch → 401.

**Request:**
```json
{
  "place_id": "real_dental_houston_001",
  "owner_name": "Jane Smith",
  "owner_title": "Practice Manager",
  "owner_email": "jane@hfd.com",
  "owner_phone": "+17135559999",
  "owner_linkedin": "https://linkedin.com/in/janesmith"
}
```

All owner fields optional. `place_id` required.

**Behavior:**
- If any of `owner_name`, `owner_email`, `owner_phone` is non-empty → status = `'enriched'`.
- Otherwise (Clay couldn't find anyone) → status = `'failed'`.
- Upsert only the fields present in the payload (don't null out fields Clay didn't return).
- Stamp `enriched_at = now()`.
- Do NOT stamp `last_touched_by` — this is system activity, not rep activity.

**Response:** `200 {"ok": true}`. We don't echo the updated row; Clay doesn't care.

**Errors:**
- 401 — missing/bad `X-Clay-Secret`.
- 404 — `place_id` not found. (Clay retries harmlessly; eventually gives up.)
- 400 — malformed JSON / missing `place_id`.

## Frontend

### New component: `web/components/enrich-button.tsx`

Props: `{ practice, onEnriched, className }`.

Behavior:
- If `enrichment_status === 'pending'` → disabled, spinner, label "Enriching…".
- Else if `enrichment_status === 'enriched'` or `'failed'` → label "Re-enrich", tooltip "Re-enrich (uses credits)".
- Else → label "Enrich owner".
- On click: `await enrichPractice(place_id)` (helper in `api.ts`). On response, call `onEnriched(updatedPractice, warning)`. If `clay_warning` present → `console.warn('[Clay]', warning)`.

Placement: on the practice card, next to Analyze. Not on the Call Prep page (sidebar shows read-only owner).

### Polling hook: `web/lib/use-enrichment-poll.ts`

Custom hook used by `practice-card.tsx`:

```ts
export function useEnrichmentPoll(
  practice: Practice,
  onRefresh: (next: Practice) => void,
) {
  // Polls getPractice(place_id) every 5s while enrichment_status === 'pending'.
  // Stops on success/fail OR after 36 polls (≈3 minutes).
  // Shows a fallback message after 3 min if still pending.
}
```

Poll interval: 5 seconds. Hard cap: 36 iterations. On timeout, the card surfaces an inline note `"Enrichment taking longer than expected — refresh in a bit"` (status stays 'pending' — a real Clay webhook arriving later still heals the row on next page load).

### `practice-card.tsx` — wire the enrich flow + owner mini-card

1. Pull `useEnrichmentPoll(practice, onPatchPractice)` near the top of the component.
2. Add `<EnrichButton>` to the action-buttons row between Analyze and Call Prep.
3. Below the "Last call" strip (if any), render an `<OwnerMiniCard>` when `owner_name || owner_email || owner_phone` is present:
   - One line: `👤 {owner_name} · {owner_title}` (omit title if null).
   - Second line: icons for email / phone / LinkedIn, each a link.
4. If `enrichment_status === 'failed'`: render a tiny red note `"No owner found — try Re-enrich"`.

### `PracticeInfo` sidebar on Call Prep page

Add a new "Owner" block below the category chip. Read-only:
- Name · title
- Email (click-to-copy + mailto: link)
- Phone (click-to-call via existing `openRingCentralCall`)
- LinkedIn (external link, LinkedIn icon)

If `enrichment_status` is `'pending'` → skeleton loading state.
If `'failed'` or status is null and no owner fields → "No owner info yet — enrich from the map."

### `web/lib/api.ts` — new helper

```ts
export interface EnrichResponse {
  practice: Practice
  clay_warning: string | null
}

export async function enrichPractice(placeId: string): Promise<EnrichResponse>
```

### `web/lib/types.ts` — extend `Practice`

```ts
owner_name: string | null
owner_email: string | null
owner_phone: string | null
owner_title: string | null
owner_linkedin: string | null
enrichment_status: "pending" | "enriched" | "failed" | null
enriched_at: string | null
```

Mock data (`web/lib/mock-data.ts`): populate two of the 14 mock practices with realistic owner info so the UI is demo-able without Clay. Rest default to `null` / `null`.

## Env vars

Add to `.env` and `.env.example`:

```
# Clay owner enrichment
CLAY_TABLE_WEBHOOK_URL=
CLAY_TABLE_API_KEY=
CLAY_INBOUND_SECRET=
```

Add to `Settings` (`src/settings.py`): three strings, default `""`.

`CLAY_INBOUND_SECRET` is any random string you generate (e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`). Paste the same value into Clay's Send Webhook headers and our `.env`.

**Note on `CLAY_TABLE_API_KEY`** (revised 2026-04-27): Clay v3 webhook sources expose an "Authentication token" that we send as the `x-clay-webhook-auth` header (not `Authorization: Bearer`). Some webhook sources are unauthenticated (the URL itself contains the secret); in that case `CLAY_TABLE_API_KEY` can be left blank and `src/clay.py` simply omits the auth header. The trigger logic only requires `CLAY_TABLE_WEBHOOK_URL` to be set.

## Clay setup gotchas (2026-04-27)

Captured during the first end-to-end setup against a real Clay workspace. Save anyone re-doing this from re-discovering each one.

1. **Auth header name**: Clay v3 webhook sources require `x-clay-webhook-auth: <token>` (not `Authorization: Bearer ...`, not `x-clay-api-key`). The token is exposed in the source's "Authentication token" panel — click "Refresh auth token" if it's hidden.

2. **Sandbox Mode**: visible top-right of every Clay workbook. When ON, outbound actions (HTTP API, Send Webhook) silently no-op. The button label flips between "Sandbox Mode" (when off) and "Disable Sandbox" (when on). Verify it's OFF before testing.

3. **HTTP API action gating**: by default, Clay refuses to fire the action on a row if any column referenced in the body is null. Two ways around this:
   - **Remove empty values toggle** (in the action's Configure tab) — when ON, null fields are stripped from the body. Doesn't help if Clay also tracks "input readiness" upstream.
   - **Strip optional fields from the body entirely** — only include `place_id` + `owner_name` + `owner_email` (most reliable to populate). Phone and LinkedIn are optional in our schema and our backend handles missing fields fine.

4. **`Custom Waterfall` column type**: Clay auto-types the "Find People at Company" output column as URL because providers often return LinkedIn URLs as a primary value. The column actually stores a Person object with sub-fields (`Full Name`, `LinkedIn Url`, `Current Job Title`). The column **must be retyped to Text** (or Object) for downstream enrichments to read it correctly. Findymail's email finder will silently fail with "Missing input" otherwise.

5. **Account headers carry over malformed entries**: when configuring an HTTP API account, Clay's UI has a placeholder text "Header value" / "Header name" in the empty input fields. If you hit Add before typing anything, those placeholders sometimes get persisted as actual header rows, which then show up as `Header name must be a valid HTTP token ["Header value"]` errors when the action fires. Fix: open the account in Manage accounts and delete any rows with placeholder-text-as-name. Or skip the account model entirely and put headers inline on the action.

6. **"Save and don't run"** vs **"Save and run X rows"**: Clay's Save button has a hidden dropdown. "Save and don't run" is the default and means the action stays dormant — it won't fire on existing rows. To trigger on past rows, pick "Save and run X rows" or use the play icon on the column header.

7. **Field name mapping in column picker**: the picker shows column DISPLAY names which sometimes differ from internal references. When pointing one enrichment's input at another's output (e.g. Findymail Phone needs the Profile URL output), use the column picker dialog (`/` key in formula or click the chevron) — don't hand-type `{{ColumnName}}`.

8. **Phone enrichments need a LinkedIn URL**: every mobile-phone provider in Clay's catalog (LeadMagic, Findymail, Datagma, etc.) takes a LinkedIn profile URL as input, not Full Name + Domain. So the chain becomes: *Find People at Company → Find LinkedIn URL (Champify or similar) → Find Mobile Phone*, even though the first enrichment usually returns a LinkedIn URL embedded in its Person object. The simplest path is to add a Champify "Find professional profile URL" column between people-find and phone-find.

9. **Clay → our backend reachability**: in local dev, Clay's servers can't reach `localhost:8000`. Use `ngrok http 8000` to expose the backend, paste the ngrok URL into Clay's Send Webhook configuration. ngrok-free URLs change on each `ngrok` restart — update Clay every time. Free plan users need to verify their account first (`ngrok config add-authtoken <token>` after sign-up).

10. **Inspect every webhook hit**: ngrok provides a local web UI at `http://127.0.0.1:4040` that shows every request hitting the tunnel, including request body, response body, and timing. This is the fastest way to confirm Clay actually fired the action. If the inspector shows nothing, Clay isn't sending — debug Clay's gating, not the backend.

## Error handling & edge cases

| Situation                                       | Behavior                                                                                                       |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Clay creds missing                              | Trigger endpoint returns `{practice, clay_warning: "Clay not configured..."}`. Status unchanged.               |
| Clay ingest POST fails (network, 5xx, 4xx)      | `enrichment_status='failed'`, warning surfaced. Frontend shows "Enrichment failed — Retry" on the card.        |
| Clay webhook arrives for unknown `place_id`     | 404 to Clay. Clay retries per its policy; if the practice gets deleted between trigger and callback, it drops. |
| Clay webhook arrives with bad/missing secret    | 401. Log the attempt (IP). Nothing written.                                                                    |
| Clay webhook: all owner fields empty            | `enrichment_status='failed'`. Card shows "No owner found".                                                     |
| Clay webhook: some fields empty, some present   | Status `'enriched'`. Persist only non-empty fields. Old fields kept if not re-provided.                        |
| Two rapid Enrich clicks (double-tap)            | UI disables the button during flight. Server-side: second POST still sets status='pending' + re-triggers Clay. Clay may produce two webhook calls — both upsert idempotently. |
| Poll cap hit (3 min) with no webhook yet        | Card shows "Taking longer than expected" note. Status stays `'pending'` in DB — a late webhook still heals.    |
| Rep navigates away during enrichment            | Polling stops on unmount. Status remains `'pending'` in DB. When they come back, `GET /api/practices/{id}` shows whatever state the DB is in (polling resumes if still pending). |

## Testing

Backend (Python, mirrors existing patterns):

- `tests/test_clay.py` — 3 tests: `trigger_enrichment` skips when not configured, POSTs correct payload, raises on non-2xx.
- `tests/test_api_enrich.py` — 4 tests: auth required, happy path flips status to pending and returns warning=null, Clay failure flips status to failed + returns warning, 404 when practice missing.
- `tests/test_api_webhook_clay.py` — 5 tests: auth required via header, happy path upserts owner fields + status='enriched', all-empty payload sets status='failed', partial payload only writes non-null fields, 404 on unknown place_id.

All tests mock HTTP (no real Clay calls). Target: +12 tests → 80 passing total.

Frontend: typecheck clean. No unit tests added for the polling hook in v1 (follow existing convention — no frontend tests yet in this codebase).

## Non-goals (explicit)

- No dashboard showing Clay credit usage.
- No "draft owner outreach email" action — existing email flow stays on the business email; tying to owner_email is a v2.
- No UI for manually editing owner fields. Correction requires re-enrichment or direct DB edit.
- No storage of raw Clay payload / audit trail. Fields only.
- No batching of Clay calls. Every click = 1 row = 1 POST.

## Open questions (resolved)

1. ~~Single owner vs multiple contacts?~~ → Single (A).
2. ~~On-demand vs auto-enrichment?~~ → On-demand.
3. ~~Button placement?~~ → Practice card only; Call Prep shows read-only.
4. ~~Webhook auth?~~ → Shared secret header.
5. ~~Polling vs realtime?~~ → HTTP polling every 5s, cap 3 min.
6. ~~Re-enrichment allowed?~~ → Yes, button label becomes "Re-enrich".

## Success criteria

- Rep clicks Enrich → card shows spinner within <500ms and `enrichment_status='pending'` is visible via GET.
- Clay round-trip under 2 minutes in 90% of cases. Card auto-updates the moment the webhook lands.
- Enriched practices show name · title · clickable email / phone / LinkedIn inline on the card.
- Clay not configured: UI still works, button shows a warning toast instead of silently doing nothing.
- Clay returns no one: card clearly says "No owner found" with a Retry option.
- Re-enrich on an already-enriched practice refreshes fields in place; no duplicate state, no flicker.
- `pytest -q` passes (80 tests). `npx tsc --noEmit` clean.
