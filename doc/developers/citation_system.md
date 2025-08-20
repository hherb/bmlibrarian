# Citation Finder System

This document describes the BMLibrarian citation finder system for extracting verifiable citations from scored documents to support evidence-based reporting.

## Overview

The Citation Finder Agent processes documents that exceed a specified relevance score threshold to extract specific passages that answer user questions. It builds a queue of verifiable citations that can be used by reporting agents to synthesize evidence-based responses with proper references.

## Architecture

### Core Components

1. **CitationFinderAgent**: Main agent class for citation extraction
2. **Citation**: Data structure representing extracted citations
3. **Queue Integration**: Memory-efficient processing via SQLite queues
4. **Document Verification**: Ensures citation integrity and prevents hallucination

### Citation Data Structure

```python
@dataclass
class Citation:
    passage: str              # Exact text from document
    summary: str              # Brief explanation of relevance
    relevance_score: float    # 0-1 confidence score
    document_id: str          # Verified database document ID
    document_title: str       # Document title
    authors: List[str]        # Author list
    publication_date: str     # Publication date
    pmid: Optional[str]       # PubMed ID if available
    created_at: datetime      # Citation creation timestamp
```

### Processing Workflow

```
Scored Documents → Threshold Filter → Citation Extraction → Verification → Citation Queue
```

1. **Input**: Documents with relevance scores from DocumentScoringAgent
2. **Filtering**: Only process documents above score threshold (e.g., >2.0)
3. **Extraction**: Use LLM to identify relevant passages and create summaries
4. **Verification**: Ensure document IDs match database records
5. **Output**: Queue of verified citations for reporting

## Key Features

### 1. Threshold-Based Processing

Only documents exceeding a configurable score threshold are processed:

```python
citations = citation_agent.process_scored_documents_for_citations(
    user_question="What is COVID-19 vaccine effectiveness?",
    scored_documents=scored_docs,
    score_threshold=2.0,      # Only process docs scoring > 2.0
    min_relevance=0.7         # Only accept citations with relevance ≥ 0.7
)
```

### 2. LLM-Based Passage Extraction

Uses structured prompts to extract relevant passages:

```python
prompt = f"""Extract the most relevant passage from this abstract that answers: "{question}"

Response format (JSON):
{{
    "relevant_passage": "exact text from abstract",
    "summary": "brief explanation of relevance", 
    "relevance_score": 0.8,
    "has_relevant_content": true
}}"""
```

### 3. Document ID Verification

Document IDs are programmatically assigned from database records to prevent:
- Hallucinated references
- Malformed citations
- Non-existent document references

### 4. Queue-Based Processing

Supports memory-efficient processing of large document sets:

```python
# Process citations via queue system
for doc, citation in citation_agent.process_citation_queue(
    user_question=question,
    scored_documents=large_document_set,
    batch_size=25
):
    if citation:
        verified_citations.append(citation)
```

## API Reference

### CitationFinderAgent Methods

#### Core Citation Extraction

```python
def extract_citation_from_document(self, user_question: str, 
                                 document: Dict[str, Any], 
                                 min_relevance: float = 0.7) -> Optional[Citation]
```
Extract citation from single document with relevance filtering.

#### Batch Processing

```python
def process_scored_documents_for_citations(self, user_question: str,
                                         scored_documents: List[Tuple[Dict, Dict]],
                                         score_threshold: float = 2.0,
                                         min_relevance: float = 0.7) -> List[Citation]
```
Process multiple scored documents to extract qualifying citations.

#### Queue Integration

```python
def submit_citation_extraction_tasks(self, user_question: str,
                                   scored_documents: List[Tuple[Dict, Dict]],
                                   score_threshold: float = 2.0,
                                   priority: TaskPriority = TaskPriority.NORMAL) -> Optional[List[str]]
```
Submit citation extraction tasks to the processing queue.

```python
def process_citation_queue(self, user_question: str,
                         scored_documents: List[Tuple[Dict, Dict]],
                         score_threshold: float = 2.0,
                         batch_size: int = 25) -> Iterator[Tuple[Dict, Optional[Citation]]]
```
Memory-efficient citation processing using queue system.

#### Statistics and Analysis

```python
def get_citation_stats(self, citations: List[Citation]) -> Dict[str, Any]
```
Generate statistics about extracted citations including:
- Total citations and unique documents
- Average, min, max relevance scores
- Publication date ranges
- Citations per document ratio

## Implementation Details

### LLM Integration

The system uses Ollama for citation extraction with:
- **Low temperature** (0.1) for consistent extraction
- **Structured JSON responses** for reliable parsing
- **Timeout handling** for robust processing
- **Error recovery** for failed extractions

### Queue Processing

Citations integrate with the existing queue system:

```python
# Task submission
task_ids = citation_agent.submit_citation_extraction_tasks(
    user_question=question,
    scored_documents=qualifying_docs,
    priority=TaskPriority.HIGH
)

# Result collection
results = orchestrator.wait_for_completion(task_ids, timeout=60.0)
```

### Memory Efficiency

Large document sets are processed in configurable batches:
- **Batch processing**: Process documents in chunks (default 25)
- **Streaming results**: Yield citations as they're processed
- **Queue persistence**: Tasks persist across process restarts
- **Progress tracking**: Optional progress callbacks

## Usage Examples

### Basic Citation Extraction

