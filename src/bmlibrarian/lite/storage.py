"""
Unified storage layer for BMLibrarian Lite.

Combines ChromaDB for vector storage and SQLite for structured metadata.
All data is persisted to the configured data directory.

Usage:
    from bmlibrarian.lite import LiteConfig
    from bmlibrarian.lite.storage import LiteStorage

    config = LiteConfig.load()
    storage = LiteStorage(config)

    # Add documents
    storage.add_document(doc, embedding_function=embed_fn)

    # Search by semantic similarity
    results = storage.search_documents("query", embedding_function=embed_fn)
"""

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from .config import LiteConfig
from .constants import (
    CHROMA_CHUNKS_COLLECTION,
    CHROMA_DOCUMENTS_COLLECTION,
    PUBMED_CACHE_TTL_SECONDS,
)
from .data_models import (
    DocumentSource,
    LiteDocument,
    ReviewCheckpoint,
    SearchSession,
)
from .exceptions import ChromaDBError, SQLiteError, LiteStorageError

logger = logging.getLogger(__name__)


class LiteStorage:
    """
    Unified storage layer for BMLibrarian Lite.

    Provides:
    - ChromaDB collections for vector storage (documents, chunks)
    - SQLite database for structured metadata (sessions, checkpoints)
    - Unified API for all storage operations

    All data is persisted to ~/.bmlibrarian_lite/ by default.
    """

    def __init__(self, config: Optional[LiteConfig] = None) -> None:
        """
        Initialize storage layer.

        Args:
            config: Configuration object. If None, uses defaults.
        """
        self.config = config or LiteConfig()
        self._storage_config = self.config.storage

        # Ensure directories exist
        self.config.ensure_directories()

        # Initialize ChromaDB
        self._chroma_client = self._init_chroma()

        # Initialize SQLite
        self._init_sqlite()

        logger.info(f"LiteStorage initialized at {self._storage_config.data_dir}")

    def _init_chroma(self) -> chromadb.PersistentClient:
        """
        Initialize ChromaDB client with persistent storage.

        Returns:
            ChromaDB PersistentClient

        Raises:
            ChromaDBError: If ChromaDB initialization fails
        """
        try:
            settings = ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
            )
            client = chromadb.PersistentClient(
                path=str(self._storage_config.chroma_dir),
                settings=settings,
            )
            logger.debug(f"ChromaDB initialized at {self._storage_config.chroma_dir}")
            return client
        except Exception as e:
            raise ChromaDBError(
                f"Failed to initialize ChromaDB at {self._storage_config.chroma_dir}: {e}"
            ) from e

    def _init_sqlite(self) -> None:
        """
        Initialize SQLite database with schema.

        Raises:
            SQLiteError: If SQLite initialization fails
        """
        try:
            with self._sqlite_connection() as conn:
                conn.executescript(self._get_sqlite_schema())
                conn.commit()
            logger.debug(f"SQLite initialized at {self._storage_config.sqlite_path}")
        except sqlite3.Error as e:
            raise SQLiteError(
                f"Failed to initialize SQLite at {self._storage_config.sqlite_path}: {e}"
            ) from e

    @contextmanager
    def _sqlite_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for SQLite connections.

        Yields:
            SQLite connection with Row factory
        """
        conn = sqlite3.connect(
            self._storage_config.sqlite_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _get_sqlite_schema(self) -> str:
        """
        Return SQLite schema definition.

        Uses CREATE IF NOT EXISTS for idempotency.

        Returns:
            SQL schema string
        """
        return """
        -- Search sessions
        CREATE TABLE IF NOT EXISTS search_sessions (
            id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            natural_language_query TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            document_count INTEGER DEFAULT 0,
            metadata TEXT DEFAULT '{}'
        );

        -- Review checkpoints
        CREATE TABLE IF NOT EXISTS review_checkpoints (
            id TEXT PRIMARY KEY,
            research_question TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            step TEXT DEFAULT 'start',
            search_session_id TEXT,
            report TEXT,
            metadata TEXT DEFAULT '{}',
            FOREIGN KEY (search_session_id) REFERENCES search_sessions(id)
        );

        -- Scored documents (linked to checkpoints)
        CREATE TABLE IF NOT EXISTS scored_documents (
            id TEXT PRIMARY KEY,
            checkpoint_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
            explanation TEXT,
            scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (checkpoint_id) REFERENCES review_checkpoints(id)
        );

        -- Citations (linked to checkpoints)
        CREATE TABLE IF NOT EXISTS citations (
            id TEXT PRIMARY KEY,
            checkpoint_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            passage TEXT NOT NULL,
            relevance_score INTEGER,
            context TEXT,
            FOREIGN KEY (checkpoint_id) REFERENCES review_checkpoints(id)
        );

        -- User settings
        CREATE TABLE IF NOT EXISTS user_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- PubMed cache
        CREATE TABLE IF NOT EXISTS pubmed_cache (
            query_hash TEXT PRIMARY KEY,
            response TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        );

        -- Interrogation sessions
        CREATE TABLE IF NOT EXISTS interrogation_sessions (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            document_title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            messages TEXT DEFAULT '[]',
            metadata TEXT DEFAULT '{}'
        );

        -- Create indexes for common queries
        CREATE INDEX IF NOT EXISTS idx_search_sessions_created
            ON search_sessions(created_at);
        CREATE INDEX IF NOT EXISTS idx_checkpoints_updated
            ON review_checkpoints(updated_at);
        CREATE INDEX IF NOT EXISTS idx_scored_docs_checkpoint
            ON scored_documents(checkpoint_id);
        CREATE INDEX IF NOT EXISTS idx_citations_checkpoint
            ON citations(checkpoint_id);
        CREATE INDEX IF NOT EXISTS idx_pubmed_cache_expires
            ON pubmed_cache(expires_at);
        CREATE INDEX IF NOT EXISTS idx_interrogation_sessions_created
            ON interrogation_sessions(created_at);
        """

    # =========================================================================
    # ChromaDB Collection Management
    # =========================================================================

    def get_documents_collection(self, embedding_function: Any = None) -> Any:
        """
        Get or create the documents collection.

        Args:
            embedding_function: ChromaDB embedding function (e.g., FastEmbed)

        Returns:
            ChromaDB collection for documents
        """
        return self._chroma_client.get_or_create_collection(
            name=CHROMA_DOCUMENTS_COLLECTION,
            embedding_function=embedding_function,
            metadata={"description": "PubMed and local documents"},
        )

    def get_chunks_collection(self, embedding_function: Any = None) -> Any:
        """
        Get or create the chunks collection.

        Args:
            embedding_function: ChromaDB embedding function (e.g., FastEmbed)

        Returns:
            ChromaDB collection for document chunks
        """
        return self._chroma_client.get_or_create_collection(
            name=CHROMA_CHUNKS_COLLECTION,
            embedding_function=embedding_function,
            metadata={"description": "Document chunks for interrogation"},
        )

    # =========================================================================
    # Document Operations
    # =========================================================================

    def add_document(
        self,
        document: LiteDocument,
        embedding_function: Any = None,
    ) -> str:
        """
        Add a document to the storage.

        Args:
            document: Document to add
            embedding_function: Optional embedding function

        Returns:
            Document ID

        Raises:
            ChromaDBError: If ChromaDB upsert fails

        Example:
            from bmlibrarian.lite.chroma_embeddings import create_embedding_function

            embed_fn = create_embedding_function()
            doc = LiteDocument(
                id="pmid-12345",
                title="Example Study",
                abstract="This study examines...",
                authors=["Smith J", "Jones A"],
                year=2023,
            )
            doc_id = storage.add_document(doc, embedding_function=embed_fn)
        """
        try:
            collection = self.get_documents_collection(embedding_function)

            metadata = {
                "title": document.title,
                "authors": json.dumps(document.authors),
                "year": document.year or 0,
                "journal": document.journal or "",
                "doi": document.doi or "",
                "pmid": document.pmid or "",
                "pmc_id": document.pmc_id or "",
                "url": document.url or "",
                "mesh_terms": json.dumps(document.mesh_terms),
                "source": document.source.value,
            }
            # Add custom metadata
            for key, value in document.metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    metadata[key] = value

            collection.upsert(
                ids=[document.id],
                documents=[document.abstract],
                metadatas=[metadata],
            )

            logger.debug(f"Added document {document.id} to storage")
            return document.id
        except Exception as e:
            raise ChromaDBError(f"Failed to add document {document.id}: {e}") from e

    def add_documents(
        self,
        documents: list[LiteDocument],
        embedding_function: Any = None,
    ) -> list[str]:
        """
        Add multiple documents to storage.

        Args:
            documents: List of documents to add
            embedding_function: Optional embedding function

        Returns:
            List of document IDs

        Raises:
            ChromaDBError: If ChromaDB upsert fails

        Example:
            docs = [doc1, doc2, doc3]
            ids = storage.add_documents(docs, embedding_function=embed_fn)
            print(f"Added {len(ids)} documents")
        """
        if not documents:
            return []

        try:
            collection = self.get_documents_collection(embedding_function)

            ids = [doc.id for doc in documents]
            texts = [doc.abstract for doc in documents]
            metadatas = []

            for doc in documents:
                metadata = {
                    "title": doc.title,
                    "authors": json.dumps(doc.authors),
                    "year": doc.year or 0,
                    "journal": doc.journal or "",
                    "doi": doc.doi or "",
                    "pmid": doc.pmid or "",
                    "pmc_id": doc.pmc_id or "",
                    "url": doc.url or "",
                    "mesh_terms": json.dumps(doc.mesh_terms),
                    "source": doc.source.value,
                }
                metadatas.append(metadata)

            collection.upsert(ids=ids, documents=texts, metadatas=metadatas)

            logger.info(f"Added {len(documents)} documents to storage")
            return ids
        except Exception as e:
            raise ChromaDBError(f"Failed to add {len(documents)} documents: {e}") from e

    def get_document(
        self,
        document_id: str,
        embedding_function: Any = None,
    ) -> Optional[LiteDocument]:
        """
        Retrieve a document by ID.

        Args:
            document_id: Document ID to retrieve
            embedding_function: Optional embedding function

        Returns:
            Document if found, None otherwise

        Raises:
            ChromaDBError: If ChromaDB query fails (not for missing documents)

        Example:
            doc = storage.get_document("pmid-12345678", embed_fn)
            if doc:
                print(f"Found: {doc.title}")
            else:
                print("Document not found")
        """
        try:
            collection = self.get_documents_collection(embedding_function)

            result = collection.get(
                ids=[document_id],
                include=["documents", "metadatas"],
            )

            if not result["ids"]:
                return None

            metadata = result["metadatas"][0]
            return LiteDocument(
                id=document_id,
                title=metadata.get("title", ""),
                abstract=result["documents"][0],
                authors=json.loads(metadata.get("authors", "[]")),
                year=metadata.get("year") or None,
                journal=metadata.get("journal") or None,
                doi=metadata.get("doi") or None,
                pmid=metadata.get("pmid") or None,
                pmc_id=metadata.get("pmc_id") or None,
                url=metadata.get("url") or None,
                mesh_terms=json.loads(metadata.get("mesh_terms", "[]")),
                source=DocumentSource(metadata.get("source", "pubmed")),
            )
        except Exception as e:
            logger.error(f"Failed to get document {document_id}: {e}")
            raise ChromaDBError(f"Failed to get document {document_id}: {e}") from e

    def get_documents(
        self,
        document_ids: list[str],
        embedding_function: Any = None,
    ) -> list[LiteDocument]:
        """
        Retrieve multiple documents by ID.

        Args:
            document_ids: List of document IDs
            embedding_function: Optional embedding function

        Returns:
            List of found documents (may be fewer than requested)

        Raises:
            ChromaDBError: If ChromaDB query fails

        Example:
            ids = ["pmid-123", "pmid-456", "pmid-789"]
            docs = storage.get_documents(ids, embed_fn)
            for doc in docs:
                print(f"{doc.id}: {doc.title}")
        """
        if not document_ids:
            return []

        try:
            collection = self.get_documents_collection(embedding_function)

            result = collection.get(
                ids=document_ids,
                include=["documents", "metadatas"],
            )

            documents = []
            for i, doc_id in enumerate(result["ids"]):
                metadata = result["metadatas"][i]
                documents.append(LiteDocument(
                    id=doc_id,
                    title=metadata.get("title", ""),
                    abstract=result["documents"][i],
                    authors=json.loads(metadata.get("authors", "[]")),
                    year=metadata.get("year") or None,
                    journal=metadata.get("journal") or None,
                    doi=metadata.get("doi") or None,
                    pmid=metadata.get("pmid") or None,
                    pmc_id=metadata.get("pmc_id") or None,
                    url=metadata.get("url") or None,
                    mesh_terms=json.loads(metadata.get("mesh_terms", "[]")),
                    source=DocumentSource(metadata.get("source", "pubmed")),
                ))

            return documents
        except Exception as e:
            logger.error(f"Failed to get documents: {e}")
            raise ChromaDBError(f"Failed to get {len(document_ids)} documents: {e}") from e

    def search_documents(
        self,
        query: str,
        n_results: int = 20,
        embedding_function: Any = None,
    ) -> list[LiteDocument]:
        """
        Search documents by semantic similarity.

        Uses ChromaDB's built-in vector search to find documents
        with abstracts most similar to the query text.

        Args:
            query: Search query (natural language)
            n_results: Maximum number of results
            embedding_function: Optional embedding function

        Returns:
            List of matching documents ordered by similarity

        Raises:
            ChromaDBError: If ChromaDB query fails

        Example:
            # Find documents about heart disease
            results = storage.search_documents(
                query="cardiovascular disease treatment",
                n_results=10,
                embedding_function=embed_fn
            )
            for doc in results:
                print(f"[{doc.year}] {doc.title}")
        """
        try:
            collection = self.get_documents_collection(embedding_function)

            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )

            documents = []
            for i, doc_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i]
                documents.append(LiteDocument(
                    id=doc_id,
                    title=metadata.get("title", ""),
                    abstract=results["documents"][0][i],
                    authors=json.loads(metadata.get("authors", "[]")),
                    year=metadata.get("year") or None,
                    journal=metadata.get("journal") or None,
                    doi=metadata.get("doi") or None,
                    pmid=metadata.get("pmid") or None,
                    pmc_id=metadata.get("pmc_id") or None,
                    url=metadata.get("url") or None,
                    mesh_terms=json.loads(metadata.get("mesh_terms", "[]")),
                    source=DocumentSource(metadata.get("source", "pubmed")),
                ))

            return documents
        except Exception as e:
            raise ChromaDBError(f"Semantic search failed for query: {e}") from e

    def delete_document(
        self,
        document_id: str,
        embedding_function: Any = None,
    ) -> bool:
        """
        Delete a document from storage.

        Args:
            document_id: Document ID to delete
            embedding_function: Optional embedding function

        Returns:
            True if deleted, False otherwise
        """
        collection = self.get_documents_collection(embedding_function)

        try:
            collection.delete(ids=[document_id])
            logger.debug(f"Deleted document {document_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            return False

    # =========================================================================
    # Search Session Operations
    # =========================================================================

    def create_search_session(
        self,
        query: str,
        natural_language_query: str,
        document_count: int = 0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SearchSession:
        """
        Create a new search session.

        Records a PubMed search for history and reproducibility.

        Args:
            query: PubMed query string
            natural_language_query: Original natural language query
            document_count: Number of documents found
            metadata: Optional metadata

        Returns:
            Created search session

        Raises:
            SQLiteError: If database insert fails

        Example:
            session = storage.create_search_session(
                query="diabetes[MeSH] AND treatment",
                natural_language_query="How is diabetes treated?",
                document_count=42,
            )
            print(f"Session ID: {session.id}")
        """
        session_id = str(uuid.uuid4())
        now = datetime.now()

        try:
            with self._sqlite_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO search_sessions
                    (id, query, natural_language_query, created_at, document_count, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        query,
                        natural_language_query,
                        now,
                        document_count,
                        json.dumps(metadata or {}),
                    ),
                )
                conn.commit()

            return SearchSession(
                id=session_id,
                query=query,
                natural_language_query=natural_language_query,
                created_at=now,
                document_count=document_count,
                metadata=metadata or {},
            )
        except sqlite3.Error as e:
            raise SQLiteError(f"Failed to create search session: {e}") from e

    def get_search_sessions(self, limit: int = 50) -> list[SearchSession]:
        """
        Get recent search sessions.

        Args:
            limit: Maximum number of sessions to return

        Returns:
            List of search sessions, most recent first
        """
        with self._sqlite_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, query, natural_language_query, created_at,
                       document_count, metadata
                FROM search_sessions
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )

            sessions = []
            for row in cursor:
                sessions.append(SearchSession(
                    id=row["id"],
                    query=row["query"],
                    natural_language_query=row["natural_language_query"],
                    created_at=row["created_at"],
                    document_count=row["document_count"],
                    metadata=json.loads(row["metadata"]),
                ))

            return sessions

    def get_search_session(self, session_id: str) -> Optional[SearchSession]:
        """
        Get a search session by ID.

        Args:
            session_id: Session ID

        Returns:
            Search session if found, None otherwise
        """
        with self._sqlite_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, query, natural_language_query, created_at,
                       document_count, metadata
                FROM search_sessions
                WHERE id = ?
                """,
                (session_id,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            return SearchSession(
                id=row["id"],
                query=row["query"],
                natural_language_query=row["natural_language_query"],
                created_at=row["created_at"],
                document_count=row["document_count"],
                metadata=json.loads(row["metadata"]),
            )

    # =========================================================================
    # Review Checkpoint Operations
    # =========================================================================

    def create_checkpoint(
        self,
        research_question: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ReviewCheckpoint:
        """
        Create a new review checkpoint.

        Creates a checkpoint to track systematic review progress.
        Use update_checkpoint() to update step and data.

        Args:
            research_question: The research question
            metadata: Optional metadata

        Returns:
            Created checkpoint

        Raises:
            SQLiteError: If database insert fails

        Example:
            checkpoint = storage.create_checkpoint(
                research_question="What are the effects of exercise on depression?"
            )
            print(f"Checkpoint ID: {checkpoint.id}")
            # Later: update progress
            storage.update_checkpoint(checkpoint.id, step="scoring")
        """
        checkpoint_id = str(uuid.uuid4())
        now = datetime.now()

        try:
            with self._sqlite_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO review_checkpoints
                    (id, research_question, created_at, updated_at, step, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        checkpoint_id,
                        research_question,
                        now,
                        now,
                        "start",
                        json.dumps(metadata or {}),
                    ),
                )
                conn.commit()

            return ReviewCheckpoint(
                id=checkpoint_id,
                research_question=research_question,
                created_at=now,
                updated_at=now,
                step="start",
                metadata=metadata or {},
            )
        except sqlite3.Error as e:
            raise SQLiteError(f"Failed to create checkpoint: {e}") from e

    def update_checkpoint(
        self,
        checkpoint_id: str,
        step: Optional[str] = None,
        search_session_id: Optional[str] = None,
        report: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Update a review checkpoint.

        Args:
            checkpoint_id: Checkpoint ID to update
            step: New workflow step
            search_session_id: Associated search session
            report: Generated report text
            metadata: Updated metadata
        """
        updates = ["updated_at = ?"]
        values: list[Any] = [datetime.now()]

        if step is not None:
            updates.append("step = ?")
            values.append(step)
        if search_session_id is not None:
            updates.append("search_session_id = ?")
            values.append(search_session_id)
        if report is not None:
            updates.append("report = ?")
            values.append(report)
        if metadata is not None:
            updates.append("metadata = ?")
            values.append(json.dumps(metadata))

        values.append(checkpoint_id)

        with self._sqlite_connection() as conn:
            conn.execute(
                f"UPDATE review_checkpoints SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            conn.commit()

    def get_checkpoint(self, checkpoint_id: str) -> Optional[ReviewCheckpoint]:
        """
        Get a checkpoint by ID.

        Args:
            checkpoint_id: Checkpoint ID to retrieve

        Returns:
            Checkpoint if found, None otherwise
        """
        with self._sqlite_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, research_question, created_at, updated_at, step,
                       search_session_id, report, metadata
                FROM review_checkpoints
                WHERE id = ?
                """,
                (checkpoint_id,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            return ReviewCheckpoint(
                id=row["id"],
                research_question=row["research_question"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                step=row["step"],
                search_session_id=row["search_session_id"],
                report=row["report"],
                metadata=json.loads(row["metadata"]),
            )

    def get_recent_checkpoints(self, limit: int = 20) -> list[ReviewCheckpoint]:
        """
        Get recent review checkpoints.

        Args:
            limit: Maximum number to return

        Returns:
            List of checkpoints, most recent first
        """
        with self._sqlite_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, research_question, created_at, updated_at, step,
                       search_session_id, report, metadata
                FROM review_checkpoints
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )

            checkpoints = []
            for row in cursor:
                checkpoints.append(ReviewCheckpoint(
                    id=row["id"],
                    research_question=row["research_question"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    step=row["step"],
                    search_session_id=row["search_session_id"],
                    report=row["report"],
                    metadata=json.loads(row["metadata"]),
                ))

            return checkpoints

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """
        Delete a checkpoint and associated data.

        Args:
            checkpoint_id: Checkpoint ID to delete

        Returns:
            True if deleted, False otherwise
        """
        with self._sqlite_connection() as conn:
            try:
                # Delete associated data first
                conn.execute(
                    "DELETE FROM citations WHERE checkpoint_id = ?",
                    (checkpoint_id,),
                )
                conn.execute(
                    "DELETE FROM scored_documents WHERE checkpoint_id = ?",
                    (checkpoint_id,),
                )
                conn.execute(
                    "DELETE FROM review_checkpoints WHERE id = ?",
                    (checkpoint_id,),
                )
                conn.commit()
                logger.debug(f"Deleted checkpoint {checkpoint_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to delete checkpoint {checkpoint_id}: {e}")
                return False

    # =========================================================================
    # PubMed Cache Operations
    # =========================================================================

    def get_cached_pubmed_response(self, query_hash: str) -> Optional[str]:
        """
        Get cached PubMed API response.

        Args:
            query_hash: Hash of the query

        Returns:
            Cached response if valid, None otherwise
        """
        with self._sqlite_connection() as conn:
            cursor = conn.execute(
                """
                SELECT response FROM pubmed_cache
                WHERE query_hash = ? AND expires_at > ?
                """,
                (query_hash, datetime.now()),
            )
            row = cursor.fetchone()
            return row["response"] if row else None

    def cache_pubmed_response(
        self,
        query_hash: str,
        response: str,
        ttl_seconds: int = PUBMED_CACHE_TTL_SECONDS,
    ) -> None:
        """
        Cache a PubMed API response.

        Args:
            query_hash: Hash of the query
            response: Response to cache
            ttl_seconds: Time to live in seconds
        """
        now = datetime.now()
        expires_at = datetime.fromtimestamp(now.timestamp() + ttl_seconds)

        with self._sqlite_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pubmed_cache
                (query_hash, response, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (query_hash, response, now, expires_at),
            )
            conn.commit()

    def clear_expired_cache(self) -> int:
        """
        Clear expired cache entries.

        Returns:
            Number of entries cleared
        """
        with self._sqlite_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM pubmed_cache WHERE expires_at < ?",
                (datetime.now(),),
            )
            conn.commit()
            return cursor.rowcount

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_statistics(self) -> dict[str, Any]:
        """
        Get storage statistics.

        Returns:
            Dictionary with storage statistics
        """
        doc_collection = self.get_documents_collection()
        chunk_collection = self.get_chunks_collection()

        with self._sqlite_connection() as conn:
            sessions = conn.execute(
                "SELECT COUNT(*) FROM search_sessions"
            ).fetchone()[0]
            checkpoints = conn.execute(
                "SELECT COUNT(*) FROM review_checkpoints"
            ).fetchone()[0]

        return {
            "documents": doc_collection.count(),
            "chunks": chunk_collection.count(),
            "search_sessions": sessions,
            "checkpoints": checkpoints,
            "data_dir": str(self._storage_config.data_dir),
        }

    def clear_all(self, confirm: bool = False) -> None:
        """
        Clear all data from storage.

        WARNING: This permanently deletes all data!

        Args:
            confirm: Must be True to actually clear data

        Raises:
            ValueError: If confirm is not True
        """
        if not confirm:
            raise ValueError("Must pass confirm=True to clear all data")

        # Reset ChromaDB collections
        try:
            self._chroma_client.delete_collection(CHROMA_DOCUMENTS_COLLECTION)
        except ValueError:
            pass  # Collection doesn't exist
        try:
            self._chroma_client.delete_collection(CHROMA_CHUNKS_COLLECTION)
        except ValueError:
            pass  # Collection doesn't exist

        # Clear SQLite tables
        with self._sqlite_connection() as conn:
            conn.executescript("""
                DELETE FROM citations;
                DELETE FROM scored_documents;
                DELETE FROM review_checkpoints;
                DELETE FROM search_sessions;
                DELETE FROM pubmed_cache;
                DELETE FROM interrogation_sessions;
                DELETE FROM user_settings;
            """)
            conn.commit()

        logger.warning("All data cleared from storage")
