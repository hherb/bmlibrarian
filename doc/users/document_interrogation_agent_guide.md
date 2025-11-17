# Document Interrogation Agent Guide

## Overview

The Document Interrogation Agent enables you to ask questions about large documents that exceed typical LLM context limits. It uses a sliding window approach to process documents in overlapping chunks, ensuring comprehensive coverage while maintaining context continuity.

**Key Innovation**: Unlike traditional approaches that truncate documents at 50,000 characters, this agent processes arbitrarily large documents by breaking them into manageable chunks with configurable overlap, ensuring no information is lost.

## Key Features

- **No Truncation**: Process documents of any size without losing information
- **Configurable Chunking**: Control chunk size and overlap for optimal processing
- **Multiple Processing Modes**: Choose between thoroughness and speed
- **Database Integration**: Reuse pre-chunked and pre-embedded documents
- **Progress Tracking**: Real-time feedback during chunk processing
- **Confidence Scoring**: Understand how reliable the answers are

## Processing Modes

### SEQUENTIAL Mode (Default)
**Best for: Thorough analysis, critical information**

Processes every chunk in order, extracting relevant sections from each. This ensures no information is missed but takes longer for large documents.

```python
from bmlibrarian.agents import DocumentInterrogationAgent, ProcessingMode

agent = DocumentInterrogationAgent()
result = agent.process_document(
    question="What are the cardiovascular benefits of exercise?",
    document_text=document,
    mode=ProcessingMode.SEQUENTIAL
)
```

**Pros:**
- Most thorough - examines entire document
- Best for critical medical information
- No risk of missing relevant sections

**Cons:**
- Slower for very large documents
- Higher LLM API costs

### EMBEDDING Mode
**Best for: Quick lookups, semantic search**

Uses embeddings to identify semantically similar chunks, then processes only those chunks. Much faster but may miss relevant information if semantic similarity doesn't capture the relationship well.

```python
result = agent.process_document(
    question="What side effects were reported?",
    document_text=document,
    mode=ProcessingMode.EMBEDDING
)
```

**Pros:**
- Significantly faster (5-10x)
- Lower LLM API costs
- Good for straightforward questions

**Cons:**
- May miss relevant sections with different wording
- Requires embedding generation (unless using database chunks)
- Less thorough than sequential

### HYBRID Mode
**Best for: Balanced approach**

Combines both approaches - uses embeddings to pre-filter chunks, then processes all high-similarity chunks sequentially. Provides a middle ground between speed and thoroughness.

```python
result = agent.process_document(
    question="Describe the methodology",
    document_text=document,
    mode=ProcessingMode.HYBRID
)
```

**Pros:**
- Balances speed and thoroughness
- Reduces false negatives from pure embedding mode
- Still faster than pure sequential

**Cons:**
- Still requires embedding generation
- More complex processing pipeline

## Configuration

### Basic Parameters

Edit `~/.bmlibrarian/config.json`:

```json
{
  "models": {
    "document_interrogation_agent": "gpt-oss:20b",
    "document_interrogation_embedding": "snowflake-arctic-embed2:latest"
  },
  "document_interrogation": {
    "temperature": 0.1,
    "top_p": 0.9,
    "max_tokens": 3000,
    "chunk_size": 10000,
    "chunk_overlap": 250,
    "processing_mode": "sequential",
    "embedding_threshold": 0.5,
    "max_sections": 10
  }
}
```

### Parameter Guide

**chunk_size** (default: 10000)
- Maximum characters per chunk
- Larger = more context per chunk, fewer chunks
- Smaller = more granular processing, better for pinpoint information
- Recommended range: 5000-15000

**chunk_overlap** (default: 250)
- Characters of overlap between adjacent chunks
- Ensures context continuity across chunk boundaries
- Prevents information split at boundaries from being lost
- Recommended: 2-5% of chunk_size

**processing_mode** (default: "sequential")
- Options: "sequential", "embedding", "hybrid"
- See Processing Modes section above

**embedding_threshold** (default: 0.5)
- Minimum cosine similarity for chunk selection in embedding/hybrid modes
- Range: 0.0 to 1.0
- Higher = more selective (faster but may miss sections)
- Lower = more inclusive (slower but more thorough)
- Recommended range: 0.4-0.7

