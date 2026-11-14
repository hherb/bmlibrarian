"""PDFMatcher BaseAgent-migration tests.

PDFMatcher was migrated from a hand-constructed LLMClient onto BaseAgent so
it gains token accounting, ``test_connection()``, unified host handling, and
— crucially — a wired ``fallback_model`` (its ``FALLBACK_MODEL`` constant was
previously dead). These tests pin that migration and confirm metadata
extraction behavior is unchanged.
"""

import os
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bmlibrarian.agents import BaseAgent
from bmlibrarian.importers.pdf_matcher import PDFMatcher
from bmlibrarian.utils.browser_downloader import CHROME_DOWNLOAD_DIR_PREFIX


@pytest.fixture
def matcher():
    """Construct a PDFMatcher without touching the database or filesystem."""
    with patch("bmlibrarian.importers.pdf_matcher.get_db_manager"), \
         patch("bmlibrarian.importers.pdf_matcher.PDFManager"):
        return PDFMatcher(show_model_info=False)


def test_pdf_matcher_is_base_agent(matcher):
    """PDFMatcher inherits the shared agent plumbing."""
    assert isinstance(matcher, BaseAgent)


def test_pdf_matcher_agent_type(matcher):
    """PDFMatcher exposes a stable agent-type identifier."""
    assert matcher.get_agent_type() == "pdf_matcher"


def test_pdf_matcher_wires_fallback_model(matcher):
    """The previously-dead FALLBACK_MODEL is now an active fallback."""
    assert matcher.fallback_model == PDFMatcher.FALLBACK_MODEL


def test_extract_metadata_parses_llm_json(matcher):
    """Metadata extraction still returns a parsed dict (behavior preserved)."""
    response = SimpleNamespace(
        content='{"doi": "10.1234/example", "pmid": "12345678", '
                '"title": "A Study", "authors": ["Smith J"]}',
        prompt_tokens=1,
        completion_tokens=1,
        duration_seconds=0.0,
        stop_reason="stop",
        model="stub",
        provider=SimpleNamespace(value="ollama"),
    )

    with patch("bmlibrarian.llm.client.LLMClient.generate", return_value=response):
        metadata = matcher.extract_metadata_with_llm("First page text of a paper")

    assert metadata["doi"] == "10.1234/example"
    assert metadata["pmid"] == "12345678"
    assert metadata["title"] == "A Study"
    assert metadata["authors"] == ["Smith J"]


def test_recursive_import_skips_chrome_download_dirs(matcher, tmp_path):
    """Leftover undetected-Chrome download dirs are never imported (#325)."""
    year_dir = tmp_path / "2024"
    leftover = year_dir / f"{CHROME_DOWNLOAD_DIR_PREFIX}abc123"
    leftover.mkdir(parents=True)
    (leftover / "orphan.pdf").write_bytes(b"%PDF-1.4\n")
    (year_dir / "10.1000_x.pdf").write_bytes(b"%PDF-1.4\n")
    seen = []

    def fake_import(pdf_file, dry_run):
        """Record each PDF the directory import would process."""
        seen.append(pdf_file)
        return {"status": "skipped"}

    with patch.object(matcher, "match_and_import_pdf", side_effect=fake_import):
        stats = matcher.match_and_import_directory(tmp_path, recursive=True)

    assert seen == [year_dir / "10.1000_x.pdf"]
    assert stats["total"] == 1


def _patch_target(target, db_update_ok=True):
    """Patch PDFManager so import_pdf_for_document places files at ``target``."""
    manager = patch("bmlibrarian.importers.pdf_matcher.PDFManager").start()
    manager.return_value.get_pdf_path.return_value = target
    manager.return_value.get_relative_pdf_path.return_value = target.name
    manager.return_value.update_database_pdf_path.return_value = db_update_ok
    manager.return_value._find_current_pdf_path.return_value = None
    return manager


@pytest.fixture
def placement(tmp_path):
    """A source PDF and a target path in separate folders."""
    source = tmp_path / "in" / "paper.pdf"
    source.parent.mkdir()
    source.write_bytes(b"%PDF-1.4 incoming, longer")
    target = tmp_path / "lib" / "2024" / "10.1000_x.pdf"
    yield source, target
    patch.stopall()


def test_import_never_replaces_a_different_existing_pdf(matcher, placement):
    """A newer, different PDF does not overwrite the stored one (#443)."""
    source, target = placement
    target.parent.mkdir(parents=True)
    target.write_bytes(b"%PDF-1.4 original")
    os.utime(target, (0, 0))  # stored file is older than the incoming one
    manager = _patch_target(target)

    result = matcher.import_pdf_for_document(source, {"id": 1, "doi": "10.1000/x"})

    assert result["status"] == "skipped"
    assert target.read_bytes() == b"%PDF-1.4 original"
    manager.return_value.update_database_pdf_path.assert_not_called()


def test_import_failed_db_update_leaves_no_file(matcher, placement):
    """A failed database update removes only our own copy (#443)."""
    source, target = placement
    _patch_target(target, db_update_ok=False)

    result = matcher.import_pdf_for_document(source, {"id": 1, "doi": "10.1000/x"})

    assert result["status"] == "failed"
    assert list(target.parent.iterdir()) == []


