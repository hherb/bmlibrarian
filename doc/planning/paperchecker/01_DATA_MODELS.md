# Step 1: Data Models Design and Implementation

## Context

This is the first implementation step for PaperChecker. The architecture overview (00_ARCHITECTURE_OVERVIEW.md) has been defined. We now need to create the foundational data structures that will be used throughout the system.

## Objective

Create type-safe, well-documented dataclasses that represent every stage of the PaperChecker workflow. These models will be the backbone of the entire system, ensuring consistent data flow and type checking.

## Requirements

- Python >=3.12
- dataclasses module
- typing module
- Adherence to BMLibrarian naming conventions

## Implementation Location

Create new file: `src/bmlibrarian/paperchecker/data_models.py`

## Data Models to Implement

### 1. Statement
```python
@dataclass
class Statement:
    """Extracted core statement from abstract

    Represents a single extractedresearch claim, hypothesis, or finding
    from the original abstract being fact-checked.
    """
    text: str  # The extracted statement
    context: str  # Surrounding sentences for context
    statement_type: str  # "hypothesis", "finding", "conclusion"
    confidence: float  # Extraction confidence (0.0-1.0)
    statement_order: int  # Position in original abstract (1, 2, etc.)

    def __post_init__(self):
        """Validate statement fields"""
        assert 0.0 <= self.confidence <= 1.0, "Confidence must be 0.0-1.0"
        assert self.statement_type in ["hypothesis", "finding", "conclusion"], \
            "Invalid statement type"
        assert self.statement_order >= 1, "Order must be >= 1"
```

### 2. CounterStatement
```python
@dataclass
class CounterStatement:
    """Negated statement with search materials

    Represents the counter-claim to the original statement, along with
    generated materials (HyDE abstracts, keywords) for finding supporting
    evidence.
    """
    original_statement: Statement
    negated_text: str  # The counter-claim
    hyde_abstracts: List[str]  # Hypothetical abstracts (usually 2)
    keywords: List[str]  # Search keywords (up to 10)
    generation_metadata: Dict[str, Any]  # Model, temperature, etc.

    def __post_init__(self):
        """Validate counter-statement fields"""
        assert len(self.negated_text.strip()) > 0, "Negated text cannot be empty"
        assert len(self.hyde_abstracts) > 0, "Must have at least one HyDE abstract"
        assert len(self.keywords) > 0, "Must have at least one keyword"
```

### 3. SearchResults
```python
@dataclass
class SearchResults:
    """Multi-strategy search results with provenance tracking

    Captures results from three parallel search strategies (semantic, HyDE,
    keyword) and maintains provenance metadata showing which strategy found
    each document.
    """
    semantic_docs: List[int]  # Document IDs from semantic search
    hyde_docs: List[int]  # Document IDs from HyDE search
    keyword_docs: List[int]  # Document IDs from keyword search
    deduplicated_docs: List[int]  # Unique document IDs
    provenance: Dict[int, List[str]]  # doc_id → ["semantic", "hyde", "keyword"]
    search_metadata: Dict[str, Any]  # Timing, limits, etc.

    def __post_init__(self):
        """Validate and compute provenance"""
        # Verify all deduplicated docs are in provenance
        assert set(self.deduplicated_docs) == set(self.provenance.keys()), \
            "Provenance must include all deduplicated docs"

        # Verify provenance values are valid
        valid_strategies = {"semantic", "hyde", "keyword"}
        for doc_id, strategies in self.provenance.items():
            assert set(strategies).issubset(valid_strategies), \
                f"Invalid strategy for doc {doc_id}"

    @classmethod
    def from_strategy_results(cls, semantic: List[int], hyde: List[int],
                             keyword: List[int], metadata: Dict = None):
        """Factory method to create SearchResults from individual strategies"""
        deduplicated = list(set(semantic + hyde + keyword))
        provenance = {}
        for doc_id in deduplicated:
            strategies = []
            if doc_id in semantic:
                strategies.append("semantic")
            if doc_id in hyde:
                strategies.append("hyde")
            if doc_id in keyword:
                strategies.append("keyword")
            provenance[doc_id] = strategies

        return cls(
            semantic_docs=semantic,
            hyde_docs=hyde,
            keyword_docs=keyword,
            deduplicated_docs=deduplicated,
            provenance=provenance,
            search_metadata=metadata or {}
        )
```

### 4. ScoredDocument
```python
@dataclass
class ScoredDocument:
    """Document with relevance score for counter-statement support

    Represents a document scored by DocumentScoringAgent for its usefulness
    in supporting the counter-statement.
    """
    doc_id: int  # Database document ID
    document: Dict[str, Any]  # Full document data (title, abstract, etc.)
    score: int  # Relevance score (1-5)
    explanation: str  # Why this score was assigned
    supports_counter: bool  # True if score >= threshold
    found_by: List[str]  # Search strategies that found this doc

    def __post_init__(self):
        """Validate scored document fields"""
        assert 1 <= self.score <= 5, "Score must be 1-5"
        assert self.doc_id > 0, "Document ID must be positive"
        valid_strategies = {"semantic", "hyde", "keyword"}
        assert set(self.found_by).issubset(valid_strategies), \
            "Invalid search strategy in found_by"
```