**max_sections** (default: 10)
- Maximum relevant sections to extract
- Higher = more comprehensive but longer synthesis
- Lower = faster but may miss details
- Recommended range: 5-15

## Usage Examples

### Basic Usage with Raw Text

```python
from bmlibrarian.agents import DocumentInterrogationAgent, ProcessingMode

# Initialize agent
agent = DocumentInterrogationAgent(
    chunk_size=10000,
    chunk_overlap=250,
    temperature=0.1
)

# Load document
with open('research_paper.txt', 'r') as f:
    document_text = f.read()

# Ask question
result = agent.process_document(
    question="What were the primary outcomes?",
    document_text=document_text,
    mode=ProcessingMode.SEQUENTIAL,
    max_sections=10
)

# Access results
print(f"Answer: {result.answer}")
print(f"Confidence: {result.confidence:.2f}")
print(f"Sections found: {len(result.relevant_sections)}")

# Examine relevant sections
for section in result.relevant_sections:
    print(f"\nChunk {section.chunk_index + 1}:")
    print(f"Relevance: {section.relevance_score:.2f}")
    print(f"Text: {section.text[:200]}...")
    if section.reasoning:
        print(f"Reasoning: {section.reasoning}")
```

### Using Pre-Chunked Database Documents

If a document has already been ingested into BMLibrarian (chunked and embedded), you can reuse those chunks:

```python
# Use database document_id instead of text
result = agent.process_document(
    question="What are the conclusions?",
    document_id=12345,  # Document ID from database
    mode=ProcessingMode.EMBEDDING  # Fast mode using cached embeddings
)
```

**Advantages of database chunks:**
- No need to re-chunk the document
- Reuses pre-computed embeddings (faster in EMBEDDING mode)
- Consistent chunking across multiple queries
- Ideal for documents in your knowledge base

### With Progress Callbacks

Track progress during long-running operations:

```python
def progress_callback(step: str, data: str):
    print(f"[{step}] {data}")

agent = DocumentInterrogationAgent(callback=progress_callback)

result = agent.process_document(
    question="What methods were used?",
    document_text=long_document,
    mode=ProcessingMode.SEQUENTIAL
)

# Output:
# [document_interrogation_start] Processing document text (50000 chars) with mode: sequential
# [chunking_complete] Created 5 chunks (size=10000, overlap=250)
# [processing_chunk] Processing chunk 1/5
# [processing_chunk] Processing chunk 2/5
# ...
# [synthesizing_answer] Combining 8 relevant sections
```

### Batch Processing Multiple Documents

```python
from bmlibrarian.agents import DocumentInterrogationAgent, ProcessingMode

agent = DocumentInterrogationAgent()
question = "What are the main findings?"

documents = [
    ("doc1.txt", open("doc1.txt").read()),
    ("doc2.txt", open("doc2.txt").read()),
    ("doc3.txt", open("doc3.txt").read())
]

results = []
for doc_name, doc_text in documents:
    print(f"\nProcessing {doc_name}...")
    result = agent.process_document(
        question=question,
        document_text=doc_text,
        mode=ProcessingMode.EMBEDDING  # Faster for batch processing
    )
    results.append((doc_name, result))

# Compare answers across documents
for doc_name, result in results:
    print(f"\n{doc_name}: {result.answer}")
    print(f"  Confidence: {result.confidence:.2f}")
```

## Performance Considerations

### Processing Speed

**Small documents (<20,000 chars)**
- All modes perform similarly (~2-5 seconds)
- Use SEQUENTIAL for maximum accuracy

**Medium documents (20,000-100,000 chars)**
- SEQUENTIAL: 10-30 seconds
- EMBEDDING: 3-8 seconds
- HYBRID: 5-15 seconds

**Large documents (>100,000 chars)**
- SEQUENTIAL: 30-120 seconds
- EMBEDDING: 5-15 seconds
- HYBRID: 10-30 seconds

### Optimization Tips

