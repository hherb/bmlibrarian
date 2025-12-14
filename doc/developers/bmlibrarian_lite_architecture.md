# BMLibrarian Lite Architecture

Technical documentation for developers working on BMLibrarian Lite.

## Architecture Overview

BMLibrarian Lite is a lightweight, portable version of BMLibrarian designed for users without PostgreSQL or local Ollama infrastructure. It uses:

- **ChromaDB** for vector storage (embedded, no server required)
- **SQLite** for structured metadata storage
- **FastEmbed** for CPU-optimized local embeddings
- **Anthropic Claude** for LLM inference (online API)
- **NCBI E-utilities** for PubMed search (online API)

### Design Philosophy

1. **Minimal Dependencies**: Single `pip install` to get started
2. **Portable**: All data in `~/.bmlibrarian_lite/`
3. **Offline-Capable**: Embeddings work offline once models are cached
4. **Golden Rules Compliant**: Type hints, docstrings, constants, error handling

## Module Structure

```
src/bmlibrarian/lite/
├── __init__.py              # Module exports
├── config.py                # LiteConfig dataclass hierarchy
├── constants.py             # All magic numbers and defaults
├── data_models.py           # Type-safe dataclasses
├── storage.py               # LiteStorage (ChromaDB + SQLite)
├── embeddings.py            # LiteEmbedder (FastEmbed wrapper)
├── chroma_embeddings.py     # FastEmbedFunction for ChromaDB
├── chunking.py              # Document chunking utilities
├── exceptions.py            # Custom exception classes
├── agents/
│   ├── __init__.py
│   ├── base.py              # LiteBaseAgent (LLM communication)
│   ├── search_agent.py      # LiteSearchAgent (PubMed + caching)
│   ├── scoring_agent.py     # LiteScoringAgent (relevance scoring)
│   ├── citation_agent.py    # LiteCitationAgent (passage extraction)
│   ├── reporting_agent.py   # LiteReportingAgent (report synthesis)
│   └── interrogation_agent.py # LiteInterrogationAgent (Q&A)
└── gui/
    ├── __init__.py
    ├── app.py               # LiteMainWindow (main application)
    ├── systematic_review_tab.py  # Search/score/report workflow
    ├── document_interrogation_tab.py  # Document Q&A
    └── settings_dialog.py   # Configuration UI
```

## Configuration System

### LiteConfig Hierarchy

```python
LiteConfig
├── llm: LLMConfig
│   ├── provider: str = "anthropic"
│   ├── model: str = "claude-sonnet-4-20250514"
│   ├── temperature: float = 0.3
│   └── max_tokens: int = 4096
├── embeddings: EmbeddingConfig
│   ├── model: str = "BAAI/bge-small-en-v1.5"
│   └── cache_dir: Optional[Path]
├── pubmed: PubMedConfig
│   ├── email: str = ""
│   └── api_key: Optional[str]
├── storage: StorageConfig
│   └── data_dir: Path = "~/.bmlibrarian_lite"
└── search: SearchConfig
    ├── chunk_size: int = 8000
    ├── chunk_overlap: int = 200
    ├── similarity_threshold: float = 0.5
    └── max_results: int = 20
```

### Configuration Loading

```python
from bmlibrarian.lite import LiteConfig

# Load from default location (~/.bmlibrarian_lite/config.json)
config = LiteConfig.load()

# Load from specific path
config = LiteConfig.load(Path("/path/to/config.json"))

# Use defaults
config = LiteConfig()

# Validate configuration
errors = config.validate()
if errors:
    raise ValueError(f"Invalid config: {errors}")

# Modify and save
config.llm.temperature = 0.5
config.save()
```

### Configuration Validation

```python
def validate(self) -> list[str]:
    """
    Validate configuration values.

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Email validation
    if self.pubmed.email and "@" not in self.pubmed.email:
        errors.append("Invalid email format for PubMed configuration")

    # Temperature range
    if not 0.0 <= self.llm.temperature <= 1.0:
        errors.append("LLM temperature must be between 0.0 and 1.0")

    # Max tokens
    if self.llm.max_tokens < 1:
        errors.append("LLM max_tokens must be positive")

    # Chunk settings
    if self.search.chunk_size < MIN_CHUNK_SIZE:
        errors.append(f"Chunk size must be >= {MIN_CHUNK_SIZE}")
    if self.search.chunk_overlap >= self.search.chunk_size:
        errors.append("Chunk overlap must be less than chunk size")

    return errors
```

