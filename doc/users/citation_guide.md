# Citation Finder Guide

This guide explains how to use BMLibrarian's Citation Finder to extract relevant passages and build evidence-based reports with verifiable references.

## What is the Citation Finder?

The Citation Finder automatically extracts relevant passages from research papers that answer your questions. It processes documents that scored highly in relevance and finds specific text that directly supports or answers your query.

**Key Benefits:**
- ✅ **Verifiable References**: All citations link to real documents in the database
- ✅ **Relevant Passages**: Only extracts text that directly answers your question
- ✅ **Quality Control**: Filters out low-relevance content automatically
- ✅ **No Hallucination**: Cannot create fake citations or references

## How It Works

```
Your Question → Document Search → Relevance Scoring → Citation Extraction → Evidence Report
```

1. **Search**: Find documents related to your question
2. **Score**: Rate how relevant each document is (1-5 scale)
3. **Filter**: Only process documents above quality threshold (e.g., score > 2.0)
4. **Extract**: Find specific passages that answer your question
5. **Verify**: Confirm all document references are real and accurate

## Basic Usage

### Step 1: Get Scored Documents

First, you need documents with relevance scores. This typically comes from the Document Scoring Agent:

```python
from bmlibrarian.agents import DocumentScoringAgent, CitationFinderAgent

# Score documents for relevance
scoring_agent = DocumentScoringAgent()
scored_documents = []

for document in your_documents:
    score = scoring_agent.score_document_relevance(
        user_question="What are the side effects of aspirin?",
        document=document
    )
    if score:
        scored_documents.append((document, score))
```

### Step 2: Extract Citations

Process the scored documents to find relevant citations:

```python
# Initialize citation agent
citation_agent = CitationFinderAgent()

# Extract citations from high-scoring documents
citations = citation_agent.process_scored_documents_for_citations(
    user_question="What are the side effects of aspirin?",
    scored_documents=scored_documents,
    score_threshold=2.0,    # Only process docs scoring > 2.0
    min_relevance=0.7       # Only accept highly relevant citations
)

print(f"Found {len(citations)} relevant citations")
```

### Step 3: Use the Citations

Display or use the extracted citations:

```python
for citation in citations:
    print(f"Document: {citation.document_title}")
    print(f"Authors: {', '.join(citation.authors)}")
    print(f"Published: {citation.publication_date}")
    print(f"Relevant passage: \"{citation.passage}\"")
    print(f"Why it's relevant: {citation.summary}")
    print(f"Confidence: {citation.relevance_score:.2f}/1.0")
    print(f"Document ID: {citation.document_id}")
    print("-" * 50)
```

## Configuration Options

### Quality Thresholds

Control which documents get processed and which citations get accepted:

```python
citations = citation_agent.process_scored_documents_for_citations(
    user_question=question,
    scored_documents=scored_docs,
    score_threshold=3.0,    # Higher = only very relevant documents
    min_relevance=0.8       # Higher = only very relevant passages
)
```

**Recommended Settings:**
- **score_threshold**: 2.0-3.0 (documents must be somewhat to very relevant)
- **min_relevance**: 0.7-0.9 (citations must be quite to very relevant)

### Processing Large Document Sets

For thousands of documents, use queue-based processing for better performance:

```python
# Process efficiently with progress tracking
def show_progress(current, total):
    percent = (current / total) * 100
    print(f"Progress: {current}/{total} ({percent:.1f}%)")

citations = []
for doc, citation in citation_agent.process_citation_queue(
    user_question=question,
    scored_documents=large_document_set,
    score_threshold=2.5,
    progress_callback=show_progress,
    batch_size=50  # Process 50 documents at a time
):
    if citation:
        citations.append(citation)
```

## Understanding Citation Results

### Citation Structure

Each citation contains:

```python
citation.passage           # Exact text from the document
citation.summary           # Brief explanation of relevance  
citation.relevance_score   # 0.0-1.0 confidence rating
citation.document_id       # Database document identifier
citation.document_title    # Paper title
citation.authors          # List of authors
citation.publication_date # When published
citation.pmid             # PubMed ID (if available)
```

### Quality Indicators

**High Quality Citations:**
- Relevance score ≥ 0.8
- Clear, specific passages
- Direct answers to your question
- Recent publication dates

**Lower Quality Citations:**
- Relevance score 0.6-0.7
- Vague or indirect relevance
- Tangential information
- May need manual review

## Example Workflows

### Basic Research Question

```python
question = "What are the cardiovascular benefits of exercise?"

# 1. Get scored documents (assume you have them)
scored_docs = get_scored_documents(question)

# 2. Extract citations
citations = citation_agent.process_scored_documents_for_citations(
    user_question=question,
    scored_documents=scored_docs,
    score_threshold=2.5
)

# 3. Analyze results
stats = citation_agent.get_citation_stats(citations)
print(f"Found {stats['total_citations']} citations")
print(f"Average relevance: {stats['average_relevance']:.2f}")
print(f"From {stats['unique_documents']} different papers")
```

### Drug Safety Research

```python
question = "What are the side effects of metformin in elderly patients?"

# Process only highly relevant documents
citations = citation_agent.process_scored_documents_for_citations(
    user_question=question,
    scored_documents=scored_docs,
    score_threshold=3.5,    # Very high threshold
    min_relevance=0.85      # Very high relevance requirement
)

# Group by type of side effect mentioned
side_effects = {}
for citation in citations:
    # Analyze citation content (would need additional processing)
    print(f"Citation: {citation.passage}")
    print(f"Source: {citation.document_title}")
```

### Systematic Review Support

