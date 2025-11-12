# Fact Checker System - Developer Documentation

## Overview

The Fact Checker system provides automated verification of biomedical statements against literature evidence. It's designed for auditing LLM training data, validating medical claims, and ensuring factual accuracy in biomedical corpora.

**Architecture**: Modular PostgreSQL-based system with multi-agent orchestration and multi-user annotation support.

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                BMLibrarian Fact Checker                     │
└─────────────────────────────────────────────────────────────┘
           │
           ├─► src/bmlibrarian/factchecker/
           │   │
           │   ├─► agent/
           │   │   └─► fact_checker_agent.py (FactCheckerAgent)
           │   │       - Orchestrates multi-agent workflow
           │   │       - Coordinates query, scoring, citation agents
           │   │       - LLM evaluation synthesis
           │   │
           │   ├─► db/
           │   │   └─► database.py (FactCheckerDB)
           │   │       - PostgreSQL operations (factcheck schema)
           │   │       - Multi-user annotation support
           │   │       - No data duplication (FK to public.document)
           │   │
           │   ├─► cli/
           │   │   ├─► app.py (main CLI entry point)
           │   │   ├─► commands.py (CLI command handlers)
           │   │   └─► formatters.py (output formatting)
           │   │
           │   └─► gui/
           │       ├─► review_app.py (main GUI application)
           │       ├─► data_manager.py (database queries)
           │       ├─► annotation_manager.py (annotation logic)
           │       ├─► statement_display.py (statement UI)
           │       ├─► citation_display.py (citation cards)
           │       └─► dialogs.py (login, export dialogs)
           │
           ├─► fact_checker_cli.py (thin entry point)
           └─► fact_checker_review_gui.py (thin entry point)
```

### Data Flow

```
1. INPUT: JSON file with biomedical statements
   ↓
2. FactCheckerAgent orchestrates:
   - QueryAgent: Convert statement to database query
   - DocumentScoringAgent: Score document relevance
   - CitationFinderAgent: Extract evidence passages
   - LLM Evaluation: Synthesize yes/no/maybe with reasoning
   ↓
3. STORAGE: PostgreSQL factcheck schema
   - statements table (biomedical statements)
   - ai_evaluations table (AI fact-check results)
   - evidence table (literature citations, FK to public.document)
   - human_annotations table (multi-user annotations)
   - annotators table (user profiles)
   ↓
4. REVIEW: Human annotation via GUI
   - Login with user profile
   - Review AI evaluations and evidence
   - Provide human annotations
   - Save directly to PostgreSQL
   ↓
5. OUTPUT: JSON export or SQL queries
   - Export to JSON for analysis
   - Query database for statistics
   - Calculate inter-annotator agreement
```

## Core Classes

### FactCheckerAgent

Main orchestration agent that coordinates the fact-checking workflow.

**Location**: `src/bmlibrarian/factchecker/agent/fact_checker_agent.py`

**Inheritance**: `BaseAgent`

**Key Methods**:

```python
def check_statement(
    self,
    statement: str,
    expected_answer: Optional[str] = None,
    max_documents: Optional[int] = None,
    score_threshold: Optional[float] = None
) -> FactCheckResult:
    """
    Check a biomedical statement against literature evidence.

    Args:
        statement: The statement to fact-check
        expected_answer: Optional expected answer for validation
        max_documents: Max documents to search (overrides default)
        score_threshold: Min relevance score (overrides default)

    Returns:
        FactCheckResult with evaluation and evidence
    """
```

```python
def check_batch_from_file(
    self,
    input_file: str,
    output_file: Optional[str] = None
) -> List[FactCheckResult]:
    """
    Check multiple statements from JSON file.

    Args:
        input_file: Path to JSON file with statements
        output_file: Optional JSON export file

    Returns:
        List of FactCheckResult objects

    Notes:
        - Always stores results in PostgreSQL
        - Supports incremental mode (skip evaluated statements)
        - Supports both legacy and extracted JSON formats
    """
