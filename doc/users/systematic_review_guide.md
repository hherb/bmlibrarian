# Systematic Literature Review Agent - User Guide

This guide explains how to use BMLibrarian's SystematicReviewAgent to conduct AI-assisted systematic literature reviews with human oversight and complete audit trails.

## Overview

The SystematicReviewAgent automates the systematic review process while maintaining transparency and reproducibility. It:

- Generates diverse search queries using multiple strategies
- Filters papers using fast heuristics and LLM-based evaluation
- Scores relevance and quality using specialized AI agents
- Ranks papers by configurable composite scores
- Generates comprehensive reports in multiple formats
- Maintains a complete audit trail for reproducibility

## Quick Start

### Using the CLI

The simplest way to run a systematic review:

```bash
# Basic review
python systematic_review_cli.py --question "What is the effect of statins on cardiovascular disease prevention?"

# With inclusion/exclusion criteria
python systematic_review_cli.py \
    --question "Effect of exercise on depression treatment" \
    --include "RCTs" "Adult patients" "Depression diagnosis" \
    --exclude "Animal studies" "Case reports"

# Automatic mode (no checkpoints)
python systematic_review_cli.py --question "..." --auto

# Quick mode (reduced limits for testing)
python systematic_review_cli.py --question "..." --quick
```

### Using Python

```python
from bmlibrarian.agents.systematic_review import (
    SystematicReviewAgent,
    SearchCriteria,
    ScoringWeights,
    StudyTypeFilter,
)

# Define search criteria
criteria = SearchCriteria(
    research_question="What is the efficacy of statins for CVD prevention?",
    purpose="Systematic review for clinical guidelines",
    inclusion_criteria=[
        "Human studies",
        "Statin intervention",
        "Cardiovascular disease outcomes"
    ],
    exclusion_criteria=[
        "Animal studies",
        "Case reports"
    ],
    target_study_types=[
        StudyTypeFilter.RCT,
        StudyTypeFilter.META_ANALYSIS,
    ],
    date_range=(2010, 2024),
)

# Run review
agent = SystematicReviewAgent()
result = agent.run_review(
    criteria=criteria,
    interactive=True,  # Pause at checkpoints
    output_path="review_results.json"
)

# Access results
print(f"Included: {result.statistics.final_included}")
print(f"Excluded: {result.statistics.final_excluded}")
```

## Search Criteria

### Required Fields

- **research_question**: The primary research question (natural language)
- **purpose**: Purpose of the review (e.g., "Clinical guideline development")
- **inclusion_criteria**: List of criteria papers must meet

### Optional Fields

- **exclusion_criteria**: List of criteria that disqualify papers
- **target_study_types**: Specific study designs to target
- **date_range**: Tuple of (start_year, end_year)
- **language**: Language filter (default: "English")
- **mesh_terms**: MeSH terms for targeted searches
- **custom_search_terms**: Additional search terms

### Study Type Filters

Available study type filters:

| Filter | Description |
|--------|-------------|
| `RCT` | Randomized controlled trials |
| `COHORT_PROSPECTIVE` | Prospective cohort studies |
| `COHORT_RETROSPECTIVE` | Retrospective cohort studies |
| `CASE_CONTROL` | Case-control studies |
| `CROSS_SECTIONAL` | Cross-sectional studies |
| `SYSTEMATIC_REVIEW` | Systematic reviews |
| `META_ANALYSIS` | Meta-analyses |
| `CASE_SERIES` | Case series |
| `CASE_REPORT` | Case reports |
| `QUASI_EXPERIMENTAL` | Quasi-experimental designs |
| `PILOT_FEASIBILITY` | Pilot/feasibility studies |

## Scoring Weights

Customize how papers are ranked by adjusting weights (must sum to 1.0):

```python
weights = ScoringWeights(
    relevance=0.30,        # Relevance to research question
    study_quality=0.25,    # Study design and methodology
    paper_weight=0.25,     # Evidential weight
    recency=0.10,          # Publication year
    source_reliability=0.10,  # Source reliability
)
```

