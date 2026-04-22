from datetime import datetime, timezone

from supabase import create_client

from src.models import Practice
from src.settings import settings

PROFILE_JOIN_SELECT = "*, last_touched_by_profile:profiles!last_touched_by(name)"


def _get_client():
    """Return Supabase client or None if unconfigured."""
    if settings.supabase_url and settings.supabase_key:
        return create_client(settings.supabase_url, settings.supabase_key)
    return None


def _with_attribution(fields: dict, touched_by: str | None) -> dict:
    if not touched_by:
        return fields
    return {
        **fields,
        "last_touched_by": touched_by,
        "last_touched_at": datetime.now(timezone.utc).isoformat(),
    }


def _flatten_attribution(row: dict) -> dict:
    """Flatten the joined profile into last_touched_by_name."""
    if not row:
        return row
    joined = row.pop("last_touched_by_profile", None)
    row["last_touched_by_name"] = joined.get("name") if joined else None
    return row


def upsert_practices(
    practices: list[Practice],
    touched_by: str | None = None,
) -> int:
    """Upsert practices. Returns count. Stamps attribution when touched_by set."""
    client = _get_client()
    if not client or not practices:
        return 0
    rows = []
    for p in practices:
        row = p.model_dump(exclude={"last_touched_by_name"})
        rows.append(_with_attribution(row, touched_by))
    result = client.table("practices").upsert(rows, on_conflict="place_id").execute()
    return len(result.data) if result.data else 0


def query_practices(
    city: str | None = None,
    category: str | None = None,
    min_rating: float | None = None,
    limit: int = 50,
) -> list[dict]:
    """List practices with profile join. Returns [] if unconfigured."""
    client = _get_client()
    if not client:
        return []
    q = client.table("practices").select(PROFILE_JOIN_SELECT)
    if city:
        q = q.ilike("city", f"%{city}%")
    if category:
        q = q.eq("category", category)
    if min_rating:
        q = q.gte("rating", min_rating)
    q = q.order("rating", desc=True).limit(limit)
    result = q.execute()
    return [_flatten_attribution(r) for r in (result.data or [])]


def get_practice(place_id: str) -> dict | None:
    """Get single practice with profile join. Returns None if not found."""
    client = _get_client()
    if not client:
        return None
    try:
        result = (
            client.table("practices").select(PROFILE_JOIN_SELECT)
            .eq("place_id", place_id).maybe_single().execute()
        )
    except Exception:
        return None
    return _flatten_attribution(result.data) if result and result.data else None


def update_practice_analysis(
    place_id: str,
    analysis: dict,
    touched_by: str | None = None,
) -> dict | None:
    """Update Phase 2 analysis fields. Stamps attribution when touched_by set."""
    client = _get_client()
    if not client:
        return None
    result = (
        client.table("practices")
        .update(_with_attribution(analysis, touched_by))
        .eq("place_id", place_id)
        .execute()
    )
    return result.data[0] if result.data else None


def update_practice_fields(
    place_id: str,
    fields: dict,
    touched_by: str | None = None,
) -> dict | None:
    """Update arbitrary fields. Stamps attribution when touched_by set."""
    client = _get_client()
    if not client:
        return None
    result = (
        client.table("practices")
        .update(_with_attribution(fields, touched_by))
        .eq("place_id", place_id)
        .execute()
    )
    return result.data[0] if result.data else None
