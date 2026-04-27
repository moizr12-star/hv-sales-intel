from unittest.mock import MagicMock, patch

from src.storage import add_tags


def _fake_client_with_existing_tags(existing: list[str]):
    """Build a Supabase client mock returning a row with the given tags."""
    client = MagicMock()
    select_chain = MagicMock()
    select_chain.execute.return_value.data = {"tags": existing}
    client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value = select_chain

    update_chain = MagicMock()
    update_chain.execute.return_value.data = [{"tags": existing + ["NEW"]}]
    client.table.return_value.update.return_value.eq.return_value = update_chain
    return client


def test_add_tags_appends_when_absent():
    fake = _fake_client_with_existing_tags(["RESEARCHED"])
    with patch("src.storage._get_client", return_value=fake):
        add_tags("place-1", ["SCRIPT_READY"])
    update_args = fake.table.return_value.update.call_args.args[0]
    assert sorted(update_args["tags"]) == ["RESEARCHED", "SCRIPT_READY"]


def test_add_tags_dedupes_existing():
    fake = _fake_client_with_existing_tags(["RESEARCHED", "SCRIPT_READY"])
    with patch("src.storage._get_client", return_value=fake):
        add_tags("place-1", ["RESEARCHED"])
    fake.table.return_value.update.assert_not_called()


def test_add_tags_handles_empty_existing():
    fake = _fake_client_with_existing_tags([])
    with patch("src.storage._get_client", return_value=fake):
        add_tags("place-1", ["RESEARCHED", "ENRICHED"])
    update_args = fake.table.return_value.update.call_args.args[0]
    assert sorted(update_args["tags"]) == ["ENRICHED", "RESEARCHED"]


def test_add_tags_noop_when_no_new_tags():
    fake = _fake_client_with_existing_tags(["RESEARCHED"])
    with patch("src.storage._get_client", return_value=fake):
        add_tags("place-1", [])
    fake.table.return_value.update.assert_not_called()


def test_add_tags_skips_when_client_unconfigured():
    with patch("src.storage._get_client", return_value=None):
        add_tags("place-1", ["RESEARCHED"])  # must not raise