### Using a Weights File

Create a JSON file (e.g., `weights.json`):

```json
{
    "relevance": 0.35,
    "study_quality": 0.30,
    "paper_weight": 0.20,
    "recency": 0.10,
    "source_reliability": 0.05
}
```

Use with CLI:

```bash
python systematic_review_cli.py --question "..." --weights-file weights.json
```

## Workflow Phases

The systematic review proceeds through nine phases:

### 1. Search Planning

The Planner analyzes your research question and generates diverse queries:

- **Semantic queries**: Using embedding similarity
- **Keyword queries**: PostgreSQL tsquery format
- **Hybrid queries**: Combined semantic + keyword
- **HyDE queries**: Hypothetical Document Embeddings
- **PICO-based queries**: For clinical questions

### 2. Search Execution

The SearchExecutor runs all queries and aggregates results:

- Deduplicates papers found by multiple queries
- Tracks which queries found each paper
- Records execution time and result counts

### 3. Initial Filtering

Fast heuristic filters applied before expensive LLM evaluation:

- Date range filtering
- Language filtering
- Study type keyword detection
- Exclusion keyword matching

### 4. Relevance Scoring

LLM-based scoring of each paper's relevance (1-5 scale):

- Analyzes title and abstract
- Provides detailed rationale
- Applies relevance threshold

### 5. Quality Assessment

Comprehensive quality evaluation using multiple agents:

- **StudyAssessmentAgent**: Study design and quality
- **PaperWeightAssessmentAgent**: Evidential weight
- **PICOAgent**: PICO extraction (for applicable studies)
- **PRISMA2020Agent**: PRISMA compliance (for reviews)

### 6. Composite Scoring

Calculates weighted composite scores for ranking:

- Combines relevance, quality, and other metrics
- Paper weight and replication come from the paper weight assessment's
  final weight and replication score. When a paper has no paper weight
  (assessment disabled in configuration, or missing from a run saved before
  this version), those two dimensions are left out and the other weights
  scaled up, so the missing part counts as the average of the paper's other
  scores. The inclusion rationale then says "Paper weight: not assessed".
  Replication is left out the same way when no replication is on record
  (replications are entered by hand)
- Methodological rigor comes from the study assessment's five bias-risk
  ratings (selection, performance, detection, attrition, reporting): the
  worst rated one sets the score (low 8, moderate 5, high 2; "unclear" is
  ignored). Sample size comes from the participant count the study
  assessment reports ("N=120 participants"): under 30 scores 2, under 100
  scores 4, under 500 scores 6, under 1,000 scores 8, larger scores 10. When no
  bias domain is rated, or no count can be read, that dimension is left out
  the same way as a missing paper weight
- If a paper's paper weight assessment fails during the review, the paper
  is listed as a failed assessment and not ranked
- Applies quality gate threshold
- Generates final ranking

### 7. Classification

Papers are classified into three categories:

- **Included**: Meet all criteria, above thresholds
- **Excluded**: Failed one or more criteria
- **Uncertain**: Need human review

### 8. Evidence Synthesis (Optional)

For included papers, the EvidenceSynthesizer extracts and synthesizes relevant evidence:

- **Citation Extraction**: Uses CitationFinderAgent to extract key passages from each paper that directly address the research question
- **Narrative Synthesis**: Generates a cohesive narrative answer using LLM-based synthesis
- **Key Findings**: Identifies main findings with supporting citations
- **Evidence Strength Assessment**: Rates overall evidence as Strong/Moderate/Limited/Insufficient
- **Limitations Identification**: Notes gaps and limitations in the evidence

This phase is enabled by default but can be disabled via configuration:

```json
{
    "agents": {
        "systematic_review": {
            "enable_evidence_synthesis": true,
            "synthesis_model": "gpt-oss:20b",
            "citation_min_relevance": 0.7,
            "max_citations_per_paper": 3,
            "synthesis_temperature": 0.3
        }
    }
}
```

### 9. Report Generation

Creates comprehensive outputs:

- JSON: Full machine-readable results
- Markdown: Human-readable report
- CSV: Spreadsheet export
- PRISMA: Flow diagram data

## Interactive Mode

In interactive mode (`interactive=True`), the agent pauses at key checkpoints:

### Checkpoint 1: Search Strategy

Review generated queries before execution. You can:

- Approve and continue
- Abort the review

### Checkpoint 2: Initial Results

Review search results summary:

- Number of unique papers found
- Sample titles
- Deduplication statistics

### Checkpoint 3: Scoring Complete

Review scoring results:

- Papers above/below threshold
- Average scores
- Distribution statistics

### Checkpoint 4: Quality Assessment

Review quality assessment results:

- Assessment statistics
- Study type distribution

At each checkpoint, enter:

- `Y` or Enter: Continue
- `N` or `Q`: Stop the review here

A stopped review writes no report. The CLI prints **REVIEW STOPPED** with the
checkpoint it stopped at, and from Python the result has `aborted == True`
and an `abort_reason` (an aborted result has no papers; it is not an empty
finding). Resume it later from its checkpoint file.

## Resuming a Review

When an output directory is set, the agent saves a checkpoint file at each
checkpoint (`<output-dir>/checkpoints/<review_id>_<checkpoint>.json`).
Every relevance score and quality assessment is also saved to the database
the moment it is made, in the review's *evaluation run*.

Resume an aborted, interrupted or failed review with:

```bash
uv run python systematic_review_cli.py --resume <review_id or checkpoint path>
```

or, from Python, `agent.run_review_from_checkpoint("path/to/checkpoint.json")`.

The review continues from the phase after the checkpoint:

| Resume from | Runs again |
|-------------|------------|
| Search Strategy | Search (phased or standard, as configured), then everything after |
| Initial Results | Initial filter, scoring, quality assessment, report |
| Scoring Complete | Quality assessment and report |
| Quality Assessment | Ranking, quality gate, synthesis and report |

Papers already scored or assessed in the evaluation run are **reused, not
re-evaluated** — a review that crashed half-way through scoring only scores
the remaining papers.

The relevance and quality thresholds are re-applied to the saved scores, so
you can change them when resuming: papers that fall below a raised relevance
threshold are excluded (even if they were already assessed), and papers
admitted by a lowered threshold are assessed before the report is written.

- **CLI**: a resume keeps the thresholds recorded in the checkpoint;
  `--relevance-threshold` / `--quality-threshold` replace them.
- **GUI**: the threshold fields of the resume form apply.
- **Python**: the agent's configuration applies.

### Papers whose evaluation failed

If the language model fails on a paper (for example, the model server goes
down mid-review), that paper's score or assessment is **not** saved. The
review continues, and the paper appears in the report's *uncertain* list
("Relevance scoring failed" or "Quality assessment failed") so it is
reviewed by hand rather than lost. You are warned how many papers this
affected. Because nothing was saved for them, resuming retries them:

- failed **scoring**: resume from the Search Strategy or Initial Results
  checkpoint;
- failed **quality assessment**: resume from the Scoring Complete or Quality
  Assessment checkpoint.

If a score or assessment cannot be *saved* to the database, the review stops
with an error instead of continuing without that paper.

### When resuming fails

Resuming fails with an error explaining why (the CLI prefixes it with
"Cannot resume" or "Invalid checkpoint"), rather than producing an empty
report, when:

- the checkpoint file is malformed or incomplete;
- none of the checkpoint's papers are in the database, or the checkpoint's
  evaluation run is not (for example, the application is connected to a
  different database than the review used);
- the evaluation run belongs to a different research question;
- a Scoring Complete or Quality Assessment checkpoint has no evaluation run
  at all — resume from Search Strategy or Initial Results instead.

