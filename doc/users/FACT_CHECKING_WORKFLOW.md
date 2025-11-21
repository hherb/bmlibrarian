# Fact-Checking Workflow Guide

This guide explains how to use BMLibrarian's FactCheckerAgent to verify biomedical statements against literature evidence, with support for batch processing from structured JSON files.

## Overview

The fact-checking workflow consists of three main steps:

1. **Extract** question/answer pairs from structured JSON files
2. **Process** statements through FactCheckerAgent to verify against literature
3. **Analyze** results comparing agent evaluations with expected answers

## File Formats

### Input Format (Original Structured JSON)

The original dataset format with nested structure:

```json
{
  "21645374": {
    "QUESTION": "Do mitochondria play a role in remodelling lace plant leaves during programmed cell death?",
    "CONTEXTS": [...],
    "LABELS": [...],
    "MESHES": [...],
    "YEAR": "2011",
    "reasoning_required_pred": "yes",
    "reasoning_free_pred": "yes",
    "final_decision": "yes",
    "LONG_ANSWER": "..."
  },
  "16418930": {
    "QUESTION": "Landolt C and snellen e acuity: differences in strabismus amblyopia?",
    ...
    "final_decision": "no",
    ...
  }
}
```

### Extracted Format (Simplified JSON)

After extraction with `extract_qa.py`:

```json
[
  {
    "id": "21645374",
    "question": "Do mitochondria play a role in remodelling lace plant leaves during programmed cell death?",
    "answer": "yes"
  },
  {
    "id": "16418930",
    "question": "Landolt C and snellen e acuity: differences in strabismus amblyopia?",
    "answer": "no"
  }
]
```

### Output Format (Fact-Check Results)

After processing with `FactCheckerAgent`:

```json
{
  "results": [
    {
      "input_statement_id": "21645374",
      "statement": "Do mitochondria play a role in remodelling lace plant leaves during programmed cell death?",
      "evaluation": "yes",
      "reason": "Multiple studies demonstrate that mitochondria undergo dynamic changes during PCD...",
      "confidence": "high",
      "expected_answer": "yes",
      "matches_expected": true,
      "evidence_list": [
        {
          "citation": "Results depicted mitochondrial dynamics in vivo as PCD progresses...",
          "pmid": "PMID:21645374",
          "relevance_score": 4.5,
          "stance": "supports"
        }
      ],
      "metadata": {
        "documents_reviewed": 12,
        "supporting_citations": 5,
        "contradicting_citations": 0,
        "neutral_citations": 2,
        "timestamp": "2025-11-10T12:34:56.789Z"
      }
    }
  ],
  "summary": {
    "total_statements": 100,
    "evaluations": {
      "yes": 45,
      "no": 32,
      "maybe": 20,
      "error": 3
    },
    "confidences": {
      "high": 28,
      "medium": 52,
      "low": 17
    },
    "validation": {
      "matches": 85,
      "mismatches": 12,
      "accuracy": 0.876
    }
  }
}
```

## Step-by-Step Workflow

### Step 1: Extract Questions

Extract ID, question, and answer from the original JSON:

```bash
# Extract all questions
uv run python extract_qa.py ~/Downloads/ori_pqal.json extracted_questions.json

# Verify extraction
cat extracted_questions.json | jq '.[0:3]'
```

**What it does:**
- Reads nested JSON structure
- Extracts `id`, `QUESTION`, and `final_decision` fields
- Outputs simplified array format
- Preserves original IDs for traceability

### Step 2: Run Fact-Checking

Process questions through FactCheckerAgent:

```bash
# Process all questions
uv run python fact_check_workflow_demo.py extracted_questions.json results.json

# Process first 10 questions (for testing)
uv run python fact_check_workflow_demo.py extracted_questions.json results.json 10
```

**What happens during processing:**

