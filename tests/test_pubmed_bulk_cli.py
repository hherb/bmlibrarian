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
