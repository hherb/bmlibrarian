# HyDE Search User Guide

## Overview

HyDE (Hypothetical Document Embeddings) is an advanced search strategy that improves semantic retrieval by generating and searching with hypothetical documents instead of directly searching with your question.

## How HyDE Works

Traditional semantic search embeds your question and searches for similar documents. HyDE takes a different approach:

1. **Generate**: Creates hypothetical research abstracts that would answer your question
2. **Embed**: Converts these hypothetical documents to vectors
3. **Search**: Finds real documents similar to the hypothetical ones
4. **Fuse**: Combines results using Reciprocal Rank Fusion (RRF)

This approach often finds more relevant documents because hypothetical abstracts are more similar to actual research papers than raw questions.

## When to Use HyDE

### Best For:
- **Complex research questions** that need nuanced understanding
- **Broad topics** where keyword matching struggles
- **Literature reviews** requiring comprehensive coverage
- **Finding similar studies** to a hypothetical research design

### Consider Alternatives For:
- **Simple keyword searches** (use keyword or BM25 search)
- **Known entity searches** (author names, specific drugs, etc.)
- **Time-critical searches** (HyDE is slower due to document generation)

## Configuration

HyDE search is configured in `~/.bmlibrarian/config.json`:

```json
{
  "search_strategy": {
    "hyde": {
      "enabled": true,
      "max_results": 100,
      "generation_model": "medgemma-27b-text-it-Q8_0:latest",
      "embedding_model": "snowflake-arctic-embed2:latest",
      "num_hypothetical_docs": 3,
      "similarity_threshold": 0.7
    }
  }
}
```

### Configuration Parameters

#### `generation_model`
- **Purpose**: LLM used to generate hypothetical research abstracts
- **Default**: `"medgemma-27b-text-it-Q8_0:latest"` (medical domain model)
- **Alternatives**: Any Ollama model capable of scientific writing
- **Impact**: Affects quality of hypothetical documents

#### `embedding_model`
- **Purpose**: Model used to generate vector embeddings
- **Default**: `"snowflake-arctic-embed2:latest"` (matches database model_id=1)
- **Important**: **Must match** the model used to create embeddings in your database
- **Do not change** unless you re-embed all documents

#### `num_hypothetical_docs`
- **Purpose**: Number of hypothetical documents to generate
- **Default**: `3`
- **Range**: 1-5 recommended
- **Trade-offs**:
  - More docs = better coverage, slower search
  - Fewer docs = faster search, may miss relevant documents

#### `similarity_threshold`
- **Purpose**: Minimum normalized RRF score for results (0-1)
- **Default**: `0.7`
- **Interpretation**:
  - `0.9+`: Very similar to hypothetical documents
  - `0.7-0.9`: Good match
  - `0.5-0.7`: Moderate relevance
  - `<0.5`: Low relevance (usually filtered out)

#### `max_results`
- **Purpose**: Maximum documents to return after fusion
- **Default**: `100`
- **Note**: Each hypothetical document retrieves up to this many, then RRF fuses them

## Usage Examples

### Programmatic Usage

```python
import ollama
from bmlibrarian.agents.utils.hyde_search import hyde_search

# Initialize Ollama client
client = ollama.Client(host="http://localhost:11434")

# Perform HyDE search
results = hyde_search(
    question="What are the long-term cardiovascular outcomes of bariatric surgery?",
    client=client,
    generation_model="medgemma-27b-text-it-Q8_0:latest",
    embedding_model="snowflake-arctic-embed2:latest",
    max_results=100,
    num_hypothetical_docs=3,
    similarity_threshold=0.7
)

# Process results
for doc in results[:10]:
    print(f"{doc['id']}: {doc['title']}")
    print(f"  Score: {doc['score']:.3f} (RRF: {doc['rrf_score']:.3f})")
```

### With Progress Tracking

```python
def progress_callback(step: str, message: str):
    print(f"[{step.upper()}] {message}")

results = hyde_search(
    question="How does microbiome composition affect IBD treatment response?",
    client=client,
    generation_model="medgemma-27b-text-it-Q8_0:latest",
    embedding_model="snowflake-arctic-embed2:latest",
    callback=progress_callback
)

# Output:
# [HYDE_GENERATION] Generating 3 hypothetical documents...
# [HYDE_GENERATION] Generated document 1/3
# [HYDE_EMBEDDING] Generating embeddings for 3 documents...
# [HYDE_SEARCH] Searching with 3 embeddings...
# [HYDE_SEARCH] Fusing results with RRF...
# [HYDE_SEARCH] Found 45 documents above threshold
```

### Integration with QueryAgent

```python
from bmlibrarian.agents import QueryAgent
from bmlibrarian.config import get_config

# QueryAgent can use HyDE if configured
agent = QueryAgent(model="medgemma-27b-text-it-Q8_0:latest")

# HyDE will be used if enabled in config
documents = agent.search_documents(
    user_question="What are novel biomarkers for early Alzheimer's detection?"
)
```

## Understanding Results

### Result Structure

Each result includes:

```python
{
    'id': 12345678,           # Document database ID
    'title': "Study title...", # Document title
    'score': 0.85,            # Normalized RRF score (0-1)
    'rrf_score': 0.0234       # Raw RRF score
}
```

### Score Interpretation

**Normalized Score** (`score` field):
- Ranges 0-1 after min-max normalization
- Higher = better match to hypothetical documents
- Threshold filtering applied (default: 0.7)

