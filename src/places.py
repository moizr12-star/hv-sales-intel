import json
from pathlib import Path

import httpx

from src.models import Practice
from src.settings import settings

MOCK_PATH = Path(__file__).parent / "mock_practices.json"

FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.location,places.rating,places.userRatingCount,"
    "places.nationalPhoneNumber,places.websiteUri,"
    "places.types,places.regularOpeningHours"
)


async def search_places(query: str) -> list[Practice]:
    """Search for practices. Uses Google Places API if key is set, else mock data."""
    if settings.google_maps_api_key:
        return await _google_search(query)
    return _mock_search(query)


async def _google_search(query: str) -> list[Practice]:
    """Call Google Places Text Search (New) API."""
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": FIELD_MASK,
        "Content-Type": "application/json",
    }
    body = {"textQuery": query, "maxResultCount": 20}

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=body, headers=headers, timeout=15)
        resp.raise_for_status()

    results = resp.json().get("places", [])
    practices = []
    for p in results:
        loc = p.get("location", {})
        hours_periods = p.get("regularOpeningHours", {}).get("weekdayDescriptions", [])
        practices.append(
            Practice(
                place_id=p["id"],
                name=p.get("displayName", {}).get("text", "Unknown"),
                address=p.get("formattedAddress"),
                city=_extract_city(p.get("formattedAddress", "")),
                state=_extract_state(p.get("formattedAddress", "")),
                phone=p.get("nationalPhoneNumber"),
                website=p.get("websiteUri"),
                rating=p.get("rating"),
                review_count=p.get("userRatingCount", 0),
                category=_classify_types(p.get("types", [])),
                lat=loc.get("latitude"),
                lng=loc.get("longitude"),
                opening_hours="; ".join(hours_periods) if hours_periods else None,
            )
        )
    return practices


def _mock_search(query: str) -> list[Practice]:
    """Filter mock data by keyword matching on name, category, city."""
    with open(MOCK_PATH) as f:
        raw = json.load(f)
    query_lower = query.lower()
    tokens = query_lower.split()
    matches = []
    for item in raw:
        searchable = f"{item['name']} {item['category']} {item['city']}".lower()
        if any(tok in searchable for tok in tokens):
            matches.append(Practice(**item))
    return matches if matches else [Practice(**item) for item in raw[:20]]


def _extract_city(address: str) -> str | None:
    """Best-effort city extraction from formatted address."""
    parts = address.split(",")
    if len(parts) >= 3:
        state_zip = parts[-2].strip()
        city_part = parts[-3].strip() if len(parts) >= 4 else state_zip.rsplit(" ", 1)[0].strip()
        return city_part
    return None


def _extract_state(address: str) -> str | None:
    """Best-effort state extraction from formatted address."""
    parts = address.split(",")
    if len(parts) >= 2:
        state_zip = parts[-1].strip() if "USA" not in parts[-1] else parts[-2].strip()
        tokens = state_zip.split()
        return tokens[0] if tokens else None
    return None


def _classify_types(types: list[str]) -> str:
    """Map Google Places types to our category taxonomy."""
    type_set = set(types)
    if type_set & {"dentist", "dental_clinic"}:
        return "dental"
    if type_set & {"physiotherapist", "chiropractor"}:
        return "chiropractic"
    if type_set & {"hospital", "urgent_care_center", "emergency_room"}:
        return "urgent_care"
    if type_set & {"psychiatrist", "psychologist", "mental_health"}:
        return "mental_health"
    if type_set & {"doctor", "general_practitioner", "primary_care"}:
        return "primary_care"
    return "specialty"
