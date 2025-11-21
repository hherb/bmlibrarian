# Step 7: Document Scoring Integration

## Context

Multi-strategy search (Step 6) now provides lists of potentially relevant documents. We need to score each document for its usefulness in supporting the counter-statement.

## Objective

Integrate existing DocumentScoringAgent to score documents for counter-statement support. Adapt the agent's prompts and scoring logic to evaluate documents in the context of finding contradictory evidence.

## Requirements

- Reuse existing DocumentScoringAgent (no need to reimplement)
- Adapt prompts for counter-statement evaluation context
- Score on 1-5 scale (existing BMLibrarian standard)
- Filter documents above threshold (default: 3.0)
- Track provenance from search strategies
- Batch process for efficiency

## Implementation Location

Update: `src/bmlibrarian/paperchecker/agent.py` (`_score_documents` method)

## Design Approach

The existing DocumentScoringAgent already provides:
- 1-5 relevance scoring
- Explanations for scores
- Batch processing capabilities

We need to:
1. Modify the question/context to focus on counter-evidence
2. Fetch full document data for scoring
3. Apply existing scoring logic
4. Create ScoredDocument objects with provenance

## Implementation

Update `src/bmlibrarian/paperchecker/agent.py`:

```python
def _score_documents(
    self, counter_stmt: CounterStatement, search_results: SearchResults
) -> List[ScoredDocument]:
    """
    Step 4: Score documents for counter-statement support

    Uses DocumentScoringAgent to evaluate how useful each document is
    for supporting the counter-claim. Documents are scored 1-5, and only
    those above the configured threshold are kept.

    Args:
        counter_stmt: CounterStatement to evaluate against
        search_results: SearchResults with document IDs and provenance

    Returns:
        List of ScoredDocument objects (only those above threshold)
    """
    logger.info(
        f"Scoring {len(search_results.deduplicated_docs)} documents "
        f"for counter-statement support"
    )

    # Fetch full document data
    documents = self._fetch_documents(search_results.deduplicated_docs)

    # Build scoring question focused on counter-evidence
    scoring_question = self._build_scoring_question(counter_stmt)

    # Score each document
    scored_docs = []
    for doc_id, document in documents.items():
        try:
            # Get provenance for this document
            found_by = search_results.provenance.get(doc_id, [])

            # Score using DocumentScoringAgent
            score = self.scoring_agent.evaluate_document(
                user_question=scoring_question,
                document=document
            )

            # Skip if below threshold
            if score < self.score_threshold:
                continue

            # Create ScoredDocument
            scored_doc = ScoredDocument(
                doc_id=doc_id,
                document=document,
                score=score,
                explanation=self._get_score_explanation(score, document, scoring_question),
                supports_counter=(score >= self.score_threshold),
                found_by=found_by
            )

            scored_docs.append(scored_doc)

            logger.debug(
                f"Doc {doc_id}: score={score}, found_by={found_by}"
            )

        except Exception as e:
            logger.error(f"Failed to score document {doc_id}: {e}")
            # Continue with other documents
            continue

    logger.info(
        f"Scoring complete: {len(scored_docs)}/{len(documents)} documents "
        f"above threshold ({self.score_threshold})"
    )

    # Sort by score (descending)
    scored_docs.sort(key=lambda x: x.score, reverse=True)

    return scored_docs

def _build_scoring_question(self, counter_stmt: CounterStatement) -> str:
    """
    Build question for scoring documents in counter-evidence context

    The question frames the scoring in terms of finding evidence that
    SUPPORTS the counter-statement (i.e., contradicts the original claim).

    Args:
        counter_stmt: CounterStatement object

    Returns:
        Question string for DocumentScoringAgent
    """
    return (
        f"Does this document provide evidence that supports or relates to "
        f"the following claim: {counter_stmt.negated_text}? "
        f"We are looking for evidence that contradicts: {counter_stmt.original_statement.text}"
    )

def _fetch_documents(self, doc_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """
    Fetch full document data from database

    Args:
        doc_ids: List of document IDs to fetch

    Returns:
        Dict mapping doc_id → document data

    Raises:
        RuntimeError: If database query fails
    """
    if not doc_ids:
        return {}

    try:
        with self.db.conn.cursor(row_factory=dict_row) as cur:
            # Use ANY for efficient IN query
            cur.execute("""
                SELECT
                    id, title, abstract, authors, publication_year,
                    journal, pmid, doi, source
                FROM public.documents
                WHERE id = ANY(%s)
            """, (doc_ids,))

            results = cur.fetchall()

        # Convert to dict keyed by ID
        documents = {row["id"]: dict(row) for row in results}

        logger.debug(f"Fetched {len(documents)} documents from database")

        return documents

    except Exception as e:
        logger.error(f"Failed to fetch documents: {e}")
        raise RuntimeError(f"Database query failed: {e}") from e

def _get_score_explanation(
    self, score: int, document: Dict[str, Any], question: str
) -> str:
    """
    Generate explanation for document score

    This is a simple heuristic. For production, you might want to:
    1. Extract explanation from ScoringAgent if it provides one
    2. Use an LLM to generate explanation
    3. Provide more detailed relevance analysis

    Args:
        score: The relevance score (1-5)
        document: Document data
        question: Scoring question

    Returns:
        Explanation string
    """
    explanations = {
        5: "Highly relevant - directly addresses the counter-claim",
        4: "Very relevant - provides strong supporting evidence",
        3: "Moderately relevant - provides some relevant information",
        2: "Minimally relevant - tangentially related",
        1: "Not relevant - does not address the counter-claim"
    }

    base_explanation = explanations.get(score, "Relevance unclear")

    # Add title context if available
    if document.get("title"):
        base_explanation += f" (Title: {document['title'][:50]}...)"

    return base_explanation
```

