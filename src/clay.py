import httpx

from src.models import Practice
from src.settings import settings


def _is_configured() -> bool:
    """Webhook URL is required. Auth token (sent as x-clay-webhook-auth)
    is optional — some Clay sources don't require one."""
    return bool(settings.clay_table_webhook_url)


async def trigger_enrichment(practice: Practice) -> dict:
    """POST practice data to Clay's HTTP API source.

    Returns {'status': 'pending'} on success or
    {'skipped': True, 'reason': 'clay_not_configured'} when webhook URL is empty.
    Raises httpx errors on non-2xx response; caller decides how to surface.
    """
    if not _is_configured():
        return {"skipped": True, "reason": "clay_not_configured"}

    payload = {
        "place_id": practice.place_id,
        "practice_name": practice.name,
        "website": practice.website,
        "city": practice.city,
        "state": practice.state,
        "phone": practice.phone,
    }
    headers = {"Content-Type": "application/json"}
    if settings.clay_table_api_key:
        headers["x-clay-webhook-auth"] = settings.clay_table_api_key

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            settings.clay_table_webhook_url, headers=headers, json=payload
        )
        resp.raise_for_status()

    return {"status": "pending"}
