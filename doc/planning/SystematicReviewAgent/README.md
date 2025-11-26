# SystematicReviewAgent Planning Documentation

## Overview

The **SystematicReviewAgent** is an AI-assisted systematic literature review agent that automates the process of finding, filtering, evaluating, and ranking scientific papers based on user-defined research criteria. It represents the most ambitious component of BMLibrarian to date.

Unlike simpler agents that execute fixed workflows, the SystematicReviewAgent exhibits **agentic planning behavior**: it reasons about search strategies, decides when to iterate, and adapts its approach based on results.

## Purpose

The agent accepts:
- A research question
- Brief explanation of research purpose and target document types
- Inclusion criteria (what makes a paper relevant)
- Exclusion criteria (what disqualifies a paper)

And produces:
- A ranked list of papers with comprehensive metadata
- Individual quality assessments for each paper
- Rationale for inclusion/exclusion decisions
- Full audit trail of the search process

## Key Design Decisions

### 1. Checkpoint-Based Autonomy
The agent operates autonomously but pauses at key decision points for human approval:
- After search strategy generation (before running queries)
- After initial search results (before detailed scoring)
- After inclusion/exclusion filtering (before quality assessment)

This balances efficiency with human oversight for scientific rigor.

### 2. Hybrid Inclusion/Exclusion Approach
- Use inclusion criteria to **expand** search (generate related queries)
- Use exclusion criteria to **pre-filter** with fast heuristics
- Use LLM for borderline cases during detailed scoring

### 3. Multi-Tier Scoring with User-Defined Weights
- Individual scores reported for each dimension (relevance, quality, etc.)
- Composite score calculated using user-configurable weights
- PRISMA compliance scored when applicable (systematic reviews/meta-analyses)
- Multi-tier gating: papers must pass quality thresholds before final ranking

### 4. Complete Audit Trail
- **Both included AND rejected papers** are documented in the final report
- Every decision includes rationale
- Process is reproducible and defensible

## Documentation Index

| Document | Description |
|----------|-------------|
| [architecture.md](architecture.md) | System architecture, component design, and tool integration |
| [data_models.md](data_models.md) | Data structures, JSON schemas, and type definitions |
| [implementation_plan.md](implementation_plan.md) | Phased implementation with deliverables and milestones |
| [validation_strategy.md](validation_strategy.md) | Testing, validation, and quality assurance approach |

## Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    SystematicReviewAgent                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    │
│  │  Planner    │───▶│   Executor   │───▶│  Documenter     │    │
│  │  (Strategy) │    │  (Actions)   │    │  (Audit Trail)  │    │
│  └─────────────┘    └──────────────┘    └─────────────────┘    │
│         │                  │                     │              │
│         ▼                  ▼                     ▼              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    Tool Registry                            ││
│  │  ┌───────────────┐ ┌────────────────┐ ┌─────────────────┐  ││
│  │  │ HybridSearch  │ │ DocScoring     │ │ CitationFinder  │  ││
│  │  └───────────────┘ └────────────────┘ └─────────────────┘  ││
│  │  ┌───────────────┐ ┌────────────────┐ ┌─────────────────┐  ││
│  │  │ PICOAgent     │ │ StudyAssess    │ │ PaperWeight     │  ││
│  │  └───────────────┘ └────────────────┘ └─────────────────┘  ││
│  │  ┌───────────────┐ ┌────────────────┐                      ││
│  │  │ PRISMA2020    │ │ QueryAgent     │                      ││
│  │  └───────────────┘ └────────────────┘                      ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

## Workflow Overview

```
┌──────────────────┐
│ 1. Input Criteria │
│  - Research Q    │
│  - Purpose       │
│  - Inc/Exc rules │
└────────┬─────────┘
         ▼
┌──────────────────┐     ┌─────────────────────┐
│ 2. Plan Search   │────▶│ CHECKPOINT: Approve │
│  - Generate      │     │ search strategy?    │
│    queries       │     └──────────┬──────────┘
└──────────────────┘                ▼
                        ┌──────────────────┐
                        │ 3. Execute Search│
                        │  - Run queries   │
                        │  - Deduplicate   │
                        └────────┬─────────┘
                                 ▼
┌──────────────────┐     ┌─────────────────────┐
│ 4. Initial Filter│────▶│ CHECKPOINT: Review  │
│  - Fast exclude  │     │ initial results?    │
│  - Heuristics    │     └──────────┬──────────┘
└──────────────────┘                ▼
                        ┌──────────────────┐
                        │ 5. Score Papers  │
                        │  - Relevance     │
                        │  - Inc/Exc eval  │
                        └────────┬─────────┘
                                 ▼
┌──────────────────┐     ┌─────────────────────┐
│ 6. Quality Assess│────▶│ CHECKPOINT: Proceed │
│  - Study design  │     │ with quality eval?  │
│  - PICO/PRISMA   │     └──────────┬──────────┘
│  - Paper weight  │                ▼
└──────────────────┘     ┌──────────────────┐
                        │ 7. Final Ranking │
                        │  - Compute scores│
                        │  - Apply weights │
                        └────────┬─────────┘
                                 ▼
                        ┌──────────────────┐
                        │ 8. Generate      │
                        │    Report        │
                        │  - Included list │
                        │  - Excluded list │
                        │  - Audit trail   │
                        └──────────────────┘
```

