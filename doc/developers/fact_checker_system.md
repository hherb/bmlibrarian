# Fact Checker System - Developer Documentation

## Overview

The Fact Checker system provides automated verification of biomedical statements against literature evidence. It's designed for auditing LLM training data, validating medical claims, and ensuring factual accuracy in biomedical corpora.

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    FactCheckerAgent                         │
│  (Orchestrates fact-checking workflow)                      │
└────────────┬────────────────────────────────────────────────┘
             │
             ├─► QueryAgent
             │   (Search for relevant documents)
             │
             ├─► DocumentScoringAgent
             │   (Score document relevance)
             │
             ├─► CitationFinderAgent
             │   (Extract supporting/contradicting evidence)
             │
             └─► LLM Evaluation
                 (Synthesize evaluation with reasoning)
```

### Data Flow

1. **Input**: Biomedical statement + optional expected answer
2. **Search**: Convert statement to query, search literature
3. **Scoring**: Evaluate document relevance to statement
4. **Extraction**: Extract relevant passages as citations
5. **Evaluation**: Analyze evidence and determine yes/no/maybe
6. **Output**: Structured result with evidence references

## Core Classes

### FactCheckerAgent

Main orchestration agent that coordinates the fact-checking workflow.

**Location**: `src/bmlibrarian/agents/fact_checker_agent.py`

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
def check_batch(
    self,
    statements: List[Dict[str, str]],
    output_file: Optional[str] = None
) -> List[FactCheckResult]:
    """
    Check multiple statements in batch.

    Args:
        statements: List of statement dicts with 'statement' and 'answer' keys
        output_file: Optional JSON output file

    Returns:
        List of FactCheckResult objects
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
    show_model_info=True                # Display model info
)
```

### FactCheckResult

Dataclass representing the fact-check evaluation result.

**Location**: `src/bmlibrarian/agents/fact_checker_agent.py`

**Fields**:

```python
@dataclass
class FactCheckResult:
    statement: str                      # Original statement
    evaluation: str                     # "yes", "no", or "maybe"
    reason: str                         # Explanation (1-3 sentences)
    evidence_list: List[EvidenceReference]  # Supporting evidence
    confidence: str                     # "high", "medium", or "low"
    documents_reviewed: int             # Total documents analyzed
    supporting_citations: int           # Count of supporting evidence
    contradicting_citations: int        # Count of contradicting evidence
    neutral_citations: int              # Count of neutral evidence
    expected_answer: Optional[str]      # Expected answer (if provided)
    matches_expected: Optional[bool]    # Match with expected answer
    timestamp: str                      # ISO 8601 timestamp
```

**Methods**:

```python
def to_dict(self) -> Dict[str, Any]:
    """Convert to dictionary for JSON serialization."""
```

### EvidenceReference

Dataclass representing a literature reference supporting the evaluation.

**Location**: `src/bmlibrarian/agents/fact_checker_agent.py`

**Fields**:

```python
@dataclass
class EvidenceReference:
    citation_text: str                  # Extracted passage
    pmid: Optional[str]                 # PubMed ID
    doi: Optional[str]                  # DOI
    document_id: Optional[str]          # Database document ID
    relevance_score: Optional[float]    # Document relevance (1-5)
    supports_statement: Optional[bool]  # True=supports, False=contradicts
```

**Methods**:

```python
def to_dict(self) -> Dict[str, Any]:
    """Convert to dictionary for JSON serialization."""
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

### Statement to Question Conversion

The agent converts statements to questions for better search results:

```python
def _statement_to_question(statement: str) -> str:
    """Convert statement to question format."""
    # Already a question?
    if statement.endswith('?'):
        return statement

    # Yes/no statement?
    if contains_yes_no_indicators(statement):
        if starts_with_quantifier(statement):
            return f"Is it true that {statement}?"
        else:
            return f"{statement}?"

    # General topic
    return f"What does the literature say about: {statement}"
