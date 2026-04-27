# Leads Workspace + Personalization — Design Spec

**Date:** 2026-04-27
**Status:** Draft — awaiting review

## Goal

Make the leads sidebar a workflow-grade workspace and make the AI outputs (analysis + call script) actually personalized to the practice. Five jobs:

1. **State persistence** — navigating to a practice page and back returns the user to the exact same map state (search, filters, list, selection, scroll).
2. **Local search bar** — instant substring filter over the loaded sidebar list.
3. **Multi-tag visibility** — a record can carry multiple status milestones simultaneously (e.g., `RESEARCHED` + `SCRIPT_READY`) and show up under any of those filters.
4. **Owner filter + assignment** — admins assign practices to SDRs; SDRs see their assigned book by default.
5. **Personalized AI outputs** — extract the practice's lead doctor name and direct phone from their website during analysis; feed those + reviews + location into the call-script prompt so each script is specific to the practice.

## Scope

### In scope
- Sidebar local search bar (substring over `name`, `address`, `city`, `owner_name`, `website_doctor_name`).
- New filter UI: tags multi-select (replaces single status dropdown for filtering), enriched tri-state, owner dropdown.
- URL query param mirroring of filters (`q`, `search`, `cat`, `rating`, `tags`, `enriched`, `owner`, `sel`).
- sessionStorage cache of full page state (`practices`, filters, `selectedId`, scroll) so back-from-practice restores synchronously without re-fetch or flicker.
- New schema columns: `tags text[]`, `assigned_to`, `assigned_at`, `assigned_by`, `website_doctor_name`, `website_doctor_phone`.
- `add_tags(place_id, tags[])` helper that auto-tags on system events: analyze → `RESEARCHED`, script gen → `SCRIPT_READY`, Clay success → `ENRICHED`, first call/email out → `CONTACTED`, inbound email → `REPLIED`, status change to MEETING SET / CLOSED WON / CLOSED LOST → matching tag.
- One-time backfill migration that derives tags for existing rows from `status`, analysis fields, `enrichment_status`, `call_count`.
- Admin-only assignment UI on the practice page header (dropdown next to status). `PATCH /api/practices/{place_id}` accepts `assigned_to`.
- SDR default view filter: `owner = me`. Admin default: no owner filter.
- `crawl_website` extended to return `{text, doctor_name, doctor_phone}` instead of just text.
- Analyzer stores extracted doctor name + phone into the new columns. Phone never overwrites the Google Places `phone`.
- Practice card + `PracticeInfo` panel surface the doctor name and direct line, visually distinct from the receptionist phone.
- `generate_script` accepts richer context (city, state, rating, review_count, doctor name, owner name/title, 2-3 verbatim review excerpts) and the system prompt is rewritten to require their use.
- Tests for: validators, doctor extraction, scriptgen prompt construction, tags helper, backfill, frontend state-persistence + filter logic.

### Out of scope
- Manual user editing of tags (system-managed only).
- Bulk-assign UI in the admin panel (admin assigns one practice at a time from its page).
- Re-extraction of doctor info on every rescan (only on first analysis or explicit re-analyze).
- Server-side practice search by name (Q1 confirmed local-only).
- Saved filter presets / "views".
- Notifying an SDR when a lead is assigned to them.
- Reassignment audit history beyond `assigned_by` + `assigned_at` (overwritten on each reassign).
- Multi-select for any other filter besides tags.

## Schema changes

```sql
-- Multi-tag visibility (orthogonal to status)
alter table practices add column if not exists tags text[] not null default '{}';
create index if not exists idx_practices_tags on practices using gin (tags);

-- Assignment workflow
alter table practices add column if not exists assigned_to uuid references profiles(id);
alter table practices add column if not exists assigned_at timestamptz;
alter table practices add column if not exists assigned_by uuid references profiles(id);
create index if not exists idx_practices_assigned_to on practices (assigned_to);

-- Website-extracted doctor info (separate from Google Places `phone`)
alter table practices add column if not exists website_doctor_name text;
alter table practices add column if not exists website_doctor_phone text;
```

### Tag taxonomy

Tags are uppercase string constants, system-managed, append-only per practice. The set:

| Tag | Added when |
|---|---|
| `RESEARCHED` | analyzer succeeds (lead_score written) |
| `SCRIPT_READY` | call script generated |
| `ENRICHED` | Clay returns `enrichment_status='enriched'` |
| `CONTACTED` | first call logged OR first email sent |
| `REPLIED` | first inbound email matched |
| `MEETING_SET` | status set to `MEETING SET` |
| `CLOSED_WON` | status set to `CLOSED WON` |
| `CLOSED_LOST` | status set to `CLOSED LOST` |