## Storage Layer

### LiteStorage Class

Unified interface combining ChromaDB (vectors) and SQLite (metadata).

```python
from bmlibrarian.lite import LiteConfig
from bmlibrarian.lite.storage import LiteStorage
from bmlibrarian.lite.chroma_embeddings import create_embedding_function

# Initialize storage
config = LiteConfig.load()
storage = LiteStorage(config)
embed_fn = create_embedding_function(config.embeddings.model)

# Add documents
doc_id = storage.add_document(document, embedding_function=embed_fn)

# Search by semantic similarity
results = storage.search_documents("query", embedding_function=embed_fn)

# Create search session (SQLite)
session = storage.create_search_session(
    query="pubmed query",
    natural_language_query="user question",
    document_count=42
)
```

### ChromaDB Collections

| Collection | Purpose | Schema |
|------------|---------|--------|
| `documents` | PubMed abstracts + local docs | id, document text, metadata |
| `chunks` | Document chunks for RAG | id, chunk text, parent doc id |

### SQLite Tables

| Table | Purpose |
|-------|---------|
| `search_sessions` | PubMed search history |
| `review_checkpoints` | Systematic review progress |
| `scored_documents` | Document relevance scores |
| `citations` | Extracted passages |
| `user_settings` | Configuration overrides |
| `pubmed_cache` | API response cache (24h TTL) |
| `interrogation_sessions` | Q&A conversation history |

### Exception Handling

Storage operations use specific exception types:

```python
from bmlibrarian.lite.exceptions import (
    LiteStorageError,
    ChromaDBError,
    SQLiteError,
    EmbeddingError,
)

try:
    storage.add_document(doc, embed_fn)
except ChromaDBError as e:
    logger.error(f"ChromaDB operation failed: {e}")
    # Handle vector storage failure
except SQLiteError as e:
    logger.error(f"SQLite operation failed: {e}")
    # Handle metadata storage failure
except EmbeddingError as e:
    logger.error(f"Embedding generation failed: {e}")
    # Handle embedding failure
```

## Embedding System

### FastEmbed Integration

BMLibrarian Lite uses FastEmbed for CPU-optimized embeddings via ONNX:

```python
from bmlibrarian.lite.embeddings import LiteEmbedder
from bmlibrarian.lite.chroma_embeddings import FastEmbedFunction

# Direct embedding
embedder = LiteEmbedder(model_name="BAAI/bge-small-en-v1.5")
vectors = embedder.embed(["text 1", "text 2"])

# ChromaDB-compatible function
embed_fn = FastEmbedFunction(model_name="BAAI/bge-small-en-v1.5")
collection = chroma_client.get_or_create_collection(
    name="documents",
    embedding_function=embed_fn
)
```

### Supported Models

| Model | Dimensions | Size | Description |
|-------|------------|------|-------------|
| `BAAI/bge-small-en-v1.5` | 384 | 50MB | Default, fast |
| `BAAI/bge-base-en-v1.5` | 768 | 130MB | Better quality |
| `intfloat/multilingual-e5-small` | 384 | 50MB | Multi-language |

## Agent Architecture

### LiteBaseAgent

Base class providing LLM communication:

```python
class LiteBaseAgent:
    def __init__(
        self,
        config: Optional[LiteConfig] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.config = config or LiteConfig()
        self._llm_client = llm_client

    @property
    def llm_client(self) -> LLMClient:
        """Lazy-initialized LLM client."""
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def _get_model(self) -> str:
        """Get model string (e.g., 'anthropic:claude-sonnet-4-20250514')."""
        return f"{self.config.llm.provider}:{self.config.llm.model}"

    def _chat(
        self,
        messages: list[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        """Send chat request to LLM."""
        ...
```

### Agent Workflow

```
LiteSearchAgent
    │
    ├── convert_query(question) → PubMedQuery
    │   └── Uses LLM to optimize query
    │
    └── search(question) → (SearchSession, List[LiteDocument])
        └── PubMed search + ChromaDB caching

LiteScoringAgent
    │
    └── score_document(question, doc) → ScoredDocument
        └── Returns score 1-5 with explanation

LiteCitationAgent
    │
    └── extract_citations(question, scored_doc) → List[Citation]
        └── Extracts 1-3 key passages

LiteReportingAgent
    │
    └── generate_report(question, citations) → str (markdown)
        └── Synthesizes evidence into report

LiteInterrogationAgent
    │
    ├── add_document(doc) → None
    │   └── Chunk + embed + store
    │
    └── ask_question(question) → str
        └── RAG: retrieve chunks + generate answer
```

