from unittest.mock import AsyncMock, patch

import pytest

from src import email_send


@pytest.mark.asyncio
async def test_send_email_posts_to_graph_and_retrieves_message_id():
    send_resp = AsyncMock()
    send_resp.status_code = 202
    send_resp.raise_for_status = lambda: None

    sent_items_resp = AsyncMock()
    sent_items_resp.status_code = 200
    sent_items_resp.raise_for_status = lambda: None
    sent_items_resp.json = lambda: {
        "value": [{
            "internetMessageId": "<msg-123@host>",
            "subject": "Hello",
            "sentDateTime": "2026-04-22T10:00:00Z",
            "toRecipients": [{"emailAddress": {"address": "to@example.com"}}],
        }]
    }

    client = AsyncMock()
    client.post = AsyncMock(return_value=send_resp)
    client.get = AsyncMock(return_value=sent_items_resp)

    with patch("src.email_send.get_access_token", return_value="tok"):
        with patch("src.email_send.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value = client
            result = await email_send.send_email("to@example.com", "Hello", "Body text")

    assert result["message_id"] == "<msg-123@host>"
    assert "sent_at" in result

    call = client.post.call_args
    assert "sendMail" in call.args[0]
    payload = call.kwargs["json"]
    assert payload["message"]["subject"] == "Hello"
    assert payload["message"]["toRecipients"][0]["emailAddress"]["address"] == "to@example.com"
    assert payload["message"]["body"]["content"] == "Body text"


@pytest.mark.asyncio
async def test_send_email_raises_on_graph_error():
    def raise_http():
        import httpx
        raise httpx.HTTPStatusError("401", request=None, response=None)

    resp = AsyncMock()
    resp.raise_for_status = raise_http

    client = AsyncMock()
    client.post = AsyncMock(return_value=resp)

    with patch("src.email_send.get_access_token", return_value="tok"):
        with patch("src.email_send.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value = client
            with pytest.raises(Exception):
                await email_send.send_email("to@example.com", "s", "b")
