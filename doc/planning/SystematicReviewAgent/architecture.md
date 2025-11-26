# SystematicReviewAgent Architecture

## Design Philosophy

The SystematicReviewAgent follows a **hierarchical planning architecture** that combines:

1. **High-level LLM reasoning** for strategic decisions
2. **Structured execution** for reliable tool invocation
3. **Comprehensive documentation** for auditability

This approach provides the flexibility of agentic reasoning while maintaining the predictability required for scientific workflows.

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SystematicReviewAgent                              │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         Core Components                              │   │
│  │                                                                      │   │
│  │   ┌─────────────┐   ┌──────────────┐   ┌────────────────────────┐  │   │
│  │   │  Planner    │   │   Executor   │   │     Documenter         │  │   │
│  │   │             │   │              │   │                        │  │   │
│  │   │ - Strategy  │──▶│ - Run tools  │──▶│ - Log steps            │  │   │
│  │   │ - Reasoning │   │ - Handle err │   │ - Track decisions      │  │   │
│  │   │ - Iteration │   │ - Aggregate  │   │ - Generate reports     │  │   │
│  │   └─────────────┘   └──────────────┘   └────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        State Manager                                 │   │
│  │                                                                      │   │
│  │   ┌─────────────┐   ┌──────────────┐   ┌────────────────────────┐  │   │
│  │   │ SearchState │   │ PaperResults │   │    ProcessHistory      │  │   │
│  │   │             │   │              │   │                        │  │   │
│  │   │ - Queries   │   │ - Papers[]   │   │ - Steps[]              │  │   │
│  │   │ - Results   │   │ - Scores     │   │ - Checkpoints[]        │  │   │
│  │   │ - Filters   │   │ - Decisions  │   │ - Metrics              │  │   │
│  │   └─────────────┘   └──────────────┘   └────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         Tool Registry                                │   │
│  │                                                                      │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐ │   │
│  │  │ SearchTools  │ │ ScoringTools │ │ QualityTools │ │ ExportTools│ │   │
│  │  │              │ │              │ │              │ │            │ │   │
│  │  │ -Semantic    │ │ -DocScoring  │ │ -StudyAssess │ │ -JSON      │ │   │
│  │  │ -Keyword     │ │ -Citation    │ │ -PaperWeight │ │ -Markdown  │ │   │
│  │  │ -QueryGen    │ │ -Relevance   │ │ -PICO        │ │ -CSV       │ │   │
│  │  │ -HyDE        │ │              │ │ -PRISMA2020  │ │            │ │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Planner

The Planner component handles strategic reasoning using LLM capabilities.

**Responsibilities:**
- Analyze research question and criteria
- Generate diverse search strategies
- Decide when to iterate vs. finalize
- Reason about inclusion/exclusion edge cases

**Key Methods:**
```python
class Planner:
    def generate_search_plan(
        self,
        research_question: str,
        purpose: str,
        inclusion_criteria: List[str],
        exclusion_criteria: List[str],
    ) -> SearchPlan:
        """Generate a comprehensive search plan."""

    def should_iterate(
        self,
        current_results: SearchResults,
        target_count: int,
    ) -> Tuple[bool, Optional[str]]:
        """Decide if more search iterations are needed."""

    def evaluate_borderline_paper(
        self,
        paper: PaperData,
        criteria: SearchCriteria,
    ) -> InclusionDecision:
        """LLM-based evaluation for edge cases."""
```

**Design Notes:**
- Uses a lower temperature (0.3) for consistent planning
- Generates multiple query variations (semantic, keyword, Boolean)
- Incorporates domain knowledge for medical/biomedical terms

### 2. Executor

The Executor handles tool invocation and result aggregation.

**Responsibilities:**
- Invoke tools with proper error handling
- Retry failed operations with backoff
- Aggregate and deduplicate results
- Track progress through workflow stages

**Key Methods:**
```python
class Executor:
    def execute_search_plan(
        self,
        plan: SearchPlan,
        progress_callback: Optional[Callable] = None,
    ) -> SearchResults:
        """Execute all queries in the search plan."""

    def score_papers(
        self,
        papers: List[PaperData],
        criteria: SearchCriteria,
        progress_callback: Optional[Callable] = None,
    ) -> List[ScoredPaper]:
        """Score papers for relevance and inclusion."""

    def assess_quality(
        self,
        papers: List[ScoredPaper],
        progress_callback: Optional[Callable] = None,
    ) -> List[AssessedPaper]:
        """Run quality assessments on papers."""
```

