# Document Q&A System Architecture

This document describes the technical architecture of BMLibrarian's document question-answering system.

## Overview

The Document Q&A system provides a high-level function `answer_from_document()` that orchestrates multiple subsystems to answer questions about specific documents in the knowledge base.

## Module Structure

```
src/bmlibrarian/qa/
├── __init__.py          # Module exports
├── data_types.py        # Type definitions (AnswerSource, QAError, etc.)
└── document_qa.py       # Main implementation
```

## Data Types

### AnswerSource Enum

Indicates the source of context used for generating answers:

```python
class AnswerSource(Enum):
    FULLTEXT_SEMANTIC = "fulltext_semantic"  # Semantic search on full-text chunks
    ABSTRACT = "abstract"                     # Used document abstract as context
```

### QAError Enum

Structured error codes with descriptions:

```python
class QAError(Enum):
    DOCUMENT_NOT_FOUND = "document_not_found"
    NO_TEXT_AVAILABLE = "no_text_available"
    NO_FULLTEXT = "no_fulltext"
    DOWNLOAD_FAILED = "download_failed"
    EMBEDDING_FAILED = "embedding_failed"
    SEMANTIC_SEARCH_FAILED = "semantic_search_failed"
    LLM_ERROR = "llm_error"
    DATABASE_ERROR = "database_error"
    CONFIGURATION_ERROR = "configuration_error"
    PROXY_REQUIRED = "proxy_required"      # PDF requires institutional access
    USER_CANCELLED = "user_cancelled"      # User declined proxy/upload

    @property
    def description(self) -> str:
        """Get human-readable description."""
        ...
```

### ProxyCallbackResult

Result from the proxy callback function for user consent:

```python
@dataclass
class ProxyCallbackResult:
    pdf_made_available: bool = False  # User uploaded PDF externally
    allow_proxy: bool = False         # User consents to proxy download
```

### ProxyCallback Type

Type alias for the callback function signature:

```python
ProxyCallback = Callable[[int, Optional[str]], ProxyCallbackResult]
# Callback receives: (document_id, document_title) -> ProxyCallbackResult
```

### ChunkContext

Represents a chunk of text used as context:

```python
@dataclass
class ChunkContext:
    chunk_no: int
    text: str
    score: float
    chunk_id: Optional[int] = None
```

### DocumentTextStatus

Status of text availability for a document:

```python
@dataclass
class DocumentTextStatus:
    document_id: int
    has_abstract: bool = False
    has_fulltext: bool = False
    has_abstract_embeddings: bool = False
    has_fulltext_chunks: bool = False
    abstract_length: int = 0
    fulltext_length: int = 0
    title: Optional[str] = None

    @property
    def can_use_fulltext_semantic(self) -> bool: ...
    @property
    def can_use_abstract_semantic(self) -> bool: ...
    @property
    def has_any_text(self) -> bool: ...
```

### SemanticSearchAnswer

Complete result from document Q&A:

```python
@dataclass
class SemanticSearchAnswer:
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

    @property
    def success(self) -> bool: ...
    @property
    def used_fulltext(self) -> bool: ...
    def to_dict(self) -> dict: ...
```

## SQL Functions

### Document-Specific Search Functions

Created in migration `018_create_document_specific_search_functions.sql`:

#### semantic_search_document()

Searches abstract chunks within a specific document:

```sql
CREATE FUNCTION semantic_search_document(
    p_document_id INTEGER,
    query_text TEXT,
    threshold FLOAT DEFAULT 0.7,
    result_limit INTEGER DEFAULT 5
) RETURNS TABLE (
    chunk_id INTEGER,
    chunk_no INTEGER,
    score FLOAT,
    chunk_text TEXT
)
```

**Key Design Points:**
- Filters by `document_id` **inside** the query (not post-filtering)
- Uses `emb_1024` table for abstract embeddings
- Embedding generated via `ollama_embedding()` at runtime

#### semantic.chunksearch_document()

Searches full-text chunks within a specific document:

