# The Quest for Accuracy: Building a Hybrid Search System for Biomedical RAG

*An essay on the iterative development of semantic search improvements in BMLibrarian*

## Introduction

Retrieval-Augmented Generation (RAG) systems live or die by the quality of their retrieval. A language model, no matter how capable, cannot answer questions about information it cannot see. In biomedical applications, where precision matters and incorrect information can have real consequences, the stakes are even higher. This essay chronicles our journey to improve semantic search accuracy in BMLibrarian's document interrogation system, from a 60% baseline to 70% through a combination of hybrid search and query expansion.

## The Problem: When Semantic Similarity Isn't Enough

Semantic search using vector embeddings is elegant in theory: convert text to dense vectors that capture meaning, then find similar vectors using cosine similarity. For questions like "What are the health benefits of exercise?", semantic search excels—it understands that "cardiovascular improvements" and "heart health" are related concepts even without exact word matches.

But biomedical literature presents a harder challenge. Consider a question like "What was the baseline soleus muscle oxygen saturation at rest?" The answer might be a specific number: "65.2%". Semantic embeddings struggle here because:

1. **Numbers don't embed well**: The semantic relationship between "65.2%" and "baseline oxygen saturation" is weak in vector space
2. **Specificity matters**: "65.2%" and "63.8%" are semantically almost identical, but factually different
3. **Context windows**: When a chunk mentions "oxygen saturation" in one sentence and "65.2%" three sentences later, the semantic connection may be lost

We discovered this limitation not through theory but through measurement.

## Building a Benchmark: The Soleus Study Test

To improve something, you must first measure it. We created a deliberately difficult benchmark based on a real biomedical study: "Fuel selection and metabolic cost during postural sway in two lower leg muscles" (PMID 36034224). This study on soleus muscle physiology contains exactly the kind of specific factual content that challenges RAG systems.

The benchmark consists of 50 questions requiring precise extraction from the full-text PDF:

```json
{
  "question": "What was the baseline soleus muscle oxygen saturation at rest?",
  "expected_answer": "65.2%",
  "answer_aliases": ["65.2", "65.2%", "65.2 %", "approximately 65%"]
}
```

We chose this study because:
- It contains numerous specific numerical values
- Measurements appear in tables, figures, and prose
- Scientific terminology requires exact matching
- The chunking of a 20-page paper creates real retrieval challenges

Running our initial semantic-only search against this benchmark: **30 out of 50 correct (60%)**. A sobering baseline.

## Analyzing the Failures

Examining the 20 failures revealed patterns:

1. **Number retrieval failures**: Questions asking for specific measurements often retrieved chunks discussing the concept but missing the actual values
2. **Table data**: Values in tables were semantically disconnected from their column headers
3. **Synonym blindness**: "TSI" (Tissue Saturation Index) and "oxygen saturation" weren't recognized as related
4. **Unit confusion**: "30 seconds" vs "0.5 minutes"—semantically different, factually identical

The common thread: semantic similarity alone cannot bridge the gap between a question's intent and the precise textual evidence.

## The Hybrid Search Solution

The insight was simple: combine the strengths of semantic and keyword search. Semantic search finds conceptually related content; keyword search finds exact matches. By fusing their results, we can get the best of both worlds.

### PostgreSQL ts_vector for Keyword Search

PostgreSQL's full-text search provides mature, battle-tested keyword matching:

```sql
ALTER TABLE semantic.chunks
ADD COLUMN IF NOT EXISTS ts_vector tsvector;

CREATE INDEX IF NOT EXISTS idx_semantic_chunks_ts_vector
ON semantic.chunks USING GIN(ts_vector);
```

The `ts_vector` column stores pre-processed tokens with linguistic normalization—"running" and "runs" match "run". The GIN index enables fast lookups even across millions of chunks.

A trigger automatically populates the ts_vector when chunks are created:

```sql
CREATE TRIGGER trg_chunks_ts_vector
BEFORE INSERT OR UPDATE OF start_pos, end_pos ON semantic.chunks
FOR EACH ROW
EXECUTE FUNCTION semantic.chunks_ts_vector_trigger();
```

### Reciprocal Rank Fusion (RRF)

The key challenge in hybrid search is combining rankings from different systems. A chunk ranked #1 by semantic search and #50 by keyword search—how do we score it? Raw scores aren't comparable; semantic similarity might be 0.85 while keyword tf-idf is 3.7.

Reciprocal Rank Fusion provides an elegant solution:

```
RRF_score = 1 / (k + rank)
```

Where `k` is a constant (typically 60) that dampens the influence of high ranks. The beauty of RRF:

- It uses only rank positions, not raw scores
- It naturally handles different score scales
- A chunk ranked #1 by both systems gets strong reinforcement
- A chunk ranked #1 by one and #100 by the other gets modest boost

Our combined score:

```sql
combined_score = (
    semantic_weight * (1.0 / (k + semantic_rank)) +
    (1.0 - semantic_weight) * (1.0 / (k + keyword_rank))
)
```

With `semantic_weight = 0.6`, we favor semantic understanding while still benefiting from keyword precision.

### The Hybrid Search Function

The complete hybrid search function combines CTEs for clarity:

```sql
WITH
semantic_results AS (
    SELECT id, chunk_no,
           (1 - (embedding <=> query_embedding)) AS sem_score,
           ROW_NUMBER() OVER (ORDER BY embedding <=> query_embedding) AS sem_rank
    FROM semantic.chunks
    WHERE document_id = p_document_id
      AND (1 - (embedding <=> query_embedding)) >= p_semantic_threshold
),
keyword_results AS (
    SELECT id, chunk_no,
           ts_rank_cd(ts_vector, ts_query) AS kw_score,
           ROW_NUMBER() OVER (ORDER BY ts_rank_cd(ts_vector, ts_query) DESC) AS kw_rank
    FROM semantic.chunks
    WHERE document_id = p_document_id
      AND ts_vector @@ ts_query
),
combined AS (
    SELECT COALESCE(s.id, k.id) AS chunk_id,
           -- RRF combination
           ...
    FROM semantic_results s
    FULL OUTER JOIN keyword_results k ON s.id = k.id
)
SELECT ... FROM combined ORDER BY combined_score DESC;
```

The `FULL OUTER JOIN` is crucial: it includes chunks found by either method, even if the other method missed them entirely.

## First Results: Hybrid Search

Running the benchmark with hybrid search: **34 out of 50 correct (68%)**. An 8 percentage point improvement—meaningful, but not transformative. Analysis of remaining failures showed a new pattern: queries weren't generating the right keywords.

"What was the baseline soleus muscle oxygen saturation at rest?" produces the tsquery:
```
'baselin' & 'soleus' & 'muscl' & 'oxygen' & 'satur' & 'rest'
```

But if the paper uses "TSI" instead of "oxygen saturation", we miss it. If it writes "65.2%" but we're searching for the concept, not the number, keyword search can't help.

## Query Expansion: Teaching the System to Think Like a Researcher

The solution was to expand queries before searching. A researcher asking about "oxygen saturation" knows to also look for "TSI", "SpO2", and "O2 sat". We taught the system this intuition using the LLM itself:

```python
def expand_query(self, query: str) -> dict:
    """Use LLM to expand query into keywords and alternative phrasings."""

    prompt = """Analyze this question and extract search terms:

    Question: {query}

    Extract:
    1. Key technical terms
    2. Synonyms and abbreviations
    3. Specific numbers/values mentioned
    4. Alternative phrasings

    Format as JSON: {{"keywords": [...], "synonyms": [...],
                      "numbers": [...], "alternatives": [...]}}
    """
```

For "What was the baseline soleus muscle oxygen saturation at rest?", the expansion might produce:

```json
{
  "keywords": ["baseline", "soleus", "oxygen saturation", "rest"],
  "synonyms": ["TSI", "tissue saturation index", "SmO2", "resting"],
  "numbers": [],
  "alternatives": ["initial soleus oxygenation", "starting muscle O2 levels"]
}
```

The expanded search then runs multiple queries:
1. Original semantic search
2. Keyword search with extracted terms
3. Additional keyword searches with synonyms

Results are merged using RRF, giving chunks found by multiple variants stronger scores.

## Final Results: Expanded Hybrid Search

Running the benchmark with expanded hybrid search: **35 out of 50 correct (70%)**. A 10 percentage point improvement from baseline—significant in a domain where accuracy matters.

| Mode | Accuracy | Avg Time/Question |
|------|----------|-------------------|
| Semantic | 60% (30/50) | 6.7s |
| Hybrid | 68% (34/50) | 5.8s |
| Expanded | 70% (35/50) | 8.7s |

Interestingly, basic hybrid search is *faster* than pure semantic search because the lower similarity threshold (0.3 vs 0.5) allows the HNSW index to prune more aggressively. Expanded search is slower due to the LLM call for query expansion, but the accuracy gain justifies it for our use case.

## Making It the Default

With clear evidence of improved accuracy, we integrated expanded hybrid search as the default in the document interrogation system:

```python
def answer_from_document(
    document_id: int,
    question: str,
    *,
    search_mode: str = "expanded",  # NEW DEFAULT
    semantic_weight: float = 0.6,
    ...
) -> SemanticSearchAnswer:
```

Users who prefer speed over accuracy can explicitly choose `search_mode="semantic"`. But the principle we followed: **accuracy matters**. In biomedical applications, a wrong answer is worse than a slow answer.

## Lessons Learned

### 1. Measure Before Optimizing

Without the benchmark, we would have been guessing. The specific failure patterns—number retrieval, synonym blindness—only became visible through systematic measurement.

### 2. Combine Methods, Don't Choose

The hybrid approach outperformed either method alone. Semantic search handles paraphrase and conceptual matching; keyword search handles exact terms and numbers. Neither is universally better.

### 3. RRF is Remarkably Robust

Reciprocal Rank Fusion requires no tuning of score scales. It just works. The `k=60` parameter is stable across different query types and corpus sizes.

### 4. LLMs Can Bootstrap Traditional Search

Using an LLM to expand queries improves keyword search—a pleasant inversion where neural methods enhance traditional information retrieval.

### 5. Speed vs Accuracy is a Real Tradeoff

Expanded search adds ~2 seconds per query. For interactive use, this matters. We chose accuracy as the default but made speed an option.

## Future Directions

Even at 70%, 15 questions remain unanswered correctly. Analyzing these failures suggests:

1. **Multi-hop retrieval**: Some answers require combining information from multiple chunks
2. **Table understanding**: Structured data needs specialized handling
3. **Figure captions**: Values in figures are often mentioned only in captions
4. **Cross-reference resolution**: "As shown in Table 2" requires understanding document structure

Each of these represents a potential next step in our accuracy journey.

## Conclusion

The path from 60% to 70% accuracy was paved with measurement, analysis, and iterative improvement. Hybrid search with RRF provided the foundation; query expansion added the final boost. The system now provides noticeably better answers when users interrogate biomedical documents.

But perhaps the most important lesson is methodological: build a benchmark, measure relentlessly, analyze failures, and let the data guide optimization. In the quest for accuracy, there are no shortcuts—only systematic improvement.

---

*Written November 2024, documenting the implementation of hybrid semantic search in BMLibrarian's document interrogation system.*
