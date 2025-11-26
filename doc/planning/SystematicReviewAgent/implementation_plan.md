# SystematicReviewAgent Implementation Plan

This document outlines the phased implementation approach for the SystematicReviewAgent.

## Implementation Principles

1. **Incremental Development**: Each phase produces working, testable code
2. **Integration First**: Leverage existing agents from the start
3. **Test-Driven**: Write tests alongside implementation
4. **Documentation as Code**: Update docs with each phase

## Phase Overview

| Phase | Focus | Key Deliverables |
|-------|-------|------------------|
| 1 | Foundation | Data models, agent skeleton, documenter |
| 2 | Search Strategy | Planner, query generation, search execution |
| 3 | Filtering & Scoring | Inclusion/exclusion logic, relevance scoring |
| 4 | Quality Assessment | Integration with quality tools, composite scoring |
| 5 | Output & Reporting | Report generation, CLI, export formats |
| 6 | Validation & Polish | Testing, benchmarking, refinement |

---

## Phase 1: Foundation

**Goal**: Establish core infrastructure and data models

### 1.1 Create Module Structure

```
src/bmlibrarian/agents/systematic_review/
├── __init__.py              # Module exports
├── data_models.py           # All dataclasses from data_models.md
├── agent.py                 # SystematicReviewAgent main class
├── planner.py               # Search strategy planning
├── executor.py              # Tool execution
├── documenter.py            # Audit trail logging
├── filters.py               # Inclusion/exclusion logic
├── scorer.py                # Relevance and composite scoring
├── quality.py               # Quality assessment orchestration
├── reporter.py              # Report generation
└── config.py                # Configuration management
```

### 1.2 Implement Data Models

**File**: `data_models.py`

Implement all dataclasses from [data_models.md](data_models.md):
- `SearchCriteria`, `ScoringWeights`
- `PlannedQuery`, `SearchPlan`, `ExecutedQuery`
- `PaperData`, `InclusionDecision`, `ScoredPaper`, `AssessedPaper`
- `ProcessStep`, `Checkpoint`
- `SystematicReviewResult`

**Acceptance Criteria**:
- All dataclasses have `to_dict()` methods
- Validation functions work correctly
- JSON serialization round-trips without data loss

### 1.3 Implement Agent Skeleton

**File**: `agent.py`

```python
class SystematicReviewAgent(BaseAgent):
    """Skeleton with configuration and component initialization."""

    def __init__(self, ...):
        # Load config
        # Initialize components (placeholders)
        # Initialize child agents

    def get_agent_type(self) -> str:
        return "SystematicReviewAgent"

    def run_review(
        self,
        criteria: SearchCriteria,
        weights: ScoringWeights,
        interactive: bool = True,
    ) -> SystematicReviewResult:
        """Main entry point - stub for now."""
        raise NotImplementedError("Implemented in Phase 2-5")
```

### 1.4 Implement Documenter

**File**: `documenter.py`

The Documenter is independent and can be fully implemented first:

```python
class Documenter:
    """Audit trail logging component."""

    def __init__(self):
        self.steps: List[ProcessStep] = []
        self.checkpoints: List[Checkpoint] = []
        self._step_counter = 0

    def log_step(
        self,
        action: str,
        tool: Optional[str],
        input_summary: str,
        output_summary: str,
        decision_rationale: str,
        metrics: Dict[str, Any],
    ) -> ProcessStep:
        """Log a workflow step."""

    def log_checkpoint(
        self,
        checkpoint_type: str,
        phase: str,
        state_snapshot: Dict,
        user_decision: Optional[str] = None,
    ) -> Checkpoint:
        """Log a checkpoint."""

    def generate_process_log(self) -> List[Dict]:
        """Generate serializable process log."""

    def export_markdown(self) -> str:
        """Export audit trail as Markdown."""
```

### 1.5 Write Initial Tests

**File**: `tests/test_systematic_review_data_models.py`

