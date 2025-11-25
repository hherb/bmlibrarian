"""
Chunk Embedder for BMLibrarian.

Provides functionality for chunking document text and generating embeddings
for storage in the semantic.chunks table.

The chunking strategy uses adaptive sentence-boundary-aware splitting with
configurable overlap to ensure semantic continuity across chunk boundaries.

Supports two embedding backends:
- "ollama": Uses Ollama's API (default, requires running Ollama server)
- "llama_cpp": Uses llama-cpp-python for direct GGUF inference (more stable)

Example usage:
    from bmlibrarian.embeddings.chunk_embedder import ChunkEmbedder

    # Using Ollama (default)
    embedder = ChunkEmbedder()
    num_chunks = embedder.chunk_and_embed(document_id=12345)

    # Using llama.cpp directly (more stable for bulk operations)
    embedder = ChunkEmbedder(backend="llama_cpp", model_path="/path/to/model.gguf")
    num_chunks = embedder.chunk_and_embed(document_id=12345)

    # Or use the pure function directly
    from bmlibrarian.embeddings.adaptive_chunker_optimized import adaptive_chunker_with_positions
    chunks = adaptive_chunker_with_positions("Long document text...", max_chars=1800, overlap_chars=320)
    for chunk in chunks:
        print(f"Chunk {chunk.chunk_no}: [{chunk.start_pos}:{chunk.end_pos}] {chunk.text[:50]}...")
"""

import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional, Callable, Literal

from bmlibrarian.database import get_db_manager
from bmlibrarian.embeddings.adaptive_chunker_optimized import adaptive_chunker_with_positions

logger = logging.getLogger(__name__)

try:
    import ollama
except ImportError:
    logger.warning("ollama not installed. Ollama backend will not be available.")
    ollama = None

# Type alias for backend selection
EmbeddingBackend = Literal["ollama", "ollama_http", "llama_cpp", "sentence_transformers"]

# Default chunking parameters (aligned with adaptive_chunker_optimized defaults)
DEFAULT_CHUNK_SIZE = 1800
DEFAULT_CHUNK_OVERLAP = 320
DEFAULT_EMBEDDING_MODEL_ID = 1
DEFAULT_EMBEDDING_MODEL_NAME = "snowflake-arctic-embed2:latest"
EMBEDDING_DIMENSION = 1024

# Queue processing constants
# Ollama embedding can be unstable under load - use generous retries
MAX_RETRY_ATTEMPTS = 5
RETRY_BASE_DELAY = 2.0  # Base delay in seconds (doubles each retry)

# Batch processing - process multiple chunks in one API call for efficiency
DEFAULT_BATCH_SIZE = 10  # Number of chunks to embed in one batch


@dataclass
class ChunkPosition:
    """
    Represents a chunk's position within a document.

    Attributes:
        chunk_no: Sequential chunk number (0-indexed).
        start_pos: Start position in the source text (0-indexed).
        end_pos: End position in the source text (inclusive).
    """

    chunk_no: int
    start_pos: int
    end_pos: int

    @property
    def length(self) -> int:
        """Return the length of the chunk in characters."""
        return self.end_pos - self.start_pos + 1

    def extract_text(self, source_text: str) -> str:
        """
        Extract the chunk text from the source.

        Args:
            source_text: The full source text.

        Returns:
            The chunk text.
        """
        return source_text[self.start_pos : self.end_pos + 1]


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[ChunkPosition]:
    """
    Split text into overlapping chunks.

    This is a pure function that calculates chunk positions without
    modifying any state. The actual text extraction happens when needed.

    Args:
        text: The text to chunk.
        chunk_size: Target size of each chunk in characters.
        overlap: Number of overlapping characters between consecutive chunks.

    Returns:
        List of ChunkPosition objects with start/end positions.

    Raises:
        ValueError: If parameters are invalid.

    Example:
        >>> text = "This is a sample text for chunking demonstration."
        >>> chunks = chunk_text(text, chunk_size=20, overlap=5)
        >>> for chunk in chunks:
        ...     print(f"[{chunk.start_pos}:{chunk.end_pos}] = '{chunk.extract_text(text)}'")
    """
    # Validate parameters
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    if overlap < 0:
        raise ValueError(f"overlap cannot be negative, got {overlap}")
    if overlap >= chunk_size:
        raise ValueError(
            f"overlap ({overlap}) must be less than chunk_size ({chunk_size})"
        )

    if not text:
        return []

    text_length = len(text)
    chunks: List[ChunkPosition] = []
    chunk_no = 0
    start_pos = 0

    # Calculate step size (how much to advance for each new chunk)
    step = chunk_size - overlap

    while start_pos < text_length:
        # Calculate end position (inclusive)
        end_pos = min(start_pos + chunk_size - 1, text_length - 1)

        chunks.append(
            ChunkPosition(chunk_no=chunk_no, start_pos=start_pos, end_pos=end_pos)
        )

        # If this chunk reached the end of text, we're done
        if end_pos >= text_length - 1:
            break

        chunk_no += 1
        start_pos += step

        # Avoid creating a tiny final chunk that's smaller than overlap
        # If remaining text is smaller than overlap, the previous chunk covers it
        if text_length - start_pos < overlap:
            break

    return chunks


