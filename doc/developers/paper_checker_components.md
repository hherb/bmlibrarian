# PaperChecker Component Documentation

## Overview

PaperChecker is built from modular, independently testable components. Each component implements a specific step in the fact-checking workflow.

## Component Summary

| Component | Purpose | Input | Output |
|-----------|---------|-------|--------|
| `StatementExtractor` | Extract claims from abstracts | Abstract text | `List[Statement]` |
| `CounterStatementGenerator` | Generate counter-claims | `Statement` | Negated text |
| `HyDEGenerator` | Generate search materials | Statement + negation | HyDE abstracts + keywords |
| `SearchCoordinator` | Multi-strategy search | `CounterStatement` | `SearchResults` |
| `VerdictAnalyzer` | Analyze evidence | Statement + report | `Verdict` |

## StatementExtractor

**Location:** `src/bmlibrarian/paperchecker/components/statement_extractor.py`

### Purpose

Extracts core research claims, hypotheses, and findings from medical abstracts using LLM analysis. This is the first step in the PaperChecker workflow.

### Class Definition

```python
class StatementExtractor:
    def __init__(
        self,
        model: str,
        max_statements: int = 2,
        temperature: float = 0.3,
        host: str = "http://localhost:11434"
    ) -> None: ...

    def extract(self, abstract: str) -> List[Statement]: ...
    def test_connection(self) -> bool: ...
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str` | Required | Ollama model name |
| `max_statements` | `int` | `2` | Maximum statements to extract |
| `temperature` | `float` | `0.3` | LLM temperature |
| `host` | `str` | `"http://localhost:11434"` | Ollama server URL |

### Output: Statement

```python
@dataclass
class Statement:
    text: str                # Extracted statement text
    context: str             # Surrounding context
    statement_type: str      # "hypothesis", "finding", "conclusion"
    confidence: float        # 0.0-1.0 extraction confidence
    statement_order: int     # Position in abstract (1, 2, ...)
```

### Usage Example

```python
from bmlibrarian.paperchecker.components import StatementExtractor

extractor = StatementExtractor(
    model="gpt-oss:20b",
    max_statements=2,
    temperature=0.3
)

abstract = "Background: Type 2 diabetes... Conclusion: Metformin is superior."
statements = extractor.extract(abstract)

for stmt in statements:
    print(f"{stmt.statement_type}: {stmt.text}")
```

### Validation

- Abstract must be at least 50 characters
- Statement type must be "hypothesis", "finding", or "conclusion"
- Confidence must be between 0.0 and 1.0

---

## CounterStatementGenerator

**Location:** `src/bmlibrarian/paperchecker/components/counter_statement_generator.py`

### Purpose

Generates semantically precise negations of research claims. Unlike simple negation (adding "not"), this component creates meaningful counter-claims that represent alternative hypotheses.

### Class Definition

```python
class CounterStatementGenerator:
    def __init__(
        self,
        model: str,
        temperature: float = 0.3,
        host: str = "http://localhost:11434"
    ) -> None: ...

    def generate(self, statement: Statement) -> str: ...
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str` | Required | Ollama model name |
| `temperature` | `float` | `0.3` | LLM temperature |
| `host` | `str` | `"http://localhost:11434"` | Ollama server URL |

### Negation Strategy

The generator creates semantic negations, not syntactic ones:

| Original | Poor Negation | Good Negation |
|----------|---------------|---------------|
| "Metformin is superior to GLP-1" | "Metformin is not superior" | "GLP-1 agonists are superior or equivalent to metformin" |
| "Exercise reduces mortality" | "Exercise does not reduce mortality" | "Exercise has no significant effect on, or increases, mortality" |

### Usage Example

```python
from bmlibrarian.paperchecker.components import CounterStatementGenerator

generator = CounterStatementGenerator(model="gpt-oss:20b")

# Assume statement is from StatementExtractor
counter_text = generator.generate(statement)
print(f"Counter-claim: {counter_text}")
```

---

## HyDEGenerator

**Location:** `src/bmlibrarian/paperchecker/components/hyde_generator.py`

### Purpose

Generates Hypothetical Document Embeddings (HyDE) materials for improved document search. Creates synthetic abstracts and keywords that would support the counter-claim.

### Class Definition

