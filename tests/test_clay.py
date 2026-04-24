from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src import clay
from src.models import Practice


def _practice(**overrides) -> Practice:
    base = dict(
        place_id="abc",
        name="Houston Family Dental",
        website="https://hfd.com",
        city="Houston",
        state="TX",
        phone="+17135551234",
    )
    base.update(overrides)
    return Practice(**base)


@pytest.mark.asyncio
async def test_trigger_enrichment_skips_when_webhook_url_missing():
    with patch("src.clay.settings") as s:
        s.clay_table_webhook_url = ""
        s.clay_table_api_key = "anything"
        result = await clay.trigger_enrichment(_practice())
    assert result == {"skipped": True, "reason": "clay_not_configured"}


@pytest.mark.asyncio
async def test_trigger_enrichment_omits_auth_header_when_no_api_key():
    fake_post = AsyncMock()
    fake_post.return_value.status_code = 200
    fake_post.return_value.raise_for_status = lambda: None

    with patch("src.clay.settings") as s:
        s.clay_table_webhook_url = "https://api.clay.com/v3/sources/webhook/abc"
        s.clay_table_api_key = ""
        with patch("src.clay.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value.post = fake_post
            result = await clay.trigger_enrichment(_practice())

    assert result == {"status": "pending"}
    headers = fake_post.call_args.kwargs["headers"]
    assert "Authorization" not in headers
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_trigger_enrichment_posts_correct_payload():
    fake_post = AsyncMock()
    fake_post.return_value.status_code = 200
    fake_post.return_value.raise_for_status = lambda: None

    with patch("src.clay.settings") as s:
        s.clay_table_webhook_url = "https://clay.example/v1/rows"
        s.clay_table_api_key = "ck_test"
        with patch("src.clay.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value.post = fake_post
            result = await clay.trigger_enrichment(_practice())

    assert result == {"status": "pending"}
    url_called = fake_post.call_args.args[0]
    assert url_called == "https://clay.example/v1/rows"

    headers = fake_post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer ck_test"
    assert headers["Content-Type"] == "application/json"

    body = fake_post.call_args.kwargs["json"]
    assert body == {
        "place_id": "abc",
        "practice_name": "Houston Family Dental",
        "website": "https://hfd.com",
        "city": "Houston",
        "state": "TX",
        "phone": "+17135551234",
    }


@pytest.mark.asyncio
async def test_trigger_enrichment_raises_on_http_error():
    fake_post = AsyncMock()
    def raise_for_status():
        raise httpx.HTTPStatusError("boom", request=None, response=None)
    fake_post.return_value.raise_for_status = raise_for_status

    with patch("src.clay.settings") as s:
        s.clay_table_webhook_url = "https://clay.example/v1/rows"
        s.clay_table_api_key = "ck_test"
        with patch("src.clay.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value.post = fake_post
            with pytest.raises(httpx.HTTPStatusError):
                await clay.trigger_enrichment(_practice())
