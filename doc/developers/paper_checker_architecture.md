# PaperChecker Architecture

## System Overview

PaperChecker is a hybrid architecture combining patterns from CounterfactualAgent (reference tracking, multi-strategy search) and FactCheckerAgent (evidence evaluation, verdict generation). It provides comprehensive fact-checking for medical abstracts through systematic counter-evidence analysis.

## Component Architecture

```
┌─────────────────────────────────────────────────────────┐
│              PaperCheckerAgent                          │
│  (Main orchestrator, inherits from BaseAgent)           │
└───────────────────┬─────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
┌───────▼─────┐ ┌──▼────────┐ ┌▼──────────────┐
│ Statement   │ │ Counter-  │ │ HyDE          │
│ Extractor   │ │ Statement │ │ Generator     │
│             │ │ Generator │ │               │
└─────────────┘ └───────────┘ └───────────────┘
                    │
            ┌───────┼───────┐
            │       │       │
    ┌───────▼───┐ ┌▼───────▼────┐ ┌────────────┐
    │ Search    │ │ Document    │ │ Citation   │
    │Coordinator│ │ Scoring     │ │ Extractor  │
    │           │ │ Agent       │ │            │
    └───────────┘ └─────────────┘ └────────────┘
                    │
            ┌───────┼───────┐
            │               │
    ┌───────▼────┐  ┌──────▼────────┐
    │ Counter-   │  │ Verdict       │
    │ Report     │  │ Analyzer      │
    │ Generator  │  │               │
    └────────────┘  └───────────────┘
                    │
            ┌───────▼────────┐
            │ PaperCheckDB   │
            │ (PostgreSQL)   │
            └────────────────┘
```

## Module Structure

```
src/bmlibrarian/paperchecker/
├── __init__.py              # Module exports
├── agent.py                 # PaperCheckerAgent main orchestrator
├── data_models.py           # Type-safe dataclasses
├── database.py              # PaperCheckDB persistence layer
├── components/              # Workflow components
│   ├── __init__.py
│   ├── statement_extractor.py
│   ├── counter_statement_generator.py
│   ├── hyde_generator.py
│   ├── search_coordinator.py
│   └── verdict_analyzer.py
└── cli/                     # CLI application
    ├── __init__.py
    ├── app.py
    ├── commands.py
    └── formatters.py
```

## Workflow Steps

### Step 1: Statement Extraction

**Component:** `StatementExtractor`

- **Input:** Abstract text
- **Output:** `List[Statement]`
- **Process:** LLM analyzes abstract for core claims, hypotheses, and conclusions
- **Configuration:** `max_statements` (default: 2)

### Step 2: Counter-Statement Generation

**Component:** `CounterStatementGenerator`

- **Input:** `Statement`
- **Output:** Negated statement text
- **Process:** Semantic negation (not just adding "not")
- **Example:** "Metformin is superior" → "GLP-1 agonists are superior or equivalent"

### Step 3: HyDE Generation

**Component:** `HyDEGenerator`

- **Input:** Counter-statement
- **Output:** Hypothetical abstracts + keywords
- **Process:** Generates synthetic abstracts that would support the counter-claim
- **Configuration:** `num_abstracts` (default: 2), `max_keywords` (default: 10)

### Step 4: Multi-Strategy Search

**Component:** `SearchCoordinator`

- **Input:** Counter-statement with search materials
- **Output:** `SearchResults` with provenance
- **Process:** Three parallel strategies:
  - **Semantic:** Embedding-based conceptual similarity
  - **HyDE:** Hypothetical document matching
  - **Keyword:** Full-text search
- **Features:** Deduplication, provenance tracking

### Step 5: Document Scoring

**Component:** Reuses `DocumentScoringAgent`

- **Input:** Counter-statement + documents
- **Output:** `List[ScoredDocument]`
- **Process:** 1-5 relevance scoring with threshold filtering
- **Configuration:** `score_threshold` (default: 3.0)

### Step 6: Citation Extraction

**Component:** Reuses `CitationFinderAgent`

- **Input:** Counter-statement + high-scoring docs
- **Output:** `List[ExtractedCitation]`
- **Process:** Passage extraction with metadata
- **Configuration:** `min_score` (default: 3), `max_citations_per_statement` (default: 10)

### Step 7: Counter-Report Generation

**Component:** Built into `PaperCheckerAgent`

- **Input:** Citations + search stats
- **Output:** `CounterReport`
- **Process:** Prose synthesis with inline citations
- **Validation:** Citation format, coherence, markdown structure

### Step 8: Verdict Analysis

**Component:** `VerdictAnalyzer`

- **Input:** Original statement + counter-report
- **Output:** `Verdict`
- **Process:** Supports/contradicts/undecided classification with confidence

## Data Flow

```
Abstract
  → Statement Extraction
    → List[Statement]
      → (For each statement)
        → Counter-Statement Generation
          → Counter-Statement
            → HyDE Generation
              → HyDE abstracts + keywords
                → Multi-Strategy Search
                  → SearchResults (doc IDs + provenance)
                    → Document Scoring
                      → List[ScoredDocument]
                        → Citation Extraction
                          → List[ExtractedCitation]
                            → Counter-Report Generation
                              → CounterReport
                                → Verdict Analysis
                                  → Verdict
  → PaperCheckResult
    → Database Persistence
```

## Data Models

### Core Types