A single helper does the dedupe + append:
```python
def add_tags(place_id: str, new_tags: list[str], touched_by: str | None = None) -> None:
    """Append tags to the practice's tags array; existing tags are preserved.
    Uses postgres array_append + array(select distinct unnest) to dedupe."""
```

### Backfill migration

```sql
update practices set tags = (
  select array_agg(distinct t) from unnest(array[
    case when lead_score is not null then 'RESEARCHED' end,
    case when call_script is not null then 'SCRIPT_READY' end,
    case when enrichment_status = 'enriched' then 'ENRICHED' end,
    case when call_count > 0 then 'CONTACTED' end,
    case when status = 'MEETING SET' then 'MEETING_SET' end,
    case when status = 'CLOSED WON' then 'CLOSED_WON' end,
    case when status = 'CLOSED LOST' then 'CLOSED_LOST' end
  ]) t where t is not null
) where tags = '{}'::text[];
```

Idempotent (only writes rows whose tags array is empty). Run once after migration.

## Sidebar filtering

### Search bar (local)

A new `<input type="search">` above the existing filter dropdowns. Debounced 150ms. Filters the in-memory `practices` array client-side by case-insensitive substring on:
- `name`
- `address`
- `city`
- `owner_name`
- `website_doctor_name`

Empty string → no filter.

### Filter bar (replaces current single row)

Contained in `web/components/filter-bar.tsx`, expanded to:

| Control | Type | Behavior |
|---|---|---|
| Search | text input | local substring (above) |
| Category | dropdown | unchanged from today |
| Min rating | slider | unchanged from today |
| Tags | multi-select chip dropdown | record matches if it has ANY selected tag; empty = no filter |
| Enriched | tri-state toggle: `Any` / `Enriched` / `Not enriched` | matches `enrichment_status='enriched'` for "Enriched", else for "Not enriched" |
| Owner | dropdown of users (fetched from `/api/admin/users` for admin, just self for SDR) | matches if `assigned_to == X` OR `last_touched_by == X`; empty = no filter |

The current single-value `status` filter is **removed from the filter bar** (filtering moves to tags). The `status` field itself stays in the schema and continues to drive the badge + sequential pipeline progression on the practice page.

### Filter logic precedence

```
filtered = practices
  .filter(searchSubstring matches name/address/city/owner_name/website_doctor_name)
  .filter(category == filter || filter == "")
  .filter(rating >= minRating)
  .filter(tags.some(t => selectedTags.includes(t)) || selectedTags.length == 0)
  .filter(enrichmentMatches(enrichedFilter))
  .filter(assigned_to == ownerFilter || last_touched_by == ownerFilter || ownerFilter == "")
  .sort(lead_score desc nulls last)
```

## State persistence

### URL query params

```
/?q=Dental+Boise&search=smile&cat=dental&rating=4&tags=SCRIPT_READY,RESEARCHED&enriched=yes&owner=<uuid>&sel=ChIJ...
```

- `q` = original Google search term used to populate the list (so a fresh tab can re-hydrate)
- `search` = local search string
- `cat` = category
- `rating` = min rating
- `tags` = comma-separated tag list
- `enriched` = `yes` | `no` | omit
- `owner` = user UUID
- `sel` = selected `place_id`

Implemented with a `useUrlState` hook that wraps `useSearchParams` + `router.replace` (no full page reload).

### sessionStorage snapshot

Key: `leads-workspace-snapshot-v1`. Value: JSON `{practices, filters, selectedId, scrollTop, savedAt}`.

- Updated whenever `practices`, filters, selection, or scroll change (debounced 200ms for scroll).
- On mount of `/`, if a snapshot exists AND `savedAt` is within 30 minutes, restore everything synchronously before first paint. Otherwise call `listPractices({})`.
- A "Refresh" button in the toolbar manually clears the snapshot and refetches.
- Hard refresh (Ctrl+R) is *expected* to clear in-page React state but session storage stays — so users coming back from a tab restore land on their cached view. To deliberately clear, use the Refresh button.

This gives the user the requested behavior: "click into a practice, click back, and the sidebar is *exactly* as I left it."

## Assignment workflow

### Backend

`PATCH /api/practices/{place_id}` accepts a new optional field:
```python
class PatchPracticeRequest(BaseModel):
    ...existing...
    assigned_to: str | None = None  # UUID or empty string to clear
```
Authorization: only `admin` role can change `assigned_to`. SDRs editing other fields don't pass it. On change, sets `assigned_at = now()`, `assigned_by = current_user.id`.

### Frontend

