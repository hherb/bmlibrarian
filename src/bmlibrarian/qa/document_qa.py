"""
Document Question-Answering for BMLibrarian.

This module provides the `answer_from_document()` function for answering
questions about specific documents using semantic search and LLM inference.

The function handles the complete workflow:
1. Check document text availability (full-text vs abstract)
2. Download missing full-text if requested
3. Generate embeddings if needed
4. Perform document-specific semantic search
5. Generate answer using LLM with optional thinking model support
6. Fallback to abstract if full-text unavailable

Example:
    from bmlibrarian.qa import answer_from_document

    result = answer_from_document(
        document_id=12345,
        question="What methodology did the authors use?"
    )
    print(result.answer)
"""

import logging
import re
from pathlib import Path
from typing import Optional, List, Tuple, TYPE_CHECKING

import ollama

if TYPE_CHECKING:
    from bmlibrarian.database import DatabaseManager

from .data_types import (
    AnswerSource,
    QAError,
    ChunkContext,
    SemanticSearchAnswer,
    DocumentTextStatus,
    ProxyCallbackResult,
    ProxyCallback,
)

logger = logging.getLogger(__name__)

# Default configuration constants
DEFAULT_QA_MODEL = "gpt-oss:20b"
DEFAULT_EMBEDDING_MODEL = "snowflake-arctic-embed2:latest"
DEFAULT_MAX_CHUNKS = 5
DEFAULT_SIMILARITY_THRESHOLD = 0.7
DEFAULT_TEMPERATURE = 0.3
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

# Minimum abstract length to consider usable (characters)
MIN_ABSTRACT_LENGTH = 50

# Maximum retries when user claims PDF was made available but it's still not found
MAX_PDF_AVAILABILITY_RETRIES = 2


def _get_document_text_status(
    document_id: int,
    db_manager: "DatabaseManager",
) -> Optional[DocumentTextStatus]:
    """
    Get text availability status for a document.

    Uses the SQL function get_document_text_status() for efficient checking.

    Args:
        document_id: The document's database ID.
        db_manager: Database manager instance.

    Returns:
        DocumentTextStatus object, or None if document not found.
    """
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Get basic document info
                cur.execute(
                    """
                    SELECT title, abstract, full_text
                    FROM public.document
                    WHERE id = %s
                    """,
                    (document_id,),
                )
                row = cur.fetchone()

                if not row:
                    return None

                title, abstract, full_text = row

                # Get status from helper function
                cur.execute(
                    "SELECT * FROM get_document_text_status(%s)",
                    (document_id,),
                )
                status_row = cur.fetchone()

                if status_row:
                    (
                        has_abstract,
                        has_fulltext,
                        has_abstract_embeddings,
                        has_fulltext_chunks,
                        abstract_length,
                        fulltext_length,
                    ) = status_row

                    return DocumentTextStatus(
                        document_id=document_id,
                        has_abstract=has_abstract,
                        has_fulltext=has_fulltext,
                        has_abstract_embeddings=has_abstract_embeddings,
                        has_fulltext_chunks=has_fulltext_chunks,
                        abstract_length=abstract_length,
                        fulltext_length=fulltext_length,
                        title=title,
                    )

                # Fallback if function doesn't exist
                return DocumentTextStatus(
                    document_id=document_id,
                    has_abstract=bool(abstract and abstract.strip()),
                    has_fulltext=bool(full_text and full_text.strip()),
                    has_abstract_embeddings=False,
                    has_fulltext_chunks=False,
                    abstract_length=len(abstract) if abstract else 0,
                    fulltext_length=len(full_text) if full_text else 0,
                    title=title,
                )

    except Exception as e:
        logger.error(f"Error getting document text status: {e}")
        return None


