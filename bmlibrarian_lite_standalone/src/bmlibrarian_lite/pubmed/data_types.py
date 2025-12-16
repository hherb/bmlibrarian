"""
Type-safe dataclasses for PubMed API Search module.

This module defines all data structures used throughout the PubMed search system,
ensuring type safety and clear interfaces between components.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid


class PublicationType(Enum):
    """PubMed publication type filters for search refinement."""

    CLINICAL_TRIAL = "Clinical Trial"
    RCT = "Randomized Controlled Trial"
    META_ANALYSIS = "Meta-Analysis"
    SYSTEMATIC_REVIEW = "Systematic Review"
    REVIEW = "Review"
    CASE_REPORT = "Case Reports"
    GUIDELINE = "Guideline"
    OBSERVATIONAL = "Observational Study"

    def to_pubmed_filter(self) -> str:
        """Convert to PubMed search filter syntax."""
        return f'"{self.value}"[Publication Type]'


class SearchStatus(Enum):
    """Status of a PubMed API search operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MeSHTerm:
    """
    Represents a MeSH (Medical Subject Headings) term.

    Attributes:
        descriptor_ui: Unique identifier (e.g., "D006331")
        descriptor_name: Official MeSH term name
        tree_numbers: Hierarchical tree location(s)
        entry_terms: Synonyms and related terms
        scope_note: Definition/description
        is_valid: Whether term was validated against official MeSH
    """

    descriptor_ui: str
    descriptor_name: str
    tree_numbers: List[str] = field(default_factory=list)
    entry_terms: List[str] = field(default_factory=list)
    scope_note: Optional[str] = None
    is_valid: bool = True

    def to_pubmed_syntax(self, explode: bool = True) -> str:
        """
        Convert to PubMed query syntax.

        Args:
            explode: If True, include narrower terms (default MeSH behavior)

        Returns:
            PubMed-formatted MeSH term query
        """
        if explode:
            return f'"{self.descriptor_name}"[MeSH Terms]'
        else:
            return f'"{self.descriptor_name}"[MeSH Terms:noexp]'


@dataclass
class QueryConcept:
    """
    A single concept extracted from a research question.

    Represents one semantic unit in the query, with its associated
    MeSH terms and free-text keywords for comprehensive searching.

    Attributes:
        name: Human-readable concept name
        mesh_terms: Validated MeSH terms for this concept
        keywords: Free-text keywords for title/abstract search
        synonyms: Alternative terms/spellings
        is_pico_component: If part of PICO framework (P/I/C/O)
        pico_role: Which PICO component (population, intervention, etc.)
    """

    name: str
    mesh_terms: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    synonyms: List[str] = field(default_factory=list)
    is_pico_component: bool = False
    pico_role: Optional[str] = None  # "population", "intervention", "comparison", "outcome"

    def to_pubmed_clause(self, mesh_explosion: bool = True) -> str:
        """
        Convert concept to a PubMed query clause.

        Combines MeSH terms and keywords with OR, using appropriate field tags.

        Args:
            mesh_explosion: Include narrower MeSH terms

        Returns:
            PubMed-formatted query clause for this concept
        """
        parts = []

        # Add MeSH terms
        for mesh in self.mesh_terms:
            if mesh_explosion:
                parts.append(f'"{mesh}"[MeSH Terms]')
            else:
                parts.append(f'"{mesh}"[MeSH Terms:noexp]')

        # Add keywords with title/abstract field tag
        all_keywords = self.keywords + self.synonyms
        for kw in all_keywords:
            # Handle multi-word phrases
            if ' ' in kw:
                parts.append(f'"{kw}"[Title/Abstract]')
            else:
                parts.append(f'{kw}[Title/Abstract]')

        if not parts:
            return ""

        # Combine with OR
        return f"({' OR '.join(parts)})"


@dataclass
class DateRange:
    """
    Date range for filtering PubMed search results.

    Attributes:
        start_date: Beginning of date range (inclusive)
        end_date: End of date range (inclusive)
        date_type: Type of date to filter ("pdat" for publication, "edat" for entry)
    """

    start_date: Optional[date] = None
    end_date: Optional[date] = None
    date_type: str = "pdat"  # publication date

    def to_pubmed_params(self) -> Dict[str, str]:
        """Convert to E-utilities URL parameters."""
        params = {}
        if self.start_date:
            params["mindate"] = self.start_date.strftime("%Y/%m/%d")
        if self.end_date:
            params["maxdate"] = self.end_date.strftime("%Y/%m/%d")
        if self.start_date or self.end_date:
            params["datetype"] = self.date_type
        return params


