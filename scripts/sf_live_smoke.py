"""Live smoke test for the Salesforce Apex REST integration.

Creates a Lead, then updates it. Prints both responses. Reads SF_APEX_URL
and SF_API_KEY from .env. Run with: python scripts/sf_live_smoke.py
"""
import asyncio
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from src import salesforce
from src.models import Practice
from src.settings import settings


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


async def main() -> int:
    if not salesforce.is_configured():
        print("FAIL: SF_APEX_URL or SF_API_KEY not set in .env")
        return 1

    print(f"Endpoint: {settings.sf_apex_url}")
    print(f"API key:  {settings.sf_api_key[:6]}...{settings.sf_api_key[-3:]}")
    print()

    practice = Practice(
        place_id="smoke-test",
        name=f"Smoke Test Practice {_ts()}",
        address="1234 Main St",
        city="Houston",
        state="TX",
        phone="+17135551234",
        email="smoketest@example.com",
        website="https://example.com",
        owner_name="Office Manager",
        owner_phone="+17135551234",
        owner_email="manager@example.com",
        lead_score=82,
        urgency_score=70,
        hiring_signal_score=60,
    )

    line1 = f"[{_ts()}] Smoke Test: Initial outreach call from live smoke test."
    print("Step 1: CREATE Lead")
    create_resp = await salesforce.create_lead(practice, line1)
    print(f"  Response: {create_resp}")
    lead_id = create_resp.get("leadId") or create_resp.get("id")
    if not lead_id:
        print("  FAIL: no leadId in response")
        return 1
    print(f"  Lead ID:  {lead_id}")
    print()

    print("Step 2: UPDATE Lead (call_count=2, append note)")
    line2 = f"[{_ts()}] Smoke Test: Second call - left voicemail."
    notes = f"{line1}\n{line2}"
    update_resp = await salesforce.update_lead(lead_id, 2, notes)
    print(f"  Response: {update_resp}")
    if not update_resp.get("success"):
        print("  FAIL: update returned success=false")
        return 1
    print()

    print("Step 3: sync_practice (high-level) on a fresh practice -> CREATE")
    sync_practice = Practice(
        place_id="smoke-test-2",
        name=f"Smoke Test 2 {_ts()}",
        owner_name="Front Desk",
        phone="+17135551234",
        email="smoketest2@example.com",
        lead_score=70,
        urgency_score=50,
        hiring_signal_score=40,
    )
    sync_line = f"[{_ts()}] Smoke Test: sync_practice create branch."
    sync_resp = await salesforce.sync_practice(sync_practice, sync_line)
    print(f"  sync_result: {sync_resp}")
    sync_lead_id = sync_resp.get("sf_lead_id")
    if not sync_lead_id:
        print("  FAIL: sync did not return sf_lead_id")
        return 1
    print()

    print("Step 4: sync_practice (high-level) when lead_id exists -> UPDATE")
    sync_practice.salesforce_lead_id = sync_lead_id
    sync_practice.call_count = 2
    sync_practice.call_notes = f"{sync_line}\n[{_ts()}] Smoke Test: update branch via sync_practice."
    sync_resp2 = await salesforce.sync_practice(sync_practice, "")
    print(f"  sync_result: {sync_resp2}")
    if sync_resp2.get("sf_lead_id") != sync_lead_id:
        print("  FAIL: lead id changed across update branch")
        return 1
    print()

    print("PASS: all four live calls succeeded.")
    print(f"  Created lead 1: {lead_id}")
    print(f"  Created lead 2: {sync_lead_id}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
