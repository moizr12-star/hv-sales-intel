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
