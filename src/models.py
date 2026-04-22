from pydantic import BaseModel


class Practice(BaseModel):
    place_id: str
    name: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    phone: str | None = None
    website: str | None = None
    rating: float | None = None
    review_count: int = 0
    category: str | None = None
    lat: float | None = None
    lng: float | None = None
    opening_hours: str | None = None

    # Phase 2 (AI)
    summary: str | None = None
    pain_points: str | None = None
    sales_angles: str | None = None
    recommended_service: str | None = None
    lead_score: int | None = None
    urgency_score: int | None = None
    hiring_signal_score: int | None = None

    # Phase 3 (CRM)
    status: str = "NEW"
    notes: str | None = None

    # Attribution
    last_touched_by: str | None = None
    last_touched_by_name: str | None = None
    last_touched_at: str | None = None
