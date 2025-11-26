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
import concurrent.futures
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
from ..utils.url_validation import get_validated_openathens_url
from ..agents.semantic_query_agent import (
    SemanticQueryAgent,
    SemanticSearchResult,
    SearchMode,
    DEFAULT_SEMANTIC_WEIGHT,
)

logger = logging.getLogger(__name__)

# Default configuration constants
DEFAULT_QA_MODEL = "gpt-oss:20b"
DEFAULT_EMBEDDING_MODEL = "snowflake-arctic-embed2:latest"
DEFAULT_MAX_CHUNKS = 5
# Note: 0.5 is a reasonable threshold for semantic search. Higher values (0.7+)
# may miss relevant content when query terms don't match document terminology exactly.
# For example, "quality assessment" may not semantically match "GRADE framework".
DEFAULT_SIMILARITY_THRESHOLD = 0.5
DEFAULT_TEMPERATURE = 0.3
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

# Minimum abstract length to consider usable (characters)
MIN_ABSTRACT_LENGTH = 50

# Maximum retries when user claims PDF was made available but it's still not found
MAX_PDF_AVAILABILITY_RETRIES = 2

# Default timeout for proxy callback (seconds)
DEFAULT_PROXY_CALLBACK_TIMEOUT = 300  # 5 minutes

# Fallback reason constants
FALLBACK_USER_DECLINED = "user_declined"
FALLBACK_PROXY_FAILED = "proxy_download_failed"
FALLBACK_NO_PROXY_CONFIGURED = "no_proxy_configured"
FALLBACK_OPEN_ACCESS_FAILED = "open_access_failed"
FALLBACK_NO_FULLTEXT_CHUNKS = "no_fulltext_chunks"
FALLBACK_CALLBACK_TIMEOUT = "callback_timeout"


