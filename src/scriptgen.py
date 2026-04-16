import json

from openai import AsyncOpenAI

from src.settings import settings

SYSTEM_PROMPT = """You are a cold call script writer for Health & Virtuals, a healthcare staffing and talent acquisition company.

Given information about a healthcare practice (name, category, analysis summary, pain points, sales angles), generate a structured cold call playbook.

Return ONLY valid JSON with this exact structure:
{
  "sections": [
    {
      "title": "Opening",
      "icon": "phone",
      "content": "The opening script text..."
    },
    {
      "title": "Discovery Questions",
      "icon": "search",
      "content": "3-4 numbered questions..."
    },
    {
      "title": "Pitch",
      "icon": "target",
      "content": "The tailored pitch..."
    },
    {
      "title": "Objection Handling",
      "icon": "shield",
      "content": "3-4 objections with rebuttals, formatted as 'Objection: ... Response: ...'"
    },
    {
      "title": "Closing",
      "icon": "check",
      "content": "The closing script with next steps..."
    }
  ]
}

Guidelines:
- Opening: Reference the practice by name, mention something specific about them (category, size, detail from analysis)
- Discovery Questions: Ask about staffing challenges, hiring timeline, current workflow pain points
- Pitch: Directly address their specific pain points. Mention Health & Virtuals by name. Focus on staffing solutions they need.
- Objection Handling: Include "We already have a recruiter", "We can't afford it", "We're not hiring right now", and one specific to their situation
- Closing: Suggest a 15-minute meeting, offer a free staffing assessment, provide follow-up framing

Keep each section 3-6 sentences. Be conversational, not robotic. Use the rep's perspective ("I", "we at Health & Virtuals")."""


async def generate_script(
    name: str,
    category: str | None,
    summary: str | None,
    pain_points: str | None,
    sales_angles: str | None,
) -> dict:
    """Generate a cold call playbook. Uses GPT if API key set, otherwise mock."""
    if not settings.openai_api_key:
        return _mock_script(name, category)

    user_prompt = f"""Generate a cold call playbook for this practice:

Practice: {name}
Category: {category or 'Healthcare'}
Analysis Summary: {summary or 'No analysis available'}
Pain Points: {pain_points or '[]'}
Sales Angles: {sales_angles or '[]'}
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

    return _mock_script(name, category)


def _mock_script(name: str, category: str | None) -> dict:
    """Return a category-appropriate mock playbook."""
    return {
        "sections": [
            {
                "title": "Opening",
                "icon": "phone",
                "content": f"Hi, this is [Your Name] calling from Health & Virtuals. I'm reaching out because we specialize in staffing solutions for {(category or 'healthcare').replace('_', ' ')} practices, and I noticed {name} may benefit from some of our services. Do you have a quick moment?",
            },
            {
                "title": "Discovery Questions",
                "icon": "search",
                "content": "1. How are you currently handling front desk coverage when staff call out or during peak hours?\n2. Are you finding it challenging to recruit and retain qualified staff in this market?\n3. How much time does your team spend on scheduling and administrative tasks versus patient coordination?\n4. If you could add one more person to your team tomorrow, what role would make the biggest impact?",
            },
            {
                "title": "Pitch",
                "icon": "target",
                "content": f"At Health & Virtuals, we provide pre-vetted front desk staff, medical assistants, and administrative support specifically for practices like {name}. We handle recruiting, screening, and onboarding so you can focus on patient care. Our placements typically reduce scheduling delays and free up significant admin time for your existing team.",
            },
            {
                "title": "Objection Handling",
                "icon": "shield",
                "content": "Objection: \"We already have a recruiter.\"\nResponse: We complement existing recruiters. We focus specifically on healthcare staffing with candidates who are pre-trained in clinical workflows, so there's no overlap.\n\nObjection: \"We can't afford it right now.\"\nResponse: Many of our clients actually save money because our temp-to-perm model eliminates costly bad hires and reduces overtime costs.\n\nObjection: \"We're not hiring right now.\"\nResponse: That's perfectly fine. Many practices work with us proactively so when a position does open up, they have qualified candidates ready within 48 hours instead of spending weeks searching.\n\nObjection: \"We've had bad experiences with staffing agencies.\"\nResponse: We're not a general staffing agency — we only place healthcare professionals, and every candidate goes through a specialty-specific skills assessment.",
            },
            {
                "title": "Closing",
                "icon": "check",
                "content": f"I'd love to set up a quick 15-minute call to learn more about {name} and share how we've helped similar practices in your area. We also offer a free staffing assessment where we review your current team structure and identify areas where we could add value. Would Tuesday or Wednesday work better for a brief chat?",
            },
        ]
    }
