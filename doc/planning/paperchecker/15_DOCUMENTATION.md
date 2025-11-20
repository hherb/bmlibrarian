# Step 15: Comprehensive Documentation

## Context

All PaperChecker components, tests, and interfaces are now complete. We need comprehensive documentation for users and developers.

## Objective

Create complete documentation covering:
- User guides for CLI and laboratory
- Developer documentation for architecture and components
- API reference documentation
- Example workflows and use cases
- Configuration guide

## Requirements

- Clear, concise writing
- Code examples throughout
- Screenshots/diagrams where helpful
- Multiple audience levels (user, developer, contributor)
- Markdown format for easy maintenance

## Documentation Structure

```
doc/
├── users/
│   ├── paper_checker_guide.md          # Main user guide
│   ├── paper_checker_cli_guide.md      # CLI usage guide
│   ├── paper_checker_lab_guide.md      # Laboratory guide
│   └── paper_checker_configuration.md  # Configuration reference
└── developers/
    ├── paper_checker_architecture.md   # System architecture
    ├── paper_checker_components.md     # Component documentation
    ├── paper_checker_database.md       # Database schema docs
    └── paper_checker_api_reference.md  # API reference
```

## User Documentation

### `doc/users/paper_checker_guide.md`

```markdown
# PaperChecker User Guide

## Overview

PaperChecker is a sophisticated fact-checking system for medical abstracts that validates research claims by systematically searching for and analyzing contradictory evidence.

## What is PaperChecker?

PaperChecker analyzes medical abstracts to determine if their core claims are supported by the broader literature. For any given abstract, it:

1. Extracts the main research claims
2. Formulates counter-claims
3. Searches the literature for contradictory evidence
4. Evaluates the strength of counter-evidence
5. Provides a verdict on each claim (supports/contradicts/undecided)

## Key Features

- **Automated Statement Extraction**: Identifies core research claims
- **Intelligent Counter-Evidence Search**: Multi-strategy literature search
- **Comprehensive Analysis**: Scores, citations, and synthesis
- **Clear Verdicts**: Evidence-based classification with confidence levels
- **Multiple Interfaces**: CLI for batch processing, Lab for interactive use

## Quick Start

### CLI Usage

```bash
# Check abstracts from JSON file
uv run python paper_checker_cli.py abstracts.json

# Check specific PMIDs
uv run python paper_checker_cli.py --pmid 12345678 23456789

# Export results
uv run python paper_checker_cli.py abstracts.json -o results.json --export-markdown reports/
```

### Laboratory Usage

```bash
# Launch interactive laboratory
uv run python paper_checker_lab.py
```

## Understanding Results

### Verdict Types

- **CONTRADICTS**: Counter-evidence contradicts the original claim
  - Multiple high-quality studies support the counter-position
  - Original claim is not well-supported by current literature

- **SUPPORTS**: Counter-evidence actually supports the original claim
  - Search failed to find contradictory evidence
  - Found studies confirm the original statement

- **UNDECIDED**: Evidence is mixed, insufficient, or unclear
  - Some evidence for and against
  - Too few studies or significant limitations

### Confidence Levels

- **High**: Strong, consistent evidence from multiple sources
- **Medium**: Moderate evidence with some limitations
- **Low**: Weak, limited, or uncertain evidence

## Example Workflow

### Input Abstract

```
Background: Type 2 diabetes management requires effective long-term
glycemic control. Objective: To compare the efficacy of metformin versus
GLP-1 receptor agonists. Results: Metformin demonstrated superior HbA1c
reduction (1.5% vs 1.2%, p<0.001). Conclusion: Metformin shows superior
efficacy compared to GLP-1 agonists for T2DM.
```

### PaperChecker Analysis

**Statement Extracted:**
> "Metformin demonstrates superior efficacy to GLP-1 agonists in T2DM"

**Counter-Statement:**
> "GLP-1 agonists are superior or equivalent to metformin in T2DM"

**Counter-Evidence Found:**
- 47 documents identified via multi-strategy search
- 12 high-relevance documents (score ≥ 3)
- 8 citations extracted supporting counter-claim

**Verdict:** CONTRADICTS (High Confidence)

**Rationale:**
> Multiple randomized controlled trials from 2022-2023 demonstrate GLP-1
> agonist superiority over metformin in HbA1c reduction, cardiovascular
> outcomes, and weight management. Meta-analyses confirm these findings
> with high statistical significance.

## Input File Format

```json
[
  {
    "abstract": "Full abstract text...",
    "metadata": {
      "pmid": 12345678,
      "title": "Study Title",
      "authors": ["Smith J", "Jones A"],
      "year": 2023,
      "journal": "Journal Name",
      "doi": "10.1234/example"
    }
  }
]
```

## Best Practices

### When to Use PaperChecker

✅ **Good use cases:**
- Validating claims from new preprints
- Auditing systematic reviews
- Identifying controversial findings
- Training data quality assessment

❌ **Not recommended for:**
- Extremely recent findings (< 3 months)
- Highly specialized niche topics with limited literature
- Methodological statements without empirical claims

### Interpreting Results

1. **Check confidence levels**: High confidence verdicts are more reliable
2. **Review citations**: Examine the specific evidence found
3. **Consider context**: PaperChecker searches your database, not all literature
4. **Domain expertise**: Always apply your medical knowledge

## Troubleshooting

### "No documents found"

- Database may not contain relevant literature
- Try broader search terms
- Check that abstracts are indexed with embeddings

### "All undecided verdicts"

- May indicate genuinely mixed evidence
- Could suggest topic is too specialized
- Check that counter-statements are well-formed

### Slow processing

- Each abstract takes 2-5 minutes
- Use batch processing for multiple abstracts
- Consider using faster models for scoring

## See Also

- [CLI Guide](paper_checker_cli_guide.md) - Detailed CLI usage
- [Laboratory Guide](paper_checker_lab_guide.md) - Interactive interface
- [Configuration Guide](paper_checker_configuration.md) - Settings reference
```

