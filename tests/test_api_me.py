from unittest.mock import patch

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


def test_me_returns_is_bootstrap_admin_true_for_bootstrap(sample_admin_profile):
    bootstrap_user = {**sample_admin_profile, "email": "boss@healthandgroup.com"}
    _override_user(bootstrap_user)

    with patch("src.auth.settings") as s:
        s.bootstrap_admin_email = "boss@healthandgroup.com"
        client = TestClient(app)
        resp = client.get("/api/me")

    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "boss@healthandgroup.com"
    assert body["is_bootstrap_admin"] is True


def test_me_returns_is_bootstrap_admin_false_for_other_admin(sample_admin_profile):
    other_admin = {**sample_admin_profile, "email": "other@healthandgroup.com"}
    _override_user(other_admin)

    with patch("src.auth.settings") as s:
        s.bootstrap_admin_email = "boss@healthandgroup.com"
        client = TestClient(app)
        resp = client.get("/api/me")

    assert resp.status_code == 200
    assert resp.json()["is_bootstrap_admin"] is False


def test_me_requires_auth():
    client = TestClient(app)
    resp = client.get("/api/me")
    assert resp.status_code == 401
