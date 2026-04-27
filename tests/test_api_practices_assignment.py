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


def test_patch_assigned_to_allowed_for_admin(sample_admin_profile):
    _override_user(sample_admin_profile)
    existing = {"place_id": "p1", "name": "X", "tags": [], "status": "NEW"}

    captured: dict = {}

    def _fake_update(place_id, fields, touched_by=None):
        captured.update(fields)
        return {**existing, **fields}

    with patch("api.index.update_practice_fields", side_effect=_fake_update), \
         patch("api.index.add_tags"):
        client = TestClient(app)
        resp = client.patch(
            "/api/practices/p1",
            json={"assigned_to": "user-uuid-1"},
        )

    assert resp.status_code == 200
    assert captured["assigned_to"] == "user-uuid-1"
    assert "assigned_at" in captured
    assert captured["assigned_by"] == sample_admin_profile["id"]


def test_patch_assigned_to_blocked_for_sdr(sample_sdr_profile):
    _override_user(sample_sdr_profile)

    with patch("api.index.update_practice_fields"):
        client = TestClient(app)
        resp = client.patch(
            "/api/practices/p1",
            json={"assigned_to": "user-uuid-1"},
        )

    assert resp.status_code == 403
    assert "admin" in resp.json()["detail"].lower()


def test_patch_assigned_to_empty_string_clears_assignment(sample_admin_profile):
    _override_user(sample_admin_profile)
    existing = {
        "place_id": "p1", "name": "X", "tags": [], "status": "NEW",
        "assigned_to": "user-uuid-1",
    }

    captured: dict = {}

    def _fake_update(place_id, fields, touched_by=None):
        captured.update(fields)
        return {**existing, **fields}

    with patch("api.index.update_practice_fields", side_effect=_fake_update), \
         patch("api.index.add_tags"):
        client = TestClient(app)
        resp = client.patch(
            "/api/practices/p1",
            json={"assigned_to": ""},
        )

    assert resp.status_code == 200
    assert captured["assigned_to"] is None
    assert captured["assigned_at"] is None
    assert captured["assigned_by"] is None