```

**Configuration**:

```python
agent = FactCheckerAgent(
    model="gpt-oss:20b",                # LLM for evaluation
    host="http://localhost:11434",      # Ollama host
    temperature=0.1,                    # Model temperature
    top_p=0.9,                          # Nucleus sampling
    max_tokens=2000,                    # Max response length
    score_threshold=2.5,                # Min document relevance
    max_search_results=50,              # Max documents to retrieve
    max_citations=10,                   # Max citations to extract
    callback=progress_callback,         # Progress updates
    orchestrator=orchestrator,          # Queue orchestrator
    show_model_info=True,               # Display model info
    use_database=True,                  # Use PostgreSQL storage (default)
    db_path=None,                       # Auto-managed (not used)
    incremental=False                   # Skip evaluated statements
)
```

### FactCheckerDB

Database manager for PostgreSQL operations using centralized DatabaseManager.

**Location**: `src/bmlibrarian/factchecker/db/database.py`

**Connection Management**: Uses `bmlibrarian.database.get_db_manager()` for connection pooling

**Key Methods**:

```python
def insert_statement(self, statement: Statement) -> int:
    """Insert statement or return existing ID if duplicate."""

def insert_ai_evaluation(self, evaluation: AIEvaluation) -> int:
    """Insert AI evaluation for a statement."""

def insert_evidence(self, evidence: Evidence) -> int:
    """
    Insert evidence citation.

    Note: document_id is FK to public.document(id) - NO DUPLICATION!
    """

def insert_human_annotation(self, annotation: HumanAnnotation) -> int:
    """
    Insert or update human annotation.

    Uses UPSERT (ON CONFLICT) for idempotent updates.
    """

def insert_or_get_annotator(self, annotator: Annotator) -> int:
    """Insert annotator profile or return existing ID."""

def get_all_statements_with_evaluations(self) -> List[Dict[str, Any]]:
    """
    Get all statements with their latest AI evaluations and evidence.

    Returns complete fact-check data for export or analysis.
    """

def get_statements_needing_evaluation(self, statement_texts: List[str]) -> List[str]:
    """
    Check which statements need AI evaluation (incremental mode).

    Returns list of statement texts without evaluations.
    """

def export_to_json(self, output_file: str, export_type: str = "full",
                  requested_by: str = "system") -> str:
    """
    Export database contents to JSON file.

    Args:
        output_file: Path to output JSON file
        export_type: full/ai_only/human_annotated/summary
        requested_by: Username for audit trail
    """

def import_json_results(self, json_file: str, skip_existing: bool = True) -> Dict[str, int]:
    """
    Import fact-check results from legacy JSON format.

    Supports incremental import (skip existing statements with evaluations).
    """

def get_inter_annotator_agreement(self) -> Dict[str, Any]:
    """
    Calculate inter-annotator agreement statistics.

    Uses factcheck.calculate_inter_annotator_agreement() SQL function.
    """
```

### Database Schema (PostgreSQL)

**Schema**: `factcheck` (separate from main `public` schema)

**Tables**:

```sql
-- Biomedical statements to be fact-checked
CREATE TABLE factcheck.statements (
    statement_id SERIAL PRIMARY KEY,
    statement_text TEXT NOT NULL UNIQUE,  -- Indexed for fast lookup
    input_statement_id TEXT,              -- Original ID (e.g., PMID)
    expected_answer TEXT CHECK (expected_answer IN ('yes', 'no', 'maybe')),
    created_at TIMESTAMP DEFAULT NOW(),
    source_file TEXT,
    review_status TEXT DEFAULT 'pending'
);

-- AI-generated evaluations
CREATE TABLE factcheck.ai_evaluations (
    evaluation_id SERIAL PRIMARY KEY,
    statement_id INTEGER REFERENCES factcheck.statements(statement_id),
    evaluation TEXT NOT NULL CHECK (evaluation IN ('yes', 'no', 'maybe', 'error')),
    reason TEXT NOT NULL,
    confidence TEXT CHECK (confidence IN ('high', 'medium', 'low')),
    documents_reviewed INTEGER DEFAULT 0,
    supporting_citations INTEGER DEFAULT 0,
    contradicting_citations INTEGER DEFAULT 0,
    neutral_citations INTEGER DEFAULT 0,
    matches_expected BOOLEAN,
    evaluated_at TIMESTAMP DEFAULT NOW(),
    model_used TEXT,
    model_version TEXT,
    agent_config JSONB,                   -- Configuration snapshot
    session_id TEXT,
    version INTEGER DEFAULT 1             -- Version tracking
);

