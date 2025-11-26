# Phase 4 Code Review: Quality Assessment Implementation

**Date**: 2025-11-26
**Reviewer**: Claude (AI Assistant)
**Status**: Initial implementation complete, revisions needed

## Executive Summary

Phase 4 implementation successfully delivers a working QualityAssessor that orchestrates all quality assessment tools with lazy loading, error handling, and comprehensive statistics. However, user feedback reveals critical design issues that require revision before Phase 5.

**Critical Issue**: Study type determination uses keyword matching, which has proven unreliable in experiments. Must delegate to PICO/PRISMA agents using LLM-based applicability assessment.

## Golden Rules Compliance

| Rule | Status | Details |
|------|--------|---------|
| 1. Input validation | ✓ PASS | Parameters validated, progress callbacks wrapped in try/except |
| 2. No magic numbers | ✓ PASS | MAX_TEXT_LENGTH constants used |
| 3. No hardcoded paths | ✓ PASS | No paths in quality.py |
| 4. Ollama library | ✓ PASS | Delegated to underlying agents |
| 5. Database manager | ✗ **FAIL** | No database storage implementation (required for versioning) |
| 6. Type hints | ✓ PASS | All parameters have type hints |
| 7. Docstrings | ✓ PASS | All functions and classes documented |
| 8. Error handling | ✓ PASS | Try/except blocks, logger.error, graceful degradation |
| 9. No inline styles | N/A | No GUI code |
| 10. No hardcoded pixels | N/A | No GUI code |
| 11. Reusable functions | ⚠️ WARN | _paper_to_document could be factored out to shared utility |
| 12. Documentation | ✗ **FAIL** | Missing doc/users and doc/developers guides |
| 13. Tests written | ✓ PASS | Comprehensive test suite with 747 lines |
| 14. No truncation | ⚠️ WARN | Abstract truncation uses fixed MAX_TEXT_LENGTH, not configurable |

**Overall**: 9/14 Pass, 2/14 Fail, 3/14 Warn

## Critical Issues Requiring Immediate Revision

### 1. Study Type Determination (CRITICAL)

**Current Implementation**:
```python
# Lines 48-65: Keyword-based study type sets
PICO_APPLICABLE_STUDY_TYPES = {
    "rct", "randomized controlled trial", "clinical trial",
    "cohort", "cohort study", "case-control", ...
}

# Lines 553-594: Keyword matching logic
def _should_run_pico(self, study_type: str) -> bool:
    study_type_lower = study_type.lower().strip()
    for applicable_type in PICO_APPLICABLE_STUDY_TYPES:
        if applicable_type in study_type_lower:
            return True
    return False
```

**Problem**: Keyword-based extraction has proven unreliable in experiments (per user feedback).

**Required Change**: Delegate applicability determination to PICO/PRISMA agents using LLM:
- PICOAgent.extract_pico() should return error with rationale if study type not applicable
- PRISMA2020Agent already has suitability assessment (SuitabilityAssessment dataclass)
- PICO is widely applicable anyway (population + observation usually present, intervention/control can be N/A)
- QualityAssessor handles errors gracefully, continues with other assessments

**Action Items**:
1. Remove _should_run_pico() and _should_run_prisma() methods
2. Always call PICO/PRISMA agents, let them decide applicability
3. Handle agent-returned errors gracefully (log and continue)
4. Remove PICO_APPLICABLE_STUDY_TYPES and PRISMA_APPLICABLE_STUDY_TYPES constants

### 2. No Permanent Storage (CRITICAL)

**Current Implementation**: Quality assessments are ephemeral, only exist in memory during workflow execution.

**Required**: Permanent database storage with versioning metadata:
- Model name and version
- Model parameters (temperature, top_p, etc.)
- Prompt version/hash
- Assessment timestamp
- Agent version
- Document ID reference

**Action Items**:
1. Create database schema: `systematic_review.quality_assessments` table
2. Implement _store_assessment() method using DatabaseManager
3. Add metadata collection from agents
4. Support retrieval of historical assessments
5. Version tracking for reproducibility

### 3. No Partial Assessment Support

**Current Implementation**: All assessments always run (study, weight, PICO, PRISMA).

**Required**: Configurable which assessments to run:
```python
def assess_batch(
    self,
    papers: List[ScoredPaper],
    run_study: bool = True,
    run_weight: bool = True,
    run_pico: bool = True,
    run_prisma: bool = True,
    store_results: bool = True,
) -> QualityAssessmentResult:
```

**Use Cases**:
- Re-run only specific assessments after prompt updates
- Skip expensive assessments for large batches
- Performance optimization

**Action Items**:
1. Add boolean flags to assess_batch() and _assess_single()
2. Update _assess_single() to conditionally run assessments
3. Update tests to cover partial assessment scenarios
4. Document configuration options

## Non-Critical Issues

### 4. Abstract Truncation (Rule 14 Warning)

**Lines 433-435, 487-489, 523-525**: Abstract truncation with fixed MAX_TEXT_LENGTH constants.

```python
text = document.get("abstract", "")
if len(text) > MAX_TEXT_LENGTH_STUDY_ASSESSMENT:
    text = text[:MAX_TEXT_LENGTH_STUDY_ASSESSMENT]
    logger.debug(f"Truncated abstract...")
```

**Issue**: Violates "no truncation" rule (Rule 14). While logged, not configurable.

**Recommendation**: Make truncation configurable via SystematicReviewConfig:
```python
config = {
    "quality_assessment": {
        "max_text_lengths": {
            "study_assessment": 12000,
            "pico": 8000,
            "prisma": 15000,
        },
        "truncate_abstracts": True,  # Allow disabling
    }
}
```

### 5. Missing Documentation (Rule 12 Failure)

