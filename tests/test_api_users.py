from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.index import app
from src.auth import require_admin


def _override_admin(profile: dict):
    app.dependency_overrides[require_admin] = lambda: profile


@pytest.fixture(autouse=True)
def cleanup():
    yield
    app.dependency_overrides.clear()


def test_create_user_rejects_bad_email_domain(sample_admin_profile):
    _override_admin(sample_admin_profile)
    client = TestClient(app)
    resp = client.post("/api/admin/users", json={
        "email": "rep@example.com",
        "name": "Rep",
        "password": "Healthy123!",
    })
    assert resp.status_code == 400
    assert "@healthandgroup.com" in resp.json()["detail"]


def test_create_user_rejects_double_dash_email(sample_admin_profile):
    _override_admin(sample_admin_profile)
    client = TestClient(app)
    resp = client.post("/api/admin/users", json={
        "email": "rep--admin@healthandgroup.com",
        "name": "Rep",
        "password": "Healthy123!",
    })
    assert resp.status_code == 400
    assert "--" in resp.json()["detail"]


def test_create_user_rejects_weak_password(sample_admin_profile):
    _override_admin(sample_admin_profile)
    client = TestClient(app)
    resp = client.post("/api/admin/users", json={
        "email": "rep@healthandgroup.com",
        "name": "Rep",
        "password": "weak",
    })
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Password" in detail


def test_create_user_maps_duplicate_email_to_friendly_message(sample_admin_profile):
    _override_admin(sample_admin_profile)

    fake_admin = MagicMock()
    fake_admin.auth.admin.create_user.side_effect = Exception("User already registered")

    with patch("api.index.get_admin_client", return_value=fake_admin):
        client = TestClient(app)
        resp = client.post("/api/admin/users", json={
            "email": "rep@healthandgroup.com",
            "name": "Rep",
            "password": "Healthy123!",
        })

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Email already in use."


def test_create_user_happy_path(sample_admin_profile):
    _override_admin(sample_admin_profile)

    created_user = MagicMock()
    created_user.user.id = "new-user-id"
    fake_admin = MagicMock()
    fake_admin.auth.admin.create_user.return_value = created_user
    profile_select = MagicMock()
    profile_select.execute.return_value.data = {
        "id": "new-user-id",
        "email": "rep@healthandgroup.com",
        "name": "Rep",
        "role": "sdr",
        "created_at": "2026-04-27T00:00:00Z",
    }
    fake_admin.table.return_value.select.return_value.eq.return_value.single.return_value = profile_select

    with patch("api.index.get_admin_client", return_value=fake_admin):
        client = TestClient(app)
        resp = client.post("/api/admin/users", json={
            "email": "rep@healthandgroup.com",
            "name": "Rep",
            "password": "Healthy123!",
            "role": "sdr",
        })

    assert resp.status_code == 200
    assert resp.json()["email"] == "rep@healthandgroup.com"
