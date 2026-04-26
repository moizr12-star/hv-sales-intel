from unittest.mock import AsyncMock, patch

import pytest

from src import salesforce
from src.models import Practice


def _practice(**overrides) -> Practice:
    base = dict(
        place_id="abc",
        name="Houston Family Dental",
        address="1234 Main St",
        city="Houston",
        state="TX",
        phone="+17135551234",
        email="hello@hfd.com",
        website="https://hfd.com",
        owner_name="Office Manager",
        owner_phone="+17135551234",
        owner_email="",
        lead_score=82,
        urgency_score=70,
        hiring_signal_score=60,
    )
    base.update(overrides)
    return Practice(**base)


def test_is_configured_false_when_either_missing():
    with patch("src.salesforce.settings") as s:
        s.sf_apex_url = "https://x/apexrest/lead/"
        s.sf_api_key = ""
        assert salesforce.is_configured() is False
    with patch("src.salesforce.settings") as s:
        s.sf_apex_url = ""
        s.sf_api_key = "k"
        assert salesforce.is_configured() is False


def test_is_configured_true_when_both_set():
    with patch("src.salesforce.settings") as s:
        s.sf_apex_url = "https://x/apexrest/lead/"
        s.sf_api_key = "k"
        assert salesforce.is_configured() is True


def test_build_create_payload_includes_all_required_fields():
    payload = salesforce._build_create_payload(
        _practice(), call_note_line="[ts] Rep: init"
    )
    assert payload["Company"] == "Houston Family Dental"
    assert payload["OwnerName"] == "Office Manager"
    assert payload["OwnerPhone"] == "+17135551234"
    assert payload["OwnerEmail"] == ""
    assert payload["Email"] == "hello@hfd.com"
    assert payload["Website"] == "https://hfd.com"
    assert payload["Street"] == "1234 Main St"
    assert payload["City"] == "Houston"
    assert payload["State"] == "TX"
    assert payload["Country"] == "USA"
    assert payload["Industry"] == "Healthcare"
    assert payload["LeadSource"] == "HV Sales Intel"
    assert payload["Status"] == "Working - Contacted"
    assert payload["Lead_Type__c"] == "Outbound"
    assert payload["Description"] == "Lead Score: 82 | Urgency: 70 | Hiring Signal: 60"
    assert payload["Call_Count__c"] == "1"
    assert payload["Call_Notes__c"] == "[ts] Rep: init"


def test_build_create_payload_falls_back_owner_phone_to_practice_phone():
    p = _practice(owner_phone=None, phone="+19998887777")
    payload = salesforce._build_create_payload(p, call_note_line="[ts] Rep: init")
    assert payload["OwnerPhone"] == "+19998887777"


def test_build_create_payload_handles_missing_optionals():
    p = _practice(
        email=None,
        website=None,
        city=None,
        state=None,
        owner_name=None,
        owner_phone=None,
        owner_email=None,
        phone=None,
        lead_score=None,
        urgency_score=None,
        hiring_signal_score=None,
    )
    payload = salesforce._build_create_payload(p, call_note_line="[ts] Rep: init")
    assert payload["Email"] == ""
    assert payload["Website"] == ""
    assert payload["City"] == ""
    assert payload["State"] == ""
    assert payload["OwnerName"] == ""
    assert payload["OwnerPhone"] == ""
    assert payload["Description"] == ""


def test_build_update_payload_only_call_fields():
    body = salesforce._build_update_payload("00Q123", 3, "[t1]\n[t2]\n[t3]")
    assert body == {
        "Id": "00Q123",
        "Status": "Working - Contacted",
        "Lead_Type__c": "Outbound",
        "Call_Count__c": "3",
        "Call_Notes__c": "[t1]\n[t2]\n[t3]",
    }


