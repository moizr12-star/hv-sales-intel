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
        with patch("api.index.update_practice_fields", return_value=failed):
            with patch("api.index.trigger_enrichment", trigger_err):
                client = TestClient(app)
                resp = client.post("/api/practices/abc/enrich")

    assert resp.status_code == 200
    body = resp.json()
    assert body["practice"]["enrichment_status"] == "failed"
    assert body["clay_warning"] is not None
    assert "502" in body["clay_warning"] or "Bad Gateway" in body["clay_warning"]
