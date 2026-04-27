import pytest


@pytest.fixture
def sample_sdr_profile() -> dict:
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "sdr@example.com",
        "name": "Test SDR",
        "role": "sdr",
        "created_at": "2026-04-22T00:00:00Z",
    }


@pytest.fixture
def sample_admin_profile() -> dict:
    return {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "admin@example.com",
        "name": "Test Admin",
        "role": "admin",
        "created_at": "2026-04-22T00:00:00Z",
    }