## Developer Documentation

### `doc/developers/paper_checker_architecture.md`

```markdown
# PaperChecker Architecture

## System Overview

PaperChecker is a hybrid architecture combining patterns from CounterfactualAgent (reference tracking, multi-strategy search) and FactCheckerAgent (evidence evaluation, verdict generation).

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

## Workflow Steps

1. **Statement Extraction** (`StatementExtractor`)
   - Input: Abstract text
   - Output: List[Statement]
   - LLM analyzes abstract for core claims
   - Configurable max_statements (default: 2)

2. **Counter-Statement Generation** (`CounterStatementGenerator`)
   - Input: Statement
   - Output: Negated statement text
   - Semantic negation (not just adding "not")

3. **HyDE Generation** (`HyDEGenerator`)
   - Input: Counter-statement
   - Output: Hypothetical abstracts + keywords
   - Multiple HyDE abstracts per statement

4. **Multi-Strategy Search** (`SearchCoordinator`)
   - Input: Counter-statement with search materials
   - Output: SearchResults with provenance
   - Three parallel strategies: semantic, HyDE, keyword
   - Deduplication and provenance tracking

5. **Document Scoring** (reuses `DocumentScoringAgent`)
   - Input: Counter-statement + documents
   - Output: List[ScoredDocument]
   - 1-5 relevance scale
   - Threshold filtering

6. **Citation Extraction** (reuses `CitationFinderAgent`)
   - Input: Counter-statement + high-scoring docs
   - Output: List[ExtractedCitation]
   - Passage extraction with metadata

7. **Counter-Report Generation**
   - Input: Citations + search stats
   - Output: CounterReport
   - Prose synthesis of counter-evidence

8. **Verdict Analysis** (`VerdictAnalyzer`)
   - Input: Original statement + counter-report
   - Output: Verdict
   - Supports/contradicts/undecided classification

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

## Key Design Decisions

### 1. Multi-Strategy Search

Why: Different search strategies capture different aspects of relevance

- **Semantic**: Conceptual similarity via embeddings
- **HyDE**: Structural similarity to hypothetical documents
- **Keyword**: Explicit term matching

Combination provides comprehensive coverage.

### 2. Reference Tracking (Provenance)

Every document ID tracked from search → scoring → citation

Benefits:
- Transparency: Know which strategy found each document
- Debugging: Identify strategy effectiveness
- Optimization: Prioritize multi-strategy matches

### 3. Verdict Granularity

Per-statement verdicts + overall assessment

Why:
- Abstracts often contain multiple claims
- Some may be supported, others contradicted
- Granular analysis more informative

### 4. Integration Over Reimplementation

Reuses existing BMLibrarian agents:
- DocumentScoringAgent for scoring
- CitationFinderAgent for extraction

Benefits:
- Code reuse
- Consistency with existing workflows
- Faster development

## Performance Characteristics

- **Single abstract**: 2-5 minutes (production)
- **Batch processing**: Serial execution (local Ollama optimization)
- **Bottlenecks**: LLM calls (extraction, generation, analysis)
- **Optimization**: Use faster models for scoring

## Error Handling

- **Graceful degradation**: If one statement fails, continue with others
- **Retry logic**: LLM API failures retried with backoff
- **Validation**: Document IDs verified before processing
- **Checkpointing**: Database saves after each major step

## See Also

- [Component Documentation](paper_checker_components.md)
- [Database Schema](paper_checker_database.md)
- [API Reference](paper_checker_api_reference.md)
```

## Success Criteria

- [ ] All user documentation complete
- [ ] All developer documentation complete
- [ ] API reference generated
- [ ] Code examples tested and working
- [ ] Configuration guide comprehensive
- [ ] Architecture diagrams created
- [ ] Troubleshooting guide helpful
- [ ] Examples cover common use cases
- [ ] Documentation reviewed for clarity
- [ ] Links between documents working

## Next Steps

After completing this step, proceed to:
- **Step 16**: Final Integration and Deployment (16_FINAL_INTEGRATION.md)
- Final testing, deployment preparation, and launch checklist
