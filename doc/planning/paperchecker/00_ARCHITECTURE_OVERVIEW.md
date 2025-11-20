# PaperChecker Architecture Overview

## Purpose

PaperChecker is a sophisticated fact-checking system for medical abstracts that validates research claims by systematically searching for and analyzing contradictory evidence. Unlike the existing FactCheckerAgent (which validates PubMedQA dataset statements), PaperChecker focuses on analyzing complete medical abstracts and maintaining comprehensive reference tracking.

## Core Design Philosophy

PaperChecker is a **hybrid architecture** combining:
- **CounterfactualAgent patterns**: Meticulous reference tracking, multi-strategy search, citation management
- **FactCheckerAgent patterns**: Evidence evaluation, verdict generation, structured output
- **Query workflow patterns**: Semantic + HyDE + keyword search for comprehensive coverage

## High-Level Workflow

```
Abstract Input
    ↓
[1] Statement Extraction (LLM) → List[Statement]
    ↓
[2] Counter-Statement Generation (LLM) → List[CounterStatement]
    ↓
[3] HyDE + Keywords (LLM) → List[HyDE abstracts + keyword lists]
    ↓
[4] Multi-Strategy Search (Semantic + HyDE + Keyword) → List[Document IDs]
    ↓
[5] Document Scoring (ScoringAgent) → List[ScoredDocument]
    ↓
[6] Citation Extraction (CitationAgent) → List[Citation]
    ↓
[7] Counter-Report Generation (ReportingAgent patterns) → Report
    ↓
[8] Verdict Analysis (LLM) → supports/contradicts/undecided + rationale
    ↓
JSON Output
```

## Component Architecture

### 1. Core Agent
**PaperCheckerAgent** (inherits from BaseAgent)
- Main orchestrator for the entire workflow
- Manages state and context across all steps
- Coordinates sub-components and existing agents
- Handles error recovery and validation
- Queue-based processing for batch operations

### 2. Sub-Components (Internal to PaperCheckerAgent)

**StatementExtractor**
- Analyzes abstract for core research claims
- Identifies hypotheses, findings, conclusions
- Configurable max_statements (default: 2)
- Returns structured Statement objects

**CounterStatementGenerator**
- Negates extracted statements
- Similar to CounterfactualAgent's query generation
- Preserves semantic precision (e.g., "Metformin superior to GLP-1" → "GLP-1 superior or equivalent to Metformin")

**HyDEGenerator**
- Creates hypothetical abstracts supporting counter-statements
- Generates focused keyword lists
- Multiple strategies (semantic, structural, clinical)

**SearchCoordinator**
- Executes three parallel search strategies:
  1. Semantic search (embedding-based)
  2. HyDE search (hypothetical document matching)
  3. Keyword search (traditional text matching)
- Deduplicates results across strategies
- Tracks search provenance for each document

**VerdictAnalyzer**
- Analyzes counter-report against original statement
- Three-level classification: supports/contradicts/undecided
- Generates evidence-based rationale
- Confidence scoring

### 3. Integration with Existing Agents

**DocumentScoringAgent** (reuse existing)
- Ranks documents for counter-statement support
- 1-5 relevance scale
- Configured threshold (default: 3.0)

**CitationFinderAgent** (reuse existing, adapt prompts)
- Extracts passages supporting counter-statements
- Maintains document provenance
- Full citation metadata

**ReportingAgent patterns** (reuse architecture)
- Generates structured counter-evidence reports
- Professional medical writing style
- Proper reference formatting

## Data Models

### Core Data Structures

