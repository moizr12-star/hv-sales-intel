from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.index import app
from src.auth import get_current_user


def _override_user(profile: dict):
    app.dependency_overrides[get_current_user] = lambda: profile


@pytest.fixture(autouse=True)
def cleanup():
    yield
    app.dependency_overrides.clear()


# ---------- analyze → RESEARCHED ----------


def test_analyze_appends_researched_tag(sample_admin_profile):
    _override_user(sample_admin_profile)

    existing = {"place_id": "p1", "name": "X", "status": "NEW", "tags": []}
    analysis = {
        "summary": "s",
        "pain_points": "[]",
        "sales_angles": "[]",
        "lead_score": 50,
        "urgency_score": 50,
        "hiring_signal_score": 50,
        "call_script": None,
        "email_draft": None,
        "email_draft_updated_at": None,
        "website_doctor_name": None,
        "website_doctor_phone": None,
    }

    async def _aresult(*args, **kwargs):
        return analysis

    with patch("api.index.get_practice", return_value=existing), \
         patch("api.index.analyze_practice", new=_aresult), \
         patch("api.index.update_practice_analysis", return_value={**existing, **analysis}), \
         patch("api.index.add_tags") as add_tags_mock:
        client = TestClient(app)
        resp = client.post("/api/practices/p1/analyze", json={"force": True})

    assert resp.status_code == 200
    add_tags_mock.assert_any_call("p1", ["RESEARCHED"])


# ---------- script gen → SCRIPT_READY ----------


def test_get_script_appends_script_ready_tag(sample_admin_profile):
    _override_user(sample_admin_profile)
    existing = {
        "place_id": "p1", "name": "X", "status": "RESEARCHED", "tags": ["RESEARCHED"],
        "category": "dental", "summary": "s", "pain_points": "[]", "sales_angles": "[]",
        "city": "Boise", "state": "ID", "rating": 4.5, "review_count": 30,
        "website_doctor_name": None, "owner_name": None, "owner_title": None,
        "call_script": None,
    }
    script = {"sections": [{"title": "Opening", "icon": "phone", "content": "..."}] * 5}

    async def _agen(*args, **kwargs):
        return script

    with patch("api.index.get_practice", return_value=existing), \
         patch("api.index.generate_script", new=_agen), \
         patch("api.index.update_practice_fields"), \
         patch("api.index.add_tags") as add_tags_mock:
        client = TestClient(app)
        resp = client.get("/api/practices/p1/script")

    assert resp.status_code == 200
    add_tags_mock.assert_any_call("p1", ["SCRIPT_READY"])


# ---------- Clay webhook → ENRICHED ----------


def test_clay_webhook_appends_enriched_tag_on_success():
    existing = {"place_id": "p1", "name": "X", "tags": []}

    with patch("api.index.app_settings") as s, \
         patch("api.index.get_practice", return_value=existing), \
         patch("api.index.update_practice_fields"), \
         patch("api.index.add_tags") as add_tags_mock:
        s.clay_inbound_secret = "secret"
        client = TestClient(app)
        resp = client.post(
            "/api/webhooks/clay",
            headers={"X-Clay-Secret": "secret"},
            json={"place_id": "p1", "owner_name": "Dr. Y", "owner_email": "y@y.com"},
        )

    assert resp.status_code == 200
    add_tags_mock.assert_any_call("p1", ["ENRICHED"])


def test_clay_webhook_does_not_tag_on_no_contact():
    existing = {"place_id": "p1", "name": "X", "tags": []}

    with patch("api.index.app_settings") as s, \
         patch("api.index.get_practice", return_value=existing), \
         patch("api.index.update_practice_fields"), \
         patch("api.index.add_tags") as add_tags_mock:
        s.clay_inbound_secret = "secret"
        client = TestClient(app)
        resp = client.post(
            "/api/webhooks/clay",
            headers={"X-Clay-Secret": "secret"},
            json={"place_id": "p1"},  # no owner data
        )

    assert resp.status_code == 200
    add_tags_mock.assert_not_called()


