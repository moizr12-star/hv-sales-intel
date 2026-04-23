# Salesforce Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a rep clicks Call, log a GPT-polished note to Supabase, create/update a Salesforce Lead with running call history + call count, and store the SF Lead ID + owner on the practice.

**Architecture:** Three isolated backend modules (`sf_auth.py`, `salesforce.py`, `call_log.py`) behind one new endpoint `POST /api/practices/{place_id}/call/log`. Modal-on-click UX on the frontend. Fail-soft SF sync — local save always wins. Mirrors the conventions already used by `ms_auth.py` / email outreach.

**Tech Stack:** FastAPI, pydantic-settings, httpx (AsyncClient), AsyncOpenAI (gpt-4o-mini), Supabase service-role client, Next.js 14 App Router, React.

**Spec:** [docs/specs/2026-04-23-salesforce-integration-design.md](../../specs/2026-04-23-salesforce-integration-design.md)

---

## File Structure

**Backend — create:**
- `src/sf_auth.py` — SF username-password OAuth token fetch + in-process cache + invalidation
- `src/salesforce.py` — Lead CRUD (create/update/get_owner) + `sync_practice` orchestrator
- `src/call_log.py` — GPT note polisher + append orchestrator
- `tests/test_sf_auth.py`, `tests/test_salesforce.py`, `tests/test_call_log.py`, `tests/test_api_call_log.py`

**Backend — modify:**
- `src/settings.py` — add 7 SF_* env vars
- `src/models.py` — add 6 fields to `Practice`
- `api/index.py` — add call-log endpoint + imports
- `supabase/schema.sql` — add columns + index

**Frontend — create:**
- `web/components/call-log-modal.tsx`

**Frontend — modify:**
- `web/lib/types.ts` — extend `Practice` interface
- `web/lib/mock-data.ts` — default values for new fields on each mock
- `web/lib/api.ts` — `logCall()` helper
- `web/components/call-button.tsx` — open modal instead of dialing directly
- `web/components/practice-card.tsx` — wire `onLogged`, render "Last call" strip
- `web/app/practice/[place_id]/page.tsx` — Activity tab → Call log tab

**Config:**
- `.env.example` — document new SF_* vars

`src/storage.py` **does not change** — `update_practice_fields(place_id, fields, touched_by)` already accepts an arbitrary dict, which is all we need.

---

### Task 1: Supabase schema + manual migration

**Files:**
- Modify: `supabase/schema.sql` (append)
- Manual: run the same SQL in the Supabase SQL editor

- [ ] **Step 1: Append to `supabase/schema.sql`**

```sql
-- ======================= Salesforce integration + call log =======================

alter table practices
  add column if not exists salesforce_lead_id     text,
  add column if not exists salesforce_owner_id    text,
  add column if not exists salesforce_owner_name  text,
  add column if not exists salesforce_synced_at   timestamptz,
  add column if not exists call_count             integer not null default 0,
  add column if not exists call_notes             text;

create index if not exists idx_practices_sf_lead_id on practices(salesforce_lead_id);
```

- [ ] **Step 2: Apply the same SQL in Supabase dashboard**

Open the Supabase SQL editor for the project and paste the same block, then Run. Verify in Table editor that `practices` now shows 6 new columns and the index exists.

- [ ] **Step 3: Commit schema change**

```bash
git add supabase/schema.sql
git commit -m "feat(sf): add salesforce_* + call_count/notes columns to practices"
```

---

### Task 2: Settings — new SF env vars

**Files:**
- Modify: `src/settings.py`
- Modify: `.env.example`

- [ ] **Step 1: Add SF fields to `Settings`**

Open `src/settings.py` and append these lines to the `Settings` class (after `email_reply_lookback_days: int = 30`, before the `class Config:`):

```python
    # Salesforce integration (username-password OAuth)
    sf_client_id: str = ""
    sf_client_secret: str = ""
    sf_username: str = ""
    sf_password: str = ""
    sf_security_token: str = ""
    sf_login_url: str = "https://login.salesforce.com"
    sf_api_version: str = "v60.0"
```

- [ ] **Step 2: Verify the app still starts**

Run: `python -c "from src.settings import settings; print('sf_login_url=', settings.sf_login_url)"`
Expected: `sf_login_url= https://login.salesforce.com`

- [ ] **Step 3: Add documentation block to `.env.example`**

Append to `.env.example`:

```
# Salesforce (username-password OAuth)
SF_CLIENT_ID=
SF_CLIENT_SECRET=
SF_USERNAME=
SF_PASSWORD=
SF_SECURITY_TOKEN=
SF_LOGIN_URL=https://login.salesforce.com
SF_API_VERSION=v60.0
```

- [ ] **Step 4: Commit**

```bash
git add src/settings.py .env.example
git commit -m "feat(sf): add SF_* settings + .env.example entries"
```

---

### Task 3: Extend `Practice` model

**Files:**
- Modify: `src/models.py`

- [ ] **Step 1: Add the 6 new fields**

Open `src/models.py` and append to the `Practice` class (after the Attribution block):

```python

    # Salesforce integration + call log
    salesforce_lead_id: str | None = None
    salesforce_owner_id: str | None = None
    salesforce_owner_name: str | None = None
    salesforce_synced_at: str | None = None
    call_count: int = 0
    call_notes: str | None = None
```

- [ ] **Step 2: Verify model still loads**

Run: `python -c "from src.models import Practice; p = Practice(place_id='x', name='y'); print(p.call_count, p.salesforce_lead_id)"`
Expected: `0 None`

- [ ] **Step 3: Commit**

```bash
git add src/models.py
git commit -m "feat(sf): extend Practice model with SF + call log fields"
```

---

### Task 4: `sf_auth.py` — token fetch + cache + invalidation

