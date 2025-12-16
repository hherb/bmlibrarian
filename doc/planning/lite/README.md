# BMLibrarian Lite Quality Filtering - Implementation Guide

## Overview

This directory contains step-by-step implementation plans for adding quality filtering to BMLibrarian Lite. The feature enables users to filter literature by study design quality (RCTs, systematic reviews, etc.) while preserving Lite's lightweight, easy-to-deploy nature.

## Key Design Decisions

### Why LLM Classification Over Keywords?

**Rejected Approach**: Rule-based keyword extraction was considered but rejected because:
- Documents frequently reference other studies' methodologies
- Example: "Unlike the RCT by Smith et al., our observational study..." incorrectly matches "RCT"
- No amount of exclusion patterns can reliably handle all linguistic variations
- False positive rate is unacceptable for quality filtering decisions

**Adopted Approach**: LLM-based classification using Claude Haiku:
- Understands semantic context ("we conducted an RCT" vs "unlike previous RCTs")
- Cost: ~$0.00025 per document (negligible)
- Accuracy: ~90-95% for study design classification
- Simple, maintainable, and reliable

### Tiered Assessment Strategy

```
Tier 1: PubMed Metadata (free, instant)
    │   Uses NLM-assigned publication types
    │   ~85-95% accuracy when available
    │
    ↓   (if unclassified or low confidence)

Tier 2: Claude Haiku (cheap, accurate)
    │   Fast classification (~0.5s/doc)
    │   ~$0.00025 per document
    │
    ↓   (if detailed assessment requested)

Tier 3: Claude Sonnet (comprehensive, optional)
        Full quality assessment with:
        - Bias risk evaluation
        - Strengths/limitations
        - Evidence level (Oxford CEBM)
```

## Implementation Phases

| Phase | Focus | Key Files | Status |
|-------|-------|-----------|--------|
| [Phase 1](phase1_core_quality_module.md) | Data models, Metadata filter | `data_models.py`, `metadata_filter.py` | Planned |
| [Phase 2](phase2_llm_classification.md) | LLM classifiers, Manager | `study_classifier.py`, `quality_agent.py`, `quality_manager.py` | Planned |
| [Phase 3](phase3_gui_integration.md) | GUI widgets, Workflow | `quality_filter_panel.py`, `quality_badge.py` | Planned |
| [Phase 4](phase4_report_enhancement.md) | Report formatting, Export | `evidence_summary.py`, `report_formatter.py` | Planned |

## Directory Structure (After Implementation)

```
src/bmlibrarian/lite/
├── quality/                        # NEW: Quality filtering module
│   ├── __init__.py
│   ├── data_models.py              # Phase 1: Enums, dataclasses
│   ├── metadata_filter.py          # Phase 1: PubMed type filter
│   ├── study_classifier.py         # Phase 2: Haiku classifier
│   ├── quality_agent.py            # Phase 2: Sonnet assessor
│   ├── quality_manager.py          # Phase 2: Orchestrator
│   ├── evidence_summary.py         # Phase 4: Summary generator
│   └── report_formatter.py         # Phase 4: Citation formatter
├── gui/
│   ├── quality_filter_panel.py     # Phase 3: Filter UI
│   ├── quality_badge.py            # Phase 3: Badge widget
│   └── quality_summary.py          # Phase 3: Summary widget
└── constants.py                    # Updated with quality constants
```

## Cost Analysis

| Scenario | Documents | Haiku Calls | Sonnet Calls | Est. Cost |
|----------|-----------|-------------|--------------|-----------|
| Metadata only | 50 | 0 | 0 | $0.00 |
| Metadata + Haiku fallback (30%) | 50 | 15 | 0 | ~$0.004 |
| Full Haiku classification | 50 | 50 | 0 | ~$0.0125 |
| Haiku + Sonnet detailed | 50 | 50 | 50 | ~$0.16 |

**Default**: Metadata + Haiku for unclassified documents (~$0.004/session)

## User-Facing Features

### Quality Filter Options
- "Only systematic reviews & meta-analyses" (Tier 5)
- "Only RCTs and above" (Tier 4+)
- "Controlled studies and above" (Tier 3+)
- "All primary research" (Tier 2+)
- "No filtering" (include all)

### Additional Requirements
- Require randomization
- Require blinding
- Minimum sample size

### Assessment Depth
- Metadata only (free, instant)
- AI classification (default)
- Detailed assessment (opt-in)

## Quality Tier Hierarchy

| Tier | Description | Study Designs |
|------|-------------|---------------|
| 5 | Systematic synthesis | Systematic reviews, Meta-analyses |
| 4 | Experimental | RCTs, Clinical trials, Guidelines |
| 3 | Controlled observational | Prospective cohorts, Case-control |
| 2 | Observational | Cross-sectional, Retrospective |
| 1 | Anecdotal/opinion | Case reports, Editorials, Letters |
| 0 | Unclassified | Unknown, Other |

## Report Enhancements

After implementation, reports will include:

1. **Evidence Summary Section**
   - Total studies by quality tier
   - Average quality score
   - High-quality evidence percentage
   - Quality considerations and gaps

2. **Quality-Annotated Citations**
   - Study design label
   - Sample size (when available)
   - Blinding status

3. **References with Quality Badges**
   - Study design in brackets after each reference

## Testing Strategy

### Unit Tests
- Data model validation
- Metadata filter accuracy
- LLM response parsing
- Quality manager tier selection

### Critical Test Cases
- Abstracts that MENTION RCTs but ARE NOT RCTs
- Abstracts that DISCUSS systematic reviews but ARE observational
- Abstracts that COMPARE to double-blind studies but ARE open-label

### Validation Set
100 curated abstracts with known study designs:
- 10 systematic reviews
- 20 RCTs
- 20 cohort studies
- 20 case-control studies
- 20 case reports
- 10 editorials/letters

## Implementation Order

1. **Phase 1** (Foundation)
   - Must be completed first
   - No dependencies on other phases

2. **Phase 2** (LLM Integration)
   - Requires Phase 1 complete
   - Can be tested independently

3. **Phase 3** (GUI)
   - Requires Phases 1 and 2
   - Enables user interaction

4. **Phase 4** (Reports)
   - Can proceed in parallel with Phase 3
   - Requires Phase 2 for assessments

## References

- [Main Quality Filtering Plan](../lite_quality_filtering_plan.md)
- [BMLibrarian Lite Architecture](../../developers/bmlibrarian_lite_architecture.md)
- [BMLibrarian Lite User Guide](../../users/bmlibrarian_lite_guide.md)
