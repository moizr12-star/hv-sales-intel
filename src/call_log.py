from datetime import datetime, timezone

from openai import AsyncOpenAI

from src import salesforce
from src.models import Practice
from src.settings import settings
from src.storage import get_practice, update_practice_fields


POLISH_SYSTEM_PROMPT = """You are a sales rep's assistant logging a call in a CRM. Given the rep's raw note, produce one clear CRM entry that captures outcome and next steps.

Rules:
- 1-3 sentences, max ~200 characters
- Past tense, third person, professional tone
- Only use facts present in the raw note — do not invent details
- No greeting, no sign-off, no bullet points, no quotation marks

Return only the polished entry, no other text."""


EMPTY_MARKER = "(call logged, no note)"


async def polish_note(raw_note: str) -> str:
    """Polish a rep's raw call note via GPT. Fail-safe with fallbacks."""
    if not raw_note or not raw_note.strip():
        return EMPTY_MARKER

    if not settings.openai_api_key:
        return f"{raw_note.strip()} (unpolished)"

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": POLISH_SYSTEM_PROMPT},
                {"role": "user", "content": raw_note.strip()},
            ],
            temperature=0.3,
            max_tokens=120,
        )
        polished = (response.choices[0].message.content or "").strip()
        if polished:
            return polished
    except Exception:
        pass

    return f"{raw_note.strip()} (unpolished)"


def _format_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


async def append_call_note(
    place_id: str, raw_note: str, user: dict
) -> tuple[dict, str | None]:
    """Polish raw_note, append to practice.call_notes, increment count, sync SF.

    Returns (updated_practice_row, sf_warning_or_none). Raises LookupError if
    the practice does not exist. Local save is always persisted; SF failures
    surface as a warning string rather than an exception.
    """
    existing = get_practice(place_id)
    if not existing:
        raise LookupError(f"Practice not found: {place_id}")

    polished = await polish_note(raw_note)
    rep_name = user.get("name") or user.get("email") or "Unknown"
    line = f"[{_format_timestamp()}] {rep_name}: {polished}"

    prior_notes = existing.get("call_notes")
    new_notes = f"{prior_notes}\n{line}" if prior_notes else line
    new_count = (existing.get("call_count") or 0) + 1

    updates: dict = {
        "call_count": new_count,
        "call_notes": new_notes,
    }

    sync_view = Practice(**{**existing, **updates})

    warning: str | None = None
    try:
        sync_result = await salesforce.sync_practice(sync_view, line)
        if not sync_result.get("skipped"):
            updates["salesforce_lead_id"] = sync_result["sf_lead_id"]
            updates["salesforce_owner_id"] = sync_result["sf_owner_id"]
            updates["salesforce_owner_name"] = sync_result["sf_owner_name"]
            updates["salesforce_synced_at"] = sync_result["synced_at"]
    except Exception as e:
        warning = f"Salesforce sync failed: {e}. Local log saved."

    updated = update_practice_fields(place_id, updates, touched_by=user.get("id"))
    return updated or {**existing, **updates}, warning
