from unittest.mock import MagicMock, patch

from src.storage import (
    insert_email_message,
    list_email_messages,
    list_outbound_message_ids,
)


def _make_client_with(insert_data=None, select_data=None):
    client = MagicMock()
    table = MagicMock()
    table.insert.return_value = table
    table.select.return_value = table
    table.eq.return_value = table
    table.order.return_value = table
    table.execute.return_value = MagicMock(
        data=insert_data if insert_data is not None else select_data
    )
    client.table.return_value = table
    return client, table


def test_insert_email_message_happy_path():
    client, table = _make_client_with(insert_data=[{"id": 1, "practice_id": 5}])
    with patch("src.storage._get_client", return_value=client):
        result = insert_email_message(
            practice_id=5,
            user_id="user-uuid",
            direction="out",
            subject="Hello",
            body="...",
            message_id="<m@h>",
            in_reply_to=None,
            error=None,
        )
    assert result == {"id": 1, "practice_id": 5}
    insert_arg = table.insert.call_args.args[0]
    assert insert_arg["practice_id"] == 5
    assert insert_arg["direction"] == "out"
    assert insert_arg["message_id"] == "<m@h>"


def test_list_email_messages_returns_rows():
    rows = [{"id": 1, "direction": "out"}, {"id": 2, "direction": "in"}]
    client, _ = _make_client_with(select_data=rows)
    with patch("src.storage._get_client", return_value=client):
        result = list_email_messages(5)
    assert result == rows


def test_list_outbound_message_ids():
    rows = [{"message_id": "<a>"}, {"message_id": "<b>"}, {"message_id": None}]
    client, _ = _make_client_with(select_data=rows)
    with patch("src.storage._get_client", return_value=client):
        result = list_outbound_message_ids(5)
    assert result == ["<a>", "<b>"]
