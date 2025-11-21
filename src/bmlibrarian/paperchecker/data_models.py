"""
Data models for PaperChecker module.

This module defines type-safe dataclasses for the entire PaperChecker workflow,
from statement extraction through verdict generation. These models ensure
consistent data flow and enable proper type checking throughout the system.

Classes:
    Statement: Extracted research claim from abstract
    CounterStatement: Negated claim with search materials
    SearchResults: Multi-strategy search results with provenance
    ScoredDocument: Document with relevance score
    ExtractedCitation: Citation passage supporting counter-statement
    CounterReport: Synthesized counter-evidence report
    Verdict: Final verdict on original statement
    PaperCheckResult: Complete result for one abstract check

Constants:
    MIN_CONFIDENCE: Minimum confidence value (0.0)
    MAX_CONFIDENCE: Maximum confidence value (1.0)
    MIN_SCORE: Minimum relevance score (1)
    MAX_SCORE: Maximum relevance score (5)
    MIN_ORDER: Minimum statement/citation order (1)
    MIN_DOC_ID: Minimum valid document ID (1)
    VALID_STATEMENT_TYPES: Valid statement type values
    VALID_SEARCH_STRATEGIES: Valid search strategy names
    VALID_VERDICT_VALUES: Valid verdict classifications
    VALID_CONFIDENCE_LEVELS: Valid confidence level labels
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Set

# Validation Constants
MIN_CONFIDENCE: float = 0.0
MAX_CONFIDENCE: float = 1.0
MIN_SCORE: int = 1
MAX_SCORE: int = 5
MIN_ORDER: int = 1
MIN_DOC_ID: int = 1

# Valid Values
VALID_STATEMENT_TYPES: Set[str] = {"hypothesis", "finding", "conclusion"}
VALID_SEARCH_STRATEGIES: Set[str] = {"semantic", "hyde", "keyword"}
VALID_VERDICT_VALUES: Set[str] = {"supports", "contradicts", "undecided"}
VALID_CONFIDENCE_LEVELS: Set[str] = {"high", "medium", "low"}

# Default Values for Search Statistics
DEFAULT_DOCUMENTS_FOUND: int = 0
DEFAULT_DOCUMENTS_SCORED: int = 0


@dataclass
class Statement:
    """Extracted core statement from abstract.

    Represents a single extracted research claim, hypothesis, or finding
    from the original abstract being fact-checked.

    Attributes:
        text: The extracted statement text
        context: Surrounding sentences providing context
        statement_type: Type of statement ("hypothesis", "finding", "conclusion")
        confidence: Extraction confidence (0.0-1.0)
        statement_order: Position in original abstract (1, 2, etc.)
    """

    text: str
    context: str
    statement_type: str
    confidence: float
    statement_order: int

    def __post_init__(self) -> None:
        """Validate statement fields.

        Raises:
            AssertionError: If confidence is outside valid range, statement_type is invalid,
                          or statement_order is less than minimum.
        """
        assert MIN_CONFIDENCE <= self.confidence <= MAX_CONFIDENCE, \
            f"Confidence must be between {MIN_CONFIDENCE} and {MAX_CONFIDENCE}"
        assert self.statement_type in VALID_STATEMENT_TYPES, \
            f"Invalid statement type: {self.statement_type}. Must be one of {VALID_STATEMENT_TYPES}"
        assert self.statement_order >= MIN_ORDER, \
            f"Order must be >= {MIN_ORDER}"


@dataclass
class CounterStatement:
    """Negated statement with search materials.

    Represents the counter-claim to the original statement, along with
    generated materials (HyDE abstracts, keywords) for finding supporting
    evidence.

    Attributes:
        original_statement: The original statement being countered
        negated_text: The counter-claim text
        hyde_abstracts: List of hypothetical abstracts (usually 2)
        keywords: Search keywords (up to 10)
        generation_metadata: Model, temperature, and other generation parameters
    """

    original_statement: Statement
    negated_text: str
    hyde_abstracts: List[str]
    keywords: List[str]
    generation_metadata: Dict[str, Any]

    def __post_init__(self) -> None:
        """Validate counter-statement fields.

        Raises:
            AssertionError: If negated_text is empty, hyde_abstracts list is empty,
                          or keywords list is empty.
        """
        assert len(self.negated_text.strip()) > 0, "Negated text cannot be empty"
        assert len(self.hyde_abstracts) > 0, "Must have at least one HyDE abstract"
        assert len(self.keywords) > 0, "Must have at least one keyword"


@dataclass
class SearchResults:
    """Multi-strategy search results with provenance tracking.

    Captures results from three parallel search strategies (semantic, HyDE,
    keyword) and maintains provenance metadata showing which strategy found
    each document.

    Attributes:
        semantic_docs: Document IDs from semantic search
        hyde_docs: Document IDs from HyDE search
        keyword_docs: Document IDs from keyword search
        deduplicated_docs: Unique document IDs across all strategies
        provenance: Mapping of doc_id to list of strategies that found it
        search_metadata: Timing, limits, and other search parameters
    """

    semantic_docs: List[int]
    hyde_docs: List[int]
    keyword_docs: List[int]
    deduplicated_docs: List[int]
    provenance: Dict[int, List[str]]
    search_metadata: Dict[str, Any]

    def __post_init__(self) -> None:
        """Validate and verify provenance consistency.

        Raises:
            AssertionError: If provenance keys don't match deduplicated_docs or if
                          provenance contains invalid search strategies.
        """
        # Verify all deduplicated docs are in provenance
        assert set(self.deduplicated_docs) == set(self.provenance.keys()), \
            "Provenance must include all deduplicated docs"

        # Verify provenance values are valid
        for doc_id, strategies in self.provenance.items():
            assert set(strategies).issubset(VALID_SEARCH_STRATEGIES), \
                f"Invalid strategy for doc {doc_id}: {strategies}. " \
                f"Must be subset of {VALID_SEARCH_STRATEGIES}"

    @classmethod
    def from_strategy_results(
        cls,
        semantic: List[int],
        hyde: List[int],
        keyword: List[int],
        metadata: Dict[str, Any] | None = None
    ) -> SearchResults:
        """Create SearchResults from individual strategy results.

        Factory method that automatically computes deduplicated documents and
        provenance tracking from the three search strategy results.

        Args:
            semantic: Document IDs from semantic search
            hyde: Document IDs from HyDE search
            keyword: Document IDs from keyword search
            metadata: Optional search metadata

        Returns:
            SearchResults instance with computed provenance
        """
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


@dataclass
class ScoredDocument:
    """Document with relevance score for counter-statement support.

    Represents a document scored by DocumentScoringAgent for its usefulness
    in supporting the counter-statement.

    Attributes:
        doc_id: Database document ID
        document: Full document data (title, abstract, metadata)
        score: Relevance score (1-5)
        explanation: Explanation for the assigned score
        supports_counter: True if score >= threshold
        found_by: List of search strategies that found this document
    """

    doc_id: int
    document: Dict[str, Any]
    score: int
    explanation: str
    supports_counter: bool
    found_by: List[str]

    def __post_init__(self) -> None:
        """Validate scored document fields.

        Raises:
            AssertionError: If score is outside valid range, doc_id is invalid,
                          or found_by contains invalid search strategies.
        """
        assert MIN_SCORE <= self.score <= MAX_SCORE, \
            f"Score must be between {MIN_SCORE} and {MAX_SCORE}, got {self.score}"
        assert self.doc_id >= MIN_DOC_ID, \
            f"Document ID must be >= {MIN_DOC_ID}"
        assert set(self.found_by).issubset(VALID_SEARCH_STRATEGIES), \
            f"Invalid search strategy in found_by: {self.found_by}. " \
            f"Must be subset of {VALID_SEARCH_STRATEGIES}"


@dataclass
class ExtractedCitation:
    """Citation passage supporting counter-statement.

    Represents a specific passage extracted from a document that supports
    the counter-claim, with full metadata for reference formatting.

    Attributes:
        doc_id: Database document ID
        passage: Extracted text passage
        relevance_score: Document's overall relevance score
        full_citation: Formatted reference (AMA style)
        metadata: Authors, year, journal, PMID, DOI, etc.
        citation_order: Position in counter-report (1, 2, etc.)
    """

    doc_id: int
    passage: str
    relevance_score: int
    full_citation: str
    metadata: Dict[str, Any]
    citation_order: int

    def __post_init__(self) -> None:
        """Validate citation fields.

        Raises:
            AssertionError: If passage is empty, relevance_score is outside valid range,
                          or citation_order is less than minimum.
        """
        assert len(self.passage.strip()) > 0, "Passage cannot be empty"
        assert MIN_SCORE <= self.relevance_score <= MAX_SCORE, \
            f"Score must be between {MIN_SCORE} and {MAX_SCORE}, got {self.relevance_score}"
        assert self.citation_order >= MIN_ORDER, \
            f"Order must be >= {MIN_ORDER}"

    def to_markdown_reference(self) -> str:
        """Format citation as markdown reference with links.

        Returns:
            Markdown-formatted reference string with PMID/DOI links if available
        """
        ref = f"{self.citation_order}. {self.full_citation}"
        if "pmid" in self.metadata and self.metadata["pmid"]:
            ref += f" [PMID: {self.metadata['pmid']}]"
        if "doi" in self.metadata and self.metadata["doi"]:
            ref += f" [DOI: {self.metadata['doi']}]"
        return ref


@dataclass
class CounterReport:
    """Synthesized counter-evidence report.

    Contains the prose summary of counter-evidence, all citations, and
    statistics about the search and scoring process.

    Attributes:
        summary: Markdown-formatted prose report
        num_citations: Total citations included
        citations: All citations in order
        search_stats: Documents found, scored, cited
        generation_metadata: Model, timestamp, and generation parameters
    """

    summary: str
    num_citations: int
    citations: List[ExtractedCitation]
    search_stats: Dict[str, Any]
    generation_metadata: Dict[str, Any]

    def __post_init__(self) -> None:
        """Validate counter-report fields.

        Raises:
            AssertionError: If summary is empty, num_citations doesn't match citations list
                          length, or citations contains non-ExtractedCitation objects.
        """
        assert len(self.summary.strip()) > 0, "Summary cannot be empty"
        assert self.num_citations == len(self.citations), \
            f"num_citations ({self.num_citations}) must match citations list length ({len(self.citations)})"
        assert all(isinstance(c, ExtractedCitation) for c in self.citations), \
            "All citations must be ExtractedCitation instances"

    def to_markdown(self) -> str:
        """Generate complete markdown report with references.

        Returns:
            Markdown-formatted report with summary, references, and statistics
        """
        md = f"## Counter-Evidence Summary\n\n{self.summary}\n\n"
        md += f"## References\n\n"
        for citation in self.citations:
            md += f"{citation.to_markdown_reference()}\n"
        md += f"\n---\n"
        docs_found = self.search_stats.get('documents_found', DEFAULT_DOCUMENTS_FOUND)
        docs_scored = self.search_stats.get('documents_scored', DEFAULT_DOCUMENTS_SCORED)
        md += f"*Search statistics: {docs_found} found, "
        md += f"{docs_scored} scored, "
        md += f"{self.num_citations} cited*\n"
        return md


@dataclass
class Verdict:
    """Final verdict on original statement.

    Represents the analysis of whether the counter-evidence supports,
    contradicts, or is undecided about the original statement.

    Attributes:
        verdict: Classification ("supports", "contradicts", "undecided")
        rationale: 2-3 sentence explanation
        confidence: Confidence level ("high", "medium", "low")
        counter_report: The evidence basis for this verdict
        analysis_metadata: Model, timestamp, and analysis parameters
    """

    verdict: str
    rationale: str
    confidence: str
    counter_report: CounterReport
    analysis_metadata: Dict[str, Any]

    def __post_init__(self) -> None:
        """Validate verdict fields.

        Raises:
            AssertionError: If verdict value is invalid, confidence level is invalid,
                          or rationale is empty.
        """
        assert self.verdict in VALID_VERDICT_VALUES, \
            f"Invalid verdict value: {self.verdict}. Must be one of {VALID_VERDICT_VALUES}"
        assert self.confidence in VALID_CONFIDENCE_LEVELS, \
            f"Invalid confidence value: {self.confidence}. Must be one of {VALID_CONFIDENCE_LEVELS}"
        assert len(self.rationale.strip()) > 0, "Rationale cannot be empty"

    def to_dict(self) -> Dict[str, Any]:
        """Convert verdict to dictionary for JSON serialization.

        Returns:
            Dictionary with verdict, rationale, confidence, and statistics
        """
        return {
            "verdict": self.verdict,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "num_citations": self.counter_report.num_citations,
            "search_stats": self.counter_report.search_stats
        }


@dataclass
class PaperCheckResult:
    """Complete result for one abstract check.

    Top-level container for all results from checking a single abstract.
    Includes all intermediate results and final verdicts for each extracted
    statement.

    Attributes:
        original_abstract: The abstract being checked
        source_metadata: PMID, DOI, title, and other source information
        statements: Extracted statements from abstract
        counter_statements: Counter-claims for each statement
        search_results: Multi-strategy search results (one per statement)
        scored_documents: Scored documents (one list per statement)
        counter_reports: Counter-evidence reports (one per statement)
        verdicts: Final verdicts (one per statement)
        overall_assessment: Aggregate verdict across all statements
        processing_metadata: Timestamps, models, configuration
    """

    original_abstract: str
    source_metadata: Dict[str, Any]
    statements: List[Statement]
    counter_statements: List[CounterStatement]
    search_results: List[SearchResults]
    scored_documents: List[List[ScoredDocument]]
    counter_reports: List[CounterReport]
    verdicts: List[Verdict]
    overall_assessment: str
    processing_metadata: Dict[str, Any]

    def __post_init__(self) -> None:
        """Validate result consistency across all components.

        Raises:
            AssertionError: If any result component lists have mismatched lengths
                          compared to the number of statements.
        """
        n = len(self.statements)
        assert len(self.counter_statements) == n, \
            f"Mismatched counter_statements: {len(self.counter_statements)} vs {n}"
        assert len(self.search_results) == n, \
            f"Mismatched search_results: {len(self.search_results)} vs {n}"
        assert len(self.scored_documents) == n, \
            f"Mismatched scored_documents: {len(self.scored_documents)} vs {n}"
        assert len(self.counter_reports) == n, \
            f"Mismatched counter_reports: {len(self.counter_reports)} vs {n}"
        assert len(self.verdicts) == n, \
            f"Mismatched verdicts: {len(self.verdicts)} vs {n}"

    def to_json_dict(self) -> Dict[str, Any]:
        """Convert complete result to dictionary for JSON export.

        Returns:
            Dictionary with all results structured for JSON serialization
        """
        return {
            "original_abstract": self.original_abstract,
            "source_metadata": self.source_metadata,
            "statements": [
                {
                    "text": s.text,
                    "type": s.statement_type,
                    "confidence": s.confidence,
                    "order": s.statement_order
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
        """Generate human-readable markdown report.

        Returns:
            Complete markdown report with abstract, analysis, and verdicts
        """
        md = f"# PaperChecker Report\n\n"
        md += f"## Original Abstract\n\n{self.original_abstract}\n\n"

        if self.source_metadata.get("title"):
            md += f"**Title:** {self.source_metadata['title']}\n\n"
        if self.source_metadata.get("pmid"):
            md += f"**PMID:** {self.source_metadata['pmid']}\n\n"
        if self.source_metadata.get("doi"):
            md += f"**DOI:** {self.source_metadata['doi']}\n\n"

        md += f"## Analysis Results\n\n"

        for i, (stmt, verdict) in enumerate(zip(self.statements, self.verdicts), 1):
            md += f"### Statement {i}\n\n"
            md += f"**Claim:** {stmt.text}\n\n"
            md += f"**Type:** {stmt.statement_type}\n\n"
            md += f"**Verdict:** {verdict.verdict.upper()}\n\n"
            md += f"**Confidence:** {verdict.confidence}\n\n"
            md += f"**Rationale:** {verdict.rationale}\n\n"
            md += verdict.counter_report.to_markdown()
            md += "\n\n"

        md += f"## Overall Assessment\n\n{self.overall_assessment}\n"

        return md
