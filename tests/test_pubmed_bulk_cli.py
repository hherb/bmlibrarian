"""Tests for pubmed_bulk_cli.py argument handling (no database or network)."""

import sys
from pathlib import Path
from typing import List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

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
    """The subcommand exists and scans update files by default."""
    args = cli.build_parser().parse_args(["backfill-withdrawals"])
    assert args.command == "backfill-withdrawals" and args.type == "update"


def backfill_result(**overrides: object) -> dict:
    """A backfill_withdrawals() result with all counters."""
    result = {"files_scanned": 2, "pmids_listed": 5, "pmids_invalid": 0, "pmids_recorded": 3,
              "documents_marked": 2, "files_failed": []}
    result.update(overrides)
    return result


def run_backfill(argv: List[str], result: Optional[dict] = None,
                 error: Optional[Exception] = None) -> Tuple[int, MagicMock]:
    """Run cmd_backfill_withdrawals with a mocked importer; returns (exit code, importer mock)."""
    args = cli.build_parser().parse_args(["backfill-withdrawals", *argv])
    with patch.object(cli, "PubMedBulkImporter") as importer_cls:
        importer = MagicMock()
        if error is not None:
            importer.backfill_withdrawals.side_effect = error
        else:
            importer.backfill_withdrawals.return_value = result or backfill_result()
        importer_cls.return_value = importer
        return cli.cmd_backfill_withdrawals(args), importer


@pytest.mark.parametrize("cli_type, file_type", [("all", None), ("baseline", "baseline"), ("update", "update")])
def test_cmd_backfill_withdrawals_maps_type(cli_type: str, file_type: Optional[str]) -> None:
    """--type all/baseline/update reach the importer as None/'baseline'/'update'."""
    code, importer = run_backfill(["--type", cli_type])
    assert code == 0
    assert importer.backfill_withdrawals.call_args.kwargs["file_type"] == file_type


def test_cmd_backfill_withdrawals_reports_failure(capsys: pytest.CaptureFixture) -> None:
    """An exception is printed and exits 1."""
    code, _ = run_backfill([], error=FileNotFoundError("no downloaded PubMed files"))
    assert code == 1
    assert "no downloaded PubMed files" in capsys.readouterr().out


def test_cmd_backfill_withdrawals_unreadable_files_exit_nonzero(capsys: pytest.CaptureFixture) -> None:
    """Unreadable files are listed and make the command exit 1."""
    code, _ = run_backfill([], result=backfill_result(files_failed=["bad.xml.gz"]))
    assert code == 1
    out = capsys.readouterr().out
    assert "bad.xml.gz" in out and "Documents newly marked: 2" in out