1. **Use database chunks for repeated queries**: If you'll query the same document multiple times, ingest it into BMLibrarian first

   ```python
   # First time: ingest document
   from bmlibrarian.embeddings import DocumentEmbedder
   embedder = DocumentEmbedder()
   doc_id = embedder.embed_document(document_text, metadata={...})

   # Subsequent queries: use document_id
   result = agent.process_document(
       question="What is X?",
       document_id=doc_id,
       mode=ProcessingMode.EMBEDDING
   )
   ```

2. **Start with EMBEDDING mode**: Try faster mode first, fall back to SEQUENTIAL if answers are insufficient

3. **Adjust chunk_size**: Larger chunks reduce overhead but may dilute relevance

   ```python
   # For dense technical documents
   agent = DocumentInterrogationAgent(chunk_size=8000, chunk_overlap=500)

   # For narrative documents
   agent = DocumentInterrogationAgent(chunk_size=12000, chunk_overlap=200)
   ```

4. **Tune embedding_threshold**: Lower threshold (0.4) for better recall, higher (0.7) for better precision

5. **Cache agent instances**: Reuse agent objects instead of creating new ones for each query

## Troubleshooting

### "No chunks found for document_id"

**Cause**: Document not chunked/embedded in database, or wrong embedding model

**Solution:**
```bash
# Embed the document first
uv run python embed_documents_cli.py embed --document-id 12345
```

### "document_text cannot be empty"

**Cause**: Empty or whitespace-only document text

**Solution**: Verify document loaded correctly before processing

```python
# Validate before processing
if not document_text or not document_text.strip():
    raise ValueError("Document text is empty")

result = agent.process_document(question, document_text=document_text)
```

### Low confidence scores (<0.5)

**Possible causes:**
- Question not answerable from document
- Relevant information split across many chunks
- Processing mode too restrictive (EMBEDDING with high threshold)

**Solutions:**
- Try SEQUENTIAL mode for thorough analysis
- Lower embedding_threshold in EMBEDDING mode
- Increase max_sections to capture more context
- Rephrase question to match document terminology

```python
# Try with lower threshold
result = agent.process_document(
    question=question,
    document_text=document_text,
    mode=ProcessingMode.EMBEDDING
)

if result.confidence < 0.5:
    # Retry with sequential mode
    result = agent.process_document(
        question=question,
        document_text=document_text,
        mode=ProcessingMode.SEQUENTIAL,
        max_sections=15  # More sections
    )
```

### Very slow processing

**Cause**: Large document with SEQUENTIAL mode

**Solutions:**
- Try EMBEDDING or HYBRID mode first
- Increase chunk_size to reduce number of chunks
- Use database chunks with pre-computed embeddings
- Consider processing on more powerful hardware

## Best Practices

### Question Formulation

**Good questions:**
- "What were the primary outcomes of the clinical trial?"
- "Describe the methodology used in this study"
- "What side effects were reported in patients receiving the treatment?"
- "What are the study's limitations?"

