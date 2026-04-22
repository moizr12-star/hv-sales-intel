from unittest.mock import MagicMock, patch

from src.storage import update_practice_fields


def _mock_supabase_update_returning(row):
    client = MagicMock()
    table = MagicMock()
    table.update.return_value = table
    table.eq.return_value = table
    table.execute.return_value = MagicMock(data=[row])
    client.table.return_value = table
    return client, table


def test_update_practice_fields_stamps_touched_by():
    client, table = _mock_supabase_update_returning({"place_id": "p1"})
    with patch("src.storage._get_client", return_value=client):
        update_practice_fields("p1", {"status": "CONTACTED"}, touched_by="user-1")
    call_args = table.update.call_args.args[0]
    assert call_args["status"] == "CONTACTED"
    assert call_args["last_touched_by"] == "user-1"
    assert "last_touched_at" in call_args


def test_update_practice_fields_no_stamp_when_touched_by_none():
    client, table = _mock_supabase_update_returning({"place_id": "p1"})
    with patch("src.storage._get_client", return_value=client):
        update_practice_fields("p1", {"status": "CONTACTED"})
    call_args = table.update.call_args.args[0]
    assert "last_touched_by" not in call_args
    assert "last_touched_at" not in call_args