```python
# Process large literature set
all_citations = []
question = "Effectiveness of telemedicine interventions"

# Use queue processing for efficiency
for doc, citation in citation_agent.process_citation_queue(
    user_question=question,
    scored_documents=comprehensive_document_set,
    score_threshold=2.0,    # Include moderately relevant
    batch_size=100
):
    if citation and citation.relevance_score >= 0.75:
        all_citations.append(citation)

# Sort by relevance
sorted_citations = sorted(all_citations, 
                         key=lambda c: c.relevance_score, 
                         reverse=True)

# Top evidence
print("Top 10 Most Relevant Citations:")
for citation in sorted_citations[:10]:
    print(f"{citation.relevance_score:.3f}: {citation.summary}")
```

## Best Practices

### 1. Use Appropriate Thresholds

**For Broad Exploration:**
- score_threshold = 2.0
- min_relevance = 0.7

**For High-Quality Evidence:**
- score_threshold = 3.0  
- min_relevance = 0.8

**For Systematic Reviews:**
- score_threshold = 2.5
- min_relevance = 0.75

### 2. Review Citation Quality

Always review extracted citations:

```python
# Check citation statistics
stats = citation_agent.get_citation_stats(citations)

if stats['average_relevance'] < 0.7:
    print("⚠️  Low average relevance - consider raising thresholds")

if stats['total_citations'] < 3:
    print("⚠️  Few citations found - consider lowering thresholds")
```

### 3. Verify Important Citations

For critical research, manually verify key citations:

```python
# Show top citations for manual review
top_citations = sorted(citations, 
                      key=lambda c: c.relevance_score, 
                      reverse=True)[:5]

print("🔍 Please review these top citations:")
for i, citation in enumerate(top_citations, 1):
    print(f"{i}. Score: {citation.relevance_score:.3f}")
    print(f"   Document: {citation.document_title}")
    print(f"   Passage: {citation.passage}")
    print(f"   ID: {citation.document_id}")
    print()
```

### 4. Handle No Results

When no citations are found:

```python
if not citations:
    print("No citations found. Try:")
    print("• Lowering score_threshold (e.g., from 3.0 to 2.0)")
    print("• Lowering min_relevance (e.g., from 0.8 to 0.7)")  
    print("• Rephrasing your question")
    print("• Checking if documents have abstracts")
```

## Troubleshooting

### Common Issues

**"No citations found"**
- Lower your thresholds (score_threshold, min_relevance)
- Check that documents have abstracts
- Verify Ollama service is running
- Try rephrasing your question

**"Citations seem irrelevant"**
- Increase min_relevance threshold
- Review your question phrasing
- Check the original document scores

**"Processing is slow"**
- Use queue-based processing for large sets
- Increase batch_size parameter
- Consider using a faster Ollama model

**"Getting connection errors"**
- Verify Ollama is running: `curl http://localhost:11434/api/tags`
- Check the ollama_url parameter
- Ensure the specified model is downloaded

### Performance Tips

**For Large Document Sets:**
```python
# Use queue processing with larger batches
for doc, citation in citation_agent.process_citation_queue(
    user_question=question,
    scored_documents=large_set,
    batch_size=100,  # Larger batches = fewer queue operations
    score_threshold=2.5  # Pre-filter more aggressively
):
    # Process citations...
```

**For Faster Processing:**
```python
# Use a smaller, faster model
citation_agent = CitationFinderAgent(
    model="medgemma4B_it_q8:latest"  # Faster than 20b default model
)
```

## Citation Statistics

Monitor extraction quality with built-in statistics:

```python
stats = citation_agent.get_citation_stats(citations)

print(f"📊 Citation Analysis:")
print(f"   Total citations: {stats['total_citations']}")
print(f"   Unique documents: {stats['unique_documents']}")
print(f"   Average relevance: {stats['average_relevance']:.3f}")
print(f"   Relevance range: {stats['min_relevance']:.3f} - {stats['max_relevance']:.3f}")
print(f"   Citations per document: {stats['citations_per_document']:.1f}")

if 'date_range' in stats:
    print(f"   Publication range: {stats['date_range']['earliest']} to {stats['date_range']['latest']}")
```

## Integration with Other Tools

### With Document Scoring

Complete workflow from search to citations:

```python
# 1. Search documents
documents = query_agent.search_documents("diabetes treatment")

# 2. Score for relevance  
scored_docs = []
for doc in documents:
    score = scoring_agent.score_document_relevance(
        "What are effective diabetes treatments?", 
        doc
    )
    scored_docs.append((doc, score))

# 3. Extract citations
citations = citation_agent.process_scored_documents_for_citations(
    user_question="What are effective diabetes treatments?",
    scored_documents=scored_docs,
    score_threshold=2.5
)

# 4. Generate report with citations
# (would use separate reporting tool)
```

### Export for External Tools

Citations can be formatted for various uses:

```python
# Export to JSON for external processing
import json

citation_data = []
for citation in citations:
    citation_data.append({
        'passage': citation.passage,
        'summary': citation.summary, 
        'relevance': citation.relevance_score,
        'title': citation.document_title,
        'authors': citation.authors,
        'date': citation.publication_date,
        'id': citation.document_id,
        'pmid': citation.pmid
    })

with open('citations.json', 'w') as f:
    json.dump(citation_data, f, indent=2)
```

## Getting Help

For additional support:

1. **Check the logs** for error messages
2. **Verify Ollama connection** with `citation_agent.test_connection()`
3. **Review citation statistics** to understand extraction quality
4. **Try the demonstration script**: `python examples/citation_demo.py`
5. **Consult the developer documentation** for technical details

The Citation Finder is designed to provide reliable, verifiable citations for evidence-based research. With proper configuration and quality review, it can significantly speed up literature analysis while maintaining citation integrity.