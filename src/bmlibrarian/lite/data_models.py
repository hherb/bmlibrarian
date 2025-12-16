"""
Data models for BMLibrarian Lite.

Type-safe dataclasses for documents, chunks, search sessions,
citations, and review checkpoints. These models are used throughout
the lite module for consistent data handling.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .quality.data_models import QualityAssessment


class DocumentSource(Enum):
    """Source of a document."""

    PUBMED = "pubmed"
    LOCAL_PDF = "local_pdf"
    LOCAL_TEXT = "local_text"


@dataclass
class LiteDocument:
    """
    Document representation for Lite version.

    Stores essential document metadata and abstract text.
    Used for both PubMed articles and local documents.

    Attributes:
        id: Unique identifier (e.g., "pmid-12345" or UUID)
        title: Document title
        abstract: Document abstract text
        authors: List of author names
        year: Publication year
        journal: Journal name
        doi: Digital Object Identifier
        pmid: PubMed ID
        pmc_id: PubMed Central ID (for open access articles)
        url: URL to the article
        mesh_terms: MeSH terms associated with the article
        source: Source of the document (PubMed, local PDF, etc.)
        metadata: Additional custom metadata
    """

    id: str  # Unique identifier (e.g., "pmid-12345" or UUID)
    title: str
    abstract: str
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    journal: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    pmc_id: Optional[str] = None
    url: Optional[str] = None
    mesh_terms: list[str] = field(default_factory=list)
    source: DocumentSource = DocumentSource.PUBMED
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def formatted_authors(self) -> str:
        """
        Return formatted author string.

        Returns:
            Formatted authors (e.g., "Smith J, Jones A" or "Smith J et al.")
        """
        if not self.authors:
            return "Unknown"
        if len(self.authors) <= 3:
            return ", ".join(self.authors)
        return f"{self.authors[0]} et al."

    @property
    def citation(self) -> str:
        """
        Return formatted citation string.

        Returns:
            Citation in standard format
        """
        parts = [self.formatted_authors]
        if self.year:
            parts.append(f"({self.year})")
        parts.append(self.title)
        if self.journal:
            parts.append(self.journal)
        return ". ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation
        """
        return {
            "id": self.id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "year": self.year,
            "journal": self.journal,
            "doi": self.doi,
            "pmid": self.pmid,
            "pmc_id": self.pmc_id,
            "url": self.url,
            "mesh_terms": self.mesh_terms,
            "source": self.source.value,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LiteDocument":
        """
        Create from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            LiteDocument instance
        """
        return cls(
            id=data["id"],
            title=data["title"],
            abstract=data["abstract"],
            authors=data.get("authors", []),
            year=data.get("year"),
            journal=data.get("journal"),
            doi=data.get("doi"),
            pmid=data.get("pmid"),
            pmc_id=data.get("pmc_id"),
            url=data.get("url"),
            mesh_terms=data.get("mesh_terms", []),
            source=DocumentSource(data.get("source", "pubmed")),
            metadata=data.get("metadata", {}),
        )


@dataclass
class DocumentChunk:
    """
    A chunk of a document for embedding and retrieval.

    Used in document interrogation for semantic search
    over document sections.
    """

    id: str  # Unique chunk ID (e.g., "doc-123_chunk_0")
    document_id: str  # Parent document ID
    text: str  # Chunk text content
    chunk_index: int  # Position in document (0-indexed)
    start_char: int  # Start character position in original
    end_char: int  # End character position in original
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "document_id": self.document_id,
            "text": self.text,
            "chunk_index": self.chunk_index,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "metadata": self.metadata,
        }


@dataclass
class SearchSession:
    """
    A PubMed search session.

    Tracks search queries and their results for history
    and reproducibility.
    """

    id: str  # Session UUID
    query: str  # PubMed query string
    natural_language_query: str  # Original user question
    created_at: datetime
    document_count: int  # Number of documents found
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "query": self.query,
            "natural_language_query": self.natural_language_query,
            "created_at": self.created_at.isoformat(),
            "document_count": self.document_count,
            "metadata": self.metadata,
        }


@dataclass
class ScoredDocument:
    """
    Document with relevance score.

    Result of document scoring by the LLM.
    """

    document: LiteDocument
    score: int  # 1-5 scale
    explanation: str  # Why this score was assigned
    scored_at: datetime = field(default_factory=datetime.now)

    @property
    def is_relevant(self) -> bool:
        """Check if document meets minimum relevance threshold (score >= 3)."""
        return self.score >= 3


@dataclass
class Citation:
    """
    Extracted citation from a document.

    Contains a specific passage that supports answering
    the research question.
    """

    document: LiteDocument
    passage: str  # Extracted text passage
    relevance_score: int  # Score of parent document
    context: str = ""  # Why this passage is relevant
    assessment: Optional["QualityAssessment"] = None  # Quality assessment if available

    @property
    def formatted_citation(self) -> str:
        """
        Return formatted citation with passage.

        Returns:
            Citation with quoted passage
        """
        return f'"{self.passage}" [{self.document.formatted_authors}, {self.document.year or "n.d."}]'

    @property
    def formatted_reference(self) -> str:
        """
        Return a short reference string.

        Returns:
            Short reference (e.g., "Smith et al., 2023")
        """
        if self.document.authors:
            first_author = self.document.authors[0].split(",")[0].split()[-1]
            if len(self.document.authors) > 1:
                author_str = f"{first_author} et al."
            else:
                author_str = first_author
        else:
            author_str = "Unknown"
        year = self.document.year or "n.d."
        return f"{author_str}, {year}"

    @property
    def quality_annotation(self) -> str:
        """
        Get quality annotation for inline use.

        Returns:
            Quality annotation string or empty string
        """
        if not self.assessment:
            return ""

        parts = []
        design = self.assessment.study_design.value.replace("_", " ").title()
        if design.lower() not in ["unknown", "other"]:
            parts.append(design)

        if self.assessment.sample_size:
            parts.append(f"n={self.assessment.sample_size:,}")

        if self.assessment.is_blinded and self.assessment.is_blinded != "none":
            parts.append(f"{self.assessment.is_blinded}-blind")

        if parts:
            return f"**{', '.join(parts)}**"
        return ""


@dataclass
class ReviewCheckpoint:
    """
    Checkpoint for systematic review progress.

    Allows resuming reviews from any step in the workflow.
    """

    id: str  # Checkpoint UUID
    research_question: str
    created_at: datetime
    updated_at: datetime
    step: str  # Current workflow step (e.g., "search", "scoring", "report")
    search_session_id: Optional[str] = None
    scored_documents: list[ScoredDocument] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    report: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "research_question": self.research_question,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "step": self.step,
            "search_session_id": self.search_session_id,
            "report": self.report,
            "metadata": self.metadata,
        }


@dataclass
class InterrogationSession:
    """
    Session for document interrogation.

    Tracks the loaded document and conversation history.
    """

    id: str  # Session UUID
    document_id: str  # ID of loaded document
    document_title: str
    created_at: datetime
    messages: list[dict[str, str]] = field(default_factory=list)  # Chat history
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str) -> None:
        """
        Add a message to the conversation history.

        Args:
            role: "user" or "assistant"
            content: Message text
        """
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