On the practice page header, next to the status dropdown, render a new "Owner: <name>" dropdown when the current user is admin. Shows:
- Empty (unassigned)
- Each SDR + admin

Saves immediately on change (no separate save button). Reflects in the sidebar's Owner column on next return.

### Default views

In `useUrlState`'s init logic:
- If `owner` is not present in URL AND user is SDR → default to their own UUID.
- If user is admin → default to no filter.

SDRs can still clear it via the dropdown.

## Personalized analysis

### `crawl_website` returns structured data

Signature change:
```python
async def crawl_website(url: str) -> dict:
    """Returns {text, doctor_name, doctor_phone, pages_visited}."""
```

`text` matches today's combined text (no behavior change for downstream callers that already use it as a string — they migrate to the new shape in the same change).

### Doctor name extraction

In priority order:
1. Pages crawled at high priority: `/about`, `/team`, `/staff`, `/providers`, `/our-doctors`, `/meet-the-doctor`. The crawler's `PRIORITY_PATTERNS` regex is extended.
2. Heuristic regex over those pages first, then fallback to homepage:
   - `(?:Dr\.|Doctor)\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)` (e.g., "Dr. Sarah J. Smith")
   - `([A-Z][a-z]+\s+[A-Z][a-z]+),?\s*(MD|DDS|DO|DPM|DC|FNP|PA-C)` in `<h1>`/`<h2>`/`<title>`
3. If multiple candidates found, pick the most-frequently-mentioned across pages. If tied, pick the one nearest the `<h1>` of the homepage.
4. If `openai_api_key` is set and heuristics found nothing, send the first 4000 chars of the about/team page text to GPT with a strict extraction prompt: `Return only the lead doctor's full name including title (e.g., "Dr. Sarah Smith") or "NONE" if absent.` Result is parsed; "NONE" → `None`.

If no name found, `doctor_name = None`.

### Doctor phone extraction

In priority order:
1. Find phone numbers (regex `(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}`) within the same `<section>` / `<div>` / paragraph as the doctor name. Take the first.
2. If none near the name, scan the `/contact` page text for phones labelled "Direct", "Doctor", "Personal", "Mobile", "Cell".
3. Skip any phone that, after digit-normalization, equals the practice's Google Places `phone`.
4. Validate: must be 10 digits (after stripping country code).

If no qualifying phone found, `doctor_phone = None`.

### Storage

`update_practice_analysis` (in `src/storage.py`) is extended to also persist `website_doctor_name` and `website_doctor_phone` from the analyzer's return dict. Stored even when GPT fails — heuristic-only output is fine.

## Personalized script

### `generate_script` signature

```python
async def generate_script(
    name: str,
    category: str | None,
    summary: str | None,
    pain_points: str | None,        # JSON string
    sales_angles: str | None,        # JSON string
    *,
    city: str | None,
    state: str | None,
    rating: float | None,
    review_count: int | None,
    website_doctor_name: str | None,
    owner_name: str | None,
    owner_title: str | None,
    review_excerpts: list[str] | None,  # 2-3 short verbatim quotes
) -> dict
```

### Prompt rewrite

The system prompt is replaced with one that requires:

- **Opening section**: Use `website_doctor_name` if present (`"Hi, may I speak with Dr. Smith?"`); otherwise `owner_name + owner_title`; otherwise practice name. Include city ("a [city]-area practice").
- **Discovery questions**: Reference 1-2 specific items from `pain_points` directly (not generic). Example: "I noticed reviews mentioning 'long wait times for new patient appointments' — is staffing a contributor to that?"
- **Pitch section**: Quote one item from `review_excerpts` verbatim with leading attribution ("One of your patient reviews mentioned, '...' — that's exactly the kind of thing our front desk staffing is designed to address.").
- **Objection handling**: Keep the four standard objections but tailor the wording to `category`.
- **Closing**: Reference `city` ("we've placed staff at multiple [city]-area clinics").

### Endpoint wiring

`GET /api/practices/{place_id}/script` (and the regenerate POST) builds the context dict from the practice row:
- `city`, `state`, `rating`, `review_count` directly from the row
- `website_doctor_name` from the new column
- `owner_name`, `owner_title` from Clay enrichment (may be `None` if not enriched)
- `review_excerpts` lazily — call `fetch_reviews(place_id, ...)` and pick the 2-3 shortest review texts. Cached on the practice as `review_excerpts text` column? **No** — fetched per-script-gen for now (cheap, and reviews change). If that turns out to be slow, we cache later.

Mock script (no OpenAI key) gets the same context shape and substitutes the doctor name into the opening so dev-without-API-key still tests the wiring.