**Required**:
- `doc/users/quality_assessment_guide.md` - End-user guide
- `doc/developers/quality_assessment_system.md` - Technical documentation
- `doc/llm/quality_assessment.md` - AI assistant context

### 6. Reusable Function Opportunity (Rule 11 Warning)

**Lines 600-621**: _paper_to_document() converts PaperData to document dict.

**Recommendation**: Extract to shared utility module `src/bmlibrarian/agents/systematic_review/utils.py`:
```python
def paper_to_document(paper: PaperData) -> Dict[str, Any]:
    """Convert PaperData to document dict for agents."""
    return {...}
```

Benefits:
- Reusable across planner, executor, filters, scorer, quality modules
- Consistent document format
- Single source of truth for field mapping

### 7. No Interactive Error Handling

**Current**: Errors logged and workflow continues with None values.

**Required**: Interactive prompts when errors would abort workflow:
- Agent failure (LLM timeout, parsing error)
- Applicability rejection (study type mismatch)
- Database storage failure

**User Options**: Skip paper, retry, abort workflow, continue without assessment

**Action Items**:
1. Add error_handler callback parameter
2. Define ErrorHandlerCallback protocol
3. Implement user prompt UI (Phase 5)
4. Support non-interactive mode with configured fallback

## Positive Aspects

✓ **Lazy Loading**: All agents lazy-loaded for performance
✓ **Error Handling**: Comprehensive try/except blocks with graceful degradation
✓ **Progress Callbacks**: Support for UI integration
✓ **Batch Processing**: Efficient processing with progress tracking
✓ **Statistics**: Detailed assessment statistics generation
✓ **Type Safety**: All parameters properly typed
✓ **Comprehensive Tests**: 747 lines of tests with mocking
✓ **Module Structure**: Clean separation of concerns

## Test Coverage Analysis

**Test File**: `tests/test_systematic_review_quality.py` (747 lines)

**Covered Scenarios**:
- ✓ QualityAssessor initialization
- ✓ Conditional PICO execution logic (11 test cases)
- ✓ Conditional PRISMA execution logic (8 test cases)
- ✓ Single paper assessment
- ✓ Batch assessment with progress tracking
- ✓ Error handling and graceful degradation
- ✓ Assessment statistics generation
- ✓ Integration with CompositeScorer
- ✓ End-to-end workflow tests

**Missing Tests** (due to new requirements):
- ✗ Partial assessment flags
- ✗ Permanent storage with versioning
- ✗ Delegated applicability (PICO/PRISMA deciding)
- ✗ Interactive error handling
- ✗ Configurable truncation

## Recommendations for Next Iteration

### High Priority (Must Fix Before Phase 5):
1. **Remove keyword-based study type logic** - Delegate to PICO/PRISMA agents
2. **Implement permanent storage** - Database schema + _store_assessment()
3. **Add partial assessment support** - Boolean flags for which tools to run

### Medium Priority (Fix During Phase 5):
4. **Add interactive error handling** - User prompts for workflow-blocking errors
5. **Write user/developer documentation** - Complete doc/users and doc/developers guides
6. **Make truncation configurable** - Add config options for max_text_lengths

### Low Priority (Post-Phase 5):
7. **Extract _paper_to_document to utils** - Shared utility for all modules
8. **Expand test coverage** - Tests for new features

## Database Schema Proposal

```sql
-- systematic_review.quality_assessments table
CREATE TABLE IF NOT EXISTS systematic_review.quality_assessments (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES document(id),
    assessment_type TEXT NOT NULL,  -- 'study', 'weight', 'pico', 'prisma'
    assessment_version TEXT NOT NULL,  -- Version identifier for schema changes

    -- Assessment data (JSONB for flexibility)
    assessment_data JSONB NOT NULL,

    -- Metadata for reproducibility
    model_name TEXT NOT NULL,
    model_parameters JSONB NOT NULL,  -- {temperature, top_p, etc.}
    prompt_hash TEXT,  -- SHA256 hash of prompt template
    agent_version TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Indexes
    UNIQUE(document_id, assessment_type, assessment_version, model_name, prompt_hash)
);

CREATE INDEX idx_qa_document_id ON systematic_review.quality_assessments(document_id);
CREATE INDEX idx_qa_type ON systematic_review.quality_assessments(assessment_type);
CREATE INDEX idx_qa_created_at ON systematic_review.quality_assessments(created_at);
```

## Quality Threshold Evolution Strategy

Per user feedback, quality thresholds will evolve during testing:

1. **Initial Phase**: Conservative thresholds based on literature review standards
2. **Testing Phase**: Benchmark against known systematic reviews (Cochrane, PROSPERO)
3. **Validation Phase**: Adjust thresholds to achieve target recall (≥80%) and precision (≥60%)
4. **Production Phase**: Document threshold rationale for reproducibility

**Configuration**:
```json
{
  "systematic_review": {
    "quality_thresholds": {
      "relevance_score_min": 2.5,
      "study_quality_min": 5.0,
      "composite_score_min": 4.0,
      "confidence_min": 0.5,
      "rationale": "Conservative initial thresholds for high precision"
    }
  }
}
```

## Conclusion

Phase 4 delivers a solid foundation for quality assessment orchestration, but requires critical revisions before Phase 5. The keyword-based study type determination must be replaced with LLM-based applicability assessment delegated to PICO/PRISMA agents. Permanent storage with versioning is essential for reproducibility and longitudinal analysis.

**Next Steps**:
1. Implement database schema for assessment storage
2. Remove keyword-based applicability logic
3. Add partial assessment flags
4. Expand test coverage for new features
5. Write user/developer documentation

**Estimated Effort**: 4-6 hours for critical revisions, 2-3 hours for documentation

**Recommendation**: Address critical issues (1-3) before proceeding to Phase 5 reporting.
