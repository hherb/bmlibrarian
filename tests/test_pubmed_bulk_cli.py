"""Tests for pubmed_bulk_cli.py argument handling (no database or network)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pubmed_bulk_cli as cli  # noqa: E402


def test_import_accepts_workers() -> None:
    args = cli.build_parser().parse_args(["import", "--type", "baseline", "--workers", "6"])
    assert args.workers == 6


def test_workers_default_is_positive() -> None:
    args = cli.build_parser().parse_args(["import"])
    assert args.workers >= 1


def test_sync_accepts_workers() -> None:
    args = cli.build_parser().parse_args(["sync", "--updates-only", "--workers", "3"])
    assert args.workers == 3


def test_cmd_import_passes_workers_to_importer() -> None:
    args = cli.build_parser().parse_args(["import", "--type", "update", "--workers", "4"])
    with patch.object(cli, "PubMedBulkImporter") as importer_cls:
        importer = MagicMock()
        importer.import_all_files.return_value = {"files_processed": 0, "files_skipped": 0,
                                                  "total_articles": 0, "total_errors": 0}
        importer_cls.return_value = importer
        assert cli.cmd_import(args) == 0
    importer.import_all_files.assert_called_once()
    assert importer.import_all_files.call_args.kwargs["workers"] == 4
    assert importer.import_all_files.call_args.kwargs["file_type"] == "update"


def test_import_profile_flags_parse() -> None:
    args = cli.build_parser().parse_args(["import", "--import-profile", "--force-profile"])
    assert args.import_profile is True and args.force_profile is True
    assert cli.build_parser().parse_args(["import"]).import_profile is False


def test_profile_subcommand_parses() -> None:
    assert cli.build_parser().parse_args(["profile", "restore"]).profile_action == "restore"


def test_cmd_import_with_profile_closes_pool_inside_profile() -> None:
    """The profile is applied before the pool opens and restored after it closes."""
    from contextlib import contextmanager

    events = []

    @contextmanager
    def fake_profile(conninfo, force=False):
        events.append(("apply", conninfo, force))
        yield None
        events.append(("restore",))

    args = cli.build_parser().parse_args(["import", "--import-profile"])
    importer = MagicMock()
    importer.import_all_files.side_effect = lambda **kw: events.append(("import",)) or {
        "files_processed": 0, "files_skipped": 0, "total_articles": 0, "total_errors": 0}
    importer.db_manager.close.side_effect = lambda: events.append(("close",))
    with patch.object(cli, "import_profile", fake_profile), \
         patch.object(cli, "current_conninfo", return_value="dbname=dev"), \
         patch.object(cli, "PubMedBulkImporter", side_effect=lambda **kw: events.append(("open",)) or importer):
        assert cli.cmd_import(args) == 0
    assert [e[0] for e in events] == ["apply", "open", "import", "close", "restore"]
    assert events[0][1] == "dbname=dev"


def test_backfill_withdrawals_parses_with_update_default() -> None:
    args = cli.build_parser().parse_args(["backfill-withdrawals"])
    assert args.command == "backfill-withdrawals" and args.type == "update"


def test_cmd_backfill_withdrawals_calls_importer() -> None:
    args = cli.build_parser().parse_args(["backfill-withdrawals", "--type", "all"])
    with patch.object(cli, "PubMedBulkImporter") as importer_cls:
        importer = MagicMock()
        importer.backfill_withdrawals.return_value = {"files_scanned": 2, "pmids_listed": 5, "pmids_recorded": 3}
        importer_cls.return_value = importer
        assert cli.cmd_backfill_withdrawals(args) == 0
    assert importer.backfill_withdrawals.call_args.kwargs["file_type"] is None
