"""
Data types for the Document Question-Answering module.

This module defines the dataclasses and enums used throughout the QA system,
following BMLibrarian's type-safe design principles.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TypeAlias


class AnswerSource(Enum):
    """
    Source of context used for generating the answer.

    Indicates whether the answer was derived from full-text semantic search
    or from the document abstract.
    """

    FULLTEXT_SEMANTIC = "fulltext_semantic"  # Semantic search on full-text chunks
    ABSTRACT = "abstract"  # Used document abstract as context


class QAError(Enum):
    """
    Error types for document Q&A operations.

    Provides structured error codes for programmatic error handling,
    each with a descriptive message available via `.description`.
    """

    DOCUMENT_NOT_FOUND = "document_not_found"
    NO_TEXT_AVAILABLE = "no_text_available"
    NO_FULLTEXT = "no_fulltext"
    DOWNLOAD_FAILED = "download_failed"
    EMBEDDING_FAILED = "embedding_failed"
    SEMANTIC_SEARCH_FAILED = "semantic_search_failed"
    LLM_ERROR = "llm_error"
    DATABASE_ERROR = "database_error"
    CONFIGURATION_ERROR = "configuration_error"
    PROXY_REQUIRED = "proxy_required"
    USER_CANCELLED = "user_cancelled"
    PROXY_DOWNLOAD_FAILED = "proxy_download_failed"

    @property
    def description(self) -> str:
        """Get a human-readable description of the error."""
        descriptions = {
            QAError.DOCUMENT_NOT_FOUND: "Document with the specified ID was not found in the database",
            QAError.NO_TEXT_AVAILABLE: "Document has neither abstract nor full-text available",
            QAError.NO_FULLTEXT: "Full-text is not available and could not be obtained",
            QAError.DOWNLOAD_FAILED: "Failed to download the full-text PDF",
            QAError.EMBEDDING_FAILED: "Failed to generate or retrieve embeddings for the document",
            QAError.SEMANTIC_SEARCH_FAILED: "Semantic search operation failed",
            QAError.LLM_ERROR: "Error during LLM inference",
            QAError.DATABASE_ERROR: "Database operation failed",
            QAError.CONFIGURATION_ERROR: "Configuration is invalid or missing required settings",
            QAError.PROXY_REQUIRED: "PDF requires institutional access; proxy authentication needed",
            QAError.USER_CANCELLED: "User declined to provide PDF or authorize proxy access",
            QAError.PROXY_DOWNLOAD_FAILED: "Proxy download was attempted but failed",
        }
        return descriptions.get(self, "Unknown error")


@dataclass
class ProxyCallbackResult:
    """
    Result from the proxy callback function.

    Used when the QA system needs user consent to either:
    1. Use institutional proxy (OpenAthens) for PDF download
    2. Accept a manually uploaded/provided PDF

    Attributes:
        pdf_made_available: True if the caller has downloaded and embedded
            the PDF externally (e.g., user uploaded it manually via GUI).
            If True, the QA system will refresh document status and continue
            processing with the newly available full-text.
        allow_proxy: True if the user consents to using institutional proxy
            (OpenAthens) to attempt PDF download. Only used if
            pdf_made_available is False.
    """

    pdf_made_available: bool = False
    allow_proxy: bool = False

    def __repr__(self) -> str:
        """Return a concise representation for debugging."""
        return f"ProxyCallbackResult(pdf_made_available={self.pdf_made_available}, allow_proxy={self.allow_proxy})"


# Type alias for the proxy callback function signature
# Callback receives: (document_id: int, document_title: Optional[str]) -> ProxyCallbackResult
ProxyCallback = Callable[[int, Optional[str]], ProxyCallbackResult]


@dataclass
class ChunkContext:
    """
    Represents a chunk of text used as context for answering.

    Attributes:
        chunk_no: Sequential chunk number within the document.
        text: The actual text content of the chunk.
        score: Semantic similarity score (0.0 to 1.0).
        chunk_id: Database ID of the chunk (optional).
    """

    chunk_no: int
    text: str
    score: float
    chunk_id: Optional[int] = None

    def __repr__(self) -> str:
        """Return a concise representation for debugging."""
        text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"ChunkContext(no={self.chunk_no}, score={self.score:.3f}, text='{text_preview}')"


@dataclass
class DocumentTextStatus:
    """
    Status of text availability for a document.

    Used to determine which Q&A strategy to use (full-text vs abstract).

    Attributes:
        document_id: The document's database ID.
        has_abstract: Whether an abstract exists and is non-empty.
        has_fulltext: Whether full_text exists and is non-empty.
        has_abstract_embeddings: Whether abstract embeddings exist in emb_1024.
        has_fulltext_chunks: Whether full-text chunks exist in semantic.chunks.
        abstract_length: Length of abstract in characters.
        fulltext_length: Length of full_text in characters.
        title: Document title (for error messages).
    """

    document_id: int
    has_abstract: bool = False
    has_fulltext: bool = False
    has_abstract_embeddings: bool = False
    has_fulltext_chunks: bool = False
    abstract_length: int = 0
    fulltext_length: int = 0
    title: Optional[str] = None

    @property
    def can_use_fulltext_semantic(self) -> bool:
        """Check if full-text semantic search is available."""
        return self.has_fulltext and self.has_fulltext_chunks

    @property
    def can_use_abstract_semantic(self) -> bool:
        """Check if abstract semantic search is available."""
        return self.has_abstract and self.has_abstract_embeddings

    @property
    def can_use_abstract_direct(self) -> bool:
        """Check if abstract can be used directly (without embeddings)."""
        return self.has_abstract

    @property
    def has_any_text(self) -> bool:
        """Check if any text is available for Q&A."""
        return self.has_abstract or self.has_fulltext


@dataclass
class SemanticSearchAnswer:
    """
    Result from document question-answering.

    Contains the generated answer, metadata about how it was generated,
    and any error information if the operation failed.

    Attributes:
        answer: The generated answer text. Empty string if error occurred.
        reasoning: For thinking models, the model's reasoning process.
            Extracted from `<think>` blocks or `message.thinking` field.
        source: Which source was used for context (fulltext or abstract).
        error: Error enum if operation failed, None on success.
        error_message: Detailed error message with context.
        chunks_used: List of chunks used as context (for transparency).
        model_used: Name of the LLM model that generated the answer.
        document_id: The document that was queried.
        question: The original question asked.
        confidence: Optional confidence score (0.0 to 1.0) if model provides it.
        fallback_reason: If abstract was used instead of full-text, explains why
            (e.g., "user_declined", "proxy_failed", "no_proxy_configured").
    """

    answer: str
    reasoning: Optional[str] = None
    source: AnswerSource = AnswerSource.ABSTRACT
    error: Optional[QAError] = None
    error_message: Optional[str] = None
    chunks_used: Optional[List[ChunkContext]] = None
    model_used: str = ""
    document_id: int = 0
    question: str = ""
    confidence: Optional[float] = None
    fallback_reason: Optional[str] = None  # Why abstract was used instead of full-text

    @property
    def success(self) -> bool:
        """Check if the Q&A operation succeeded."""
        return self.error is None and bool(self.answer)

    @property
    def used_fulltext(self) -> bool:
        """Check if full-text was used for the answer."""
        return self.source == AnswerSource.FULLTEXT_SEMANTIC

    def to_dict(self) -> dict:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "answer": self.answer,
            "reasoning": self.reasoning,
            "source": self.source.value,
            "error": self.error.value if self.error else None,
            "error_message": self.error_message,
            "chunks_used": [
                {
                    "chunk_no": c.chunk_no,
                    "text": c.text,
                    "score": c.score,
                    "chunk_id": c.chunk_id,
                }
                for c in (self.chunks_used or [])
            ],
            "model_used": self.model_used,
            "document_id": self.document_id,
            "question": self.question,
            "confidence": self.confidence,
            "fallback_reason": self.fallback_reason,
            "success": self.success,
        }

    def __repr__(self) -> str:
        """Return a concise representation for debugging."""
        if self.error:
            return f"SemanticSearchAnswer(error={self.error.value}, msg='{self.error_message}')"
        answer_preview = self.answer[:80] + "..." if len(self.answer) > 80 else self.answer
        return (
            f"SemanticSearchAnswer(source={self.source.value}, "
            f"chunks={len(self.chunks_used or [])}, "
            f"answer='{answer_preview}')"
        )
