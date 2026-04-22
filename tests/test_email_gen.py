import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import email_gen


@pytest.mark.asyncio
async def test_generate_email_draft_mock_when_no_openai_key():
    with patch("src.email_gen.settings") as s:
        s.openai_api_key = ""
        result = await email_gen.generate_email_draft(
            name="Bright Smiles Dental",
            category="dental",
            summary=None,
            pain_points=None,
            sales_angles=None,
        )
    assert "subject" in result
    assert "body" in result
    assert "Bright Smiles Dental" in result["body"] or "Bright Smiles Dental" in result["subject"]


@pytest.mark.asyncio
async def test_generate_email_draft_with_gpt():
    fake_content = json.dumps({"subject": "Staffing support for your practice", "body": "Hi there..."})
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=fake_content))]

    create_mock = AsyncMock(return_value=response)
    client = MagicMock()
    client.chat.completions.create = create_mock

    with patch("src.email_gen.settings") as s:
        s.openai_api_key = "sk-test"
        s.openai_model = "gpt-4o"
        with patch("src.email_gen.AsyncOpenAI", return_value=client):
            result = await email_gen.generate_email_draft(
                name="Test Clinic",
                category="dental",
                summary="Summary",
                pain_points='["pain 1"]',
                sales_angles='["angle 1"]',
            )

    assert result == {"subject": "Staffing support for your practice", "body": "Hi there..."}


@pytest.mark.asyncio
async def test_generate_email_draft_falls_back_on_gpt_error():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=Exception("boom"))

    with patch("src.email_gen.settings") as s:
        s.openai_api_key = "sk-test"
        s.openai_model = "gpt-4o"
        with patch("src.email_gen.AsyncOpenAI", return_value=client):
            result = await email_gen.generate_email_draft(
                name="Fallback Clinic", category="dental",
                summary=None, pain_points=None, sales_angles=None,
            )
    assert "subject" in result
    assert "body" in result
