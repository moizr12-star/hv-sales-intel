from unittest.mock import AsyncMock, patch

import pytest

from src import email_poll


FAKE_GRAPH_RESPONSE = {
    "value": [
        {
            "internetMessageId": "<reply-1@host>",
            "subject": "Re: Staffing",
            "from": {"emailAddress": {"address": "dr@practice.com"}},
            "toRecipients": [{"emailAddress": {"address": "sales@hv.com"}}],
            "sentDateTime": "2026-04-22T10:00:00Z",
            "receivedDateTime": "2026-04-22T10:00:01Z",
            "body": {"contentType": "text", "content": "Yes, interested."},
            "internetMessageHeaders": [
                {"name": "In-Reply-To", "value": "<outbound-1@hv.com>"},
            ],
        },
        {
            # Not threaded — matches by envelope sender
            "internetMessageId": "<reply-2@host>",
            "subject": "Question",
            "from": {"emailAddress": {"address": "dr@practice.com"}},
            "toRecipients": [{"emailAddress": {"address": "sales@hv.com"}}],
            "sentDateTime": "2026-04-22T11:00:00Z",
            "receivedDateTime": "2026-04-22T11:00:01Z",
            "body": {"contentType": "text", "content": "One more question."},
            "internetMessageHeaders": [],
        },
    ]
}


@pytest.mark.asyncio
async def test_poll_replies_threads_by_in_reply_to_and_by_envelope():
    get_resp = AsyncMock()
    get_resp.raise_for_status = lambda: None
    get_resp.json = lambda: FAKE_GRAPH_RESPONSE

    client = AsyncMock()
    client.get = AsyncMock(return_value=get_resp)

    with patch("src.email_poll.get_access_token", return_value="tok"):
        with patch("src.email_poll.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value = client
            results = await email_poll.poll_replies(
                practice_email="dr@practice.com",
                outbound_message_ids=["<outbound-1@hv.com>"],
                since_iso="2026-04-22T00:00:00Z",
            )

    assert len(results) == 2
    assert results[0]["message_id"] == "<reply-1@host>"
    assert results[0]["in_reply_to"] == "<outbound-1@hv.com>"
    assert results[1]["message_id"] == "<reply-2@host>"
    # Envelope-match fallback
    assert results[1]["in_reply_to"] is None


@pytest.mark.asyncio
async def test_poll_replies_returns_empty_when_no_new_messages():
    get_resp = AsyncMock()
    get_resp.raise_for_status = lambda: None
    get_resp.json = lambda: {"value": []}
    client = AsyncMock()
    client.get = AsyncMock(return_value=get_resp)

    with patch("src.email_poll.get_access_token", return_value="tok"):
        with patch("src.email_poll.httpx.AsyncClient") as client_cls:
            client_cls.return_value.__aenter__.return_value = client
            results = await email_poll.poll_replies(
                practice_email="dr@practice.com",
                outbound_message_ids=[],
                since_iso="2026-04-22T00:00:00Z",
            )
    assert results == []