@dataclass
class PubMedQuery:
    """
    Structured PubMed query ready for API submission.

    Contains the original question, extracted concepts, and the final
    query string formatted for PubMed's E-utilities API.

    Attributes:
        original_question: The natural language research question
        query_string: Final PubMed-formatted query string
        concepts: Extracted and structured query concepts
        publication_types: Filter by publication type(s)
        date_range: Filter by date range
        humans_only: Filter to human studies only
        has_abstract: Filter to articles with abstracts
        free_full_text: Filter to free full text only
        language: Filter by language (e.g., "english")
        generation_model: LLM model used to generate this query
        confidence_score: LLM's confidence in query quality (0-1)
    """

    original_question: str
    query_string: str
    concepts: List[QueryConcept] = field(default_factory=list)
    publication_types: List[PublicationType] = field(default_factory=list)
    date_range: Optional[DateRange] = None
    humans_only: bool = False
    has_abstract: bool = False
    free_full_text: bool = False
    language: Optional[str] = None
    generation_model: Optional[str] = None
    confidence_score: Optional[float] = None

    def to_url_params(self) -> Dict[str, str]:
        """
        Convert to E-utilities URL parameters.

        Returns:
            Dictionary of URL parameters for esearch
        """
        params = {
            "db": "pubmed",
            "term": self.query_string,
            "retmode": "json",
        }

        # Add date range parameters
        if self.date_range:
            params.update(self.date_range.to_pubmed_params())

        return params

    def get_search_summary(self) -> str:
        """
        Get human-readable summary of the query.

        Returns:
            Formatted summary string
        """
        lines = [
            f"Original Question: {self.original_question}",
            f"PubMed Query: {self.query_string}",
            f"Concepts: {len(self.concepts)}",
        ]

        if self.publication_types:
            types = ", ".join(pt.value for pt in self.publication_types)
            lines.append(f"Publication Types: {types}")

        if self.date_range and (self.date_range.start_date or self.date_range.end_date):
            start = self.date_range.start_date or "any"
            end = self.date_range.end_date or "present"
            lines.append(f"Date Range: {start} to {end}")

        filters = []
        if self.humans_only:
            filters.append("humans only")
        if self.has_abstract:
            filters.append("has abstract")
        if self.free_full_text:
            filters.append("free full text")
        if self.language:
            filters.append(f"language: {self.language}")

        if filters:
            lines.append(f"Filters: {', '.join(filters)}")

        return "\n".join(lines)


@dataclass
class SearchResult:
    """
    Result from a PubMed API search operation.

    Contains the query used, result counts, and list of PMIDs found.

    Attributes:
        query: The PubMedQuery that was executed
        total_count: Total number of matching articles in PubMed
        retrieved_count: Number of PMIDs actually retrieved
        pmids: List of PubMed IDs found
        search_time_seconds: Time taken for the search
        web_env: WebEnv for history server (for large result sets)
        query_key: QueryKey for history server
    """

    query: PubMedQuery
    total_count: int
    retrieved_count: int
    pmids: List[str] = field(default_factory=list)
    search_time_seconds: float = 0.0
    web_env: Optional[str] = None
    query_key: Optional[str] = None

    @property
    def has_more_results(self) -> bool:
        """Check if there are more results available than retrieved."""
        return self.total_count > self.retrieved_count


@dataclass
class ArticleMetadata:
    """
    Metadata for a PubMed article.

    Attributes:
        pmid: PubMed ID
        doi: Digital Object Identifier
        title: Article title
        abstract: Article abstract (Markdown formatted)
        authors: List of author names
        publication: Journal/publication name
        publication_date: Date of publication
        url: PubMed URL
        mesh_terms: MeSH terms assigned to article
        keywords: Author-provided keywords
        pmc_id: PubMed Central ID (if available)
        relevance_rank: Position in search results (if applicable)
    """

    pmid: str
    title: str
    abstract: str = ""
    doi: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    publication: str = "PubMed"
    publication_date: Optional[str] = None
    url: Optional[str] = None
    mesh_terms: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    pmc_id: Optional[str] = None
    relevance_rank: Optional[int] = None

    def __post_init__(self) -> None:
        """Set URL if not provided."""
        if not self.url and self.pmid:
            self.url = f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"