def _semantic_search_fulltext(
    document_id: int,
    question: str,
    threshold: float,
    max_chunks: int,
    db_manager: "DatabaseManager",
) -> List[ChunkContext]:
    """
    Perform semantic search on full-text chunks within a document.

    Args:
        document_id: The document's database ID.
        question: The question to search for.
        threshold: Minimum similarity threshold (0.0 to 1.0).
        max_chunks: Maximum number of chunks to return.
        db_manager: Database manager instance.

    Returns:
        List of ChunkContext objects sorted by score descending.
    """
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT chunk_id, chunk_no, score, chunk_text
                    FROM semantic.chunksearch_document(%s, %s, %s, %s)
                    ORDER BY score DESC
                    """,
                    (document_id, question, threshold, max_chunks),
                )
                rows = cur.fetchall()

                return [
                    ChunkContext(
                        chunk_id=row[0],
                        chunk_no=row[1],
                        score=row[2],
                        text=row[3],
                    )
                    for row in rows
                ]

    except Exception as e:
        logger.error(f"Full-text semantic search failed: {e}")
        return []


def _semantic_search_abstract(
    document_id: int,
    question: str,
    threshold: float,
    max_chunks: int,
    db_manager: "DatabaseManager",
) -> List[ChunkContext]:
    """
    Perform semantic search on abstract chunks within a document.

    Args:
        document_id: The document's database ID.
        question: The question to search for.
        threshold: Minimum similarity threshold (0.0 to 1.0).
        max_chunks: Maximum number of chunks to return.
        db_manager: Database manager instance.

    Returns:
        List of ChunkContext objects sorted by score descending.
    """
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT chunk_id, chunk_no, score, chunk_text
                    FROM semantic_search_document(%s, %s, %s, %s)
                    ORDER BY score DESC
                    """,
                    (document_id, question, threshold, max_chunks),
                )
                rows = cur.fetchall()

                return [
                    ChunkContext(
                        chunk_id=row[0],
                        chunk_no=row[1],
                        score=row[2],
                        text=row[3],
                    )
                    for row in rows
                ]

    except Exception as e:
        logger.error(f"Abstract semantic search failed: {e}")
        return []


def _get_document_abstract(document_id: int, db_manager: "DatabaseManager") -> Optional[str]:
    """
    Get the abstract text for a document.

    Args:
        document_id: The document's database ID.
        db_manager: Database manager instance.

    Returns:
        Abstract text, or None if not available.
    """
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT abstract FROM public.document WHERE id = %s",
                    (document_id,),
                )
                row = cur.fetchone()
                return row[0] if row and row[0] else None

    except Exception as e:
        logger.error(f"Error getting document abstract: {e}")
        return None


def _get_document_title(document_id: int, db_manager: "DatabaseManager") -> Optional[str]:
    """
    Get the title for a document.

    Used to provide context in the proxy callback.

    Args:
        document_id: The document's database ID.
        db_manager: Database manager instance.

    Returns:
        Document title, or None if not available.
    """
    try:
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT title FROM public.document WHERE id = %s",
                    (document_id,),
                )
                row = cur.fetchone()
                return row[0] if row and row[0] else None

    except Exception as e:
        logger.error(f"Error getting document title: {e}")
        return None


def _embed_fulltext_if_needed(
    document_id: int,
    db_manager: "DatabaseManager",
) -> bool:
    """
    Ensure full-text chunks are embedded for a document.

    If the document has full_text but no chunks, triggers embedding.

    Args:
        document_id: The document's database ID.
        db_manager: Database manager instance.

    Returns:
        True if chunks exist or were successfully created, False otherwise.
    """
    try:
        from bmlibrarian.embeddings.chunk_embedder import ChunkEmbedder

        embedder = ChunkEmbedder()

        # Check if chunks already exist
        if embedder.has_chunks(document_id):
            logger.debug(f"Document {document_id} already has full-text chunks")
            return True

        # Check if full_text exists
        full_text = embedder.get_document_full_text(document_id)
        if not full_text:
            logger.warning(f"Document {document_id} has no full_text to embed")
            return False

        # Generate chunks and embeddings
        logger.info(f"Embedding full-text for document {document_id}")
        num_chunks = embedder.chunk_and_embed(document_id, overwrite=False)

        if num_chunks > 0:
            logger.info(f"Created {num_chunks} chunks for document {document_id}")
            return True
        else:
            logger.warning(f"Failed to create chunks for document {document_id}")
            return False

    except ImportError:
        logger.error("ChunkEmbedder not available")
        return False
    except Exception as e:
        logger.error(f"Error embedding full-text: {e}")
        return False