```python
def test_search_criteria_validation():
    """Test SearchCriteria validation."""

def test_scoring_weights_sum_to_one():
    """Test ScoringWeights validation."""

def test_paper_data_serialization():
    """Test PaperData JSON round-trip."""

def test_documenter_step_logging():
    """Test Documenter logs steps correctly."""
```

### Phase 1 Deliverables

| Deliverable | File(s) |
|-------------|---------|
| Data models | `src/bmlibrarian/agents/systematic_review/data_models.py` |
| Agent skeleton | `src/bmlibrarian/agents/systematic_review/agent.py` |
| Documenter | `src/bmlibrarian/agents/systematic_review/documenter.py` |
| Unit tests | `tests/test_systematic_review_data_models.py` |
| Module init | `src/bmlibrarian/agents/systematic_review/__init__.py` |

---

## Phase 2: Search Strategy

**Goal**: Implement search planning and execution

### 2.1 Implement Planner

**File**: `planner.py`

```python
class Planner:
    """LLM-based search strategy planning."""

    def __init__(self, model: str, host: str, config: Dict):
        self.model = model
        self.host = host
        self.config = config

    def generate_search_plan(
        self,
        criteria: SearchCriteria,
    ) -> SearchPlan:
        """
        Generate diverse search queries.

        Strategy:
        1. Parse research question for key concepts
        2. Generate semantic query variations
        3. Extract keywords for keyword search
        4. Build Boolean queries for precision
        5. Consider PICO decomposition if applicable
        """

    def _generate_query_variations(
        self,
        research_question: str,
        num_variations: int = 3,
    ) -> List[str]:
        """Use LLM to generate query variations."""

    def _extract_mesh_terms(
        self,
        text: str,
    ) -> List[str]:
        """Extract relevant MeSH terms using thesaurus."""

    def should_iterate(
        self,
        current_results: int,
        target_minimum: int,
        iteration: int,
    ) -> Tuple[bool, str]:
        """Decide if more search iterations are needed."""
```

### 2.2 Implement Search Executor

**File**: `executor.py`

```python
class SearchExecutor:
    """Executes search queries and aggregates results."""

    def __init__(self, config: Dict):
        self.config = config
        self.semantic_agent = SemanticQueryAgent()
        self.query_agent = QueryAgent()

    def execute_plan(
        self,
        plan: SearchPlan,
        progress_callback: Optional[Callable] = None,
    ) -> Tuple[List[ExecutedQuery], Set[int]]:
        """
        Execute all queries in the plan.

        Returns:
            Tuple of (executed_queries, unique_document_ids)
        """

    def execute_semantic_query(
        self,
        query: PlannedQuery,
    ) -> ExecutedQuery:
        """Execute a semantic search query."""

    def execute_keyword_query(
        self,
        query: PlannedQuery,
    ) -> ExecutedQuery:
        """Execute a keyword/full-text search query."""

    def deduplicate_results(
        self,
        document_ids_by_query: Dict[str, List[int]],
    ) -> Set[int]:
        """Merge and deduplicate document IDs."""
```

### 2.3 Integration with Existing Agents

Connect to existing search infrastructure:
- `SemanticQueryAgent` for embedding-based search
- `QueryAgent` for SQL generation
- `SearchCoordinator` patterns for multi-strategy search

### 2.4 Add Search Tests

**File**: `tests/test_systematic_review_search.py`

```python
def test_planner_generates_diverse_queries():
    """Test that planner generates multiple query types."""

def test_executor_runs_semantic_search():
    """Test semantic search execution."""

def test_deduplication_removes_duplicates():
    """Test result deduplication."""

def test_iteration_decision():
    """Test should_iterate logic."""
```

### Phase 2 Deliverables

| Deliverable | File(s) |
|-------------|---------|
| Planner component | `src/bmlibrarian/agents/systematic_review/planner.py` |
| Search executor | `src/bmlibrarian/agents/systematic_review/executor.py` |
| Search tests | `tests/test_systematic_review_search.py` |
| Integration test | `tests/test_systematic_review_integration.py` |

---

## Phase 3: Filtering & Scoring

**Goal**: Implement paper filtering and relevance scoring