```

### Evidence Evaluation

The LLM analyzes citations to determine their stance:

```python
def _evaluate_statement(statement, citations, scored_docs, expected_answer):
    # 1. Prepare evidence summary
    evidence_summary = _prepare_evidence_summary(citations)

    # 2. Create evaluation prompt
    prompt = _create_evaluation_prompt(statement, evidence_summary)

    # 3. Get LLM evaluation
    response = _make_ollama_request(messages=[{'role': 'user', 'content': prompt}])

    # 4. Parse response
    evaluation_data = _parse_evaluation_response(response)
    # Returns: {
    #     "evaluation": "yes|no|maybe",
    #     "reason": "explanation",
    #     "citation_stances": {"1": "supports", "2": "contradicts", ...}
    # }

    # 5. Convert citations to evidence references
    evidence_refs = _citations_to_evidence_refs(citations, scored_docs, stances)

    # 6. Determine confidence
    confidence = _determine_confidence(evaluation, supporting, contradicting, neutral, total_docs)

    # 7. Create result
    return FactCheckResult(...)
```

### Confidence Determination

Confidence is based on evidence quantity and consistency:

```python
def _determine_confidence(evaluation, supporting, contradicting, neutral, total_docs):
    total_citations = supporting + contradicting + neutral

    # Low confidence: insufficient evidence
    if total_citations == 0 or total_docs < 3:
        return "low"

    # High confidence: clear majority with multiple sources
    if evaluation in ['yes', 'no']:
        dominant = supporting if evaluation == 'yes' else contradicting
        ratio = dominant / total_citations

        if dominant >= 3 and ratio >= 0.7 and total_docs >= 5:
            return "high"
        elif dominant >= 2 and ratio >= 0.6:
            return "medium"

    # Maybe: mixed evidence
    if evaluation == 'maybe':
        if total_citations >= 4 and total_docs >= 5:
            return "medium"

    return "low"
```

## Sub-Agent Integration

### QueryAgent Integration

Converts statements to database queries:

```python
def _search_documents(statement, max_results):
    # Convert statement to question
    search_question = _statement_to_question(statement)

    # Use QueryAgent to search
    documents = query_agent.search_documents(
        user_question=search_question,
        max_results=max_results
    )

    return documents
```

### DocumentScoringAgent Integration

Scores document relevance:

```python
def _score_documents(statement, documents, threshold):
    scored_docs = []

    for doc in documents:
        score = scoring_agent.evaluate_document(
            user_question=statement,
            document=doc
        )

        if score and score >= threshold:
            scored_docs.append((doc, score))

    # Sort by score descending
    scored_docs.sort(key=lambda x: x[1], reverse=True)

    return scored_docs
```

### CitationFinderAgent Integration

Extracts relevant passages:

```python
def _extract_citations(statement, scored_documents):
    # Limit to top documents
    top_docs = scored_documents[:max_citations]

    # Extract citations
    citations = citation_agent.process_scored_documents_for_citations(
        user_question=statement,
        scored_documents=top_docs,
        score_threshold=score_threshold
    )

    return citations
```

## CLI Tool

### fact_checker_cli.py

Command-line interface for batch processing.

**Location**: `fact_checker_cli.py`

**Key Functions**:

```python
def load_input_file(file_path: str) -> List[Dict[str, str]]:
    """Load statements from JSON file."""

def create_agent(args: argparse.Namespace) -> FactCheckerAgent:
    """Create and configure agent from CLI args."""

def save_output_file(results: List[FactCheckResult], output_path: str):
    """Save results to JSON file."""

def print_result_summary(results: List[FactCheckResult]):
    """Print summary statistics to console."""
```

**Usage**:

```bash
python fact_checker_cli.py input.json -o output.json [OPTIONS]
```

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
- Error handling

**Running Tests**:

```bash
# Run fact checker tests only
uv run python -m pytest tests/test_fact_checker_agent.py -v

# Run all agent tests
uv run python -m pytest tests/test_*_agent.py -v

# Run with coverage
uv run python -m pytest tests/test_fact_checker_agent.py --cov=bmlibrarian.agents.fact_checker_agent
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
from bmlibrarian.agents import FactCheckerAgent
from bmlibrarian.config import get_model, get_agent_config

# Create agent
model = get_model('fact_checker_agent')
config = get_agent_config('fact_checker')