# ---------- call log + email send → CONTACTED ----------


def test_call_log_appends_contacted_tag(sample_admin_profile):
    _override_user(sample_admin_profile)
    practice_after = {
        "place_id": "p1", "id": 1, "name": "X", "tags": ["CONTACTED"],
        "call_count": 1, "call_notes": "logged", "status": "RESEARCHED",
    }

    async def _alog(*args, **kwargs):
        return practice_after, None

    with patch("api.index.append_call_note", new=_alog), \
         patch("api.index.add_tags") as add_tags_mock:
        client = TestClient(app)
        resp = client.post(
            "/api/practices/p1/call/log",
            json={"note": "rang and chatted"},
        )

    assert resp.status_code == 200
    add_tags_mock.assert_any_call("p1", ["CONTACTED"])


# ---------- email poll → REPLIED ----------


def test_email_poll_appends_replied_tag_on_inbound(sample_admin_profile):
    _override_user(sample_admin_profile)
    practice = {"place_id": "p1", "id": 1, "tags": [], "email": "x@y.com", "status": "CONTACTED"}

    async def _apoll(*args, **kwargs):
        return [{"message_id": "m1", "subject": "Re: Hi", "body": "thanks", "in_reply_to": "out1"}]

    with patch("api.index._email_configured", return_value=True), \
         patch("api.index.get_practice", return_value=practice), \
         patch("api.index.list_outbound_message_ids", return_value=["out1"]), \
         patch("api.index.list_email_messages", return_value=[]), \
         patch("api.index.poll_replies", new=_apoll), \
         patch("api.index.insert_email_message", return_value={"id": 99, "direction": "in"}), \
         patch("api.index.update_practice_fields"), \
         patch("api.index.add_tags") as add_tags_mock:
        client = TestClient(app)
        resp = client.post("/api/practices/p1/email/poll")

    assert resp.status_code == 200
    add_tags_mock.assert_any_call("p1", ["REPLIED"])


# ---------- PATCH practice → status-change tags ----------


@pytest.mark.parametrize("status,expected_tag", [
    ("MEETING SET", "MEETING_SET"),
    ("CLOSED WON", "CLOSED_WON"),
    ("CLOSED LOST", "CLOSED_LOST"),
])
def test_patch_practice_tags_on_closing_status(sample_admin_profile, status, expected_tag):
    _override_user(sample_admin_profile)
    existing = {"place_id": "p1", "id": 1, "name": "X", "tags": [], "status": "CONTACTED"}

    with patch("api.index.update_practice_fields", return_value={**existing, "status": status}), \
         patch("api.index.add_tags") as add_tags_mock:
        client = TestClient(app)
        resp = client.patch("/api/practices/p1", json={"status": status})

    assert resp.status_code == 200
    add_tags_mock.assert_any_call("p1", [expected_tag])


def test_email_send_appends_contacted_tag(sample_admin_profile):
    _override_user(sample_admin_profile)
    existing = {
        "place_id": "p1", "id": 1, "name": "X", "tags": [],
        "email": "x@y.com", "status": "RESEARCHED",
        "email_draft": '{"subject": "Hi", "body": "Hello"}',
    }

    async def _asend(*args, **kwargs):
        return {"message_id": "m1"}

    with patch("api.index._email_configured", return_value=True), \
         patch("api.index.get_practice", return_value=existing), \
         patch("api.index.send_email", new=_asend), \
         patch("api.index.insert_email_message", return_value={"id": 99}), \
         patch("api.index.update_practice_fields"), \
         patch("api.index.add_tags") as add_tags_mock:
        client = TestClient(app)
        resp = client.post("/api/practices/p1/email/send")

    assert resp.status_code == 200
    add_tags_mock.assert_any_call("p1", ["CONTACTED"])