### 3.1 Implement Initial Filter

**File**: `filters.py`

```python
class InitialFilter:
    """Fast heuristic-based filtering."""

    def __init__(self, criteria: SearchCriteria):
        self.criteria = criteria

    def filter_batch(
        self,
        papers: List[PaperData],
    ) -> Tuple[List[PaperData], List[Tuple[PaperData, str]]]:
        """
        Fast filter on papers.

        Returns:
            Tuple of (passed_papers, rejected_with_reasons)
        """

    def _check_date_range(self, paper: PaperData) -> Optional[str]:
        """Check if paper is within date range."""

    def _check_study_type_keywords(self, paper: PaperData) -> Optional[str]:
        """Quick keyword check for study type."""

    def _check_exclusion_keywords(self, paper: PaperData) -> Optional[str]:
        """Check for obvious exclusion keyword matches."""
```

### 3.2 Implement Inclusion Evaluator

**File**: `filters.py` (continued)

```python
class InclusionEvaluator:
    """LLM-based inclusion/exclusion evaluation."""

    def __init__(self, model: str, host: str, criteria: SearchCriteria):
        self.model = model
        self.host = host
        self.criteria = criteria

    def evaluate(
        self,
        paper: PaperData,
        relevance_score: float,
    ) -> InclusionDecision:
        """
        Evaluate paper against inclusion/exclusion criteria.

        Uses LLM to assess each criterion explicitly.
        """

    def _build_evaluation_prompt(
        self,
        paper: PaperData,
    ) -> str:
        """Build LLM prompt for evaluation."""

    def _parse_evaluation_response(
        self,
        response: str,
    ) -> InclusionDecision:
        """Parse LLM JSON response."""
```

### 3.3 Implement Relevance Scorer

**File**: `scorer.py`

```python
class RelevanceScorer:
    """Wrapper around DocumentScoringAgent with batch support."""

    def __init__(self, config: Dict):
        self.config = config
        self.scoring_agent = DocumentScoringAgent()

    def score_batch(
        self,
        papers: List[PaperData],
        research_question: str,
        progress_callback: Optional[Callable] = None,
    ) -> List[ScoredPaper]:
        """
        Score papers for relevance.

        Uses DocumentScoringAgent internally.
        """

    def apply_relevance_threshold(
        self,
        scored_papers: List[ScoredPaper],
        threshold: float = 2.5,
    ) -> Tuple[List[ScoredPaper], List[ScoredPaper]]:
        """Split by relevance threshold."""
```

### 3.4 Add Filtering Tests

**File**: `tests/test_systematic_review_filtering.py`

```python
def test_initial_filter_date_range():
    """Test date range filtering."""

def test_initial_filter_exclusion_keywords():
    """Test exclusion keyword matching."""

def test_inclusion_evaluator():
    """Test LLM inclusion evaluation."""

def test_relevance_scoring_batch():
    """Test batch relevance scoring."""
```

### Phase 3 Deliverables

| Deliverable | File(s) |
|-------------|---------|
| Filter components | `src/bmlibrarian/agents/systematic_review/filters.py` |
| Scorer component | `src/bmlibrarian/agents/systematic_review/scorer.py` |
| Filter tests | `tests/test_systematic_review_filtering.py` |

---

## Phase 4: Quality Assessment

**Goal**: Integrate quality assessment tools and compute composite scores

**Status**: ✓ COMPLETED (with refinements needed)

### 4.1 Implement Quality Orchestrator

**File**: `quality.py`

**Implementation Notes**:
- ✓ Lazy loading of all assessment agents (performance)
- ✓ Batch processing with progress callbacks
- ✓ Error handling with graceful degradation
- ✓ Assessment statistics generation
- **REVISION NEEDED**: Study type determination should be delegated to PICO/PRISMA agents
- **REVISION NEEDED**: Add permanent storage with versioning (model, params, prompt metadata)
- **REVISION NEEDED**: Support partial assessments (configurable which tools to run)
- **REVISION NEEDED**: User prompts on workflow-blocking errors

