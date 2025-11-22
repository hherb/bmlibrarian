# PaperChecker API Reference

## Module: `bmlibrarian.paperchecker`

### Main Classes

## PaperCheckerAgent

**Location:** `bmlibrarian.paperchecker.agent`

Main orchestrator for medical abstract fact-checking.

### Constructor

```python
def __init__(
    self,
    orchestrator: Optional[AgentOrchestrator] = None,
    config: Optional[Dict[str, Any]] = None,
    db_connection: Optional[psycopg.Connection] = None,
    show_model_info: bool = True
) -> None
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `orchestrator` | `Optional[AgentOrchestrator]` | `None` | Queue-based processing orchestrator |
| `config` | `Optional[Dict[str, Any]]` | `None` | Configuration dict (uses config file if None) |
| `db_connection` | `Optional[psycopg.Connection]` | `None` | Database connection (creates new if None) |
| `show_model_info` | `bool` | `True` | Display model info on initialization |

### Methods

#### `check_abstract`

```python
def check_abstract(
    self,
    abstract: str,
    source_metadata: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> PaperCheckResult
```

Check a single abstract for factual accuracy.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `abstract` | `str` | Required | Abstract text to check |
| `source_metadata` | `Optional[Dict[str, Any]]` | `None` | Metadata (pmid, doi, title, etc.) |
| `progress_callback` | `Optional[Callable[[str, float], None]]` | `None` | Progress callback(step_name, fraction) |

**Returns:** `PaperCheckResult`

**Raises:**
- `ValueError`: If abstract is empty or invalid
- `RuntimeError`: If processing fails unrecoverably

**Example:**

```python
agent = PaperCheckerAgent()

def on_progress(step: str, progress: float):
    print(f"{step}: {progress*100:.0f}%")

result = agent.check_abstract(
    abstract="Background: Type 2 diabetes...",
    source_metadata={"pmid": 12345678},
    progress_callback=on_progress
)

print(result.overall_assessment)
for verdict in result.verdicts:
    print(f"{verdict.verdict}: {verdict.rationale}")
```

#### `check_abstracts_batch`

```python
def check_abstracts_batch(
    self,
    abstracts: List[Dict[str, Any]],
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> List[PaperCheckResult]
```

Check multiple abstracts in batch.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `abstracts` | `List[Dict[str, Any]]` | Required | List of `{"abstract": str, "metadata": dict}` |
| `progress_callback` | `Optional[Callable[[int, int], None]]` | `None` | Callback(completed, total) |

**Returns:** `List[PaperCheckResult]` (successful checks only)

#### `test_connection`

```python
def test_connection(self) -> bool
```

Test connectivity to all required services.

**Returns:** `True` if all connections successful

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `max_statements` | `int` | Maximum statements to extract |
| `search_config` | `Dict[str, Any]` | Search configuration |
| `citation_config` | `Dict[str, Any]` | Citation configuration |

---

## PaperCheckDB

**Location:** `bmlibrarian.paperchecker.database`

Database interface for result persistence.

### Constructor

```python
def __init__(
    self,
    connection: Optional[psycopg.Connection] = None,
    db_name: Optional[str] = None,
    db_user: Optional[str] = None,
    db_password: Optional[str] = None,
    db_host: Optional[str] = None,
    db_port: Optional[str] = None
) -> None
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `connection` | `Optional[psycopg.Connection]` | `None` | Existing connection |
| `db_name` | `Optional[str]` | env or `"knowledgebase"` | Database name |
| `db_user` | `Optional[str]` | env | Database user |
| `db_password` | `Optional[str]` | env | Database password |
| `db_host` | `Optional[str]` | env or `"localhost"` | Database host |
| `db_port` | `Optional[str]` | env or `"5432"` | Database port |

### Methods

#### `save_complete_result`

```python
def save_complete_result(self, result: PaperCheckResult) -> int
```

Save a complete result to the database.

**Returns:** Abstract ID of saved record

#### `get_result_by_id`

```python
def get_result_by_id(self, abstract_id: int) -> Optional[Dict[str, Any]]
```

Retrieve a complete result by abstract ID.

**Returns:** Result dictionary or `None`

#### `get_results_by_pmid`

```python
def get_results_by_pmid(self, pmid: int) -> List[Dict[str, Any]]
```

Retrieve all results for a given PMID.

#### `list_recent_checks`

```python
def list_recent_checks(
    self,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]
```

List recent abstract checks.

#### `get_verdicts_summary`

```python
def get_verdicts_summary(self, abstract_id: int) -> List[Dict[str, Any]]
```

Get verdict summaries for an abstract.

#### `get_statistics`

```python
def get_statistics(self) -> Dict[str, Any]
```

Get overall database statistics.

**Returns:**

```python
{
    "total_abstracts": int,
    "total_statements": int,
    "verdicts_breakdown": {"supports": int, "contradicts": int, "undecided": int},
    "confidence_breakdown": {"high": int, "medium": int, "low": int},
    "recent_activity": int  # Last 24 hours
}
```

#### `delete_result`

```python
def delete_result(self, abstract_id: int) -> bool
```

Delete a result and all related data.

#### Context Manager

```python
with PaperCheckDB() as db:
    result_id = db.save_complete_result(result)
```

---

## Data Models

**Location:** `bmlibrarian.paperchecker.data_models`

### Statement

```python
@dataclass
class Statement:
    text: str                    # Extracted statement
    context: str                 # Surrounding context
    statement_type: str          # "hypothesis" | "finding" | "conclusion"
    confidence: float            # 0.0-1.0
    statement_order: int         # Position (1, 2, ...)
```

### CounterStatement

```python
@dataclass
class CounterStatement:
    original_statement: Statement
    negated_text: str            # Counter-claim
    hyde_abstracts: List[str]    # Hypothetical abstracts
    keywords: List[str]          # Search keywords
    generation_metadata: Dict[str, Any]
```

### SearchResults

```python
@dataclass
class SearchResults:
    semantic_docs: List[int]     # IDs from semantic search
    hyde_docs: List[int]         # IDs from HyDE search
    keyword_docs: List[int]      # IDs from keyword search
    deduplicated_docs: List[int] # Unique IDs
    provenance: Dict[int, List[str]]  # doc_id → strategies
    search_metadata: Dict[str, Any]

    @classmethod
    def from_strategy_results(
        cls,
        semantic: List[int],
        hyde: List[int],
        keyword: List[int],
        metadata: Optional[Dict[str, Any]] = None
    ) -> SearchResults
```

### ScoredDocument

```python
@dataclass
class ScoredDocument:
    doc_id: int
    document: Dict[str, Any]     # Full document data
    score: int                   # 1-5 relevance
    explanation: str             # Score reasoning
    supports_counter: bool       # score >= threshold
    found_by: List[str]          # Search strategies
```

### ExtractedCitation

```python
@dataclass
class ExtractedCitation:
    doc_id: int
    passage: str                 # Extracted text
    relevance_score: int         # Document score
    full_citation: str           # AMA-formatted
    metadata: Dict[str, Any]     # PMID, DOI, etc.
    citation_order: int          # Position in report

    def to_markdown_reference(self) -> str
```

### CounterReport

```python
@dataclass
class CounterReport:
    summary: str                 # Markdown prose
    num_citations: int
    citations: List[ExtractedCitation]
    search_stats: Dict[str, Any]
    generation_metadata: Dict[str, Any]

    def to_markdown(self) -> str
```

### Verdict

```python
@dataclass
class Verdict:
    verdict: str                 # "supports" | "contradicts" | "undecided"
    rationale: str               # 2-3 sentence explanation
    confidence: str              # "high" | "medium" | "low"
    counter_report: CounterReport
    analysis_metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]
```

### PaperCheckResult

```python
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

    def to_json_dict(self) -> Dict[str, Any]
    def to_markdown_report(self) -> str
```

---

## Components

### StatementExtractor

```python
class StatementExtractor:
    def __init__(
        self,
        model: str,
        max_statements: int = 2,
        temperature: float = 0.3,
        host: str = "http://localhost:11434"
    ) -> None

    def extract(self, abstract: str) -> List[Statement]
    def test_connection(self) -> bool
```

### CounterStatementGenerator

```python
class CounterStatementGenerator:
    def __init__(
        self,
        model: str,
        temperature: float = 0.3,
        host: str = "http://localhost:11434"
    ) -> None

    def generate(self, statement: Statement) -> str
```

### HyDEGenerator

```python
class HyDEGenerator:
    def __init__(
        self,
        model: str,
        num_abstracts: int = 2,
        max_keywords: int = 10,
        temperature: float = 0.3,
        host: str = "http://localhost:11434"
    ) -> None

    def generate(
        self,
        statement: Statement,
        negated_text: str
    ) -> Dict[str, Any]
```

### SearchCoordinator

```python
class SearchCoordinator:
    def __init__(
        self,
        config: Dict[str, Any],
        db_connection: Optional[Any] = None,
        embedding_model: Optional[str] = None,
        ollama_host: Optional[str] = None
    ) -> None

    def search(self, counter_stmt: CounterStatement) -> SearchResults
```

### VerdictAnalyzer

```python
class VerdictAnalyzer:
    def __init__(
        self,
        model: str,
        temperature: float = 0.3,
        host: str = "http://localhost:11434"
    ) -> None

    def analyze(
        self,
        statement: Statement,
        counter_report: CounterReport
    ) -> Verdict

    def generate_overall_assessment(
        self,
        statements: List[Statement],
        verdicts: List[Verdict]
    ) -> str
```

---

## Constants

### Validation Constants

```python
MIN_CONFIDENCE: float = 0.0
MAX_CONFIDENCE: float = 1.0
MIN_SCORE: int = 1
MAX_SCORE: int = 5
MIN_ORDER: int = 1
MIN_DOC_ID: int = 1

VALID_STATEMENT_TYPES: Set[str] = {"hypothesis", "finding", "conclusion"}
VALID_SEARCH_STRATEGIES: Set[str] = {"semantic", "hyde", "keyword"}
VALID_VERDICT_VALUES: Set[str] = {"supports", "contradicts", "undecided"}
VALID_CONFIDENCE_LEVELS: Set[str] = {"high", "medium", "low"}
```

### Configuration Defaults

```python
DEFAULT_MAX_STATEMENTS: int = 2
DEFAULT_TEMPERATURE: float = 0.3
DEFAULT_TOP_P: float = 0.9
DEFAULT_SCORE_THRESHOLD: float = 3.0
DEFAULT_MIN_CITATION_SCORE: int = 3
DEFAULT_HYDE_NUM_ABSTRACTS: int = 2
DEFAULT_HYDE_MAX_KEYWORDS: int = 10
DEFAULT_SEMANTIC_LIMIT: int = 50
DEFAULT_HYDE_LIMIT: int = 50
DEFAULT_KEYWORD_LIMIT: int = 50
DEFAULT_MAX_DEDUPLICATED: int = 100
DEFAULT_MAX_CITATIONS_PER_STATEMENT: int = 10
DEFAULT_SCORING_BATCH_SIZE: int = 20
DEFAULT_EARLY_STOP_COUNT: int = 20
```

---

## Exceptions

PaperChecker uses standard Python exceptions:

| Exception | When Raised |
|-----------|-------------|
| `ValueError` | Invalid input (empty abstract, bad parameters) |
| `RuntimeError` | Processing failure (LLM error, search failure) |
| `ConnectionError` | Service connectivity issues |
| `AssertionError` | Data validation failures in dataclasses |

---

## Usage Examples

### Basic Usage

```python
from bmlibrarian.paperchecker import PaperCheckerAgent

agent = PaperCheckerAgent()
result = agent.check_abstract(
    abstract="Your abstract text here...",
    source_metadata={"pmid": 12345678}
)

print(f"Overall: {result.overall_assessment}")
for v in result.verdicts:
    print(f"  {v.verdict} ({v.confidence}): {v.rationale}")
```

### With Progress Tracking

```python
def progress(step: str, fraction: float):
    print(f"[{fraction*100:3.0f}%] {step}")

result = agent.check_abstract(
    abstract="...",
    progress_callback=progress
)
```

### Batch Processing

```python
abstracts = [
    {"abstract": "First abstract...", "metadata": {"pmid": 1}},
    {"abstract": "Second abstract...", "metadata": {"pmid": 2}},
]

def batch_progress(done: int, total: int):
    print(f"Processed {done}/{total}")

results = agent.check_abstracts_batch(
    abstracts,
    progress_callback=batch_progress
)
```

### Database Operations

```python
from bmlibrarian.paperchecker.database import PaperCheckDB

with PaperCheckDB() as db:
    # List recent
    recent = db.list_recent_checks(limit=10)

    # Get stats
    stats = db.get_statistics()
    print(f"Total: {stats['total_abstracts']} abstracts")
    print(f"Verdicts: {stats['verdicts_breakdown']}")
```

---

## See Also

- [Architecture](paper_checker_architecture.md) - System design
- [Components](paper_checker_components.md) - Component details
- [Database](paper_checker_database.md) - Database schema
- [User Guide](../users/paper_checker_guide.md) - End-user docs
- [Configuration](../users/paper_checker_configuration.md) - Config options
