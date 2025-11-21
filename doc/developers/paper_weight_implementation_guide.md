# PaperWeightAssessment Implementation Guide

**Master Document - Complete Implementation Plan**

## Overview

This guide provides a comprehensive roadmap for implementing the PaperWeightAssessment module for BMLibrarian. The module provides multi-dimensional assessment of biomedical research papers to determine their evidential weight.

## Project Goals

### Primary Objective
Create a reusable, generic paper weighting system that can:
1. Assess individual papers with high reliability
2. Provide full audit trail for reproducibility
3. Scale to batch processing of entire databases
4. Support algorithmic ranking based on evidence quality

### Design Principles
- **Multi-dimensional assessment:** Five independent scores combined into final weight
- **Hybrid approach:** Rule-based extractors + LLM-based assessors
- **Database-backed:** Full persistence with audit trail in PostgreSQL
- **Versioned methodology:** Re-assessment when methodology improves
- **Battle-tested:** Visual laboratory for validation and refinement

## Implementation Steps

### Sequential Implementation Order

**IMPORTANT:** Implement steps sequentially, validating each before proceeding to the next.

### Step 1: Database Migration Script
**File:** `doc/developers/paper_weight_step1_database_migration.md`

**Objective:** Create PostgreSQL schema for storing assessments

**Deliverables:**
- [ ] `migrations/add_paper_weight_schema.sql`
- [ ] `migrations/rollback_paper_weight_schema.sql`
- [ ] Schema validation tests

**Key Tables:**
- `paper_weights.assessments` - Main assessment table
- `paper_weights.assessment_details` - Audit trail
- `paper_weights.replications` - Replication tracking

**Estimated Time:** 2-3 hours

---

### Step 2: Data Models Implementation
**File:** `doc/developers/paper_weight_step2_data_models.md`

**Objective:** Implement Python dataclasses for type-safe assessment representation

**Deliverables:**
- [ ] `src/bmlibrarian/agents/paper_weight_agent.py` (dataclasses only)
- [ ] `tests/test_paper_weight_models.py`
- [ ] Export in `src/bmlibrarian/agents/__init__.py`

**Key Classes:**
- `AssessmentDetail` - Single audit trail entry
- `DimensionScore` - Score for one dimension with details
- `PaperWeightResult` - Complete assessment result

**Estimated Time:** 3-4 hours

---

### Step 3: Configuration Schema
**File:** `doc/developers/paper_weight_step3_configuration.md`

**Objective:** Add configuration section to BMLibrarian config system

**Deliverables:**
- [ ] Configuration schema in `src/bmlibrarian/cli/config.py`
- [ ] `config_examples/paper_weight_assessment_example.json`
- [ ] `tests/test_paper_weight_config.py`
- [ ] Validation functions

**Key Configuration:**
- Dimension weights (must sum to 1.0)
- Study type hierarchy
- Sample size scoring parameters
- Methodological quality weights
- Risk of bias weights

**Estimated Time:** 2-3 hours

---

### Step 4: Rule-Based Extractors
**File:** `doc/developers/paper_weight_step4_rule_based_extractors.md`

**Objective:** Implement fast, deterministic extractors for study type and sample size

**Deliverables:**
- [ ] `_extract_study_type()` method
- [ ] `_extract_sample_size()` method
- [ ] Helper methods for pattern matching
- [ ] `tests/test_paper_weight_extractors.py`

**Features:**
- Keyword-based study type detection
- Regex-based sample size extraction
- Power calculation detection
- CI reporting detection

**Estimated Time:** 4-5 hours

---

### Step 5: LLM-Based Assessors
**File:** `doc/developers/paper_weight_step5_llm_assessors.md`

**Objective:** Implement LLM-powered assessors for methodological quality and risk of bias

**Deliverables:**
- [ ] `_assess_methodological_quality()` method
- [ ] `_assess_risk_of_bias()` method
- [ ] LLM prompt templates
- [ ] JSON parsing logic
- [ ] `tests/test_paper_weight_llm_assessors.py`

**Components:**
- Methodological quality (6 sub-components, 10 points total)
- Risk of bias (4 domains, 10 points total)
- Structured JSON output from LLM
- Evidence extraction and reasoning

**Estimated Time:** 6-8 hours

---

### Step 6: Database Persistence and Caching
**File:** `doc/developers/paper_weight_step6_database_persistence.md`

**Objective:** Implement caching and database operations

**Deliverables:**
- [ ] `_get_cached_assessment()` method
- [ ] `_store_assessment()` method
- [ ] `assess_paper()` main method
- [ ] `_check_replication_status()` method
- [ ] `tests/test_paper_weight_persistence.py`

**Features:**
- Version-based cache invalidation
- Full audit trail storage
- Replication status checking
- Error handling and recovery

**Estimated Time:** 4-6 hours

---

### Step 7: Laboratory GUI (PySide6)
**File:** `doc/developers/paper_weight_step7_qt_laboratory_gui.md`

**Objective:** Build visual laboratory for battle testing

**Deliverables:**
- [ ] `paper_weight_lab.py` (main application)
- [ ] Document selection interface
- [ ] Real-time progress display
- [ ] Results visualization
- [ ] Audit trail tree view
- [ ] Export functionality

**Features:**
- Background thread assessment (responsive GUI)
- Expandable audit trail
- Markdown report export
- Weight configuration dialog

**Estimated Time:** 8-12 hours

---

## Total Estimated Time: 29-41 hours

## Assessment Dimensions

### 1. Study Design (0-10 points, weight: 0.25)
**Method:** Rule-based keyword matching