```sql
CREATE FUNCTION semantic.chunksearch_document(
    p_document_id INTEGER,
    query_text TEXT,
    threshold FLOAT DEFAULT 0.7,
    result_limit INTEGER DEFAULT 5
) RETURNS TABLE (
    chunk_id INTEGER,
    chunk_no INTEGER,
    score FLOAT,
    chunk_text TEXT
)
```

**Key Design Points:**
- Uses `semantic.chunks` table for full-text embeddings
- Extracts text on-the-fly via `substr(full_text, start_pos, end_pos)`
- No redundant text storage (chunks store positions only)

#### get_document_text_status()

Helper function for checking document text availability:

```sql
CREATE FUNCTION get_document_text_status(p_document_id INTEGER)
RETURNS TABLE (
    has_abstract BOOLEAN,
    has_fulltext BOOLEAN,
    has_abstract_embeddings BOOLEAN,
    has_fulltext_chunks BOOLEAN,
    abstract_length INTEGER,
    fulltext_length INTEGER
)
```

### Why Document-Specific Functions?

The existing `semantic.chunksearch()` function searches the **entire corpus**. Using:

```sql
SELECT * FROM semantic.chunksearch(...) WHERE document_id = 12345
```

Would execute the full corpus search first, then filter—defeating the purpose. The document-specific functions pass `document_id` into the query, enabling efficient index-assisted filtering.

## Workflow

```
answer_from_document(document_id, question)
    │
    ├─► 1. Validate inputs
    │       └─► Return error if question empty
    │
    ├─► 2. Get database manager
    │       └─► Return error if unavailable
    │
    ├─► 3. Load configuration
    │       └─► Merge with defaults
    │
    ├─► 4. Get document text status
    │       └─► Return DOCUMENT_NOT_FOUND if missing
    │
    ├─► 5. Check for any text
    │       └─► Return NO_TEXT_AVAILABLE if none
    │
    ├─► 6. If use_fulltext=True:
    │       │
    │       ├─► 6a. If no fulltext and download_missing=True:
    │       │       └─► First try open-access sources (no proxy)
    │       │           │
    │       │           ├─► If success: refresh status
    │       │           │
    │       │           └─► If failed, decide on proxy:
    │       │               │
    │       │               ├─► If always_allow_proxy=True:
    │       │               │       └─► Use proxy directly
    │       │               │
    │       │               ├─► If proxy_callback provided:
    │       │               │       └─► Invoke callback
    │       │               │           ├─► pdf_made_available → refresh status
    │       │               │           ├─► allow_proxy → retry with proxy
    │       │               │           └─► neither → fall back to abstract
    │       │               │
    │       │               └─► Otherwise: skip proxy, fall back to abstract
    │       │
    │       ├─► 6b. If fulltext exists but no chunks:
    │       │       └─► _embed_fulltext_if_needed()
    │       │           └─► ChunkEmbedder.chunk_and_embed()
    │       │
    │       └─► 6c. If chunks exist:
    │               └─► _semantic_search_fulltext()
    │
    ├─► 7. If no fulltext chunks, fallback to abstract:
    │       └─► _get_document_abstract()
    │
    ├─► 8. Build context from chunks/abstract
    │
    ├─► 9. Generate answer via LLM:
    │       └─► _generate_answer()
    │           ├─► Check if model supports thinking
    │           ├─► Call ollama.chat() with think=True if supported
    │           └─► Extract thinking from response
    │
    └─► 10. Return SemanticSearchAnswer
```

## Thinking Model Support

The system supports thinking/reasoning models (DeepSeek-R1, Qwen, etc.):

### Detection

```python
thinking_models = ["deepseek-r1", "qwen", "qwq"]
model_supports_thinking = any(tm in model.lower() for tm in thinking_models)
```

### Response Handling

1. **Primary**: Check `response["message"]["thinking"]` field
2. **Fallback**: Extract `<think>...</think>` blocks from content

