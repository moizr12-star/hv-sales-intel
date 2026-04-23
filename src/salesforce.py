from datetime import datetime, timezone

import httpx

from src import sf_auth
from src.models import Practice
from src.settings import settings


def _rating_from_score(score: int | None) -> str:
    if score is None:
        return "Warm"
    if score >= 75:
        return "Hot"
    if score >= 50:
        return "Warm"
    return "Cold"


def _build_lead_payload(practice: Practice, call_note_line: str) -> dict:
    """Build the POST body for creating a Lead from a Practice."""
    payload: dict = {
        "Company": practice.name,
        "LastName": "Office",
        "Industry": "Healthcare",
        "LeadSource": "HV Sales Intel",
        "Status": "Working - Contacted",
        "Rating": _rating_from_score(practice.lead_score),
        "Call_Count__c": 1,
        "Call_Notes__c": call_note_line,
    }
    if practice.phone:
        payload["Phone"] = practice.phone
    if practice.email:
        payload["Email"] = practice.email
    if practice.website:
        payload["Website"] = practice.website
    if practice.address:
        payload["Street"] = practice.address
    if practice.city:
        payload["City"] = practice.city

    scores = [practice.lead_score, practice.urgency_score, practice.hiring_signal_score]
    if any(s is not None for s in scores):
        payload["Description"] = (
            f"Lead Score: {practice.lead_score or 0} | "
            f"Urgency: {practice.urgency_score or 0} | "
            f"Hiring Signal: {practice.hiring_signal_score or 0}"
        )
    return payload


async def create_lead(practice: Practice, call_note_line: str) -> dict:
    """POST to SF sobjects/Lead/. Returns the SF response body."""
    token, instance_url = await sf_auth.get_access_token()
    url = f"{instance_url}/services/data/{settings.sf_api_version}/sobjects/Lead/"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = _build_lead_payload(practice, call_note_line)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
    return resp.json()


async def update_lead(sf_lead_id: str, call_count: int, call_notes: str) -> None:
    """PATCH call log fields on an existing Lead. 204 on success."""
    token, instance_url = await sf_auth.get_access_token()
    url = f"{instance_url}/services/data/{settings.sf_api_version}/sobjects/Lead/{sf_lead_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {"Call_Count__c": call_count, "Call_Notes__c": call_notes}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.patch(url, headers=headers, json=body)
        resp.raise_for_status()


async def get_owner(sf_lead_id: str) -> tuple[str, str]:
    """GET Id, OwnerId, Owner.Name for a Lead."""
    token, instance_url = await sf_auth.get_access_token()
    url = (
        f"{instance_url}/services/data/{settings.sf_api_version}"
        f"/sobjects/Lead/{sf_lead_id}"
    )
    params = {"fields": "Id,OwnerId,Owner.Name"}
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    data = resp.json()
    return data["OwnerId"], data.get("Owner", {}).get("Name", "")


async def sync_practice(practice: Practice, polished_line: str) -> dict:
    """Create or update the SF Lead for this practice.

    Returns dict with SF fields on success, or {'skipped': True, 'reason': ...}
    when SF is not configured. Raises on network/API failures so the caller
    can decide how to surface them.
    """
    if not sf_auth.is_configured():
        return {"skipped": True, "reason": "sf_not_configured"}

    now_iso = datetime.now(timezone.utc).isoformat()

    if practice.salesforce_lead_id:
        await update_lead(
            practice.salesforce_lead_id,
            practice.call_count,
            practice.call_notes or "",
        )
        owner_id, owner_name = await get_owner(practice.salesforce_lead_id)
        return {
            "sf_lead_id": practice.salesforce_lead_id,
            "sf_owner_id": owner_id,
            "sf_owner_name": owner_name,
            "synced_at": now_iso,
        }

    created = await create_lead(practice, polished_line)
    sf_lead_id = created["id"]
    owner_id, owner_name = await get_owner(sf_lead_id)
    return {
        "sf_lead_id": sf_lead_id,
        "sf_owner_id": owner_id,
        "sf_owner_name": owner_name,
        "synced_at": now_iso,
    }
