from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.places import search_places
from src.storage import upsert_practices, query_practices, get_practice

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
