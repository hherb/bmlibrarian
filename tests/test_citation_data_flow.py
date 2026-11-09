"""Live check: a citation keeps the database document's DOI, PMID and publication.

Needs the database and Ollama: run with ``--run-live``.
"""

import pytest

from bmlibrarian.agents import CitationFinderAgent, ReportingAgent
from bmlibrarian.database import find_abstracts

pytestmark = [pytest.mark.requires_database, pytest.mark.requires_ollama]

QUERY = "omega-3 & cardiovascular"
QUESTION = "What are the cardiovascular benefits of omega-3 fatty acids?"
MAX_ROWS = 5
MIN_RELEVANCE = 0.5


def test_citation_with_real_data() -> None:
    """Citation and Vancouver reference carry the document's real identifiers."""
    documents = [d for d in find_abstracts(QUERY, max_rows=MAX_ROWS) if d.get("doi") and d.get("pmid")]
    if not documents:
        pytest.skip(f"no document with DOI and PMID for {QUERY!r}")
    document = documents[0]

    citation_agent = CitationFinderAgent(show_model_info=False)
    if not citation_agent.test_connection():
        pytest.skip("LLM provider not reachable")
    citation = citation_agent.extract_citation_from_document(
        user_question=QUESTION, document=document, min_relevance=MIN_RELEVANCE)
    if citation is None:
        pytest.skip("no citation extracted (below relevance threshold)")

    assert (citation.doi, citation.pmid, citation.publication) == (
        document["doi"], document["pmid"], document.get("publication"))
    reference = ReportingAgent(show_model_info=False).create_references([citation])[0]
    formatted = reference.format_vancouver_style()
    assert citation.doi in formatted
    assert citation.pmid in formatted
