from supabase import create_client

from src.models import Practice
from src.settings import settings


def _get_client():
    """Return Supabase client or None if unconfigured."""
    if settings.supabase_url and settings.supabase_key:
        return create_client(settings.supabase_url, settings.supabase_key)
    return None


def upsert_practices(practices: list[Practice]) -> int:
    """Upsert practices into Supabase. Returns count upserted. No-ops if unconfigured."""
    client = _get_client()
    if not client or not practices:
        return 0
    rows = [p.model_dump() for p in practices]
    result = client.table("practices").upsert(rows, on_conflict="place_id").execute()
    return len(result.data) if result.data else 0


def query_practices(
    city: str | None = None,
    category: str | None = None,
    min_rating: float | None = None,
    limit: int = 50,
) -> list[dict]:
    """Query practices from Supabase with optional filters. Returns [] if unconfigured."""
    client = _get_client()
    if not client:
        return []
    q = client.table("practices").select("*")
    if city:
        q = q.ilike("city", f"%{city}%")
    if category:
        q = q.eq("category", category)
    if min_rating:
        q = q.gte("rating", min_rating)
    q = q.order("rating", desc=True).limit(limit)
    result = q.execute()
    return result.data if result.data else []


def get_practice(place_id: str) -> dict | None:
    """Get a single practice by place_id. Returns None if unconfigured or not found."""
    client = _get_client()
    if not client:
        return None
    result = client.table("practices").select("*").eq("place_id", place_id).single().execute()
    return result.data


def update_practice_analysis(place_id: str, analysis: dict) -> dict | None:
    """Update Phase 2 analysis fields for a practice. Returns updated row or None."""
    client = _get_client()
    if not client:
        return None
    result = (
        client.table("practices")
        .update(analysis)
        .eq("place_id", place_id)
        .execute()
    )
    return result.data[0] if result.data else None


def update_practice_fields(place_id: str, fields: dict) -> dict | None:
    """Update arbitrary fields on a practice. Returns updated row or None."""
    client = _get_client()
    if not client:
        return None
    result = (
        client.table("practices")
        .update(fields)
        .eq("place_id", place_id)
        .execute()
    )
    return result.data[0] if result.data else None
