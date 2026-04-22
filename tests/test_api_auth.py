from fastapi.testclient import TestClient

from api.index import app

client = TestClient(app)


def test_health_is_public():
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_list_practices_requires_auth():
    resp = client.get("/api/practices")
    assert resp.status_code == 401


def test_get_practice_requires_auth():
    resp = client.get("/api/practices/some_id")
    assert resp.status_code == 401


def test_patch_practice_requires_auth():
    resp = client.patch("/api/practices/some_id", json={"status": "CONTACTED"})
    assert resp.status_code == 401


def test_me_requires_auth():
    resp = client.get("/api/me")
    assert resp.status_code == 401


def test_admin_users_list_requires_auth():
    resp = client.get("/api/admin/users")
    assert resp.status_code == 401


def test_admin_users_create_requires_auth():
    resp = client.post(
        "/api/admin/users",
        json={"email": "x@y.com", "name": "X", "password": "p"},
    )
    assert resp.status_code == 401
