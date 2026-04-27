import json

from openai import AsyncOpenAI

from src.settings import settings

SYSTEM_PROMPT = """You are a cold call script writer for Health & Virtuals, a healthcare staffing and talent acquisition company.

Given information about a healthcare practice (name, category, location, lead doctor, owner, analysis summary, pain points, sales angles, review excerpts), generate a personalized cold call playbook tailored to THIS specific practice.

Return ONLY valid JSON with this exact structure:
{
  "sections": [
    {"title": "Opening", "icon": "phone", "content": "..."},
    {"title": "Discovery Questions", "icon": "search", "content": "..."},
    {"title": "Pitch", "icon": "target", "content": "..."},
    {"title": "Objection Handling", "icon": "shield", "content": "..."},
    {"title": "Closing", "icon": "check", "content": "..."}
  ]
}

Personalization requirements:
- Opening: If a lead doctor name is provided, ask for them by name ("Hi, may I speak with Dr. Smith?"). Otherwise greet the practice. Reference the city if provided.
- Discovery Questions: Reference 1-2 specific items from the provided pain_points by name (not generic). 3-4 numbered questions total.
- Pitch: If review_excerpts are provided, quote ONE excerpt verbatim with leading attribution ("One of your patient reviews mentioned, '...'") and tie it to a Health & Virtuals staffing solution. Mention Health & Virtuals by name.
- Objection Handling: Cover "We already have a recruiter", "We can't afford it", "We're not hiring right now", and one objection specific to this category.
- Closing: Reference the city when present ("we've placed staff at multiple [city]-area clinics"). Suggest a 15-minute meeting and a free staffing assessment.

Keep each section 3-6 sentences. Be conversational, not robotic. Use the rep's perspective ("I", "we at Health & Virtuals")."""


async def generate_script(
    name: str,
    category: str | None,
    summary: str | None,
    pain_points: str | None,
    sales_angles: str | None,
    *,
    city: str | None = None,
    state: str | None = None,
    rating: float | None = None,
    review_count: int | None = None,
    website_doctor_name: str | None = None,
    owner_name: str | None = None,
    owner_title: str | None = None,
    review_excerpts: list[str] | None = None,
) -> dict:
    """Generate a cold call playbook personalized to the practice."""
    if not settings.openai_api_key:
        return _mock_script(
            name=name,
            category=category,
            website_doctor_name=website_doctor_name,
            city=city,
        )

    excerpts = review_excerpts or []
    location = (
        f"{city}, {state}" if (city and state) else (city or state or "Unknown")
    )
    excerpts_block = (
        "\n".join(f'- "{ex}"' for ex in excerpts) if excerpts else "(none available)"
    )
    user_prompt = f"""Generate a personalized cold call playbook for this practice:

Practice: {name}
Category: {category or 'Healthcare'}
Location: {location}
Rating: {rating if rating is not None else 'unknown'} ({review_count or 0} reviews)
Lead Doctor: {website_doctor_name or 'Unknown'}
Owner Contact: {owner_name or 'Unknown'} ({owner_title or 'no title'})

Analysis Summary: {summary or 'No analysis available'}
Pain Points: {pain_points or '[]'}
Sales Angles: {sales_angles or '[]'}

Verbatim Patient Review Excerpts:
{excerpts_block}
"""

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        result = json.loads(content)
        if "sections" in result and len(result["sections"]) == 5:
            return result
    except Exception:
        pass

    return _mock_script(
        name=name,
        category=category,
        website_doctor_name=website_doctor_name,
        city=city,
    )


def _mock_script(
    name: str,
    category: str | None,
    website_doctor_name: str | None = None,
    city: str | None = None,
) -> dict:
    """Return a category-appropriate mock playbook with optional personalization."""
    cat_label = (category or "healthcare").replace("_", " ")
    doctor_greeting = (
        f"Hi, may I speak with {website_doctor_name}?"
        if website_doctor_name
        else f"Hi, this is [Your Name] calling from Health & Virtuals about {name}."
    )
    city_phrase = f" in the {city} area" if city else ""

    return {
        "sections": [
            {
                "title": "Opening",
                "icon": "phone",
                "content": (
                    f"{doctor_greeting} I'm reaching out because Health & Virtuals "
                    f"helps {cat_label} practices{city_phrase} with staffing solutions. "
                    "Do you have a quick moment?"
                ),
            },
            {
                "title": "Discovery Questions",
                "icon": "search",
                "content": (
                    "1. How are you currently handling front desk coverage when staff call out?\n"
                    "2. Are you finding it challenging to recruit and retain qualified staff in this market?\n"
                    "3. How much time does your team spend on admin tasks versus patient coordination?\n"
                    "4. If you could add one more person to your team tomorrow, what role would make the biggest impact?"
                ),
            },
            {
                "title": "Pitch",
                "icon": "target",
                "content": (
                    f"At Health & Virtuals, we provide pre-vetted front desk staff, medical "
                    f"assistants, and administrative support specifically for practices like "
                    f"{name}. We handle recruiting, screening, and onboarding so you can focus "
                    "on patient care."
                ),
            },
            {
                "title": "Objection Handling",
                "icon": "shield",
                "content": (
                    'Objection: "We already have a recruiter."\n'
                    "Response: We complement existing recruiters with healthcare specialists.\n\n"
                    'Objection: "We can\'t afford it right now."\n'
                    "Response: Many of our clients save money via temp-to-perm placements that "
                    "prevent costly bad hires.\n\n"
                    'Objection: "We\'re not hiring right now."\n'
                    "Response: Many practices work with us proactively so they have qualified "
                    "candidates ready when a position opens."
                ),
            },
            {
                "title": "Closing",
                "icon": "check",
                "content": (
                    f"I'd love to set up a quick 15-minute call to learn more about {name}"
                    f"{city_phrase} and share how we've helped similar practices. Would Tuesday "
                    "or Wednesday work for a brief chat?"
                ),
            },
        ]
    }