## GUI Architecture

### LiteMainWindow

Main application window with tab-based navigation:

```python
class LiteMainWindow(QMainWindow):
    def __init__(self):
        # Load config
        self.config = LiteConfig.load()
        self.storage = LiteStorage(self.config)

        # Create tabs
        self.tabs = QTabWidget()
        self.systematic_review_tab = SystematicReviewTab(self.config, self.storage)
        self.interrogation_tab = DocumentInterrogationTab(self.config, self.storage)

        self.tabs.addTab(self.systematic_review_tab, "Systematic Review")
        self.tabs.addTab(self.interrogation_tab, "Document Interrogation")
```

### Background Workers

All LLM/API operations run in background threads:

```python
class WorkflowWorker(QThread):
    """Background worker for systematic review workflow."""

    progress = Signal(str, int, int)  # step, current, total
    step_complete = Signal(str, object)  # step name, result
    error = Signal(str, str)  # step name, error message
    finished = Signal(str)  # final report

    def run(self):
        try:
            # 1. Search
            self.progress.emit("search", 0, 4)
            session, documents = self.search_agent.search(self.question)
            self.step_complete.emit("search", documents)

            # 2. Score
            self.progress.emit("scoring", 1, 4)
            scored = [self.scoring_agent.score_document(self.question, doc)
                      for doc in documents]
            ...
        except Exception as e:
            self.error.emit("workflow", str(e))
```

### Styling

Uses BMLibrarian's centralized styling system:

```python
from bmlibrarian.gui.qt.resources.dpi_scale import scaled
from bmlibrarian.gui.qt.resources.stylesheet_generator import StylesheetGenerator

# Scale dimensions by DPI
layout.setContentsMargins(scaled(8), scaled(8), scaled(8), scaled(8))

# Generate stylesheet
generator = StylesheetGenerator()
stylesheet = generator.generate()
self.setStyleSheet(stylesheet)
```

## Network Operations

### Retry Logic

Network operations include retry with exponential backoff:

```python
from bmlibrarian.lite.utils import retry_with_backoff

@retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=10.0)
def fetch_pubmed_articles(pmids: list[str]) -> list[ArticleMetadata]:
    """Fetch articles with automatic retry."""
    return client.fetch_details(pmids)
```

### Retry Decorator Implementation

```python
import time
import functools
from typing import Callable, TypeVar

T = TypeVar('T')

def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple = (ConnectionError, TimeoutError),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying operations with exponential backoff.

    Args:
        max_retries: Maximum retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        exponential_base: Multiplier for delay increase
        retryable_exceptions: Exceptions that trigger retry
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(
                            base_delay * (exponential_base ** attempt),
                            max_delay
                        )
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}), "
                            f"retrying in {delay:.1f}s: {e}"
                        )
                        time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator
```

## Performance Monitoring

### Metrics Collection

```python
from bmlibrarian.lite.metrics import MetricsCollector

metrics = MetricsCollector()

# Time an operation
with metrics.timer("pubmed_search"):
    results = search_agent.search(question)

# Record a count
metrics.increment("documents_processed", len(documents))

# Record a value
metrics.record("relevance_score", score)

# Get statistics
stats = metrics.get_statistics()
# {'pubmed_search': {'count': 5, 'mean': 2.3, 'min': 1.1, 'max': 4.2}}
```

### Logging

All operations use structured logging:

```python
import logging

logger = logging.getLogger(__name__)

# Operations log at INFO level
logger.info(f"Processing {len(documents)} documents")

# Performance metrics at DEBUG level
logger.debug(f"Embedding generation took {elapsed:.2f}s")

# Errors with context
logger.error(f"Failed to score document {doc.id}: {e}", exc_info=True)
```

## Testing

### Unit Tests

```bash
# Run all Lite tests
uv run python -m pytest tests/lite/ -v

# Run specific test module
uv run python -m pytest tests/lite/test_config.py -v

# Run with coverage
uv run python -m pytest tests/lite/ --cov=bmlibrarian.lite
```

### Test Structure