### 5. ExtractedCitation
```python
@dataclass
class ExtractedCitation:
    """Citation passage supporting counter-statement

    Represents a specific passage extracted from a document that supports
    the counter-claim, with full metadata for reference formatting.
    """
    doc_id: int  # Database document ID
    passage: str  # Extracted text passage
    relevance_score: int  # Document's overall relevance score
    full_citation: str  # Formatted reference (AMA style)
    metadata: Dict[str, Any]  # authors, year, journal, pmid, doi, etc.
    citation_order: int  # Position in counter-report

    def __post_init__(self):
        """Validate citation fields"""
        assert len(self.passage.strip()) > 0, "Passage cannot be empty"
        assert 1 <= self.relevance_score <= 5, "Score must be 1-5"
        assert self.citation_order >= 1, "Order must be >= 1"

    def to_markdown_reference(self) -> str:
        """Format as markdown reference with link if available"""
        ref = f"{self.citation_order}. {self.full_citation}"
        if "pmid" in self.metadata and self.metadata["pmid"]:
            ref += f" [PMID: {self.metadata['pmid']}]"
        if "doi" in self.metadata and self.metadata["doi"]:
            ref += f" [DOI: {self.metadata['doi']}]"
        return ref
```

### 6. CounterReport
```python
@dataclass
class CounterReport:
    """Synthesized counter-evidence report

    Contains the prose summary of counter-evidence, all citations, and
    statistics about the search and scoring process.
    """
    summary: str  # Markdown-formatted prose report
    num_citations: int  # Total citations included
    citations: List[ExtractedCitation]  # All citations in order
    search_stats: Dict[str, Any]  # Documents found, scored, cited
    generation_metadata: Dict[str, Any]  # Model, timestamp, etc.

    def __post_init__(self):
        """Validate counter-report fields"""
        assert len(self.summary.strip()) > 0, "Summary cannot be empty"
        assert self.num_citations == len(self.citations), \
            "num_citations must match citations list length"
        assert all(isinstance(c, ExtractedCitation) for c in self.citations), \
            "All citations must be ExtractedCitation instances"

    def to_markdown(self) -> str:
        """Generate complete markdown report with references"""
        md = f"## Counter-Evidence Summary\n\n{self.summary}\n\n"
        md += f"## References\n\n"
        for citation in self.citations:
            md += f"{citation.to_markdown_reference()}\n"
        md += f"\n---\n"
        md += f"*Search statistics: {self.search_stats['documents_found']} found, "
        md += f"{self.search_stats['documents_scored']} scored, "
        md += f"{self.num_citations} cited*\n"
        return md
```

### 7. Verdict
```python
@dataclass
class Verdict:
    """Final verdict on original statement

    Represents the analysis of whether the counter-evidence supports,
    contradicts, or is undecided about the original statement.
    """
    verdict: str  # "supports", "contradicts", "undecided"
    rationale: str  # 2-3 sentence explanation
    confidence: str  # "high", "medium", "low"
    counter_report: CounterReport  # The evidence basis
    analysis_metadata: Dict[str, Any]  # Model, timestamp, etc.

    def __post_init__(self):
        """Validate verdict fields"""
        assert self.verdict in ["supports", "contradicts", "undecided"], \
            "Invalid verdict value"
        assert self.confidence in ["high", "medium", "low"], \
            "Invalid confidence value"
        assert len(self.rationale.strip()) > 0, "Rationale cannot be empty"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "verdict": self.verdict,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "num_citations": self.counter_report.num_citations,
            "search_stats": self.counter_report.search_stats
        }
```

