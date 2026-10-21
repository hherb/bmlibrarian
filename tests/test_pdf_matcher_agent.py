"""PDFMatcher BaseAgent-migration tests.

PDFMatcher was migrated from a hand-constructed LLMClient onto BaseAgent so
it gains token accounting, ``test_connection()``, unified host handling, and
— crucially — a wired ``fallback_model`` (its ``FALLBACK_MODEL`` constant was
previously dead). These tests pin that migration and confirm metadata
extraction behavior is unchanged.
"""

from types import SimpleNamespace
from unittest.mock import patch

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
