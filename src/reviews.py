import httpx

from src.settings import settings

REVIEWS_FIELD_MASK = "reviews.text,reviews.rating,reviews.originalText"


async def fetch_reviews(place_id: str) -> list[dict]:
    """Fetch up to 5 reviews for a place via Google Places API.

    Returns list of dicts with 'text' and 'rating' keys.
    Returns [] if no API key or place_id starts with 'mock_'.
    """
    if not settings.google_maps_api_key:
        return []
    if place_id.startswith("mock_"):
        return []

    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "X-Goog-Api-Key": settings.google_maps_api_key,
        "X-Goog-FieldMask": REVIEWS_FIELD_MASK,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
    except (httpx.HTTPError, Exception):
        return []

    data = resp.json()
    reviews = []
    for r in data.get("reviews", []):
        text = r.get("originalText", {}).get("text") or r.get("text", {}).get("text", "")
        rating = r.get("rating")
        if text:
            reviews.append({"text": text, "rating": rating})
    return reviews


def format_reviews_for_prompt(reviews: list[dict]) -> str:
    """Format reviews into a string for the LLM prompt."""
    if not reviews:
        return "No Google reviews available."
    lines = []
    for i, r in enumerate(reviews, 1):
        stars = f"{r['rating']}/5" if r.get("rating") else "no rating"
        lines.append(f"Review {i} ({stars}): {r['text']}")
    return "\n".join(lines)