def _download_fulltext_if_needed(
    document_id: int,
    db_manager: "DatabaseManager",
    use_proxy: bool = True,
    output_dir: Optional[Path] = None,
) -> bool:
    """
    Attempt to download full-text PDF for a document.

    Uses FullTextFinder to discover and download PDFs.

    Args:
        document_id: The document's database ID.
        db_manager: Database manager instance.
        use_proxy: Whether to use OpenAthens proxy if configured.
        output_dir: Directory for PDF storage (uses default if None).

    Returns:
        True if full-text was obtained and stored, False otherwise.
    """
    try:
        from bmlibrarian.discovery import download_pdf_for_document
        from bmlibrarian.config import get_config

        config = get_config()

        # Get document metadata
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT doi, external_id, title, publication_date
                    FROM public.document
                    WHERE id = %s
                    """,
                    (document_id,),
                )
                row = cur.fetchone()

                if not row:
                    return False

                doi, pmid, title, pub_date = row

        document = {
            "id": document_id,
            "doi": doi,
            "pmid": pmid,
            "title": title,
            "publication_date": pub_date,
        }

        # Determine output directory
        if output_dir is None:
            pdf_base_dir = config.get("pdf", {}).get("base_dir", "~/knowledgebase/pdf")
            output_dir = Path(pdf_base_dir).expanduser()

        # Get OpenAthens proxy URL if enabled
        openathens_url = None
        if use_proxy:
            openathens_config = config.get("openathens", {})
            if openathens_config.get("enabled", False):
                openathens_url = openathens_config.get("institution_url")

        # Attempt download
        unpaywall_email = config.get("unpaywall_email")

        result = download_pdf_for_document(
            document=document,
            output_dir=output_dir,
            unpaywall_email=unpaywall_email,
            openathens_proxy_url=openathens_url,
            use_browser_fallback=True,
        )

        if result.success and result.file_path:
            logger.info(f"Downloaded PDF for document {document_id}: {result.file_path}")

            # Extract text from PDF and store in database
            # This would require PDF text extraction - for now just return success
            # The actual text extraction should be handled by a separate process
            return True
        else:
            logger.warning(
                f"Failed to download PDF for document {document_id}: {result.error_message}"
            )
            return False

    except ImportError:
        logger.error("Discovery module not available")
        return False
    except Exception as e:
        logger.error(f"Error downloading full-text: {e}")
        return False


def _extract_thinking(response_content: str) -> Tuple[str, Optional[str]]:
    """
    Extract thinking/reasoning from model response.

    Handles both `<think>` blocks (Qwen-style) and strips them from the answer.

    Args:
        response_content: Raw response from the model.

    Returns:
        Tuple of (answer_text, reasoning_text or None).
    """
    # Pattern for <think>...</think> blocks
    think_pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)

    match = think_pattern.search(response_content)
    if match:
        thinking = match.group(1).strip()
        # Remove the thinking block from the answer
        answer = think_pattern.sub("", response_content).strip()
        return answer, thinking

    return response_content.strip(), None


def _generate_answer(
    question: str,
    context: str,
    model: str,
    temperature: float,
    host: str,
    use_thinking: bool = True,
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Generate an answer using the LLM.

    Args:
        question: The question to answer.
        context: Context text from document chunks or abstract.
        model: LLM model name.
        temperature: Model temperature.
        host: Ollama server URL.
        use_thinking: Whether to enable thinking mode for supported models.

    Returns:
        Tuple of (answer, reasoning, error_message).
    """
    system_prompt = """You are a biomedical research assistant helping to answer questions about scientific documents.

Your task:
1. Read the provided context from the document carefully
2. Answer the question based ONLY on the information in the context
3. If the context doesn't contain enough information to answer, say so clearly
4. Be concise but complete in your answer
5. Cite specific details from the context when relevant

If you cannot answer the question from the given context, explain what information is missing."""

    user_prompt = f"""Context from document:
{context}

Question: {question}

Please answer the question based on the context provided."""

    try:
        client = ollama.Client(host=host)

        # Check if model supports thinking
        # DeepSeek-R1 and similar models support the think parameter
        thinking_models = ["deepseek-r1", "qwen", "qwq"]
        model_supports_thinking = any(tm in model.lower() for tm in thinking_models)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # Use think parameter if supported
        if use_thinking and model_supports_thinking:
            response = client.chat(
                model=model,
                messages=messages,
                options={"temperature": temperature},
                think=True,
            )

            content = response["message"]["content"]
            # Check for thinking field in response
            thinking = response["message"].get("thinking")

            if thinking:
                return content.strip(), thinking.strip(), None

            # Fallback: extract from content if not in separate field
            answer, extracted_thinking = _extract_thinking(content)
            return answer, extracted_thinking, None

        else:
            # Standard chat without thinking
            response = client.chat(
                model=model,
                messages=messages,
                options={"temperature": temperature},
            )

            content = response["message"]["content"]
            # Still try to extract thinking blocks if present
            answer, extracted_thinking = _extract_thinking(content)
            return answer, extracted_thinking, None

    except ollama.ResponseError as e:
        error_msg = f"Ollama error: {e}"
        logger.error(error_msg)
        return "", None, error_msg
    except Exception as e:
        error_msg = f"LLM generation error: {e}"
        logger.error(error_msg)
        return "", None, error_msg


