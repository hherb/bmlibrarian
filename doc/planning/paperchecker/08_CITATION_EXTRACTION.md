# Step 8: Citation Extraction Integration

## Context

Document scoring (Step 7) has identified high-relevance documents. Now we need to extract specific passages that support the counter-statement.

## Objective

Integrate existing CitationFinderAgent to extract citations from high-scoring documents. Adapt prompts to focus on finding evidence that supports the counter-claim (contradicts the original statement).

## Requirements

- Reuse existing CitationFinderAgent
- Adapt prompts for counter-evidence extraction
- Extract specific passages with context
- Format citations in AMA style
- Track all metadata (PMID, DOI, authors, etc.)
- Limit citations per statement (default: 10)

## Implementation Location

Update: `src/bmlibrarian/paperchecker/agent.py` (`_extract_citations` method)

## Design Approach

The existing CitationFinderAgent provides:
- Passage extraction from documents
- Citation formatting
- Relevance assessment

We need to:
1. Convert ScoredDocument objects to format expected by CitationAgent
2. Adapt extraction question to focus on counter-evidence
3. Create ExtractedCitation objects with full metadata
4. Order citations by relevance score

## Implementation

Update `src/bmlibrarian/paperchecker/agent.py`:

```python
def _extract_citations(
    self, counter_stmt: CounterStatement, scored_docs: List[ScoredDocument]
) -> List[ExtractedCitation]:
    """
    Step 5: Extract citations from high-scoring documents

    Uses CitationFinderAgent to extract specific passages that support
    the counter-statement. Only documents above the min_citation_score
    are processed.

    Args:
        counter_stmt: CounterStatement being supported
        scored_docs: List of ScoredDocument objects (sorted by score)

    Returns:
        List of ExtractedCitation objects (ordered by relevance)
    """
    logger.info(
        f"Extracting citations from {len(scored_docs)} scored documents "
        f"(min score: {self.min_citation_score})"
    )

    # Filter to documents above min_citation_score
    eligible_docs = [
        doc for doc in scored_docs
        if doc.score >= self.min_citation_score
    ]

    logger.info(f"{len(eligible_docs)} documents eligible for citation extraction")

    if not eligible_docs:
        logger.warning("No documents above min_citation_score for citation extraction")
        return []

    # Prepare for citation extraction
    extraction_question = self._build_extraction_question(counter_stmt)

    # Convert to format expected by CitationFinderAgent
    scored_tuples = [
        (doc.document, doc.score)
        for doc in eligible_docs
    ]

    # Extract citations using CitationFinderAgent
    try:
        # Use existing agent's batch extraction capability
        citation_results = self.citation_agent.process_scored_documents_for_citations(
            user_question=extraction_question,
            scored_documents=scored_tuples,
            score_threshold=self.min_citation_score
        )

        # Convert to ExtractedCitation objects
        citations = []
        for i, citation_data in enumerate(citation_results, 1):
            # Find corresponding ScoredDocument for metadata
            doc_id = citation_data.get("doc_id")
            scored_doc = next(
                (d for d in eligible_docs if d.doc_id == doc_id),
                None
            )

            if not scored_doc:
                logger.warning(f"Could not find scored_doc for citation {i}")
                continue

            # Create ExtractedCitation
            citation = ExtractedCitation(
                doc_id=doc_id,
                passage=citation_data["passage"],
                relevance_score=scored_doc.score,
                full_citation=self._format_citation(scored_doc.document),
                metadata=self._extract_metadata(scored_doc.document),
                citation_order=i
            )

            citations.append(citation)

            # Respect max_citations limit
            max_citations = self.agent_config.get("citation", {}).get(
                "max_citations_per_statement", 10
            )
            if len(citations) >= max_citations:
                logger.info(f"Reached max_citations limit ({max_citations})")
                break

        logger.info(f"Extracted {len(citations)} citations")

        return citations

    except Exception as e:
        logger.error(f"Citation extraction failed: {e}", exc_info=True)
        raise RuntimeError(f"Failed to extract citations: {e}") from e

def _build_extraction_question(self, counter_stmt: CounterStatement) -> str:
    """
    Build question for citation extraction in counter-evidence context

    Frames the extraction to focus on passages that support the counter-claim.

    Args:
        counter_stmt: CounterStatement object

    Returns:
        Question string for CitationFinderAgent
    """
    return (
        f"Extract specific passages that provide evidence for this claim: "
        f"{counter_stmt.negated_text}. "
        f"We are looking for evidence that contradicts the statement: "
        f"{counter_stmt.original_statement.text}"
    )

def _format_citation(self, document: Dict[str, Any]) -> str:
    """
    Format document as AMA-style citation

    AMA (American Medical Association) format:
    Authors. Title. Journal. Year;Volume(Issue):Pages. DOI

    Args:
        document: Document data dict

    Returns:
        Formatted citation string
    """
    parts = []

    # Authors (limit to first 3, then et al)
    if document.get("authors"):
        authors = document["authors"]
        if isinstance(authors, list):
            if len(authors) <= 3:
                authors_str = ", ".join(authors)
            else:
                authors_str = ", ".join(authors[:3]) + ", et al"
        else:
            authors_str = str(authors)
        parts.append(authors_str)

    # Title
    if document.get("title"):
        parts.append(document["title"])

    # Journal
    if document.get("journal"):
        parts.append(document["journal"])

    # Year
    if document.get("publication_year"):
        parts.append(str(document["publication_year"]))

    # DOI (if available)
    if document.get("doi"):
        parts.append(f"doi:{document['doi']}")

    return ". ".join(parts) + "."

def _extract_metadata(self, document: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract metadata from document for citation tracking

    Args:
        document: Document data dict

    Returns:
        Metadata dict with pmid, doi, authors, year, journal, etc.
    """
    return {
        "pmid": document.get("pmid"),
        "doi": document.get("doi"),
        "authors": document.get("authors", []),
        "year": document.get("publication_year"),
        "journal": document.get("journal"),
        "title": document.get("title"),
        "source": document.get("source")
    }
```

