# Document Q&A Guide

This guide explains how to use BMLibrarian's document question-answering functionality to ask questions about specific documents in your knowledge base.

## Overview

The `answer_from_document()` function provides a high-level interface for answering questions about individual documents. It automatically:

1. Checks what text is available (full-text vs abstract)
2. Downloads missing full-text PDFs if requested
3. Generates embeddings if needed
4. Performs document-specific semantic search
5. Generates an answer using the LLM
6. Falls back to abstract if full-text is unavailable

## Quick Start

```python
from bmlibrarian.qa import answer_from_document

# Ask a question about a specific document
result = answer_from_document(
    document_id=12345,
    question="What are the main findings of this study?"
)

if result.success:
    print(f"Answer: {result.answer}")
    print(f"Source: {result.source.value}")  # 'fulltext_semantic' or 'abstract'

    # If using a thinking model, reasoning is also available
    if result.reasoning:
        print(f"Reasoning: {result.reasoning}")
else:
    print(f"Error: {result.error_message}")
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `document_id` | int | required | Database ID of the document to query |
| `question` | str | required | The question to answer |
| `use_fulltext` | bool | True | Prefer full-text over abstract when available |
| `download_missing_fulltext` | bool | True | Attempt to download PDFs if full-text is missing |
| `use_proxy` | bool | True | Use OpenAthens proxy for paywalled content |
| `model` | str | None | LLM model for answer generation (uses config if None) |
| `max_chunks` | int | 5 | Maximum context chunks to use |
| `similarity_threshold` | float | 0.7 | Minimum semantic similarity (0.0-1.0) |
| `temperature` | float | 0.3 | LLM temperature for generation |

## Return Value

The function returns a `SemanticSearchAnswer` object with these fields:

```python
@dataclass
class SemanticSearchAnswer:
    answer: str                           # The generated answer
    reasoning: Optional[str]              # Thinking/reasoning (for thinking models)
    source: AnswerSource                  # FULLTEXT_SEMANTIC or ABSTRACT
    error: Optional[QAError]              # Error enum if failed
    error_message: Optional[str]          # Detailed error message
    chunks_used: Optional[List[ChunkContext]]  # Context chunks used
    model_used: str                       # LLM model name
    document_id: int                      # The queried document
    question: str                         # The original question
    confidence: Optional[float]           # Confidence score (if available)
```

### Checking Success

```python
result = answer_from_document(document_id=123, question="...")

# Using the success property
if result.success:
    print(result.answer)
else:
    print(f"Failed: {result.error.description}")
```

### Error Types

The `QAError` enum provides structured error codes:

| Error | Description |
|-------|-------------|
| `DOCUMENT_NOT_FOUND` | Document ID doesn't exist in database |
| `NO_TEXT_AVAILABLE` | Document has neither abstract nor full-text |
| `NO_FULLTEXT` | Full-text unavailable and no abstract fallback |
| `DOWNLOAD_FAILED` | Failed to download the full-text PDF |
| `EMBEDDING_FAILED` | Failed to generate or retrieve embeddings |
| `SEMANTIC_SEARCH_FAILED` | Semantic search operation failed |
| `LLM_ERROR` | Error during LLM inference |
| `DATABASE_ERROR` | Database operation failed |
| `CONFIGURATION_ERROR` | Invalid configuration |

## Configuration

Configure the document Q&A settings in `~/.bmlibrarian/config.json`:

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
      "use_proxy": true,
      "use_thinking": true,
      "embedding_model": "snowflake-arctic-embed2:latest"
    }
  }
}
```

## Workflow Details

### 1. Text Availability Check

The function first checks what text is available for the document:

```
┌─────────────────────────────────────┐
│ get_document_text_status(doc_id)    │
├─────────────────────────────────────┤
│ has_abstract: bool                  │
│ has_fulltext: bool                  │
│ has_abstract_embeddings: bool       │
│ has_fulltext_chunks: bool           │
│ abstract_length: int                │
│ fulltext_length: int                │
└─────────────────────────────────────┘
```

### 2. Full-Text Strategy

When `use_fulltext=True`:

1. **Check for existing full-text chunks** in `semantic.chunks`
2. **If full-text exists but no chunks**: Run embedding via `ChunkEmbedder`
3. **If no full-text and `download_missing_fulltext=True`**:
   - Discover PDF via PMC, Unpaywall, DOI resolution
   - Download with browser fallback if needed
   - Use OpenAthens proxy if `use_proxy=True`
4. **If still no full-text**: Fall back to abstract

### 3. Semantic Search

The function uses document-specific SQL functions that filter at the database level:

```sql
-- For full-text chunks
SELECT * FROM semantic.chunksearch_document(
    p_document_id := 12345,
    query_text := 'What are the main findings?',
    threshold := 0.7,
    result_limit := 5
);

-- For abstract chunks (fallback)
SELECT * FROM semantic_search_document(
    p_document_id := 12345,
    query_text := 'What are the main findings?',
    threshold := 0.7,
    result_limit := 5
);
```

### 4. Answer Generation

Context is assembled from the top-scoring chunks:

```
[Chunk 1, Score: 0.89]
The study found that regular exercise reduced cardiovascular risk by 30%...

---

[Chunk 2, Score: 0.82]
Participants who exercised 3+ times per week showed significant improvement...
```

The LLM then generates an answer using this context.

## Thinking Model Support

For models that support thinking/reasoning (DeepSeek-R1, Qwen, etc.), the function:

1. Enables thinking mode via `think=True` parameter
2. Extracts reasoning from `response.message.thinking` field
3. Falls back to extracting `<think>...</think>` blocks from content

```python
result = answer_from_document(
    document_id=123,
    question="What methodology did the authors use?"
)

if result.reasoning:
    print("Model's reasoning:")
    print(result.reasoning)
    print("\nFinal answer:")
    print(result.answer)
```

## Examples

### Basic Usage

```python
from bmlibrarian.qa import answer_from_document

# Simple question
result = answer_from_document(
    document_id=42,
    question="What sample size was used in this study?"
)
print(result.answer)
```

### Prefer Abstract Only

```python
# Skip full-text, use abstract directly
result = answer_from_document(
    document_id=42,
    question="What is the main conclusion?",
    use_fulltext=False
)
```

### Offline Mode (No Downloads)

```python
# Don't attempt to download missing PDFs
result = answer_from_document(
    document_id=42,
    question="Describe the methodology",
    download_missing_fulltext=False
)
```

### Custom Model and Temperature

```python
result = answer_from_document(
    document_id=42,
    question="Summarize the findings",
    model="medgemma-27b-text-it-Q8_0:latest",
    temperature=0.1,  # More focused
    max_chunks=3      # Less context
)
```

### Accessing Chunk Details

```python
result = answer_from_document(document_id=42, question="...")

if result.chunks_used:
    for chunk in result.chunks_used:
        print(f"Chunk {chunk.chunk_no} (score: {chunk.score:.2f}):")
        print(chunk.text[:200])
        print("---")
```

## Integration with GUI

For Qt/PySide6 applications, wrap the function call in a worker thread:

```python
from PySide6.QtCore import QThread, Signal

class QAWorker(QThread):
    finished = Signal(object)

    def __init__(self, document_id: int, question: str):
        super().__init__()
        self.document_id = document_id
        self.question = question

    def run(self):
        from bmlibrarian.qa import answer_from_document
        result = answer_from_document(
            document_id=self.document_id,
            question=self.question
        )
        self.finished.emit(result)
```

## Troubleshooting

### "Document not found"
Verify the document ID exists in your database:
```sql
SELECT id, title FROM document WHERE id = 12345;
```

### "No full-text available"
Check document status:
```sql
SELECT * FROM get_document_text_status(12345);
```

### Slow Performance
- Full-text download can take 10-30 seconds
- Embedding generation takes 2-5 seconds per document
- Consider pre-embedding documents with `ChunkEmbedder`

### Low Quality Answers
- Increase `max_chunks` to provide more context
- Lower `similarity_threshold` to include more chunks
- Try a larger model (`gpt-oss:20b`)

## See Also

- [Developer Documentation](../developers/document_qa_system.md)
- [PDF Discovery Guide](pdf_download_guide.md)
- [Document Embedding Guide](document_embedding_guide.md)
- [Configuration Guide](settings_migration_guide.md)