```
tests/lite/
├── test_config.py       # Configuration tests
├── test_storage.py      # ChromaDB + SQLite tests
├── test_embeddings.py   # FastEmbed tests
├── test_chunking.py     # Document chunking tests
├── test_agents.py       # Agent tests (mocked LLM)
└── test_gui.py          # GUI widget tests
```

### Mocking LLM Calls

```python
import pytest
from unittest.mock import Mock, patch

@pytest.fixture
def mock_llm_client():
    """Mock LLM client for testing."""
    client = Mock()
    client.chat.return_value = Mock(content='{"score": 4, "explanation": "test"}')
    return client

def test_scoring_agent(mock_llm_client):
    agent = LiteScoringAgent(llm_client=mock_llm_client)
    result = agent.score_document("test question", mock_document)
    assert result.score == 4
```

## Error Handling

### Exception Hierarchy

```python
class LiteError(Exception):
    """Base exception for BMLibrarian Lite."""
    pass

class LiteStorageError(LiteError):
    """Base storage exception."""
    pass

class ChromaDBError(LiteStorageError):
    """ChromaDB-specific error."""
    pass

class SQLiteError(LiteStorageError):
    """SQLite-specific error."""
    pass

class EmbeddingError(LiteError):
    """Embedding generation error."""
    pass

class ConfigurationError(LiteError):
    """Configuration validation error."""
    pass

class NetworkError(LiteError):
    """Network operation error."""
    pass

class LLMError(LiteError):
    """LLM API error."""
    pass
```

### Error Handling Pattern

```python
def add_document(self, document: LiteDocument, embed_fn: Any) -> str:
    """Add document with proper error handling."""
    try:
        # ChromaDB operation
        collection = self.get_documents_collection(embed_fn)
        collection.upsert(ids=[document.id], documents=[document.abstract], ...)
    except chromadb.errors.ChromaError as e:
        raise ChromaDBError(f"Failed to add document {document.id}: {e}") from e

    try:
        # SQLite operation
        with self._sqlite_connection() as conn:
            conn.execute("INSERT INTO ...", ...)
    except sqlite3.Error as e:
        raise SQLiteError(f"Failed to record document metadata: {e}") from e

    return document.id
```

## Constants

All magic numbers are defined in `constants.py`:

```python
# Data directory
DEFAULT_DATA_DIR = Path.home() / ".bmlibrarian_lite"

# ChromaDB collections
CHROMA_DOCUMENTS_COLLECTION = "documents"
CHROMA_CHUNKS_COLLECTION = "chunks"

# Embedding defaults
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_EMBEDDING_DIMENSIONS = 384

# Chunking
DEFAULT_CHUNK_SIZE = 8000
DEFAULT_CHUNK_OVERLAP = 200
MIN_CHUNK_SIZE = 100

# LLM defaults
DEFAULT_LLM_PROVIDER = "anthropic"
DEFAULT_LLM_MODEL = "claude-sonnet-4-20250514"
DEFAULT_LLM_TEMPERATURE = 0.3
DEFAULT_LLM_MAX_TOKENS = 4096

# Timeouts (milliseconds)
EMBEDDING_TIMEOUT_MS = 30000
LLM_TIMEOUT_MS = 120000
PUBMED_TIMEOUT_MS = 30000

# Scoring
SCORE_MIN = 1
SCORE_MAX = 5
DEFAULT_MIN_SCORE = 3

# Network retry
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BASE_DELAY = 1.0
DEFAULT_RETRY_MAX_DELAY = 10.0
```

## Contributing

### Adding a New Agent

1. Create agent file in `src/bmlibrarian/lite/agents/`
2. Inherit from `LiteBaseAgent`
3. Use configuration from `self.config`
4. Add docstrings with usage examples
5. Add to `agents/__init__.py` exports
6. Write tests in `tests/lite/test_agents.py`
7. Update documentation

### Adding Configuration Options

1. Add default constant to `constants.py`
2. Add field to appropriate config dataclass in `config.py`
3. Update `_from_dict()` and `to_dict()` methods
4. Add validation in `validate()` method
5. Update SettingsDialog if user-configurable
6. Update documentation

### Code Style

- Type hints on all parameters and return values
- Docstrings on all public methods
- Use constants, no magic numbers
- Handle all errors with appropriate exception types
- Log operations at INFO, performance at DEBUG
- Use `scaled()` for all UI dimensions