class ChunkEmbedder:
    """
    Handles chunking and embedding of document full text.

    Uses the semantic.chunks table for storage, with embeddings
    generated via Ollama or llama-cpp-python.

    Supports four backends:
    - "ollama": Uses Ollama Python library API (default)
    - "ollama_http": Uses raw HTTP requests to Ollama (most stable, recommended)
    - "sentence_transformers": Uses sentence-transformers library (slow startup)
    - "llama_cpp": Uses llama-cpp-python for direct GGUF inference
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL_NAME,
        model_id: Optional[int] = None,
        backend: EmbeddingBackend = "ollama",
        model_path: Optional[str] = None,
        n_ctx: int = 8192,
    ) -> None:
        """
        Initialize the chunk embedder.

        Args:
            model_name: Embedding model name (for Ollama or database reference).
            model_id: Database model ID (if known). If None, will be looked up.
            backend: Embedding backend to use ("ollama", "ollama_http", "sentence_transformers", or "llama_cpp").
            model_path: Path to GGUF model file (required for llama_cpp backend).
                       If None with llama_cpp, will try to find Ollama's cached model.
            n_ctx: Context window size for llama_cpp backend (default: 8192).

        Raises:
            ImportError: If required backend is not installed.
            FileNotFoundError: If model_path doesn't exist (llama_cpp backend).
        """
        self.backend = backend
        self.db_manager = get_db_manager()
        self.model_name = model_name
        self._llama_embedder = None
        self._st_embedder = None
        self._http_embedder = None

        if backend == "ollama":
            if not ollama:
                raise ImportError(
                    "ollama package required for ollama backend. "
                    "Install with: pip install ollama"
                )
        elif backend == "ollama_http":
            self._init_ollama_http(model_name)
        elif backend == "sentence_transformers":
            self._init_sentence_transformers(model_name)
        elif backend == "llama_cpp":
            self._init_llama_cpp(model_name, model_path, n_ctx)
        else:
            raise ValueError(
                f"Unknown backend: {backend}. "
                f"Use 'ollama', 'ollama_http', 'sentence_transformers', or 'llama_cpp'."
            )

        self.model_id = model_id or self._get_or_create_model_id()

        logger.info(
            f"ChunkEmbedder initialized with model: {model_name} "
            f"(id={self.model_id}, backend={backend})"
        )

    def _init_llama_cpp(
        self, model_name: str, model_path: Optional[str], n_ctx: int
    ) -> None:
        """
        Initialize the llama.cpp backend.

        Args:
            model_name: Model name (used to find Ollama cache if model_path is None).
            model_path: Explicit path to GGUF file, or None to auto-detect.
            n_ctx: Context window size.
        """
        from bmlibrarian.embeddings.llama_cpp_embedder import (
            LlamaCppEmbedder,
            find_ollama_model_path,
        )

        # If no model_path provided, try to find Ollama's cached model
        if model_path is None:
            model_path = find_ollama_model_path(model_name)
            if model_path is None:
                raise FileNotFoundError(
                    f"Could not find GGUF model for '{model_name}'. "
                    f"Either provide model_path explicitly or ensure the model "
                    f"is pulled via Ollama first: ollama pull {model_name}"
                )

        self._llama_embedder = LlamaCppEmbedder(
            model_path=model_path,
            n_ctx=n_ctx,
            verbose=False,
        )

    def _init_ollama_http(self, model_name: str) -> None:
        """
        Initialize the Ollama HTTP backend using raw requests.

        Args:
            model_name: Ollama model name.
        """
        from bmlibrarian.embeddings.embedding_server import EmbeddingServer

        self._http_embedder = EmbeddingServer(model=model_name)

        # Verify server is available
        if not self._http_embedder.is_available():
            raise ConnectionError(
                f"Ollama server not available at {self._http_embedder.config.base_url}. "
                f"Ensure Ollama is running."
            )

    def _init_sentence_transformers(self, model_name: str) -> None:
        """
        Initialize the sentence-transformers backend.

        Args:
            model_name: Model name (Ollama-style or HuggingFace-style).
        """
        from bmlibrarian.embeddings.sentence_transformer_embedder import (
            SentenceTransformerEmbedder,
            get_hf_model_name,
        )

        # Convert Ollama model name to HuggingFace model name if needed
        hf_model_name = get_hf_model_name(model_name)

        self._st_embedder = SentenceTransformerEmbedder(
            model_name=hf_model_name,
            trust_remote_code=True,
        )

    def _get_or_create_model_id(self) -> int:
        """
        Get the model ID from database, creating if necessary.

        Returns:
            The database model ID.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Check if model exists
                cur.execute(
                    "SELECT id FROM embedding_models WHERE model_name = %s",
                    (self.model_name,),
                )
                result = cur.fetchone()

                if result:
                    return result[0]

                # Create model entry
                cur.execute(
                    """
                    INSERT INTO embedding_models (provider_id, model_name, model_description)
                    VALUES (
                        (SELECT id FROM embedding_provider WHERE provider_name = 'ollama'),
                        %s,
                        %s
                    )
                    RETURNING id
                    """,
                    (self.model_name, f"Ollama embedding model: {self.model_name}"),
                )
                model_id = cur.fetchone()[0]
                logger.info(f"Created embedding model entry with ID: {model_id}")
                return model_id

    def create_embedding(
        self, text: str, max_retries: int = MAX_RETRY_ATTEMPTS
    ) -> Optional[List[float]]:
        """
        Generate embedding vector for text.

        Uses the configured backend (ollama or llama_cpp).

        Args:
            text: Text to embed.
            max_retries: Maximum number of retry attempts on failure (ollama only).

        Returns:
            Embedding vector as list of floats, or None on failure.
        """
        if not text or not text.strip():
            logger.warning("Cannot create embedding for empty text")
            return None

        if self.backend == "sentence_transformers":
            return self._create_embedding_sentence_transformers(text)
        elif self.backend == "llama_cpp":
            return self._create_embedding_llama_cpp(text)
        elif self.backend == "ollama_http":
            return self._create_embedding_ollama_http(text)
        else:
            return self._create_embedding_ollama(text, max_retries)

    def _create_embedding_llama_cpp(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding using llama.cpp backend.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector as list of floats, or None on failure.
        """
        if self._llama_embedder is None:
            logger.error("LlamaCpp embedder not initialized")
            return None

        embedding = self._llama_embedder.embed(text)

        if embedding and len(embedding) != EMBEDDING_DIMENSION:
            logger.warning(
                f"Unexpected embedding dimension: {len(embedding)}, "
                f"expected {EMBEDDING_DIMENSION}"
            )

        return embedding

    def _create_embedding_sentence_transformers(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding using sentence-transformers backend.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector as list of floats, or None on failure.
        """
        if self._st_embedder is None:
            logger.error("SentenceTransformer embedder not initialized")
            return None

        embedding = self._st_embedder.embed(text)

        if embedding and len(embedding) != EMBEDDING_DIMENSION:
            logger.warning(
                f"Unexpected embedding dimension: {len(embedding)}, "
                f"expected {EMBEDDING_DIMENSION}"
            )

        return embedding

    def _create_embedding_ollama_http(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding using Ollama HTTP backend.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector as list of floats, or None on failure.
        """
        if self._http_embedder is None:
            logger.error("Ollama HTTP embedder not initialized")
            return None

        embedding = self._http_embedder.embed(text)

        if embedding and len(embedding) != EMBEDDING_DIMENSION:
            logger.warning(
                f"Unexpected embedding dimension: {len(embedding)}, "
                f"expected {EMBEDDING_DIMENSION}"
            )

        return embedding

    def _create_embedding_ollama(
        self, text: str, max_retries: int
    ) -> Optional[List[float]]:
        """
        Generate embedding using Ollama backend with retry logic.

        Args:
            text: Text to embed.
            max_retries: Maximum number of retry attempts on failure.

        Returns:
            Embedding vector as list of floats, or None on failure.
        """
        import time

        if ollama is None:
            logger.error("Ollama library not available")
            return None

        for attempt in range(max_retries):
            try:
                response = ollama.embeddings(model=self.model_name, prompt=text)
                embedding = response.get("embedding")

                if embedding:
                    if len(embedding) != EMBEDDING_DIMENSION:
                        logger.warning(
                            f"Unexpected embedding dimension: {len(embedding)}, "
                            f"expected {EMBEDDING_DIMENSION}"
                        )
                    return embedding

                logger.error(f"No embedding in Ollama response: {response}")

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = RETRY_BASE_DELAY * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Embedding attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"Embedding generation failed after {max_retries} attempts: {e}"
                    )

        return None

    def create_embeddings_batch(
        self, texts: List[str], max_retries: int = MAX_RETRY_ATTEMPTS
    ) -> List[Optional[List[float]]]:
        """
        Generate embedding vectors for multiple texts.

        For llama_cpp backend: processes texts sequentially (stable).
        For ollama backend: uses batch API with retry logic.

        Args:
            texts: List of texts to embed.
            max_retries: Maximum number of retry attempts on failure (ollama only).

        Returns:
            List of embedding vectors (or None for failed texts), same length as input.
        """
        if not texts:
            return []

        if self.backend == "sentence_transformers":
            return self._create_embeddings_batch_sentence_transformers(texts)
        elif self.backend == "llama_cpp":
            return self._create_embeddings_batch_llama_cpp(texts)
        elif self.backend == "ollama_http":
            return self._create_embeddings_batch_ollama_http(texts)
        else:
            return self._create_embeddings_batch_ollama(texts, max_retries)

    def _create_embeddings_batch_llama_cpp(
        self, texts: List[str]
    ) -> List[Optional[List[float]]]:
        """
        Generate batch embeddings using llama.cpp backend.

        Processes texts sequentially - very stable, no network issues.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors (or None for failed texts).
        """
        if self._llama_embedder is None:
            logger.error("LlamaCpp embedder not initialized")
            return [None] * len(texts)

        return self._llama_embedder.embed_batch(texts)

    def _create_embeddings_batch_sentence_transformers(
        self, texts: List[str]
    ) -> List[Optional[List[float]]]:
        """
        Generate batch embeddings using sentence-transformers backend.

        sentence-transformers handles batching efficiently internally.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors (or None for failed texts).
        """
        if self._st_embedder is None:
            logger.error("SentenceTransformer embedder not initialized")
            return [None] * len(texts)

        return self._st_embedder.embed_batch(texts)

    def _create_embeddings_batch_ollama_http(
        self, texts: List[str]
    ) -> List[Optional[List[float]]]:
        """
        Generate batch embeddings using Ollama HTTP backend.

        Uses native batch embedding via /api/embed endpoint.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors (or None for failed texts).
        """
        if self._http_embedder is None:
            logger.error("Ollama HTTP embedder not initialized")
            return [None] * len(texts)

        return self._http_embedder.embed_batch(texts)

    def _create_embeddings_batch_ollama(
        self, texts: List[str], max_retries: int
    ) -> List[Optional[List[float]]]:
        """
        Generate batch embeddings using Ollama backend with retry logic.

        Args:
            texts: List of texts to embed.
            max_retries: Maximum number of retry attempts on failure.

        Returns:
            List of embedding vectors (or None for failed texts).
        """
        import time

        if ollama is None:
            logger.error("Ollama library not available")
            return [None] * len(texts)

        # Filter out empty texts and track their positions
        valid_texts = []
        valid_indices = []
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)

        if not valid_texts:
            logger.warning("All texts in batch are empty")
            return [None] * len(texts)

        # Retry loop for the batch
        for attempt in range(max_retries):
            try:
                # Use the newer embed() API which supports batching
                response = ollama.embed(model=self.model_name, input=valid_texts)
                embeddings = response.get("embeddings", [])

                if len(embeddings) == len(valid_texts):
                    # Build result list with None for invalid texts
                    result: List[Optional[List[float]]] = [None] * len(texts)
                    for idx, embedding in zip(valid_indices, embeddings):
                        if len(embedding) != EMBEDDING_DIMENSION:
                            logger.warning(
                                f"Unexpected embedding dimension: {len(embedding)}, "
                                f"expected {EMBEDDING_DIMENSION}"
                            )
                        result[idx] = embedding
                    return result

                logger.error(
                    f"Batch embedding count mismatch: got {len(embeddings)}, "
                    f"expected {len(valid_texts)}"
                )

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"Batch embedding attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"Batch embedding failed after {max_retries} attempts: {e}"
                    )

        return [None] * len(texts)

    def has_chunks(
        self,
        document_id: int,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> bool:
        """
        Check if document already has chunks with specified parameters.

        Args:
            document_id: Document database ID.
            chunk_size: Chunk size to check for.
            overlap: Chunk overlap to check for.

        Returns:
            True if chunks exist, False otherwise.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT semantic.has_chunks(%s, %s, %s, %s)
                    """,
                    (document_id, self.model_id, chunk_size, overlap),
                )
                result = cur.fetchone()
                return result[0] if result else False

    def get_document_full_text(self, document_id: int) -> Optional[str]:
        """
        Retrieve document full_text from database.

        Args:
            document_id: Document database ID.

        Returns:
            The full_text content, or None if not found or empty.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT full_text FROM public.document
                    WHERE id = %s AND full_text IS NOT NULL AND full_text != ''
                    """,
                    (document_id,),
                )
                result = cur.fetchone()
                return result[0] if result else None

    def delete_existing_chunks(
        self,
        document_id: int,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> int:
        """
        Delete existing chunks for a document with specified parameters.

        Args:
            document_id: Document database ID.
            chunk_size: Chunk size to match.
            overlap: Chunk overlap to match.

        Returns:
            Number of chunks deleted.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT semantic.delete_chunks(%s, %s, %s, %s)
                    """,
                    (document_id, self.model_id, chunk_size, overlap),
                )
                result = cur.fetchone()
                deleted = result[0] if result else 0
                if deleted > 0:
                    logger.info(
                        f"Deleted {deleted} existing chunks for document {document_id}"
                    )
                return deleted

    def chunk_and_embed(
        self,
        document_id: int,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
        overwrite: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> int:
        """
        Chunk document full_text and generate embeddings using batch processing.

        Uses batch embedding API calls for improved efficiency and stability.

        Args:
            document_id: Document database ID.
            chunk_size: Target chunk size in characters.
            overlap: Overlap between consecutive chunks.
            overwrite: If True, delete existing chunks first.
                      If False, skip if chunks already exist.
            progress_callback: Optional callback(current, total) for progress updates.
            batch_size: Number of chunks to embed in each API call.

        Returns:
            Number of chunks created (0 if failed or skipped).

        Raises:
            ValueError: If chunk parameters are invalid.
        """
        # Validate parameters
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {chunk_size}")
        if overlap < 0:
            raise ValueError(f"overlap cannot be negative, got {overlap}")
        if overlap >= chunk_size:
            raise ValueError(f"overlap ({overlap}) must be less than chunk_size ({chunk_size})")

        # Check for existing chunks
        if not overwrite and self.has_chunks(document_id, chunk_size, overlap):
            logger.info(
                f"Document {document_id} already has chunks with these parameters, skipping"
            )
            return 0

        # Get document full_text
        full_text = self.get_document_full_text(document_id)
        if not full_text:
            logger.warning(f"Document {document_id} has no full_text, skipping")
            return 0

        # Calculate chunk positions using adaptive sentence-aware chunker
        chunk_positions = adaptive_chunker_with_positions(
            full_text, max_chars=chunk_size, overlap_chars=overlap
        )
        if not chunk_positions:
            logger.warning(f"No chunks generated for document {document_id}")
            return 0

        total_chunks = len(chunk_positions)
        logger.info(
            f"Processing document {document_id}: {total_chunks} chunks "
            f"(size={chunk_size}, overlap={overlap})"
        )

        # Delete existing chunks if overwriting
        if overwrite:
            self.delete_existing_chunks(document_id, chunk_size, overlap)

        # Generate embeddings in batches and store chunks
        chunks_created = 0

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Process chunks in batches
                for batch_start in range(0, total_chunks, batch_size):
                    batch_end = min(batch_start + batch_size, total_chunks)
                    batch_chunks = chunk_positions[batch_start:batch_end]

                    # Report progress (at batch level)
                    if progress_callback:
                        progress_callback(batch_end, total_chunks)

                    # Extract texts for batch embedding
                    batch_texts = [chunk.text for chunk in batch_chunks]

                    # Generate embeddings for the batch
                    embeddings = self.create_embeddings_batch(batch_texts)

                    # Store each chunk with its embedding
                    for chunk_pos, embedding in zip(batch_chunks, embeddings):
                        if not embedding:
                            logger.warning(
                                f"Failed to generate embedding for chunk {chunk_pos.chunk_no} "
                                f"of document {document_id}"
                            )
                            continue

                        # Store chunk with embedding
                        try:
                            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
                            cur.execute(
                                """
                                INSERT INTO semantic.chunks (
                                    document_id, model_id, chunk_size, chunk_overlap,
                                    chunk_no, start_pos, end_pos, embedding
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (document_id, model_id, chunk_size, chunk_overlap, chunk_no)
                                DO UPDATE SET
                                    start_pos = EXCLUDED.start_pos,
                                    end_pos = EXCLUDED.end_pos,
                                    embedding = EXCLUDED.embedding,
                                    created_at = NOW()
                                """,
                                (
                                    document_id,
                                    self.model_id,
                                    chunk_size,
                                    overlap,
                                    chunk_pos.chunk_no,
                                    chunk_pos.start_pos,
                                    chunk_pos.end_pos,
                                    embedding_str,
                                ),
                            )
                            chunks_created += 1

                        except Exception as e:
                            logger.error(
                                f"Failed to store chunk {chunk_pos.chunk_no} "
                                f"of document {document_id}: {e}"
                            )
                            # Continue with other chunks

        logger.info(
            f"Document {document_id}: created {chunks_created}/{total_chunks} chunks"
        )
        return chunks_created

    def process_queue(
        self,
        batch_size: int = 100,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Tuple[int, int]:
        """
        Process documents from the chunk queue.

        Args:
            batch_size: Maximum number of documents to process.
            chunk_size: Chunk size to use.
            overlap: Chunk overlap to use.
            progress_callback: Optional callback(stage, current, total) for progress.

        Returns:
            Tuple of (processed_count, failed_count).
        """
        # Get queued documents
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT document_id
                    FROM semantic.chunk_queue
                    WHERE attempts < %s
                    ORDER BY priority DESC, queued_at ASC
                    LIMIT %s
                    """,
                    (MAX_RETRY_ATTEMPTS, batch_size),
                )
                queued_docs = [row[0] for row in cur.fetchall()]

        if not queued_docs:
            logger.info("No documents in chunk queue")
            return (0, 0)

        total_docs = len(queued_docs)
        logger.info(f"Processing {total_docs} documents from queue")

        processed = 0
        failed = 0

        for i, document_id in enumerate(queued_docs):
            if progress_callback:
                progress_callback("chunking", i + 1, total_docs)

            try:
                num_chunks = self.chunk_and_embed(
                    document_id=document_id,
                    chunk_size=chunk_size,
                    overlap=overlap,
                    overwrite=True,
                )

                if num_chunks > 0:
                    # Success - remove from queue
                    self._remove_from_queue(document_id)
                    processed += 1
                else:
                    # No chunks created (e.g., no full_text)
                    self._update_queue_error(
                        document_id, "No chunks created (empty full_text?)"
                    )
                    failed += 1

            except Exception as e:
                logger.error(f"Failed to process document {document_id}: {e}")
                self._update_queue_error(document_id, str(e))
                failed += 1

        logger.info(f"Queue processing complete: {processed} processed, {failed} failed")
        return (processed, failed)

    def _remove_from_queue(self, document_id: int) -> None:
        """Remove document from chunk queue after successful processing."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM semantic.chunk_queue WHERE document_id = %s",
                    (document_id,),
                )

    def _update_queue_error(self, document_id: int, error: str) -> None:
        """Update queue entry with error information."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE semantic.chunk_queue
                    SET attempts = attempts + 1,
                        last_error = %s,
                        last_attempt_at = NOW()
                    WHERE document_id = %s
                    """,
                    (error[:1000], document_id),  # Truncate error to avoid overflow
                )

    def rechunk_all(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> dict:
        """
        Re-chunk all documents in semantic.chunks with new chunking parameters.

        This method:
        1. Saves unique document IDs from semantic.chunks to a temp table
        2. Truncates semantic.chunks (clears data but preserves HNSW index)
        3. Re-chunks each document using adaptive_chunker_with_positions
        4. Reports statistics

        Args:
            chunk_size: Target chunk size in characters (default: 1800).
            overlap: Overlap between consecutive chunks (default: 320).
            progress_callback: Optional callback(stage, current, total) for progress.
            batch_size: Number of chunks to embed per API call (default: 10).

        Returns:
            Dictionary with statistics:
                - total_documents: Number of documents to process
                - processed: Successfully processed documents
                - failed: Failed documents
                - total_chunks_created: Total chunks created
                - elapsed_seconds: Total time taken
                - chunks_per_second: Processing rate
                - avg_chunks_per_doc: Average chunks per document
        """
        import time

        stats = {
            "total_documents": 0,
            "processed": 0,
            "failed": 0,
            "total_chunks_created": 0,
            "elapsed_seconds": 0.0,
            "chunks_per_second": 0.0,
            "avg_chunks_per_doc": 0.0,
        }

        # Step 1: Get unique document IDs and save to temp table
        logger.info("Step 1: Collecting document IDs from semantic.chunks...")
        if progress_callback:
            progress_callback("collecting_ids", 0, 0)

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # First check if semantic.chunks has any data
                cur.execute("SELECT COUNT(*) FROM semantic.chunks")
                result = cur.fetchone()
                chunks_count = result[0] if result else 0

                if chunks_count > 0:
                    # Re-chunk mode: get document IDs from existing chunks
                    logger.info("Re-chunk mode: getting document IDs from semantic.chunks")
                    cur.execute("""
                        CREATE TEMP TABLE IF NOT EXISTS rechunk_doc_ids AS
                        SELECT DISTINCT document_id FROM semantic.chunks
                    """)
                else:
                    # Initial population mode: get document IDs from public.document
                    logger.info(
                        "Initial population mode: semantic.chunks is empty, "
                        "getting document IDs from public.document"
                    )
                    cur.execute("""
                        CREATE TEMP TABLE IF NOT EXISTS rechunk_doc_ids AS
                        SELECT id AS document_id FROM public.document
                        WHERE full_text IS NOT NULL AND full_text != ''
                    """)

                # Get count
                cur.execute("SELECT COUNT(*) FROM rechunk_doc_ids")
                result = cur.fetchone()
                total_docs = result[0] if result else 0
                stats["total_documents"] = total_docs

                if total_docs == 0:
                    logger.warning("No documents found to process")
                    return stats

                logger.info(f"Found {total_docs} documents to rechunk")

                # Step 2: Truncate semantic.chunks
                logger.info("Step 2: Truncating semantic.chunks table...")
                if progress_callback:
                    progress_callback("truncating", 0, total_docs)

                cur.execute("TRUNCATE TABLE semantic.chunks")
                logger.info("semantic.chunks truncated (HNSW index preserved but empty)")

                # Step 3: Fetch document IDs
                cur.execute("SELECT document_id FROM rechunk_doc_ids ORDER BY document_id")
                document_ids = [row[0] for row in cur.fetchall()]

                # Clean up temp table
                cur.execute("DROP TABLE IF EXISTS rechunk_doc_ids")

        # Step 4: Re-chunk each document
        logger.info(f"Step 3: Re-chunking {total_docs} documents...")
        start_time = time.perf_counter()

        for i, doc_id in enumerate(document_ids):
            if progress_callback:
                progress_callback("chunking", i + 1, total_docs)

            try:
                num_chunks = self.chunk_and_embed(
                    document_id=doc_id,
                    chunk_size=chunk_size,
                    overlap=overlap,
                    overwrite=False,  # Table already truncated
                    batch_size=batch_size,
                )

                if num_chunks > 0:
                    stats["processed"] += 1
                    stats["total_chunks_created"] += num_chunks
                else:
                    stats["failed"] += 1
                    logger.warning(f"Document {doc_id}: no chunks created")

            except Exception as e:
                stats["failed"] += 1
                logger.error(f"Document {doc_id}: rechunk failed - {e}")

        # Calculate final statistics
        elapsed = time.perf_counter() - start_time
        stats["elapsed_seconds"] = round(elapsed, 2)

        if elapsed > 0:
            stats["chunks_per_second"] = round(stats["total_chunks_created"] / elapsed, 2)

        if stats["processed"] > 0:
            stats["avg_chunks_per_doc"] = round(
                stats["total_chunks_created"] / stats["processed"], 2
            )

        logger.info(
            f"Rechunk complete: {stats['processed']}/{total_docs} documents, "
            f"{stats['total_chunks_created']} chunks in {stats['elapsed_seconds']}s"
        )

        return stats

    def chunk_document_list(
        self,
        document_ids: List[int],
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_CHUNK_OVERLAP,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        overwrite: bool = True,
    ) -> dict:
        """
        Chunk and embed a specific list of documents.

        Unlike rechunk_all, this does NOT truncate the table - it only processes
        the specified documents, optionally overwriting existing chunks.

        Args:
            document_ids: List of document IDs to process.
            chunk_size: Target chunk size in characters (default: 1800).
            overlap: Overlap between consecutive chunks (default: 320).
            progress_callback: Optional callback(stage, current, total) for progress.
            batch_size: Number of chunks to embed per API call (default: 10).
            overwrite: If True, delete existing chunks for these documents first.

        Returns:
            Dictionary with statistics:
                - total_documents: Number of documents to process
                - processed: Successfully processed documents
                - failed: Failed documents
                - total_chunks_created: Total chunks created
                - elapsed_seconds: Total time taken
                - chunks_per_second: Processing rate
                - avg_chunks_per_doc: Average chunks per document
        """
        import time

        stats = {
            "total_documents": len(document_ids),
            "processed": 0,
            "failed": 0,
            "total_chunks_created": 0,
            "elapsed_seconds": 0.0,
            "chunks_per_second": 0.0,
            "avg_chunks_per_doc": 0.0,
        }

        if not document_ids:
            logger.warning("No document IDs provided")
            return stats

        total_docs = len(document_ids)
        logger.info(f"Processing {total_docs} documents")

        if progress_callback:
            progress_callback("starting", 0, total_docs)

        start_time = time.perf_counter()

        for i, doc_id in enumerate(document_ids):
            if progress_callback:
                progress_callback("chunking", i + 1, total_docs)

            try:
                num_chunks = self.chunk_and_embed(
                    document_id=doc_id,
                    chunk_size=chunk_size,
                    overlap=overlap,
                    overwrite=overwrite,
                    batch_size=batch_size,
                )

                if num_chunks > 0:
                    stats["processed"] += 1
                    stats["total_chunks_created"] += num_chunks
                else:
                    stats["failed"] += 1
                    logger.warning(f"Document {doc_id}: no chunks created")

            except Exception as e:
                stats["failed"] += 1
                logger.error(f"Document {doc_id}: chunk failed - {e}")

        # Calculate final statistics
        elapsed = time.perf_counter() - start_time
        stats["elapsed_seconds"] = round(elapsed, 2)

        if elapsed > 0:
            stats["chunks_per_second"] = round(stats["total_chunks_created"] / elapsed, 2)

        if stats["processed"] > 0:
            stats["avg_chunks_per_doc"] = round(
                stats["total_chunks_created"] / stats["processed"], 2
            )

        logger.info(
            f"Chunk complete: {stats['processed']}/{total_docs} documents, "
            f"{stats['total_chunks_created']} chunks in {stats['elapsed_seconds']}s"
        )

        return stats
