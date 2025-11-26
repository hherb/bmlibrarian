"""
Unit tests for SystematicReviewAgent data models and documenter.

Tests cover:
- SearchCriteria validation
- ScoringWeights validation (sum to 1.0)
- PaperData serialization round-trip
- Documenter step logging
- Checkpoint creation and retrieval
- All dataclass serialization methods
"""

import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path

from bmlibrarian.agents.systematic_review import (
    # Enums
    StudyTypeFilter,
    QueryType,
    InclusionStatus,
    ExclusionStage,
    # Input models
    SearchCriteria,
    ScoringWeights,
    # Search planning models
    PlannedQuery,
    SearchPlan,
    ExecutedQuery,
    # Paper data models
    PaperData,
    InclusionDecision,
    ScoredPaper,
    AssessedPaper,
    # Process documentation models
    ProcessStep,
    Checkpoint,
    # Output models
    ReviewStatistics,
    SystematicReviewResult,
    # Validation functions
    validate_search_criteria,
    validate_scoring_weights,
    # Documenter
    Documenter,
    StepTimer,
    # Constants
    MIN_RELEVANCE_SCORE,
    MAX_RELEVANCE_SCORE,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_criteria() -> SearchCriteria:
    """Create sample SearchCriteria for testing."""
    return SearchCriteria(
        research_question="What is the efficacy of statins for CVD prevention?",
        purpose="Systematic review for clinical guidelines",
        inclusion_criteria=[
            "Human studies",
            "Statin intervention",
            "Cardiovascular disease outcomes"
        ],
        exclusion_criteria=[
            "Animal studies",
            "Pediatric-only populations",
            "Case reports"
        ],
        target_study_types=[
            StudyTypeFilter.RCT,
            StudyTypeFilter.META_ANALYSIS,
        ],
        date_range=(2010, 2024),
        language="English",
    )


@pytest.fixture
def sample_weights() -> ScoringWeights:
    """Create sample ScoringWeights for testing."""
    return ScoringWeights(
        relevance=0.30,
        study_quality=0.25,
        methodological_rigor=0.20,
        sample_size=0.10,
        recency=0.10,
        replication_status=0.05,
    )


@pytest.fixture
def sample_paper() -> PaperData:
    """Create sample PaperData for testing."""
    return PaperData(
        document_id=12345,
        title="Efficacy of Statins in Primary Prevention of Cardiovascular Disease",
        authors=["Smith J", "Johnson A", "Williams B"],
        year=2023,
        journal="Lancet",
        abstract="Background: Statins are widely used...",
        doi="10.1000/example.doi",
        pmid="12345678",
        pmc_id="PMC1234567",
        source="pubmed",
    )


@pytest.fixture
def sample_documenter() -> Documenter:
    """Create sample Documenter for testing."""
    return Documenter(review_id="test_review_001")


# =============================================================================
# SearchCriteria Tests
# =============================================================================

class TestSearchCriteria:
    """Tests for SearchCriteria dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating SearchCriteria with minimum required fields."""
        criteria = SearchCriteria(
            research_question="Test question",
            purpose="Test purpose",
            inclusion_criteria=["Criterion 1"],
            exclusion_criteria=[],
        )
        assert criteria.research_question == "Test question"
        assert criteria.purpose == "Test purpose"
        assert len(criteria.inclusion_criteria) == 1

    def test_to_dict_serialization(self, sample_criteria: SearchCriteria) -> None:
        """Test to_dict produces valid dictionary."""
        data = sample_criteria.to_dict()

        assert data["research_question"] == sample_criteria.research_question
        assert data["purpose"] == sample_criteria.purpose
        assert data["inclusion_criteria"] == sample_criteria.inclusion_criteria
        assert data["exclusion_criteria"] == sample_criteria.exclusion_criteria
        assert data["date_range"] == [2010, 2024]
        assert data["target_study_types"] == ["rct", "meta_analysis"]

    def test_from_dict_deserialization(self, sample_criteria: SearchCriteria) -> None:
        """Test from_dict creates equivalent object."""
        data = sample_criteria.to_dict()
        restored = SearchCriteria.from_dict(data)

        assert restored.research_question == sample_criteria.research_question
        assert restored.purpose == sample_criteria.purpose
        assert restored.inclusion_criteria == sample_criteria.inclusion_criteria
        assert restored.date_range == sample_criteria.date_range

    def test_json_round_trip(self, sample_criteria: SearchCriteria) -> None:
        """Test JSON serialization round-trip."""
        json_str = json.dumps(sample_criteria.to_dict())
        data = json.loads(json_str)
        restored = SearchCriteria.from_dict(data)

        assert restored.research_question == sample_criteria.research_question

    def test_validation_empty_question(self) -> None:
        """Test validation catches empty research question."""
        criteria = SearchCriteria(
            research_question="",
            purpose="Test",
            inclusion_criteria=["Criterion"],
            exclusion_criteria=[],
        )
        errors = validate_search_criteria(criteria)
        assert len(errors) > 0
        assert any("cannot be empty" in e.lower() for e in errors)

    def test_validation_no_inclusion_criteria(self) -> None:
        """Test validation catches missing inclusion criteria."""
        criteria = SearchCriteria(
            research_question="Valid question",
            purpose="Test",
            inclusion_criteria=[],
            exclusion_criteria=[],
        )
        errors = validate_search_criteria(criteria)
        assert len(errors) > 0
        assert any("inclusion" in e.lower() for e in errors)

    def test_validation_invalid_date_range(self) -> None:
        """Test validation catches invalid date range."""
        criteria = SearchCriteria(
            research_question="Valid question",
            purpose="Test",
            inclusion_criteria=["Criterion"],
            exclusion_criteria=[],
            date_range=(2024, 2020),  # End before start
        )
        errors = validate_search_criteria(criteria)
        assert len(errors) > 0

    def test_validation_valid_criteria(self, sample_criteria: SearchCriteria) -> None:
        """Test validation passes for valid criteria."""
        errors = validate_search_criteria(sample_criteria)
        assert len(errors) == 0


# =============================================================================
# ScoringWeights Tests
# =============================================================================

class TestScoringWeights:
    """Tests for ScoringWeights dataclass."""

    def test_default_weights_sum_to_one(self) -> None:
        """Test default weights sum to 1.0."""
        weights = ScoringWeights()
        assert weights.validate()

    def test_custom_weights_sum_to_one(self, sample_weights: ScoringWeights) -> None:
        """Test custom weights that sum to 1.0 validate."""
        assert sample_weights.validate()

    def test_invalid_weights_not_sum_to_one(self) -> None:
        """Test weights not summing to 1.0 fail validation."""
        weights = ScoringWeights(
            relevance=0.5,
            study_quality=0.5,
            methodological_rigor=0.5,  # Sum = 1.5, invalid
            sample_size=0.0,
            recency=0.0,
            replication_status=0.0,
        )
        assert not weights.validate()

    def test_get_validation_errors_negative_weight(self) -> None:
        """Test negative weights produce validation errors."""
        weights = ScoringWeights(
            relevance=-0.1,  # Negative
            study_quality=0.55,
            methodological_rigor=0.25,
            sample_size=0.1,
            recency=0.1,
            replication_status=0.1,
        )
        errors = weights.get_validation_errors()
        assert len(errors) > 0
        assert any("negative" in e.lower() for e in errors)

    def test_to_dict_serialization(self, sample_weights: ScoringWeights) -> None:
        """Test to_dict produces valid dictionary."""
        data = sample_weights.to_dict()
        assert data["relevance"] == 0.30
        assert data["study_quality"] == 0.25
        assert sum(data.values()) == pytest.approx(1.0, abs=0.01)

    def test_from_dict_deserialization(self, sample_weights: ScoringWeights) -> None:
        """Test from_dict creates equivalent object."""
        data = sample_weights.to_dict()
        restored = ScoringWeights.from_dict(data)
        assert restored.relevance == sample_weights.relevance
        assert restored.validate()


# =============================================================================
# PaperData Tests
# =============================================================================

class TestPaperData:
    """Tests for PaperData dataclass."""

    def test_creation(self, sample_paper: PaperData) -> None:
        """Test creating PaperData."""
        assert sample_paper.document_id == 12345
        assert sample_paper.title.startswith("Efficacy of Statins")
        assert len(sample_paper.authors) == 3

    def test_to_dict_excludes_full_text(self, sample_paper: PaperData) -> None:
        """Test to_dict excludes full_text but includes has_full_text flag."""
        sample_paper.full_text = "This is the full text content..."
        data = sample_paper.to_dict()

        assert "full_text" not in data
        assert data["has_full_text"] is True

    def test_to_full_dict_includes_full_text(self, sample_paper: PaperData) -> None:
        """Test to_full_dict includes full_text."""
        sample_paper.full_text = "This is the full text content..."
        data = sample_paper.to_full_dict()

        assert "full_text" in data
        assert data["full_text"] == sample_paper.full_text

    def test_json_round_trip(self, sample_paper: PaperData) -> None:
        """Test JSON serialization round-trip."""
        json_str = json.dumps(sample_paper.to_dict())
        data = json.loads(json_str)
        restored = PaperData.from_dict(data)

        assert restored.document_id == sample_paper.document_id
        assert restored.title == sample_paper.title
        assert restored.doi == sample_paper.doi

    def test_from_database_row(self) -> None:
        """Test from_database_row with typical database column names."""
        row = {
            "id": 999,
            "title": "Test Paper",
            "authors": '["Author A", "Author B"]',  # JSON string
            "publication_year": 2023,
            "journal_name": "Test Journal",
            "abstract": "Test abstract",
            "doi": "10.1234/test",
            "pmid": "99999",
        }
        paper = PaperData.from_database_row(row)

        assert paper.document_id == 999
        assert paper.title == "Test Paper"
        assert paper.authors == ["Author A", "Author B"]
        assert paper.year == 2023
        assert paper.journal == "Test Journal"


# =============================================================================
# PlannedQuery and SearchPlan Tests
# =============================================================================

class TestSearchPlanning:
    """Tests for search planning models."""

    def test_planned_query_creation(self) -> None:
        """Test creating PlannedQuery."""
        query = PlannedQuery(
            query_id="q1_semantic",
            query_text="cardiovascular disease statin prevention",
            query_type=QueryType.SEMANTIC,
            purpose="Find papers about statin efficacy",
            expected_coverage="Primary intervention studies",
        )
        assert query.query_id == "q1_semantic"
        assert query.query_type == QueryType.SEMANTIC

    def test_planned_query_auto_id(self) -> None:
        """Test PlannedQuery generates ID if not provided."""
        query = PlannedQuery(
            query_id="",
            query_text="test query",
            query_type=QueryType.KEYWORD,
            purpose="Test",
            expected_coverage="Test",
        )
        assert query.query_id != ""
        assert "keyword" in query.query_id

    def test_search_plan_serialization(self) -> None:
        """Test SearchPlan serialization."""
        queries = [
            PlannedQuery(
                query_id="q1",
                query_text="query 1",
                query_type=QueryType.SEMANTIC,
                purpose="Purpose 1",
                expected_coverage="Coverage 1",
            ),
            PlannedQuery(
                query_id="q2",
                query_text="query 2",
                query_type=QueryType.KEYWORD,
                purpose="Purpose 2",
                expected_coverage="Coverage 2",
            ),
        ]
        plan = SearchPlan(
            queries=queries,
            total_estimated_yield=500,
            search_rationale="Testing search strategy",
        )

        data = plan.to_dict()
        assert len(data["queries"]) == 2
        assert data["total_estimated_yield"] == 500

        restored = SearchPlan.from_dict(data)
        assert len(restored.queries) == 2
        assert restored.queries[0].query_id == "q1"


# =============================================================================
# InclusionDecision Tests
# =============================================================================

class TestInclusionDecision:
    """Tests for InclusionDecision dataclass."""

    def test_create_excluded(self) -> None:
        """Test factory method for exclusion decisions."""
        decision = InclusionDecision.create_excluded(
            stage=ExclusionStage.INITIAL_FILTER,
            reasons=["Date out of range", "Wrong study type"],
            rationale="Paper published in 1995, before date range",
            exclusion_matched=["Date filter"],
        )
        assert decision.status == InclusionStatus.EXCLUDED
        assert decision.stage == ExclusionStage.INITIAL_FILTER
        assert len(decision.reasons) == 2

    def test_create_included(self) -> None:
        """Test factory method for inclusion decisions."""
        decision = InclusionDecision.create_included(
            stage=ExclusionStage.INCLUSION_CRITERIA,
            rationale="Paper meets all criteria",
            criteria_matched=["Human studies", "Statin intervention"],
        )
        assert decision.status == InclusionStatus.INCLUDED
        assert len(decision.criteria_matched) == 2

    def test_serialization(self) -> None:
        """Test serialization round-trip."""
        decision = InclusionDecision(
            status=InclusionStatus.UNCERTAIN,
            stage=ExclusionStage.RELEVANCE_SCORING,
            reasons=["Borderline relevance"],
            rationale="Needs human review",
            confidence=0.6,
        )
        data = decision.to_dict()
        restored = InclusionDecision.from_dict(data)

        assert restored.status == decision.status
        assert restored.confidence == 0.6


# =============================================================================
# ScoredPaper and AssessedPaper Tests
# =============================================================================

class TestScoredAndAssessedPaper:
    """Tests for ScoredPaper and AssessedPaper dataclasses."""

    def test_scored_paper_properties(self, sample_paper: PaperData) -> None:
        """Test ScoredPaper convenience properties."""
        decision = InclusionDecision.create_included(
            stage=ExclusionStage.RELEVANCE_SCORING,
            rationale="Highly relevant",
            criteria_matched=["All criteria met"],
        )
        scored = ScoredPaper(
            paper=sample_paper,
            relevance_score=4.5,
            relevance_rationale="Directly addresses research question",
            inclusion_decision=decision,
        )

        assert scored.is_included
        assert not scored.is_excluded
        assert not scored.needs_review

    def test_assessed_paper_convenience_properties(
        self, sample_paper: PaperData
    ) -> None:
        """Test AssessedPaper convenience properties."""
        decision = InclusionDecision.create_included(
            stage=ExclusionStage.QUALITY_GATE,
            rationale="High quality",
            criteria_matched=["All criteria"],
        )
        scored = ScoredPaper(
            paper=sample_paper,
            relevance_score=4.5,
            relevance_rationale="Relevant",
            inclusion_decision=decision,
        )
        assessed = AssessedPaper(
            scored_paper=scored,
            study_assessment={"quality": "high"},
            paper_weight={"score": 8.5},
            composite_score=8.0,
            final_rank=1,
        )

        assert assessed.document_id == sample_paper.document_id
        assert assessed.title == sample_paper.title
        assert assessed.is_included


# =============================================================================
# ProcessStep Tests
# =============================================================================

class TestProcessStep:
    """Tests for ProcessStep dataclass."""

    def test_creation(self) -> None:
        """Test creating ProcessStep."""
        step = ProcessStep(
            step_number=1,
            action="execute_search",
            tool_used="SemanticQueryAgent",
            input_summary="Query: cardiovascular disease",
            output_summary="Found 150 papers",
            decision_rationale="Using semantic search for coverage",
            timestamp=datetime.now().isoformat(),
            duration_seconds=2.5,
            metrics={"papers_found": 150},
        )
        assert step.step_number == 1
        assert step.success  # No error = success

    def test_success_property(self) -> None:
        """Test success property based on error field."""
        step = ProcessStep(
            step_number=1,
            action="test",
            tool_used=None,
            input_summary="input",
            output_summary="output",
            decision_rationale="rationale",
            timestamp=datetime.now().isoformat(),
            duration_seconds=1.0,
            error="Something went wrong",
        )
        assert not step.success

    def test_serialization(self) -> None:
        """Test serialization round-trip."""
        step = ProcessStep(
            step_number=5,
            action="score_papers",
            tool_used="DocumentScoringAgent",
            input_summary="Scoring 100 papers",
            output_summary="45 above threshold",
            decision_rationale="Using threshold 2.5",
            timestamp="2024-01-15T10:30:00",
            duration_seconds=45.5,
            metrics={"scored": 100, "above_threshold": 45},
        )
        data = step.to_dict()
        restored = ProcessStep.from_dict(data)

        assert restored.step_number == 5
        assert restored.action == "score_papers"
        assert restored.metrics["scored"] == 100


# =============================================================================
# Checkpoint Tests
# =============================================================================

class TestCheckpoint:
    """Tests for Checkpoint dataclass."""

    def test_creation(self) -> None:
        """Test creating Checkpoint."""
        checkpoint = Checkpoint(
            checkpoint_id="",  # Auto-generate
            checkpoint_type="search_strategy",
            timestamp=datetime.now().isoformat(),
            phase="search",
            state_snapshot={"plan": {"queries": []}},
        )
        assert checkpoint.checkpoint_id.startswith("cp_")
        assert checkpoint.checkpoint_type == "search_strategy"

    def test_to_dict_excludes_state_snapshot(self) -> None:
        """Test to_dict excludes large state_snapshot."""
        checkpoint = Checkpoint(
            checkpoint_id="cp_test",
            checkpoint_type="test",
            timestamp="2024-01-15T10:00:00",
            phase="test",
            state_snapshot={"large": "data" * 1000},
        )
        data = checkpoint.to_dict()
        assert "state_snapshot" not in data

    def test_to_full_dict_includes_state_snapshot(self) -> None:
        """Test to_full_dict includes state_snapshot."""
        checkpoint = Checkpoint(
            checkpoint_id="cp_test",
            checkpoint_type="test",
            timestamp="2024-01-15T10:00:00",
            phase="test",
            state_snapshot={"important": "state"},
        )
        data = checkpoint.to_full_dict()
        assert "state_snapshot" in data
        assert data["state_snapshot"]["important"] == "state"


# =============================================================================
# ReviewStatistics Tests
# =============================================================================

class TestReviewStatistics:
    """Tests for ReviewStatistics dataclass."""

    def test_create_empty(self) -> None:
        """Test create_empty factory method."""
        stats = ReviewStatistics.create_empty()
        assert stats.total_considered == 0
        assert stats.final_included == 0
        assert stats.processing_time_seconds == 0.0

    def test_serialization(self) -> None:
        """Test serialization round-trip."""
        stats = ReviewStatistics(
            total_considered=500,
            passed_initial_filter=350,
            passed_relevance_threshold=100,
            passed_quality_gate=50,
            final_included=50,
            final_excluded=450,
            uncertain_for_review=5,
            processing_time_seconds=1234.567,
            total_llm_calls=200,
            total_tokens_used=500000,
        )
        data = stats.to_dict()
        restored = ReviewStatistics.from_dict(data)

        assert restored.total_considered == 500
        assert restored.final_included == 50
        # Check rounding
        assert restored.processing_time_seconds == 1234.57


# =============================================================================
# SystematicReviewResult Tests
# =============================================================================

class TestSystematicReviewResult:
    """Tests for SystematicReviewResult dataclass."""

    def test_creation_and_serialization(self) -> None:
        """Test creating and serializing result."""
        result = SystematicReviewResult(
            metadata={
                "research_question": "Test question",
                "generated_at": datetime.now().isoformat(),
            },
            search_strategy={"queries": []},
            scoring_config={"weights": {"relevance": 0.5}},
            included_papers=[{"title": "Paper 1"}],
            excluded_papers=[{"title": "Paper 2", "reason": "Wrong type"}],
            uncertain_papers=[],
            process_log=[],
            statistics=ReviewStatistics.create_empty(),
        )

        data = result.to_dict()
        assert data["metadata"]["research_question"] == "Test question"
        assert len(data["included_papers"]) == 1

    def test_to_json(self) -> None:
        """Test JSON serialization."""
        result = SystematicReviewResult(
            metadata={"question": "Test"},
            search_strategy={},
            scoring_config={},
            included_papers=[],
            excluded_papers=[],
            uncertain_papers=[],
            process_log=[],
            statistics=ReviewStatistics.create_empty(),
        )
        json_str = result.to_json()
        data = json.loads(json_str)
        assert data["metadata"]["question"] == "Test"

    def test_save_and_load(self) -> None:
        """Test save and load from file."""
        result = SystematicReviewResult(
            metadata={"test": "data"},
            search_strategy={"queries": []},
            scoring_config={},
            included_papers=[{"id": 1}],
            excluded_papers=[],
            uncertain_papers=[],
            process_log=[{"step": 1}],
            statistics=ReviewStatistics(
                total_considered=100,
                passed_initial_filter=80,
                passed_relevance_threshold=40,
                passed_quality_gate=20,
                final_included=20,
                final_excluded=80,
                uncertain_for_review=0,
                processing_time_seconds=60.0,
                total_llm_calls=50,
                total_tokens_used=10000,
            ),
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            result.save(f.name)
            loaded = SystematicReviewResult.load(f.name)

        assert loaded.metadata["test"] == "data"
        assert loaded.statistics.final_included == 20


# =============================================================================
# Documenter Tests
# =============================================================================

class TestDocumenter:
    """Tests for Documenter class."""

    def test_initialization(self, sample_documenter: Documenter) -> None:
        """Test Documenter initialization."""
        assert sample_documenter.review_id == "test_review_001"
        assert len(sample_documenter.steps) == 0
        assert len(sample_documenter.checkpoints) == 0

    def test_auto_review_id(self) -> None:
        """Test Documenter generates review ID if not provided."""
        documenter = Documenter()
        assert documenter.review_id.startswith("review_")

    def test_start_and_end_review(self, sample_documenter: Documenter) -> None:
        """Test review lifecycle tracking."""
        sample_documenter.start_review()
        import time
        time.sleep(0.1)
        duration = sample_documenter.end_review()

        assert duration > 0
        assert sample_documenter.get_duration() > 0

    def test_log_step(self, sample_documenter: Documenter) -> None:
        """Test logging a process step."""
        step = sample_documenter.log_step(
            action="test_action",
            tool="TestTool",
            input_summary="Test input",
            output_summary="Test output",
            decision_rationale="Testing",
            metrics={"count": 42},
            duration_seconds=1.5,
        )

        assert step.step_number == 1
        assert step.action == "test_action"
        assert len(sample_documenter.steps) == 1

    def test_log_multiple_steps_increments_counter(
        self, sample_documenter: Documenter
    ) -> None:
        """Test step counter increments correctly."""
        for i in range(5):
            step = sample_documenter.log_step(
                action=f"action_{i}",
                tool=None,
                input_summary="input",
                output_summary="output",
                decision_rationale="testing",
            )
            assert step.step_number == i + 1

        assert len(sample_documenter.steps) == 5

    def test_log_checkpoint(self, sample_documenter: Documenter) -> None:
        """Test logging a checkpoint."""
        checkpoint = sample_documenter.log_checkpoint(
            checkpoint_type="search_strategy",
            phase="search",
            state_snapshot={"plan": {"queries": []}},
            user_decision="approved",
        )

        assert checkpoint.checkpoint_type == "search_strategy"
        assert checkpoint.user_decision == "approved"
        assert len(sample_documenter.checkpoints) == 1

    def test_get_checkpoint(self, sample_documenter: Documenter) -> None:
        """Test retrieving checkpoint by ID."""
        checkpoint = sample_documenter.log_checkpoint(
            checkpoint_type="test",
            phase="test",
            state_snapshot={},
        )

        retrieved = sample_documenter.get_checkpoint(checkpoint.checkpoint_id)
        assert retrieved is not None
        assert retrieved.checkpoint_id == checkpoint.checkpoint_id

        # Non-existent ID
        assert sample_documenter.get_checkpoint("nonexistent") is None

    def test_get_latest_checkpoint(self, sample_documenter: Documenter) -> None:
        """Test getting the most recent checkpoint."""
        sample_documenter.log_checkpoint("type_a", "phase_a", {})
        sample_documenter.log_checkpoint("type_b", "phase_b", {})
        cp3 = sample_documenter.log_checkpoint("type_a", "phase_c", {})

        latest = sample_documenter.get_latest_checkpoint()
        assert latest.checkpoint_id == cp3.checkpoint_id

        # Filter by type
        latest_a = sample_documenter.get_latest_checkpoint(checkpoint_type="type_a")
        assert latest_a.checkpoint_id == cp3.checkpoint_id

    def test_export_markdown(self, sample_documenter: Documenter) -> None:
        """Test Markdown export."""
        sample_documenter.start_review()
        sample_documenter.log_step(
            action="test",
            tool="TestTool",
            input_summary="input",
            output_summary="output",
            decision_rationale="testing",
            metrics={"count": 1},
        )

        markdown = sample_documenter.export_markdown()

        assert "# Systematic Review Audit Trail" in markdown
        assert "test_review_001" in markdown
        assert "test" in markdown
        assert "TestTool" in markdown

    def test_export_json(self, sample_documenter: Documenter) -> None:
        """Test JSON export."""
        sample_documenter.start_review()
        sample_documenter.log_step(
            action="test",
            tool="Tool",
            input_summary="input",
            output_summary="output",
            decision_rationale="testing",
        )

        json_str = sample_documenter.export_json()
        data = json.loads(json_str)

        assert data["review_id"] == "test_review_001"
        assert len(data["steps"]) == 1

    def test_save_to_file(self, sample_documenter: Documenter) -> None:
        """Test saving to file."""
        sample_documenter.log_step(
            action="test",
            tool=None,
            input_summary="input",
            output_summary="output",
            decision_rationale="testing",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "audit.json"
            sample_documenter.save_to_file(str(json_path), format="json")
            assert json_path.exists()

            md_path = Path(tmpdir) / "audit.md"
            sample_documenter.save_to_file(str(md_path), format="markdown")
            assert md_path.exists()

    def test_get_statistics(self, sample_documenter: Documenter) -> None:
        """Test getting statistics."""
        sample_documenter.log_step(
            action="success",
            tool=None,
            input_summary="i",
            output_summary="o",
            decision_rationale="r",
        )
        sample_documenter.log_step(
            action="failure",
            tool=None,
            input_summary="i",
            output_summary="o",
            decision_rationale="r",
            error="Something failed",
        )

        stats = sample_documenter.get_statistics()
        assert stats["total_steps"] == 2
        assert stats["successful_steps"] == 1
        assert stats["failed_steps"] == 1


# =============================================================================
# StepTimer Tests
# =============================================================================

class TestStepTimer:
    """Tests for StepTimer context manager."""

    def test_basic_usage(self, sample_documenter: Documenter) -> None:
        """Test basic StepTimer usage."""
        with sample_documenter.log_step_with_timer(
            action="timed_action",
            tool="TestTool",
            input_summary="timing test",
            decision_rationale="testing timer",
        ) as timer:
            import time
            time.sleep(0.1)
            timer.set_output("Completed timing test")
            timer.add_metrics({"test_metric": 42})

        assert len(sample_documenter.steps) == 1
        step = sample_documenter.steps[0]
        assert step.action == "timed_action"
        assert step.duration_seconds >= 0.1
        assert step.metrics["test_metric"] == 42

    def test_exception_handling(self, sample_documenter: Documenter) -> None:
        """Test StepTimer captures exceptions as errors."""
        with pytest.raises(ValueError):
            with sample_documenter.log_step_with_timer(
                action="failing_action",
                tool="TestTool",
                input_summary="will fail",
                decision_rationale="testing error capture",
            ) as timer:
                raise ValueError("Test error")

        assert len(sample_documenter.steps) == 1
        step = sample_documenter.steps[0]
        assert step.error is not None
        assert "Test error" in step.error
        assert not step.success


# =============================================================================
# Enum Tests
# =============================================================================

class TestEnums:
    """Tests for enum types."""

    def test_study_type_from_string(self) -> None:
        """Test StudyTypeFilter.from_string."""
        assert StudyTypeFilter.from_string("rct") == StudyTypeFilter.RCT
        assert StudyTypeFilter.from_string("RCT") == StudyTypeFilter.RCT
        assert StudyTypeFilter.from_string("  meta_analysis  ") == StudyTypeFilter.META_ANALYSIS

        with pytest.raises(ValueError):
            StudyTypeFilter.from_string("invalid_type")

    def test_query_type_values(self) -> None:
        """Test QueryType values."""
        assert QueryType.SEMANTIC.value == "semantic"
        assert QueryType.KEYWORD.value == "keyword"
        assert QueryType.HYDE.value == "hyde"

    def test_inclusion_status_values(self) -> None:
        """Test InclusionStatus values."""
        assert InclusionStatus.INCLUDED.value == "included"
        assert InclusionStatus.EXCLUDED.value == "excluded"
        assert InclusionStatus.UNCERTAIN.value == "uncertain"

    def test_exclusion_stage_values(self) -> None:
        """Test ExclusionStage values."""
        assert ExclusionStage.INITIAL_FILTER.value == "initial_filter"
        assert ExclusionStage.QUALITY_GATE.value == "quality_gate"