## UI surfacing — doctor info

### Practice card (sidebar)

Below the rating row, when `website_doctor_name` is present, render a new line:
```
Dr. Sarah Smith · (555) 555-0100  [direct]
```
The phone is rendered only if `website_doctor_phone` is present and clickable as `tel:`. The `[direct]` chip distinguishes from the receptionist line.

### Practice info panel (`/practice/[place_id]`)

Existing "Phone" row stays (Google Places phone, labelled "Front desk"). Below it:
```
Direct line:   (555) 555-0100  (from website)
Doctor:        Dr. Sarah Smith
```
Both rows hidden if their fields are null.

## Migration order

1. Schema migration: add columns + indexes.
2. Backfill migration: populate `tags` from existing `status` / analysis / enrichment / call_count.
3. Backend code: tags helper + auto-tagging hooks in analyze/script/email/call-log endpoints.
4. Backend code: `crawl_website` shape change + analyzer wiring + storage.
5. Backend code: `generate_script` signature + prompt rewrite + endpoint context building.
6. Backend code: PATCH `assigned_to` field + admin-only check.
7. Frontend: `useUrlState` + sessionStorage hook.
8. Frontend: filter bar rebuild (search bar, tags multi-select, enriched, owner).
9. Frontend: practice card + info panel doctor surfacing.
10. Frontend: assignment dropdown on practice page header.
11. Tests, smoke test.

## Testing approach

### Backend unit tests
- `tests/test_crawler.py` — fixture HTML (about page with "Dr. Sarah Smith, MD"); assert `doctor_name == "Dr. Sarah Smith"`. Fixture with no doctor → `None`. Phone-near-name extraction. Phone equal to Google `phone` → skipped.
- `tests/test_scriptgen.py` — assert system prompt + user prompt contain `website_doctor_name` when provided. Assert prompt falls back to practice name when None. Mock OpenAI client; assert sent message body includes review excerpts.
- `tests/test_storage.py` — `add_tags` deduplicates, preserves existing, returns updated row.
- `tests/test_api_practices.py` — `/analyze` populates new columns + appends `RESEARCHED` tag. `/script` populates `SCRIPT_READY` tag and uses doctor name in prompt. PATCH `/api/practices/{id}` rejects `assigned_to` change for SDR caller; accepts for admin.
- `tests/test_api_filter.py` — `listPractices` query passes through new filter params if added later (not in scope; client-side filtering for now).

### Backfill verification
A dedicated test runs the backfill SQL on a seeded fixture DB; asserts each combination of pre-existing fields produces the expected tags.

### Frontend tests (Vitest + RTL)
- `state-persistence.test.tsx` — mount `/`, set filters, navigate to `/practice/X`, navigate back, assert filters + selection restored.
- `filter-bar.test.tsx` — search input filters list. Tags multi-select shows union. Enriched tri-state matches correctly. Owner filter matches `assigned_to` OR `last_touched_by`.
- `practice-card.test.tsx` — renders doctor name + direct phone when present, hidden when absent.

### Smoke test (manual, post-deploy)
1. Search "Dental Boise" → list loads → click into a practice → click back → list, filters, selection, scroll restored.
2. Use the new search input → list filters live → reload tab → still filtered (URL param survives).
3. Set Owner = "me" as SDR → list shrinks. Switch to admin → see Owner dropdown, change owner, refresh → SDR's view updates.
4. Analyze a practice with a clear doctor on website → verify doctor name + direct phone show on card and panel, distinct from front desk number.
5. Generate script for that practice → verify GPT output references the doctor by name and quotes a review excerpt verbatim.
6. Verify a practice that has `RESEARCHED` + `SCRIPT_READY` tags shows up under either tag filter.

## Risks

- **Doctor extraction false positives** — heuristics may pick a non-lead doctor (e.g., a rotating associate). Mitigation: prefer most-frequently-mentioned, restrict to about/team pages first, fallback to GPT for ambiguity. If a wrong name lands, the SDR can ignore it; the `phone` field gives them the fallback. We do not yet expose UI to manually override the extracted name (deferred).
- **Cost of GPT-fallback in extraction** — only invoked when heuristics fail; capped at one ~4000-token call per analyze run.
- **sessionStorage snapshot drift** — if the user has multiple tabs open, the last tab's snapshot wins. Acceptable for v1.
- **Tag backfill on a large practices table** — single `update` statement; fine at our current row counts (low thousands). Re-running it is idempotent due to the `where tags = '{}'` guard.
- **Owner filter performance** — combined `assigned_to || last_touched_by` filter is OR'd in client-side filtering for now; if the loaded list grows large we can move to server-side filtering later.
