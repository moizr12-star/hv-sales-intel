import time
from unittest.mock import AsyncMock, patch

import pytest

from src import ms_auth


@pytest.fixture(autouse=True)
def reset_cache():
    ms_auth._cached_token = None
    ms_auth._cached_expires_at = 0.0
    yield
    ms_auth._cached_token = None
    ms_auth._cached_expires_at = 0.0


@pytest.mark.asyncio
async def test_fetches_token_when_cache_empty():
    fake_post = AsyncMock()
    fake_post.return_value.json = lambda: {"access_token": "tok", "expires_in": 3600}
    fake_post.return_value.raise_for_status = lambda: None

    with patch("src.ms_auth.settings") as s:
        s.ms_tenant_id = "t"
        s.ms_client_id = "c"
        s.ms_client_secret = "s"
        s.ms_refresh_token = "r"
        with patch("src.ms_auth.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value.post = fake_post
            token = await ms_auth.get_access_token()

    assert token == "tok"
    assert ms_auth._cached_token == "tok"
    assert ms_auth._cached_expires_at > time.time()


@pytest.mark.asyncio
async def test_reuses_cached_token():
    ms_auth._cached_token = "cached"
    ms_auth._cached_expires_at = time.time() + 1000
    token = await ms_auth.get_access_token()
    assert token == "cached"


@pytest.mark.asyncio
async def test_raises_when_not_configured():
    with patch("src.ms_auth.settings") as s:
        s.ms_tenant_id = ""
        s.ms_client_id = ""
        s.ms_client_secret = ""
        s.ms_refresh_token = ""
        with pytest.raises(RuntimeError, match="not configured"):
            await ms_auth.get_access_token()
