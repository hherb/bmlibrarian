"""Tests for pubmed_repair_cli.py repair exit codes (no database or network)."""

import argparse
import gzip
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pubmed_repair_cli as cli  # noqa: E402


def run_repair(tmp_path: Path, import_errors: int) -> int:
    """Repair one corrupted baseline file (the re-download succeeds) and re-import it."""
    baseline_dir = tmp_path / "baseline"
    update_dir = tmp_path / "updatefiles"
    baseline_dir.mkdir()
    update_dir.mkdir()
    corrupted = baseline_dir / "pubmed26n0001.xml.gz"
    corrupted.write_bytes(b"not gzip")

    def redownload(skip_existing: bool) -> None:
        with gzip.open(corrupted, "wb") as f:
            f.write(b"<PubmedArticleSet/>")

    args = argparse.Namespace(data_dir=tmp_path, reimport=True, type=None, verbose=False, yes=True)
    with patch.object(cli, "PubMedBulkImporter") as importer_cls, \
            patch.object(cli, "DownloadTracker"), \
            patch.object(cli, "reset_file_for_redownload"), \
            patch.object(cli, "reset_file_for_reimport"):
        importer = importer_cls.return_value
        importer.baseline_dir = baseline_dir
        importer.update_dir = update_dir
        importer.download_baseline.side_effect = redownload
        importer.import_all_files.return_value = {
            "files_processed": 1, "total_articles": 0, "total_errors": import_errors}
        return cli.cmd_repair(args)


@pytest.mark.parametrize("import_errors,expected", [(0, 0), (1, 1)])
def test_repair_exit_code_counts_reimport_errors(tmp_path: Path, import_errors: int, expected: int) -> None:
    """A repaired file that then fails to import must not exit 0 (#445 for repair)."""
    assert run_repair(tmp_path, import_errors) == expected
