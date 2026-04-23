# Salesforce Integration — Design Spec

**Date:** 2026-04-23
**Status:** Draft — awaiting review

## Goal

When a rep clicks **Call** on a practice for the first time, create a Salesforce Lead. On every subsequent call, update the same Lead — pushing the full call history and an incrementing call count. Before anything is written to Salesforce, the rep's raw note is polished by GPT into a professional CRM entry. The Salesforce Lead ID and owner name are stored on the practice so the team can see who owns the lead in SF without leaving the app.

## Scope

### In scope
- Salesforce REST auth via **Username-Password OAuth** (Connected App + SF credentials in `.env`).
- Single standard **Lead** object with two custom fields (`Call_Count__c`, `Call_Notes__c`).
- Modal on Call click: rep types a note, clicks **Save & Call**, single action does note-log + SF sync + RingCentral dialer.
- GPT polishing of rep's raw note (gpt-4o-mini, silent auto-save, fallback on OpenAI error).
- New Supabase columns for SF linkage + call tracking.
- New endpoint `POST /api/practices/{place_id}/call/log`.
- Fail-soft SF sync: local save always succeeds; SF failures surface as a non-blocking warning.
- Mock mode: feature works without SF credentials (local log only, no SF calls).

### Out of scope (future)
- Salesforce **Task** objects per call (v2; current design uses a single appending text field).
- JWT Bearer auth for SF (production-grade; current design uses username-password which is simpler but being deprecated by SF long-term).
- Two-way sync (SF → app). Owner refreshes on each push; status/stage changes in SF don't flow back.
- Custom score fields on the Lead (`Lead_Score__c` etc.) — v2 if requested.
- Account/Contact modeling instead of Lead.
- Audit trail of raw vs polished notes.
- Bulk sync / backfill of existing practices.

## Architecture

```
[Rep clicks Call]
       │
       ▼
[CallModal textarea + Save&Call]
       │  POST /api/practices/{id}/call/log {note}
       ▼
[Backend: call_log.append_call_note]
       │  1. polish via GPT (skip if empty)
       │  2. append "[ts UTC] {rep}: {polished}" to practices.call_notes
       │  3. increment practices.call_count
       ▼
[Backend: salesforce.sync_practice]
       │  if sf_lead_id null → create_lead + get_owner
       │  else              → update_lead (Call_Count__c, Call_Notes__c)
       │  stamp salesforce_synced_at
       │  fail-soft: return {practice, sf_warning?}
       ▼
[Frontend: close modal, openRingCentralCall(practice.phone)]
```

Three isolated backend modules, one endpoint, one modal component. Matches the pattern already established by email outreach and analysis.

## Data model changes

### Supabase: `practices` table

```sql
alter table practices
  add column salesforce_lead_id     text,
  add column salesforce_owner_id    text,
  add column salesforce_owner_name  text,
  add column salesforce_synced_at   timestamptz,
  add column call_count             integer not null default 0,
  add column call_notes             text;

create index idx_practices_sf_lead_id on practices(salesforce_lead_id);
```

### Salesforce: custom Lead fields (manual setup)

| API name          | Type                          | Purpose                            |
| ----------------- | ----------------------------- | ---------------------------------- |
| `Call_Count__c`   | Number(8, 0), default 0       | Running count of calls from the app |
| `Call_Notes__c`   | Long Text Area (32,768 chars) | Full appended call log (newest at bottom) |

No triggers, workflows, or validation rules needed. Field-level security must allow read/write for the integration user.

### Append format

```
[2026-04-23 10:22 UTC] Sarah Khan: Left voicemail. Contact seemed preoccupied; planning to retry Thursday around 2pm.
[2026-04-24 14:05 UTC] Sarah Khan: Spoke with office manager. Interested in a demo next week.
```

- Timestamp: UTC, format `YYYY-MM-DD HH:MM UTC`.
- Rep name: from `profiles.full_name` (already stamped on `last_touched_by_name`).
- Polished note: GPT output, or raw note + ` (unpolished)` on GPT failure, or `(call logged, no note)` if empty.
- Chronological, newline-separated. Backend always rewrites the whole `Call_Notes__c` field on PATCH (not a delta).

