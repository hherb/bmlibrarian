# Phase 1: Storage Layer Implementation

## Overview

The storage layer provides a unified interface for all data persistence in BMLibrarian Lite, combining ChromaDB for vector storage and SQLite for structured metadata.

## Components

### 1.1 Constants Module (`src/bmlibrarian/lite/constants.py`)

Define all constants to avoid magic numbers and hardcoded values:

```python
"""Constants for BMLibrarian Lite - no magic numbers or hardcoded paths."""

from pathlib import Path

# Default data directory (can be overridden by config)
DEFAULT_DATA_DIR = Path.home() / ".bmlibrarian_lite"

# ChromaDB settings
CHROMA_DOCUMENTS_COLLECTION = "documents"
CHROMA_CHUNKS_COLLECTION = "chunks"

# Embedding model settings
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_EMBEDDING_DIMENSIONS = 384

# SQLite database name
SQLITE_DATABASE_NAME = "metadata.db"

# PubMed API settings
PUBMED_CACHE_TTL_SECONDS = 86400  # 24 hours
PUBMED_DEFAULT_MAX_RESULTS = 200
PUBMED_BATCH_SIZE = 200

# Document chunking settings
DEFAULT_CHUNK_SIZE = 8000  # characters
DEFAULT_CHUNK_OVERLAP = 200  # characters

# Search settings
DEFAULT_SIMILARITY_THRESHOLD = 0.5
DEFAULT_MAX_RESULTS = 20

# Timeouts (milliseconds)
EMBEDDING_TIMEOUT_MS = 30000
LLM_TIMEOUT_MS = 120000
```

### 1.2 Configuration Module (`src/bmlibrarian/lite/config.py`)

Configuration management with sensible defaults:

```python
"""Configuration management for BMLibrarian Lite."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json
import logging

from .constants import (
    DEFAULT_DATA_DIR,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_MAX_RESULTS,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """LLM provider configuration."""
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.3
    max_tokens: int = 4096


@dataclass
class EmbeddingConfig:
    """Embedding model configuration."""
    model: str = DEFAULT_EMBEDDING_MODEL
    cache_dir: Optional[Path] = None


@dataclass
class PubMedConfig:
    """PubMed API configuration."""
    email: str = ""  # Required by NCBI
    api_key: Optional[str] = None  # Optional, increases rate limit


@dataclass
class StorageConfig:
    """Storage configuration."""
    data_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR)

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma_db"

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / "metadata.db"

    @property
    def reviews_dir(self) -> Path:
        return self.data_dir / "reviews"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"


@dataclass
class SearchConfig:
    """Search configuration."""
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    max_results: int = DEFAULT_MAX_RESULTS


@dataclass
class LiteConfig:
    """Main configuration for BMLibrarian Lite."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    embeddings: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    pubmed: PubMedConfig = field(default_factory=PubMedConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    search: SearchConfig = field(default_factory=SearchConfig)

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "LiteConfig":
        """Load configuration from file or use defaults."""
        if config_path is None:
            config_path = DEFAULT_DATA_DIR / "config.json"

        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return cls._from_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")
                logger.info("Using default configuration")

        return cls()

    @classmethod
    def _from_dict(cls, data: dict) -> "LiteConfig":
        """Create config from dictionary."""
        config = cls()

        if "llm" in data:
            config.llm = LLMConfig(**data["llm"])
        if "embeddings" in data:
            config.embeddings = EmbeddingConfig(**data["embeddings"])
        if "pubmed" in data:
            config.pubmed = PubMedConfig(**data["pubmed"])
        if "storage" in data:
            storage_data = data["storage"].copy()
            if "data_dir" in storage_data:
                storage_data["data_dir"] = Path(storage_data["data_dir"]).expanduser()
            config.storage = StorageConfig(**storage_data)
        if "search" in data:
            config.search = SearchConfig(**data["search"])

        return config

    def save(self, config_path: Optional[Path] = None) -> None:
        """Save configuration to file."""
        if config_path is None:
            config_path = self.storage.data_dir / "config.json"

        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "llm": {
                "provider": self.llm.provider,
                "model": self.llm.model,
                "temperature": self.llm.temperature,
                "max_tokens": self.llm.max_tokens,
            },
            "embeddings": {
                "model": self.embeddings.model,
            },
            "pubmed": {
                "email": self.pubmed.email,
                "api_key": self.pubmed.api_key,
            },
            "storage": {
                "data_dir": str(self.storage.data_dir),
            },
            "search": {
                "chunk_size": self.search.chunk_size,
                "chunk_overlap": self.search.chunk_overlap,
                "similarity_threshold": self.search.similarity_threshold,
                "max_results": self.search.max_results,
            },
        }

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        logger.info(f"Configuration saved to {config_path}")
```