```python
class QualityAssessor:
    """Orchestrates quality assessment tools."""

    def __init__(self, config: Dict):
        self.config = config
        # Lazy-loaded agents
        self._study_agent = None
        self._weight_agent = None
        self._pico_agent = None
        self._prisma_agent = None

    def assess_batch(
        self,
        papers: List[ScoredPaper],
        progress_callback: Optional[Callable] = None,
        run_pico: bool = True,  # NEW: Support partial assessments
        run_prisma: bool = True,  # NEW: Support partial assessments
        store_results: bool = True,  # NEW: Permanent storage
    ) -> QualityAssessmentResult:
        """
        Run quality assessments on all papers.

        PICO/PRISMA agents determine their own applicability.
        """

    def _assess_single(
        self,
        paper: ScoredPaper,
        run_pico: bool = True,
        run_prisma: bool = True,
    ) -> AssessedPaper:
        """Assess a single paper."""

    # REMOVED: _should_run_pico() - delegated to PICOAgent
    # REMOVED: _should_run_prisma() - delegated to PRISMA2020Agent

    def _store_assessment(
        self,
        paper: AssessedPaper,
        metadata: Dict[str, Any],  # NEW: Model, params, prompt info
    ) -> None:
        """Store assessment with versioning."""
```

### 4.1.1 Design Changes from User Feedback

**Study Type Determination** (CRITICAL REVISION):
- Original design: QualityAssessor uses keyword-based logic to decide if PICO/PRISMA apply
- **Revised design**: PICO/PRISMA agents assess their own applicability using LLM
- **Rationale**: Keyword-based extraction has proven unreliable in experiments
- **Implementation**:
  - PICOAgent.extract_pico() returns error with rationale if study type not applicable
  - PRISMA2020Agent.assess_document() already has suitability assessment
  - PICO widely applicable (population + observation usually present, intervention/control can be N/A)
  - QualityAssessor handles errors gracefully (logs, continues with other assessments)

**Permanent Storage with Versioning** (NEW REQUIREMENT):
- Quality assessments must be permanently stored, not just cached
- Each assessment stored with metadata:
  - Model name and version
  - Model parameters (temperature, top_p, etc.)
  - Prompt version/hash
  - Assessment timestamp
  - Agent version
- Supports reproducibility and longitudinal analysis
- Database schema needs assessment_history table

**Partial Assessment Support** (NEW REQUIREMENT):
- QualityAssessor should accept flags for which assessments to run
- Use cases:
  - Skip PICO for non-intervention studies
  - Skip PRISMA for non-reviews
  - Re-run only specific assessments after prompt updates
  - Performance optimization for large batches
- Configuration via method parameters or config file

**Interactive Error Handling** (NEW REQUIREMENT):
- When errors would abort the workflow, prompt user for clarification
- Error scenarios:
  - Agent failure (LLM timeout, parsing error)
  - Applicability rejection (study type mismatch)
  - Database storage failure
- User options: Skip paper, retry, abort workflow, continue without assessment
- Non-interactive mode: Use configured fallback behavior

### 4.2 Implement Composite Scorer

**File**: `scorer.py` (continued)

```python
class CompositeScorer:
    """Calculates weighted composite scores."""

    def __init__(self, weights: ScoringWeights):
        self.weights = weights

    def score(
        self,
        paper: AssessedPaper,
    ) -> float:
        """
        Calculate composite score.

        Formula uses user-defined weights.
        """

    def rank(
        self,
        papers: List[AssessedPaper],
    ) -> List[AssessedPaper]:
        """Sort papers by composite score."""

    def apply_quality_gate(
        self,
        papers: List[AssessedPaper],
        threshold: float = 4.0,
    ) -> Tuple[List[AssessedPaper], List[AssessedPaper]]:
        """Filter by quality threshold."""
```

### 4.3 Add Quality Tests

**File**: `tests/test_systematic_review_quality.py`