**Files:**
- Create: `src/sf_auth.py`
- Create: `tests/test_sf_auth.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_sf_auth.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest

from src import sf_auth


@pytest.fixture(autouse=True)
def reset_cache():
    sf_auth._cached_access_token = None
    sf_auth._cached_instance_url = None
    yield
    sf_auth._cached_access_token = None
    sf_auth._cached_instance_url = None


def test_is_configured_false_when_any_missing():
    with patch("src.sf_auth.settings") as s:
        s.sf_client_id = "a"
        s.sf_client_secret = "b"
        s.sf_username = "c"
        s.sf_password = "d"
        s.sf_security_token = ""
        assert sf_auth.is_configured() is False


def test_is_configured_true_when_all_set():
    with patch("src.sf_auth.settings") as s:
        s.sf_client_id = "a"
        s.sf_client_secret = "b"
        s.sf_username = "c"
        s.sf_password = "d"
        s.sf_security_token = "e"
        assert sf_auth.is_configured() is True


@pytest.mark.asyncio
async def test_fetches_token_when_cache_empty():
    fake_post = AsyncMock()
    fake_post.return_value.json = lambda: {
        "access_token": "tok-abc",
        "instance_url": "https://yourorg.my.salesforce.com",
    }
    fake_post.return_value.raise_for_status = lambda: None

    with patch("src.sf_auth.settings") as s:
        s.sf_client_id = "cid"
        s.sf_client_secret = "csec"
        s.sf_username = "u@example.com"
        s.sf_password = "pw"
        s.sf_security_token = "tok"
        s.sf_login_url = "https://login.salesforce.com"
        with patch("src.sf_auth.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value.post = fake_post
            token, url = await sf_auth.get_access_token()

    assert token == "tok-abc"
    assert url == "https://yourorg.my.salesforce.com"
    assert sf_auth._cached_access_token == "tok-abc"

    call_args = fake_post.call_args
    posted_data = call_args.kwargs["data"]
    assert posted_data["grant_type"] == "password"
    assert posted_data["password"] == "pwtok"


@pytest.mark.asyncio
async def test_reuses_cached_token():
    sf_auth._cached_access_token = "cached"
    sf_auth._cached_instance_url = "https://cached.salesforce.com"
    token, url = await sf_auth.get_access_token()
    assert token == "cached"
    assert url == "https://cached.salesforce.com"


@pytest.mark.asyncio
async def test_invalidate_clears_cache():
    sf_auth._cached_access_token = "cached"
    sf_auth._cached_instance_url = "https://cached.salesforce.com"
    sf_auth.invalidate_token()
    assert sf_auth._cached_access_token is None
    assert sf_auth._cached_instance_url is None


@pytest.mark.asyncio
async def test_raises_when_not_configured():
    with patch("src.sf_auth.settings") as s:
        s.sf_client_id = ""
        s.sf_client_secret = ""
        s.sf_username = ""
        s.sf_password = ""
        s.sf_security_token = ""
        with pytest.raises(RuntimeError, match="not configured"):
            await sf_auth.get_access_token()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sf_auth.py -v`
Expected: all tests FAIL with `ModuleNotFoundError: No module named 'src.sf_auth'`.

- [ ] **Step 3: Implement `src/sf_auth.py`**

Create the file:

```python
import asyncio

import httpx

from src.settings import settings


_cached_access_token: str | None = None
_cached_instance_url: str | None = None
_lock = asyncio.Lock()


def is_configured() -> bool:
    """True if all 5 required SF_* env vars are non-empty."""
    return bool(
        settings.sf_client_id
        and settings.sf_client_secret
        and settings.sf_username
        and settings.sf_password
        and settings.sf_security_token
    )


def invalidate_token() -> None:
    """Clear the in-process cache. Call on 401 before retrying."""
    global _cached_access_token, _cached_instance_url
    _cached_access_token = None
    _cached_instance_url = None


async def get_access_token() -> tuple[str, str]:
    """Return (access_token, instance_url). Cached until invalidated.

    Exchanges username+password+security_token via Salesforce OAuth 2.0
    username-password flow. SF does not return expires_in for this flow,
    so we cache indefinitely and rely on callers to invalidate on 401.
    """
    global _cached_access_token, _cached_instance_url

    if _cached_access_token and _cached_instance_url:
        return _cached_access_token, _cached_instance_url

    if not is_configured():
        raise RuntimeError("Salesforce not configured")

    async with _lock:
        if _cached_access_token and _cached_instance_url:
            return _cached_access_token, _cached_instance_url

        url = f"{settings.sf_login_url}/services/oauth2/token"
        data = {
            "grant_type": "password",
            "client_id": settings.sf_client_id,
            "client_secret": settings.sf_client_secret,
            "username": settings.sf_username,
            "password": settings.sf_password + settings.sf_security_token,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
        payload = resp.json()

        _cached_access_token = payload["access_token"]
        _cached_instance_url = payload["instance_url"]
        return _cached_access_token, _cached_instance_url
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sf_auth.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/sf_auth.py tests/test_sf_auth.py
git commit -m "feat(sf): add sf_auth with username-password OAuth token cache"
```

---

### Task 5: `salesforce.py` — Lead CRUD helpers