**Design Notes:**
- Uses batch processing for efficiency
- Implements circuit breaker pattern for external calls
- Supports progress callbacks for UI integration

### 3. Documenter

The Documenter maintains the complete audit trail.

**Responsibilities:**
- Log every decision with rationale
- Track tool invocations and outcomes
- Generate reproducible process reports
- Support debugging and validation

**Key Methods:**
```python
class Documenter:
    def log_step(
        self,
        action: str,
        tool: Optional[str],
        input_summary: str,
        output_summary: str,
        decision_rationale: str,
        metrics: Dict[str, Any],
    ) -> ProcessStep:
        """Log a single workflow step."""

    def log_checkpoint(
        self,
        checkpoint_type: str,
        state_snapshot: Dict,
        user_decision: Optional[str] = None,
    ) -> None:
        """Log a checkpoint with state."""

    def generate_report(
        self,
        format: str = "json",
    ) -> str:
        """Generate the final report."""
```

**Design Notes:**
- All logging is synchronous (audit trail integrity)
- Supports multiple output formats (JSON, Markdown, CSV)
- Includes timing information for performance analysis

## State Management

### SearchState

Tracks the current state of the search process:

```python
@dataclass
class SearchState:
    """Current state of the search workflow."""

    # Configuration
    criteria: SearchCriteria
    scoring_weights: Dict[str, float]

    # Query state
    planned_queries: List[PlannedQuery]
    executed_queries: List[ExecutedQuery]
    current_iteration: int = 0
    max_iterations: int = 3

    # Result state
    all_document_ids: Set[int]
    documents_by_query: Dict[str, List[int]]

    # Filter state
    passed_initial_filter: Set[int]
    excluded_at_filter: Dict[int, str]  # doc_id -> reason

    # Status
    phase: WorkflowPhase
    is_complete: bool = False
```

### PaperResults

Holds the current paper evaluations:

```python
@dataclass
class PaperResults:
    """Collection of paper results at various stages."""

    # All papers considered
    all_papers: Dict[int, PaperData]

    # Scoring results
    relevance_scores: Dict[int, float]
    inclusion_decisions: Dict[int, InclusionDecision]

    # Quality assessments (only for included papers)
    study_assessments: Dict[int, StudyAssessment]
    paper_weights: Dict[int, PaperWeightResult]
    pico_extractions: Dict[int, PICOResult]
    prisma_assessments: Dict[int, PRISMA2020Result]

    # Final rankings
    composite_scores: Dict[int, float]
    final_rankings: List[RankedPaper]
```

### ProcessHistory

Records the complete execution history:

```python
@dataclass
class ProcessHistory:
    """Complete process execution history."""

    # Timing
    started_at: datetime
    completed_at: Optional[datetime]

    # Steps
    steps: List[ProcessStep]

    # Checkpoints (for resumability)
    checkpoints: List[Checkpoint]

    # Aggregated metrics
    total_papers_considered: int = 0
    total_llm_calls: int = 0
    total_tokens_used: int = 0
```

## Tool Integration

### Search Tools

The agent uses multiple search strategies:

| Tool | Description | When Used |
|------|-------------|-----------|
| `SemanticQueryAgent.search_database()` | Embedding-based similarity search | Primary search method |
| `QueryAgent.generate_query()` | NL to PostgreSQL conversion | Structured queries |
| `SearchCoordinator.search_hybrid()` | Combined semantic + keyword | Factual queries |
| `HyDE` generation | Hypothetical document embeddings | Finding contradictory evidence |

**Search Strategy Generation:**
```python
def generate_search_strategies(
    research_question: str,
    inclusion_criteria: List[str],
    target_study_types: List[str],
) -> List[PlannedQuery]:
    """
    Generate diverse search queries to maximize coverage.

    Strategies:
    1. Direct semantic search on research question
    2. PICO-decomposed queries (if applicable)
    3. Keyword expansion from MeSH/UMLS
    4. Inclusion criteria as separate queries
    5. Study type filters
    """
```