If only *some* of the checkpoint's papers are missing from the database, the
resume continues without them and warns you, naming their document IDs.

A finished review's evaluation run is marked *completed*; a stopped or
interrupted one *paused*; a failed one *failed*. Resuming puts the run back
in progress.

## Output Formats

### JSON Report

Complete machine-readable output including:

- Metadata and configuration
- Search strategy details
- All included/excluded papers with scores
- Complete audit trail

### Markdown Report

Human-readable report with:

- **Evidence Synthesis** (if enabled):
  - Answer to Research Question: Direct answer based on extracted evidence
  - Evidence Strength: Overall assessment
  - Synthesized Evidence: Narrative synthesis with inline citations
  - Key Findings: Main findings with supporting studies
  - Limitations: Identified gaps in evidence
  - Supporting Citations: Full details of extracted passages
- Executive summary (statistics)
- Methodology description
- Included papers with details
- Excluded papers by stage
- PRISMA flow diagram
- Audit trail

### CSV Export

Spreadsheet-compatible format for analysis:

- `{name}_included.csv`: Included papers
- `{name}_excluded.csv`: Excluded papers

### PRISMA Flow Diagram

JSON data structured for PRISMA 2020 flow diagrams:

```json
{
    "format": "PRISMA_2020",
    "identification": {...},
    "screening": {...},
    "eligibility": {...},
    "included": {...}
}
```

## Configuration

### Using config.json

Add to `~/.bmlibrarian/config.json`:

```json
{
    "agents": {
        "systematic_review": {
            "model": "gpt-oss:20b",
            "temperature": 0.3,
            "relevance_threshold": 3.0,
            "quality_threshold": 5.0,
            "max_results_per_query": 100,
            "run_study_assessment": true,
            "run_paper_weight": true,
            "run_pico_extraction": true,
            "run_prisma_assessment": true,
            "enable_evidence_synthesis": true,
            "synthesis_model": null,
            "citation_min_relevance": 0.7,
            "max_citations_per_paper": 3,
            "synthesis_temperature": 0.3,
            "use_phased_search": true,
            "max_phase2_no_overlap": 10,
            "enable_query_feedback": true
        }
    }
}
```

### Evidence Synthesis Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `enable_evidence_synthesis` | `true` | Enable/disable evidence synthesis phase |
| `synthesis_model` | `null` | LLM for synthesis (uses main model if null) |
| `citation_min_relevance` | `0.7` | Minimum citation relevance threshold (0-1) |
| `max_citations_per_paper` | `3` | Maximum citations to extract per paper |
| `synthesis_temperature` | `0.3` | LLM temperature for narrative synthesis |

### Phased Search Configuration

The systematic review agent uses a two-phase search strategy by default to reduce irrelevant document processing:

- **Phase 1**: Semantic and HyDE queries establish a high-quality baseline
- **Phase 2**: Keyword queries run against the baseline with overlap tracking

| Setting | Default | Description |
|---------|---------|-------------|
| `use_phased_search` | `true` | Enable two-phase search strategy |
| `max_phase2_no_overlap` | `10` | Max documents to score from keyword queries with no Phase 1 overlap |
| `enable_query_feedback` | `true` | Track query effectiveness for adaptive query generation |

When `enable_query_feedback` is enabled, the system:
- Tracks which queries found documents scoring above the relevance threshold
- Identifies "effective" vs "ineffective" query patterns
- Uses these patterns as examples to improve future LLM-generated queries

### CLI Options

