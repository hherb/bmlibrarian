# Fact-Checker System: Complete Overview

## Table of Contents

1. [Introduction](#introduction)
2. [What is the Fact-Checker?](#what-is-the-fact-checker)
3. [Use Cases](#use-cases)
4. [System Architecture](#system-architecture)
5. [How It Works](#how-it-works)
6. [Getting Started](#getting-started)
7. [Workflow Walkthrough](#workflow-walkthrough)
8. [Advanced Features](#advanced-features)
9. [Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)
11. [Related Documentation](#related-documentation)

## Introduction

The BMLibrarian Fact-Checker is an AI-powered system for automated verification of biomedical statements against published literature evidence. It was designed to address the critical need for validating medical claims in Large Language Model (LLM) training datasets, ensuring factual accuracy and reducing the risk of medical misinformation.

### Why Fact-Checking Matters

Medical misinformation in training data can lead to:
- **Dangerous Hallucinations**: LLMs generating medically incorrect advice
- **Dataset Contamination**: Inaccurate statements propagating through training pipelines
- **Research Quality Issues**: Compromised systematic reviews and meta-analyses
- **Patient Safety Risks**: Healthcare AI systems providing false information

The Fact-Checker helps mitigate these risks by providing:
- Automated verification against literature evidence
- Human review and annotation capabilities
- Inter-rater reliability analysis for quality control
- Comprehensive audit trails for dataset validation

## What is the Fact-Checker?

The Fact-Checker is a **multi-agent orchestration system** that:

1. **Analyzes Biomedical Statements**: Processes natural language medical claims
2. **Searches Literature**: Queries the PostgreSQL literature database for relevant evidence
3. **Evaluates Truthfulness**: Uses AI to determine if statements are:
   - **Yes** (supported by evidence)
   - **No** (contradicted by evidence)
   - **Maybe** (insufficient or conflicting evidence)
4. **Extracts Evidence**: Provides specific citations supporting the evaluation
5. **Supports Human Review**: Enables multi-user annotation and comparison

### Key Features

- ✅ **Automated Verification**: Batch process thousands of statements
- 📚 **Evidence-Based**: Cites specific literature passages
- 🤖 **Multi-Agent Orchestration**: Coordinates QueryAgent, ScoringAgent, CitationAgent
- 💾 **PostgreSQL Storage**: Persistent storage with multi-user support
- 👥 **Human Annotation**: Review and compare AI evaluations with human judgments
- 📊 **Inter-Rater Reliability**: Statistical analysis of annotator agreement
- 🔄 **Incremental Processing**: Resume interrupted workflows
- 📤 **JSON Import/Export**: Flexible data exchange formats

## Use Cases

### 1. LLM Training Data Auditing

**Problem**: Medical training datasets may contain false statements that become embedded in model weights.

**Solution**: Use the fact-checker to verify every medical claim in your training corpus:

```bash
# Audit training data statements
uv run python fact_checker_cli.py training_statements.json

# Review results in Qt GUI
uv run python bmlibrarian_qt.py
# → Go to "Fact Checker" tab
```

**Outcome**: Identify and remove inaccurate statements before training, improving model reliability.

### 2. Systematic Review Validation

**Problem**: Systematic reviews require verification of multiple medical claims across literature.

**Solution**: Extract key claims from reviews and verify against your literature database:

```json
[
  {
    "statement": "Meta-analysis shows statins reduce cardiovascular mortality by 15%",
    "answer": "yes"
  },
  {
    "statement": "Aspirin prevents primary cardiovascular events in all populations",
    "answer": "maybe"
  }
]
```

**Outcome**: Rapid evidence-based validation of systematic review conclusions.

### 3. Medical Knowledge Base Quality Control

**Problem**: Knowledge bases accumulate outdated or incorrect information over time.

**Solution**: Periodically fact-check knowledge base entries:

```bash
# Check knowledge base entries
uv run python fact_checker_cli.py kb_statements.json --incremental

# Generate statistics
uv run python fact_checker_stats.py
```

**Outcome**: Maintain high-quality, evidence-based medical knowledge bases.

### 4. Inter-Rater Reliability Studies

**Problem**: Need to measure agreement between AI evaluations and human expert annotators.

**Solution**: Use the fact-checker's multi-user annotation system:

1. **Generate AI evaluations** (automated)
2. **Distribute to human reviewers** (Qt GUI or standalone review app)
3. **Import annotations** (from multiple reviewers)
4. **Analyze agreement** (Cohen's kappa, concordance rates)

**Outcome**: Quantitative assessment of AI fact-checking reliability.

### 5. Temporal Validity Studies

**Problem**: Medical knowledge evolves; statements true in 2010 may be false today.

**Solution**: Re-check historical statements against current literature:

```bash
# Check 2015 statements against 2024 literature
uv run python fact_checker_cli.py statements_2015.json -o results_2024.json

# Compare with original evaluations
uv run python fact_checker_stats.py
```

**Outcome**: Track how medical consensus changes over time.

## System Architecture

### Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    BMLibrarian Fact-Checker                     │
└─────────────────────────────────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌─────────────┐      ┌──────────────┐    ┌──────────────┐
│   CLI Tool  │      │   Qt GUI Tab │    │  Review GUI  │
│  (Batch)    │      │ (Integrated) │    │ (Standalone) │
└─────────────┘      └──────────────┘    └──────────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                             ▼
                ┌────────────────────────┐
                │  FactCheckerAgent      │
                │  (Multi-Agent Orch.)   │
                └────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ QueryAgent   │    │ ScoringAgent │    │ CitationAgent│
│ (DB Search)  │    │ (Relevance)  │    │ (Evidence)   │
└──────────────┘    └──────────────┘    └──────────────┘
                             │
                             ▼
                ┌────────────────────────┐
                │  PostgreSQL Database   │
                │  (factcheck schema)    │
                └────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  statements  │    │ai_evaluations│    │   evidence   │
│ (biomedical  │    │ (AI verdicts)│    │ (citations)  │
│  claims)     │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
                             │
        ┌────────────────────┴────────────────────┐
        │                                         │
        ▼                                         ▼
┌──────────────────┐                    ┌──────────────────┐
│ human_annotations│                    │   annotators     │
│ (reviewer notes) │                    │ (user profiles)  │
└──────────────────┘                    └──────────────────┘
```

### Database Schema

The fact-checker uses a dedicated PostgreSQL schema (`factcheck`) with:

**Core Tables**:
- `statements`: Biomedical statements to verify
- `ai_evaluations`: AI-generated fact-check results
- `evidence`: Literature citations (foreign keys to `public.document`)
- `human_annotations`: Human reviewer annotations
- `annotators`: User profiles for multi-reviewer studies

**Key Design Decisions**:
- **No data duplication**: Evidence references `public.document` via foreign keys
- **Multi-user support**: Multiple annotations per statement per user
- **Audit trail**: Timestamps and user tracking for all operations
- **Incremental processing**: Track which statements have been evaluated

## How It Works

### Phase 1: Statement Input

Input statements as JSON:

```json
[
  {
    "statement": "Vitamin D supplementation reduces COVID-19 severity",
    "answer": "yes"  // Optional: expected answer for validation
  },
  {
    "statement": "All statins have identical efficacy",
    "answer": "no"
  }
]
```

**Fields**:
- `statement` (required): The biomedical claim to verify
- `answer` (optional): Expected answer for validation studies

### Phase 2: Multi-Agent Processing

**Step 1: Query Generation (QueryAgent)**
- Converts statement to PostgreSQL query
- Searches `pubmed_articles` and `medrxiv_articles`
- Returns ranked list of potentially relevant documents

**Step 2: Relevance Scoring (ScoringAgent)**
- Scores each document for relevance (1-5 scale)
- Filters documents below threshold (default: 2.5)
- Focuses on high-relevance literature

**Step 3: Evidence Extraction (CitationAgent)**
- Extracts specific passages from relevant documents
- Identifies supporting or contradicting evidence
- Links evidence to specific documents (preserves provenance)

**Step 4: Evaluation Synthesis (FactCheckerAgent)**
- Analyzes all evidence
- Generates verdict: **Yes**, **No**, or **Maybe**
- Provides reasoning and confidence level
- Assigns confidence: **High**, **Medium**, **Low**

### Phase 3: Storage

Results stored in PostgreSQL:

```sql
-- Statement
INSERT INTO factcheck.statements (statement_text, expected_answer)
VALUES ('Vitamin D reduces COVID-19 severity', 'yes');

-- AI Evaluation
INSERT INTO factcheck.ai_evaluations (
  statement_id, evaluation, reasoning, confidence
)
VALUES (1, 'yes', 'Multiple RCTs show...', 'high');

-- Evidence (references public.document)
INSERT INTO factcheck.evidence (
  statement_id, document_id, passage_text, relevance_score
)
VALUES (1, 12345, 'RCT results: vitamin D...', 4.2);
```

### Phase 4: Human Review (Optional)

Humans can review AI evaluations via Qt GUI or standalone review app:

```sql
-- Human Annotation
INSERT INTO factcheck.human_annotations (
  statement_id, annotator_id, annotation, explanation
)
VALUES (1, 'reviewer1', 'yes', 'Agree with AI, evidence is strong');
```

### Phase 5: Analysis

Statistical analysis of results:

```bash
# Generate comprehensive statistics
uv run python fact_checker_stats.py --export-csv stats_output/ --plot

# Query inter-annotator agreement
psql -d knowledgebase -c "SELECT * FROM factcheck.calculate_inter_annotator_agreement();"
```

**Metrics Calculated**:
- Concordance rates (AI vs Expected, AI vs Human, Human vs Human)
- Cohen's kappa (inter-rater reliability)
- Confusion matrices (accuracy, precision, recall, F1)
- Confidence calibration (how well confidence predicts accuracy)
- Category transitions (Yes→No, No→Yes, stability)

## Getting Started

### Prerequisites

- BMLibrarian installed and configured
- PostgreSQL with literature database populated
- Ollama running with required models

### Quick Start: 5-Minute Fact-Check

**1. Create test file** (`test_statements.json`):
```json
[
  {
    "statement": "Aspirin reduces risk of heart attack",
    "answer": "yes"
  },
  {
    "statement": "Antibiotics cure viral infections",
    "answer": "no"
  },
  {
    "statement": "Vitamin C prevents common cold",
    "answer": "maybe"
  }
]
```

**2. Run fact-checker**:
```bash
uv run python fact_checker_cli.py test_statements.json
```

**3. View results**:
```bash
# In database
psql -d knowledgebase -c "SELECT * FROM factcheck.v_statement_evaluations LIMIT 5;"

# Or export to JSON
uv run python fact_checker_cli.py test_statements.json -o results.json
cat results.json
```

**4. Review in GUI**:
```bash
uv run python bmlibrarian_qt.py
# Click "Fact Checker" tab
```

### Full Workflow Example

**Scenario**: Audit 1000 medical statements from LLM training data.

**Step 1: Prepare input**:
```bash
# Convert training data to fact-checker format
python convert_training_data.py dataset.jsonl statements.json
```

**Step 2: Batch fact-check** (may take hours for large datasets):
```bash
# Run with progress tracking
uv run python fact_checker_cli.py statements.json 2>&1 | tee factcheck.log
```

**Step 3: Review results**:
```bash
# Generate statistics
uv run python fact_checker_stats.py --export-csv stats_output/

# Review in Qt GUI for spot-checking
uv run python bmlibrarian_qt.py
```

**Step 4: Human annotation** (optional):
```bash
# Annotate in Qt GUI
# Or use standalone review app for blind annotation
uv run python fact_checker_review_gui.py --user reviewer1 --blind
```

**Step 5: Analyze quality**:
```bash
# Calculate inter-rater agreement
uv run python fact_checker_stats.py
# Review concordance rates and kappa values
```

**Step 6: Filter dataset**:
```sql
-- Export statements where AI and expected answer agree
COPY (
  SELECT statement_text
  FROM factcheck.v_statement_evaluations
  WHERE ai_evaluation = expected_answer
) TO '/path/to/verified_statements.csv' CSV HEADER;
```

## Advanced Features

### Incremental Processing

Resume interrupted fact-checking:

```bash
# Initial run (interrupted after 500/1000 statements)
uv run python fact_checker_cli.py statements.json

# Resume (skips already-evaluated statements)
uv run python fact_checker_cli.py statements.json --incremental
```

**How it works**:
- Checks for existing AI evaluations in database
- Skips statements that already have evaluations
- Only processes new or unevaluated statements

### Custom Configuration

Override default settings:

```bash
# Use specific model
uv run python fact_checker_cli.py statements.json --model "medgemma-27b-text-it-Q8_0:latest"

# Adjust scoring threshold
uv run python fact_checker_cli.py statements.json --score-threshold 3.0

# Increase max documents searched
uv run python fact_checker_cli.py statements.json --max-documents 100

# Adjust temperature for more deterministic results
uv run python fact_checker_cli.py statements.json --temperature 0.1
```

### Multi-User Annotation Workflow

For inter-rater reliability studies:

**1. Generate AI evaluations**:
```bash
uv run python fact_checker_cli.py statements.json
```

**2. Distribute to reviewers**:
```bash
# Reviewer 1
uv run python fact_checker_review_gui.py --user reviewer1 --blind

# Reviewer 2
uv run python fact_checker_review_gui.py --user reviewer2 --blind

# Reviewer 3
uv run python fact_checker_review_gui.py --user reviewer3 --blind
```

**Blind Mode**:
- Hides AI evaluations from human reviewers
- Prevents anchoring bias
- Shows only statements and evidence

**3. Analyze agreement**:
```bash
uv run python fact_checker_stats.py

# Or query database directly
psql -d knowledgebase -c "
  SELECT
    annotator1, annotator2,
    agreement_rate, cohens_kappa, interpretation
  FROM factcheck.v_inter_annotator_agreement;
"
```

### Confidence Calibration Analysis

Assess whether AI confidence levels are well-calibrated:

```bash
# Generate confidence calibration report
uv run python fact_checker_stats.py --plot

# Review confidence_calibration.png
# - High confidence should → high accuracy
# - Low confidence should → low accuracy
```

**Interpretation**:
- **Well-calibrated**: Confidence predicts accuracy
- **Overconfident**: High confidence but low accuracy
- **Underconfident**: Low confidence but high accuracy

### Temporal Validity Studies

Track how medical consensus changes over time:

**Setup**:
```sql
-- Add year restriction to search
ALTER TABLE factcheck.ai_evaluations
  ADD COLUMN max_publication_year INTEGER;
```

**Workflow**:
```bash
# Check statements against 2020 literature
uv run python fact_checker_cli.py statements.json --max-year 2020

# Check same statements against 2024 literature
uv run python fact_checker_cli.py statements.json --max-year 2024

# Compare evaluations
python compare_temporal_validity.py results_2020.json results_2024.json
```

**Analysis**:
- Identify statements with changed evaluations (Yes→No, No→Yes)
- Track evolving medical evidence
- Detect paradigm shifts in clinical practice

## Best Practices

### Input Statement Design

**✅ Good Statements**:
- Specific and testable
- Focused on single claim
- Uses medical terminology appropriately

```json
{
  "statement": "Metformin reduces cardiovascular mortality in type 2 diabetes patients by approximately 30%"
}
```

**❌ Avoid**:
- Vague statements
- Multiple claims in one statement
- Subjective opinions

```json
{
  "statement": "Diabetes is bad and people should eat healthier"
}
```

### Batch Size Recommendations

| Batch Size | Use Case | Processing Time |
|------------|----------|-----------------|
| 1-10 | Testing, quick checks | Seconds-minutes |
| 10-100 | Small datasets, research | Minutes-hours |
| 100-1000 | Medium datasets | Hours-day |
| 1000+ | Large audits | Days-weeks |

**Tips**:
- Use incremental mode for large batches
- Monitor Ollama resource usage
- Split very large datasets into chunks

### Model Selection

| Model | Use Case | Speed | Accuracy |
|-------|----------|-------|----------|
| `gpt-oss:20b` | Default, balanced | Medium | High |
| `medgemma-27b-text-it-Q8_0:latest` | High accuracy | Slow | Highest |
| `medgemma4B_it_q8:latest` | Fast processing | Fast | Good |

**Recommendation**: Start with `gpt-oss:20b`, upgrade to 27B model for final production audits.

### Human Annotation Guidelines

**For Reviewers**:
1. **Read statement carefully**: Understand exactly what is claimed
2. **Review ALL evidence**: Don't rely on first citation alone
3. **Consider publication quality**: RCTs > observational studies > case reports
4. **Check for conflicts**: Note if evidence contradicts itself
5. **Explain reasoning**: Write clear explanation for your annotation
6. **Use "Maybe" appropriately**: When evidence is truly ambiguous

**For Study Coordinators**:
1. **Train annotators**: Provide clear guidelines and examples
2. **Use blind mode**: Prevent AI anchoring bias
3. **Measure agreement**: Calculate Cohen's kappa for quality control
4. **Adjudicate conflicts**: Resolve disagreements between reviewers
5. **Track time**: Monitor annotation time per statement (for workload estimation)

## Troubleshooting

### No Relevant Documents Found

**Symptom**: Fact-checker returns "maybe" for all statements with "no relevant literature found".

**Causes**:
1. Literature database not populated
2. Query generation issues
3. Search filters too restrictive

**Solutions**:
```bash
# Check database has documents
psql -d knowledgebase -c "SELECT COUNT(*) FROM pubmed_articles;"
psql -d knowledgebase -c "SELECT COUNT(*) FROM medrxiv_articles;"

# If empty, import literature
uv run python pubmed_import_cli.py search "your topic" --max-results 1000
uv run python medrxiv_import_cli.py update

# Lower score threshold
uv run python fact_checker_cli.py statements.json --score-threshold 2.0

# Increase max documents
uv run python fact_checker_cli.py statements.json --max-documents 100
```

### Low Concordance with Expected Answers

**Symptom**: AI evaluations frequently disagree with expected answers.

**Causes**:
1. Outdated expected answers
2. Literature database incomplete
3. Model selection issues
4. Expected answers incorrect

**Solutions**:
```bash
# Review specific disagreements
psql -d knowledgebase -c "
  SELECT
    statement_text, expected_answer, ai_evaluation, ai_reasoning
  FROM factcheck.v_statement_evaluations
  WHERE expected_answer != ai_evaluation
  LIMIT 10;
"

# Try different model
uv run python fact_checker_cli.py statements.json --model "medgemma-27b-text-it-Q8_0:latest"

# Review evidence quality manually in Qt GUI
uv run python bmlibrarian_qt.py
```

### Slow Processing

**Symptom**: Fact-checking takes very long time.

**Causes**:
1. Large batch size
2. Slow model
3. Database query performance
4. Ollama configuration

**Solutions**:
```bash
# Use faster model
uv run python fact_checker_cli.py statements.json --model "medgemma4B_it_q8:latest"

# Reduce max documents per statement
uv run python fact_checker_cli.py statements.json --max-documents 20

# Process in batches with incremental mode
split -l 100 statements.json batch_
for file in batch_*; do
  uv run python fact_checker_cli.py "$file" --incremental
done

# Enable GPU acceleration in Ollama (if available)
# See Ollama documentation for GPU setup
```

### Database Connection Errors

**Symptom**: "psycopg.OperationalError: connection refused"

**Solutions**:
```bash
# Check PostgreSQL running
sudo systemctl status postgresql  # Linux
brew services list                # macOS

# Verify connection parameters in .env
cat .env | grep POSTGRES

# Test connection manually
psql -h localhost -U your_user -d knowledgebase

# Check factcheck schema exists
psql -d knowledgebase -c "\\dn factcheck"

# If missing, run database setup
uv run python initial_setup_and_download.py test.env
```

## Related Documentation

### User Guides
- **[Fact Checker CLI Guide](fact_checker_guide.md)**: Detailed CLI usage and options
- **[Fact Checker Review GUI Guide](fact_checker_review_guide.md)**: Human annotation interface
- **[Qt GUI User Guide](qt_gui_user_guide.md)**: Using the Fact Checker tab in Qt GUI

### Developer Documentation
- **[Fact Checker System Architecture](../developers/fact_checker_system.md)**: Technical implementation details
- **[API Reference](../developers/api_reference.md)**: FactCheckerAgent API documentation
- **[Contributing Guide](../developers/contributing.md)**: Contributing to fact-checker development

### Related Tools
- **[Citation Guide](citation_guide.md)**: Understanding citation extraction
- **[Query Agent Guide](query_agent_guide.md)**: How natural language queries work
- **[Agents Guide](agents_guide.md)**: Multi-agent orchestration overview

---

**The BMLibrarian Fact-Checker provides a robust, evidence-based solution for validating biomedical statements at scale, ensuring the integrity and reliability of medical AI training datasets and knowledge bases.**

For questions or issues, please refer to the [Troubleshooting Guide](troubleshooting.md) or check the developer documentation.
