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
        model="stub",
        provider=SimpleNamespace(value="ollama"),
    )

    with patch("bmlibrarian.llm.client.LLMClient.generate", return_value=response):
        metadata = matcher.extract_metadata_with_llm("First page text of a paper")

    assert metadata["doi"] == "10.1234/example"
    assert metadata["pmid"] == "12345678"
    assert metadata["title"] == "A Study"
    assert metadata["authors"] == ["Smith J"]
