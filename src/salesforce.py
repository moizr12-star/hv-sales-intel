from datetime import datetime, timezone

import httpx

from src.models import Practice
from src.settings import settings


def is_configured() -> bool:
    """True when both Apex endpoint URL and API key are set."""
    return bool(settings.sf_apex_url and settings.sf_api_key)


def _scores_description(practice: Practice) -> str | None:
    scores = (practice.lead_score, practice.urgency_score, practice.hiring_signal_score)
    if all(s is None for s in scores):
        return None
    return (
        f"Lead Score: {practice.lead_score or 0} | "
        f"Urgency: {practice.urgency_score or 0} | "
        f"Hiring Signal: {practice.hiring_signal_score or 0}"
    )


def _build_create_payload(practice: Practice, call_note_line: str) -> dict:
    """Build the POST body for the Apex REST Lead create endpoint.

    Includes every field the Apex handler expects, including the required
    custom field Lead_Type__c. Omits None values so Salesforce keeps its
    own defaults rather than receiving "None" strings.
    """
    payload: dict = {
        "Company": practice.name,
        "OwnerName": practice.owner_name or "",
        "OwnerPhone": practice.owner_phone or practice.phone or "",
        "OwnerEmail": practice.owner_email or "",
        "Email": practice.email or "",
        "Website": practice.website or "",
        "Street": practice.address or "",
        "City": practice.city or "",
        "State": practice.state or "",
        "PostalCode": "",
        "Country": "USA",
        "Industry": "Healthcare",
        "LeadSource": "HV Sales Intel",
        "Status": "Working - Contacted",
        "Lead_Type__c": "Outbound",
        "Description": _scores_description(practice) or "",
        "Call_Count__c": str(practice.call_count or 1),
        "Call_Notes__c": call_note_line,
    }
    return payload


def _build_update_payload(sf_lead_id: str, call_count: int, call_notes: str) -> dict:
    return {
        "Id": sf_lead_id,
        "Status": "Working - Contacted",
        "Lead_Type__c": "Outbound",
        "Call_Count__c": str(call_count),
        "Call_Notes__c": call_notes,
    }


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "x-api-key": settings.sf_api_key,
    }


async def create_lead(practice: Practice, call_note_line: str) -> dict:
    """POST a new Lead to the Apex endpoint. Returns the parsed JSON response."""
    body = _build_create_payload(practice, call_note_line)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(settings.sf_apex_url, headers=_headers(), json=body)
        resp.raise_for_status()
    return resp.json()


async def update_lead(sf_lead_id: str, call_count: int, call_notes: str) -> dict:
    """PUT updates to an existing Lead. Returns the parsed JSON response."""
    body = _build_update_payload(sf_lead_id, call_count, call_notes)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.put(settings.sf_apex_url, headers=_headers(), json=body)
        resp.raise_for_status()
    return resp.json()


async def sync_practice(practice: Practice, polished_line: str) -> dict:
    """Create or update the SF Lead for this practice via the Apex endpoint.

    Returns dict with sf_lead_id + synced_at on success, or
    {'skipped': True, 'reason': ...} when SF is not configured. Raises on
    network/API failures so the caller can surface a warning.
    """
    if not is_configured():
        return {"skipped": True, "reason": "sf_not_configured"}

    now_iso = datetime.now(timezone.utc).isoformat()

    if practice.salesforce_lead_id:
        await update_lead(
            practice.salesforce_lead_id,
            practice.call_count,
            practice.call_notes or "",
        )
        return {
            "sf_lead_id": practice.salesforce_lead_id,
            "sf_owner_name": practice.owner_name or "",
            "synced_at": now_iso,
        }

    created = await create_lead(practice, polished_line)
    sf_lead_id = created.get("leadId") or created.get("id")
    if not sf_lead_id:
        raise RuntimeError(f"Salesforce response missing leadId: {created}")
    return {
        "sf_lead_id": sf_lead_id,
        "sf_owner_name": practice.owner_name or "",
        "synced_at": now_iso,
    }