def _invoke_proxy_callback_with_timeout(
    callback: "ProxyCallback",
    document_id: int,
    document_title: Optional[str],
    timeout_seconds: float,
) -> Tuple[Optional[ProxyCallbackResult], bool]:
    """
    Invoke the proxy callback with a timeout.

    For GUI applications, the callback typically returns immediately after user
    interaction. For programmatic use, this prevents indefinite hanging.

    Args:
        callback: The proxy callback function to invoke.
        document_id: Document ID to pass to the callback.
        document_title: Document title to pass to the callback.
        timeout_seconds: Maximum time to wait for callback to return.

    Returns:
        Tuple of (ProxyCallbackResult or None, timed_out: bool).
        If timed_out is True, the result will be None.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(callback, document_id, document_title)
        try:
            result = future.result(timeout=timeout_seconds)
            return result, False
        except concurrent.futures.TimeoutError:
            logger.warning(
                f"Proxy callback timed out after {timeout_seconds}s for document {document_id}"
            )
            return None, True
        except Exception as e:
            logger.error(f"Proxy callback raised exception for document {document_id}: {e}")
            return None, False


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
                # First, check how many chunks exist for this document
                cur.execute(
                    "SELECT COUNT(*) FROM semantic.chunks WHERE document_id = %s",
                    (document_id,),
                )
                total_chunks = cur.fetchone()[0]
                logger.info(
                    f"[DEBUG] Document {document_id} has {total_chunks} chunks in semantic.chunks"
                )

                if total_chunks == 0:
                    logger.warning(
                        f"[DEBUG] No chunks found for document {document_id}. "
                        f"Document may not have been embedded yet."
                    )
                    return []

                # Perform the semantic search with threshold
                logger.info(
                    f"[DEBUG] Searching document {document_id} with question: "
                    f"'{question[:100]}...' threshold={threshold}, max_chunks={max_chunks}"
                )

                cur.execute(
                    """
                    SELECT chunk_id, chunk_no, score, chunk_text
                    FROM semantic.chunksearch_document(%s, %s, %s, %s)
                    ORDER BY score DESC
                    """,
                    (document_id, question, threshold, max_chunks),
                )
                rows = cur.fetchall()

                if not rows:
                    # No chunks above threshold - let's see what scores we're getting
                    logger.warning(
                        f"[DEBUG] No chunks above threshold {threshold}. "
                        f"Checking top scores without threshold filter..."
                    )
                    # Query without threshold to see actual scores
                    cur.execute(
                        """
                        SELECT chunk_id, chunk_no, score,
                               LEFT(chunk_text, 100) as preview
                        FROM semantic.chunksearch_document(%s, %s, %s, %s)
                        ORDER BY score DESC
                        """,
                        (document_id, question, 0.0, 5),  # No threshold
                    )
                    debug_rows = cur.fetchall()
                    if debug_rows:
                        logger.warning(
                            f"[DEBUG] Top 5 chunk scores (no threshold): "
                            f"{[(r[1], round(r[2], 3)) for r in debug_rows]}"
                        )
                        for row in debug_rows[:3]:
                            logger.debug(
                                f"[DEBUG] Chunk {row[1]}: score={row[2]:.3f}, "
                                f"preview='{row[3][:80]}...'"
                            )
                    else:
                        logger.warning(
                            f"[DEBUG] Even with threshold=0, no chunks returned. "
                            f"Check if embedding function is working."
                        )
                else:
                    logger.info(
                        f"[DEBUG] Found {len(rows)} chunks above threshold {threshold}. "
                        f"Scores: {[round(r[2], 3) for r in rows]}"
                    )

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
        logger.error(f"Full-text semantic search failed: {e}", exc_info=True)
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
                # Check for abstract embeddings
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM chunks c
                    JOIN emb_1024 e ON c.id = e.chunk_id
                    WHERE c.document_id = %s
                    """,
                    (document_id,),
                )
                total_chunks = cur.fetchone()[0]
                logger.info(
                    f"[DEBUG] Document {document_id} has {total_chunks} abstract chunks in emb_1024"
                )

                if total_chunks == 0:
                    logger.warning(
                        f"[DEBUG] No abstract embeddings for document {document_id}."
                    )
                    return []

                logger.info(
                    f"[DEBUG] Abstract search for document {document_id}: "
                    f"'{question[:100]}...' threshold={threshold}"
                )

                cur.execute(
                    """
                    SELECT chunk_id, chunk_no, score, chunk_text
                    FROM semantic_search_document(%s, %s, %s, %s)
                    ORDER BY score DESC
                    """,
                    (document_id, question, threshold, max_chunks),
                )
                rows = cur.fetchall()

                if rows:
                    logger.info(
                        f"[DEBUG] Abstract search found {len(rows)} chunks. "
                        f"Scores: {[round(r[2], 3) for r in rows]}"
                    )
                else:
                    logger.warning(
                        f"[DEBUG] Abstract search returned no chunks above threshold {threshold}"
                    )

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
        logger.error(f"Abstract semantic search failed: {e}", exc_info=True)
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

        # Get validated OpenAthens proxy URL if enabled (prevents SSRF attacks)
        openathens_url = None
        if use_proxy:
            openathens_url = get_validated_openathens_url(config)

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
    proxy_callback_timeout: Optional[float] = None,
    model: Optional[str] = None,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    temperature: float = DEFAULT_TEMPERATURE,
    ollama_host: Optional[str] = None,
    use_adaptive_search: bool = True,
    search_mode: str = "expanded",
    semantic_weight: float = DEFAULT_SEMANTIC_WEIGHT,
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
        proxy_callback_timeout: Maximum seconds to wait for proxy_callback to
            return. For GUI applications this can be None (no timeout).
            For programmatic use, set a timeout (e.g., 30 seconds) to prevent
            indefinite hanging. Defaults to 300 seconds (5 minutes) if not specified.
        model: LLM model for answer generation. Uses config default if None.
        max_chunks: Maximum number of context chunks to use. Default 5.
        similarity_threshold: Minimum semantic similarity (0.0-1.0). Default 0.5.
            Can be overridden via config["agents"]["document_qa"]["similarity_threshold"].
            Lower values (0.3-0.5) capture more results but may include noise.
            Higher values (0.6-0.8) are stricter but may miss relevant content.
        temperature: LLM temperature for generation. Default 0.3.
        ollama_host: Ollama server URL. Uses config default if None.
        use_adaptive_search: If True (default), use SemanticQueryAgent for adaptive
            threshold adjustment and query rephrasing. This automatically:
            - Lowers threshold if no results are found
            - Raises threshold if too many results
            - Rephrases query up to 3 times if needed
            If False, uses a single fixed-threshold search.
        search_mode: Search mode to use when use_adaptive_search=True:
            - "expanded" (default): Hybrid search with query expansion - best accuracy
            - "hybrid": Semantic + keyword search with RRF fusion
            - "semantic": Pure semantic similarity search (baseline)
        semantic_weight: Weight for semantic vs keyword in hybrid modes (0.0-1.0).
            Higher values favor semantic similarity, lower favor keyword matching.
            Default 0.6.

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

    # If similarity_threshold is at default, check config for override
    # This allows config-based customization while respecting explicit parameters
    if similarity_threshold == DEFAULT_SIMILARITY_THRESHOLD:
        config_threshold = qa_config.get("similarity_threshold")
        if config_threshold is not None:
            similarity_threshold = float(config_threshold)
            logger.debug(
                f"[DEBUG] Using config similarity_threshold={similarity_threshold}"
            )

    logger.info(
        f"[DEBUG] answer_from_document: doc_id={document_id}, "
        f"threshold={similarity_threshold}, max_chunks={max_chunks}, model={model}"
    )

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
    fallback_reason: Optional[str] = None  # Track why full-text wasn't used

    # Resolve callback timeout
    callback_timeout = (
        proxy_callback_timeout
        if proxy_callback_timeout is not None
        else DEFAULT_PROXY_CALLBACK_TIMEOUT
    )

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
                fallback_reason = FALLBACK_OPEN_ACCESS_FAILED

                if always_allow_proxy:
                    # Auto-consent: use proxy directly without asking
                    logger.info(f"Using proxy automatically for document {document_id}")
                    if _download_fulltext_if_needed(document_id, db_manager, use_proxy=True):
                        status = _get_document_text_status(document_id, db_manager)
                        fallback_reason = None  # Success - no fallback
                    else:
                        # Proxy download failed
                        logger.warning(f"Proxy download failed for document {document_id}")
                        fallback_reason = FALLBACK_PROXY_FAILED

                elif proxy_callback is not None:
                    # Ask user via callback (with timeout)
                    doc_title = status.title or _get_document_title(document_id, db_manager)
                    logger.info(f"Invoking proxy callback for document {document_id}")

                    callback_result, timed_out = _invoke_proxy_callback_with_timeout(
                        proxy_callback, document_id, doc_title, callback_timeout
                    )

                    if timed_out:
                        # Callback timed out - fall back to abstract
                        logger.warning(f"Proxy callback timed out for document {document_id}")
                        fallback_reason = FALLBACK_CALLBACK_TIMEOUT

                    elif callback_result is None:
                        # Callback raised an exception
                        logger.warning(f"Proxy callback failed for document {document_id}")
                        fallback_reason = FALLBACK_NO_PROXY_CONFIGURED

                    elif callback_result.pdf_made_available:
                        # User uploaded PDF manually - refresh status
                        # Use retry loop in case embedding takes time
                        logger.info(f"PDF made available externally for document {document_id}")
                        for retry in range(MAX_PDF_AVAILABILITY_RETRIES):
                            status = _get_document_text_status(document_id, db_manager)
                            if status and status.has_fulltext:
                                logger.info(f"Full-text now available for document {document_id}")
                                fallback_reason = None  # Success - no fallback
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
                            # Keep fallback_reason as FALLBACK_OPEN_ACCESS_FAILED

                    elif callback_result.allow_proxy:
                        # User consented to proxy - try OpenAthens
                        logger.info(f"User consented to proxy for document {document_id}")
                        if _download_fulltext_if_needed(document_id, db_manager, use_proxy=True):
                            status = _get_document_text_status(document_id, db_manager)
                            fallback_reason = None  # Success - no fallback
                        else:
                            # Proxy download failed
                            logger.warning(f"Proxy download failed for document {document_id}")
                            fallback_reason = FALLBACK_PROXY_FAILED
                    else:
                        # User declined both options
                        logger.info(f"User declined proxy/upload for document {document_id}")
                        fallback_reason = FALLBACK_USER_DECLINED
                else:
                    # No callback provided and not auto-allow → skip proxy, fall back to abstract
                    fallback_reason = FALLBACK_NO_PROXY_CONFIGURED

        if status.has_fulltext:
            # Ensure embeddings exist
            if not status.has_fulltext_chunks:
                logger.info(f"Generating embeddings for document {document_id}")
                if _embed_fulltext_if_needed(document_id, db_manager):
                    status.has_fulltext_chunks = True
                else:
                    # Embedding failed
                    if fallback_reason is None:
                        fallback_reason = FALLBACK_NO_FULLTEXT_CHUNKS

            if status.has_fulltext_chunks:
                # Perform full-text semantic search
                if use_adaptive_search:
                    # Use SemanticQueryAgent for adaptive threshold and query rephrasing
                    # Determine search mode
                    if search_mode == "expanded":
                        agent_search_mode = SearchMode.HYBRID
                        use_expansion = True
                    elif search_mode == "hybrid":
                        agent_search_mode = SearchMode.HYBRID
                        use_expansion = False
                    else:  # "semantic"
                        agent_search_mode = SearchMode.SEMANTIC
                        use_expansion = False

                    agent = SemanticQueryAgent(
                        initial_threshold=similarity_threshold,
                        default_search_mode=agent_search_mode,
                        semantic_weight=semantic_weight,
                    )

                    if use_expansion:
                        # Use expanded hybrid search (best accuracy)
                        search_result: SemanticSearchResult = agent.search_with_expansion(
                            document_id=document_id,
                            query=question,
                            min_results=1,
                            max_results=max_chunks,
                            use_fulltext=True,
                            db_manager=db_manager,
                            search_mode=agent_search_mode,
                            semantic_weight=semantic_weight,
                        )
                    else:
                        # Use standard search (semantic or hybrid without expansion)
                        search_result: SemanticSearchResult = agent.search_document(
                            document_id=document_id,
                            query=question,
                            min_results=1,
                            max_results=max_chunks,
                            use_fulltext=True,
                            db_manager=db_manager,
                            search_mode=agent_search_mode,
                            semantic_weight=semantic_weight,
                        )

                    if search_result.success and search_result.chunks:
                        chunks = [
                            ChunkContext(
                                chunk_id=c.chunk_id,
                                chunk_no=c.chunk_no,
                                score=c.score,
                                text=c.text,
                            )
                            for c in search_result.chunks
                        ]
                        # Include hybrid stats if available
                        hybrid_info = ""
                        if search_result.search_mode == SearchMode.HYBRID:
                            stats = search_result.hybrid_stats
                            if stats:
                                hybrid_info = (
                                    f", hybrid_stats={{semantic:{stats.get('semantic_only', 0)}, "
                                    f"keyword:{stats.get('keyword_only', 0)}, "
                                    f"both:{stats.get('both', 0)}}}"
                                )
                        logger.info(
                            f"[AdaptiveSearch] Found {len(chunks)} chunks after "
                            f"{search_result.iterations} iterations, "
                            f"threshold={search_result.threshold_used:.2f}, "
                            f"mode={search_result.search_mode.value}, "
                            f"queries tried: {len(search_result.queries_tried)}"
                            f"{hybrid_info}"
                        )
                    else:
                        logger.warning(
                            f"[AdaptiveSearch] Failed after {search_result.iterations} "
                            f"iterations: {search_result.message}"
                        )
                        chunks = []
                else:
                    # Use fixed-threshold search
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
                    fallback_reason = None  # Success - no fallback
            else:
                # No chunks despite having full-text
                if fallback_reason is None:
                    fallback_reason = FALLBACK_NO_FULLTEXT_CHUNKS

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
                logger.info(
                    f"Using abstract for document {document_id}"
                    + (f" (reason: {fallback_reason})" if fallback_reason else "")
                )
            else:
                return SemanticSearchAnswer(
                    answer="",
                    error=QAError.NO_TEXT_AVAILABLE,
                    error_message="Abstract is too short or unavailable",
                    document_id=document_id,
                    question=question,
                    model_used=model,
                    fallback_reason=fallback_reason,
                )
        else:
            return SemanticSearchAnswer(
                answer="",
                error=QAError.NO_FULLTEXT,
                error_message="No full-text available and no abstract fallback",
                document_id=document_id,
                question=question,
                model_used=model,
                fallback_reason=fallback_reason,
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
            fallback_reason=fallback_reason,
        )

    return SemanticSearchAnswer(
        answer=answer,
        reasoning=reasoning,
        source=source,
        chunks_used=chunks,
        document_id=document_id,
        question=question,
        model_used=model,
        fallback_reason=fallback_reason,
    )
