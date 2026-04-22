from unittest.mock import MagicMock

from src.auth import _read_supabase_token


def _mock_request(cookies: dict):
    req = MagicMock()
    req.cookies = cookies
    return req


def test_read_token_returns_none_when_no_cookies():
    assert _read_supabase_token(_mock_request({})) is None


def test_read_token_reads_single_auth_cookie():
    token_payload = '{"access_token":"abc.def.ghi"}'
    req = _mock_request({"sb-proj-auth-token": token_payload})
    assert _read_supabase_token(req) == "abc.def.ghi"


def test_read_token_reassembles_chunked_cookies():
    part0 = '{"access_token":"abc.de'
    part1 = 'f.ghi","refresh_token":"r"}'
    req = _mock_request({
        "sb-proj-auth-token.0": part0,
        "sb-proj-auth-token.1": part1,
    })
    assert _read_supabase_token(req) == "abc.def.ghi"


def test_read_token_returns_none_on_malformed_cookie():
    req = _mock_request({"sb-proj-auth-token": "not json"})
    assert _read_supabase_token(req) is None


def test_read_token_decodes_base64_prefixed_cookie():
    import base64
    payload = '{"access_token":"abc.def.ghi","refresh_token":"r"}'
    encoded = "base64-" + base64.b64encode(payload.encode()).decode()
    req = _mock_request({"sb-proj-auth-token": encoded})
    assert _read_supabase_token(req) == "abc.def.ghi"


from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.auth import get_current_user, require_admin


@pytest.mark.asyncio
async def test_get_current_user_401_when_no_token():
    req = MagicMock()
    req.cookies = {}
    with pytest.raises(HTTPException) as exc:
        await get_current_user(req)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_returns_profile(sample_rep_profile):
    token = "abc.def.ghi"
    req = MagicMock()
    req.cookies = {"sb-proj-auth-token": f'{{"access_token":"{token}"}}'}

    auth_user = MagicMock()
    auth_user.id = sample_rep_profile["id"]

    client = MagicMock()
    client.auth.get_user.return_value = MagicMock(user=auth_user)
    table = MagicMock()
    table.select.return_value = table
    table.eq.return_value = table
    table.single.return_value = table
    table.execute.return_value = MagicMock(data=sample_rep_profile)
    client.table.return_value = table

    with patch("src.auth.get_admin_client", return_value=client):
        result = await get_current_user(req)
    assert result == sample_rep_profile


@pytest.mark.asyncio
async def test_get_current_user_401_on_invalid_token():
    req = MagicMock()
    req.cookies = {"sb-proj-auth-token": '{"access_token":"bad"}'}
    client = MagicMock()
    client.auth.get_user.side_effect = Exception("invalid")
    with patch("src.auth.get_admin_client", return_value=client):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(req)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_403_when_profile_missing():
    req = MagicMock()
    req.cookies = {"sb-proj-auth-token": '{"access_token":"abc"}'}
    auth_user = MagicMock()
    auth_user.id = "missing"
    client = MagicMock()
    client.auth.get_user.return_value = MagicMock(user=auth_user)
    table = MagicMock()
    table.select.return_value = table
    table.eq.return_value = table
    table.single.return_value = table
    table.execute.return_value = MagicMock(data=None)
    client.table.return_value = table
    with patch("src.auth.get_admin_client", return_value=client):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(req)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_passes_for_admin(sample_admin_profile):
    result = await require_admin(sample_admin_profile)
    assert result == sample_admin_profile


@pytest.mark.asyncio
async def test_require_admin_403_for_rep(sample_rep_profile):
    with pytest.raises(HTTPException) as exc:
        await require_admin(sample_rep_profile)
    assert exc.value.status_code == 403
