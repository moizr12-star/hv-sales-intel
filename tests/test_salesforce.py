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