## Auth: Salesforce Username-Password OAuth

### One-time setup (user does in SF)
1. **Setup → App Manager → New Connected App**. Enable OAuth, pick API (Full access) + refresh_token scope. Callback URL can be `https://localhost` (unused).
2. Note **Consumer Key** (client_id) and **Consumer Secret** (client_secret).
3. Create an **integration user** (or reuse a seat) with API Enabled permission and access to the Lead object + the two custom fields.
4. Get the user's **security token** (Setup → Personal → Reset Security Token — it's emailed).

### Runtime flow
- On the first API call of a process (and on 401/419 refresh), POST to `https://login.salesforce.com/services/oauth2/token`:
  ```
  grant_type=password
  client_id={SF_CLIENT_ID}
  client_secret={SF_CLIENT_SECRET}
  username={SF_USERNAME}
  password={SF_PASSWORD}{SF_SECURITY_TOKEN}    # concatenated, no separator
  ```
- Response:
  ```json
  {
    "access_token": "00D5f...!AQ...",
    "instance_url": "https://yourorg.my.salesforce.com",
    "token_type": "Bearer",
    "id": "...", "issued_at": "...", "signature": "..."
  }
  ```
- Cache `access_token` + `instance_url` in-process. No expiry is returned by this flow, so invalidate on 401 and refetch.
- All subsequent API calls use `Authorization: Bearer {access_token}` against `{instance_url}/services/data/v60.0/...`.

Module: `src/sf_auth.py` — mirrors the pattern of `src/ms_auth.py` (module-level cache + async lock).

### If auth fails or creds are missing → mock mode
If any of `SF_CLIENT_ID`, `SF_CLIENT_SECRET`, `SF_USERNAME`, `SF_PASSWORD`, `SF_SECURITY_TOKEN` are empty, `salesforce.sync_practice` returns `{"skipped": True, "reason": "sf_not_configured"}` without raising. The rest of the call log flow still runs.

## Backend modules

### `src/sf_auth.py`
```
async def get_access_token() -> tuple[str, str]:
    """Returns (access_token, instance_url). Cached until 401."""

def invalidate_token() -> None:
    """Clear cached token after 401, forces next call to re-auth."""

def is_configured() -> bool:
    """True if all 5 SF_* env vars are set."""
```

### `src/salesforce.py`
```
async def create_lead(practice: Practice, call_note_line: str, rep_name: str) -> dict:
    """POST /services/data/v60.0/sobjects/Lead/. Returns the SF response."""

async def update_lead(sf_lead_id: str, call_count: int, call_notes: str) -> None:
    """PATCH /services/data/v60.0/sobjects/Lead/{id}. 204 No Content on success."""

async def get_owner(sf_lead_id: str) -> tuple[str, str]:
    """GET /services/data/v60.0/sobjects/Lead/{id}?fields=Id,OwnerId,Owner.Name. Returns (owner_id, owner_name)."""

async def sync_practice(
    practice: Practice, polished_line: str, rep_name: str
) -> dict:
    """
    Orchestrates create-or-update.
    Returns {'sf_lead_id': str, 'sf_owner_id': str, 'sf_owner_name': str, 'synced_at': iso}
    or {'skipped': True, 'reason': str} on mock mode / auth failure.
    On non-skip failure, raises — caller decides how to surface.
    """
```

Lead field mapping on CREATE (see "Salesforce request bodies" below). On UPDATE, only `Call_Count__c` and `Call_Notes__c` are PATCHed — we do not touch Status or other fields so reps can manage them freely inside SF.

### `src/call_log.py`
```
async def polish_note(raw_note: str) -> str:
    """
    GPT-4o-mini single-shot. Prompt in code below.
    Returns polished text; on OpenAI error returns raw_note + ' (unpolished)'.
    Returns '(call logged, no note)' if raw_note is blank.
    """

async def append_call_note(
    place_id: str, raw_note: str, profile: Profile
) -> tuple[Practice, dict | None]:
    """
    1. Loads practice.
    2. Polishes note.
    3. Builds '[YYYY-MM-DD HH:MM UTC] {rep}: {polished}' line.
    4. Appends to practice.call_notes (newline-separated; empty → just the line).
    5. Increments practice.call_count.
    6. Persists via storage.update_practice_fields (also stamps last_touched_by).
    7. Calls salesforce.sync_practice(...). On failure, captures warning but does NOT roll back local save.
    8. Returns (updated_practice, sf_warning_or_none).
    """
```