For each question, the agent:
1. **Search** - Uses QueryAgent to find relevant literature
2. **Score** - Uses DocumentScoringAgent to rate relevance (1-5 scale)
3. **Extract** - Uses CitationFinderAgent to pull supporting passages
4. **Evaluate** - Synthesizes evidence to determine yes/no/maybe
5. **Compare** - Checks if evaluation matches expected answer

**Progress output:**
```
🔍 Searching literature for: Do mitochondria play a role...
📊 Scoring 15 documents...
📄 Extracting evidence from 8 documents...
🤔 Evaluating statement based on 5 citations...
✅ Fact-check complete: yes
⏳ Processing 2/10: Landolt C and snellen e acuity...
```

### Step 3: Analyze Results

Review results and identify mismatches:

```bash
# Analyze results file
uv run python fact_check_workflow_demo.py --analyze results.json
```

**Analysis output:**
```
ANALYSIS SUMMARY
================================================================
Total statements: 10

Evaluations:
  ✓ Yes: 5
  ✗ No: 3
  ? Maybe: 2

Confidence levels:
  High: 3
  Medium: 5
  Low: 2

Validation (vs expected answers):
  Matches: 8
  Mismatches: 2
  Accuracy: 80.0%

================================================================
MISMATCHES (Expected vs Actual)
================================================================

1. Statement: Is there a role for SPARC in liver fibrosis?...
   Expected: yes
   Actual: maybe
   Confidence: low
   Reason: Limited evidence found. Only 2 documents above threshold...

2. Statement: Does increased Syk phosphorylation lead to overexpression...
   Expected: no
   Actual: yes
   Confidence: medium
   Reason: Multiple studies show correlation between Syk phosphorylation...
```

## Configuration

### Agent Configuration

Edit `~/.bmlibrarian/config.json` to customize FactCheckerAgent behavior:

```json
{
  "fact_checker_agent": {
    "model": "gpt-oss:20b",
    "temperature": 0.1,
    "top_p": 0.9,
    "max_tokens": 2000,
    "score_threshold": 2.5,
    "max_search_results": 50,
    "max_citations": 10
  }
}
```

**Parameters:**
- `score_threshold` - Minimum relevance score (1-5) for documents
- `max_search_results` - Maximum documents to retrieve from database
- `max_citations` - Maximum evidence passages to extract
- `temperature` - Model randomness (lower = more deterministic)

### Sub-Agent Configuration

FactCheckerAgent uses three sub-agents that can be configured independently:

```json
{
  "query_agent": {
    "model": "medgemma4B_it_q8:latest",
    "temperature": 0.2
  },
  "scoring_agent": {
    "model": "gpt-oss:20b",
    "temperature": 0.1
  },
  "citation_agent": {
    "model": "gpt-oss:20b",
    "temperature": 0.3
  }
}
```

## Programmatic Usage

### Python API

```python
from bmlibrarian.agents import FactCheckerAgent
from bmlibrarian.config import get_model, get_agent_config

# Initialize agent
model = get_model("fact_checker_agent", default="gpt-oss:20b")
config = get_agent_config("fact_checker")

agent = FactCheckerAgent(
    model=model,
    temperature=config.get("temperature", 0.1),
    score_threshold=config.get("score_threshold", 2.5)
)

# Single statement
result = agent.check_statement(
    statement="Does aspirin reduce cardiovascular events?",
    expected_answer="yes"
)

print(f"Evaluation: {result.evaluation}")
print(f"Reason: {result.reason}")
print(f"Confidence: {result.confidence}")
print(f"Evidence: {len(result.evidence_list)} citations")

# Batch from file
results = agent.check_batch_from_file(
    input_file="extracted_questions.json",
    output_file="results.json"
)

# Batch from list
statements = [
    {"question": "Is smoking a risk factor for lung cancer?", "answer": "yes"},
    {"question": "Does vitamin C cure the common cold?", "answer": "no"}
]

results = agent.check_batch(statements, output_file="results.json")
```

### Custom Callback

Monitor progress with custom callback:

```python
def my_callback(stage: str, message: str):
    """Custom progress handler."""
    if stage == "complete":
        print(f"✓ {message}")
    elif stage == "warning":
        print(f"⚠ {message}")
    else:
        print(f"[{stage}] {message}")

agent = FactCheckerAgent(
    model="gpt-oss:20b",
    callback=my_callback
)
```

## Understanding Results

### Evaluation Values

- **yes** - Statement is supported by evidence
- **no** - Statement is contradicted by evidence
- **maybe** - Insufficient or mixed evidence
- **error** - Processing error occurred

### Confidence Levels

- **high** - Strong evidence (≥3 citations, ≥70% agreement, ≥5 documents)
- **medium** - Moderate evidence (≥2 citations, ≥60% agreement)
- **low** - Weak evidence (few citations or documents)

### Citation Stances

Each evidence citation is marked as:
- **supports** - Supports the statement
- **contradicts** - Contradicts the statement
- **neutral** - Provides context but doesn't clearly support or contradict

## Troubleshooting

### No Documents Found

**Problem:** Agent returns "maybe" with "No relevant documents found"

**Solutions:**
1. Check database connection
2. Verify question is biomedical in nature
3. Try broader search terms
4. Lower `score_threshold` in configuration

### Low Accuracy

**Problem:** Many mismatches between expected and actual answers

**Solutions:**
1. Increase `max_search_results` to find more literature
2. Lower `score_threshold` to include more documents
3. Increase `max_citations` to gather more evidence
4. Use larger/better model for evaluation
5. Check if expected answers are correct

### Slow Processing

**Problem:** Batch processing takes too long

**Solutions:**
1. Reduce `max_search_results` (try 20-30)
2. Reduce `max_citations` (try 5-8)
3. Use faster model for sub-agents (e.g., medgemma4B)
4. Process smaller batches
5. Use queue-based orchestration for parallelization

### Memory Issues

**Problem:** Out of memory during large batch processing

**Solutions:**
1. Process in smaller batches
2. Enable queue-based processing with orchestrator
3. Reduce `max_search_results`
4. Use smaller models

## Advanced Features

### Queue-Based Processing

For large batches, use orchestrator for memory-efficient processing:

```python
from bmlibrarian.agents import AgentOrchestrator, FactCheckerAgent

orchestrator = AgentOrchestrator(max_workers=4)
agent = FactCheckerAgent(
    model="gpt-oss:20b",
    orchestrator=orchestrator
)

# Queue tasks instead of blocking
results = agent.check_batch_from_file("large_dataset.json")
```

### Custom Thresholds Per Statement

Override defaults for specific statements:

```python
result = agent.check_statement(
    statement="Complex question requiring more evidence...",
    max_documents=100,  # Search more documents
    score_threshold=2.0  # Lower threshold
)
```

### Extract Specific Evidence

Access detailed evidence from results:

```python
for result in results:
    print(f"\nStatement: {result.statement}")
    print(f"Evaluation: {result.evaluation}")

    for evidence in result.evidence_list:
        print(f"\n  Citation: {evidence.citation_text[:100]}...")
        print(f"  PMID: {evidence.pmid}")
        print(f"  Stance: {'Supports' if evidence.supports_statement else 'Contradicts'}")
        print(f"  Relevance: {evidence.relevance_score}/5.0")
```

## Performance Tips

1. **Start small** - Test with 10-20 statements before running large batches
2. **Tune thresholds** - Adjust `score_threshold` based on your accuracy requirements
3. **Model selection** - Faster models for sub-agents, better model for evaluation
4. **Parallel processing** - Use orchestrator for CPU-bound operations
5. **Cache results** - Save intermediate results to avoid re-processing

## Related Documentation

- [FactCheckerAgent Developer Docs](doc/developers/fact_checker_system.md)
- [Multi-Agent Architecture](doc/developers/agent_module.md)
- [Configuration Guide](doc/users/configuration_guide.md)
- [QueryAgent Guide](doc/users/query_agent_guide.md)
- [Citation System](doc/developers/citation_system.md)
