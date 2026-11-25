"""
Document Embedder for BMLibrarian

This module provides functionality to create embeddings for documents in the database.
It uses Ollama for generating embeddings and stores them in the appropriate embedding tables.

Example usage:
    from bmlibrarian.embeddings import DocumentEmbedder

    embedder = DocumentEmbedder(model_name="snowflake-arctic-embed2:latest")
    stats = embedder.embed_documents(source_name='medrxiv', limit=100)
    print(f"Embedded {stats['embedded_count']} documents")
"""

import logging
from typing import List, Dict, Any, Optional

from bmlibrarian.config import get_ollama_host
from bmlibrarian.database import get_db_manager
from bmlibrarian.llm import LLMClient, list_ollama_models

logger = logging.getLogger(__name__)

try:
    from tqdm import tqdm
except ImportError:
    logger.warning("tqdm not installed. Progress bars will not be displayed.")
    tqdm = None


class DocumentEmbedder:
    """
    Document embedder for creating and storing vector embeddings.

    This class handles the complete workflow:
    1. Fetches documents without embeddings
    2. Creates chunks from document text
    3. Generates embeddings using Ollama
    4. Stores chunks and embeddings in database
    """

    def __init__(self, model_name: str = "snowflake-arctic-embed2:latest"):
        """
        Initialize the document embedder.

        Args:
            model_name: Name of the Ollama embedding model to use
        """
        # Resolve the host explicitly rather than letting each side pick its
        # own default: list_ollama_models() reads it from the bmlibrarian
        # config, while an unconfigured LLMClient falls back to OLLAMA_HOST.
        # Left implicit, verification and embedding can address different
        # servers — the model is found on one and missing from the other.
        self.host = get_ollama_host()
        self._llm_client = LLMClient(track_usage=False, ollama_host=self.host)
        self.db_manager = get_db_manager()
        self.model_name = model_name
        self.embedding_dimension = None  # Will be determined from first embedding
        self.model_id = None  # Will be set when model is registered
        self.chunking_strategy_id = None  # Will be set for abstract chunking
        self.chunktype_id = None  # Will be set for abstract chunk type

        # Verify model is available
        self._verify_model()

        # Get or create model ID
        self._register_model()

        # Get or create chunking strategy and chunk type IDs
        self._setup_chunking_strategy()

        logger.info(f"DocumentEmbedder initialized with model: {model_name}")

    def _verify_model(self):
        """
        Verify that the embedding model is available on the server.

        Previously this auto-pulled a missing model. That relied on
        ollama.pull(), which the LLM abstraction does not expose, and it
        started a multi-gigabyte download as an implicit side effect of
        constructing an embedder. A missing model is now reported with
        the command to fix it.

        Raises:
            RuntimeError: If the configured model is not on the server
            ConnectionError: If the server cannot be reached. Allowed to
                propagate: an embedder that cannot reach its server has
                nothing useful to do, and failing here names the cause
                rather than leaving every later embed call to fail.
        """
        available = list_ollama_models(self.host)

        if not available:
            logger.warning(
                "Server at %s reports no models, so %s could not be verified; "
                "continuing, embedding calls will fail if it is missing.",
                self.host,
                self.model_name,
            )
            return

        if self.model_name not in available:
            raise RuntimeError(
                f"Embedding model '{self.model_name}' is not available on the "
                f"Ollama server. Install it with:\n\n"
                f"    ollama pull {self.model_name}\n"
            )

    def _register_model(self):
        """Register the model in the embedding_models table."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Check if model exists
                cur.execute("""
                    SELECT id FROM embedding_models WHERE model_name = %s
                """, (self.model_name,))

                result = cur.fetchone()
                if result:
                    self.model_id = result[0]
                    logger.debug(f"Using existing model ID: {self.model_id}")
                else:
                    # Get Ollama provider_id (or create it)
                    cur.execute("""
                        INSERT INTO embedding_provider (provider_name, base_url)
                        VALUES ('ollama', 'http://localhost:11434')
                        ON CONFLICT (provider_name) DO UPDATE
                        SET base_url = EXCLUDED.base_url
                        RETURNING id
                    """)
                    provider_id = cur.fetchone()[0]

                    # Insert model
                    cur.execute("""
                        INSERT INTO embedding_models (provider_id, model_name, model_description)
                        VALUES (%s, %s, %s)
                        RETURNING id
                    """, (provider_id, self.model_name, f"Ollama model: {self.model_name}"))

                    self.model_id = cur.fetchone()[0]
                    logger.info(f"Registered new model with ID: {self.model_id}")

    def _setup_chunking_strategy(self):
        """Set up chunking strategy and chunk type for abstracts."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Get or create chunking strategy for abstracts
                cur.execute("""
                    INSERT INTO chunking_strategies (strategy_name, modelname, parameters)
                    VALUES ('abstract_single_chunk', 'none', '{"description": "Single chunk for entire abstract"}')
                    ON CONFLICT (strategy_name) DO UPDATE
                    SET strategy_name = EXCLUDED.strategy_name
                    RETURNING id
                """)
                self.chunking_strategy_id = cur.fetchone()[0]

                # Get or create chunk type for abstracts
                cur.execute("""
                    INSERT INTO chunktypes (chunktype)
                    VALUES ('abstract')
                    ON CONFLICT (chunktype) DO UPDATE
                    SET chunktype = EXCLUDED.chunktype
                    RETURNING id
                """)
                self.chunktype_id = cur.fetchone()[0]

                logger.debug(f"Chunking strategy ID: {self.chunking_strategy_id}, Chunk type ID: {self.chunktype_id}")

    def create_embedding(self, text: str) -> List[float]:
        """
        Create an embedding for the given text using Ollama.

        Args:
            text: Text to embed

        Returns:
            Vector embedding as a list of floats
        """
        try:
            embedding = self._llm_client.embed(
                text=text, model=self.model_name,
            ).embedding

            if embedding:

                # Set embedding dimension from first embedding
                if self.embedding_dimension is None:
                    self.embedding_dimension = len(embedding)
                    logger.info(f"Model embedding dimension: {self.embedding_dimension}")

                return embedding
            else:
                logger.error(
                    "Model %s returned an empty embedding for a %d-character text",
                    self.model_name,
                    len(text),
                )
                return []
        except Exception as e:
            logger.error(f"Error creating embedding: {e}")
            return []

    def _get_documents_without_embeddings(self, source_name: Optional[str] = None,
                                         limit: Optional[int] = None,
                                         after_id: int = 0) -> List[Dict[str, Any]]:
        """
        Get one page of documents that don't have embeddings yet.

        Pages by document ID (keyset paging), so a full-corpus run never holds
        more than one page in memory. Only the columns that are embedded are
        fetched (no full text).

        Args:
            source_name: Filter by source name (e.g., 'medrxiv', 'pubmed')
            limit: Maximum number of documents to return (None for all)
            after_id: Only return documents with an ID greater than this

        Returns:
            List of document dictionaries, ordered by ID
        """
        query = """
            SELECT DISTINCT d.id, d.title, d.abstract, s.name as source_name
            FROM document d
            LEFT JOIN sources s ON d.source_id = s.id
            LEFT JOIN chunks c ON d.id = c.document_id
            LEFT JOIN embedding_base eb ON c.id = eb.chunk_id AND eb.model_id = %s
            WHERE d.abstract IS NOT NULL
            AND d.abstract != ''
            AND eb.id IS NULL
            AND d.id > %s
        """

        params: List[Any] = [self.model_id, after_id]

        if source_name:
            query += " AND LOWER(s.name) LIKE %s"
            params.append(f'%{source_name.lower()}%')

        query += " ORDER BY d.id"

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                columns = [desc[0] for desc in cur.description]
                return [dict(zip(columns, row)) for row in cur.fetchall()]

    def _store_chunk_and_embedding(self, document_id: int, document_title: str,
                                   text: str, embedding: List[float]) -> Optional[int]:
        """
        Store a chunk and its embedding in the database.

        Args:
            document_id: Document ID
            document_title: Document title
            text: Chunk text
            embedding: Embedding vector

        Returns:
            Chunk ID if successful, None otherwise
        """
        # Determine which embedding table to use
        embedding_table = f"emb_{self.embedding_dimension}"
        if embedding_table not in ['emb_768', 'emb_1024']:
            logger.error(f"Unsupported embedding dimension: {self.embedding_dimension}")
            return None

        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    # Check if chunk already exists
                    cur.execute("""
                        SELECT id FROM chunks
                        WHERE document_id = %s
                        AND chunking_strategy_id = %s
                        AND chunk_no = 0
                    """, (document_id, self.chunking_strategy_id))

                    existing_chunk = cur.fetchone()

                    if existing_chunk:
                        chunk_id = existing_chunk[0]
                        logger.debug(f"Using existing chunk ID: {chunk_id}")
                    else:
                        # Insert chunk
                        cur.execute("""
                            INSERT INTO chunks (
                                document_id, chunking_strategy_id, chunktype_id,
                                document_title, text, chunklength, chunk_no
                            ) VALUES (%s, %s, %s, %s, %s, %s, 0)
                            RETURNING id
                        """, (
                            document_id,
                            self.chunking_strategy_id,
                            self.chunktype_id,
                            document_title,
                            text,
                            len(text)
                        ))

                        chunk_id = cur.fetchone()[0]
                        logger.debug(f"Created new chunk ID: {chunk_id}")

                    # Check if embedding already exists
                    cur.execute(f"""
                        SELECT id FROM {embedding_table}
                        WHERE chunk_id = %s AND model_id = %s
                    """, (chunk_id, self.model_id))

                    if cur.fetchone():
                        logger.debug(f"Embedding already exists for chunk {chunk_id}")
                        return chunk_id

                    # Insert embedding
                    embedding_str = '[' + ','.join(map(str, embedding)) + ']'
                    cur.execute(f"""
                        INSERT INTO {embedding_table} (chunk_id, model_id, embedding)
                        VALUES (%s, %s, %s)
                    """, (chunk_id, self.model_id, embedding_str))

                    logger.debug(f"Stored embedding for chunk {chunk_id}")
                    return chunk_id

        except Exception as e:
            logger.error(f"Error storing chunk and embedding: {e}")
            return None

    def embed_documents(self, source_name: Optional[str] = None, limit: Optional[int] = None,
                       batch_size: int = 100) -> Dict[str, int]:
        """
        Embed documents that don't have embeddings yet.

        Args:
            source_name: Filter by source name (e.g., 'medrxiv', 'pubmed')
            limit: Maximum number of documents to embed
            batch_size: Number of documents fetched from the database per page

        Returns:
            Dictionary with statistics: {'total_processed': int, 'embedded_count': int, 'failed_count': int}
        """
        if batch_size < 1:
            raise ValueError(f"batch_size must be at least 1, got {batch_size}")

        total_processed = 0
        embedded_count = 0
        failed_count = 0
        last_id = 0
        progress = tqdm(total=limit, desc="Embedding documents", unit="doc") if tqdm else None

        try:
            while limit is None or total_processed < limit:
                page_size = batch_size if limit is None else min(batch_size, limit - total_processed)
                documents = self._get_documents_without_embeddings(
                    source_name, page_size, after_id=last_id
                )
                if not documents:
                    break
                # Failed documents stay "without embeddings"; moving past their IDs
                # means they are retried on the next run, not in an endless loop.
                last_id = documents[-1]['id']

                for doc in documents:
                    total_processed += 1
                    if self._embed_document(doc):
                        embedded_count += 1
                    else:
                        failed_count += 1
                    if progress is not None:
                        progress.update(1)
                        progress.set_postfix({'embedded': embedded_count, 'failed': failed_count})
        finally:
            if progress is not None:
                progress.close()

        if total_processed == 0:
            logger.info("No documents found that need embedding")
        else:
            logger.info(
                f"Embedding complete: {embedded_count} embedded, {failed_count} failed "
                f"out of {total_processed} total"
            )

        return {
            'total_processed': total_processed,
            'embedded_count': embedded_count,
            'failed_count': failed_count
        }

    def _embed_document(self, doc: Dict[str, Any]) -> bool:
        """
        Embed one document's abstract and store it.

        Args:
            doc: Document dictionary with 'id', 'title' and 'abstract'

        Returns:
            True if the embedding was stored, False otherwise (logged)
        """
        doc_id = doc['id']
        title = doc.get('title') or ''
        abstract = doc.get('abstract') or ''

        if not abstract.strip():
            logger.debug(f"Skipping document {doc_id}: no abstract")
            return False

        try:
            embedding = self.create_embedding(abstract)
            if not embedding:
                logger.warning(f"Failed to create embedding for document {doc_id}")
                return False
            return self._store_chunk_and_embedding(doc_id, title, abstract, embedding) is not None
        except Exception as e:
            logger.error(f"Error embedding document {doc_id}: {e}")
            return False

    def count_documents_without_embeddings(self, source_name: Optional[str] = None) -> int:
        """
        Count documents that don't have embeddings yet.

        Args:
            source_name: Filter by source name (e.g., 'medrxiv', 'pubmed')

        Returns:
            Number of documents without embeddings
        """
        query = """
            SELECT COUNT(DISTINCT d.id)
            FROM document d
            LEFT JOIN sources s ON d.source_id = s.id
            LEFT JOIN chunks c ON d.id = c.document_id
            LEFT JOIN embedding_base eb ON c.id = eb.chunk_id AND eb.model_id = %s
            WHERE d.abstract IS NOT NULL
            AND d.abstract != ''
            AND eb.id IS NULL
        """

        params = [self.model_id]

        if source_name:
            query += " AND LOWER(s.name) LIKE %s"
            params.append(f'%{source_name.lower()}%')

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                count = cur.fetchone()[0]
                return count