### 1.3 Data Models (`src/bmlibrarian/lite/data_models.py`)

Type-safe data structures for Lite version:

```python
"""Data models for BMLibrarian Lite."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class DocumentSource(Enum):
    """Source of a document."""
    PUBMED = "pubmed"
    LOCAL_PDF = "local_pdf"
    LOCAL_TEXT = "local_text"


@dataclass
class LiteDocument:
    """Document representation for Lite version."""
    id: str  # Unique identifier (PMID or generated UUID)
    title: str
    abstract: str
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    journal: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    source: DocumentSource = DocumentSource.PUBMED
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def formatted_authors(self) -> str:
        """Return formatted author string."""
        if not self.authors:
            return "Unknown"
        if len(self.authors) <= 3:
            return ", ".join(self.authors)
        return f"{self.authors[0]} et al."

    @property
    def citation(self) -> str:
        """Return formatted citation."""
        parts = [self.formatted_authors]
        if self.year:
            parts.append(f"({self.year})")
        parts.append(self.title)
        if self.journal:
            parts.append(self.journal)
        return ". ".join(parts)


@dataclass
class DocumentChunk:
    """A chunk of a document for embedding."""
    id: str  # Unique chunk ID
    document_id: str  # Parent document ID
    text: str
    chunk_index: int
    start_char: int
    end_char: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchSession:
    """A PubMed search session."""
    id: str
    query: str
    natural_language_query: str
    created_at: datetime
    document_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoredDocument:
    """Document with relevance score."""
    document: LiteDocument
    score: int  # 1-5 scale
    explanation: str
    scored_at: datetime = field(default_factory=datetime.now)


@dataclass
class Citation:
    """Extracted citation from a document."""
    document: LiteDocument
    passage: str
    relevance_score: int
    context: str = ""


@dataclass
class ReviewCheckpoint:
    """Checkpoint for systematic review progress."""
    id: str
    research_question: str
    created_at: datetime
    updated_at: datetime
    step: str  # Current workflow step
    search_session_id: Optional[str] = None
    scored_documents: List[ScoredDocument] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    report: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 1.4 Storage Layer (`src/bmlibrarian/lite/storage.py`)

Main storage abstraction:

```python
"""Unified storage layer for BMLibrarian Lite using ChromaDB and SQLite."""

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from .config import LiteConfig, StorageConfig
from .constants import (
    CHROMA_CHUNKS_COLLECTION,
    CHROMA_DOCUMENTS_COLLECTION,
    DEFAULT_DATA_DIR,
    SQLITE_DATABASE_NAME,
)
from .data_models import (
    Citation,
    DocumentChunk,
    DocumentSource,
    LiteDocument,
    ReviewCheckpoint,
    ScoredDocument,
    SearchSession,
)

logger = logging.getLogger(__name__)


