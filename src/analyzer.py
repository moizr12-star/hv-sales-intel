import json
import random

from openai import AsyncOpenAI

from src.crawler import crawl_website
from src.icp_scorer import score_icp
from src.reviews import fetch_reviews, format_reviews_for_prompt
from src.settings import settings

SYSTEM_PROMPT = """You are a healthcare sales intelligence analyst for Health & Virtuals, a healthcare staffing and talent acquisition company.

Your job is to analyze healthcare practices and identify:
1. Staffing-related pain points (understaffed, high turnover, hiring difficulties)
2. Hiring signals (job postings, "we're hiring" pages, open positions for front desk, medical assistants, clinical staff, admin/VA roles)
3. Sales angles for pitching Health & Virtuals' staffing services

Focus specifically on roles Health & Virtuals can fill: front desk staff, medical assistants, clinical staff, administrative assistants, virtual assistants.

Scoring (0-100 each):
- lead_score: Overall composite. Weight hiring signals 50%, urgency 30%, practice size/growth 20%.
- urgency_score: How urgently they need staffing help NOW (negative reviews about wait times, staff shortages, understaffed signals).
- hiring_signal_score: Direct evidence of hiring for roles H&V fills (job postings, careers page, open positions).

Return ONLY valid JSON with this exact structure, no other text:
{
  "summary": "1-2 sentence overview relevant to staffing needs",
  "pain_points": ["point 1", "point 2"],
  "sales_angles": ["angle 1", "angle 2"],
  "lead_score": 0,
  "urgency_score": 0,
  "hiring_signal_score": 0
}

Provide 2-4 pain points and 2-3 sales angles. All scores must be integers 0-100."""


async def analyze_practice(
    place_id: str,
    name: str,
    website: str | None,
    category: str | None,
    city: str | None = None,
    state: str | None = None,
    rating: float | None = None,
    review_count: int = 0,
) -> dict:
    """Analyze a practice. Uses OpenAI if API key is set, otherwise returns mock data."""
    if not settings.openai_api_key:
        return _mock_analysis(
            name=name, category=category, state=state,
            rating=rating, review_count=review_count, website=website,
        )

    # Collect data
    crawl_result = await crawl_website(website or "")
    website_text = crawl_result["text"]
    website_doctor_name = crawl_result["doctor_name"]
    website_doctor_phone = crawl_result["doctor_phone"]
    reviews = await fetch_reviews(
        place_id,
        name=name,
        city=city,
        state=state,
        website=website,
    )
    reviews_text = format_reviews_for_prompt(reviews)

    # Build user prompt
    user_prompt = f"""Analyze this healthcare practice for staffing needs:

Practice: {name}
Category: {category or 'Unknown'}

=== WEBSITE CONTENT ===
{website_text[:15000] if website_text else 'No website available.'}

=== CUSTOMER REVIEWS (GOOGLE + EXTERNAL SOURCES) ===
{reviews_text}
"""

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        result = json.loads(content)
    except Exception:
        return _mock_analysis(
            name=name, category=category, state=state,
            rating=rating, review_count=review_count, website=website,
        )

    # Compute ICP score deterministically from practice attributes + AI
    # urgency/hiring signals. We ignore any lead_score the model returned —
    # the ICP scorer is the single source of truth for that number.
    urgency_score = _clamp(result.get("urgency_score", 0))
    hiring_signal_score = _clamp(result.get("hiring_signal_score", 0))
    icp = score_icp({
        "state": state,
        "category": category,
        "review_count": review_count,
        "rating": rating,
        "website": website,
        "urgency_score": urgency_score,
        "hiring_signal_score": hiring_signal_score,
    })
    return {
        "summary": result.get("summary", ""),
        "pain_points": json.dumps(result.get("pain_points", [])),
        "sales_angles": json.dumps(result.get("sales_angles", [])),
        "lead_score": icp["total"],
        "urgency_score": urgency_score,
        "hiring_signal_score": hiring_signal_score,
        "icp_breakdown": json.dumps(icp["breakdown"]),
        "call_script": None,
        "email_draft": None,
        "email_draft_updated_at": None,
        "website_doctor_name": website_doctor_name,
        "website_doctor_phone": website_doctor_phone,
    }


def _clamp(value: int) -> int:
    """Clamp score to 0-100."""
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


