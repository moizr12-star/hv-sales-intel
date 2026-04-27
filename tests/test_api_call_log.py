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


def test_call_log_happy_path_returns_practice_and_null_warning(sample_sdr_profile):
    _override_user(sample_sdr_profile)
    fake_practice = {"place_id": "abc", "name": "Test", "call_count": 1, "call_notes": "[ts] Test Rep: polished"}

    with patch("api.index.append_call_note", AsyncMock(return_value=(fake_practice, None))):
        client = TestClient(app)
        resp = client.post("/api/practices/abc/call/log", json={"note": "raw"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["practice"]["call_count"] == 1
    assert body["sf_warning"] is None


def test_call_log_returns_warning_on_sf_failure(sample_sdr_profile):
    _override_user(sample_sdr_profile)
    fake_practice = {"place_id": "abc", "name": "Test", "call_count": 1}
    warning = "Salesforce sync failed: 401 Unauthorized. Local log saved."

    with patch("api.index.append_call_note", AsyncMock(return_value=(fake_practice, warning))):
        client = TestClient(app)
        resp = client.post("/api/practices/abc/call/log", json={"note": "raw"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["sf_warning"] == warning


def test_call_log_returns_404_when_practice_missing(sample_sdr_profile):
    _override_user(sample_sdr_profile)

    with patch("api.index.append_call_note", AsyncMock(side_effect=LookupError("Practice not found: missing"))):
        client = TestClient(app)
        resp = client.post("/api/practices/missing/call/log", json={"note": "raw"})

    assert resp.status_code == 404


def test_call_log_accepts_empty_note(sample_sdr_profile):
    _override_user(sample_sdr_profile)
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
