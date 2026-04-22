import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.analyzer import analyze_practice
from src.models import Practice
from src.places import get_place, search_places
from src.scriptgen import generate_script
from src.storage import (
    upsert_practices,
    query_practices,
    get_practice,
    update_practice_analysis,
    update_practice_fields,
)

app = FastAPI(title="HV Sales Intel", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Status ordering for auto-transitions
STATUS_ORDER = [
    "NEW", "RESEARCHED", "SCRIPT READY", "CONTACTED",
    "FOLLOW UP", "MEETING SET", "PROPOSAL", "CLOSED WON", "CLOSED LOST",
]


def _should_auto_advance(current: str, target: str) -> bool:
    """Return True if target is ahead of current in the pipeline."""
    try:
        return STATUS_ORDER.index(target) > STATUS_ORDER.index(current)
    except ValueError:
        return False


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/practices")
def list_practices(
    city: str | None = Query(None),
    category: str | None = Query(None),
    min_rating: float | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """List practices from Supabase with optional filters."""
    rows = query_practices(city=city, category=category, min_rating=min_rating, limit=limit)
    return {"practices": rows, "count": len(rows)}


class SearchRequest(BaseModel):
    query: str
    refresh: bool = False


@app.post("/api/practices/search")
async def search(body: SearchRequest):
    """Search via Google Places (or mock). Upserts results into Supabase."""
    practices = await search_places(body.query)
    upserted = upsert_practices(practices)
    return {
        "practices": [p.model_dump() for p in practices],
        "count": len(practices),
        "upserted": upserted,
    }


@app.get("/api/practices/{place_id}")
def get_single(place_id: str):
    """Get a single practice by place_id."""
    row = get_practice(place_id)
    if not row:
        raise HTTPException(status_code=404, detail="Practice not found")
    return row


class AnalyzeRequest(BaseModel):
    force: bool = False
    rescan: bool = False


@app.post("/api/practices/{place_id}/analyze")
async def analyze(place_id: str, body: AnalyzeRequest | None = None):
    """Analyze a practice: crawl website, fetch reviews, run GPT-4o."""
    force = body.force if body else False
    rescan = body.rescan if body else False

    existing = get_practice(place_id)

    if existing and existing.get("lead_score") is not None and not force and not rescan:
        return existing

    current_record = existing
    if existing and rescan:
        refreshed = await get_place(place_id, fallback=Practice(**existing))
        if refreshed:
            upsert_practices([refreshed])
            current_record = get_practice(place_id) or refreshed.model_dump()

    if current_record:
        name = current_record["name"]
        website = current_record.get("website")
        category = current_record.get("category")
        city = current_record.get("city")
        state = current_record.get("state")
    else:
        name = place_id
        website = None
        category = None
        city = None
        state = None

    analysis = await analyze_practice(place_id, name, website, category, city=city, state=state)

    # Auto-advance status to RESEARCHED
    if current_record:
        current_status = current_record.get("status", "NEW")
        if _should_auto_advance(current_status, "RESEARCHED"):
            analysis["status"] = "RESEARCHED"

    updated = update_practice_analysis(place_id, analysis)
    if updated:
        return updated

    if current_record:
        return {**current_record, **analysis}
    return {"place_id": place_id, "name": name, **analysis}


@app.post("/api/practices/{place_id}/rescan")
async def rescan_practice(place_id: str):
    """Refresh a stored practice from the source of truth before analysis."""
    existing = get_practice(place_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Practice not found")

    refreshed = await get_place(place_id, fallback=Practice(**existing))
    if not refreshed:
        return existing

    upsert_practices([refreshed])
    return get_practice(place_id) or refreshed.model_dump()


@app.get("/api/practices/{place_id}/script")
async def get_script(place_id: str):
    """Get or generate the call script for a practice."""
    practice = get_practice(place_id)
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")

    # Return cached script if it exists
    if practice.get("call_script"):
        return json.loads(practice["call_script"])

    # Generate new script
    script = await generate_script(
        name=practice["name"],
        category=practice.get("category"),
        summary=practice.get("summary"),
        pain_points=practice.get("pain_points"),
        sales_angles=practice.get("sales_angles"),
    )

    # Store script
    update_practice_fields(place_id, {"call_script": json.dumps(script)})

    # Auto-advance status to SCRIPT READY
    current_status = practice.get("status", "NEW")
    if _should_auto_advance(current_status, "SCRIPT READY"):
        update_practice_fields(place_id, {"status": "SCRIPT READY"})

    return script


@app.post("/api/practices/{place_id}/script")
async def regenerate_script_endpoint(place_id: str):
    """Force regenerate the call script."""
    practice = get_practice(place_id)
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")

    script = await generate_script(
        name=practice["name"],
        category=practice.get("category"),
        summary=practice.get("summary"),
        pain_points=practice.get("pain_points"),
        sales_angles=practice.get("sales_angles"),
    )

    update_practice_fields(place_id, {"call_script": json.dumps(script)})

    return script


class PatchPracticeRequest(BaseModel):
    status: str | None = None
    notes: str | None = None


@app.patch("/api/practices/{place_id}")
def patch_practice(place_id: str, body: PatchPracticeRequest):
    """Update status and/or notes for a practice."""
    fields: dict = {}
    if body.status is not None:
        if body.status not in STATUS_ORDER:
            raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
        fields["status"] = body.status
    if body.notes is not None:
        fields["notes"] = body.notes
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = update_practice_fields(place_id, fields)
    if not updated:
        raise HTTPException(status_code=404, detail="Practice not found")
    return updated