```
Options:
  -q, --question TEXT       Research question
  --purpose TEXT            Purpose of the review
  --include CRITERION       Inclusion criteria (multiple allowed)
  --exclude CRITERION       Exclusion criteria (multiple allowed)
  --study-types TYPE        Target study types
  --date-range START END    Date range filter
  --mesh-terms TERM         MeSH terms (multiple allowed)
  --criteria-file PATH      Load criteria from JSON file
  --weights-file PATH       Load weights from JSON file
  --relevance-threshold N   Minimum relevance score (1-5, default 3.0;
                            with --resume, default: the checkpoint's)
  --quality-threshold N     Minimum quality score (0-10, default 5.0;
                            with --resume, default: the checkpoint's)
  -o, --output-dir PATH     Output directory
  --output-name NAME        Base name for output files
  --format FORMAT           Output format (json/markdown/csv/all)
  --auto                    Skip all checkpoints
  --quick                   Quick mode with reduced limits
  -v, --verbose             Enable debug logging
  --log-file PATH           Path to log file
```

## Criteria File Format

Create a JSON file for reusable criteria:

```json
{
    "research_question": "What is the effect of statins on CVD prevention?",
    "purpose": "Clinical guideline development",
    "inclusion_criteria": [
        "Human studies",
        "Statin intervention",
        "Cardiovascular outcomes"
    ],
    "exclusion_criteria": [
        "Animal studies",
        "Case reports"
    ],
    "target_study_types": ["rct", "meta_analysis"],
    "date_range": [2010, 2024],
    "language": "English",
    "mesh_terms": ["Statins", "Cardiovascular Diseases"]
}
```

Use with CLI:

```bash
python systematic_review_cli.py --criteria-file my_criteria.json
```

## Best Practices

### 1. Define Clear Criteria

- Be specific about inclusion/exclusion criteria
- Use study type filters when appropriate
- Set realistic date ranges

### 2. Use Interactive Mode First

- Review search results before scoring
- Adjust thresholds based on distribution
- Validate quality assessment approach

### 3. Iterate if Needed

- If results are insufficient, broaden criteria
- Adjust relevance threshold based on distribution
- Consider additional search terms

### 4. Review Uncertain Papers

- Uncertain papers need human review
- Check the rationale for uncertainty
- Make final inclusion decisions manually

### 5. Preserve Audit Trail

- Keep the JSON output for reproducibility
- Document any manual decisions
- Archive with research documentation

## Troubleshooting

### No Papers Found

- Check date range is realistic
- Verify MeSH terms are correct
- Try broader search terms
- Remove restrictive study type filters

### Too Many Papers

- Add more specific exclusion criteria
- Narrow date range
- Increase relevance threshold
- Target specific study types

### Low Relevance Scores

- Refine research question
- Add more specific inclusion criteria
- Check if papers match the domain

### Quality Assessment Issues

- Ensure papers have abstracts
- Check if study types are assessable
- Review PICO/PRISMA suitability

## Example Workflow

```bash
# 1. Create criteria file
cat > my_review.json << 'EOF'
{
    "research_question": "What is the effect of exercise on depression?",
    "purpose": "Treatment guideline review",
    "inclusion_criteria": [
        "Human studies",
        "Exercise intervention",
        "Depression outcomes"
    ],
    "exclusion_criteria": [
        "Animal studies",
        "Review articles"
    ],
    "target_study_types": ["rct", "cohort_prospective"],
    "date_range": [2015, 2024]
}
EOF

# 2. Run interactive review
python systematic_review_cli.py --criteria-file my_review.json -o ./output

# 3. Review outputs
ls ./output/
# review_*.json      - Full results
# review_*.md        - Markdown report
# review_*_prisma.json - PRISMA data

# 4. Open markdown report
cat ./output/review_*.md
```

## Related Documentation

- [Query Agent Guide](query_agent_guide.md) - Query generation details
- [Study Assessment Guide](study_assessment_guide.md) - Quality assessment
- [PRISMA 2020 Guide](prisma2020_guide.md) - PRISMA compliance
- [Multi-Model Query Guide](multi_model_query_guide.md) - Search strategies
- [Citation Guide](citation_guide.md) - Citation extraction details
- [Evidence Synthesis System](../developers/evidence_synthesis_system.md) - Technical details