@dataclass
class ImportResult:
    """
    Result of importing articles into the local database.

    Attributes:
        total_found: Total articles found in search
        articles_fetched: Articles successfully fetched from PubMed
        articles_imported: New articles imported to database
        articles_skipped: Articles skipped (already in database)
        articles_failed: Articles that failed to import
        imported_document_ids: Database IDs of newly imported documents
        skipped_pmids: PMIDs of articles that were skipped
        failed_pmids: PMIDs of articles that failed import
        errors: List of error messages
    """

    total_found: int = 0
    articles_fetched: int = 0
    articles_imported: int = 0
    articles_skipped: int = 0
    articles_failed: int = 0
    imported_document_ids: List[int] = field(default_factory=list)
    skipped_pmids: List[str] = field(default_factory=list)
    failed_pmids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def get_summary(self) -> str:
        """Get human-readable summary of import results."""
        lines = [
            f"Total found: {self.total_found}",
            f"Fetched: {self.articles_fetched}",
            f"Imported: {self.articles_imported}",
            f"Skipped (existing): {self.articles_skipped}",
            f"Failed: {self.articles_failed}",
        ]

        if self.errors:
            lines.append(f"Errors: {len(self.errors)}")

        return "\n".join(lines)


@dataclass
class SearchSession:
    """
    Tracks a complete PubMed API search session for provenance.

    Records all queries executed, articles found/imported, and provides
    audit trail for reproducibility.

    Attributes:
        session_id: Unique identifier for this search session
        research_question: Original natural language question
        queries_executed: All PubMed queries executed
        import_result: Results of database import
        full_texts_downloaded: Count of PDFs downloaded
        created_at: Session creation timestamp
        completed_at: Session completion timestamp
        status: Current status of the session
        user_id: Optional user ID for tracking
    """

    research_question: str
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    queries_executed: List[PubMedQuery] = field(default_factory=list)
    import_result: Optional[ImportResult] = None
    full_texts_downloaded: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    status: SearchStatus = SearchStatus.PENDING
    user_id: Optional[int] = None

    def mark_completed(self) -> None:
        """Mark session as completed."""
        self.status = SearchStatus.COMPLETED
        self.completed_at = datetime.now()

    def mark_failed(self, error: Optional[str] = None) -> None:
        """Mark session as failed."""
        self.status = SearchStatus.FAILED
        self.completed_at = datetime.now()
        if error and self.import_result:
            self.import_result.errors.append(error)


@dataclass
class QueryConversionResult:
    """
    Result of converting a natural language question to PubMed query.

    Includes the query, alternatives, and metadata about the conversion.

    Attributes:
        primary_query: Main recommended PubMed query
        alternative_queries: Alternative formulations
        mesh_terms_found: All MeSH terms identified
        mesh_terms_validated: MeSH terms that passed validation
        mesh_terms_invalid: MeSH terms that failed validation
        concepts_extracted: Semantic concepts from question
        warnings: Any warnings during conversion
        llm_response_raw: Raw LLM response (for debugging)
    """

    primary_query: PubMedQuery
    alternative_queries: List[PubMedQuery] = field(default_factory=list)
    mesh_terms_found: List[str] = field(default_factory=list)
    mesh_terms_validated: List[str] = field(default_factory=list)
    mesh_terms_invalid: List[str] = field(default_factory=list)
    concepts_extracted: List[QueryConcept] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    llm_response_raw: Optional[str] = None

    def get_validation_summary(self) -> str:
        """Get summary of MeSH validation results."""
        total = len(self.mesh_terms_found)
        valid = len(self.mesh_terms_validated)
        invalid = len(self.mesh_terms_invalid)

        if total == 0:
            return "No MeSH terms identified"

        return f"MeSH validation: {valid}/{total} valid, {invalid} invalid"