```python
@dataclass
class Statement:
    """Extracted core statement from abstract"""
    text: str
    context: str  # Surrounding sentences
    statement_type: str  # "hypothesis", "finding", "conclusion"
    confidence: float  # Extraction confidence

@dataclass
class CounterStatement:
    """Negated statement with search materials"""
    original_statement: Statement
    negated_text: str
    hyde_abstract: str
    keywords: List[str]

@dataclass
class SearchResults:
    """Multi-strategy search results"""
    semantic_docs: List[int]  # Document IDs
    hyde_docs: List[int]
    keyword_docs: List[int]
    deduplicated_docs: List[int]
    provenance: Dict[int, List[str]]  # doc_id → ["semantic", "hyde", "keyword"]

@dataclass
class ScoredDocument:
    """Document with relevance score"""
    doc_id: int
    document: Dict  # Full document data
    score: int  # 1-5
    explanation: str
    supports_counter: bool  # True if score >= threshold

@dataclass
class ExtractedCitation:
    """Citation supporting counter-statement"""
    doc_id: int
    passage: str
    relevance_score: int
    full_citation: str  # Formatted reference
    metadata: Dict  # Authors, year, journal, etc.

@dataclass
class CounterReport:
    """Synthesized counter-evidence report"""
    summary: str  # Prose report
    num_citations: int
    citations: List[ExtractedCitation]
    search_stats: Dict  # Documents found, scored, cited

@dataclass
class Verdict:
    """Final verdict on original statement"""
    verdict: str  # "supports", "contradicts", "undecided"
    rationale: str  # 2-3 sentence explanation
    confidence: str  # "high", "medium", "low"
    counter_report: CounterReport

@dataclass
class PaperCheckResult:
    """Complete result for one abstract"""
    original_abstract: str
    statements: List[Statement]
    counter_statements: List[CounterStatement]
    search_results: List[SearchResults]
    scored_documents: List[List[ScoredDocument]]  # One list per statement
    counter_reports: List[CounterReport]
    verdicts: List[Verdict]
    overall_assessment: str  # Aggregate verdict across all statements
    metadata: Dict  # Timestamps, model info, config
```

## Database Schema

New PostgreSQL schema: `papercheck`

### Tables

```sql
-- Main abstracts being checked
papercheck.abstracts_checked (
    id SERIAL PRIMARY KEY,
    abstract_text TEXT NOT NULL,
    source_pmid INTEGER,  -- Optional, if checking PubMed abstracts
    source_doi TEXT,
    checked_at TIMESTAMP DEFAULT NOW(),
    model_used VARCHAR(100),
    config JSONB
)

-- Extracted statements
papercheck.statements (
    id SERIAL PRIMARY KEY,
    abstract_id INTEGER REFERENCES papercheck.abstracts_checked(id),
    statement_text TEXT NOT NULL,
    context TEXT,
    statement_type VARCHAR(50),
    extraction_confidence FLOAT,
    statement_order INTEGER  -- 1, 2, etc.
)

-- Counter-statements
papercheck.counter_statements (
    id SERIAL PRIMARY KEY,
    statement_id INTEGER REFERENCES papercheck.statements(id),
    negated_text TEXT NOT NULL,
    hyde_abstract TEXT,
    keywords TEXT[]
)

-- Search results
papercheck.search_results (
    id SERIAL PRIMARY KEY,
    counter_statement_id INTEGER REFERENCES papercheck.counter_statements(id),
    doc_id INTEGER,  -- References main documents table
    search_strategy VARCHAR(20),  -- 'semantic', 'hyde', 'keyword'
    search_rank INTEGER,
    search_score FLOAT
)

-- Scored documents
papercheck.scored_documents (
    id SERIAL PRIMARY KEY,
    counter_statement_id INTEGER REFERENCES papercheck.counter_statements(id),
    doc_id INTEGER,
    relevance_score INTEGER CHECK (relevance_score BETWEEN 1 AND 5),
    explanation TEXT,
    supports_counter BOOLEAN
)

-- Extracted citations
papercheck.citations (
    id SERIAL PRIMARY KEY,
    counter_statement_id INTEGER REFERENCES papercheck.counter_statements(id),
    doc_id INTEGER,
    passage TEXT NOT NULL,
    relevance_score INTEGER,
    citation_order INTEGER
)

-- Counter-reports
papercheck.counter_reports (
    id SERIAL PRIMARY KEY,
    counter_statement_id INTEGER REFERENCES papercheck.counter_statements(id),
    report_text TEXT NOT NULL,
    num_citations INTEGER,
    generated_at TIMESTAMP DEFAULT NOW()
)

-- Verdicts
papercheck.verdicts (
    id SERIAL PRIMARY KEY,
    statement_id INTEGER REFERENCES papercheck.statements(id),
    verdict VARCHAR(20) CHECK (verdict IN ('supports', 'contradicts', 'undecided')),
    rationale TEXT NOT NULL,
    confidence VARCHAR(20),
    generated_at TIMESTAMP DEFAULT NOW()
)
```

## Configuration

Add to `~/.bmlibrarian/config.json`:

```json
{
  "paper_checker": {
    "model": "gpt-oss:20b",
    "temperature": 0.3,
    "max_statements": 2,
    "score_threshold": 3.0,
    "search": {
      "semantic_limit": 50,
      "hyde_limit": 50,
      "keyword_limit": 50,
      "max_deduplicated": 100
    },
    "citation": {
      "min_score": 3,
      "max_citations_per_statement": 10
    },
    "hyde": {
      "num_abstracts": 2,
      "max_keywords": 10
    }
  }
}
```

## Integration Points

### With Existing Systems

1. **QueryAgent**: Generate search queries from counter-statements
2. **DocumentScoringAgent**: Score documents for counter-statement support
3. **CitationFinderAgent**: Extract supporting passages
4. **ReportingAgent**: Generate counter-reports
5. **Database**: PostgreSQL for persistence
6. **Embeddings**: Semantic search using existing embeddings
7. **Queue System**: AgentOrchestrator for batch processing

### New Interfaces

1. **paper_checker_cli.py**: Batch processing interface
   - Input: JSON file with abstracts or PMIDs
   - Output: JSON file with complete results
   - Progress tracking and logging

2. **paper_checker_lab.py**: Interactive testing interface
   - Paste abstract
   - Step through workflow
   - Inspect intermediate results
   - Adjust parameters live

3. **Integration into bmlibrarian_cli.py**: Optional workflow step
   - After report generation
   - Validate generated report's claims

## Key Design Decisions

### 1. **Modular Architecture**
- Each workflow step is a separate method
- Easy to test, debug, and modify independently
- Facilitates partial re-runs if a step fails

### 2. **Reference Tracking**
- Every document ID is tracked from search → scoring → citation
- Provenance metadata shows which search strategy found each document
- Full citation chain maintained for transparency

### 3. **Multi-Strategy Search**
- Semantic (embedding-based): Conceptual similarity
- HyDE (hypothetical document): Structural similarity
- Keyword (traditional): Explicit term matching
- Combination captures different aspects of relevance

### 4. **Verdict Granularity**
- Per-statement verdicts (each claim evaluated independently)
- Overall assessment (aggregate across all statements)
- Confidence levels reflect evidence strength

### 5. **Queue-Based Processing**
- Support batch checking of multiple abstracts
- Memory-efficient for large datasets
- Progress tracking and error recovery

### 6. **Database Persistence**
- All intermediate results stored
- Enable analysis of system performance
- Support iterative improvement
- Facilitate human review

## Error Handling Strategy

1. **Graceful Degradation**: If one statement fails, continue with others
2. **Retry Logic**: LLM API failures get retried with exponential backoff
3. **Validation**: Verify document IDs exist before processing
4. **Logging**: Comprehensive logging at each step
5. **Checkpointing**: Save progress to database after each major step

## Testing Strategy

1. **Unit Tests**: Each component tested independently
2. **Integration Tests**: Full workflow with sample abstracts
3. **Regression Tests**: Known good/bad abstracts as benchmarks
4. **Performance Tests**: Batch processing timing
5. **Quality Tests**: Manual review of verdicts against gold standard

## Performance Considerations

- **Parallel Search**: Three search strategies can run concurrently
- **Batch Scoring**: Score all documents in batch, not one-by-one
- **Embedding Cache**: Reuse embeddings from database
- **Connection Pooling**: Efficient database access
- **Queue Processing**: Multiple abstracts processed concurrently

## Success Criteria

1. **Accuracy**: Verdicts align with expert human assessment
2. **Completeness**: Finds relevant contradictory evidence when it exists
3. **Transparency**: Full citation chain traceable
4. **Efficiency**: Processes abstract in reasonable time (<5 minutes)
5. **Reliability**: Handles edge cases gracefully
6. **Usability**: Clear CLI and lab interfaces

## Implementation Phases

See individual step files (01-16) for detailed implementation instructions.

### Phase 1: Foundation (Steps 1-3)
- Architecture & data models
- Database schema
- Core agent structure

### Phase 2: Statement Processing (Steps 4-6)
- Statement extraction
- Counter-statement generation
- HyDE & keyword generation

### Phase 3: Search & Scoring (Steps 7-9)
- Multi-strategy search
- Document scoring integration
- Citation extraction

### Phase 4: Synthesis (Steps 10-12)
- Counter-report generation
- Verdict analysis
- JSON output formatting

### Phase 5: Interfaces (Steps 13-14)
- CLI application
- Laboratory interface

### Phase 6: Quality (Steps 15-16)
- Testing suite
- Documentation