class LiteStorage:
    """
    Unified storage layer for BMLibrarian Lite.

    Combines ChromaDB for vector storage and SQLite for structured metadata.
    All data is persisted to the configured data directory.
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
        self._ensure_directories()

        # Initialize ChromaDB
        self._chroma_client = self._init_chroma()

        # Initialize SQLite
        self._init_sqlite()

        logger.info(f"LiteStorage initialized at {self._storage_config.data_dir}")

    def _ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        dirs = [
            self._storage_config.data_dir,
            self._storage_config.chroma_dir,
            self._storage_config.reviews_dir,
            self._storage_config.exports_dir,
            self._storage_config.cache_dir,
        ]
        for directory in dirs:
            directory.mkdir(parents=True, exist_ok=True)

    def _init_chroma(self) -> chromadb.PersistentClient:
        """Initialize ChromaDB client with persistent storage."""
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

    def _init_sqlite(self) -> None:
        """Initialize SQLite database with schema."""
        with self._sqlite_connection() as conn:
            conn.executescript(self._get_sqlite_schema())
            conn.commit()
        logger.debug(f"SQLite initialized at {self._storage_config.sqlite_path}")

    @contextmanager
    def _sqlite_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for SQLite connections."""
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
        """Return SQLite schema definition."""
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

        -- Create indexes
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
        """

    # -------------------------------------------------------------------------
    # ChromaDB Collections
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # Document Operations
    # -------------------------------------------------------------------------

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
        """
        collection = self.get_documents_collection(embedding_function)

        metadata = {
            "title": document.title,
            "authors": json.dumps(document.authors),
            "year": document.year or 0,
            "journal": document.journal or "",
            "doi": document.doi or "",
            "pmid": document.pmid or "",
            "source": document.source.value,
        }
        metadata.update(document.metadata)

        collection.upsert(
            ids=[document.id],
            documents=[document.abstract],
            metadatas=[metadata],
        )

        logger.debug(f"Added document {document.id} to storage")
        return document.id

    def add_documents(
        self,
        documents: List[LiteDocument],
        embedding_function: Any = None,
    ) -> List[str]:
        """
        Add multiple documents to storage.

        Args:
            documents: List of documents to add
            embedding_function: Optional embedding function

        Returns:
            List of document IDs
        """
        if not documents:
            return []

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
                "source": doc.source.value,
            }
            metadata.update(doc.metadata)
            metadatas.append(metadata)

        collection.upsert(ids=ids, documents=texts, metadatas=metadatas)

        logger.info(f"Added {len(documents)} documents to storage")
        return ids

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
        """
        collection = self.get_documents_collection(embedding_function)

        try:
            result = collection.get(ids=[document_id], include=["documents", "metadatas"])

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
                source=DocumentSource(metadata.get("source", "pubmed")),
            )
        except Exception as e:
            logger.error(f"Failed to get document {document_id}: {e}")
            return None

    def search_documents(
        self,
        query: str,
        n_results: int = 20,
        embedding_function: Any = None,
    ) -> List[LiteDocument]:
        """
        Search documents by semantic similarity.

        Args:
            query: Search query
            n_results: Maximum number of results
            embedding_function: Optional embedding function

        Returns:
            List of matching documents
        """
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
                source=DocumentSource(metadata.get("source", "pubmed")),
            ))

        return documents

    # -------------------------------------------------------------------------
    # Search Session Operations
    # -------------------------------------------------------------------------

    def create_search_session(
        self,
        query: str,
        natural_language_query: str,
        document_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SearchSession:
        """
        Create a new search session.

        Args:
            query: PubMed query string
            natural_language_query: Original natural language query
            document_count: Number of documents found
            metadata: Optional metadata

        Returns:
            Created search session
        """
        session_id = str(uuid.uuid4())
        now = datetime.now()

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

    def get_search_sessions(self, limit: int = 50) -> List[SearchSession]:
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

    # -------------------------------------------------------------------------
    # Review Checkpoint Operations
    # -------------------------------------------------------------------------

    def create_checkpoint(
        self,
        research_question: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReviewCheckpoint:
        """
        Create a new review checkpoint.

        Args:
            research_question: The research question
            metadata: Optional metadata

        Returns:
            Created checkpoint
        """
        checkpoint_id = str(uuid.uuid4())
        now = datetime.now()

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

    def update_checkpoint(
        self,
        checkpoint_id: str,
        step: Optional[str] = None,
        search_session_id: Optional[str] = None,
        report: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
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
        values = [datetime.now()]

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

    def get_recent_checkpoints(self, limit: int = 20) -> List[ReviewCheckpoint]:
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

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def get_statistics(self) -> Dict[str, Any]:
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

        Args:
            confirm: Must be True to actually clear data
        """
        if not confirm:
            raise ValueError("Must pass confirm=True to clear all data")

        # Reset ChromaDB collections
        self._chroma_client.delete_collection(CHROMA_DOCUMENTS_COLLECTION)
        self._chroma_client.delete_collection(CHROMA_CHUNKS_COLLECTION)

        # Clear SQLite tables
        with self._sqlite_connection() as conn:
            conn.executescript("""
                DELETE FROM citations;
                DELETE FROM scored_documents;
                DELETE FROM review_checkpoints;
                DELETE FROM search_sessions;
                DELETE FROM pubmed_cache;
            """)
            conn.commit()

        logger.warning("All data cleared from storage")