**Files:**
- Create: `src/salesforce.py` (helpers only — orchestrator in Task 6)
- Create: `tests/test_salesforce.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_salesforce.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest

from src import salesforce
from src.models import Practice


def _practice(**overrides) -> Practice:
    base = dict(
        place_id="abc",
        name="Houston Family Dental",
        address="1234 Main St, Houston, TX 77002",
        city="Houston",
        phone="+17135551234",
        email="hello@hfd.com",
        website="https://hfd.com",
        lead_score=82,
        urgency_score=70,
        hiring_signal_score=60,
    )
    base.update(overrides)
    return Practice(**base)


def test_build_lead_payload_includes_required_fields():
    payload = salesforce._build_lead_payload(
        _practice(), call_note_line="[ts] Rep: init"
    )
    assert payload["Company"] == "Houston Family Dental"
    assert payload["LastName"] == "Office"
    assert payload["Phone"] == "+17135551234"
    assert payload["Email"] == "hello@hfd.com"
    assert payload["Industry"] == "Healthcare"
    assert payload["LeadSource"] == "HV Sales Intel"
    assert payload["Status"] == "Working - Contacted"
    assert payload["Rating"] == "Hot"
    assert payload["Description"] == "Lead Score: 82 | Urgency: 70 | Hiring Signal: 60"
    assert payload["Call_Count__c"] == 1
    assert payload["Call_Notes__c"] == "[ts] Rep: init"


def test_build_lead_payload_omits_null_optionals():
    p = _practice(email=None, website=None, city=None, lead_score=None, urgency_score=None, hiring_signal_score=None)
    payload = salesforce._build_lead_payload(p, call_note_line="[ts] Rep: init")
    assert "Email" not in payload
    assert "Website" not in payload
    assert "City" not in payload
    assert "Description" not in payload
    assert payload["Rating"] == "Warm"


def test_rating_tiers():
    assert salesforce._rating_from_score(80) == "Hot"
    assert salesforce._rating_from_score(50) == "Warm"
    assert salesforce._rating_from_score(20) == "Cold"
    assert salesforce._rating_from_score(None) == "Warm"


@pytest.mark.asyncio
async def test_create_lead_posts_to_correct_url():
    fake_post = AsyncMock()
    fake_post.return_value.status_code = 201
    fake_post.return_value.json = lambda: {"id": "00Q123", "success": True, "errors": []}
    fake_post.return_value.raise_for_status = lambda: None

    with patch("src.salesforce.sf_auth.get_access_token", AsyncMock(return_value=("tok", "https://x.my.salesforce.com"))):
        with patch("src.salesforce.settings") as s:
            s.sf_api_version = "v60.0"
            with patch("src.salesforce.httpx.AsyncClient") as client_cls:
                client_cls.return_value.__aenter__.return_value.post = fake_post
                result = await salesforce.create_lead(_practice(), "[ts] Rep: init")

    assert result["id"] == "00Q123"
    url_called = fake_post.call_args.args[0]
    assert url_called == "https://x.my.salesforce.com/services/data/v60.0/sobjects/Lead/"


@pytest.mark.asyncio
async def test_update_lead_patches_only_call_fields():
    fake_patch = AsyncMock()
    fake_patch.return_value.status_code = 204
    fake_patch.return_value.raise_for_status = lambda: None

    with patch("src.salesforce.sf_auth.get_access_token", AsyncMock(return_value=("tok", "https://x.my.salesforce.com"))):
        with patch("src.salesforce.settings") as s:
            s.sf_api_version = "v60.0"
            with patch("src.salesforce.httpx.AsyncClient") as client_cls:
                client_cls.return_value.__aenter__.return_value.patch = fake_patch
                await salesforce.update_lead("00Q123", 3, "[ts1] a\n[ts2] b\n[ts3] c")

    url_called = fake_patch.call_args.args[0]
    body = fake_patch.call_args.kwargs["json"]
    assert url_called == "https://x.my.salesforce.com/services/data/v60.0/sobjects/Lead/00Q123"
    assert body == {"Call_Count__c": 3, "Call_Notes__c": "[ts1] a\n[ts2] b\n[ts3] c"}


@pytest.mark.asyncio
async def test_get_owner_extracts_id_and_name():
    fake_get = AsyncMock()
    fake_get.return_value.status_code = 200
    fake_get.return_value.json = lambda: {
        "Id": "00Q123",
        "OwnerId": "005ABC",
        "Owner": {"attributes": {}, "Name": "Sarah Khan"},
    }
    fake_get.return_value.raise_for_status = lambda: None

    with patch("src.salesforce.sf_auth.get_access_token", AsyncMock(return_value=("tok", "https://x.my.salesforce.com"))):
        with patch("src.salesforce.settings") as s:
            s.sf_api_version = "v60.0"
            with patch("src.salesforce.httpx.AsyncClient") as client_cls:
                client_cls.return_value.__aenter__.return_value.get = fake_get
                owner_id, owner_name = await salesforce.get_owner("00Q123")

    assert owner_id == "005ABC"
    assert owner_name == "Sarah Khan"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_salesforce.py -v`
Expected: all tests FAIL with `ModuleNotFoundError: No module named 'src.salesforce'`.

- [ ] **Step 3: Implement `src/salesforce.py` (helpers only)**

Create the file:

```python
import httpx

from src import sf_auth
from src.models import Practice
from src.settings import settings


def _rating_from_score(score: int | None) -> str:
    if score is None:
        return "Warm"
    if score >= 75:
        return "Hot"
    if score >= 50:
        return "Warm"
    return "Cold"


def _build_lead_payload(practice: Practice, call_note_line: str) -> dict:
    """Build the POST body for creating a Lead from a Practice."""
    payload: dict = {
        "Company": practice.name,
        "LastName": "Office",
        "Industry": "Healthcare",
        "LeadSource": "HV Sales Intel",
        "Status": "Working - Contacted",
        "Rating": _rating_from_score(practice.lead_score),
        "Call_Count__c": 1,
        "Call_Notes__c": call_note_line,
    }
    if practice.phone:
        payload["Phone"] = practice.phone
    if practice.email:
        payload["Email"] = practice.email
    if practice.website:
        payload["Website"] = practice.website
    if practice.address:
        payload["Street"] = practice.address
    if practice.city:
        payload["City"] = practice.city

    scores = [practice.lead_score, practice.urgency_score, practice.hiring_signal_score]
    if any(s is not None for s in scores):
        payload["Description"] = (
            f"Lead Score: {practice.lead_score or 0} | "
            f"Urgency: {practice.urgency_score or 0} | "
            f"Hiring Signal: {practice.hiring_signal_score or 0}"
        )
    return payload


async def create_lead(practice: Practice, call_note_line: str) -> dict:
    """POST to SF sobjects/Lead/. Returns the SF response body."""
    token, instance_url = await sf_auth.get_access_token()
    url = f"{instance_url}/services/data/{settings.sf_api_version}/sobjects/Lead/"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = _build_lead_payload(practice, call_note_line)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
    return resp.json()


async def update_lead(sf_lead_id: str, call_count: int, call_notes: str) -> None:
    """PATCH call log fields on an existing Lead. 204 on success."""
    token, instance_url = await sf_auth.get_access_token()
    url = f"{instance_url}/services/data/{settings.sf_api_version}/sobjects/Lead/{sf_lead_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {"Call_Count__c": call_count, "Call_Notes__c": call_notes}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(url, headers=headers, json=body)
        resp.raise_for_status()


async def get_owner(sf_lead_id: str) -> tuple[str, str]:
    """GET Id, OwnerId, Owner.Name for a Lead."""
    token, instance_url = await sf_auth.get_access_token()
    url = (
        f"{instance_url}/services/data/{settings.sf_api_version}"
        f"/sobjects/Lead/{sf_lead_id}"
    )
    params = {"fields": "Id,OwnerId,Owner.Name"}
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    data = resp.json()
    return data["OwnerId"], data.get("Owner", {}).get("Name", "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_salesforce.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/salesforce.py tests/test_salesforce.py
git commit -m "feat(sf): add Lead CRUD helpers (create/update/get_owner)"
```

---

### Task 6: `salesforce.sync_practice` orchestrator

**Files:**
- Modify: `src/salesforce.py` (append)
- Modify: `tests/test_salesforce.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_salesforce.py`:

```python
from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_sync_practice_skips_when_not_configured():
    with patch("src.salesforce.sf_auth.is_configured", return_value=False):
        result = await salesforce.sync_practice(_practice(), "[ts] Rep: init")
    assert result == {"skipped": True, "reason": "sf_not_configured"}


@pytest.mark.asyncio
async def test_sync_practice_creates_when_no_lead_id():
    practice = _practice()
    assert practice.salesforce_lead_id is None

    create_mock = AsyncMock(return_value={"id": "00Q_NEW", "success": True})
    owner_mock = AsyncMock(return_value=("005XYZ", "Sarah Khan"))

    with patch("src.salesforce.sf_auth.is_configured", return_value=True):
        with patch("src.salesforce.create_lead", create_mock):
            with patch("src.salesforce.get_owner", owner_mock):
                result = await salesforce.sync_practice(practice, "[ts] Rep: init")

    assert result["sf_lead_id"] == "00Q_NEW"
    assert result["sf_owner_id"] == "005XYZ"
    assert result["sf_owner_name"] == "Sarah Khan"
    assert "synced_at" in result
    create_mock.assert_awaited_once()
    owner_mock.assert_awaited_once_with("00Q_NEW")


@pytest.mark.asyncio
async def test_sync_practice_updates_when_lead_id_exists():
    practice = _practice(salesforce_lead_id="00Q_EXISTING", call_count=2, call_notes="[t1]\n[t2]")
    update_mock = AsyncMock()
    owner_mock = AsyncMock(return_value=("005XYZ", "Sarah Khan"))

    with patch("src.salesforce.sf_auth.is_configured", return_value=True):
        with patch("src.salesforce.update_lead", update_mock):
            with patch("src.salesforce.get_owner", owner_mock):
                result = await salesforce.sync_practice(practice, "[t3]")

    assert result["sf_lead_id"] == "00Q_EXISTING"
    assert result["sf_owner_name"] == "Sarah Khan"
    update_mock.assert_awaited_once_with("00Q_EXISTING", 2, "[t1]\n[t2]")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_salesforce.py -v`
Expected: the 3 new tests FAIL with `AttributeError: module 'src.salesforce' has no attribute 'sync_practice'`. The 6 prior tests should still PASS.

- [ ] **Step 3: Append `sync_practice` to `src/salesforce.py`**

Append to `src/salesforce.py`:

```python
from datetime import datetime, timezone


async def sync_practice(practice: Practice, polished_line: str) -> dict:
    """Create or update the SF Lead for this practice.

    Returns dict with SF fields on success, or {'skipped': True, 'reason': ...}
    when SF is not configured. Raises on network/API failures so the caller
    can decide how to surface them.
    """
    if not sf_auth.is_configured():
        return {"skipped": True, "reason": "sf_not_configured"}

    now_iso = datetime.now(timezone.utc).isoformat()

    if practice.salesforce_lead_id:
        await update_lead(
            practice.salesforce_lead_id,
            practice.call_count,
            practice.call_notes or "",
        )
        owner_id, owner_name = await get_owner(practice.salesforce_lead_id)
        return {
            "sf_lead_id": practice.salesforce_lead_id,
            "sf_owner_id": owner_id,
            "sf_owner_name": owner_name,
            "synced_at": now_iso,
        }

    created = await create_lead(practice, polished_line)
    sf_lead_id = created["id"]
    owner_id, owner_name = await get_owner(sf_lead_id)
    return {
        "sf_lead_id": sf_lead_id,
        "sf_owner_id": owner_id,
        "sf_owner_name": owner_name,
        "synced_at": now_iso,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_salesforce.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/salesforce.py tests/test_salesforce.py
git commit -m "feat(sf): add sync_practice orchestrator (create-or-update)"
```

---

### Task 7: `call_log.polish_note` with GPT

**Files:**
- Create: `src/call_log.py` (polish only; append_call_note in Task 8)
- Create: `tests/test_call_log.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_call_log.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import call_log


@pytest.mark.asyncio
async def test_polish_note_returns_empty_marker_for_blank_input():
    result = await call_log.polish_note("")
    assert result == "(call logged, no note)"

    result = await call_log.polish_note("   \n  ")
    assert result == "(call logged, no note)"


@pytest.mark.asyncio
async def test_polish_note_uses_gpt_when_configured():
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content="Left voicemail. Will retry Thursday."))]
    create_mock = AsyncMock(return_value=response)
    client = MagicMock()
    client.chat.completions.create = create_mock

    with patch("src.call_log.settings") as s:
        s.openai_api_key = "sk-test"
        with patch("src.call_log.AsyncOpenAI", return_value=client):
            result = await call_log.polish_note("left vm, gonna retry thu")

    assert result == "Left voicemail. Will retry Thursday."
    create_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_polish_note_falls_back_on_openai_error():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=Exception("boom"))

    with patch("src.call_log.settings") as s:
        s.openai_api_key = "sk-test"
        with patch("src.call_log.AsyncOpenAI", return_value=client):
            result = await call_log.polish_note("raw note")

    assert result == "raw note (unpolished)"


@pytest.mark.asyncio
async def test_polish_note_falls_back_when_no_openai_key():
    with patch("src.call_log.settings") as s:
        s.openai_api_key = ""
        result = await call_log.polish_note("raw note")
    assert result == "raw note (unpolished)"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_call_log.py -v`
Expected: all 4 tests FAIL with `ModuleNotFoundError: No module named 'src.call_log'`.

- [ ] **Step 3: Implement `src/call_log.py`**

Create the file with only the `polish_note` helper for now:

```python
from openai import AsyncOpenAI

from src.settings import settings


POLISH_SYSTEM_PROMPT = """You are a sales rep's assistant logging a call in a CRM. Given the rep's raw note, produce one clear CRM entry that captures outcome and next steps.

Rules:
- 1-3 sentences, max ~200 characters
- Past tense, third person, professional tone
- Only use facts present in the raw note — do not invent details
- No greeting, no sign-off, no bullet points, no quotation marks

Return only the polished entry, no other text."""


EMPTY_MARKER = "(call logged, no note)"


async def polish_note(raw_note: str) -> str:
    """Polish a rep's raw call note via GPT. Fail-safe with fallbacks."""
    if not raw_note or not raw_note.strip():
        return EMPTY_MARKER

    if not settings.openai_api_key:
        return f"{raw_note.strip()} (unpolished)"

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": POLISH_SYSTEM_PROMPT},
                {"role": "user", "content": raw_note.strip()},
            ],
            temperature=0.3,
            max_tokens=120,
        )
        polished = (response.choices[0].message.content or "").strip()
        if polished:
            return polished
    except Exception:
        pass

    return f"{raw_note.strip()} (unpolished)"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_call_log.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/call_log.py tests/test_call_log.py
git commit -m "feat(sf): add call_log.polish_note with GPT + fallbacks"
```

---

### Task 8: `call_log.append_call_note` orchestrator

**Files:**
- Modify: `src/call_log.py` (append)
- Modify: `tests/test_call_log.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_call_log.py`:

```python
from src.models import Practice


@pytest.mark.asyncio
async def test_append_call_note_increments_count_and_formats_line():
    practice = Practice(
        place_id="abc", name="Test", call_count=2, call_notes="[prev] existing"
    )
    user = {"id": "u1", "name": "Sarah Khan"}

    stored: dict = {}
    def fake_update(place_id: str, fields: dict, touched_by: str | None):
        stored.update(fields)
        stored["_place_id"] = place_id
        stored["_touched_by"] = touched_by
        return {**practice.model_dump(), **fields, "last_touched_by": touched_by}

    with patch("src.call_log.get_practice", return_value=practice.model_dump()):
        with patch("src.call_log.update_practice_fields", side_effect=fake_update):
            with patch("src.call_log.polish_note", AsyncMock(return_value="Polished entry.")):
                with patch("src.call_log.salesforce.sync_practice", AsyncMock(return_value={"skipped": True, "reason": "sf_not_configured"})):
                    result_practice, warning = await call_log.append_call_note(
                        "abc", "raw", user
                    )

    assert stored["call_count"] == 3
    assert "[prev] existing" in stored["call_notes"]
    assert "Sarah Khan: Polished entry." in stored["call_notes"]
    assert stored["call_notes"].splitlines()[-1].endswith("Sarah Khan: Polished entry.")
    assert stored["_touched_by"] == "u1"
    assert warning is None


@pytest.mark.asyncio
async def test_append_call_note_sets_sf_fields_when_sync_succeeds():
    practice = Practice(place_id="abc", name="Test", call_count=0, call_notes=None)
    user = {"id": "u1", "name": "Sarah Khan"}

    stored: dict = {}
    def fake_update(place_id: str, fields: dict, touched_by: str | None):
        stored.update(fields)
        return {**practice.model_dump(), **fields}

    sync_result = {
        "sf_lead_id": "00Q_NEW",
        "sf_owner_id": "005XYZ",
        "sf_owner_name": "Sarah Khan",
        "synced_at": "2026-04-23T10:22:00+00:00",
    }

    with patch("src.call_log.get_practice", return_value=practice.model_dump()):
        with patch("src.call_log.update_practice_fields", side_effect=fake_update):
            with patch("src.call_log.polish_note", AsyncMock(return_value="Polished.")):
                with patch("src.call_log.salesforce.sync_practice", AsyncMock(return_value=sync_result)):
                    await call_log.append_call_note("abc", "raw", user)

    assert stored["salesforce_lead_id"] == "00Q_NEW"
    assert stored["salesforce_owner_id"] == "005XYZ"
    assert stored["salesforce_owner_name"] == "Sarah Khan"
    assert stored["salesforce_synced_at"] == "2026-04-23T10:22:00+00:00"


@pytest.mark.asyncio
async def test_append_call_note_surfaces_warning_on_sf_failure():
    practice = Practice(place_id="abc", name="Test", call_count=0, call_notes=None)
    user = {"id": "u1", "name": "Sarah Khan"}

    with patch("src.call_log.get_practice", return_value=practice.model_dump()):
        with patch("src.call_log.update_practice_fields", return_value=practice.model_dump()):
            with patch("src.call_log.polish_note", AsyncMock(return_value="Polished.")):
                with patch("src.call_log.salesforce.sync_practice", AsyncMock(side_effect=Exception("Bad Request"))):
                    result_practice, warning = await call_log.append_call_note(
                        "abc", "raw", user
                    )

    assert warning is not None
    assert "Bad Request" in warning


@pytest.mark.asyncio
async def test_append_call_note_raises_when_practice_missing():
    with patch("src.call_log.get_practice", return_value=None):
        with pytest.raises(LookupError):
            await call_log.append_call_note("missing", "raw", {"id": "u1", "name": "X"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_call_log.py -v`
Expected: 4 new tests FAIL with `AttributeError: module 'src.call_log' has no attribute 'append_call_note'`. The 4 polish tests still PASS.

- [ ] **Step 3: Append `append_call_note` to `src/call_log.py`**

Append to `src/call_log.py`:

```python
from datetime import datetime, timezone

from src import salesforce
from src.models import Practice
from src.storage import get_practice, update_practice_fields


def _format_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


async def append_call_note(
    place_id: str, raw_note: str, user: dict
) -> tuple[dict, str | None]:
    """Polish raw_note, append to practice.call_notes, increment count, sync SF.

    Returns (updated_practice_row, sf_warning_or_none). Raises LookupError if
    the practice does not exist. Local save is always persisted; SF failures
    surface as a warning string rather than an exception.
    """
    existing = get_practice(place_id)
    if not existing:
        raise LookupError(f"Practice not found: {place_id}")

    polished = await polish_note(raw_note)
    rep_name = user.get("name") or user.get("email") or "Unknown"
    line = f"[{_format_timestamp()}] {rep_name}: {polished}"

    prior_notes = existing.get("call_notes")
    new_notes = f"{prior_notes}\n{line}" if prior_notes else line
    new_count = (existing.get("call_count") or 0) + 1

    updates: dict = {
        "call_count": new_count,
        "call_notes": new_notes,
    }

    # Build a Practice view of the post-local-save state for SF sync
    sync_view = Practice(**{**existing, **updates})

    warning: str | None = None
    try:
        sync_result = await salesforce.sync_practice(sync_view, line)
        if not sync_result.get("skipped"):
            updates["salesforce_lead_id"] = sync_result["sf_lead_id"]
            updates["salesforce_owner_id"] = sync_result["sf_owner_id"]
            updates["salesforce_owner_name"] = sync_result["sf_owner_name"]
            updates["salesforce_synced_at"] = sync_result["synced_at"]
    except Exception as e:
        warning = f"Salesforce sync failed: {e}. Local log saved."

    updated = update_practice_fields(place_id, updates, touched_by=user.get("id"))
    return updated or {**existing, **updates}, warning
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_call_log.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/call_log.py tests/test_call_log.py
git commit -m "feat(sf): add call_log.append_call_note orchestrator"
```

---

### Task 9: FastAPI endpoint `POST /api/practices/{place_id}/call/log`

**Files:**
- Modify: `api/index.py` (append endpoint + import)
- Create: `tests/test_api_call_log.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_api_call_log.py`:

```python
from unittest.mock import AsyncMock, patch

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


def test_call_log_requires_auth():
    client = TestClient(app)
    resp = client.post("/api/practices/abc/call/log", json={"note": "x"})
    assert resp.status_code == 401


def test_call_log_happy_path_returns_practice_and_null_warning(sample_rep_profile):
    _override_user(sample_rep_profile)
    fake_practice = {"place_id": "abc", "name": "Test", "call_count": 1, "call_notes": "[ts] Test Rep: polished"}

    with patch("api.index.append_call_note", AsyncMock(return_value=(fake_practice, None))):
        client = TestClient(app)
        resp = client.post("/api/practices/abc/call/log", json={"note": "raw"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["practice"]["call_count"] == 1
    assert body["sf_warning"] is None


def test_call_log_returns_warning_on_sf_failure(sample_rep_profile):
    _override_user(sample_rep_profile)
    fake_practice = {"place_id": "abc", "name": "Test", "call_count": 1}
    warning = "Salesforce sync failed: 401 Unauthorized. Local log saved."

    with patch("api.index.append_call_note", AsyncMock(return_value=(fake_practice, warning))):
        client = TestClient(app)
        resp = client.post("/api/practices/abc/call/log", json={"note": "raw"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["sf_warning"] == warning


def test_call_log_returns_404_when_practice_missing(sample_rep_profile):
    _override_user(sample_rep_profile)

    with patch("api.index.append_call_note", AsyncMock(side_effect=LookupError("Practice not found: missing"))):
        client = TestClient(app)
        resp = client.post("/api/practices/missing/call/log", json={"note": "raw"})

    assert resp.status_code == 404


def test_call_log_accepts_empty_note(sample_rep_profile):
    _override_user(sample_rep_profile)
    fake_practice = {"place_id": "abc", "name": "Test", "call_count": 1}

    called_with_note: dict = {}
    async def spy(place_id, note, user):
        called_with_note["note"] = note
        return fake_practice, None

    with patch("api.index.append_call_note", spy):
        client = TestClient(app)
        resp = client.post("/api/practices/abc/call/log", json={"note": ""})

    assert resp.status_code == 200
    assert called_with_note["note"] == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_call_log.py -v`
Expected: all tests FAIL — 404 (route not found) for most.

- [ ] **Step 3: Add the endpoint to `api/index.py`**

Add this import near the top of `api/index.py` alongside the other `from src.` imports:

```python
from src.call_log import append_call_note
```

Then append this endpoint block at the end of the file:

```python
# ======================= Call log + Salesforce sync =======================


class CallLogRequest(BaseModel):
    note: str = ""


@app.post("/api/practices/{place_id}/call/log")
async def call_log_endpoint(
    place_id: str,
    body: CallLogRequest,
    user: dict = Depends(get_current_user),
):
    try:
        practice, warning = await append_call_note(place_id, body.note, user)
    except LookupError:
        raise HTTPException(404, "Practice not found")
    return {"practice": practice, "sf_warning": warning}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_call_log.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run the full backend test suite**

Run: `pytest -q`
Expected: all tests pass (40 prior + 6 sf_auth + 9 salesforce + 8 call_log + 5 api_call_log = 68).

- [ ] **Step 6: Commit**

```bash
git add api/index.py tests/test_api_call_log.py
git commit -m "feat(sf): add POST /api/practices/{id}/call/log endpoint"
```

---

### Task 10: Frontend — extend `Practice` type + mock data

**Files:**
- Modify: `web/lib/types.ts`
- Modify: `web/lib/mock-data.ts`

- [ ] **Step 1: Extend `Practice` interface**

Open `web/lib/types.ts`. Find the `Practice` interface and add these fields right after the last existing field:

```typescript
  salesforce_lead_id: string | null
  salesforce_owner_id: string | null
  salesforce_owner_name: string | null
  salesforce_synced_at: string | null
  call_count: number
  call_notes: string | null
```

- [ ] **Step 2: Add defaults to every mock practice**

Open `web/lib/mock-data.ts`. For each object in the `mockPractices` array, add these six fields (anywhere in the object — order doesn't matter):

```typescript
    salesforce_lead_id: null,
    salesforce_owner_id: null,
    salesforce_owner_name: null,
    salesforce_synced_at: null,
    call_count: 0,
    call_notes: null,
```

- [ ] **Step 3: Typecheck the frontend**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add web/lib/types.ts web/lib/mock-data.ts
git commit -m "feat(sf): extend Practice type + mock data with SF + call log fields"
```

---

### Task 11: Frontend — `logCall` API helper

**Files:**
- Modify: `web/lib/api.ts`

- [ ] **Step 1: Add the helper**

Open `web/lib/api.ts`. Append at the end of the file (keeping the existing `apiFetch` pattern):

```typescript
export interface CallLogResponse {
  practice: Practice
  sf_warning: string | null
}

export async function logCall(placeId: string, note: string): Promise<CallLogResponse> {
  return apiFetch(`/api/practices/${placeId}/call/log`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  })
}
```

Make sure `Practice` is imported at the top of the file (check existing imports — add to the import line if missing).

- [ ] **Step 2: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/lib/api.ts
git commit -m "feat(sf): add logCall frontend API helper"
```

---

### Task 12: Frontend — `CallLogModal` component

**Files:**
- Create: `web/components/call-log-modal.tsx`

- [ ] **Step 1: Create the modal component**

Create `web/components/call-log-modal.tsx`:

```tsx
"use client"

import { useState } from "react"
import { Loader2, Phone, X } from "lucide-react"
import type { Practice } from "@/lib/types"
import { logCall, type CallLogResponse } from "@/lib/api"
import { openRingCentralCall } from "@/lib/ringcentral"

interface CallLogModalProps {
  practice: Practice
  open: boolean
  onClose: () => void
  onLogged: (response: CallLogResponse) => void
}