### GPT prompt

```
You are a sales rep's assistant logging a call in a CRM. Given the rep's
raw note, produce one clear CRM entry that captures outcome and next steps.

Rules:
- 1-3 sentences, max ~200 characters
- Past tense, third person, professional tone
- Only use facts present in the raw note — do not invent details
- No greeting, no sign-off, no bullet points, no quotation marks

Rep note:
{raw_note}
```

Model: `gpt-4o-mini`. Temperature: 0.3. Max tokens: 120.

## API surface

### `POST /api/practices/{place_id}/call/log`

**Auth:** `get_current_user` (any signed-in rep).

**Request:**
```json
{ "note": "left vm, sounded annoyed, gonna retry thu" }
```

Empty or whitespace-only `note` is accepted — produces a `(call logged, no note)` entry.

**Response (success, SF sync worked):**
```json
{
  "practice": { /* full Practice payload with refreshed call_count, call_notes, salesforce_* fields */ },
  "sf_warning": null
}
```

**Response (success, SF sync skipped or failed — local save still succeeded):**
```json
{
  "practice": { /* call_count and call_notes updated, salesforce_* unchanged if failed */ },
  "sf_warning": "Salesforce sync failed: {message}. Local log saved."
}
```

**Errors:**
- 401 — not signed in.
- 404 — place_id not found.
- 500 — storage / GPT failure (local save itself broke).

## Salesforce request bodies

### CREATE — `POST {instance_url}/services/data/v60.0/sobjects/Lead/`

```json
{
  "Company": "Houston Family Dental",
  "LastName": "Office",
  "Phone": "+17135551234",
  "Email": "hello@houstonfamilydental.com",
  "Website": "https://houstonfamilydental.com",
  "Street": "1234 Main St, Houston, TX 77002",
  "City": "Houston",
  "Industry": "Healthcare",
  "LeadSource": "HV Sales Intel",
  "Status": "Working - Contacted",
  "Rating": "Hot",
  "Description": "Lead Score: 82 | Urgency: 70 | Hiring Signal: 60",
  "Call_Count__c": 1,
  "Call_Notes__c": "[2026-04-23 10:22 UTC] Sarah Khan: Initial outreach call"
}
```

Field mapping rules:

| Lead field         | Source                                                                 | Notes                                                           |
| ------------------ | ---------------------------------------------------------------------- | --------------------------------------------------------------- |
| `Company`          | `practice.name`                                                         | Required by SF.                                                 |
| `LastName`         | `"Office"` (literal)                                                   | Required by SF; v1 uses placeholder.                            |
| `Phone`            | `practice.phone`                                                        | Passed as-is; SF accepts varied formats.                        |
| `Email`            | `practice.email` (nullable)                                             | Omitted from payload if null.                                   |
| `Website`          | `practice.website` (nullable)                                           | Omitted if null.                                                |
| `Street`           | `practice.address` (full string)                                        | We don't split address components in v1.                        |
| `City`             | `practice.city` (nullable)                                              | Omitted if null.                                                |
| `Industry`         | `"Healthcare"` (literal)                                                | All HV leads are healthcare practices.                          |
| `LeadSource`       | `"HV Sales Intel"` (literal)                                            | Identifies the source in SF reports.                            |
| `Status`           | `"Working - Contacted"` (literal)                                       | Rep just dialed, so this stage reflects reality.                |
| `Rating`           | Derived from `practice.lead_score`: ≥75 → Hot, ≥50 → Warm, else Cold.   | Falls back to `"Warm"` if score is null.                        |
| `Description`      | `"Lead Score: X \| Urgency: Y \| Hiring Signal: Z"`                      | Built from `practice.lead_score`, `urgency_score`, `hiring_signal_score`. Omitted if none scored. |
| `Call_Count__c`    | `1`                                                                     | First call.                                                     |
| `Call_Notes__c`    | The single formatted line for this call.                                | Newly created.                                                  |