agent = FactCheckerAgent(
    model=model,
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

# Check batch
statements = [
    {"statement": "Statement 1", "answer": "yes"},
    {"statement": "Statement 2", "answer": "no"}
]

results = agent.check_batch(statements, output_file="results.json")

for result in results:
    print(f"{result.statement}: {result.evaluation}")
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

### Integration with Orchestrator

```python
from bmlibrarian.agents import AgentOrchestrator

# Create orchestrator
orchestrator = AgentOrchestrator(max_workers=4)

# Create agent with orchestrator
agent = FactCheckerAgent(
    model=model,
    orchestrator=orchestrator,
    **config
)

# Sub-agents will use orchestrator for queue-based processing
result = agent.check_statement(statement)
```

## Extension Points

### Custom Evaluation Logic

Override `_evaluate_statement` for custom evaluation logic:

```python
class CustomFactCheckerAgent(FactCheckerAgent):
    def _evaluate_statement(self, statement, citations, scored_docs, expected_answer):
        # Custom evaluation logic
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

### Custom Statement Preprocessing

Override `_statement_to_question` for specialized conversion:

```python
class SpecializedFactCheckerAgent(FactCheckerAgent):
    def _statement_to_question(self, statement):
        # Domain-specific statement processing
        # Add medical terminology normalization
        # Handle specialty-specific phrasing
        # ...
        return processed_question
```

## Performance Optimization

### Batch Processing

For large datasets, use batch processing with progress tracking:

```python
# Process in chunks
chunk_size = 100
for i in range(0, len(all_statements), chunk_size):
    chunk = all_statements[i:i+chunk_size]
    results = agent.check_batch(chunk, output_file=f"results_chunk_{i}.json")
    print(f"Processed {i+chunk_size}/{len(all_statements)} statements")
```

### Parallel Processing

For independent statements, use multiprocessing:

```python
from multiprocessing import Pool
from functools import partial

def check_statement_wrapper(statement_dict, agent_config):
    agent = FactCheckerAgent(**agent_config)
    return agent.check_statement(
        statement=statement_dict['statement'],
        expected_answer=statement_dict.get('answer')
    )

# Create process pool
with Pool(processes=4) as pool:
    check_func = partial(check_statement_wrapper, agent_config=config)
    results = pool.map(check_func, statements)
```

### Caching Results

Cache intermediate results for repeated queries:

```python
from functools import lru_cache

class CachedFactCheckerAgent(FactCheckerAgent):
    @lru_cache(maxsize=1000)
    def _search_documents(self, statement, max_results):
        return super()._search_documents(statement, max_results)
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
- Enable result caching

**Issue**: Low accuracy vs expected answers

**Solution**:
- Review mismatched results
- Adjust score threshold
- Verify expected answers are correct
- Check evidence quality

### Debug Mode

Enable verbose logging for debugging:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('bmlibrarian.agents')
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
5. **External Database Integration**: Connect to PubMed, clinical trials databases
6. **Citation Quality Scoring**: Assess publication quality, impact factors
7. **Claim Decomposition**: Break complex statements into sub-claims
8. **Interactive Refinement**: Allow human feedback to improve evaluations

### API Considerations

For future API integration:

```python
# RESTful API endpoint example
@app.post("/api/fact-check")
def fact_check_endpoint(statement: str, expected_answer: Optional[str] = None):
    result = agent.check_statement(statement, expected_answer)
    return result.to_dict()

@app.post("/api/fact-check/batch")
def fact_check_batch_endpoint(statements: List[Dict[str, str]]):
    results = agent.check_batch(statements)
    return {
        "results": [r.to_dict() for r in results],
        "summary": agent._generate_summary(results)
    }
```

## Related Documentation

- [User Guide](../users/fact_checker_guide.md)
- [Citation System](citation_system.md)
- [Query Agent](../users/query_agent_guide.md)
- [Agent Module Overview](agent_module.md)
- [Multi-Agent Architecture](agent_module.md)

## Support

For technical questions or contributions:
- GitHub Issues: https://github.com/hherb/bmlibrarian/issues
- Developer Docs: `doc/developers/`
- Test Examples: `tests/test_fact_checker_agent.py`