export default function CallLogModal({
  practice,
  open,
  onClose,
  onLogged,
}: CallLogModalProps) {
  const [note, setNote] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!open) return null

  async function handleSaveAndCall() {
    setSubmitting(true)
    setError(null)
    try {
      const response = await logCall(practice.place_id, note)
      onLogged(response)
      setNote("")
      onClose()
      if (practice.phone) openRingCentralCall(practice.phone)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to log call")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-xl bg-white shadow-xl p-5 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-serif text-base font-bold text-gray-900">
            Log call — {practice.name}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-4 h-4" />
          </button>
        </div>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="What happened? (we'll polish this for Salesforce)"
          className="w-full h-32 text-sm p-3 rounded-lg border border-gray-200 bg-white resize-none focus:outline-none focus:ring-2 focus:ring-teal-500/40"
          disabled={submitting}
        />
        {error && <p className="text-xs text-rose-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={submitting}
            className="text-xs px-4 py-2 rounded-lg text-gray-700 hover:bg-gray-100 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSaveAndCall}
            disabled={submitting}
            className="inline-flex items-center gap-1 text-xs px-4 py-2 rounded-lg bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50"
          >
            {submitting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Phone className="w-3 h-3" />}
            {submitting ? "Saving..." : "Save & Call"}
          </button>
        </div>
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
git add web/components/call-log-modal.tsx
git commit -m "feat(sf): add CallLogModal component"
```

---

### Task 13: Frontend — `CallButton` opens modal

**Files:**
- Modify: `web/components/call-button.tsx`

- [ ] **Step 1: Replace `CallButton` body**

Open `web/components/call-button.tsx` and replace the entire file contents with:

```tsx
"use client"

import { useState } from "react"
import { Phone } from "lucide-react"
import type { Practice } from "@/lib/types"
import type { CallLogResponse } from "@/lib/api"
import CallLogModal from "./call-log-modal"

interface CallButtonProps {
  practice: Practice
  label?: string
  className: string
  onClick?: (event: React.MouseEvent<HTMLButtonElement>) => void
  onLogged?: (response: CallLogResponse) => void
}

export default function CallButton({
  practice,
  label = "Call",
  className,
  onClick,
  onLogged,
}: CallButtonProps) {
  const [open, setOpen] = useState(false)

  if (!practice.phone) return null

  return (
    <>
      <button
        type="button"
        onClick={(event) => {
          onClick?.(event)
          setOpen(true)
        }}
        className={className}
        title={`Log call + dial via RingCentral: ${practice.phone}`}
      >
        <Phone className="w-3 h-3" /> {label}
      </button>
      <CallLogModal
        practice={practice}
        open={open}
        onClose={() => setOpen(false)}
        onLogged={(response) => onLogged?.(response)}
      />
    </>
  )
}
```

Note the prop change: `phone: string` is gone, replaced by `practice: Practice`. Callers need updating (Task 14 covers the practice-card caller; if other callers exist they'll surface as typecheck errors).

- [ ] **Step 2: Typecheck to surface caller updates needed**

Run: `cd web && npx tsc --noEmit`
Expected: errors ONLY in `practice-card.tsx` (and maybe `practice/[place_id]/page.tsx`) pointing at the old `phone={practice.phone}` usage. These are fixed in Tasks 14 and 15.

- [ ] **Step 3: Do NOT commit yet**

We'll commit together with Task 14 since they form one typecheck-clean unit.

---

### Task 14: Frontend — `practice-card.tsx` wires `onLogged` + last-call strip

**Files:**
- Modify: `web/components/practice-card.tsx`

- [ ] **Step 1: Update `CallButton` call site**

Open `web/components/practice-card.tsx`.

Find this block:

```tsx
        {practice.phone && (
          <CallButton
            phone={practice.phone}
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition"
          />
        )}
```

Replace it with:

```tsx
        {practice.phone && (
          <CallButton
            practice={practice}
            onClick={(e) => e.stopPropagation()}
            onLogged={(response) => onCallLogged?.(response)}
            className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition"
          />
        )}
```

Extend `PracticeCardProps` to accept the optional callback. Find `interface PracticeCardProps` and add one line:

```typescript
interface PracticeCardProps {
  practice: Practice
  isSelected: boolean
  onSelect: (placeId: string) => void
  onAnalyze: (placeId: string, refresh?: boolean) => void
  isAnalyzing: boolean
  onCallLogged?: (response: CallLogResponse) => void
}
```

Import `CallLogResponse` at the top of the file:

```typescript
import type { CallLogResponse } from "@/lib/api"
```

Add the `onCallLogged` destructure to the component signature:

```typescript
export default function PracticeCard({
  practice,
  isSelected,
  onSelect,
  onAnalyze,
  isAnalyzing,
  onCallLogged,
}: PracticeCardProps) {
```

- [ ] **Step 2: Add "Last call" strip**

Find the block that renders `last_touched_by_name`:

```tsx
      {practice.last_touched_by_name && practice.last_touched_at && (
        <p className="text-[11px] text-gray-400 mt-1">
          Last touched by {practice.last_touched_by_name} · {timeAgo(practice.last_touched_at)}
        </p>
      )}
```

Insert immediately AFTER that block:

```tsx
      {practice.call_count > 0 && (
        <p className="text-[11px] text-gray-500 mt-0.5">
          📞 {practice.call_count} {practice.call_count === 1 ? "call" : "calls"}
          {practice.salesforce_synced_at && (
            <> · last synced {timeAgo(practice.salesforce_synced_at)}</>
          )}
          {practice.salesforce_owner_name && (
            <> · owner: {practice.salesforce_owner_name} (SF)</>
          )}
        </p>
      )}
```

- [ ] **Step 3: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors, or only the one in `practice/[place_id]/page.tsx` referenced in Task 15. If the Call Prep page doesn't currently render a CallButton, typecheck passes already.

- [ ] **Step 4: Commit Tasks 13 + 14 together**

```bash
git add web/components/call-button.tsx web/components/practice-card.tsx
git commit -m "feat(sf): CallButton opens CallLogModal, card shows last-call strip"
```

- [ ] **Step 5: Wire `onCallLogged` from the map page**

Open `web/app/page.tsx`. Find where `<PracticeCard>` is rendered and pass a handler that merges the updated practice back into the list. The existing state update pattern (used for `onAnalyze`) is the model — find the setter that replaces a practice by `place_id` and reuse it.

Add prop:

```tsx
          onCallLogged={(response) => {
            setPractices((prev) =>
              prev.map((p) =>
                p.place_id === response.practice.place_id
                  ? { ...p, ...response.practice }
                  : p
              )
            )
            if (response.sf_warning) {
              console.warn("[SF]", response.sf_warning)
            }
          }}
```

(Replace `setPractices` with whatever the existing setter is named — likely `setPractices` based on the existing analyze flow.)

- [ ] **Step 6: Typecheck and commit**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

```bash
git add web/app/page.tsx
git commit -m "feat(sf): wire onCallLogged from map page into PracticeCard"
```

---

### Task 15: Frontend — Call Prep page Activity tab → Call log

**Files:**
- Modify: `web/app/practice/[place_id]/page.tsx`

- [ ] **Step 1: Replace the Activity tab with Call log**

Open `web/app/practice/[place_id]/page.tsx`.

Find the `tabs` array passed to `<ActionsPanel>`:

```tsx
              { id: "activity", label: "Activity", disabled: true },
```

Replace with:

```tsx
              { id: "calllog", label: "Call log" },
```

Find the `renderTab` branch for `"activity"`:

```tsx
              return (
                <p className="text-xs text-gray-400">
                  Activity history — coming soon.
                </p>
              )
```

Replace with:

```tsx
              if (id === "calllog") {
                return (
                  <CallLogTab
                    practice={practice}
                    onLogged={(response) => {
                      setPractice((prev) => (prev ? { ...prev, ...response.practice } : prev))
                      if (response.sf_warning) console.warn("[SF]", response.sf_warning)
                    }}
                  />
                )
              }
              return null
```

Add this import near the top:

```typescript
import CallLogTab from "@/components/call-log-tab"
```

- [ ] **Step 2: Create `web/components/call-log-tab.tsx`**

```tsx
"use client"

import { useState } from "react"
import { Phone } from "lucide-react"
import type { Practice } from "@/lib/types"
import type { CallLogResponse } from "@/lib/api"
import { timeAgo } from "@/lib/utils"
import CallLogModal from "./call-log-modal"

interface CallLogTabProps {
  practice: Practice
  onLogged: (response: CallLogResponse) => void
}

export default function CallLogTab({ practice, onLogged }: CallLogTabProps) {
  const [modalOpen, setModalOpen] = useState(false)
  const entries = (practice.call_notes ?? "").split("\n").filter(Boolean)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xs text-gray-500">
          {practice.call_count > 0 ? (
            <>
              {practice.call_count} {practice.call_count === 1 ? "call" : "calls"}
              {practice.salesforce_owner_name && (
                <> · owner: {practice.salesforce_owner_name}</>
              )}
              {practice.salesforce_synced_at && (
                <> · synced {timeAgo(practice.salesforce_synced_at)}</>
              )}
            </>
          ) : (
            "No calls logged yet."
          )}
        </div>
        <button
          onClick={() => setModalOpen(true)}
          className="inline-flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-teal-600 text-white hover:bg-teal-700"
        >
          <Phone className="w-3 h-3" /> Log call
        </button>
      </div>

      {entries.length === 0 ? (
        <p className="text-xs text-gray-400">Nothing here yet.</p>
      ) : (
        <ul className="space-y-1.5">
          {entries.map((entry, i) => (
            <li
              key={i}
              className="text-xs text-gray-700 p-2 rounded-lg bg-white/60 border border-gray-200/60 whitespace-pre-line"
            >
              {entry}
            </li>
          ))}
        </ul>
      )}

      <CallLogModal
        practice={practice}
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onLogged={(response) => {
          onLogged(response)
          setModalOpen(false)
        }}
      />
    </div>
  )
}
```

- [ ] **Step 3: Typecheck the whole frontend**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add web/app/practice/[place_id]/page.tsx web/components/call-log-tab.tsx
git commit -m "feat(sf): Call Prep Activity tab becomes Call log tab"
```

---

### Task 16: Final verification + E2E smoke test

**Files:** none modified — manual verification.

- [ ] **Step 1: Run the full backend suite**

Run: `pytest -q`
Expected: all tests pass. Zero failures, zero errors.

- [ ] **Step 2: Frontend typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Apply the DB migration on Supabase**

Confirm with the user that the SQL from Task 1 has been run in the Supabase SQL editor. If not, block here and ask the user to run it.

- [ ] **Step 4: Create the 2 custom fields on the Salesforce org**

Confirm with the user that `Call_Count__c` (Number) and `Call_Notes__c` (Long Text Area) exist on the Lead object in their SF org. Block if not.

- [ ] **Step 5: User populates SF_* env vars in .env**

Ask the user to paste their SF Connected App consumer key/secret, integration-user username, password, security token into `.env`. Restart uvicorn so settings reload.

- [ ] **Step 6: Smoke — first call (create)**

Manual steps:
1. Start backend + frontend (`uvicorn` + `npm run dev` in `/web`).
2. Sign in, open a practice that has a phone number.
3. Click Call → modal opens → type a short note ("testing integration, left vm") → Save & Call.
4. Verify in browser devtools → Network tab: `POST /api/practices/{id}/call/log` returned 200 with `sf_warning: null` and a practice payload containing `salesforce_lead_id` + `salesforce_owner_name`.
5. Verify in Supabase Table editor: the practice row has `call_count=1`, `call_notes` with one entry, `salesforce_lead_id` populated.
6. Verify in Salesforce: a new Lead exists with Company = practice name, `Call_Count__c = 1`, `Call_Notes__c` containing the timestamped entry with polished text.
7. RingCentral should have opened in a new tab.

- [ ] **Step 7: Smoke — second call (update)**

1. Click Call on the same practice again → modal → type another note → Save & Call.
2. Verify: `call_count=2` in Supabase, `Call_Count__c=2` in SF, `Call_Notes__c` now contains both entries.
3. Verify no duplicate Lead was created in SF.

- [ ] **Step 8: Smoke — SF credentials wrong**

1. Change `SF_SECURITY_TOKEN` in `.env` to `wrong`, restart uvicorn.
2. Click Call on any practice → type note → Save & Call.
3. Verify: Network response has 200 + `sf_warning: "Salesforce sync failed: ..."`. Supabase still updated.
4. Restore the correct token. Next call should succeed AND self-heal (SF count and notes reflect full local state).

- [ ] **Step 9: Smoke — SF creds absent (mock mode)**

1. Comment out all SF_* vars in `.env`, restart.
2. Click Call → note → Save & Call.
3. Verify: 200 + `sf_warning: null`. Supabase updated. No SF call made. Dialer opens.

- [ ] **Step 10: Final commit (if any stragglers) and done**

If smoke testing surfaced no issues, there's nothing to commit. If minor fixes were needed, commit them with descriptive messages.

```bash
git log --oneline -20
```

Should show the chain of ~16 commits from this plan. Feature complete.

---

## Self-review

**Spec coverage:** Each spec section has tasks — SF custom fields (Task 1 manual + Task 16 user step); Supabase columns (Task 1); env vars (Task 2); Practice model (Task 3); `sf_auth` module (Task 4); `salesforce` module helpers (Task 5); `sync_practice` (Task 6); `polish_note` (Task 7); `append_call_note` (Task 8); FastAPI endpoint (Task 9); frontend types (Task 10); API helper (Task 11); modal (Task 12); CallButton modification (Task 13); practice-card wiring (Task 14); Call log tab (Task 15); E2E smoke (Task 16). The non-goals stay non-goals — nothing in the plan builds them.

**Placeholder scan:** No TBDs, no "similar to". Every code step has complete code. Every test shows assertions. Every commit command is exact. Task 14 Step 5 says "Replace `setPractices` with whatever the existing setter is named" — this is acceptable because the implementer will literally see the setter by reading the existing file; that's a variable name lookup, not a placeholder.

**Type consistency:** `append_call_note(place_id: str, raw_note: str, user: dict)` used in Tasks 8 + 9. `sync_practice(practice: Practice, polished_line: str)` used consistently in Task 6 and 8. SF helper functions' return shapes (`create_lead → dict`, `update_lead → None`, `get_owner → tuple[str, str]`) match their test assertions. Frontend `CallLogResponse` type defined in Task 11 and imported in Tasks 12, 14. `CallButton` prop change `phone → practice` propagated to Task 14. Good.