### 8. PaperCheckResult
```python
@dataclass
class PaperCheckResult:
    """Complete result for one abstract check

    Top-level container for all results from checking a single abstract.
    Includes all intermediate results and final verdicts.
    """
    original_abstract: str  # The abstract being checked
    source_metadata: Dict[str, Any]  # PMID, DOI, title, etc.
    statements: List[Statement]  # Extracted statements
    counter_statements: List[CounterStatement]  # Counter-claims
    search_results: List[SearchResults]  # One per statement
    scored_documents: List[List[ScoredDocument]]  # One list per statement
    counter_reports: List[CounterReport]  # One per statement
    verdicts: List[Verdict]  # One per statement
    overall_assessment: str  # Aggregate verdict
    processing_metadata: Dict[str, Any]  # Timestamps, models, config

    def __post_init__(self):
        """Validate result consistency"""
        n = len(self.statements)
        assert len(self.counter_statements) == n, "Mismatched counter_statements"
        assert len(self.search_results) == n, "Mismatched search_results"
        assert len(self.scored_documents) == n, "Mismatched scored_documents"
        assert len(self.counter_reports) == n, "Mismatched counter_reports"
        assert len(self.verdicts) == n, "Mismatched verdicts"

    def to_json_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export"""
        return {
            "original_abstract": self.original_abstract,
            "source_metadata": self.source_metadata,
            "statements": [
                {
                    "text": s.text,
                    "type": s.statement_type,
                    "confidence": s.confidence
                }
                for s in self.statements
            ],
            "results": [
                {
                    "statement": s.text,
                    "counter_statement": cs.negated_text,
                    "search_stats": {
                        "semantic": len(sr.semantic_docs),
                        "hyde": len(sr.hyde_docs),
                        "keyword": len(sr.keyword_docs),
                        "deduplicated": len(sr.deduplicated_docs)
                    },
                    "scoring_stats": {
                        "total_scored": len(sd),
                        "above_threshold": sum(1 for d in sd if d.supports_counter)
                    },
                    "counter_report": cr.to_markdown(),
                    "verdict": v.to_dict()
                }
                for s, cs, sr, sd, cr, v in zip(
                    self.statements,
                    self.counter_statements,
                    self.search_results,
                    self.scored_documents,
                    self.counter_reports,
                    self.verdicts
                )
            ],
            "overall_assessment": self.overall_assessment,
            "metadata": self.processing_metadata
        }

    def to_markdown_report(self) -> str:
        """Generate human-readable markdown report"""
        md = f"# PaperChecker Report\n\n"
        md += f"## Original Abstract\n\n{self.original_abstract}\n\n"

        if self.source_metadata.get("title"):
            md += f"**Title:** {self.source_metadata['title']}\n\n"

        md += f"## Analysis Results\n\n"

        for i, (stmt, verdict) in enumerate(zip(self.statements, self.verdicts), 1):
            md += f"### Statement {i}\n\n"
            md += f"**Claim:** {stmt.text}\n\n"
            md += f"**Verdict:** {verdict.verdict.upper()}\n\n"
            md += f"**Confidence:** {verdict.confidence}\n\n"
            md += f"**Rationale:** {verdict.rationale}\n\n"
            md += verdict.counter_report.to_markdown()
            md += "\n\n"

        md += f"## Overall Assessment\n\n{self.overall_assessment}\n"

        return md
```

## Implementation Steps

1. **Create module structure**:
   ```bash
   mkdir -p src/bmlibrarian/paperchecker
   touch src/bmlibrarian/paperchecker/__init__.py
   ```

2. **Create data_models.py** with all dataclasses above

3. **Add docstrings** for every class and method

4. **Add type hints** throughout (use `from __future__ import annotations` if needed)

5. **Add validation** in `__post_init__` methods

6. **Create helper methods**:
   - Factory methods for convenient construction
   - Conversion methods (to_dict, to_json, to_markdown)
   - Validation methods

7. **Update module exports**:
   ```python
   # src/bmlibrarian/paperchecker/__init__.py
   from .data_models import (
       Statement,
       CounterStatement,
       SearchResults,
       ScoredDocument,
       ExtractedCitation,
       CounterReport,
       Verdict,
       PaperCheckResult
   )

   __all__ = [
       "Statement",
       "CounterStatement",
       "SearchResults",
       "ScoredDocument",
       "ExtractedCitation",
       "CounterReport",
       "Verdict",
       "PaperCheckResult"
   ]
   ```

## Testing Criteria

Create `tests/test_paperchecker_data_models.py`:

1. **Test Statement validation**:
   - Valid statement creation
   - Invalid confidence (< 0 or > 1) raises error
   - Invalid statement_type raises error
   - Invalid order (< 1) raises error

2. **Test CounterStatement validation**:
   - Valid counter-statement creation
   - Empty negated_text raises error
   - Empty hyde_abstracts raises error
   - Empty keywords raises error

3. **Test SearchResults**:
   - Factory method creates correct provenance
   - Provenance matches deduplicated docs
   - Invalid strategies raise errors

4. **Test ScoredDocument validation**:
   - Valid scores (1-5) accepted
   - Invalid scores raise errors
   - Invalid doc_id raises error

5. **Test ExtractedCitation**:
   - Valid citation creation
   - to_markdown_reference() formats correctly
   - Handles missing PMID/DOI gracefully

6. **Test CounterReport**:
   - num_citations matches citations list length
   - to_markdown() generates valid markdown

7. **Test Verdict validation**:
   - Only valid verdicts accepted
   - Only valid confidence levels accepted
   - to_dict() serializes correctly

8. **Test PaperCheckResult**:
   - Length consistency validation works
   - to_json_dict() generates valid structure
   - to_markdown_report() generates readable output

## Success Criteria

- [ ] All 8 dataclasses implemented with type hints
- [ ] All validation logic in `__post_init__` methods
- [ ] All helper methods (factory, conversion) implemented
- [ ] Comprehensive docstrings for every class
- [ ] Module exports configured correctly
- [ ] All unit tests passing (>95% coverage)
- [ ] No type checking errors with mypy

## Next Steps

After completing this step, proceed to:
- **Step 2**: Database Schema Design (02_DATABASE_SCHEMA.md)
- The data models defined here will inform the database table structure
