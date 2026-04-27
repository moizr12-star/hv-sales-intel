# Clay Owner Enrichment Implementation Plan

> **Status:** Backend implemented (Tasks 1–13). Task 14 (E2E smoke test) in progress against a real Clay workspace — see [spec § Clay setup gotchas](../../specs/2026-04-24-clay-enrichment-design.md#clay-setup-gotchas-2026-04-27) for issues found during setup.

> **2026-04-27 amendments:**
> - **Task 4 (`src/clay.py`)**: `CLAY_TABLE_API_KEY` was made optional. `_is_configured()` only checks `CLAY_TABLE_WEBHOOK_URL`. The auth header is `x-clay-webhook-auth` (not `Authorization: Bearer`) and is only added when the API key is set. Test renamed from `test_trigger_enrichment_skips_when_not_configured` to `test_trigger_enrichment_skips_when_webhook_url_missing`, and a new test `test_trigger_enrichment_omits_auth_header_when_no_api_key` was added.
> - **Mock data**: 2 of 14 mock practices populated with realistic owner data so the UI is demo-able without Clay credentials.
> - **Task 14 (smoke test)**: Clay's HTTP API action requires the body to reference only columns that always have non-null values, OR the action is gated and never fires. Pragmatic v1 setup: include `place_id`, `owner_name` (from `Custom Waterfall` after retyping it to Text), and `owner_email` (from Findymail) — skip `owner_phone` and `owner_linkedin` until Clay-side gating settings are tuned. Backend handles missing fields fine.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let reps click "Enrich owner" on a practice card to fire a Clay table run, then auto-update the card with owner name / title / email / phone / LinkedIn when Clay's webhook returns.

**Architecture:** On-demand outbound POST to Clay's HTTP API source (async), inbound webhook endpoint verified by shared-secret header, frontend polling of practice row while `enrichment_status === 'pending'`. Fail-soft — Clay outages surface as warnings, don't break the UX. Mirrors the email outreach / Salesforce conventions.

**Tech Stack:** FastAPI, pydantic-settings, httpx.AsyncClient, Supabase service-role, Next.js 14 App Router, React hooks.

**Spec:** [docs/specs/2026-04-24-clay-enrichment-design.md](../../specs/2026-04-24-clay-enrichment-design.md)

---

## File Structure

**Backend — create:**
- `src/clay.py` — `trigger_enrichment(practice)` POSTs to Clay; mock-mode aware
- `tests/test_clay.py`
- `tests/test_api_enrich.py`
- `tests/test_api_webhook_clay.py`

**Backend — modify:**
- `src/settings.py` — 3 new env vars
- `src/models.py` — 7 new fields on `Practice`
- `src/storage.py` — extend the preserve set on `upsert_practices` so search/rescan doesn't clobber owner fields
- `api/index.py` — `POST /api/practices/{id}/enrich` and `POST /api/webhooks/clay`
- `supabase/schema.sql` — append 7 columns

**Frontend — create:**
- `web/components/enrich-button.tsx`
- `web/components/owner-mini-card.tsx`
- `web/lib/use-enrichment-poll.ts`

**Frontend — modify:**
- `web/lib/types.ts` — extend `Practice`
- `web/lib/mock-data.ts` — add 7 null fields to all 14 mocks, populate 2 with realistic owner data
- `web/lib/api.ts` — `enrichPractice`, `getPractice` helpers
- `web/components/practice-card.tsx` — render `EnrichButton` + `OwnerMiniCard`, wire polling
- `web/components/practice-info.tsx` — add Owner section to Call Prep sidebar

**Config:**
- `.env.example` — 3 new keys

---

### Task 1: Supabase schema + manual migration

**Files:**
- Modify: `supabase/schema.sql` (append)
- Manual: same SQL in Supabase SQL editor

- [ ] **Step 1: Append to `supabase/schema.sql`**

```sql
-- ======================= Clay owner enrichment =======================

alter table practices
  add column if not exists owner_name         text,
  add column if not exists owner_email        text,
  add column if not exists owner_phone        text,
  add column if not exists owner_title        text,
  add column if not exists owner_linkedin     text,
  add column if not exists enrichment_status  text,
  add column if not exists enriched_at        timestamptz;
```

- [ ] **Step 2: Apply the same SQL in Supabase dashboard**

Open the Supabase SQL editor and paste the block. Run. Verify the 7 new columns exist in Table editor on `practices`.

- [ ] **Step 3: Commit**

```bash
git add supabase/schema.sql
git commit -m "feat(clay): add owner_* + enrichment_status/at columns to practices"
```

---

### Task 2: Settings + `.env.example`

**Files:**
- Modify: `src/settings.py`
- Modify: `.env.example`

- [ ] **Step 1: Add Clay fields to `Settings`**

In `src/settings.py`, append to the `Settings` class (after the `sf_api_version` line, before `class Config:`):

```python
    # Clay owner enrichment
    clay_table_webhook_url: str = ""
    clay_table_api_key: str = ""
    clay_inbound_secret: str = ""
```

- [ ] **Step 2: Verify app still starts**

Run: `python -c "from src.settings import settings; print(repr(settings.clay_table_webhook_url))"`
Expected: `''`

- [ ] **Step 3: Append to `.env.example`**

Append to the end of `.env.example`:

```
# Clay owner enrichment
CLAY_TABLE_WEBHOOK_URL=
CLAY_TABLE_API_KEY=
CLAY_INBOUND_SECRET=
```

- [ ] **Step 4: Commit**

```bash
git add src/settings.py .env.example
git commit -m "feat(clay): add CLAY_* settings + .env.example entries"
```

---

### Task 3: Extend `Practice` model + storage preserve set

**Files:**
- Modify: `src/models.py`
- Modify: `src/storage.py`

- [ ] **Step 1: Add owner/enrichment fields to `Practice`**

Append to the `Practice` class in `src/models.py` (after the `call_notes` line):

```python

    # Clay owner enrichment
    owner_name: str | None = None
    owner_email: str | None = None
    owner_phone: str | None = None
    owner_title: str | None = None
    owner_linkedin: str | None = None
    enrichment_status: str | None = None
    enriched_at: str | None = None
```

- [ ] **Step 2: Extend the upsert preserve set**

In `src/storage.py`, find the `preserved = { ... }` set inside `upsert_practices` and add the new fields so search/rescan doesn't clobber them:

```python
    preserved = {
        "summary",
        "pain_points",
        "sales_angles",
        "recommended_service",
        "lead_score",
        "urgency_score",
        "hiring_signal_score",
        "status",
        "notes",
        "last_touched_by_name",  # derived from join
        "owner_name",
        "owner_email",
        "owner_phone",
        "owner_title",
        "owner_linkedin",
        "enrichment_status",
        "enriched_at",
    }
```

- [ ] **Step 3: Verify the model + storage both load**

Run: `python -c "from src.models import Practice; from src.storage import upsert_practices; p = Practice(place_id='x', name='y'); print(p.enrichment_status, p.owner_name)"`
Expected: `None None`

- [ ] **Step 4: Commit**

```bash
git add src/models.py src/storage.py
git commit -m "feat(clay): extend Practice model + storage preserve set"
```

---

### Task 4: `src/clay.py` — trigger_enrichment

**Files:**
- Create: `src/clay.py`
- Create: `tests/test_clay.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_clay.py`:

```python
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src import clay
from src.models import Practice


def _practice(**overrides) -> Practice:
    base = dict(
        place_id="abc",
        name="Houston Family Dental",
        website="https://hfd.com",
        city="Houston",
        state="TX",
        phone="+17135551234",
    )
    base.update(overrides)
    return Practice(**base)


@pytest.mark.asyncio
async def test_trigger_enrichment_skips_when_not_configured():
    with patch("src.clay.settings") as s:
        s.clay_table_webhook_url = ""
        s.clay_table_api_key = "anything"
        result = await clay.trigger_enrichment(_practice())
    assert result == {"skipped": True, "reason": "clay_not_configured"}

    with patch("src.clay.settings") as s:
        s.clay_table_webhook_url = "https://clay.example"
        s.clay_table_api_key = ""
        result = await clay.trigger_enrichment(_practice())
    assert result == {"skipped": True, "reason": "clay_not_configured"}


@pytest.mark.asyncio
async def test_trigger_enrichment_posts_correct_payload():
    fake_post = AsyncMock()
    fake_post.return_value.status_code = 200
    fake_post.return_value.raise_for_status = lambda: None

    with patch("src.clay.settings") as s:
        s.clay_table_webhook_url = "https://clay.example/v1/rows"
        s.clay_table_api_key = "ck_test"
        with patch("src.clay.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value.post = fake_post
            result = await clay.trigger_enrichment(_practice())

    assert result == {"status": "pending"}
    url_called = fake_post.call_args.args[0]
    assert url_called == "https://clay.example/v1/rows"

    headers = fake_post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer ck_test"
    assert headers["Content-Type"] == "application/json"

    body = fake_post.call_args.kwargs["json"]
    assert body == {
        "place_id": "abc",
        "practice_name": "Houston Family Dental",
        "website": "https://hfd.com",
        "city": "Houston",
        "state": "TX",
        "phone": "+17135551234",
    }


@pytest.mark.asyncio
async def test_trigger_enrichment_raises_on_http_error():
    fake_post = AsyncMock()
    def raise_for_status():
        raise httpx.HTTPStatusError("boom", request=None, response=None)
    fake_post.return_value.raise_for_status = raise_for_status

    with patch("src.clay.settings") as s:
        s.clay_table_webhook_url = "https://clay.example/v1/rows"
        s.clay_table_api_key = "ck_test"
        with patch("src.clay.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value.post = fake_post
            with pytest.raises(httpx.HTTPStatusError):
                await clay.trigger_enrichment(_practice())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_clay.py -v`
Expected: all tests FAIL with `ModuleNotFoundError: No module named 'src.clay'`.

- [ ] **Step 3: Implement `src/clay.py`**

Create `src/clay.py`:

```python
import httpx

from src.models import Practice
from src.settings import settings


def _is_configured() -> bool:
    return bool(settings.clay_table_webhook_url and settings.clay_table_api_key)


async def trigger_enrichment(practice: Practice) -> dict:
    """POST practice data to Clay's HTTP API source.

    Returns {'status': 'pending'} on success or
    {'skipped': True, 'reason': 'clay_not_configured'} when env vars are empty.
    Raises httpx errors on non-2xx response; caller decides how to surface.
    """
    if not _is_configured():
        return {"skipped": True, "reason": "clay_not_configured"}

    payload = {
        "place_id": practice.place_id,
        "practice_name": practice.name,
        "website": practice.website,
        "city": practice.city,
        "state": practice.state,
        "phone": practice.phone,
    }
    headers = {
        "Authorization": f"Bearer {settings.clay_table_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            settings.clay_table_webhook_url, headers=headers, json=payload
        )
        resp.raise_for_status()

    return {"status": "pending"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_clay.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/clay.py tests/test_clay.py
git commit -m "feat(clay): add trigger_enrichment outbound POST"
```

---

### Task 5: `POST /api/practices/{place_id}/enrich`

**Files:**
- Modify: `api/index.py`
- Create: `tests/test_api_enrich.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_api_enrich.py`:

```python
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from api.index import app
from src.auth import get_current_user


def _override_user(user: dict):
    app.dependency_overrides[get_current_user] = lambda: user


@pytest.fixture(autouse=True)
def cleanup():
    yield
    app.dependency_overrides.clear()


def test_enrich_requires_auth():
    client = TestClient(app)
    resp = client.post("/api/practices/abc/enrich")
    assert resp.status_code == 401


def test_enrich_returns_404_when_practice_missing(sample_rep_profile):
    _override_user(sample_rep_profile)
    with patch("api.index.get_practice", return_value=None):
        client = TestClient(app)
        resp = client.post("/api/practices/missing/enrich")
    assert resp.status_code == 404


def test_enrich_happy_path_sets_pending_and_returns_null_warning(sample_rep_profile):
    _override_user(sample_rep_profile)
    existing = {"place_id": "abc", "name": "Test", "enrichment_status": None}
    updated = {**existing, "enrichment_status": "pending"}

    with patch("api.index.get_practice", return_value=existing):
        with patch("api.index.update_practice_fields", return_value=updated) as upd:
            with patch("api.index.trigger_enrichment", AsyncMock(return_value={"status": "pending"})):
                client = TestClient(app)
                resp = client.post("/api/practices/abc/enrich")

    assert resp.status_code == 200
    body = resp.json()
    assert body["practice"]["enrichment_status"] == "pending"
    assert body["clay_warning"] is None

    first_call_fields = upd.call_args_list[0].args[1]
    assert first_call_fields["enrichment_status"] == "pending"


def test_enrich_returns_warning_when_clay_not_configured(sample_rep_profile):
    _override_user(sample_rep_profile)
    existing = {"place_id": "abc", "name": "Test", "enrichment_status": None}

    with patch("api.index.get_practice", return_value=existing):
        with patch("api.index.update_practice_fields", return_value=existing):
            with patch("api.index.trigger_enrichment", AsyncMock(return_value={"skipped": True, "reason": "clay_not_configured"})):
                client = TestClient(app)
                resp = client.post("/api/practices/abc/enrich")

    assert resp.status_code == 200
    body = resp.json()
    assert body["clay_warning"] == "Clay not configured. Enrichment skipped."


def test_enrich_flips_to_failed_and_warns_on_http_error(sample_rep_profile):
    _override_user(sample_rep_profile)
    existing = {"place_id": "abc", "name": "Test", "enrichment_status": None}
    failed = {**existing, "enrichment_status": "failed"}

    trigger_err = AsyncMock(side_effect=httpx.HTTPStatusError("502 Bad Gateway", request=None, response=None))

    with patch("api.index.get_practice", return_value=existing):
        with patch("api.index.update_practice_fields", side_effect=[{**existing, "enrichment_status": "pending"}, failed]):
            with patch("api.index.trigger_enrichment", trigger_err):
                client = TestClient(app)
                resp = client.post("/api/practices/abc/enrich")

    assert resp.status_code == 200
    body = resp.json()
    assert body["practice"]["enrichment_status"] == "failed"
    assert body["clay_warning"] is not None
    assert "502" in body["clay_warning"] or "Bad Gateway" in body["clay_warning"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_enrich.py -v`
Expected: all tests FAIL (endpoint doesn't exist yet).

- [ ] **Step 3: Add import + endpoint to `api/index.py`**

Add the import alongside the other `from src.` imports (top of file):

```python
from src.clay import trigger_enrichment
```

Append at the end of `api/index.py`:

```python
# ======================= Clay owner enrichment =======================


@app.post("/api/practices/{place_id}/enrich")
async def enrich_endpoint(
    place_id: str,
    user: dict = Depends(get_current_user),
):
    existing = get_practice(place_id)
    if not existing:
        raise HTTPException(404, "Practice not found")

    update_practice_fields(place_id, {"enrichment_status": "pending"}, touched_by=None)

    from src.models import Practice as _P
    trigger_result = {"skipped": False}
    clay_warning: str | None = None
    try:
        trigger_result = await trigger_enrichment(_P(**existing))
    except Exception as e:
        final = update_practice_fields(
            place_id, {"enrichment_status": "failed"}, touched_by=None
        )
        return {"practice": final, "clay_warning": f"Enrichment trigger failed: {e}"}

    if trigger_result.get("skipped"):
        # Revert the 'pending' flip — Clay never got the row.
        reverted = update_practice_fields(
            place_id,
            {"enrichment_status": existing.get("enrichment_status")},
            touched_by=None,
        )
        return {"practice": reverted, "clay_warning": "Clay not configured. Enrichment skipped."}

    current = update_practice_fields(place_id, {"enrichment_status": "pending"}, touched_by=None)
    return {"practice": current, "clay_warning": clay_warning}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_enrich.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add api/index.py tests/test_api_enrich.py
git commit -m "feat(clay): add POST /api/practices/{id}/enrich endpoint"
```

---

### Task 6: `POST /api/webhooks/clay`

**Files:**
- Modify: `api/index.py`
- Create: `tests/test_api_webhook_clay.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_api_webhook_clay.py`:

```python
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.index import app


@pytest.fixture(autouse=True)
def cleanup():
    yield
    app.dependency_overrides.clear()


def test_webhook_rejects_missing_secret():
    with patch("api.index.app_settings") as s:
        s.clay_inbound_secret = "shhh"
        client = TestClient(app)
        resp = client.post(
            "/api/webhooks/clay",
            json={"place_id": "abc", "owner_name": "Jane"},
        )
    assert resp.status_code == 401


def test_webhook_rejects_wrong_secret():
    with patch("api.index.app_settings") as s:
        s.clay_inbound_secret = "shhh"
        client = TestClient(app)
        resp = client.post(
            "/api/webhooks/clay",
            json={"place_id": "abc", "owner_name": "Jane"},
            headers={"X-Clay-Secret": "wrong"},
        )
    assert resp.status_code == 401


def test_webhook_returns_404_when_practice_missing():
    with patch("api.index.app_settings") as s:
        s.clay_inbound_secret = "shhh"
        with patch("api.index.get_practice", return_value=None):
            client = TestClient(app)
            resp = client.post(
                "/api/webhooks/clay",
                json={"place_id": "missing", "owner_name": "Jane"},
                headers={"X-Clay-Secret": "shhh"},
            )
    assert resp.status_code == 404


def test_webhook_happy_path_writes_owner_fields_and_sets_enriched():
    existing = {"place_id": "abc", "name": "Test"}
    captured = {}

    def fake_update(place_id, fields, touched_by=None):
        captured.update(fields)
        captured["_place_id"] = place_id
        return {**existing, **fields}

    payload = {
        "place_id": "abc",
        "owner_name": "Jane Smith",
        "owner_title": "Practice Manager",
        "owner_email": "jane@hfd.com",
        "owner_phone": "+17135559999",
        "owner_linkedin": "https://linkedin.com/in/janesmith",
    }

    with patch("api.index.app_settings") as s:
        s.clay_inbound_secret = "shhh"
        with patch("api.index.get_practice", return_value=existing):
            with patch("api.index.update_practice_fields", side_effect=fake_update):
                client = TestClient(app)
                resp = client.post(
                    "/api/webhooks/clay",
                    json=payload,
                    headers={"X-Clay-Secret": "shhh"},
                )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert captured["owner_name"] == "Jane Smith"
    assert captured["owner_title"] == "Practice Manager"
    assert captured["owner_email"] == "jane@hfd.com"
    assert captured["owner_phone"] == "+17135559999"
    assert captured["owner_linkedin"] == "https://linkedin.com/in/janesmith"
    assert captured["enrichment_status"] == "enriched"
    assert "enriched_at" in captured


def test_webhook_flips_to_failed_when_no_owner_fields():
    existing = {"place_id": "abc", "name": "Test"}
    captured = {}

    def fake_update(place_id, fields, touched_by=None):
        captured.update(fields)
        return {**existing, **fields}

    with patch("api.index.app_settings") as s:
        s.clay_inbound_secret = "shhh"
        with patch("api.index.get_practice", return_value=existing):
            with patch("api.index.update_practice_fields", side_effect=fake_update):
                client = TestClient(app)
                resp = client.post(
                    "/api/webhooks/clay",
                    json={"place_id": "abc"},
                    headers={"X-Clay-Secret": "shhh"},
                )

    assert resp.status_code == 200
    assert captured["enrichment_status"] == "failed"
    assert "owner_name" not in captured


def test_webhook_partial_payload_only_writes_present_fields():
    existing = {"place_id": "abc", "name": "Test", "owner_phone": "+17130000000"}
    captured = {}

    def fake_update(place_id, fields, touched_by=None):
        captured.update(fields)
        return {**existing, **fields}

    with patch("api.index.app_settings") as s:
        s.clay_inbound_secret = "shhh"
        with patch("api.index.get_practice", return_value=existing):
            with patch("api.index.update_practice_fields", side_effect=fake_update):
                client = TestClient(app)
                resp = client.post(
                    "/api/webhooks/clay",
                    json={"place_id": "abc", "owner_name": "Jane"},
                    headers={"X-Clay-Secret": "shhh"},
                )

    assert resp.status_code == 200
    assert captured["owner_name"] == "Jane"
    assert "owner_phone" not in captured
    assert captured["enrichment_status"] == "enriched"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_webhook_clay.py -v`
Expected: all 6 tests FAIL (route not found).

- [ ] **Step 3: Add the webhook endpoint to `api/index.py`**

Append to `api/index.py`:

```python
from fastapi import Header


class ClayWebhookPayload(BaseModel):
    place_id: str
    owner_name: str | None = None
    owner_email: str | None = None
    owner_phone: str | None = None
    owner_title: str | None = None
    owner_linkedin: str | None = None


@app.post("/api/webhooks/clay")
def clay_webhook(
    body: ClayWebhookPayload,
    x_clay_secret: str | None = Header(default=None, alias="X-Clay-Secret"),
):
    if not app_settings.clay_inbound_secret or x_clay_secret != app_settings.clay_inbound_secret:
        raise HTTPException(401, "Invalid secret")

    existing = get_practice(body.place_id)
    if not existing:
        raise HTTPException(404, "Practice not found")

    fields: dict = {}
    for key in ("owner_name", "owner_email", "owner_phone", "owner_title", "owner_linkedin"):
        value = getattr(body, key)
        if value is not None and value != "":
            fields[key] = value

    has_any_contact = any(k in fields for k in ("owner_name", "owner_email", "owner_phone"))
    fields["enrichment_status"] = "enriched" if has_any_contact else "failed"
    fields["enriched_at"] = datetime.now(timezone.utc).isoformat()

    update_practice_fields(body.place_id, fields, touched_by=None)
    return {"ok": True}
```

Note: `datetime`, `timezone`, `BaseModel` are already imported at the top of `api/index.py`. `app_settings` too.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_webhook_clay.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run the full backend suite**

Run: `pytest -q`
Expected: all tests pass (68 prior + 3 clay + 5 enrich + 6 webhook = 82 passing).

- [ ] **Step 6: Commit**

```bash
git add api/index.py tests/test_api_webhook_clay.py
git commit -m "feat(clay): add POST /api/webhooks/clay inbound endpoint"
```

---

### Task 7: Frontend types + mock data

**Files:**
- Modify: `web/lib/types.ts`
- Modify: `web/lib/mock-data.ts`

- [ ] **Step 1: Extend `Practice` interface**

In `web/lib/types.ts`, append inside the `Practice` interface (after `call_notes`):

```typescript
  owner_name: string | null
  owner_email: string | null
  owner_phone: string | null
  owner_title: string | null
  owner_linkedin: string | null
  enrichment_status: "pending" | "enriched" | "failed" | null
  enriched_at: string | null
```

- [ ] **Step 2: Add 7 null defaults to every mock**

In `web/lib/mock-data.ts`, use replace-all on the closing pattern that follows call log fields:

Find (exactly):
```typescript
    call_notes: null,
  },
```

Replace with:
```typescript
    call_notes: null,
    owner_name: null,
    owner_email: null,
    owner_phone: null,
    owner_title: null,
    owner_linkedin: null,
    enrichment_status: null,
    enriched_at: null,
  },
```

Apply to all 14 occurrences.

- [ ] **Step 3: Populate the first 2 mock practices with realistic owner data**

Still in `web/lib/mock-data.ts`, edit the FIRST mock entry (`real_dental_houston_001` / Houston Dental Care). Find its block of nulls and replace the owner fields:

```typescript
    owner_name: "Dr. Arjun Patel",
    owner_email: "apatel@houstondentalcare.org",
    owner_phone: "+17139560834",
    owner_title: "Owner & Principal Dentist",
    owner_linkedin: "https://www.linkedin.com/in/arjun-patel-dds",
    enrichment_status: "enriched",
    enriched_at: "2026-04-23T14:05:00.000Z",
```

Edit the SECOND mock entry (`real_dental_houston_002` / Fresh Dental Care). Same idea:

```typescript
    owner_name: "Dr. Mina Chen",
    owner_email: "dr.chen@freshdentalcare.com",
    owner_phone: "+17137296101",
    owner_title: "Practice Owner",
    owner_linkedin: "https://www.linkedin.com/in/mina-chen-dmd",
    enrichment_status: "enriched",
    enriched_at: "2026-04-22T09:30:00.000Z",
```

- [ ] **Step 4: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add web/lib/types.ts web/lib/mock-data.ts
git commit -m "feat(clay): extend Practice type + mock data with owner fields"
```

---

### Task 8: Frontend API helpers — `enrichPractice` + `getPractice`

**Files:**
- Modify: `web/lib/api.ts`

- [ ] **Step 1: Append helpers**

Open `web/lib/api.ts`. Append at the end of the file:

```typescript
export async function getPractice(placeId: string): Promise<Practice> {
  return await apiFetch<Practice>(`/api/practices/${placeId}`)
}

export interface EnrichResponse {
  practice: Practice
  clay_warning: string | null
}

export async function enrichPractice(
  placeId: string,
): Promise<EnrichResponse> {
  return await apiFetch<EnrichResponse>(
    `/api/practices/${placeId}/enrich`,
    { method: "POST" },
  )
}
```

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/lib/api.ts
git commit -m "feat(clay): add getPractice + enrichPractice frontend helpers"
```

---

### Task 9: `OwnerMiniCard` component

**Files:**
- Create: `web/components/owner-mini-card.tsx`

- [ ] **Step 1: Create the component**

Create `web/components/owner-mini-card.tsx`:

```tsx
"use client"

import { Mail, Phone, Linkedin, User } from "lucide-react"
import type { Practice } from "@/lib/types"

interface OwnerMiniCardProps {
  practice: Practice
  compact?: boolean
}

export default function OwnerMiniCard({ practice, compact = false }: OwnerMiniCardProps) {
  const hasAny =
    practice.owner_name ||
    practice.owner_email ||
    practice.owner_phone ||
    practice.owner_linkedin

  if (!hasAny) return null

  return (
    <div className={compact ? "mt-2" : "mt-3 p-3 rounded-lg bg-white/60 border border-gray-200/60"}>
      <div className="flex items-center gap-1.5 text-xs">
        <User className="w-3 h-3 text-gray-500 shrink-0" />
        <span className="font-medium text-gray-800 truncate">
          {practice.owner_name ?? "Unknown"}
        </span>
        {practice.owner_title && (
          <span className="text-gray-400 truncate">· {practice.owner_title}</span>
        )}
      </div>
      <div className="flex items-center gap-2 mt-1.5">
        {practice.owner_email && (
          <a
            href={`mailto:${practice.owner_email}`}
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1 text-[11px] text-gray-600 hover:text-teal-700"
            title={practice.owner_email}
          >
            <Mail className="w-3 h-3" />
            <span className="truncate max-w-[140px]">{practice.owner_email}</span>
          </a>
        )}
        {practice.owner_phone && (
          <a
            href={`tel:${practice.owner_phone}`}
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1 text-[11px] text-gray-600 hover:text-teal-700"
          >
            <Phone className="w-3 h-3" />
            {practice.owner_phone}
          </a>
        )}
        {practice.owner_linkedin && (
          <a
            href={practice.owner_linkedin}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-gray-500 hover:text-blue-600"
            title="LinkedIn"
          >
            <Linkedin className="w-3.5 h-3.5" />
          </a>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/components/owner-mini-card.tsx
git commit -m "feat(clay): add OwnerMiniCard component"
```

---

### Task 10: `EnrichButton` component

**Files:**
- Create: `web/components/enrich-button.tsx`

- [ ] **Step 1: Create the component**

Create `web/components/enrich-button.tsx`:

```tsx
"use client"

import { useState } from "react"
import { Loader2, Sparkles } from "lucide-react"
import type { Practice } from "@/lib/types"
import { enrichPractice, type EnrichResponse } from "@/lib/api"

interface EnrichButtonProps {
  practice: Practice
  onEnriched: (response: EnrichResponse) => void
  className: string
  onClick?: (event: React.MouseEvent<HTMLButtonElement>) => void
}

export default function EnrichButton({
  practice,
  onEnriched,
  className,
  onClick,
}: EnrichButtonProps) {
  const [submitting, setSubmitting] = useState(false)
  const isPending = practice.enrichment_status === "pending" || submitting
  const isAlreadyEnriched =
    practice.enrichment_status === "enriched" ||
    practice.enrichment_status === "failed"

  async function handleClick(e: React.MouseEvent<HTMLButtonElement>) {
    onClick?.(e)
    if (isPending) return
    setSubmitting(true)
    try {
      const response = await enrichPractice(practice.place_id)
      onEnriched(response)
      if (response.clay_warning) {
        console.warn("[Clay]", response.clay_warning)
      }
    } finally {
      setSubmitting(false)
    }
  }

  const label = isPending
    ? "Enriching…"
    : isAlreadyEnriched
      ? "Re-enrich"
      : "Enrich owner"

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={isPending}
      title={isAlreadyEnriched ? "Re-enrich (uses Clay credits)" : "Find owner via Clay"}
      className={className}
    >
      {isPending ? (
        <Loader2 className="w-3 h-3 animate-spin" />
      ) : (
        <Sparkles className="w-3 h-3" />
      )}
      {label}
    </button>
  )
}
```

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/components/enrich-button.tsx
git commit -m "feat(clay): add EnrichButton component"
```

---

### Task 11: `useEnrichmentPoll` hook

**Files:**
- Create: `web/lib/use-enrichment-poll.ts`

- [ ] **Step 1: Create the hook**

Create `web/lib/use-enrichment-poll.ts`:

```typescript
"use client"

import { useEffect, useRef } from "react"
import type { Practice } from "./types"
import { getPractice } from "./api"

const POLL_INTERVAL_MS = 5_000
const MAX_POLLS = 36 // 36 × 5s = 3 min

/**
 * While `practice.enrichment_status === 'pending'`, re-fetch the practice
 * every 5 seconds. Calls `onUpdate` whenever the server row differs.
 * Stops on status change or after MAX_POLLS iterations.
 */
export function useEnrichmentPoll(
  practice: Practice,
  onUpdate: (next: Practice) => void,
) {
  const pollsRef = useRef(0)

  useEffect(() => {
    if (practice.enrichment_status !== "pending") {
      pollsRef.current = 0
      return
    }

    let cancelled = false
    const handle = window.setInterval(async () => {
      if (pollsRef.current >= MAX_POLLS) {
        window.clearInterval(handle)
        return
      }
      pollsRef.current += 1
      try {
        const fresh = await getPractice(practice.place_id)
        if (cancelled) return
        if (fresh.enrichment_status !== "pending") {
          onUpdate(fresh)
          window.clearInterval(handle)
        } else {
          onUpdate(fresh)
        }
      } catch {
        // swallow — next tick will retry
      }
    }, POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      window.clearInterval(handle)
    }
  }, [practice.place_id, practice.enrichment_status, onUpdate])
}
```

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/lib/use-enrichment-poll.ts
git commit -m "feat(clay): add useEnrichmentPoll hook"
```

---

### Task 12: Wire `EnrichButton` + `OwnerMiniCard` + polling into `practice-card.tsx`

**Files:**
- Modify: `web/components/practice-card.tsx`
- Modify: `web/app/page.tsx`

- [ ] **Step 1: Add imports + polling hook call**

Open `web/components/practice-card.tsx`. Extend the imports block:

```tsx
import EnrichButton from "./enrich-button"
import OwnerMiniCard from "./owner-mini-card"
import { useEnrichmentPoll } from "@/lib/use-enrichment-poll"
```

Inside the `PracticeCard` component body (right after the existing `useState` for `isExpanded`), add:

```tsx
  useEnrichmentPoll(practice, (next) => {
    onCallLogged?.({ practice: next, sf_warning: null })
  })
```

Actually that reuses the wrong callback. Add a dedicated prop — extend `PracticeCardProps`:

```tsx
  onEnrichmentUpdate?: (next: Practice) => void
```

Add it to the destructure:

```tsx
export default function PracticeCard({
  practice,
  isSelected,
  onSelect,
  onAnalyze,
  isAnalyzing,
  onCallLogged,
  onEnrichmentUpdate,
}: PracticeCardProps) {
```

Now the hook call inside the component:

```tsx
  useEnrichmentPoll(practice, (next) => onEnrichmentUpdate?.(next))
```

- [ ] **Step 2: Insert `EnrichButton` in the action row**

Find the block that renders the Analyze button:

```tsx
        <button
          onClick={(e) => {
            e.stopPropagation()
            onAnalyze(practice.place_id, isScored)
          }}
          disabled={isAnalyzing}
          className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg border border-teal-600 text-teal-700 hover:bg-teal-50 disabled:opacity-50 transition"
        >
```

Insert directly AFTER the closing `</button>` of the Analyze button (and before the `<Link>` to Call Prep):

```tsx
        <EnrichButton
          practice={practice}
          onClick={(e) => e.stopPropagation()}
          onEnriched={(response) => onEnrichmentUpdate?.(response.practice)}
          className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg border border-amber-500 text-amber-700 hover:bg-amber-50 disabled:opacity-50 transition"
        />
```

- [ ] **Step 3: Render `OwnerMiniCard` after the last-call strip**

Find the "Last call" paragraph block:

```tsx
      {practice.call_count > 0 && (
        <p className="text-[11px] text-gray-500 mt-0.5">
          📞 {practice.call_count} ...
        </p>
      )}
```

Insert directly AFTER that block:

```tsx
      <OwnerMiniCard practice={practice} compact />
      {practice.enrichment_status === "failed" && !practice.owner_name && (
        <p className="text-[11px] text-rose-600 mt-1">
          No owner found — try Re-enrich
        </p>
      )}
```

- [ ] **Step 4: Typecheck (catches callers needing `onEnrichmentUpdate`)**

Run: `cd web && npx tsc --noEmit`
Expected: no errors (the new prop is optional, so `web/app/page.tsx` compiles even without being updated yet).

- [ ] **Step 5: Wire `onEnrichmentUpdate` from the map page**

Open `web/app/page.tsx`. Find where `<PracticeCard>` is rendered. Pass the same pattern already used by `onCallLogged`:

```tsx
                  onEnrichmentUpdate={(next) => {
                    setPractices((prev) =>
                      prev.map((x) =>
                        x.place_id === next.place_id ? { ...x, ...next } : x,
                      ),
                    )
                  }}
```

- [ ] **Step 6: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add web/components/practice-card.tsx web/app/page.tsx
git commit -m "feat(clay): wire EnrichButton + polling + OwnerMiniCard into card"
```

---

### Task 13: Add Owner section to `practice-info.tsx` (Call Prep sidebar)

**Files:**
- Modify: `web/components/practice-info.tsx`

- [ ] **Step 1: Import `OwnerMiniCard`**

Open `web/components/practice-info.tsx`. Add the import next to the others:

```tsx
import OwnerMiniCard from "./owner-mini-card"
```

- [ ] **Step 2: Insert the Owner section**

Find the closing of the phone/website buttons block:

```tsx
      <div className="flex gap-2">
        {practice.phone && (
          <CallButton ... />
        )}
        {practice.website && (
          <a href={practice.website} ...>
            <Globe className="w-3 h-3" /> Website
          </a>
        )}
      </div>
```

Directly AFTER that closing `</div>`, insert:

```tsx
      <div>
        <h4 className="text-xs font-semibold text-gray-700 mb-1">Owner</h4>
        {practice.enrichment_status === "pending" ? (
          <p className="text-xs text-gray-400">Enriching owner info…</p>
        ) : practice.owner_name ||
          practice.owner_email ||
          practice.owner_phone ? (
          <OwnerMiniCard practice={practice} />
        ) : (
          <p className="text-xs text-gray-400">
            {practice.enrichment_status === "failed"
              ? "No owner found."
              : "No owner info yet — enrich from the map."}
          </p>
        )}
      </div>
```

- [ ] **Step 3: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add web/components/practice-info.tsx
git commit -m "feat(clay): add Owner section to Call Prep sidebar"
```

---

### Task 14: Final verification + E2E smoke test

**Files:** none modified — manual verification.

- [ ] **Step 1: Run full backend suite**

Run: `pytest -q`
Expected: 82 tests pass.

- [ ] **Step 2: Frontend typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Confirm Supabase migration was applied**

Confirm with the user that the SQL from Task 1 has been run in the Supabase SQL editor. Block here until confirmed.

- [ ] **Step 4: Confirm Clay table is configured**

Confirm with the user:
- Clay table "HV Owner Enrichment" exists with HTTP API source
- Input columns: `place_id`, `practice_name`, `website`, `city`, `state`, `phone`
- Enrichment + output columns named `owner_name`, `owner_email`, `owner_phone`, `owner_title`, `owner_linkedin`
- Send Webhook action points to `{BACKEND_URL}/api/webhooks/clay` with header `X-Clay-Secret: <value of CLAY_INBOUND_SECRET>`

- [ ] **Step 5: User populates Clay env vars**

Ask the user to paste into `.env`:
```
CLAY_TABLE_WEBHOOK_URL=<Clay's HTTP API POST URL>
CLAY_TABLE_API_KEY=<Clay's bearer token for that source>
CLAY_INBOUND_SECRET=<random secret; also paste into Clay's Send Webhook header>
```
Restart uvicorn so settings reload.

- [ ] **Step 6: Mock-mode smoke (before Clay creds)**

If Clay creds not yet set, verify mock mode:
1. Click Enrich on a practice.
2. Response should be 200 with `clay_warning: "Clay not configured. Enrichment skipped."`
3. Card status unchanged. No error shown.

- [ ] **Step 7: Real smoke — successful enrichment**

With Clay creds set, use a practice that has a website:
1. Click Enrich → button flips to "Enriching…" with spinner.
2. Card polls every 5s (visible in Network tab).
3. Within ~1–2 min, Clay webhook hits `/api/webhooks/clay`, card updates:
   - Button becomes "Re-enrich"
   - Owner mini-card renders with name/title/email/phone/LinkedIn
4. In Supabase Table editor: `owner_*` fields populated, `enrichment_status='enriched'`, `enriched_at` stamped.

- [ ] **Step 8: Real smoke — no owner found**

Pick an obscure practice unlikely to have LinkedIn:
1. Click Enrich. Wait for webhook.
2. Card should show: "No owner found — try Re-enrich" and button becomes Re-enrich.
3. `enrichment_status='failed'`.

- [ ] **Step 9: Call Prep sidebar check**

Open a practice with owner data in Call Prep. Sidebar should show the Owner block with click-to-copy email + click-to-call phone + LinkedIn icon.

- [ ] **Step 10: Re-enrichment round-trip**

On an already-enriched practice, click Re-enrich:
1. Status flips back to pending, spinner shows.
2. Webhook arrives, fields overwrite with latest Clay result.
3. `enriched_at` updates to a fresh timestamp.

- [ ] **Step 11: Poll cap check (optional — takes 3+ min)**

Point `CLAY_TABLE_WEBHOOK_URL` at a URL that accepts the POST but never sends a webhook back. Click Enrich, wait 3 min. Card should stop polling silently; status stays `pending` in DB. Refreshing the page (card re-mounts with pending status → polling resumes — this is expected per spec).

Feature complete when Steps 1, 2, 7, 8, 9, 10 all pass.

---

## Self-review

**Spec coverage:**
- SF columns + Practice model → Task 3 ✓
- Clay HTTP API trigger + mock-mode → Task 4 ✓
- Trigger endpoint with fail-soft → Task 5 ✓
- Webhook endpoint + secret auth + failed-state logic → Task 6 ✓
- Practice TS type + mock data → Task 7 ✓
- `enrichPractice`/`getPractice` helpers → Task 8 ✓
- Owner mini-card → Task 9 ✓
- EnrichButton with 3 label states → Task 10 ✓
- 5s polling hook with 3-min cap → Task 11 ✓
- Card wiring + polling + owner card + failed message → Task 12 ✓
- Call Prep sidebar Owner section → Task 13 ✓
- Smoke test including poll cap → Task 14 ✓
- Clay setup steps → included under Task 14 Step 4 (user-facing config, not code) ✓

**Placeholder scan:** No TBDs. Every code block contains real code. Every test has assertions. Every commit command is exact.

**Type consistency:**
- `enrichPractice` returns `EnrichResponse` (Task 8), consumed by `EnrichButton` (Task 10) and wired in card (Task 12). Shape: `{practice, clay_warning}` — matches backend (Task 5 response).
- `getPractice` returns `Practice` (Task 8), consumed by `useEnrichmentPoll` (Task 11).
- `ClayWebhookPayload` (Task 6) shape matches the Clay Send Webhook config (Task 14 Step 4).
- `enrichment_status` type `"pending" | "enriched" | "failed" | null` — consistent across backend state machine (Tasks 5, 6), TS type (Task 7), and UI logic (Tasks 10, 12, 13).
- `onEnrichmentUpdate?: (next: Practice) => void` — defined in Task 12 Step 1, wired in Task 12 Step 5.

All consistent.