Only non-null, present fields are included in the POST body — we do not send `"Email": null`.

### UPDATE — `PATCH {instance_url}/services/data/v60.0/sobjects/Lead/{sf_lead_id}`

```json
{
  "Call_Count__c": 3,
  "Call_Notes__c": "[2026-04-21 14:10 UTC] Sarah Khan: Left voicemail.\n[2026-04-22 09:15 UTC] Sarah Khan: Spoke with receptionist, call back Thursday.\n[2026-04-23 10:22 UTC] Sarah Khan: Confirmed meeting Friday 2pm."
}
```

Returns HTTP 204 No Content on success. Only these two fields are PATCHed on subsequent calls; Status, Rating, Description are owned by the rep inside SF after the initial create.

### OWNER FETCH — `GET {instance_url}/services/data/v60.0/sobjects/Lead/{sf_lead_id}?fields=Id,OwnerId,Owner.Name`

```json
{
  "Id": "00Q5f00000ABCDEFG",
  "OwnerId": "0055f00000XYZ",
  "Owner": { "attributes": {...}, "Name": "Sarah Khan" }
}
```

Fetched once after create, and on every subsequent update (owner can be reassigned in SF). Extracted as `(OwnerId, Owner.Name)` and written to `salesforce_owner_id` + `salesforce_owner_name`.

## Frontend changes

### Component: `web/components/call-log-modal.tsx` (new)

Props: `{ practice, open, onClose, onLogged }`.

Structure:
- Overlay + centered card.
- Header: "Log call — {practice.name}".
- Textarea: placeholder "What happened? (we'll polish this for Salesforce)".
- Two buttons: [Cancel] (grey) and [Save & Call] (teal).
- Save & Call:
  1. POST `/api/practices/{id}/call/log` with `{ note }`.
  2. On success, call `onLogged(response)` (parent refreshes practice state; shows `sf_warning` if present).
  3. Close modal.
  4. `openRingCentralCall(practice.phone)` (existing helper).
- Loading state: disable buttons, spinner on Save & Call.
- Empty note is allowed; submits with `note: ""`.

### Component: `web/components/call-button.tsx` (modify)

Currently opens RingCentral directly. Change to: open the modal instead. The existing RingCentral handoff moves into the modal's Save & Call handler.

Accepts a new prop `onLogged?: (response) => void` so the parent can refresh.

### Component: `web/components/practice-card.tsx` (light edit)

Wire `onLogged` from the parent into `<CallButton>`. When the response comes back, update the local practice state so the card shows refreshed `call_count`, `last_touched_*`, and `salesforce_owner_name`.

Add a compact "Last call" strip (visible when `practice.call_count > 0`):
```
📞 3 calls · last logged 2m ago · owner: Sarah Khan (SF)
```

### Component: `web/app/practice/[place_id]/page.tsx` (light edit)

Repurpose the existing (currently disabled) **Activity** tab inside `ActionsPanel` as the **Call log** tab. Read-only view of `practice.call_notes` — styled as a chronological list (parse by newline, one entry per line). At the top: a button **[+ Log call]** that opens the same `<CallLogModal>`. Also show the summary strip: `Total calls: N · Last synced to SF: 2m ago · Owner: Sarah Khan`.

No new tab added — Notes / Email / Call log are the three tabs.

### API client: `web/lib/api.ts`
```ts
export async function logCall(placeId: string, note: string) {
  return apiFetch(`/api/practices/${placeId}/call/log`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  })
}
```

### Types: `web/lib/types.ts`

Extend `Practice`:
```ts
salesforce_lead_id: string | null
salesforce_owner_id: string | null
salesforce_owner_name: string | null
salesforce_synced_at: string | null
call_count: number
call_notes: string | null
```

Mock data gets these new fields populated with sensible defaults (`0`, `null`).

## Env vars

Add to `.env` and `.env.example`:

```
SF_CLIENT_ID=
SF_CLIENT_SECRET=
SF_USERNAME=
SF_PASSWORD=
SF_SECURITY_TOKEN=
SF_LOGIN_URL=https://login.salesforce.com   # or https://test.salesforce.com for sandbox
SF_API_VERSION=v60.0
```

