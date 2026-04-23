from unittest.mock import AsyncMock, patch

import pytest

from src import sf_auth


@pytest.fixture(autouse=True)
def reset_cache():
    sf_auth._cached_access_token = None
    sf_auth._cached_instance_url = None
    yield
    sf_auth._cached_access_token = None
    sf_auth._cached_instance_url = None


def test_is_configured_false_when_any_missing():
    with patch("src.sf_auth.settings") as s:
        s.sf_client_id = "a"
        s.sf_client_secret = "b"
        s.sf_username = "c"
        s.sf_password = "d"
        s.sf_security_token = ""
        assert sf_auth.is_configured() is False


def test_is_configured_true_when_all_set():
    with patch("src.sf_auth.settings") as s:
        s.sf_client_id = "a"
        s.sf_client_secret = "b"
        s.sf_username = "c"
        s.sf_password = "d"
        s.sf_security_token = "e"
        assert sf_auth.is_configured() is True


@pytest.mark.asyncio
async def test_fetches_token_when_cache_empty():
    fake_post = AsyncMock()
    fake_post.return_value.json = lambda: {
        "access_token": "tok-abc",
        "instance_url": "https://yourorg.my.salesforce.com",
    }
    fake_post.return_value.raise_for_status = lambda: None

    with patch("src.sf_auth.settings") as s:
        s.sf_client_id = "cid"
        s.sf_client_secret = "csec"
        s.sf_username = "u@example.com"
        s.sf_password = "pw"
        s.sf_security_token = "tok"
        s.sf_login_url = "https://login.salesforce.com"
        with patch("src.sf_auth.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value.post = fake_post
            token, url = await sf_auth.get_access_token()

    assert token == "tok-abc"
    assert url == "https://yourorg.my.salesforce.com"
    assert sf_auth._cached_access_token == "tok-abc"

    call_args = fake_post.call_args
    posted_data = call_args.kwargs["data"]
    assert posted_data["grant_type"] == "password"
    assert posted_data["password"] == "pwtok"


@pytest.mark.asyncio
async def test_reuses_cached_token():
    sf_auth._cached_access_token = "cached"
    sf_auth._cached_instance_url = "https://cached.salesforce.com"
    token, url = await sf_auth.get_access_token()
    assert token == "cached"
    assert url == "https://cached.salesforce.com"


@pytest.mark.asyncio
async def test_invalidate_clears_cache():
    sf_auth._cached_access_token = "cached"
    sf_auth._cached_instance_url = "https://cached.salesforce.com"
    sf_auth.invalidate_token()
    assert sf_auth._cached_access_token is None
    assert sf_auth._cached_instance_url is None


@pytest.mark.asyncio
async def test_raises_when_not_configured():
    with patch("src.sf_auth.settings") as s:
        s.sf_client_id = ""
        s.sf_client_secret = ""
        s.sf_username = ""
        s.sf_password = ""
        s.sf_security_token = ""
        with pytest.raises(RuntimeError, match="not configured"):
            await sf_auth.get_access_token()