def test_import_copies_without_leaving_a_partial_file(matcher, placement):
    """A successful import leaves just the PDF at the target."""
    source, target = placement
    _patch_target(target)

    result = matcher.import_pdf_for_document(source, {"id": 1, "doi": "10.1000/x"})

    assert result["status"] == "imported"
    assert target.read_bytes() == source.read_bytes()
    assert list(target.parent.iterdir()) == [target]


@pytest.mark.parametrize("lookup", [{"pmid": "12345678"}, {"doi": "10.1000/x"}])
def test_document_status_queries_existing_columns_only(matcher, lookup):
    """The status lookups use external_id, not a nonexistent pmid column (#436)."""
    row = (7, "T", "A", ["X"], None, "12345678", None, "J", 1, "f.pdf", None, True)
    cur = MagicMock()
    cur.fetchone.side_effect = [row, (True,)]
    conn = matcher.db_manager.get_connection.return_value.__enter__.return_value
    conn.cursor.return_value.__enter__.return_value = cur

    status = matcher.check_document_status(**lookup)

    sql = cur.execute.call_args_list[0].args[0]
    assert not re.search(r"\bpmid\b", sql)
    assert status.exists and status.has_full_text and status.has_chunks
    assert status.document["external_id"] == "12345678"
    assert status.document["pdf_filename"] == "f.pdf"


def test_import_keeps_file_when_db_points_at_it(matcher, placement):
    """Once the database points at the copy it is never deleted (title=None)."""
    source, target = placement
    manager = _patch_target(target)

    result = matcher.import_pdf_for_document(
        source, {"id": 1, "doi": "10.1000/x", "title": None}
    )

    assert result["status"] == "imported"
    assert target.exists()
    manager.return_value.update_database_pdf_path.assert_called_once()


def test_import_db_error_removes_copy_and_partial(matcher, placement):
    """A database error before the pointer is written leaves no file behind."""
    source, target = placement
    manager = _patch_target(target)
    manager.return_value.update_database_pdf_path.side_effect = RuntimeError("db down")

    result = matcher.import_pdf_for_document(source, {"id": 1, "doi": "10.1000/x"})

    assert result["status"] == "failed"
    assert list(target.parent.iterdir()) == []


def test_import_failed_copy_removes_partial(matcher, placement):
    """A copy that fails half way leaves neither target nor partial file."""
    source, target = placement
    manager = _patch_target(target)

    def half_copy(src, dst):
        """Write part of the file, then fail like a full disk."""
        with open(dst, "wb") as handle:
            handle.write(b"%PDF")
        raise OSError("No space left on device")

    with patch("bmlibrarian.importers.pdf_matcher.shutil.copy2", side_effect=half_copy):
        result = matcher.import_pdf_for_document(source, {"id": 1, "doi": "10.1000/x"})

    assert result["status"] == "failed"
    assert list(target.parent.iterdir()) == []
    manager.return_value.update_database_pdf_path.assert_not_called()


def test_import_skips_when_target_appears_during_copy(matcher, placement):
    """A file placed at the target while copying is never overwritten (#443)."""
    source, target = placement
    manager = _patch_target(target)

    def copy_and_race(src, dst):
        """Copy, while another import places its own file at the target."""
        target.write_bytes(b"%PDF-1.4 the other import")
        with open(dst, "wb") as handle:
            handle.write(open(src, "rb").read())

    with patch("bmlibrarian.importers.pdf_matcher.shutil.copy2", side_effect=copy_and_race):
        result = matcher.import_pdf_for_document(source, {"id": 1, "doi": "10.1000/x"})

    assert result["status"] == "skipped"
    assert target.read_bytes() == b"%PDF-1.4 the other import"
    assert list(target.parent.iterdir()) == [target]
    manager.return_value.update_database_pdf_path.assert_not_called()


def test_import_failed_cleanup_still_reports_failure(matcher, placement):
    """A cleanup that cannot delete the copy still returns a failed result."""
    source, target = placement
    _patch_target(target, db_update_ok=False)

    with patch("pathlib.Path.unlink", side_effect=PermissionError("read-only")):
        result = matcher.import_pdf_for_document(source, {"id": 1, "doi": "10.1000/x"})

    assert result["status"] == "failed"
    assert result["reason"] == "Database update failed"


def test_import_never_replaces_pdf_stored_under_another_path(matcher, placement):
    """A PDF the database already records elsewhere keeps its pointer (#443)."""
    source, target = placement
    stored = target.parent.parent / "unknown" / target.name
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"%PDF-1.4 original")
    manager = _patch_target(target)
    manager.return_value._find_current_pdf_path.return_value = stored

    result = matcher.import_pdf_for_document(
        source, {"id": 1, "doi": "10.1000/x", "pdf_filename": "unknown/10.1000_x.pdf"}
    )

    assert result["status"] == "skipped"
    assert not target.exists()
    assert stored.read_bytes() == b"%PDF-1.4 original"
    manager.return_value.update_database_pdf_path.assert_not_called()