## Tools Used

The SystematicReviewAgent leverages existing BMLibrarian components:

| Tool | Purpose |
|------|---------|
| **SemanticQueryAgent** | Hybrid semantic/keyword search with adaptive thresholds |
| **QueryAgent** | Natural language to PostgreSQL query generation |
| **DocumentScoringAgent** | Relevance scoring (1-5 scale) |
| **CitationFinderAgent** | Extract relevant passages from documents |
| **PICOAgent** | Extract PICO components for clinical studies |
| **StudyAssessmentAgent** | Evaluate study design, quality, and bias risk |
| **PaperWeightAssessmentAgent** | Multi-dimensional evidential weight scoring |
| **PRISMA2020Agent** | PRISMA compliance for systematic reviews |

## Output Format

The agent produces a comprehensive JSON report containing:

```json
{
  "metadata": {
    "research_question": "...",
    "purpose": "...",
    "inclusion_criteria": [...],
    "exclusion_criteria": [...],
    "generated_at": "ISO timestamp",
    "agent_version": "1.0.0"
  },
  "search_strategy": {
    "queries_planned": [...],
    "queries_executed": [...],
    "total_papers_found": 1250,
    "after_deduplication": 890
  },
  "scoring_config": {
    "dimension_weights": {
      "relevance": 0.30,
      "study_quality": 0.25,
      "methodological_rigor": 0.20,
      "sample_size": 0.10,
      "recency": 0.10,
      "citation_count": 0.05
    }
  },
  "included_papers": [
    {
      "document_id": 12345,
      "title": "...",
      "authors": [...],
      "year": 2023,
      "journal": "...",
      "doi": "...",
      "pmid": "...",
      "inclusion_rationale": "...",
      "scores": {
        "relevance": 4.5,
        "study_quality": 8.2,
        "methodological_rigor": 7.5,
        "composite_score": 7.8
      },
      "study_assessment": {...},
      "paper_weight": {...},
      "pico_components": {...},
      "relevant_citations": [...]
    }
  ],
  "excluded_papers": [
    {
      "document_id": 23456,
      "title": "...",
      "exclusion_stage": "initial_filter|scoring|quality_gate",
      "exclusion_reasons": ["study_type_mismatch", "population_excluded"],
      "exclusion_rationale": "Detailed explanation..."
    }
  ],
  "process_log": [
    {
      "step": 1,
      "action": "generate_search_strategy",
      "tool": "Planner",
      "input_summary": "...",
      "output_summary": "Generated 5 search queries",
      "decision_rationale": "...",
      "timestamp": "...",
      "metrics": {"queries_generated": 5}
    }
  ],
  "statistics": {
    "total_considered": 890,
    "passed_initial_filter": 245,
    "passed_relevance_threshold": 89,
    "passed_quality_gate": 42,
    "final_included": 42,
    "final_excluded": 848,
    "processing_time_seconds": 1234.5
  }
}
```

## Success Criteria

1. **Recall**: Find ≥80% of papers that a human expert would include
2. **Precision**: Achieve ≥60% precision (included papers are truly relevant)
3. **Reproducibility**: Same inputs produce consistent results
4. **Transparency**: Every decision is documented and defensible
5. **Efficiency**: Process thousands of papers in reasonable time

## Related Documentation

- [CLAUDE.md](/CLAUDE.md) - Project overview and development guidelines
- [Agent Module](/doc/developers/agent_module.md) - BaseAgent patterns
- [Study Assessment System](/doc/developers/study_assessment_system.md)
- [Paper Checker Architecture](/doc/developers/paper_checker_architecture.md)

## Status

**Planning Phase** - This documentation describes the intended design. Implementation will follow the phased plan in [implementation_plan.md](implementation_plan.md).