MOCK_PAIN_POINTS = {
    "dental": [
        "Multiple reviews mention long wait times for appointments",
        "Website shows 3 open front desk positions unfilled for 2+ months",
        "Patient complaints about phone responsiveness and scheduling delays",
        "Small team handling high patient volume with no admin support",
    ],
    "chiropractic": [
        "Reviews cite difficulty reaching office by phone",
        "No online scheduling available — all booking is phone-based",
        "Single receptionist managing a multi-provider practice",
        "Patients report long hold times and missed callbacks",
    ],
    "urgent_care": [
        "Frequent reviews about excessive wait times (2+ hours)",
        "Website careers page lists multiple MA and front desk openings",
        "Staff turnover evident from reviews mentioning 'new staff every visit'",
        "Understaffed night and weekend shifts based on patient feedback",
    ],
    "mental_health": [
        "Weeks-long wait for new patient appointments",
        "Reviews mention difficulty with billing and insurance follow-up",
        "No dedicated admin staff — providers handling scheduling themselves",
        "Patient intake process described as slow and disorganized",
    ],
    "primary_care": [
        "Reviews frequently mention long wait times in lobby",
        "Website shows hiring for medical assistants and front desk",
        "Patients report difficulty getting referral paperwork processed",
        "Phone system overwhelmed — multiple reviews about busy signals",
    ],
    "specialty": [
        "Complex referral and prior-auth process causing patient frustration",
        "Reviews mention staff seeming overwhelmed and rushed",
        "Limited appointment availability suggesting capacity constraints",
        "Administrative delays in test results and follow-up communication",
    ],
}

MOCK_SALES_ANGLES = {
    "dental": [
        "Pitch virtual front desk staff to handle scheduling overflow",
        "Propose trained dental admin VAs for insurance verification",
        "Offer temp-to-perm medical receptionists to fill open positions",
    ],
    "chiropractic": [
        "Propose virtual receptionist to handle call volume and scheduling",
        "Pitch admin VA for patient intake and insurance processing",
        "Offer bilingual front desk staff for diverse patient base",
    ],
    "urgent_care": [
        "Pitch staffing packages for night/weekend coverage gaps",
        "Propose trained medical assistants for triage support",
        "Offer front desk temp staffing to reduce patient wait times",
    ],
    "mental_health": [
        "Pitch dedicated intake coordinator to reduce new patient wait",
        "Propose billing specialist VA for insurance and claims management",
        "Offer virtual admin assistant so providers can focus on patients",
    ],
    "primary_care": [
        "Pitch medical assistants to support providers and reduce burnout",
        "Propose virtual front desk staff for phone and scheduling overflow",
        "Offer admin VAs for referral processing and follow-up coordination",
    ],
    "specialty": [
        "Pitch prior-authorization specialist to streamline referral process",
        "Propose admin staff for test result follow-up and patient communication",
        "Offer medical assistants trained in specialty clinic workflows",
    ],
}


def _mock_analysis(
    name: str,
    category: str | None,
    state: str | None = None,
    rating: float | None = None,
    review_count: int = 0,
    website: str | None = None,
) -> dict:
    """Return realistic mock analysis data with ICP-derived lead_score."""
    cat = category or "primary_care"
    pain_points = MOCK_PAIN_POINTS.get(cat, MOCK_PAIN_POINTS["primary_care"])
    sales_angles = MOCK_SALES_ANGLES.get(cat, MOCK_SALES_ANGLES["primary_care"])

    selected_pains = random.sample(pain_points, min(3, len(pain_points)))
    selected_angles = random.sample(sales_angles, min(2, len(sales_angles)))

    hiring = random.randint(25, 95)
    urgency = random.randint(20, 80)

    icp = score_icp({
        "state": state,
        "category": category,
        "review_count": review_count,
        "rating": rating,
        "website": website,
        "urgency_score": urgency,
        "hiring_signal_score": hiring,
    })

    return {
        "summary": f"{name} shows signs of staffing challenges typical of {cat.replace('_', ' ')} practices. Review analysis and website signals suggest opportunities for Health & Virtuals staffing services.",
        "pain_points": json.dumps(selected_pains),
        "sales_angles": json.dumps(selected_angles),
        "lead_score": icp["total"],
        "urgency_score": urgency,
        "hiring_signal_score": hiring,
        "icp_breakdown": json.dumps(icp["breakdown"]),
        "call_script": None,
        "email_draft": None,
        "email_draft_updated_at": None,
        "website_doctor_name": None,
        "website_doctor_phone": None,
    }