**Hierarchy:**
- Systematic review/meta-analysis: 10
- RCT: 8
- Prospective cohort: 6
- Retrospective cohort: 5
- Case-control: 4
- Cross-sectional: 3
- Case series: 2
- Case report: 1

### 2. Sample Size (0-10 points, weight: 0.15)
**Method:** Hybrid (regex + LLM bonuses)

**Formula:** `min(10, log10(n) * 2.0) + bonuses`

**Bonuses:**
- Power calculation: +2.0
- CI reporting: +0.5

### 3. Methodological Quality (0-10 points, weight: 0.30)
**Method:** LLM-based assessment

**Components:**
- Randomization: 2.0
- Blinding: 3.0
- Allocation concealment: 1.5
- Protocol preregistration: 1.5
- ITT analysis: 1.0
- Attrition handling: 1.0

### 4. Risk of Bias (0-10 points, weight: 0.20)
**Method:** LLM-based assessment (inverted scale: 10=low risk)

**Domains:**
- Selection bias: 2.5
- Performance bias: 2.5
- Detection bias: 2.5
- Reporting bias: 2.5

### 5. Replication Status (0-10 points, weight: 0.10)
**Method:** Database query (manual entry initially)

**Scoring:**
- Not replicated: 0
- Replicated once (comparable quality): 5
- Replicated 2+ times: 8
- Replicated with higher quality: 10

## Final Weight Calculation

```python
final_weight = (
    study_design_score * 0.25 +
    sample_size_score * 0.15 +
    methodological_quality_score * 0.30 +
    risk_of_bias_score * 0.20 +
    replication_status_score * 0.10
)
```

## Technology Stack

### Core Technologies
- **Python:** >=3.12
- **Database:** PostgreSQL with psycopg >=3.2.9
- **LLM:** Ollama (local inference)
- **GUI:** PySide6 (Qt for Python)

### Key Libraries
- `psycopg` - PostgreSQL connectivity
- `requests` - Ollama API communication
- `PySide6` - Qt GUI framework
- `matplotlib` - Visualization (future)

## Testing Strategy

### Unit Tests
- Data models (serialization, deserialization)
- Configuration validation
- Rule-based extractors
- LLM response parsing

### Integration Tests
- Database operations
- LLM communication (requires Ollama)
- Full assessment workflow

### Battle Testing
- Diverse paper types (RCT, cohort, case report)
- Edge cases (missing data, poor quality)
- Methodology refinement based on results

## Validation Plan

### Phase 1: Proof of Concept
1. Assess 10-20 diverse papers manually
2. Compare agent scores vs. expert judgment
3. Identify systematic biases or errors
4. Refine prompts and scoring logic

### Phase 2: Systematic Validation
1. Use manually validated dataset (when ready)
2. Calculate inter-rater reliability
3. Tune dimension weights based on data
4. Document validation results

### Phase 3: Production Deployment
1. Batch assessment of document database
2. Integration with DocumentScoringAgent
3. Performance monitoring
4. Continuous improvement

## Future Enhancements

### Automated Replication Discovery
- Citation network analysis
- Study similarity detection
- Automated replication identification

### Advanced Visualizations
- Radar charts for dimension scores
- Timeline of assessment history
- Comparison views for multiple papers

### Batch Processing
- Queue-based assessment of entire database
- Low-priority background processing
- Progress tracking and resumption

### Integration with Existing Agents
- Leverage StudyAssessmentAgent output
- Feed weights into DocumentScoringAgent
- PRISMA 2020 compliance weighting

## Critical Success Factors

### Must Have
✅ Full audit trail for reproducibility
✅ Version-based methodology evolution
✅ Database persistence with caching
✅ Visual laboratory for validation
✅ Configurable dimension weights

### Should Have
⭕ Integration with StudyAssessmentAgent
⭕ Batch processing capabilities
⭕ Export to multiple formats
⭕ Automated replication detection

### Nice to Have
⚪ Advanced visualizations (radar charts)
⚪ Comparative analysis tools
⚪ Real-time dashboard
⚪ API endpoints for external access

## Risk Mitigation

### Risk: LLM Hallucination
**Mitigation:** Structured JSON output with evidence quotes, manual validation in lab GUI

### Risk: Inconsistent Scoring
**Mitigation:** Low temperature (0.3), detailed prompts, versioning for methodology changes

### Risk: Performance Bottleneck
**Mitigation:** Intelligent caching, background processing, rule-based pre-filtering

### Risk: Database Corruption
**Mitigation:** Transaction safety, rollback scripts, regular backups

## Documentation Requirements

### Developer Documentation
- [x] Step 1: Database Migration
- [x] Step 2: Data Models
- [x] Step 3: Configuration
- [x] Step 4: Rule-Based Extractors
- [x] Step 5: LLM Assessors
- [x] Step 6: Database Persistence
- [x] Step 7: Laboratory GUI

### User Documentation
- [ ] `doc/users/paper_weight_guide.md` - End-user guide
- [ ] `doc/users/paper_weight_lab_guide.md` - Laboratory tutorial
- [ ] Example assessments and interpretations

### System Documentation
- [ ] Architecture overview
- [ ] Database schema documentation
- [ ] API reference (if exposed)

## Sign-Off and Approval

### Implementation Readiness
- [x] All implementation steps documented
- [x] Technical design reviewed
- [x] Dependencies identified
- [x] Testing strategy defined
- [ ] User approval obtained

### Ready to Proceed
Once user approves this master plan, proceed with Step 1 (Database Migration).

---

**Document Status:** Complete - Ready for Implementation
**Last Updated:** 2025-01-15
**Version:** 1.0.0