```python
def test_quality_assessor_runs_all_tools():
    """Test that all relevant tools are invoked."""

def test_pico_conditional_execution():
    """Test PICO only runs for intervention studies."""

def test_prisma_conditional_execution():
    """Test PRISMA only runs for systematic reviews."""

def test_composite_score_calculation():
    """Test weighted score calculation."""

def test_quality_gate_filtering():
    """Test quality threshold filtering."""
```

**Quality Thresholds** (EVOLVING REQUIREMENT):
- Quality thresholds will be determined through testing and validation
- Initial conservative thresholds will be relaxed based on benchmark performance
- System should support easy threshold adjustment without code changes
- Document threshold rationale for reproducibility

### Phase 4 Deliverables

| Deliverable | Status | File(s) | Notes |
|-------------|--------|---------|-------|
| Quality orchestrator | ✓ Complete (needs revision) | `src/bmlibrarian/agents/systematic_review/quality.py` | Needs: storage, partial assessment, delegated applicability |
| Composite scorer | ✓ Complete | `src/bmlibrarian/agents/systematic_review/scorer.py` | Implemented in Phase 3 |
| Quality tests | ✓ Complete (needs expansion) | `tests/test_systematic_review_quality.py` | Need tests for new features |
| Module exports | ✓ Complete | `src/bmlibrarian/agents/systematic_review/__init__.py` | QualityAssessor exported |

**Remaining Work for Phase 4**:
1. Database schema for assessment storage with versioning
2. Implement _store_assessment() with metadata
3. Add partial assessment flags (run_pico, run_prisma, run_study, run_weight)
4. Remove _should_run_pico() and _should_run_prisma() logic
5. Delegate applicability to PICO/PRISMA agents (verify/modify agents)
6. Interactive error handling with user prompts
7. Update tests for new functionality
8. Configuration for quality thresholds

---

## Phase 5: Output & Reporting

**Goal**: Generate comprehensive reports and CLI interface

### 5.1 Implement Reporter

**File**: `reporter.py`

```python
class Reporter:
    """Generates output reports in multiple formats."""

    def __init__(self, documenter: Documenter):
        self.documenter = documenter

    def generate_json_report(
        self,
        result: SystematicReviewResult,
        output_path: str,
    ) -> None:
        """Generate JSON output file."""

    def generate_markdown_report(
        self,
        result: SystematicReviewResult,
        output_path: str,
    ) -> None:
        """Generate human-readable Markdown report."""

    def generate_csv_export(
        self,
        papers: List[AssessedPaper],
        output_path: str,
    ) -> None:
        """Generate CSV for spreadsheet analysis."""

    def generate_prisma_flowchart(
        self,
        statistics: ReviewStatistics,
        output_path: str,
    ) -> None:
        """Generate PRISMA flow diagram data."""
```

### 5.2 Complete Main Agent

**File**: `agent.py` (updated)

```python
class SystematicReviewAgent(BaseAgent):
    """Complete agent with all phases."""

    def run_review(
        self,
        criteria: SearchCriteria,
        weights: ScoringWeights,
        interactive: bool = True,
        output_path: Optional[str] = None,
    ) -> SystematicReviewResult:
        """
        Run complete systematic review workflow.

        Phases:
        1. Generate search plan
        2. Execute searches
        3. Filter results
        4. Score for relevance
        5. Assess quality
        6. Calculate composite scores
        7. Generate report
        """

    def _checkpoint(
        self,
        checkpoint_type: str,
        state: Dict,
        interactive: bool,
    ) -> bool:
        """
        Handle checkpoint.

        Returns True to continue, False to abort.
        """
```

### 5.3 Create CLI

**File**: `systematic_review_cli.py` (project root)