```python
def _extract_thinking(response_content: str) -> Tuple[str, Optional[str]]:
    think_pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
    match = think_pattern.search(response_content)
    if match:
        thinking = match.group(1).strip()
        answer = think_pattern.sub("", response_content).strip()
        return answer, thinking
    return response_content.strip(), None
```

## Configuration

### Config Schema

```json
{
  "models": {
    "document_qa_agent": "gpt-oss:20b"
  },
  "agents": {
    "document_qa": {
      "temperature": 0.3,
      "top_p": 0.9,
      "max_tokens": 2000,
      "max_chunks": 5,
      "similarity_threshold": 0.7,
      "use_fulltext": true,
      "download_missing_fulltext": true,
      "always_allow_proxy": false,
      "use_thinking": true,
      "embedding_model": "snowflake-arctic-embed2:latest"
    }
  }
}
```

**Note**: `always_allow_proxy` controls automatic proxy usage. When `false` (default),
the system requires a `proxy_callback` to be provided for user consent before using
institutional proxy (OpenAthens). When `true`, proxy is used automatically without
asking the user.

### Config Integration

The function loads config via:

```python
from bmlibrarian.config import get_config
config = get_config()
qa_config = config.get("document_qa", {})
model = model or qa_config.get("model", DEFAULT_QA_MODEL)
```

## Dependencies

### Internal Dependencies

- `bmlibrarian.database`: Database connection management
- `bmlibrarian.config`: Configuration loading
- `bmlibrarian.embeddings.chunk_embedder`: Full-text embedding
- `bmlibrarian.discovery`: PDF discovery and download

### External Dependencies

- `ollama`: LLM inference
- `psycopg`: PostgreSQL connectivity

## Error Handling

All operations return `SemanticSearchAnswer` with error information:

```python
# Example error return
return SemanticSearchAnswer(
    answer="",
    error=QAError.DOCUMENT_NOT_FOUND,
    error_message=f"Document with ID {document_id} not found",
    document_id=document_id,
    question=question,
    model_used=model,
)
```

### Error Propagation

1. **Database errors**: Wrapped in `QAError.DATABASE_ERROR`
2. **LLM errors**: Wrapped in `QAError.LLM_ERROR`
3. **Download failures**: Logged and proceed to fallback

## Performance Considerations

### Cold Start

First query for a document may be slow due to:
- PDF download: 10-30 seconds
- Embedding generation: 2-5 seconds per document
- Query embedding: 1-2 seconds

### Warm Queries

Subsequent queries are fast:
- Semantic search: <100ms
- LLM generation: 2-10 seconds

### Optimization Strategies

1. **Pre-embed documents**: Use `ChunkEmbedder` in batch mode
2. **Lower `max_chunks`**: Reduce context for faster inference
3. **Abstract-only mode**: Skip full-text for quick answers

## Testing

### Unit Tests

Located in `tests/qa/`:

```
tests/qa/
├── __init__.py
├── test_data_types.py       # Data type tests
├── test_document_qa.py      # Function tests (mocked)
└── test_proxy_callback.py   # Proxy callback tests
```

### Integration Testing

Requires:
- PostgreSQL with migration applied
- Ollama server running
- Document in database with embeddings

```python
# Example integration test
def test_answer_from_document_integration():
    result = answer_from_document(
        document_id=12345,  # Known good document
        question="What is the sample size?"
    )
    assert result.success
    assert len(result.answer) > 0
```

## Extending the System

### Adding New Source Types

1. Add to `AnswerSource` enum
2. Implement search function
3. Update workflow in `answer_from_document()`

### Custom Models

Override via parameter or config:

```python
result = answer_from_document(
    document_id=123,
    question="...",
    model="my-custom-model:latest"
)
```

### Custom Prompts

Currently hardcoded in `_generate_answer()`. To customize:
1. Add prompt templates to config
2. Load in `_generate_answer()`

## Related Documentation

- [User Guide](../users/document_qa_guide.md)
- [Semantic Chunking Guide](../users/semantic_chunking_guide.md)
- [PDF Discovery System](full_text_discovery_system.md)
- [Database Schema](../llm/dbschema.md)