def answer_from_document(
    document_id: int,
    question: str,
    *,
    use_fulltext: bool = True,
    download_missing_fulltext: bool = True,
    always_allow_proxy: bool = False,
    proxy_callback: Optional[ProxyCallback] = None,
    model: Optional[str] = None,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    temperature: float = DEFAULT_TEMPERATURE,
    ollama_host: Optional[str] = None,
) -> SemanticSearchAnswer:
    """
    Answer a question about a specific document using semantic search and LLM.

    This function provides a complete workflow for document Q&A:
    1. Checks what text is available (full-text vs abstract)
    2. Optionally downloads missing full-text (with optional proxy consent)
    3. Generates embeddings if needed
    4. Performs document-specific semantic search
    5. Generates an answer using the LLM
    6. Falls back to abstract if full-text unavailable

    Args:
        document_id: Database ID of the document to query.
        question: The question to answer about the document.
        use_fulltext: If True, prefer full-text over abstract. Default True.
        download_missing_fulltext: If True and full-text missing, attempt download.
            Default True.
        always_allow_proxy: If True, automatically use OpenAthens proxy without
            asking for user consent. If False (default), the proxy_callback is
            invoked to request user consent before using institutional proxy.
        proxy_callback: Optional callback function invoked when PDF is not
            available via open-access sources. The callback receives
            (document_id, document_title) and should return a ProxyCallbackResult.
            This allows UI integration for user consent or manual PDF upload.
            If None and always_allow_proxy is False, proxy won't be used.
        model: LLM model for answer generation. Uses config default if None.
        max_chunks: Maximum number of context chunks to use. Default 5.
        similarity_threshold: Minimum semantic similarity (0.0-1.0). Default 0.7.
        temperature: LLM temperature for generation. Default 0.3.
        ollama_host: Ollama server URL. Uses config default if None.

    Returns:
        SemanticSearchAnswer with the answer and metadata.

    Example:
        >>> # Basic usage (no proxy)
        >>> result = answer_from_document(
        ...     document_id=12345,
        ...     question="What are the main findings?"
        ... )
        >>> if result.success:
        ...     print(result.answer)
        ... else:
        ...     print(f"Error: {result.error_message}")

        >>> # With automatic proxy (no user consent required)
        >>> result = answer_from_document(
        ...     document_id=12345,
        ...     question="What methodology was used?",
        ...     always_allow_proxy=True
        ... )

        >>> # With callback for user consent
        >>> def my_callback(doc_id, title):
        ...     # Ask user for consent
        ...     return ProxyCallbackResult(allow_proxy=True)
        >>> result = answer_from_document(
        ...     document_id=12345,
        ...     question="What are the conclusions?",
        ...     proxy_callback=my_callback
        ... )
    """
    # Validate inputs
    if not question or not question.strip():
        return SemanticSearchAnswer(
            answer="",
            error=QAError.CONFIGURATION_ERROR,
            error_message="Question cannot be empty",
            document_id=document_id,
            question=question,
        )

    # Get database manager
    try:
        from bmlibrarian.database import get_db_manager

        db_manager = get_db_manager()
    except ImportError:
        return SemanticSearchAnswer(
            answer="",
            error=QAError.DATABASE_ERROR,
            error_message="Database module not available",
            document_id=document_id,
            question=question,
        )

    # Get configuration
    try:
        from bmlibrarian.config import get_config

        config = get_config()
        qa_config = config.get("agents", {}).get("document_qa", {})
        models_config = config.get("models", {})
        ollama_config = config.get("ollama", {})
    except ImportError:
        qa_config = {}
        models_config = {}
        ollama_config = {}

    # Resolve parameters from config (following BMLibrarian conventions)
    model = model or models_config.get("document_qa_agent", DEFAULT_QA_MODEL)
    ollama_host = ollama_host or ollama_config.get("host", DEFAULT_OLLAMA_HOST)

    # Get document text status
    status = _get_document_text_status(document_id, db_manager)
    if status is None:
        return SemanticSearchAnswer(
            answer="",
            error=QAError.DOCUMENT_NOT_FOUND,
            error_message=f"Document with ID {document_id} not found",
            document_id=document_id,
            question=question,
            model_used=model,
        )

    # Check if we have any text at all
    if not status.has_any_text:
        return SemanticSearchAnswer(
            answer="",
            error=QAError.NO_TEXT_AVAILABLE,
            error_message=f"Document '{status.title}' has no abstract or full-text",
            document_id=document_id,
            question=question,
            model_used=model,
        )

    # Determine strategy
    chunks: List[ChunkContext] = []
    source = AnswerSource.ABSTRACT
    context_text = ""

    if use_fulltext:
        # Try to use full-text
        if not status.has_fulltext and download_missing_fulltext:
            # First attempt: try open-access sources (no proxy)
            logger.info(f"Attempting to download full-text for document {document_id} (open access)")
            download_success = _download_fulltext_if_needed(
                document_id, db_manager, use_proxy=False
            )

            if download_success:
                # Refresh status after successful download
                status = _get_document_text_status(document_id, db_manager)
            else:
                # Open access failed - need to decide on proxy
                logger.info(f"Open access download failed for document {document_id}")

                if always_allow_proxy:
                    # Auto-consent: use proxy directly without asking
                    logger.info(f"Using proxy automatically for document {document_id}")
                    if _download_fulltext_if_needed(document_id, db_manager, use_proxy=True):
                        status = _get_document_text_status(document_id, db_manager)

                elif proxy_callback is not None:
                    # Ask user via callback
                    doc_title = status.title or _get_document_title(document_id, db_manager)
                    logger.info(f"Invoking proxy callback for document {document_id}")

                    callback_result = proxy_callback(document_id, doc_title)

                    if callback_result.pdf_made_available:
                        # User uploaded PDF manually - refresh status
                        # Use retry loop in case embedding takes time
                        logger.info(f"PDF made available externally for document {document_id}")
                        for retry in range(MAX_PDF_AVAILABILITY_RETRIES):
                            status = _get_document_text_status(document_id, db_manager)
                            if status and status.has_fulltext:
                                logger.info(f"Full-text now available for document {document_id}")
                                break
                            logger.warning(
                                f"Full-text not yet visible for document {document_id} "
                                f"(retry {retry + 1}/{MAX_PDF_AVAILABILITY_RETRIES})"
                            )
                        else:
                            logger.warning(
                                f"PDF claimed available but full-text still not found "
                                f"for document {document_id}"
                            )

                    elif callback_result.allow_proxy:
                        # User consented to proxy - try OpenAthens
                        logger.info(f"User consented to proxy for document {document_id}")
                        if _download_fulltext_if_needed(document_id, db_manager, use_proxy=True):
                            status = _get_document_text_status(document_id, db_manager)
                    else:
                        # User declined both options
                        logger.info(f"User declined proxy/upload for document {document_id}")
                # else: no callback provided and not auto-allow → skip proxy, fall back to abstract

        if status.has_fulltext:
            # Ensure embeddings exist
            if not status.has_fulltext_chunks:
                logger.info(f"Generating embeddings for document {document_id}")
                if _embed_fulltext_if_needed(document_id, db_manager):
                    status.has_fulltext_chunks = True

            if status.has_fulltext_chunks:
                # Perform full-text semantic search
                chunks = _semantic_search_fulltext(
                    document_id,
                    question,
                    similarity_threshold,
                    max_chunks,
                    db_manager,
                )
                if chunks:
                    source = AnswerSource.FULLTEXT_SEMANTIC
                    context_text = "\n\n---\n\n".join(
                        f"[Chunk {c.chunk_no + 1}, Score: {c.score:.2f}]\n{c.text}"
                        for c in chunks
                    )
                    logger.info(
                        f"Using {len(chunks)} full-text chunks for document {document_id}"
                    )

    # Fallback to abstract if no full-text chunks
    if not chunks:
        if status.has_abstract:
            abstract = _get_document_abstract(document_id, db_manager)
            if abstract and len(abstract) >= MIN_ABSTRACT_LENGTH:
                source = AnswerSource.ABSTRACT
                context_text = abstract
                # Create a pseudo-chunk for tracking
                chunks = [
                    ChunkContext(
                        chunk_no=0,
                        text=abstract,
                        score=1.0,
                    )
                ]
                logger.info(f"Using abstract for document {document_id}")
            else:
                return SemanticSearchAnswer(
                    answer="",
                    error=QAError.NO_TEXT_AVAILABLE,
                    error_message="Abstract is too short or unavailable",
                    document_id=document_id,
                    question=question,
                    model_used=model,
                )
        else:
            return SemanticSearchAnswer(
                answer="",
                error=QAError.NO_FULLTEXT,
                error_message="No full-text available and no abstract fallback",
                document_id=document_id,
                question=question,
                model_used=model,
            )

    # Generate answer
    answer, reasoning, error = _generate_answer(
        question=question,
        context=context_text,
        model=model,
        temperature=temperature,
        host=ollama_host,
    )

    if error:
        return SemanticSearchAnswer(
            answer="",
            error=QAError.LLM_ERROR,
            error_message=error,
            source=source,
            chunks_used=chunks,
            document_id=document_id,
            question=question,
            model_used=model,
        )

    return SemanticSearchAnswer(
        answer=answer,
        reasoning=reasoning,
        source=source,
        chunks_used=chunks,
        document_id=document_id,
        question=question,
        model_used=model,
    )