```python
from bmlibrarian.agents import CitationFinderAgent

# Initialize agent
citation_agent = CitationFinderAgent(orchestrator=orchestrator)

# Process scored documents
citations = citation_agent.process_scored_documents_for_citations(
    user_question="What are the side effects of drug X?",
    scored_documents=scored_docs,
    score_threshold=2.5,
    min_relevance=0.8
)

# Display citations
for citation in citations:
    print(f"Document: {citation.document_title}")
    print(f"Passage: {citation.passage}")
    print(f"Summary: {citation.summary}")
    print(f"Relevance: {citation.relevance_score:.2f}")
    print(f"Reference: {citation.document_id}")
```

### Queue-Based Processing

```python
# Process large dataset efficiently
all_citations = []

def progress_callback(current, total):
    print(f"Progress: {current}/{total} ({current/total*100:.1f}%)")

for doc, citation in citation_agent.process_citation_queue(
    user_question=question,
    scored_documents=large_scored_dataset,
    score_threshold=2.0,
    progress_callback=progress_callback,
    batch_size=50
):
    if citation:
        all_citations.append(citation)

print(f"Extracted {len(all_citations)} citations")
```

### Integration with Scoring Workflow

```python
# Complete workflow: Query → Score → Cite
documents = query_agent.search_documents(user_query)

# Score documents for relevance
scored_docs = []
for doc in documents:
    score = scoring_agent.score_document_relevance(user_question, doc)
    if score:
        scored_docs.append((doc, score))

# Extract citations from high-scoring documents
citations = citation_agent.process_scored_documents_for_citations(
    user_question=user_question,
    scored_documents=scored_docs,
    score_threshold=3.0
)

# Generate report with verified citations
report_agent.generate_evidence_based_report(user_question, citations)
```

## Configuration

### Agent Initialization

```python
citation_agent = CitationFinderAgent(
    orchestrator=orchestrator,      # Required for queue processing
    ollama_url="http://localhost:11434",  # Ollama service URL
    model="gpt-oss:20b"            # LLM model for extraction (default)
)
```

### Processing Parameters

- **score_threshold**: Minimum document score to process (default: 2.0)
- **min_relevance**: Minimum citation relevance to accept (default: 0.7)
- **batch_size**: Queue processing batch size (default: 25)
- **timeout**: Task completion timeout (default: 60s)

## Quality Control

### Relevance Filtering

Citations undergo multiple quality checks:

1. **Document Score Filter**: Only high-scoring documents processed
2. **LLM Relevance Score**: Each citation rated 0-1 for relevance
3. **Minimum Threshold**: Only citations above threshold accepted
4. **Passage Validation**: Extracted text must exist in source document

### Document Verification

Document IDs are verified to ensure:
- **Database Existence**: ID exists in literature database
- **Proper Format**: ID follows expected format patterns
- **No Hallucination**: Prevents fabricated document references

### Error Handling

Robust error handling for:
- **Network Failures**: Ollama service unavailable
- **Malformed Responses**: Invalid JSON from LLM
- **Missing Data**: Documents without abstracts
- **Processing Timeouts**: Long-running extractions

## Performance Considerations

### Scaling Factors

Processing time depends on:
- **Document Count**: Linear scaling with queue batching
- **Abstract Length**: Longer abstracts take more processing
- **Model Performance**: Faster models reduce latency
- **Network Latency**: Local Ollama faster than remote

### Optimization Strategies

1. **Batch Processing**: Process documents in parallel batches
2. **Score Pre-filtering**: Only process high-scoring documents
3. **Model Selection**: Use faster models like `medgemma4B_it_q8:latest` for speed
4. **Caching**: Cache similar extractions (not currently implemented)
5. **Queue Persistence**: Resume processing after interruptions

### Monitoring

Track key metrics:
- **Processing Rate**: Documents per second
- **Citation Yield**: Citations per processed document
- **Quality Scores**: Average relevance scores
- **Error Rates**: Failed extractions per batch

## Integration Points

### Upstream Dependencies

- **QueryAgent**: Provides initial document search
- **DocumentScoringAgent**: Provides relevance scores
- **PostgreSQL Database**: Source of truth for document metadata

### Downstream Consumers

- **ReportingAgent**: Uses citations to generate evidence-based reports
- **SummaryAgent**: Creates summaries with proper citations
- **ExportAgent**: Formats citations for external systems

### Queue System Integration

- **QueueManager**: Handles task persistence and scheduling
- **AgentOrchestrator**: Coordinates multi-agent workflows
- **Recovery System**: Handles process interruptions and failures

## Security Considerations

### Data Integrity

- **Document ID Verification**: Prevents citation of non-existent documents
- **Source Attribution**: All citations traceable to database records
- **Audit Trail**: Citation creation timestamps and process tracking

### Privacy

- **No Data Logging**: Citations not logged to external systems
- **Local Processing**: All LLM processing happens locally via Ollama
- **Secure Storage**: Queue database uses SQLite with proper permissions

## Future Enhancements

### Planned Improvements

1. **Semantic Similarity**: Use embeddings for better passage matching
2. **Multi-language Support**: Extract citations from non-English papers
3. **Citation Clustering**: Group similar citations from different papers
4. **Quality Learning**: Improve extraction based on user feedback
5. **Export Formats**: Support multiple citation formats (APA, MLA, etc.)

### Advanced Features

1. **Citation Networks**: Build citation relationship graphs
2. **Temporal Analysis**: Track how findings evolve over time
3. **Contradiction Detection**: Identify conflicting findings
4. **Evidence Synthesis**: Automatically synthesize multiple citations
5. **Interactive Refinement**: Allow users to refine extraction criteria