```python
@dataclass
class Statement:
    text: str                    # Extracted statement text
    context: str                 # Surrounding context
    statement_type: str          # "hypothesis", "finding", "conclusion"
    confidence: float            # 0.0-1.0 extraction confidence
    statement_order: int         # Position in abstract

@dataclass
class CounterStatement:
    original_statement: Statement
    negated_text: str            # Counter-claim text
    hyde_abstracts: List[str]    # Hypothetical abstracts
    keywords: List[str]          # Search keywords
    generation_metadata: Dict[str, Any]

@dataclass
class SearchResults:
    semantic_docs: List[int]     # IDs from semantic search
    hyde_docs: List[int]         # IDs from HyDE search
    keyword_docs: List[int]      # IDs from keyword search
    deduplicated_docs: List[int] # Unique IDs
    provenance: Dict[int, List[str]]  # doc_id → strategies
    search_metadata: Dict[str, Any]

@dataclass
class ScoredDocument:
    doc_id: int
    document: Dict[str, Any]     # Full document data
    score: int                   # 1-5 relevance score
    explanation: str             # Score reasoning
    supports_counter: bool       # score >= threshold
    found_by: List[str]          # Search strategies

@dataclass
class ExtractedCitation:
    doc_id: int
    passage: str                 # Extracted text
    relevance_score: int         # Document score
    full_citation: str           # AMA-style citation
    metadata: Dict[str, Any]     # PMID, DOI, authors, etc.
    citation_order: int          # Position in report

@dataclass
class CounterReport:
    summary: str                 # Markdown prose report
    num_citations: int
    citations: List[ExtractedCitation]
    search_stats: Dict[str, Any]
    generation_metadata: Dict[str, Any]

@dataclass
class Verdict:
    verdict: str                 # "supports", "contradicts", "undecided"
    rationale: str               # 2-3 sentence explanation
    confidence: str              # "high", "medium", "low"
    counter_report: CounterReport
    analysis_metadata: Dict[str, Any]

@dataclass
class PaperCheckResult:
    original_abstract: str
    source_metadata: Dict[str, Any]
    statements: List[Statement]
    counter_statements: List[CounterStatement]
    search_results: List[SearchResults]
    scored_documents: List[List[ScoredDocument]]
    counter_reports: List[CounterReport]
    verdicts: List[Verdict]
    overall_assessment: str
    processing_metadata: Dict[str, Any]
```

## Key Design Decisions

### 1. Multi-Strategy Search

**Why:** Different search strategies capture different aspects of relevance

- **Semantic:** Conceptual similarity via embeddings
- **HyDE:** Structural similarity to hypothetical documents
- **Keyword:** Explicit term matching

**Benefit:** Comprehensive coverage through strategy combination

### 2. Reference Tracking (Provenance)

Every document ID tracked from search → scoring → citation

**Benefits:**
- Transparency: Know which strategy found each document
- Debugging: Identify strategy effectiveness
- Optimization: Prioritize multi-strategy matches

### 3. Verdict Granularity

Per-statement verdicts + overall assessment

**Why:**
- Abstracts often contain multiple claims
- Some may be supported, others contradicted
- Granular analysis more informative

### 4. Integration Over Reimplementation

Reuses existing BMLibrarian agents:
- `DocumentScoringAgent` for relevance scoring
- `CitationFinderAgent` for passage extraction

**Benefits:**
- Code reuse and consistency
- Proven, tested components
- Faster development

### 5. Type-Safe Dataclasses

All data structures use dataclasses with validation:
- Runtime type checking via `__post_init__`
- Clear API contracts
- IDE support and documentation

## Performance Characteristics

| Metric | Typical Value | Notes |
|--------|---------------|-------|
| Single abstract | 2-5 minutes | Depends on complexity and model |
| Batch processing | Serial execution | Optimized for local Ollama |
| Bottlenecks | LLM calls | Extraction, generation, analysis |
| Memory usage | ~500MB-1GB | Per abstract processing |

### Optimization Strategies

1. **Early stopping:** Stop scoring after finding enough documents
2. **Batch scoring:** Process documents in configurable batches
3. **Fast models:** Use smaller models for scoring
4. **ID-only queries:** Fetch document IDs first, bulk retrieve data

## Error Handling

### Graceful Degradation

- If one statement fails, continue with others
- Partial results saved to database
- Errors logged for debugging

### Retry Logic

- LLM API failures retried with backoff
- Database connection pooling
- Configurable timeouts

### Validation

- Document IDs verified before processing
- Data model validation via `__post_init__`
- Input validation at API boundaries

## Extension Points

### Adding New Components

1. Create component class in `components/`
2. Implement standard interface (method signature)
3. Register in `__init__.py`
4. Wire into `PaperCheckerAgent`

### Adding New Search Strategies

1. Add strategy to `SearchCoordinator`
2. Update `SearchResults` dataclass
3. Update provenance tracking
4. Add configuration options

### Adding New Verdict Types

1. Update `VALID_VERDICT_VALUES` in `data_models.py`
2. Update `VerdictAnalyzer` prompt
3. Update database schema if needed
4. Update documentation

## Testing Strategy

### Unit Tests

Each component has isolated unit tests:
- `tests/paperchecker/test_statement_extractor.py`
- `tests/paperchecker/test_counter_generator.py`
- `tests/paperchecker/test_hyde_generator.py`
- `tests/paperchecker/test_search_coordinator.py`
- `tests/paperchecker/test_verdict_analyzer.py`

### Integration Tests

End-to-end workflow tests:
- `tests/paperchecker/test_end_to_end.py`

### Performance Tests

Processing time benchmarks:
- `tests/paperchecker/test_performance.py`

## See Also

- [Component Documentation](paper_checker_components.md) - Detailed component docs
- [Database Schema](paper_checker_database.md) - Database structure
- [API Reference](paper_checker_api_reference.md) - API documentation
- [User Guide](../users/paper_checker_guide.md) - End-user documentation