@pytest.mark.asyncio
async def test_create_lead_posts_with_api_key_header():
    fake_post = AsyncMock()
    fake_post.return_value.status_code = 200
    fake_post.return_value.json = lambda: {
        "success": True,
        "message": "Lead created successfully",
        "leadId": "00Q_NEW",
    }
    fake_post.return_value.raise_for_status = lambda: None

    with patch("src.salesforce.settings") as s:
        s.sf_apex_url = "https://x/apexrest/hv-sales-intel/lead/"
        s.sf_api_key = "MY_KEY"
        with patch("src.salesforce.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value.post = fake_post
            result = await salesforce.create_lead(_practice(), "[ts] Rep: init")

    assert result["leadId"] == "00Q_NEW"
    url_called = fake_post.call_args.args[0]
    assert url_called == "https://x/apexrest/hv-sales-intel/lead/"
    headers = fake_post.call_args.kwargs["headers"]
    assert headers["x-api-key"] == "MY_KEY"
    assert headers["Content-Type"] == "application/json"
    posted = fake_post.call_args.kwargs["json"]
    assert posted["Lead_Type__c"] == "Outbound"
    assert posted["Company"] == "Houston Family Dental"


@pytest.mark.asyncio
async def test_update_lead_puts_with_api_key_header():
    fake_put = AsyncMock()
    fake_put.return_value.status_code = 200
    fake_put.return_value.json = lambda: {
        "success": True,
        "message": "Lead updated successfully",
        "leadId": "00Q123",
    }
    fake_put.return_value.raise_for_status = lambda: None

    with patch("src.salesforce.settings") as s:
        s.sf_apex_url = "https://x/apexrest/hv-sales-intel/lead/"
        s.sf_api_key = "MY_KEY"
        with patch("src.salesforce.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value.put = fake_put
            await salesforce.update_lead("00Q123", 3, "[t1]\n[t2]\n[t3]")

    url_called = fake_put.call_args.args[0]
    body = fake_put.call_args.kwargs["json"]
    headers = fake_put.call_args.kwargs["headers"]
    assert url_called == "https://x/apexrest/hv-sales-intel/lead/"
    assert headers["x-api-key"] == "MY_KEY"
    assert body["Id"] == "00Q123"
    assert body["Lead_Type__c"] == "Outbound"
    assert body["Call_Count__c"] == "3"
    assert body["Call_Notes__c"] == "[t1]\n[t2]\n[t3]"


@pytest.mark.asyncio
async def test_sync_practice_skips_when_not_configured():
    with patch("src.salesforce.is_configured", return_value=False):
        result = await salesforce.sync_practice(_practice(), "[ts] Rep: init")
    assert result == {"skipped": True, "reason": "sf_not_configured"}


@pytest.mark.asyncio
async def test_sync_practice_creates_when_no_lead_id():
    practice = _practice()
    assert practice.salesforce_lead_id is None

    create_mock = AsyncMock(return_value={
        "success": True,
        "message": "Lead created successfully",
        "leadId": "00Q_NEW",
    })

    with patch("src.salesforce.is_configured", return_value=True):
        with patch("src.salesforce.create_lead", create_mock):
            result = await salesforce.sync_practice(practice, "[ts] Rep: init")

    assert result["sf_lead_id"] == "00Q_NEW"
    assert result["sf_owner_name"] == "Office Manager"
    assert "synced_at" in result
    create_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_practice_updates_when_lead_id_exists():
    practice = _practice(
        salesforce_lead_id="00Q_EXISTING",
        call_count=2,
        call_notes="[t1]\n[t2]",
    )
    update_mock = AsyncMock(return_value={
        "success": True,
        "message": "Lead updated successfully",
        "leadId": "00Q_EXISTING",
    })

    with patch("src.salesforce.is_configured", return_value=True):
        with patch("src.salesforce.update_lead", update_mock):
            result = await salesforce.sync_practice(practice, "[t3]")

    assert result["sf_lead_id"] == "00Q_EXISTING"
    update_mock.assert_awaited_once_with("00Q_EXISTING", 2, "[t1]\n[t2]")


@pytest.mark.asyncio
async def test_sync_practice_raises_when_response_missing_lead_id():
    create_mock = AsyncMock(return_value={"success": True, "message": "Lead created successfully"})

    with patch("src.salesforce.is_configured", return_value=True):
        with patch("src.salesforce.create_lead", create_mock):
            with pytest.raises(RuntimeError, match="missing leadId"):
                await salesforce.sync_practice(_practice(), "[ts] Rep: init")
