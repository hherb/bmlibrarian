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
import time
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from bmlibrarian.database import get_db_manager

logger = logging.getLogger(__name__)

try:
    import ollama
except ImportError:
    logger.warning("ollama not installed. Embedding generation will not be available.")
    ollama = None

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
        if not ollama:
            raise ImportError("ollama package required for embedding generation. Install with: pip install ollama")

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
        """Verify that the model is available in Ollama."""
        try:
            models = ollama.list()
            model_names = [model['model'] for model in models.get('models', [])]

            if self.model_name not in model_names:
                logger.warning(f"Model {self.model_name} not found. Attempting to pull...")
                ollama.pull(self.model_name)
                logger.info(f"Successfully pulled model {self.model_name}")
        except Exception as e:
            logger.error(f"Error verifying model: {e}")
            raise

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
            response = ollama.embeddings(model=self.model_name, prompt=text)

            if 'embedding' in response:
                embedding = response['embedding']

                # Set embedding dimension from first embedding
                if self.embedding_dimension is None:
                    self.embedding_dimension = len(embedding)
                    logger.info(f"Model embedding dimension: {self.embedding_dimension}")

                return embedding
            else:
                logger.error(f"Unexpected response format from Ollama: {response}")
                return []
        except Exception as e:
            logger.error(f"Error creating embedding: {e}")
            return []

    def _get_documents_without_embeddings(self, source_name: Optional[str] = None,
                                         limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get documents that don't have embeddings yet.

        Args:
            source_name: Filter by source name (e.g., 'medrxiv', 'pubmed')
            limit: Maximum number of documents to return

        Returns:
            List of document dictionaries
        """
        query = """
            SELECT DISTINCT d.id, d.title, d.abstract, d.full_text, s.name as source_name
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

        query += " ORDER BY d.id"

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                columns = [desc[0] for desc in cur.description]
                results = []
                for row in cur.fetchall():
                    results.append(dict(zip(columns, row)))
                return results

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
            batch_size: Number of documents to process before committing

        Returns:
            Dictionary with statistics: {'total_processed': int, 'embedded_count': int, 'failed_count': int}
        """
        documents = self._get_documents_without_embeddings(source_name, limit)

        if not documents:
            logger.info("No documents found that need embedding")
            return {'total_processed': 0, 'embedded_count': 0, 'failed_count': 0}

        logger.info(f"Found {len(documents)} documents to embed")

        embedded_count = 0
        failed_count = 0

        if tqdm:
            progress = tqdm(documents, desc="Embedding documents", unit="doc")
        else:
            progress = documents

        for doc in progress:
            doc_id = doc['id']
            title = doc.get('title', '')
            abstract = doc.get('abstract', '')

            if not abstract or abstract.strip() == '':
                logger.debug(f"Skipping document {doc_id}: no abstract")
                failed_count += 1
                continue

            try:
                # Generate embedding
                start_time = time.time()
                embedding = self.create_embedding(abstract)
                embedding_time = time.time() - start_time

                if not embedding:
                    logger.warning(f"Failed to create embedding for document {doc_id}")
                    failed_count += 1
                    continue

                # Store chunk and embedding
                chunk_id = self._store_chunk_and_embedding(doc_id, title, abstract, embedding)

                if chunk_id:
                    embedded_count += 1
                    if tqdm:
                        progress.set_postfix({
                            'embedded': embedded_count,
                            'failed': failed_count,
                            'time': f'{embedding_time:.2f}s'
                        })
                else:
                    failed_count += 1

            except Exception as e:
                logger.error(f"Error embedding document {doc_id}: {e}")
                failed_count += 1

        logger.info(f"Embedding complete: {embedded_count} embedded, {failed_count} failed out of {len(documents)} total")

        return {
            'total_processed': len(documents),
            'embedded_count': embedded_count,
            'failed_count': failed_count
        }

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