```python
class HyDEGenerator:
    def __init__(
        self,
        model: str,
        num_abstracts: int = 2,
        max_keywords: int = 10,
        temperature: float = 0.3,
        host: str = "http://localhost:11434"
    ) -> None: ...

    def generate(
        self,
        statement: Statement,
        negated_text: str
    ) -> Dict[str, Any]: ...
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str` | Required | Ollama model name |
| `num_abstracts` | `int` | `2` | Number of HyDE abstracts to generate |
| `max_keywords` | `int` | `10` | Maximum keywords to extract |
| `temperature` | `float` | `0.3` | LLM temperature |
| `host` | `str` | `"http://localhost:11434"` | Ollama server URL |

### Output Structure

```python
{
    "hyde_abstracts": [
        "A hypothetical abstract supporting the counter-claim...",
        "Another hypothetical abstract..."
    ],
    "keywords": [
        "GLP-1 agonist",
        "metformin comparison",
        "diabetes efficacy",
        ...
    ]
}
```

### Usage Example

```python
from bmlibrarian.paperchecker.components import HyDEGenerator

generator = HyDEGenerator(
    model="gpt-oss:20b",
    num_abstracts=2,
    max_keywords=10
)

materials = generator.generate(statement, "GLP-1 agonists are superior")
print(f"Generated {len(materials['hyde_abstracts'])} HyDE abstracts")
print(f"Keywords: {materials['keywords']}")
```

---

## SearchCoordinator

**Location:** `src/bmlibrarian/paperchecker/components/search_coordinator.py`

### Purpose

Coordinates multi-strategy document search combining semantic, HyDE, and keyword-based approaches. Handles deduplication and provenance tracking.

### Class Definition

```python
class SearchCoordinator:
    def __init__(
        self,
        config: Dict[str, Any],
        db_connection: Optional[Any] = None,
        embedding_model: Optional[str] = None,
        ollama_host: Optional[str] = None
    ) -> None: ...

    def search(self, counter_stmt: CounterStatement) -> SearchResults: ...
```

### Configuration

```python
config = {
    "semantic_limit": 50,      # Max docs from semantic search
    "hyde_limit": 50,          # Max docs from HyDE search (per abstract)
    "keyword_limit": 50,       # Max docs from keyword search
    "max_deduplicated": 100,   # Max total unique docs
    "embedding_model": "snowflake-arctic-embed2:latest"
}
```

### Search Strategies

1. **Semantic Search**
   - Generates embedding for counter-statement
   - Uses pgvector for cosine similarity search
   - Returns documents conceptually similar to counter-claim

2. **HyDE Search**
   - Generates embeddings for hypothetical abstracts
   - Searches for documents similar to hypothetical papers
   - Finds structurally similar research

3. **Keyword Search**
   - Uses PostgreSQL full-text search (ts_vector)
   - Matches generated keywords against abstracts
   - Captures explicit term matches

### Output: SearchResults

```python
@dataclass
class SearchResults:
    semantic_docs: List[int]     # IDs from semantic search
    hyde_docs: List[int]         # IDs from HyDE search
    keyword_docs: List[int]      # IDs from keyword search
    deduplicated_docs: List[int] # Unique IDs across strategies
    provenance: Dict[int, List[str]]  # doc_id → strategies that found it
    search_metadata: Dict[str, Any]   # Timing, limits, etc.
```

### Provenance Tracking

```python
# Example provenance
provenance = {
    12345: ["semantic", "keyword"],  # Found by 2 strategies
    23456: ["semantic"],             # Found by semantic only
    34567: ["hyde", "keyword"],      # Found by HyDE and keyword
}
```

### Usage Example

```python
from bmlibrarian.paperchecker.components import SearchCoordinator

config = {
    "semantic_limit": 50,
    "hyde_limit": 50,
    "keyword_limit": 50,
    "max_deduplicated": 100
}

coordinator = SearchCoordinator(config=config)
results = coordinator.search(counter_statement)

print(f"Found {len(results.deduplicated_docs)} unique documents")
print(f"Semantic: {len(results.semantic_docs)}")
print(f"HyDE: {len(results.hyde_docs)}")
print(f"Keyword: {len(results.keyword_docs)}")
```

---

## VerdictAnalyzer

**Location:** `src/bmlibrarian/paperchecker/components/verdict_analyzer.py`

### Purpose

Analyzes counter-evidence and generates verdicts on whether evidence supports, contradicts, or is undecided about the original claim.

### Class Definition

