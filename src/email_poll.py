import httpx
from bs4 import BeautifulSoup

from src.ms_auth import get_access_token


GRAPH_MESSAGES_URL = "https://graph.microsoft.com/v1.0/me/messages"
SELECT_FIELDS = (
    "id,subject,body,from,toRecipients,sentDateTime,"
    "receivedDateTime,internetMessageId,internetMessageHeaders"
)


async def poll_replies(
    practice_email: str,
    outbound_message_ids: list[str],
    since_iso: str,
) -> list[dict]:
    """Fetch inbound messages from `practice_email` since `since_iso`.

    Returns a list of dicts ready to insert into `email_messages`:
    { message_id, in_reply_to, subject, body, sent_at }.

    Threading: if any outbound message_id appears in the message's
    In-Reply-To or References header, link it. Otherwise envelope-match
    on sender address.
    """
    token = await get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    addr = practice_email.replace("'", "''")
    filter_expr = (
        f"receivedDateTime ge {since_iso} "
        f"and from/emailAddress/address eq '{addr}'"
    )
    params = {
        "$filter": filter_expr,
        "$select": SELECT_FIELDS,
        "$orderby": "receivedDateTime desc",
        "$top": "50",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(GRAPH_MESSAGES_URL, headers=headers, params=params)
        resp.raise_for_status()

    outbound_set = set(outbound_message_ids)
    results: list[dict] = []
    for msg in resp.json().get("value", []):
        in_reply_to = _extract_threading_parent(msg, outbound_set)
        body_text = _extract_plain_body(msg.get("body", {}))
        results.append({
            "message_id": msg.get("internetMessageId"),
            "in_reply_to": in_reply_to,
            "subject": msg.get("subject"),
            "body": body_text,
            "sent_at": msg.get("receivedDateTime") or msg.get("sentDateTime"),
        })
    return results


def _extract_threading_parent(msg: dict, outbound_set: set[str]) -> str | None:
    """Return the outbound message_id this reply threads to, if any."""
    for header in msg.get("internetMessageHeaders", []) or []:
        name = (header.get("name") or "").lower()
        value = header.get("value") or ""
        if name in ("in-reply-to", "references"):
            for candidate in value.split():
                candidate = candidate.strip()
                if candidate in outbound_set:
                    return candidate
    return None


def _extract_plain_body(body: dict) -> str:
    content = body.get("content") or ""
    content_type = (body.get("contentType") or "").lower()
    if content_type == "html":
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)
    return content
