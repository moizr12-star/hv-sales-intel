from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import call_log
from src.models import Practice


@pytest.mark.asyncio
async def test_polish_note_returns_empty_marker_for_blank_input():
    result = await call_log.polish_note("")
    assert result == "(call logged, no note)"

    result = await call_log.polish_note("   \n  ")
    assert result == "(call logged, no note)"


@pytest.mark.asyncio
async def test_polish_note_uses_gpt_when_configured():
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content="Left voicemail. Will retry Thursday."))]
    create_mock = AsyncMock(return_value=response)
    client = MagicMock()
    client.chat.completions.create = create_mock

    with patch("src.call_log.settings") as s:
        s.openai_api_key = "sk-test"
        with patch("src.call_log.AsyncOpenAI", return_value=client):
            result = await call_log.polish_note("left vm, gonna retry thu")

    assert result == "Left voicemail. Will retry Thursday."
    create_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_polish_note_falls_back_on_openai_error():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=Exception("boom"))

    with patch("src.call_log.settings") as s:
        s.openai_api_key = "sk-test"
        with patch("src.call_log.AsyncOpenAI", return_value=client):
            result = await call_log.polish_note("raw note")

    assert result == "raw note (unpolished)"


@pytest.mark.asyncio
async def test_polish_note_falls_back_when_no_openai_key():
    with patch("src.call_log.settings") as s:
        s.openai_api_key = ""
        result = await call_log.polish_note("raw note")
    assert result == "raw note (unpolished)"


@pytest.mark.asyncio
async def test_append_call_note_increments_count_and_formats_line():
    practice = Practice(
        place_id="abc", name="Test", call_count=2, call_notes="[prev] existing"
    )
    user = {"id": "u1", "name": "Sarah Khan"}

    stored: dict = {}
    def fake_update(place_id: str, fields: dict, touched_by: str | None):
        stored.update(fields)
        stored["_place_id"] = place_id
        stored["_touched_by"] = touched_by
        return {**practice.model_dump(), **fields, "last_touched_by": touched_by}

    with patch("src.call_log.get_practice", return_value=practice.model_dump()):
        with patch("src.call_log.update_practice_fields", side_effect=fake_update):
            with patch("src.call_log.polish_note", AsyncMock(return_value="Polished entry.")):
                with patch("src.call_log.salesforce.sync_practice", AsyncMock(return_value={"skipped": True, "reason": "sf_not_configured"})):
                    result_practice, warning = await call_log.append_call_note(
                        "abc", "raw", user
                    )

    assert stored["call_count"] == 3
    assert "[prev] existing" in stored["call_notes"]
    assert "Sarah Khan: Polished entry." in stored["call_notes"]
    assert stored["call_notes"].splitlines()[-1].endswith("Sarah Khan: Polished entry.")
    assert stored["_touched_by"] == "u1"
    assert warning is None


@pytest.mark.asyncio
async def test_append_call_note_sets_sf_fields_when_sync_succeeds():
    practice = Practice(place_id="abc", name="Test", call_count=0, call_notes=None)
    user = {"id": "u1", "name": "Sarah Khan"}

    stored: dict = {}
    def fake_update(place_id: str, fields: dict, touched_by: str | None):
        stored.update(fields)
        return {**practice.model_dump(), **fields}

    sync_result = {
        "sf_lead_id": "00Q_NEW",
        "sf_owner_id": "005XYZ",
        "sf_owner_name": "Sarah Khan",
        "synced_at": "2026-04-23T10:22:00+00:00",
    }

    with patch("src.call_log.get_practice", return_value=practice.model_dump()):
        with patch("src.call_log.update_practice_fields", side_effect=fake_update):
            with patch("src.call_log.polish_note", AsyncMock(return_value="Polished.")):
                with patch("src.call_log.salesforce.sync_practice", AsyncMock(return_value=sync_result)):
                    await call_log.append_call_note("abc", "raw", user)

    assert stored["salesforce_lead_id"] == "00Q_NEW"
    assert stored["salesforce_owner_id"] == "005XYZ"
    assert stored["salesforce_owner_name"] == "Sarah Khan"
    assert stored["salesforce_synced_at"] == "2026-04-23T10:22:00+00:00"


@pytest.mark.asyncio
async def test_append_call_note_surfaces_warning_on_sf_failure():
    practice = Practice(place_id="abc", name="Test", call_count=0, call_notes=None)
    user = {"id": "u1", "name": "Sarah Khan"}

    with patch("src.call_log.get_practice", return_value=practice.model_dump()):
        with patch("src.call_log.update_practice_fields", return_value=practice.model_dump()):
            with patch("src.call_log.polish_note", AsyncMock(return_value="Polished.")):
                with patch("src.call_log.salesforce.sync_practice", AsyncMock(side_effect=Exception("Bad Request"))):
                    result_practice, warning = await call_log.append_call_note(
                        "abc", "raw", user
                    )

    assert warning is not None
    assert "Bad Request" in warning


@pytest.mark.asyncio
async def test_append_call_note_raises_when_practice_missing():
    with patch("src.call_log.get_practice", return_value=None):
        with pytest.raises(LookupError):
            await call_log.append_call_note("missing", "raw", {"id": "u1", "name": "X"})
