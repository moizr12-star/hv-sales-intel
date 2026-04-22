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
