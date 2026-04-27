from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.scriptgen import generate_script


@pytest.mark.asyncio
async def test_generate_script_uses_doctor_name_in_prompt():
    fake_response = MagicMock()
    fake_response.choices = [
        MagicMock(message=MagicMock(content='{"sections":[' + ',' .join(['{"title":"X","icon":"x","content":"x"}'] * 5) + ']}'))
    ]
    captured_user_prompt: list[str] = []

    async def _create(**kwargs):
        captured_user_prompt.append(kwargs["messages"][1]["content"])
        return fake_response

    with patch("src.scriptgen.settings") as s:
        s.openai_api_key = "k"
        s.openai_model = "gpt-4o-mini"
        with patch("src.scriptgen.AsyncOpenAI") as cls:
            cls.return_value.chat.completions.create = AsyncMock(side_effect=_create)
            await generate_script(
                name="Smile Dental",
                category="dental",
                summary="busy practice",
                pain_points='["wait times"]',
                sales_angles='["front desk"]',
                city="Boise", state="ID", rating=4.5, review_count=30,
                website_doctor_name="Dr. Sarah Smith",
                owner_name=None, owner_title=None,
                review_excerpts=["Long wait times in lobby"],
            )

    assert "Dr. Sarah Smith" in captured_user_prompt[0]
    assert "Boise" in captured_user_prompt[0]
    assert "Long wait times in lobby" in captured_user_prompt[0]


@pytest.mark.asyncio
async def test_generate_script_falls_back_to_practice_name_when_no_doctor():
    fake_response = MagicMock()
    fake_response.choices = [
        MagicMock(message=MagicMock(content='{"sections":[' + ',' .join(['{"title":"X","icon":"x","content":"x"}'] * 5) + ']}'))
    ]
    captured_user_prompt: list[str] = []

    async def _create(**kwargs):
        captured_user_prompt.append(kwargs["messages"][1]["content"])
        return fake_response

    with patch("src.scriptgen.settings") as s:
        s.openai_api_key = "k"
        s.openai_model = "gpt-4o-mini"
        with patch("src.scriptgen.AsyncOpenAI") as cls:
            cls.return_value.chat.completions.create = AsyncMock(side_effect=_create)
            await generate_script(
                name="Smile Dental",
                category="dental",
                summary=None, pain_points=None, sales_angles=None,
                city=None, state=None, rating=None, review_count=None,
                website_doctor_name=None,
                owner_name=None, owner_title=None,
                review_excerpts=None,
            )

    assert "Smile Dental" in captured_user_prompt[0]


@pytest.mark.asyncio
async def test_generate_script_mock_uses_doctor_name():
    """Without OpenAI key, mock script substitutes doctor name into opening."""
    with patch("src.scriptgen.settings") as s:
        s.openai_api_key = None
        result = await generate_script(
            name="Smile Dental",
            category="dental",
            summary=None, pain_points=None, sales_angles=None,
            city="Boise", state="ID", rating=4.5, review_count=30,
            website_doctor_name="Dr. Sarah Smith",
            owner_name=None, owner_title=None,
            review_excerpts=None,
        )
    opening = result["sections"][0]["content"]
    assert "Dr. Sarah Smith" in opening
