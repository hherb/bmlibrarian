"""
Document Question-Answering Module for BMLibrarian.

This module provides high-level functions for answering questions about
documents in the knowledge base using semantic search and LLM inference.

The main entry point is `answer_from_document()` which handles:
- Full-text discovery and download (if missing)
- Semantic embedding generation (if needed)
- Semantic search within the document
- Fallback to abstract if full-text unavailable
- LLM-based answer generation with thinking model support

Example Usage:
    from bmlibrarian.qa import answer_from_document

    result = answer_from_document(
        document_id=12345,
        question="What are the main findings of this study?",
        use_fulltext=True,
        download_missing_fulltext=True
    )

    if result.error:
        print(f"Error: {result.error}")
    else:
        print(f"Answer: {result.answer}")
        print(f"Source: {result.source.value}")
        if result.reasoning:
            print(f"Reasoning: {result.reasoning}")
"""

from .data_types import (
    AnswerSource,
    QAError,
    ChunkContext,
    SemanticSearchAnswer,
    DocumentTextStatus,
    ProxyCallbackResult,
    ProxyCallback,
)
from .document_qa import answer_from_document

__all__ = [
    "AnswerSource",
    "QAError",
    "ChunkContext",
    "SemanticSearchAnswer",
    "DocumentTextStatus",
    "ProxyCallbackResult",
    "ProxyCallback",
    "answer_from_document",
]
