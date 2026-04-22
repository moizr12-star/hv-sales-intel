from datetime import datetime, timezone

import httpx

from src.ms_auth import get_access_token

GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/me/sendMail"
GRAPH_SENT_ITEMS_URL = (
    "https://graph.microsoft.com/v1.0/me/mailFolders/sentitems/messages"
    "?$top=5&$orderby=sentDateTime desc"
    "&$select=internetMessageId,subject,sentDateTime,toRecipients"
)


async def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email via Microsoft Graph sendMail.

    v1 sends from MS_SENDER_EMAIL (the mailbox associated with the refresh
    token). No per-user `from` or `reply-to` override — keeps replies routed
    to the shared mailbox the poll reads.

    Returns { message_id, sent_at }. Raises on failure.
    """
    token = await get_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        },
        "saveToSentItems": True,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        send_resp = await client.post(GRAPH_SEND_URL, headers=headers, json=payload)
        send_resp.raise_for_status()

        # sendMail returns 202 Accepted with no body. Fetch the sent items
        # to find the newly sent message's internetMessageId.
        sent_resp = await client.get(GRAPH_SENT_ITEMS_URL, headers=headers)
        sent_resp.raise_for_status()

    items = sent_resp.json().get("value", [])
    match = _match_sent_message(items, to=to, subject=subject)

    return {
        "message_id": match.get("internetMessageId") if match else None,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }


def _match_sent_message(items: list[dict], to: str, subject: str) -> dict | None:
    """Find the first sent item matching the recipient + subject."""
    for item in items:
        if item.get("subject") != subject:
            continue
        recipients = [
            r.get("emailAddress", {}).get("address", "").lower()
            for r in item.get("toRecipients", [])
        ]
        if to.lower() in recipients:
            return item
    return items[0] if items else None