```python
class VerdictAnalyzer:
    def __init__(
        self,
        model: str,
        temperature: float = 0.3,
        host: str = "http://localhost:11434"
    ) -> None: ...

    def analyze(
        self,
        statement: Statement,
        counter_report: CounterReport
    ) -> Verdict: ...

    def generate_overall_assessment(
        self,
        statements: List[Statement],
        verdicts: List[Verdict]
    ) -> str: ...
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str` | Required | Ollama model name |
| `temperature` | `float` | `0.3` | LLM temperature |
| `host` | `str` | `"http://localhost:11434"` | Ollama server URL |

### Output: Verdict

```python
@dataclass
class Verdict:
    verdict: str           # "supports", "contradicts", "undecided"
    rationale: str         # 2-3 sentence explanation
    confidence: str        # "high", "medium", "low"
    counter_report: CounterReport
    analysis_metadata: Dict[str, Any]
```

### Verdict Classification

| Verdict | Meaning | Typical Evidence |
|---------|---------|------------------|
| `supports` | Counter-evidence supports original claim | Search failed to find contradictory evidence |
| `contradicts` | Counter-evidence contradicts original claim | Multiple studies support counter-position |
| `undecided` | Evidence is mixed or insufficient | Conflicting studies or limited data |

### Confidence Levels

| Level | Criteria |
|-------|----------|
| `high` | Multiple high-quality studies, consistent findings |
| `medium` | Moderate evidence, some limitations |
| `low` | Limited evidence, conflicting results, weak studies |

### Usage Example

```python
from bmlibrarian.paperchecker.components import VerdictAnalyzer

analyzer = VerdictAnalyzer(model="gpt-oss:20b")

# Analyze individual statement
verdict = analyzer.analyze(statement, counter_report)
print(f"Verdict: {verdict.verdict} ({verdict.confidence} confidence)")
print(f"Rationale: {verdict.rationale}")

# Generate overall assessment
overall = analyzer.generate_overall_assessment(statements, verdicts)
print(f"Overall: {overall}")
```

---

## Integration with PaperCheckerAgent

The `PaperCheckerAgent` orchestrates all components:

```python
class PaperCheckerAgent:
    def __init__(self, ...):
        # Initialize components
        self.statement_extractor = StatementExtractor(...)
        self.counter_generator = CounterStatementGenerator(...)
        self.hyde_generator = HyDEGenerator(...)
        self.search_coordinator = SearchCoordinator(...)
        self.verdict_analyzer = VerdictAnalyzer(...)

        # Reuse BMLibrarian agents
        self.scoring_agent = DocumentScoringAgent(...)
        self.citation_agent = CitationFinderAgent(...)

    def check_abstract(self, abstract: str, ...) -> PaperCheckResult:
        # Step 1: Extract statements
        statements = self._extract_statements(abstract)

        # Step 2: Generate counter-statements
        counter_statements = self._generate_counter_statements(statements)

        # For each statement...
        for stmt, counter_stmt in zip(statements, counter_statements):
            # Step 3: Search
            search_results = self._search_counter_evidence(counter_stmt)

            # Step 4: Score
            scored_docs = self._score_documents(counter_stmt, search_results)

            # Step 5: Extract citations
            citations = self._extract_citations(counter_stmt, scored_docs)

            # Step 6: Generate report
            counter_report = self._generate_counter_report(...)

            # Step 7: Analyze verdict
            verdict = self._analyze_verdict(stmt, counter_report)

        # Step 8: Overall assessment
        overall = self._generate_overall_assessment(statements, verdicts)

        return PaperCheckResult(...)
```

## Testing

Each component has dedicated unit tests:

```bash
# Run component tests
uv run pytest tests/paperchecker/test_statement_extractor.py -v
uv run pytest tests/paperchecker/test_counter_generator.py -v
uv run pytest tests/paperchecker/test_hyde_generator.py -v
uv run pytest tests/paperchecker/test_search_coordinator.py -v
uv run pytest tests/paperchecker/test_verdict_analyzer.py -v

# Run all PaperChecker tests
uv run pytest tests/paperchecker/ -v
```

## See Also

- [Architecture Documentation](paper_checker_architecture.md) - System design
- [Database Schema](paper_checker_database.md) - Database structure
- [API Reference](paper_checker_api_reference.md) - Complete API docs
- [User Guide](../users/paper_checker_guide.md) - End-user documentation