## Enhanced Citation Extraction with Custom Prompts

If you need more control over citation extraction, create a custom extraction method:

```python
def _extract_citations_custom(
    self, counter_stmt: CounterStatement, scored_docs: List[ScoredDocument]
) -> List[ExtractedCitation]:
    """
    Custom citation extraction with specialized prompts

    This version gives more control over the extraction process,
    allowing for more targeted passage selection.
    """
    citations = []
    extraction_question = self._build_extraction_question(counter_stmt)

    for i, scored_doc in enumerate(scored_docs, 1):
        if scored_doc.score < self.min_citation_score:
            continue

        try:
            # Build custom prompt for this document
            prompt = self._build_citation_prompt(
                counter_stmt,
                scored_doc.document
            )

            # Call LLM for extraction
            response = self._call_llm_for_citation(prompt)

            # Parse passages from response
            passages = self._parse_citation_response(response)

            # Create citations from passages
            for passage in passages:
                citation = ExtractedCitation(
                    doc_id=scored_doc.doc_id,
                    passage=passage,
                    relevance_score=scored_doc.score,
                    full_citation=self._format_citation(scored_doc.document),
                    metadata=self._extract_metadata(scored_doc.document),
                    citation_order=len(citations) + 1
                )
                citations.append(citation)

                # Check max limit
                max_citations = self.agent_config.get("citation", {}).get(
                    "max_citations_per_statement", 10
                )
                if len(citations) >= max_citations:
                    return citations

        except Exception as e:
            logger.error(f"Failed to extract citation from doc {scored_doc.doc_id}: {e}")
            continue

    return citations

def _build_citation_prompt(
    self, counter_stmt: CounterStatement, document: Dict[str, Any]
) -> str:
    """Build prompt for custom citation extraction"""
    return f"""You are a medical researcher extracting evidence from a research paper.

**Counter-Claim to Support:**
{counter_stmt.negated_text}

**Document Title:**
{document.get('title', 'N/A')}

**Document Abstract:**
{document.get('abstract', 'N/A')}

**Task:**
Extract 1-3 specific passages (exact quotes) from the abstract that provide the strongest evidence supporting the counter-claim. Each passage should be:
- A direct quote from the abstract
- Self-contained and understandable
- Clearly relevant to the counter-claim
- Focused on results, findings, or conclusions (not methods)

**Output Format:**
Return ONLY valid JSON:
{{
  "passages": [
    "First relevant passage...",
    "Second relevant passage..."
  ]
}}

Return ONLY the JSON, nothing else."""
```

## Testing Strategy

Create `tests/test_citation_extraction_integration.py`:

```python
"""Tests for citation extraction integration"""

import pytest
from bmlibrarian.paperchecker.agent import PaperCheckerAgent
from bmlibrarian.paperchecker.data_models import (
    Statement, CounterStatement, ScoredDocument
)


@pytest.fixture
def paper_checker():
    """Initialize PaperCheckerAgent"""
    return PaperCheckerAgent()


@pytest.fixture
def counter_statement():
    """Sample counter-statement"""
    original = Statement(
        text="Metformin is superior to GLP-1",
        context="",
        statement_type="finding",
        confidence=0.9,
        statement_order=1
    )

    return CounterStatement(
        original_statement=original,
        negated_text="GLP-1 is superior or equivalent to metformin",
        hyde_abstracts=["..."],
        keywords=["GLP-1", "metformin"],
        generation_metadata={}
    )


@pytest.fixture
def scored_documents():
    """Sample scored documents"""
    return [
        ScoredDocument(
            doc_id=1,
            document={
                "id": 1,
                "title": "GLP-1 vs Metformin Study",
                "abstract": "Results showed GLP-1 superior...",
                "authors": ["Smith J", "Jones A"],
                "publication_year": 2023,
                "journal": "Diabetes Care",
                "pmid": 12345678,
                "doi": "10.1234/example"
            },
            score=5,
            explanation="Highly relevant",
            supports_counter=True,
            found_by=["semantic", "hyde"]
        ),
        ScoredDocument(
            doc_id=2,
            document={
                "id": 2,
                "title": "Another Study",
                "abstract": "GLP-1 showed better outcomes...",
                "authors": ["Brown B"],
                "publication_year": 2022,
                "journal": "JAMA",
                "pmid": 23456789,
                "doi": "10.1234/another"
            },
            score=4,
            explanation="Very relevant",
            supports_counter=True,
            found_by=["keyword"]
        )
    ]


def test_build_extraction_question(paper_checker, counter_statement):
    """Test extraction question construction"""
    question = paper_checker._build_extraction_question(counter_statement)

    assert "GLP-1 is superior or equivalent to metformin" in question
    assert "evidence" in question.lower()
    assert "passage" in question.lower()


def test_format_citation(paper_checker, scored_documents):
    """Test AMA citation formatting"""
    document = scored_documents[0].document
    citation = paper_checker._format_citation(document)

    # Check for key components
    assert "Smith J" in citation or "Jones A" in citation
    assert "GLP-1 vs Metformin Study" in citation
    assert "2023" in citation
    assert "10.1234/example" in citation


def test_extract_metadata(paper_checker, scored_documents):
    """Test metadata extraction"""
    document = scored_documents[0].document
    metadata = paper_checker._extract_metadata(document)

    assert metadata["pmid"] == 12345678
    assert metadata["doi"] == "10.1234/example"
    assert metadata["year"] == 2023
    assert metadata["journal"] == "Diabetes Care"
    assert "Smith J" in metadata["authors"]


def test_extract_citations(paper_checker, counter_statement, scored_documents):
    """Test citation extraction from scored documents"""
    citations = paper_checker._extract_citations(counter_statement, scored_documents)

    # Verify structure
    assert isinstance(citations, list)
    assert len(citations) > 0
    assert all(hasattr(c, "passage") for c in citations)
    assert all(hasattr(c, "full_citation") for c in citations)
    assert all(hasattr(c, "metadata") for c in citations)

    # Verify ordering
    orders = [c.citation_order for c in citations]
    assert orders == list(range(1, len(citations) + 1))

    # Verify metadata
    for citation in citations:
        assert citation.doc_id in [1, 2]
        assert citation.relevance_score >= paper_checker.min_citation_score
        assert len(citation.passage) > 0
        assert len(citation.full_citation) > 0


def test_citation_limit_respected(paper_checker, counter_statement):
    """Test that max_citations_per_statement is respected"""
    # Create many scored documents
    many_scored_docs = [
        ScoredDocument(
            doc_id=i,
            document={"id": i, "title": f"Study {i}", "abstract": "..."},
            score=5,
            explanation="Relevant",
            supports_counter=True,
            found_by=["semantic"]
        )
        for i in range(1, 21)  # 20 documents
    ]

    citations = paper_checker._extract_citations(counter_statement, many_scored_docs)

    max_citations = paper_checker.agent_config.get("citation", {}).get(
        "max_citations_per_statement", 10
    )

    assert len(citations) <= max_citations


def test_min_score_filtering(paper_checker, counter_statement):
    """Test that only high-scoring docs are used for citations"""
    mixed_scored_docs = [
        ScoredDocument(
            doc_id=1,
            document={"id": 1, "title": "High Score", "abstract": "..."},
            score=5,
            explanation="Highly relevant",
            supports_counter=True,
            found_by=["semantic"]
        ),
        ScoredDocument(
            doc_id=2,
            document={"id": 2, "title": "Low Score", "abstract": "..."},
            score=2,
            explanation="Minimally relevant",
            supports_counter=False,
            found_by=["keyword"]
        )
    ]

    citations = paper_checker._extract_citations(counter_statement, mixed_scored_docs)

    # Should only extract from doc 1 (score >= min_citation_score)
    doc_ids = [c.doc_id for c in citations]
    assert 1 in doc_ids
    assert 2 not in doc_ids
```

## Success Criteria

- [ ] Citation extraction integration complete
- [ ] Extraction question properly framed for counter-evidence
- [ ] AMA citation formatting correct
- [ ] Metadata extraction comprehensive
- [ ] Citation ordering maintained
- [ ] Max citations limit respected
- [ ] Min score filtering working
- [ ] Error handling for extraction failures
- [ ] All unit tests passing
- [ ] Citations are meaningful and relevant

## Next Steps

After completing this step, proceed to:
- **Step 9**: Counter-Report Generation (09_COUNTER_REPORT_GENERATION.md)
- Generate prose reports synthesizing the counter-evidence citations