```python
"""
CLI for systematic literature review.

Usage:
    uv run python systematic_review_cli.py review criteria.json
    uv run python systematic_review_cli.py review criteria.json --output results.json
    uv run python systematic_review_cli.py review criteria.json --auto  # Non-interactive
    uv run python systematic_review_cli.py resume checkpoint.json
"""

import argparse
from bmlibrarian.agents.systematic_review import SystematicReviewAgent


def main():
    parser = argparse.ArgumentParser(description="Systematic Literature Review")
    subparsers = parser.add_subparsers(dest="command")

    # Review command
    review_parser = subparsers.add_parser("review", help="Run systematic review")
    review_parser.add_argument("criteria", help="Path to criteria JSON file")
    review_parser.add_argument("--output", "-o", help="Output file path")
    review_parser.add_argument("--auto", action="store_true", help="Non-interactive mode")
    review_parser.add_argument("--weights", help="Path to weights JSON file")

    # Resume command
    resume_parser = subparsers.add_parser("resume", help="Resume from checkpoint")
    resume_parser.add_argument("checkpoint", help="Path to checkpoint file")

    args = parser.parse_args()
    # ... implementation
```

### 5.4 Add Reporting Tests

**File**: `tests/test_systematic_review_reporting.py`

```python
def test_json_report_generation():
    """Test JSON report is valid."""

def test_markdown_report_generation():
    """Test Markdown report is readable."""

def test_csv_export():
    """Test CSV export for spreadsheets."""

def test_full_workflow_integration():
    """End-to-end test with mock data."""
```

### Phase 5 Deliverables

| Deliverable | File(s) |
|-------------|---------|
| Reporter component | `src/bmlibrarian/agents/systematic_review/reporter.py` |
| Complete agent | `src/bmlibrarian/agents/systematic_review/agent.py` |
| CLI application | `systematic_review_cli.py` |
| Reporting tests | `tests/test_systematic_review_reporting.py` |
| User documentation | `doc/users/systematic_review_guide.md` |

---

## Phase 6: Validation & Polish

**Goal**: Validate against benchmarks and refine

### 6.1 Benchmark Testing

Create benchmark suite using known systematic reviews:

```python
# tests/benchmarks/test_systematic_review_benchmark.py

def test_against_cochrane_review():
    """
    Compare results against a published Cochrane review.

    Measures:
    - Recall: What % of their included papers did we find?
    - Precision: What % of our included papers are in theirs?
    """

def test_against_pubmed_systematic_review():
    """Similar benchmark with PubMed systematic review."""
```

### 6.2 Performance Optimization

- Profile LLM call patterns
- Implement caching for repeated assessments
- Optimize batch sizes for throughput

### 6.3 Error Handling Refinement

- Improve error messages
- Add recovery strategies
- Test edge cases (empty results, network failures)

### 6.4 Documentation

Complete all documentation:

| Document | Path |
|----------|------|
| User Guide | `doc/users/systematic_review_guide.md` |
| Developer Guide | `doc/developers/systematic_review_system.md` |
| API Reference | `doc/developers/systematic_review_api.md` |
| LLM Context | `doc/llm/systematic_review.md` |

### Phase 6 Deliverables

| Deliverable | File(s) |
|-------------|---------|
| Benchmark suite | `tests/benchmarks/test_systematic_review_benchmark.py` |
| Performance tests | `tests/test_systematic_review_performance.py` |
| Complete documentation | `doc/users/`, `doc/developers/` |
| Example scripts | `examples/systematic_review_demo.py` |

---

## Dependency Map

```
Phase 1 ─────────┐
(Foundation)     │
                 ▼
Phase 2 ─────────┐
(Search)         │
                 ▼
Phase 3 ─────────┤
(Filtering)      │
                 ▼
Phase 4 ─────────┤
(Quality)        │
                 ▼
Phase 5 ─────────┤
(Reporting)      │
                 ▼
Phase 6
(Validation)
```

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LLM quality varies | Use low temperature, retry on parse failures |
| Search misses papers | Multiple query strategies, iteration support |
| Quality tools fail | Graceful degradation, partial results |
| Long processing time | Progress callbacks, checkpointing |
| Memory with large result sets | Batch processing, streaming |

## Success Metrics

| Metric | Target |
|--------|--------|
| Recall vs. gold standard | ≥ 80% |
| Precision vs. gold standard | ≥ 60% |
| Processing time (100 papers) | < 30 minutes |
| Test coverage | ≥ 85% |
| Documentation completeness | All public APIs documented |