**Raw RRF Score** (`rrf_score` field):
- Original Reciprocal Rank Fusion score
- Sum of 1/(k+rank) across all hypothetical document searches
- Not directly comparable across different searches

### Result Ordering

Results are ordered by **normalized score descending**:
1. Documents appearing in top ranks across multiple hypothetical searches score highest
2. Documents found by only one hypothetical search score lower
3. Rank position matters (appearing at rank 1 better than rank 50)

## Performance Considerations

### Speed

HyDE is slower than traditional search due to:
1. LLM generation of hypothetical documents (2-10 seconds)
2. Embedding generation (1-3 seconds per document)
3. Multiple vector searches (N searches for N hypothetical docs)

**Typical Timing** (3 hypothetical documents):
- Document generation: ~5-15 seconds
- Embedding generation: ~3-9 seconds
- Vector searches: ~1-3 seconds
- Total: ~10-30 seconds

**Optimization Tips**:
- Reduce `num_hypothetical_docs` for faster searches
- Use faster `generation_model` (smaller models)
- Consider caching for repeated queries

### Accuracy vs Speed Trade-offs

| Configuration | Speed | Coverage | Best For |
|---------------|-------|----------|----------|
| 1 hypothetical doc | Fast | Limited | Quick searches, prototyping |
| 3 hypothetical docs (default) | Moderate | Good | General research |
| 5 hypothetical docs | Slow | Excellent | Comprehensive reviews |

## Troubleshooting

### No Results Returned

**Possible Causes:**
1. `similarity_threshold` too high
   - **Solution**: Lower to 0.5-0.6
2. Hypothetical documents too specific
   - **Solution**: Rephrase question more broadly
3. Topic not well-represented in database
   - **Solution**: Try traditional keyword search

### Poor Quality Results

**Possible Causes:**
1. Generation model not suitable for biomedical content
   - **Solution**: Use medical domain models (medgemma, etc.)
2. Question too vague
   - **Solution**: Add more specific details
3. Wrong embedding model
   - **Solution**: Verify matches database model_id=1

### Errors During Generation

**"Failed to generate any hypothetical documents":**
- Check Ollama is running: `ollama serve`
- Verify model is available: `ollama list`
- Check model has enough context length for abstracts

**"Failed to generate embedding":**
- Verify embedding model is pulled: `ollama pull snowflake-arctic-embed2:latest`
- Check Ollama server has enough memory
- Try with shorter hypothetical documents

### Slow Performance

**If searches take >60 seconds:**
1. Reduce `num_hypothetical_docs` to 2 or 1
2. Use smaller `generation_model`
3. Lower `max_results` to 50
4. Check database has proper indexes on embedding columns

## Best Practices

### Question Formulation

**Good Questions for HyDE:**
- "What are the mechanisms by which exercise improves cognitive function in aging?"
- "How does gut microbiome composition affect response to immunotherapy in melanoma?"
- "What are the long-term outcomes of minimally invasive cardiac surgery?"

**Less Suitable for HyDE:**
- "aspirin" (too broad, use keyword search)
- "PMID:12345678" (specific ID, use direct lookup)
- "John Smith" (author search, use different strategy)

### Combining with Other Searches

HyDE works well in multi-strategy approaches:

```python
# 1. HyDE search for broad coverage
hyde_results = hyde_search(question, client, ...)

# 2. Keyword search for specific terms
keyword_results = keyword_search("aspirin AND myocardial infarction")

# 3. Combine and deduplicate
all_results = combine_and_deduplicate(hyde_results, keyword_results)
```

### Iterative Refinement

If initial results aren't satisfactory:

1. **Analyze hypothetical documents** (enable logging)
   - Are they realistic research abstracts?
   - Do they capture your question's intent?
2. **Adjust question** based on what was generated
3. **Try different generation models**
4. **Tune threshold** if too many/few results

## Advanced Usage

### Custom Temperature

For more diverse hypothetical documents:

```python
from bmlibrarian.agents.utils.hyde_search import generate_hypothetical_documents

hypothetical_docs = generate_hypothetical_documents(
    question="...",
    client=client,
    model="medgemma-27b-text-it-Q8_0:latest",
    num_docs=5,
    temperature=0.5  # Higher = more diversity
)
```

### Analyzing Generated Documents

```python
# Generate and inspect hypothetical documents
docs = generate_hypothetical_documents(
    question="What are biomarkers for Crohn's disease activity?",
    client=client,
    model="medgemma-27b-text-it-Q8_0:latest",
    num_docs=3
)

for i, doc in enumerate(docs, 1):
    print(f"\n=== Hypothetical Document {i} ===")
    print(doc)
```

### Custom RRF Parameters

The RRF fusion uses k=60 by default (literature standard):

```python
from bmlibrarian.agents.utils.hyde_search import reciprocal_rank_fusion

# Fuse with different k (lower k = more weight to top ranks)
fused = reciprocal_rank_fusion(all_results, k=30)
```

## Related Documentation

- [Developer Guide](../developers/hyde_architecture.md) - Technical implementation details
- [Query Agent Guide](query_agent_guide.md) - Natural language query processing
- [Citation Guide](citation_guide.md) - Working with search results

## References

**HyDE Method:**
- Gao, L., Ma, X., Lin, J., & Callan, J. (2022). "Precise Zero-Shot Dense Retrieval without Relevance Labels." arXiv preprint arXiv:2212.10496.

**Reciprocal Rank Fusion:**
- Cormack, G. V., Clarke, C. L., & Buettcher, S. (2009). "Reciprocal rank fusion outperforms condorcet and individual rank learning methods." SIGIR 2009.
