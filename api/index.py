from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.analyzer import analyze_practice
from src.places import search_places
from src.storage import upsert_practices, query_practices, get_practice, update_practice_analysis

app = FastAPI(title="HV Sales Intel", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.post("/api/practices/{place_id}/analyze")
async def analyze(place_id: str, body: AnalyzeRequest | None = None):
    """Analyze a practice: crawl website, fetch reviews, run GPT-4o."""
    force = body.force if body else False

    # Try to get existing practice from Supabase
    existing = get_practice(place_id)

    # If already analyzed and not forcing, return cached
    if existing and existing.get("lead_score") is not None and not force:
        return existing

    # Get practice info for the analyzer
    if existing:
        name = existing["name"]
        website = existing.get("website")
        category = existing.get("category")
    else:
        name = place_id
        website = None
        category = None

    # Run analysis
    analysis = await analyze_practice(place_id, name, website, category)

    # Upsert the analysis fields into Supabase
    updated = update_practice_analysis(place_id, analysis)
    if updated:
        return updated

    # If Supabase not configured, merge analysis into existing data or return standalone
    if existing:
        return {**existing, **analysis}
    return {"place_id": place_id, "name": name, **analysis}