Add to `Settings` class in `src/settings.py` (all strings, all default `""`).

## Error handling & edge cases

| Situation                                | Behavior                                                                                   |
| ---------------------------------------- | ------------------------------------------------------------------------------------------ |
| OpenAI key missing or API errors         | Polish returns `raw + " (unpolished)"`. Log append proceeds. SF sync proceeds.             |
| Empty note from rep                      | Append `[ts] {rep}: (call logged, no note)`. Skip GPT entirely.                            |
| All SF env vars empty                    | `sync_practice` returns `{skipped: True, reason: "sf_not_configured"}`. Endpoint returns 200 with `sf_warning: null`. |
| SF auth fails (bad creds)                | Endpoint returns 200 with `sf_warning: "Salesforce sync failed: ..."`. Local save persisted. Next click retries auth. |
| SF PATCH fails with 404 (Lead deleted)   | Clear `salesforce_lead_id` locally and retry as CREATE. One automatic retry per call.       |
| SF PATCH returns 401                     | `sf_auth.invalidate_token()`, retry once. If it fails again, surface warning.              |
| Supabase write fails                     | 500. Endpoint rolls back — call is not considered logged.                                  |
| Counter / SF Call_Count drift            | Self-healing: every PATCH sends the full local count and full notes string, overwriting SF. |
| Concurrent calls to same practice        | Small race window (read count, write count+1). Acceptable for v1; single-user-per-lead is typical. |
| Network timeout on SF POST/PATCH         | `httpx` 15s timeout. Timeout → warning, local save persisted.                              |

## Testing

Mirrors the pattern of `tests/test_ms_auth.py`, `tests/test_email_send.py`, `tests/test_email_gen.py`.

- `tests/test_sf_auth.py` — 3 tests: token fetch + cache + 401 invalidation; `is_configured()` with missing vars.
- `tests/test_salesforce.py` — 4 tests: create_lead payload shape, update_lead PATCH body, get_owner parsing, sync_practice skips when not configured.
- `tests/test_call_log.py` — 4 tests: polish_note happy path (GPT mocked), polish_note fallback on OpenAI error, append_call_note formats line correctly, append_call_note increments count.
- `tests/test_api_call_log.py` — 3 tests: endpoint requires auth (401), happy path returns practice+null_warning, SF failure returns practice+warning string.

All tests use mocked HTTP (`respx` or `httpx.MockTransport`) and a mocked `AsyncOpenAI`. No real SF or OpenAI calls in CI.

## Non-goals / explicitly not happening in v1

- Rep cannot preview/edit polished note before it's saved (decision confirmed: silent auto-save).
- Notes are not undoable once appended. To correct a mistake, reps edit in SF or we add editing in v2.
- Raw note is not persisted anywhere after polishing completes.
- We don't send analysis scores to separate custom SF fields — they go into `Description` as a single line.
- Status/Rating are set on CREATE only. Further lifecycle is managed in SF.
- No webhook / inbound sync from SF back to Supabase.
- Pressing Call multiple times rapidly is not debounced server-side in v1 (UI disables the button while the POST is in flight).

## Open questions (resolved)

1. ~~Auth flow?~~ → Username-Password OAuth.
2. ~~Custom SF fields for scores?~~ → No, scores go in `Description`.
3. ~~Modal-on-click vs inline?~~ → Modal on click (option 1).
4. ~~GPT preview vs silent?~~ → Silent auto-save.
5. ~~Account/Contact vs Lead?~~ → Lead.
6. ~~Update Status on every call?~~ → No, Status set on CREATE only.

## Success criteria

- First call on a fresh practice creates a SF Lead; `salesforce_lead_id` populated; `salesforce_owner_name` visible on the card.
- Second call PATCHes the same Lead; `Call_Count__c` goes from 1 to 2; `Call_Notes__c` has both timestamped entries.
- Rep's raw note is noticeably cleaner in SF than what they typed.
- With SF creds missing, modal still works end-to-end (local log + dialer); no errors shown to rep.
- With SF creds present but wrong, call still logs locally; rep sees a discreet warning; next corrected attempt self-heals.
- `pytest -q` passes; frontend typechecks clean.