-- Literature evidence citations (NO DATA DUPLICATION!)
CREATE TABLE factcheck.evidence (
    evidence_id SERIAL PRIMARY KEY,
    evaluation_id INTEGER REFERENCES factcheck.ai_evaluations(evaluation_id),
    citation_text TEXT NOT NULL,
    document_id INTEGER NOT NULL REFERENCES public.document(id),  -- FK to main table!
    pmid TEXT,
    doi TEXT,
    relevance_score FLOAT,
    supports_statement TEXT CHECK (supports_statement IN ('supports', 'contradicts', 'neutral')),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Human annotations (multi-user support)
CREATE TABLE factcheck.human_annotations (
    annotation_id SERIAL PRIMARY KEY,
    statement_id INTEGER REFERENCES factcheck.statements(statement_id),
    annotator_id INTEGER REFERENCES factcheck.annotators(annotator_id),
    annotation TEXT NOT NULL CHECK (annotation IN ('yes', 'no', 'maybe')),
    explanation TEXT,
    confidence TEXT CHECK (confidence IN ('high', 'medium', 'low')),
    review_duration_seconds INTEGER,
    review_date TIMESTAMP DEFAULT NOW(),
    session_id TEXT,
    UNIQUE (statement_id, annotator_id)   -- One annotation per user per statement
);

-- Annotator profiles
CREATE TABLE factcheck.annotators (
    annotator_id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    full_name TEXT,
    email TEXT,
    expertise_level TEXT CHECK (expertise_level IN ('expert', 'intermediate', 'novice')),
    institution TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Processing metadata
CREATE TABLE factcheck.processing_metadata (
    metadata_id SERIAL PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    input_file TEXT,
    total_statements INTEGER,
    processed_statements INTEGER DEFAULT 0,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    status TEXT DEFAULT 'running',
    config_snapshot JSONB
);

-- Export audit trail
CREATE TABLE factcheck.export_history (
    export_id SERIAL PRIMARY KEY,
    export_date TIMESTAMP DEFAULT NOW(),
    export_type TEXT,
    output_file TEXT,
    statement_count INTEGER,
    requested_by TEXT
);
```

**Helper Functions**:

```sql
-- Get or create statement (atomic upsert)
CREATE OR REPLACE FUNCTION factcheck.get_or_create_statement(
    p_statement_text TEXT,
    p_input_statement_id TEXT,
    p_expected_answer TEXT,
    p_source_file TEXT
) RETURNS INTEGER AS $$
    -- Implementation handles INSERT ON CONFLICT
$$ LANGUAGE plpgsql;

-- Get statements needing evaluation (incremental mode)
CREATE OR REPLACE FUNCTION factcheck.get_statements_needing_evaluation(
    p_statement_texts TEXT[]
) RETURNS SETOF TEXT AS $$
    -- Returns statements without AI evaluations
$$ LANGUAGE plpgsql;

-- Calculate inter-annotator agreement
CREATE OR REPLACE FUNCTION factcheck.calculate_inter_annotator_agreement()
RETURNS TABLE (total_pairs BIGINT, agreements BIGINT, disagreements BIGINT, agreement_percentage NUMERIC) AS $$
    -- Cohen's kappa or simple agreement percentage
$$ LANGUAGE plpgsql;
```

## Dataclasses

### Statement

```python
@dataclass
class Statement:
    """Represents a biomedical statement to be fact-checked."""
    statement_id: Optional[int] = None
    statement_text: str = ""
    input_statement_id: Optional[str] = None
    expected_answer: Optional[str] = None
    created_at: Optional[str] = None
    source_file: Optional[str] = None
    review_status: str = "pending"
```

### AIEvaluation

```python
@dataclass
class AIEvaluation:
    """Represents an AI-generated fact-check evaluation."""
    evaluation_id: Optional[int] = None
    statement_id: int = 0
    evaluation: str = ""                  # "yes", "no", "maybe"
    reason: str = ""
    confidence: Optional[str] = None      # "high", "medium", "low"
    documents_reviewed: int = 0
    supporting_citations: int = 0
    contradicting_citations: int = 0
    neutral_citations: int = 0
    matches_expected: Optional[bool] = None
    evaluated_at: Optional[str] = None
    model_used: Optional[str] = None
    model_version: Optional[str] = None
    agent_config: Optional[str] = None    # JSONB in database
    session_id: Optional[str] = None
    version: int = 1
```

### Evidence

```python
@dataclass
class Evidence:
    """Represents a literature citation supporting an evaluation."""
    evidence_id: Optional[int] = None
    evaluation_id: int = 0
    citation_text: str = ""
    document_id: int = 0                  # FK to public.document(id) - NO DUPLICATION!
    pmid: Optional[str] = None
    doi: Optional[str] = None
    relevance_score: Optional[float] = None
    supports_statement: Optional[str] = None  # 'supports', 'contradicts', 'neutral'
    created_at: Optional[str] = None
```

### HumanAnnotation

```python
@dataclass
class HumanAnnotation:
    """Represents a human reviewer's annotation."""
    annotation_id: Optional[int] = None
    statement_id: int = 0
    annotator_id: int = 0
    annotation: str = ""                  # "yes", "no", "maybe"
    explanation: Optional[str] = None
    confidence: Optional[str] = None      # "high", "medium", "low"
    review_duration_seconds: Optional[int] = None
    review_date: Optional[str] = None
    session_id: Optional[str] = None
```

### Annotator

```python
@dataclass
class Annotator:
    """Represents a human annotator."""
    annotator_id: Optional[int] = None
    username: str = ""
    full_name: Optional[str] = None
    email: Optional[str] = None
    expertise_level: Optional[str] = None  # "expert", "intermediate", "novice"
    institution: Optional[str] = None
    created_at: Optional[str] = None
```

## Workflow Details

### Statement Checking Workflow

```python
def check_statement(statement, expected_answer=None):
    # 1. Initialize sub-agents (QueryAgent, ScoringAgent, CitationAgent)
    _initialize_agents()

    # 2. Search for relevant documents
    documents = _search_documents(statement, max_results)
    if not documents:
        return FactCheckResult(evaluation="maybe", reason="No documents found")

    # 3. Score documents for relevance
    scored_docs = _score_documents(statement, documents, threshold)
    if not scored_docs:
        return FactCheckResult(evaluation="maybe", reason="No relevant documents")

    # 4. Extract citations from top documents
    citations = _extract_citations(statement, scored_docs)
    if not citations:
        return FactCheckResult(evaluation="maybe", reason="No citations extracted")

    # 5. Evaluate statement based on evidence
    result = _evaluate_statement(statement, citations, scored_docs, expected_answer)

    return result
```

### Batch Processing with Incremental Mode

```python
def check_batch_from_file(input_file, output_file=None):
    # 1. Load statements from JSON file
    with open(input_file, 'r') as f:
        statements = json.load(f)

    # 2. Initialize database (PostgreSQL factcheck schema)
    if self.use_database and not self.db:
        self.db = FactCheckerDB()

    # 3. Incremental mode: filter already-evaluated statements
    if self.incremental and self.db:
        # Extract statement texts
        statement_texts = [s.get('statement') or s.get('question', '') for s in statements]

        # Get statements needing evaluation
        texts_needing_eval = set(self.db.get_statements_needing_evaluation(statement_texts))

        # Filter statements list
        statements = [s for s in statements
                     if (s.get('statement') or s.get('question', '')) in texts_needing_eval]

    # 4. Process statements
    results = []
    for item in statements:
        result = self.check_statement(
            statement=item.get('statement') or item.get('question', ''),
            expected_answer=item.get('answer') or item.get('expected_answer')
        )
        results.append(result)

        # Store incrementally in database
        if self.db:
            self._store_result_in_database(result, input_file)

    # 5. Optional JSON export
    if output_file:
        self.db.export_to_json(output_file)

    return results
```

### Database Storage Workflow

```python
def _store_result_in_database(result: FactCheckResult, source_file: str):
    # 1. Insert or get statement
    stmt = Statement(
        statement_text=result.statement,
        input_statement_id=result.input_statement_id,
        expected_answer=result.expected_answer,
        source_file=source_file
    )
    statement_id = db.insert_statement(stmt)

    # 2. Insert AI evaluation
    ai_eval = AIEvaluation(
        statement_id=statement_id,
        evaluation=result.evaluation,
        reason=result.reason,
        confidence=result.confidence,
        documents_reviewed=result.documents_reviewed,
        supporting_citations=result.supporting_citations,
        contradicting_citations=result.contradicting_citations,
        neutral_citations=result.neutral_citations,
        matches_expected=result.matches_expected,
        model_used=self.model,
        session_id=self.current_session_id,
        version=1
    )
    eval_id = db.insert_ai_evaluation(ai_eval)

    # 3. Insert evidence citations
    for evidence_ref in result.evidence_list:
        evidence = Evidence(
            evaluation_id=eval_id,
            citation_text=evidence_ref.citation_text,
            document_id=evidence_ref.document_id,  # FK to public.document!
            pmid=evidence_ref.pmid,
            doi=evidence_ref.doi,
            relevance_score=evidence_ref.relevance_score,
            supports_statement="supports" if evidence_ref.supports_statement is True
                              else "contradicts" if evidence_ref.supports_statement is False
                              else "neutral"
        )
        db.insert_evidence(evidence)
```

## CLI Tool

### fact_checker_cli.py

Command-line interface for batch processing.

**Location**: `src/bmlibrarian/factchecker/cli/app.py`

**Key Functions**:

```python
def main():
    """Main entry point for fact checker CLI."""
    parser = argparse.ArgumentParser(...)

    # Parse arguments
    args = parser.parse_args()

    # Create agent
    agent = create_agent(args)

    # Test connection
    if not agent.test_connection():
        print("Cannot connect to Ollama server")
        return 1

    # Process statements
    results = agent.check_batch_from_file(
        input_file=args.input_file,
        output_file=args.output
    )

    # Print summary
    print_result_summary(results)

    if args.detailed:
        print_detailed_results(results)

    return 0
```

**Command-Line Arguments**:

- `input_file`: JSON file with statements (required)
- `-o, --output`: JSON export file (optional, database always used)
- `--incremental`: Skip already-evaluated statements
- `--model`: Ollama model name
- `--temperature`: Model temperature
- `--score-threshold`: Min relevance score
- `--max-search-results`: Max documents to search
- `--max-citations`: Max citations to extract
- `--quick`: Quick mode (fewer documents)
- `-v, --verbose`: Verbose output
- `--detailed`: Detailed results

## GUI Tool

### fact_checker_review_gui.py

Graphical interface for human annotation.

**Location**: `src/bmlibrarian/factchecker/gui/review_app.py`

**Architecture**:

```
FactCheckerReviewApp (main application)
│
├─► DataManager (database queries)
│   ├─ Load statements from PostgreSQL
│   ├─ Filter by annotator (incremental mode)
│   └─ Fetch evidence with abstracts
│
├─► AnnotationManager (annotation logic)
│   ├─ Save annotations to database
│   ├─ Track review progress
│   └─ Calculate review duration
│
├─► StatementDisplay (statement UI)
│   ├─ Display statement and annotations
│   ├─ Handle blind mode
│   └─ Navigation controls
│
├─► CitationDisplay (citation cards)
│   ├─ Expandable citation cards
│   ├─ Abstract fetching from database
│   └─ Citation highlighting
│
└─► Dialogs (login, export)
    ├─ Login dialog with user profile
    ├─ Export dialog
    └─ Error notifications
```

**Key Classes**:

```python
class FactCheckerReviewApp:
    """Main review GUI application."""

    def __init__(self, incremental=False, default_username=None, blind_mode=False):
        self.incremental = incremental
        self.default_username = default_username
        self.blind_mode = blind_mode
        self.db = FactCheckerDB()
        self.data_manager = DataManager(self.db)
        self.annotation_manager = AnnotationManager(self.db)

    def main(self, page: ft.Page):
        """Main entry point for Flet app."""
        # Initialize UI
        # Load statements from database
        # Display review interface
```

**Command-Line Arguments**:

- `--user USERNAME`: Skip login dialog
- `--incremental`: Show only unannotated statements
- `--blind`: Hide AI and original annotations

## Testing

### Test Suite

**Location**: `tests/test_fact_checker_agent.py`

**Test Coverage**:

- Agent initialization
- Dataclass creation and validation
- Statement to question conversion
- Evidence summary preparation
- Evaluation prompt creation
- Response parsing (valid, markdown, invalid)
- Confidence determination
- Workflow integration (mocked sub-agents)
- Batch processing
- Incremental mode
- Database operations
- Error handling

**Running Tests**:

```bash
# Run fact checker tests only
uv run python -m pytest tests/test_fact_checker_agent.py -v

# Run all agent tests
uv run python -m pytest tests/test_*_agent.py -v

# Run with coverage
uv run python -m pytest tests/test_fact_checker_agent.py --cov=bmlibrarian.factchecker
```

### Test Example

```python
def test_check_statement_success(self):
    """Test successful fact-checking workflow."""
    # Setup mocks
    with patch.object(self.agent, '_search_documents') as mock_search, \
         patch.object(self.agent, '_score_documents') as mock_score, \
         patch.object(self.agent, '_extract_citations') as mock_extract, \
         patch.object(self.agent, '_evaluate_statement') as mock_evaluate:

        mock_search.return_value = sample_documents
        mock_score.return_value = scored_documents
        mock_extract.return_value = sample_citations
        mock_evaluate.return_value = expected_result

        # Execute
        result = self.agent.check_statement(
            statement="Test statement",
            expected_answer="no"
        )

        # Verify
        self.assertEqual(result.evaluation, "no")
        self.assertTrue(result.matches_expected)

def test_incremental_mode(self):
    """Test incremental mode skips evaluated statements."""
    agent = FactCheckerAgent(
        model="gpt-oss:20b",
        incremental=True,
        use_database=True
    )

    # Process first batch
    results1 = agent.check_batch_from_file("statements.json")

    # Process again (should skip all)
    results2 = agent.check_batch_from_file("statements.json")

    self.assertEqual(len(results2), 0)  # All skipped
```

## Configuration

### Default Configuration

**Location**: `src/bmlibrarian/config.py`

```python
DEFAULT_CONFIG = {
    "models": {
        "fact_checker_agent": "gpt-oss:20b"
    },
    "agents": {
        "fact_checker": {
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 2000,
            "score_threshold": 2.5,
            "max_search_results": 50,
            "max_citations": 10
        }
    },
    "database": {
        "host": "localhost",
        "port": 5432,
        "database": "knowledgebase",
        "user": "your_username",
        "password": "your_password"
    }
}
```

### User Configuration

**Location**: `~/.bmlibrarian/config.json`

Users can override defaults:

```json
{
  "models": {
    "fact_checker_agent": "medgemma-27b-text-it-Q8_0:latest"
  },
  "agents": {
    "fact_checker": {
      "temperature": 0.15,
      "score_threshold": 3.0,
      "max_search_results": 100,
      "max_citations": 15
    }
  }
}
```

## Integration Examples

### Programmatic Usage

```python
from bmlibrarian.factchecker import FactCheckerAgent, FactCheckerDB
from bmlibrarian.config import get_model, get_agent_config

# Create agent
model = get_model('fact_checker_agent')
config = get_agent_config('fact_checker')

agent = FactCheckerAgent(
    model=model,
    use_database=True,
    incremental=False,
    **config
)

# Check single statement
result = agent.check_statement(
    statement="Metformin is first-line therapy for type 2 diabetes",
    expected_answer="yes"
)

print(f"Evaluation: {result.evaluation}")
print(f"Confidence: {result.confidence}")
print(f"Reason: {result.reason}")
print(f"Evidence: {len(result.evidence_list)} citations")

# Check batch from file
results = agent.check_batch_from_file(
    input_file="statements.json"
)

# Export to JSON
db = FactCheckerDB()
db.export_to_json("results.json", export_type="full", requested_by="developer")
```

### Custom Progress Callback

```python
def progress_callback(step: str, message: str):
    print(f"[{step.upper()}] {message}")

agent = FactCheckerAgent(
    model=model,
    callback=progress_callback,
    **config
)

# Output:
# [SEARCH] Searching literature for: What is the effectiveness...
# [SCORING] Scoring 15 documents...
# [EXTRACTION] Extracting evidence from 12 documents...
# [EVALUATION] Evaluating statement based on 8 citations...
# [COMPLETE] Fact-check complete: yes
```

### Database Queries

```python
db = FactCheckerDB()

# Get all statements with evaluations
statements = db.get_all_statements_with_evaluations()

# Get statements needing evaluation
to_evaluate = db.get_statements_needing_evaluation([
    "Statement 1",
    "Statement 2",
    "Statement 3"
])

# Get inter-annotator agreement
agreement = db.get_inter_annotator_agreement()
print(f"Agreement: {agreement['agreement_percentage']:.1f}%")

# Export to JSON
db.export_to_json("results.json", export_type="human_annotated")
```

### Multi-User Annotation Workflow

```python
# Annotator 1
app1 = FactCheckerReviewApp(
    incremental=True,
    default_username="alice",
    blind_mode=True
)
ft.app(target=app1.main)

# Annotator 2 (same statements)
app2 = FactCheckerReviewApp(
    incremental=True,
    default_username="bob",
    blind_mode=True
)
ft.app(target=app2.main)

# Calculate agreement
db = FactCheckerDB()
agreement = db.get_inter_annotator_agreement()
```

## Extension Points

### Custom Evaluation Logic

Override `_evaluate_statement` for custom evaluation logic:

```python
class CustomFactCheckerAgent(FactCheckerAgent):
    def _evaluate_statement(self, statement, citations, scored_docs, expected_answer):
        # Custom evaluation logic
        # Consider publication dates, journal impact factors, etc.
        # ...
        return FactCheckResult(...)
```

### Custom Confidence Scoring

Override `_determine_confidence` for domain-specific confidence assessment:

```python
class DomainFactCheckerAgent(FactCheckerAgent):
    def _determine_confidence(self, evaluation, supporting, contradicting, neutral, total_docs):
        # Domain-specific confidence logic
        # Consider publication recency, journal impact factors, etc.
        # ...
        return confidence
```

### Custom Database Queries

Extend `FactCheckerDB` for custom queries:

```python
class ExtendedFactCheckerDB(FactCheckerDB):
    def get_statements_by_model(self, model_name: str) -> List[Dict]:
        """Get all statements evaluated by specific model."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT s.*, ae.*
                    FROM factcheck.statements s
                    JOIN factcheck.ai_evaluations ae ON s.statement_id = ae.statement_id
                    WHERE ae.model_used = %s
                """, (model_name,))
                return [dict(row) for row in cur.fetchall()]
```

## Performance Optimization

### Connection Pooling

The system uses centralized DatabaseManager for connection pooling:

```python
from bmlibrarian.database import get_db_manager

# Automatic connection pooling (min=2, max=10 connections)
db_manager = get_db_manager()

# Connections automatically reused
with db_manager.get_connection() as conn:
    # Use connection
    pass
# Connection returned to pool
```

### Batch Processing

For large datasets, process in chunks:

```python
# Process in chunks
chunk_size = 100
for i in range(0, len(all_statements), chunk_size):
    chunk = all_statements[i:i+chunk_size]
    # Write chunk to temp file
    with open(f"chunk_{i}.json", 'w') as f:
        json.dump(chunk, f)

    # Process chunk
    results = agent.check_batch_from_file(f"chunk_{i}.json")
    print(f"Processed {i+chunk_size}/{len(all_statements)} statements")
```

### Incremental Mode

Use incremental mode for resume functionality:

```python
# Initial run
agent = FactCheckerAgent(model="gpt-oss:20b", incremental=False)
agent.check_batch_from_file("statements.json")

# Later: add more statements to same file
agent2 = FactCheckerAgent(model="gpt-oss:20b", incremental=True)
agent2.check_batch_from_file("statements_updated.json")
# Only processes NEW statements
```

### Lazy Loading

GUI uses lazy loading for abstracts:

```python
# Abstracts fetched only when citations are expanded
def on_citation_expand(evidence_id):
    # Fetch abstract from database
    evidence = db.get_evidence_with_abstract(evidence_id)
    # Display in UI
    display_abstract(evidence.abstract)
```

## Troubleshooting

### Common Issues

**Issue**: All results return "maybe"

**Solution**:
- Lower score threshold (try 2.0)
- Increase max_search_results
- Check database coverage for topic
- Verify statement clarity

**Issue**: Slow processing

**Solution**:
- Use faster model (medgemma4B_it_q8:latest)
- Reduce max_search_results
- Reduce max_citations
- Use incremental mode for resume
- Enable connection pooling

**Issue**: Database connection errors

**Solution**:
- Verify PostgreSQL is running
- Check credentials in config
- Ensure factcheck schema exists
- Run database migrations if needed

**Issue**: Incremental mode not working

**Solution**:
- Verify statements exist with AI evaluations
- Check statement text matches exactly (whitespace sensitive)
- Use verbose mode to see which statements are processed

### Debug Mode

Enable verbose logging for debugging:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('bmlibrarian.factchecker')
logger.setLevel(logging.DEBUG)

# Now agent operations will log detailed information
result = agent.check_statement(statement)
```

## Future Enhancements

### Planned Features

1. **Multi-Model Consensus**: Use multiple models for evaluation, combine results
2. **Temporal Analysis**: Track claim evolution over time
3. **Domain Specialization**: Fine-tuned models for specific medical domains
4. **Confidence Calibration**: Learn from validation data to improve confidence scores
5. **External Database Integration**: Connect to PubMed API, clinical trials databases
6. **Citation Quality Scoring**: Assess publication quality, impact factors
7. **Claim Decomposition**: Break complex statements into sub-claims
8. **Interactive Refinement**: Allow human feedback to improve evaluations
9. **Real-Time Updates**: Auto-update fact-checks as new literature is published

### API Considerations

For future API integration:

```python
# RESTful API endpoint example
@app.post("/api/fact-check")
def fact_check_endpoint(statement: str, expected_answer: Optional[str] = None):
    agent = get_cached_agent()
    result = agent.check_statement(statement, expected_answer)
    return result.to_dict()

@app.post("/api/fact-check/batch")
def fact_check_batch_endpoint(statements: List[Dict[str, str]]):
    agent = get_cached_agent()
    results = agent.check_batch(statements)
    return {
        "results": [r.to_dict() for r in results],
        "summary": agent._generate_summary(results)
    }

@app.get("/api/annotations/{username}")
def get_user_annotations(username: str):
    db = FactCheckerDB()
    # Get all annotations by user
    annotations = db.get_annotations_by_user(username)
    return annotations
```

## Related Documentation

- [User Guide](../users/fact_checker_guide.md)
- [Review GUI Guide](../users/fact_checker_review_guide.md)
- [Citation System](citation_system.md)
- [Query Agent](../users/query_agent_guide.md)
- [Agent Module Overview](agent_module.md)
- [Multi-Agent Architecture](agent_module.md)

## Support

For technical questions or contributions:
- GitHub Issues: https://github.com/hherb/bmlibrarian/issues
- Developer Docs: `doc/developers/`
- Test Examples: `tests/test_fact_checker_agent.py`
- Database Schema: `src/bmlibrarian/factchecker/db/database.py`