**Poor questions:**
- "Is this good?" (too vague)
- "What does page 5 say?" (agent doesn't track page numbers)
- "Yes or no: was the study randomized?" (use full questions)

### Mode Selection

- **Critical information**: Always use SEQUENTIAL
- **Exploratory search**: Start with EMBEDDING
- **Verification**: Use HYBRID to balance speed and accuracy
- **Repeated queries**: Use database chunks with EMBEDDING

### Chunk Configuration

For most documents:
```json
{
  "chunk_size": 10000,
  "chunk_overlap": 250
}
```

For dense technical documents (medical papers):
```json
{
  "chunk_size": 8000,
  "chunk_overlap": 500
}
```

For narrative documents (case reports):
```json
{
  "chunk_size": 12000,
  "chunk_overlap": 200
}
```

## Integration with Multi-Agent Workflows

The Document Interrogation Agent can be integrated with BMLibrarian's multi-agent research workflow:

```python
from bmlibrarian.agents import (
    QueryAgent,
    DocumentScoringAgent,
    DocumentInterrogationAgent,
    AgentOrchestrator
)

# Set up orchestrator
orchestrator = AgentOrchestrator()

# Find relevant documents
query_agent = QueryAgent(orchestrator=orchestrator)
docs = query_agent.search_documents("cardiovascular benefits of exercise")

# Score documents
scoring_agent = DocumentScoringAgent(orchestrator=orchestrator)
scored_docs = [(doc, scoring_agent.evaluate_document(question, doc))
               for doc in docs]

# Deep dive into top document
interrogation_agent = DocumentInterrogationAgent(orchestrator=orchestrator)
top_doc = scored_docs[0][0]

# Get full text and ask detailed questions
result = interrogation_agent.process_document(
    question="What specific cardiovascular markers improved?",
    document_id=top_doc['id'],
    mode=ProcessingMode.SEQUENTIAL
)

print(result.answer)
```

## API Reference

### DocumentInterrogationAgent

```python
DocumentInterrogationAgent(
    model: str = "gpt-oss:20b",
    embedding_model: str = "snowflake-arctic-embed2:latest",
    host: str = "http://localhost:11434",
    temperature: float = 0.1,
    top_p: float = 0.9,
    chunk_size: int = 10000,
    chunk_overlap: int = 250,
    embedding_threshold: float = 0.5,
    callback: Optional[Callable[[str, str], None]] = None,
    orchestrator: Optional[AgentOrchestrator] = None,
    show_model_info: bool = True
)
```

### process_document()

```python
process_document(
    question: str,
    document_text: Optional[str] = None,
    document_id: Optional[int] = None,
    mode: ProcessingMode = ProcessingMode.SEQUENTIAL,
    max_sections: int = 10
) -> DocumentAnswer
```

**Parameters:**
- `question`: The question to answer about the document
- `document_text`: Full document text (mutually exclusive with document_id)
- `document_id`: Database ID of pre-chunked document (mutually exclusive with document_text)
- `mode`: Processing mode (SEQUENTIAL, EMBEDDING, or HYBRID)
- `max_sections`: Maximum relevant sections to extract

**Returns:**
- `DocumentAnswer` object with:
  - `answer`: Synthesized answer string
  - `question`: Original question
  - `confidence`: Confidence score (0.0-1.0)
  - `relevant_sections`: List of RelevantSection objects
  - `processing_mode`: Mode used
  - `metadata`: Processing metadata (chunk info, timings, etc.)

### DocumentAnswer

```python
@dataclass
class DocumentAnswer:
    answer: str
    question: str
    confidence: float
    relevant_sections: List[RelevantSection]
    processing_mode: ProcessingMode
    metadata: Dict[str, Any]
```

### RelevantSection

```python
@dataclass
class RelevantSection:
    text: str
    chunk_index: int
    start_pos: int
    end_pos: int
    relevance_score: float
    reasoning: Optional[str] = None
```

## Advanced Usage

### Custom Chunking Strategy

```python
from bmlibrarian.agents import TextChunker

# Create custom chunker
chunker = TextChunker(chunk_size=5000, overlap=100)
chunks = chunker.chunk_text(document_text)

# Process with DocumentInterrogationAgent
agent = DocumentInterrogationAgent()
# Agent will use its default chunker, but you can inspect chunks first
info = chunker.get_chunk_info(document_text)
print(f"Will create {info['num_chunks']} chunks")
```

### Error Handling

```python
from bmlibrarian.agents import DocumentInterrogationAgent, ProcessingMode

agent = DocumentInterrogationAgent()

try:
    result = agent.process_document(
        question="What is X?",
        document_text=document_text,
        mode=ProcessingMode.SEQUENTIAL
    )
except ValueError as e:
    print(f"Validation error: {e}")
except ImportError as e:
    print(f"Missing dependency: {e}")
except Exception as e:
    print(f"Processing error: {e}")
```

### Connection Testing

```python
agent = DocumentInterrogationAgent()

# Test connection to Ollama
if not agent.test_connection():
    print("Cannot connect to Ollama server")
    print("Ensure Ollama is running: ollama serve")
else:
    print("Connection successful")
```

## See Also

- [Document Interrogation Tab Guide](document_interrogation_guide.md) - GUI interface guide
- [Citation Guide](citation_guide.md) - Extracting citations from documents
- [Reporting Guide](reporting_guide.md) - Generating reports from citations
- [Multi-Model Query Guide](multi_model_query_guide.md) - Using multiple models for better results
- [Document Interrogation UI Spec](../developers/document_interrogation_ui_spec.md) - Technical UI specification