### Scoring Tools

| Tool | Purpose | Output |
|------|---------|--------|
| `DocumentScoringAgent` | Relevance to research question | 1-5 score with rationale |
| `CitationFinderAgent` | Extract supporting passages | Citation objects |
| Inclusion/Exclusion evaluator | Criteria matching | Boolean + rationale |

**Multi-stage Scoring:**
```
Stage 1: Fast Relevance Filter
├── Semantic similarity > 0.3
├── Keywords match inclusion criteria
└── Passes basic exclusion heuristics

Stage 2: LLM Relevance Scoring
├── Full abstract evaluation
├── Explicit inclusion criteria check
└── Relevance score 1-5

Stage 3: Inclusion Decision
├── Meets all inclusion criteria?
├── Violates any exclusion criteria?
└── Borderline cases to LLM
```

### Quality Assessment Tools

| Tool | Purpose | When Used |
|------|---------|-----------|
| `StudyAssessmentAgent` | Study design, bias, confidence | All included papers |
| `PaperWeightAssessmentAgent` | Multi-dimensional evidential weight | All included papers |
| `PICOAgent` | PICO component extraction | Clinical/intervention studies |
| `PRISMA2020Agent` | PRISMA checklist compliance | Systematic reviews only |

**Conditional Quality Assessment:**
```python
def assess_paper_quality(paper: ScoredPaper) -> AssessedPaper:
    """
    Run appropriate quality assessments based on study type.
    """
    # Always run
    study_assessment = study_assessment_agent.assess_study(paper)
    paper_weight = paper_weight_agent.assess_paper(paper.document_id)

    # Conditional on study type
    pico = None
    if study_assessment.study_type in PICO_APPLICABLE_TYPES:
        pico = pico_agent.extract_pico(paper)

    prisma = None
    if study_assessment.study_type in ["systematic_review", "meta_analysis"]:
        prisma = prisma_agent.assess(paper)

    return AssessedPaper(
        base=paper,
        study_assessment=study_assessment,
        paper_weight=paper_weight,
        pico=pico,
        prisma=prisma,
    )
```

## Workflow Phases

```python
class WorkflowPhase(Enum):
    """Workflow phases for state tracking."""

    INIT = "init"
    PLANNING = "planning"
    CHECKPOINT_STRATEGY = "checkpoint_strategy"
    SEARCHING = "searching"
    CHECKPOINT_RESULTS = "checkpoint_results"
    FILTERING = "filtering"
    SCORING = "scoring"
    CHECKPOINT_QUALITY = "checkpoint_quality"
    ASSESSING = "assessing"
    RANKING = "ranking"
    REPORTING = "reporting"
    COMPLETE = "complete"
    ERROR = "error"
```

### Phase Transitions

```
INIT ──────────────▶ PLANNING
                          │
                          ▼
              ┌─── CHECKPOINT_STRATEGY ◀──┐
              │           │               │
              │           ▼               │
              │      SEARCHING ───────────┘
              │           │         (iterate if needed)
              │           ▼
              │   CHECKPOINT_RESULTS
              │           │
              │           ▼
              │      FILTERING
              │           │
              │           ▼
              │       SCORING
              │           │
              │           ▼
              │   CHECKPOINT_QUALITY
              │           │
              │           ▼
              │      ASSESSING
              │           │
              │           ▼
              │       RANKING
              │           │
              │           ▼
              └─────▶ REPORTING
                          │
                          ▼
                      COMPLETE
```

## Composite Score Calculation

The final ranking uses a weighted composite score:

```python
def calculate_composite_score(
    paper: AssessedPaper,
    weights: Dict[str, float],
) -> float:
    """
    Calculate weighted composite score.

    Default weights (user-configurable):
    - relevance: 0.30
    - study_quality: 0.25
    - methodological_rigor: 0.20
    - sample_size: 0.10
    - recency: 0.10
    - replication_status: 0.05

    PRISMA compliance adds bonus for systematic reviews.
    """
    score = 0.0

    # Relevance (normalized to 0-10)
    score += (paper.relevance_score / 5.0) * 10 * weights["relevance"]

    # Study quality from StudyAssessmentAgent
    score += paper.study_assessment.quality_score * weights["study_quality"]

    # Methodological rigor from PaperWeightAgent
    score += paper.paper_weight.methodological_quality.score * weights["methodological_rigor"]

    # Sample size (log-scaled)
    sample_score = calculate_sample_size_score(paper.paper_weight.sample_size_n)
    score += sample_score * weights["sample_size"]

    # Recency (decay function from publication date)
    recency_score = calculate_recency_score(paper.year)
    score += recency_score * weights["recency"]

    # Replication status
    score += paper.paper_weight.replication_status.score * weights["replication_status"]

    # PRISMA bonus for systematic reviews
    if paper.prisma and paper.prisma.is_applicable:
        compliance_rate = paper.prisma.items_met / paper.prisma.items_applicable
        score += compliance_rate * 1.0  # Up to 1 point bonus

    return score
```

## Error Handling Strategy

### Graceful Degradation

```python
class ErrorStrategy(Enum):
    """How to handle tool failures."""

    FAIL_FAST = "fail_fast"       # Stop on first error
    SKIP_PAPER = "skip_paper"     # Skip failed paper, continue
    RETRY_LATER = "retry_later"   # Queue for retry
    PARTIAL_RESULT = "partial"    # Accept partial assessment
```

### Error Recovery

```python
def handle_tool_error(
    tool: str,
    paper_id: int,
    error: Exception,
    strategy: ErrorStrategy = ErrorStrategy.SKIP_PAPER,
) -> None:
    """
    Handle tool execution errors.

    1. Log the error with full context
    2. Mark paper with error status
    3. Continue or halt based on strategy
    4. Add to error_papers in final report
    """
```

## Configuration

```json
{
  "systematic_review": {
    "planner": {
      "model": "gpt-oss:20b",
      "temperature": 0.3,
      "max_query_variations": 5
    },
    "search": {
      "max_iterations": 3,
      "min_results_to_proceed": 10,
      "semantic_threshold": 0.3,
      "deduplication_strategy": "by_doi_then_title"
    },
    "scoring": {
      "relevance_threshold": 2.5,
      "batch_size": 50,
      "parallel_workers": 4
    },
    "quality": {
      "run_pico_for_interventions": true,
      "run_prisma_for_reviews": true,
      "quality_gate_threshold": 4.0
    },
    "weights": {
      "relevance": 0.30,
      "study_quality": 0.25,
      "methodological_rigor": 0.20,
      "sample_size": 0.10,
      "recency": 0.10,
      "replication_status": 0.05
    },
    "checkpoints": {
      "enabled": true,
      "auto_approve_in_batch_mode": false
    }
  }
}
```

## Integration with Existing Agents

The SystematicReviewAgent inherits from `BaseAgent` and follows established patterns:

```python
class SystematicReviewAgent(BaseAgent):
    """
    AI-assisted systematic literature review agent.

    Coordinates search, scoring, and quality assessment tools
    to produce ranked paper lists with full audit trails.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional["AgentOrchestrator"] = None,
        show_model_info: bool = True,
    ):
        # Load configuration
        self.config = self._load_config()

        # Get model from config if not provided
        if model is None:
            model = get_model('systematic_review_agent')
        if host is None:
            host = get_ollama_host()

        super().__init__(
            model=model,
            host=host,
            temperature=self.config.get('temperature', 0.3),
            top_p=self.config.get('top_p', 0.9),
            callback=callback,
            orchestrator=orchestrator,
            show_model_info=show_model_info,
        )

        # Initialize components
        self.planner = Planner(config=self.config['planner'])
        self.executor = Executor(config=self.config)
        self.documenter = Documenter()

        # Initialize child agents
        self._init_child_agents()

    def get_agent_type(self) -> str:
        return "SystematicReviewAgent"
```

## Performance Considerations

### Batch Processing
- Score papers in batches of 50 to avoid LLM context overflow
- Use parallel processing for independent assessments
- Cache quality assessments to avoid recomputation

### Caching Strategy
- Cache search results by query hash
- Cache quality assessments in database (PaperWeight pattern)
- Version cache entries for invalidation on algorithm updates

### Resource Management
- Monitor LLM token usage and report in metrics
- Implement backpressure for rate-limited external services
- Support incremental progress saving for long-running reviews
