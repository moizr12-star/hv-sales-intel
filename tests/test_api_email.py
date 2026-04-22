from fastapi.testclient import TestClient

from api.index import app

client = TestClient(app)


def test_email_draft_get_requires_auth():
    resp = client.get("/api/practices/some_id/email/draft")
    assert resp.status_code == 401


def test_email_draft_post_requires_auth():
    resp = client.post("/api/practices/some_id/email/draft")
    assert resp.status_code == 401


def test_email_draft_patch_requires_auth():
    resp = client.patch("/api/practices/some_id/email/draft", json={"subject": "x"})
    assert resp.status_code == 401


def test_email_send_requires_auth():
    resp = client.post("/api/practices/some_id/email/send")
    assert resp.status_code == 401


def test_email_messages_requires_auth():
    resp = client.get("/api/practices/some_id/email/messages")
    assert resp.status_code == 401


def test_email_poll_requires_auth():
    resp = client.post("/api/practices/some_id/email/poll")
    assert resp.status_code == 401


def test_email_mark_replied_requires_auth():
    resp = client.post("/api/practices/some_id/email/mark-replied")
    assert resp.status_code == 401