```

## Implementation Steps

### Step 1: Create directory structure

```bash
mkdir -p src/bmlibrarian/lite
touch src/bmlibrarian/lite/__init__.py
touch src/bmlibrarian/lite/constants.py
touch src/bmlibrarian/lite/config.py
touch src/bmlibrarian/lite/data_models.py
touch src/bmlibrarian/lite/storage.py
```

### Step 2: Implement constants.py

Create the constants module with all magic numbers and default values.

### Step 3: Implement config.py

Create the configuration management module with dataclasses.

### Step 4: Implement data_models.py

Create the data model classes for documents, chunks, sessions, etc.

### Step 5: Implement storage.py

Create the unified storage layer with ChromaDB and SQLite integration.

### Step 6: Add tests

```bash
mkdir -p tests/lite
touch tests/lite/__init__.py
touch tests/lite/test_storage.py
touch tests/lite/test_config.py
```

## Testing Strategy

```python
# tests/lite/test_storage.py

import pytest
from pathlib import Path
import tempfile

from bmlibrarian.lite.storage import LiteStorage
from bmlibrarian.lite.config import LiteConfig, StorageConfig
from bmlibrarian.lite.data_models import LiteDocument, DocumentSource


@pytest.fixture
def temp_storage():
    """Create a temporary storage instance for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = LiteConfig()
        config.storage = StorageConfig(data_dir=Path(tmpdir))
        storage = LiteStorage(config)
        yield storage


def test_storage_initialization(temp_storage):
    """Test that storage initializes correctly."""
    stats = temp_storage.get_statistics()
    assert stats["documents"] == 0
    assert stats["chunks"] == 0


def test_add_and_get_document(temp_storage):
    """Test adding and retrieving a document."""
    doc = LiteDocument(
        id="test-123",
        title="Test Document",
        abstract="This is a test abstract.",
        authors=["Author One", "Author Two"],
        year=2024,
        source=DocumentSource.PUBMED,
    )

    temp_storage.add_document(doc)
    retrieved = temp_storage.get_document("test-123")

    assert retrieved is not None
    assert retrieved.title == "Test Document"
    assert retrieved.abstract == "This is a test abstract."


def test_create_search_session(temp_storage):
    """Test creating a search session."""
    session = temp_storage.create_search_session(
        query="cancer treatment",
        natural_language_query="What are the best cancer treatments?",
        document_count=50,
    )

    assert session.id is not None
    assert session.query == "cancer treatment"

    sessions = temp_storage.get_search_sessions()
    assert len(sessions) == 1


def test_checkpoint_operations(temp_storage):
    """Test checkpoint creation and update."""
    checkpoint = temp_storage.create_checkpoint(
        research_question="What is the effect of X on Y?"
    )

    assert checkpoint.step == "start"

    temp_storage.update_checkpoint(checkpoint.id, step="scoring")

    updated = temp_storage.get_checkpoint(checkpoint.id)
    assert updated.step == "scoring"
```

## Dependencies

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
lite = [
    "chromadb>=0.4.0",
    "fastembed>=0.3.0",
]
```

## Golden Rules Checklist

- [x] No magic numbers - all in constants.py
- [x] No hardcoded paths - all from config
- [x] Type hints on all parameters
- [x] Docstrings on all functions/classes
- [x] Error handling with logging
- [x] Database abstraction (no direct access from outside storage.py)