## Optimization: Batch Scoring

For improved performance, consider implementing batch scoring:

```python
def _score_documents_batch(
    self, counter_stmt: CounterStatement, search_results: SearchResults
) -> List[ScoredDocument]:
    """
    Batch version of document scoring (more efficient)

    Scores documents in batches to reduce overhead. This is especially
    important when dealing with 50-100+ documents.
    """
    documents = self._fetch_documents(search_results.deduplicated_docs)
    scoring_question = self._build_scoring_question(counter_stmt)

    # Batch size for scoring
    batch_size = 20
    all_scored_docs = []

    doc_items = list(documents.items())
    for i in range(0, len(doc_items), batch_size):
        batch = doc_items[i:i+batch_size]

        logger.debug(f"Scoring batch {i//batch_size + 1}/{(len(doc_items)-1)//batch_size + 1}")

        for doc_id, document in batch:
            try:
                score = self.scoring_agent.evaluate_document(
                    user_question=scoring_question,
                    document=document
                )

                if score >= self.score_threshold:
                    scored_doc = ScoredDocument(
                        doc_id=doc_id,
                        document=document,
                        score=score,
                        explanation=self._get_score_explanation(score, document, scoring_question),
                        supports_counter=True,
                        found_by=search_results.provenance.get(doc_id, [])
                    )
                    all_scored_docs.append(scored_doc)

            except Exception as e:
                logger.error(f"Failed to score document {doc_id}: {e}")
                continue

    all_scored_docs.sort(key=lambda x: x.score, reverse=True)
    return all_scored_docs
```

## Testing Strategy

Create `tests/test_document_scoring_integration.py`:

```python
"""Tests for document scoring integration"""

import pytest
from bmlibrarian.paperchecker.agent import PaperCheckerAgent
from bmlibrarian.paperchecker.data_models import Statement, CounterStatement, SearchResults


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
def search_results():
    """Sample search results"""
    return SearchResults(
        semantic_docs=[1, 2, 3],
        hyde_docs=[2, 3, 4],
        keyword_docs=[3, 4, 5],
        deduplicated_docs=[1, 2, 3, 4, 5],
        provenance={
            1: ["semantic"],
            2: ["semantic", "hyde"],
            3: ["semantic", "hyde", "keyword"],
            4: ["hyde", "keyword"],
            5: ["keyword"]
        },
        search_metadata={}
    )


def test_fetch_documents(paper_checker):
    """Test document fetching"""
    # Assuming we have some documents in the database
    doc_ids = [1, 2, 3]
    documents = paper_checker._fetch_documents(doc_ids)

    assert isinstance(documents, dict)
    assert all(doc_id in documents for doc_id in doc_ids)
    assert all("title" in doc for doc in documents.values())
    assert all("abstract" in doc for doc in documents.values())


def test_build_scoring_question(paper_checker, counter_statement):
    """Test scoring question construction"""
    question = paper_checker._build_scoring_question(counter_statement)

    assert "GLP-1 is superior or equivalent to metformin" in question
    assert "Metformin is superior to GLP-1" in question
    assert "evidence" in question.lower()


def test_score_documents(paper_checker, counter_statement, search_results):
    """Test document scoring"""
    scored_docs = paper_checker._score_documents(counter_statement, search_results)

    # Verify structure
    assert isinstance(scored_docs, list)
    assert all(hasattr(doc, "score") for doc in scored_docs)
    assert all(1 <= doc.score <= 5 for doc in scored_docs)
    assert all(doc.supports_counter for doc in scored_docs)  # All above threshold

    # Verify sorting (descending by score)
    scores = [doc.score for doc in scored_docs]
    assert scores == sorted(scores, reverse=True)

    # Verify provenance preserved
    for doc in scored_docs:
        assert len(doc.found_by) > 0
        assert all(strategy in ["semantic", "hyde", "keyword"]
                   for strategy in doc.found_by)


def test_scoring_threshold_filtering(paper_checker, counter_statement, search_results):
    """Test that only documents above threshold are returned"""
    scored_docs = paper_checker._score_documents(counter_statement, search_results)

    # All returned docs should be above threshold
    assert all(doc.score >= paper_checker.score_threshold for doc in scored_docs)


def test_score_explanation(paper_checker):
    """Test score explanation generation"""
    document = {
        "id": 1,
        "title": "Test Study on GLP-1",
        "abstract": "...",
        "authors": ["Smith J"]
    }

    explanation = paper_checker._get_score_explanation(
        score=5,
        document=document,
        question="Does this support GLP-1?"
    )

    assert len(explanation) > 0
    assert "relevant" in explanation.lower()
```

## Performance Considerations

### Expected Performance

- **Per-document scoring**: ~1-2 seconds with Ollama
- **Total for 50 documents**: ~50-100 seconds (serial)
- **Total for 50 documents**: ~10-20 seconds (batch optimized)

### Optimization Strategies

1. **Batch Processing**: Score documents in parallel where possible
2. **Early Stopping**: If enough high-scoring documents found, stop early
3. **Caching**: Cache scoring results for identical questions
4. **Model Selection**: Use faster model (e.g., medgemma4B) for scoring

### Configuration Option

Add to `~/.bmlibrarian/config.json`:

```json
{
  "paper_checker": {
    "scoring": {
      "model": "medgemma4B_it_q8:latest",  // Faster model for scoring
      "threshold": 3.0,
      "batch_size": 20,
      "early_stop_count": 20  // Stop after finding 20 high-scoring docs
    }
  }
}
```

## Success Criteria

- [ ] Document scoring integration complete
- [ ] Scoring question properly framed for counter-evidence
- [ ] Document fetching efficient (batch query)
- [ ] Threshold filtering working correctly
- [ ] Provenance preserved in ScoredDocument objects
- [ ] Sorting by score (descending) implemented
- [ ] Error handling for scoring failures
- [ ] All unit tests passing
- [ ] Performance acceptable (<2 minutes for 50 documents)

## Next Steps

After completing this step, proceed to:
- **Step 8**: Citation Extraction Integration (08_CITATION_EXTRACTION.md)
- Adapt existing CitationFinderAgent for counter-evidence citations
