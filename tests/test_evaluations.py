"""
Unit Tests for Unified Evaluations Module

Tests data types, validation, and core functionality of the
unified evaluation tracking system.
"""

import pytest
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, MagicMock, patch

from src.bmlibrarian.evaluations import (
    # Enums
    EvaluationType,
    RunType,
    RunStatus,
    CheckpointType,
    UserDecision,
    # TypedDict schemas
    RelevanceScoreData,
    QualityAssessmentData,
    PRISMASuitabilityData,
    PRISMAAssessmentData,
    PICOExtractionData,
    PaperWeightData,
    InclusionDecisionData,
    # Schema utilities
    EVALUATION_SCHEMAS,
    validate_evaluation_data,
    get_primary_score_field,
    extract_primary_score,
    # Evaluator registry
    EvaluatorInfo,
    EvaluatorRegistry,
    # Evaluation store
    EvaluationRun,
    DocumentEvaluation,
    Checkpoint,
    EvaluationStore,
)


# ============================================================================
# Enum Tests
# ============================================================================

class TestEvaluationType:
    """Test EvaluationType enum."""

    def test_all_types_exist(self) -> None:
        """Test that all expected evaluation types exist."""
        assert EvaluationType.RELEVANCE_SCORE.value == "relevance_score"
        assert EvaluationType.QUALITY_ASSESSMENT.value == "quality_assessment"
        assert EvaluationType.PRISMA_SUITABILITY.value == "prisma_suitability"
        assert EvaluationType.PRISMA_ASSESSMENT.value == "prisma_assessment"
        assert EvaluationType.PICO_EXTRACTION.value == "pico_extraction"
        assert EvaluationType.PAPER_WEIGHT.value == "paper_weight"
        assert EvaluationType.INCLUSION_DECISION.value == "inclusion_decision"

    def test_type_count(self) -> None:
        """Test correct number of evaluation types."""
        assert len(EvaluationType) == 7


class TestRunType:
    """Test RunType enum."""

    def test_all_types_exist(self) -> None:
        """Test that all expected run types exist."""
        assert RunType.RELEVANCE_SCORING.value == "relevance_scoring"
        assert RunType.QUALITY_ASSESSMENT.value == "quality_assessment"
        assert RunType.PRISMA_ASSESSMENT.value == "prisma_assessment"
        assert RunType.PICO_EXTRACTION.value == "pico_extraction"
        assert RunType.PAPER_WEIGHT.value == "paper_weight"
        assert RunType.SYSTEMATIC_REVIEW.value == "systematic_review"

    def test_type_count(self) -> None:
        """Test correct number of run types."""
        assert len(RunType) == 6


class TestRunStatus:
    """Test RunStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """Test that all expected statuses exist."""
        assert RunStatus.IN_PROGRESS.value == "in_progress"
        assert RunStatus.COMPLETED.value == "completed"
        assert RunStatus.FAILED.value == "failed"
        assert RunStatus.CANCELLED.value == "cancelled"
        assert RunStatus.PAUSED.value == "paused"

    def test_status_count(self) -> None:
        """Test correct number of statuses."""
        assert len(RunStatus) == 5


class TestCheckpointType:
    """Test CheckpointType enum."""

    def test_all_types_exist(self) -> None:
        """Test that all expected checkpoint types exist."""
        assert CheckpointType.SEARCH_PLANNING.value == "search_planning"
        assert CheckpointType.SEARCH_EXECUTION.value == "search_execution"
        assert CheckpointType.INITIAL_FILTERING.value == "initial_filtering"
        assert CheckpointType.RELEVANCE_SCORING.value == "relevance_scoring"
        assert CheckpointType.QUALITY_ASSESSMENT.value == "quality_assessment"
        assert CheckpointType.CITATION_EXTRACTION.value == "citation_extraction"
        assert CheckpointType.REPORT_GENERATION.value == "report_generation"
        assert CheckpointType.COUNTERFACTUAL_SEARCH.value == "counterfactual_search"
        assert CheckpointType.FINAL_REVIEW.value == "final_review"
        assert CheckpointType.CUSTOM.value == "custom"

    def test_type_count(self) -> None:
        """Test correct number of checkpoint types."""
        assert len(CheckpointType) == 10


class TestUserDecision:
    """Test UserDecision enum."""

    def test_all_decisions_exist(self) -> None:
        """Test that all expected user decisions exist."""
        assert UserDecision.CONTINUE.value == "continue"
        assert UserDecision.PAUSE.value == "pause"
        assert UserDecision.ABORT.value == "abort"
        assert UserDecision.ADJUST_PARAMETERS.value == "adjust_parameters"
        assert UserDecision.REQUEST_MORE.value == "request_more"

    def test_decision_count(self) -> None:
        """Test correct number of user decisions."""
        assert len(UserDecision) == 5


# ============================================================================
# Schema Validation Tests
# ============================================================================

class TestEvaluationSchemas:
    """Test evaluation schema registry."""

    def test_all_types_have_schemas(self) -> None:
        """Test that all evaluation types have schema definitions."""
        for eval_type in EvaluationType:
            assert eval_type.value in EVALUATION_SCHEMAS, (
                f"Missing schema for {eval_type.value}"
            )

    def test_schemas_have_required_keys(self) -> None:
        """Test that all schemas have required structure."""
        for eval_type, schema in EVALUATION_SCHEMAS.items():
            assert "required_fields" in schema, (
                f"Schema {eval_type} missing required_fields"
            )
            assert "optional_fields" in schema, (
                f"Schema {eval_type} missing optional_fields"
            )
            assert "typed_dict" in schema, (
                f"Schema {eval_type} missing typed_dict"
            )


class TestValidateEvaluationData:
    """Test validate_evaluation_data function."""

    def test_valid_relevance_score(self) -> None:
        """Test validation of valid relevance score data."""
        data = {"score": 4.5, "rationale": "Highly relevant"}
        is_valid, error = validate_evaluation_data(
            EvaluationType.RELEVANCE_SCORE.value, data
        )
        assert is_valid is True
        assert error is None

    def test_valid_relevance_score_minimal(self) -> None:
        """Test validation with only required fields."""
        data = {"score": 3.0}
        is_valid, error = validate_evaluation_data(
            EvaluationType.RELEVANCE_SCORE.value, data
        )
        assert is_valid is True
        assert error is None

    def test_invalid_relevance_score_missing_required(self) -> None:
        """Test validation fails when missing required field."""
        data = {"rationale": "Some rationale"}
        is_valid, error = validate_evaluation_data(
            EvaluationType.RELEVANCE_SCORE.value, data
        )
        assert is_valid is False
        assert "Missing required field: score" in error

    def test_unknown_evaluation_type(self) -> None:
        """Test validation fails for unknown evaluation type."""
        data = {"score": 4.0}
        is_valid, error = validate_evaluation_data("unknown_type", data)
        assert is_valid is False
        assert "Unknown evaluation type" in error

    def test_valid_quality_assessment(self) -> None:
        """Test validation of valid quality assessment data."""
        data = {
            "study_design": "RCT",
            "composite_score": 85.5,
            "methodology_score": 8.0,
        }
        is_valid, error = validate_evaluation_data(
            EvaluationType.QUALITY_ASSESSMENT.value, data
        )
        assert is_valid is True

    def test_valid_pico_extraction(self) -> None:
        """Test validation of valid PICO extraction data."""
        data = {
            "population": "Adults with hypertension",
            "intervention": "Daily exercise",
            "outcome": "Blood pressure reduction",
        }
        is_valid, error = validate_evaluation_data(
            EvaluationType.PICO_EXTRACTION.value, data
        )
        assert is_valid is True

    def test_valid_prisma_assessment(self) -> None:
        """Test validation of valid PRISMA assessment data."""
        data = {
            "item_scores": {"1": 2, "2": 1, "3": 0},
            "overall_compliance_percentage": 75.0,
        }
        is_valid, error = validate_evaluation_data(
            EvaluationType.PRISMA_ASSESSMENT.value, data
        )
        assert is_valid is True


class TestGetPrimaryScoreField:
    """Test get_primary_score_field function."""

    def test_relevance_score_field(self) -> None:
        """Test primary score field for relevance scoring."""
        field = get_primary_score_field(EvaluationType.RELEVANCE_SCORE.value)
        assert field == "score"

    def test_quality_assessment_field(self) -> None:
        """Test primary score field for quality assessment."""
        field = get_primary_score_field(EvaluationType.QUALITY_ASSESSMENT.value)
        assert field == "composite_score"

    def test_prisma_assessment_field(self) -> None:
        """Test primary score field for PRISMA assessment."""
        field = get_primary_score_field(EvaluationType.PRISMA_ASSESSMENT.value)
        assert field == "overall_compliance_percentage"

    def test_pico_extraction_no_field(self) -> None:
        """Test that PICO extraction has no primary score field."""
        field = get_primary_score_field(EvaluationType.PICO_EXTRACTION.value)
        assert field is None


class TestExtractPrimaryScore:
    """Test extract_primary_score function."""

    def test_extract_relevance_score(self) -> None:
        """Test extracting primary score from relevance data."""
        data = {"score": 4.5, "rationale": "Relevant"}
        score = extract_primary_score(EvaluationType.RELEVANCE_SCORE.value, data)
        assert score == 4.5

    def test_extract_quality_composite(self) -> None:
        """Test extracting primary score from quality assessment."""
        data = {"study_design": "RCT", "composite_score": 85.0}
        score = extract_primary_score(EvaluationType.QUALITY_ASSESSMENT.value, data)
        assert score == 85.0

    def test_extract_from_pico_returns_none(self) -> None:
        """Test that PICO extraction returns None."""
        data = {"population": "Adults", "intervention": "Exercise", "outcome": "Health"}
        score = extract_primary_score(EvaluationType.PICO_EXTRACTION.value, data)
        assert score is None


# ============================================================================
# EvaluatorInfo Tests
# ============================================================================

class TestEvaluatorInfo:
    """Test EvaluatorInfo dataclass."""

    def test_model_evaluator_properties(self) -> None:
        """Test properties for model evaluator."""
        info = EvaluatorInfo(
            id=1,
            name="gpt-oss:20b t=0.1",
            user_id=None,
            model_id="gpt-oss:20b",
            parameters={"temperature": 0.1, "top_p": 0.9},
            prompt=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert info.is_model is True
        assert info.is_human is False
        assert info.get_temperature() == 0.1
        assert info.get_top_p() == 0.9

    def test_human_evaluator_properties(self) -> None:
        """Test properties for human evaluator."""
        info = EvaluatorInfo(
            id=2,
            name="Human: Dr. Smith",
            user_id=123,
            model_id=None,
            parameters=None,
            prompt=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert info.is_model is False
        assert info.is_human is True
        assert info.get_temperature() == 0.0  # Default
        assert info.get_top_p() == 1.0  # Default

    def test_default_parameters(self) -> None:
        """Test default parameter values when parameters is None."""
        info = EvaluatorInfo(
            id=3,
            name="Test",
            user_id=None,
            model_id="test-model",
            parameters=None,
            prompt=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert info.get_temperature() == 0.0
        assert info.get_top_p() == 1.0


# ============================================================================
# EvaluationRun Tests
# ============================================================================

class TestEvaluationRun:
    """Test EvaluationRun dataclass."""

    def test_progress_percent_zero_total(self) -> None:
        """Test progress calculation when total is zero."""
        run = EvaluationRun(
            run_id=1,
            run_type="relevance_scoring",
            research_question_id=None,
            research_question_text="Test question",
            evaluator_id=1,
            status="in_progress",
            config_snapshot=None,
            documents_total=0,
            documents_processed=0,
            started_at=datetime.now(),
            completed_at=None,
        )
        assert run.progress_percent == 0.0

    def test_progress_percent_calculation(self) -> None:
        """Test progress percentage calculation."""
        run = EvaluationRun(
            run_id=1,
            run_type="relevance_scoring",
            research_question_id=None,
            research_question_text="Test question",
            evaluator_id=1,
            status="in_progress",
            config_snapshot=None,
            documents_total=100,
            documents_processed=50,
            started_at=datetime.now(),
            completed_at=None,
        )
        assert run.progress_percent == 50.0

    def test_is_complete_completed(self) -> None:
        """Test is_complete for completed status."""
        run = EvaluationRun(
            run_id=1,
            run_type="relevance_scoring",
            research_question_id=None,
            research_question_text="Test",
            evaluator_id=1,
            status="completed",
            config_snapshot=None,
            documents_total=100,
            documents_processed=100,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        assert run.is_complete is True

    def test_is_complete_failed(self) -> None:
        """Test is_complete for failed status."""
        run = EvaluationRun(
            run_id=1,
            run_type="relevance_scoring",
            research_question_id=None,
            research_question_text="Test",
            evaluator_id=1,
            status="failed",
            config_snapshot=None,
            documents_total=100,
            documents_processed=50,
            started_at=datetime.now(),
            completed_at=datetime.now(),
            error_message="Error occurred",
        )
        assert run.is_complete is True

    def test_is_resumable_in_progress(self) -> None:
        """Test is_resumable for in_progress status."""
        run = EvaluationRun(
            run_id=1,
            run_type="relevance_scoring",
            research_question_id=None,
            research_question_text="Test",
            evaluator_id=1,
            status="in_progress",
            config_snapshot=None,
            documents_total=100,
            documents_processed=50,
            started_at=datetime.now(),
            completed_at=None,
        )
        assert run.is_resumable is True

    def test_is_resumable_paused(self) -> None:
        """Test is_resumable for paused status."""
        run = EvaluationRun(
            run_id=1,
            run_type="relevance_scoring",
            research_question_id=None,
            research_question_text="Test",
            evaluator_id=1,
            status="paused",
            config_snapshot=None,
            documents_total=100,
            documents_processed=50,
            started_at=datetime.now(),
            completed_at=None,
        )
        assert run.is_resumable is True

    def test_is_resumable_completed(self) -> None:
        """Test is_resumable for completed status (should be False)."""
        run = EvaluationRun(
            run_id=1,
            run_type="relevance_scoring",
            research_question_id=None,
            research_question_text="Test",
            evaluator_id=1,
            status="completed",
            config_snapshot=None,
            documents_total=100,
            documents_processed=100,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )
        assert run.is_resumable is False


# ============================================================================
# EvaluatorRegistry Tests (with mocked DB)
# ============================================================================

class TestEvaluatorRegistry:
    """Test EvaluatorRegistry with mocked database."""

    @pytest.fixture
    def mock_db(self) -> Mock:
        """Create a mock database manager."""
        db = Mock()
        db.get_connection = MagicMock()
        return db

    @pytest.fixture
    def registry(self, mock_db: Mock) -> EvaluatorRegistry:
        """Create registry with mocked database."""
        return EvaluatorRegistry(mock_db)

    def test_generate_name_model(self, registry: EvaluatorRegistry) -> None:
        """Test name generation for model evaluator."""
        name = registry._generate_name(
            model_name="gpt-oss:20b",
            temperature=0.1,
            top_p=0.9
        )
        assert "gpt-oss:20b" in name
        assert "t=0.1" in name
        assert "p=0.9" in name

    def test_generate_name_model_defaults(self, registry: EvaluatorRegistry) -> None:
        """Test name generation with default parameters."""
        name = registry._generate_name(
            model_name="gpt-oss:20b",
            temperature=0.0,
            top_p=1.0
        )
        assert name == "gpt-oss:20b"
        assert "t=" not in name
        assert "p=" not in name

    def test_generate_name_human(self, registry: EvaluatorRegistry) -> None:
        """Test name generation for human evaluator."""
        name = registry._generate_name(user_name="Dr. Smith")
        assert name == "Human: Dr. Smith"

    def test_normalize_parameters(self, registry: EvaluatorRegistry) -> None:
        """Test parameter normalization."""
        params = registry._normalize_parameters(
            temperature=0.12345,
            top_p=0.98765,
            extra_params={"custom_param": "value"}
        )
        assert params["temperature"] == 0.1235  # Rounded
        assert params["top_p"] == 0.9877  # Rounded
        assert params["custom_param"] == "value"

    def test_cache_hit(self, registry: EvaluatorRegistry) -> None:
        """Test that cached evaluator IDs are returned without DB lookup."""
        # Pre-populate cache
        cache_key = ("model", "test-model", 0.0, 1.0, None)
        registry._cache[cache_key] = 42

        # Should return cached value without DB call
        evaluator_id = registry.get_or_create_model_evaluator(
            model_name="test-model",
            temperature=0.0,
            top_p=1.0
        )
        assert evaluator_id == 42

    def test_clear_cache(self, registry: EvaluatorRegistry) -> None:
        """Test cache clearing."""
        registry._cache[("test",)] = 1
        registry._info_cache[1] = Mock()

        registry.clear_cache()

        assert len(registry._cache) == 0
        assert len(registry._info_cache) == 0


# ============================================================================
# EvaluationStore Tests (with mocked DB)
# ============================================================================

class TestEvaluationStore:
    """Test EvaluationStore with mocked database."""

    @pytest.fixture
    def mock_db(self) -> Mock:
        """Create a mock database manager."""
        db = Mock()
        db.get_connection = MagicMock()
        return db

    @pytest.fixture
    def store(self, mock_db: Mock) -> EvaluationStore:
        """Create store with mocked database."""
        return EvaluationStore(mock_db)

    def test_evaluator_registry_lazy_init(self, store: EvaluationStore) -> None:
        """Test that evaluator registry is lazily initialized."""
        assert store._evaluator_registry is None
        registry = store.evaluator_registry
        assert registry is not None
        assert store._evaluator_registry is registry

    def test_create_run_with_enum(self, store: EvaluationStore, mock_db: Mock) -> None:
        """Test that create_run accepts RunType enum."""
        # Setup mock
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1, "in_progress", datetime.now())
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        run = store.create_run(
            run_type=RunType.RELEVANCE_SCORING,
            research_question="Test question",
            evaluator_id=1,
        )

        assert run.run_id == 1
        assert run.run_type == "relevance_scoring"
        assert run.status == "in_progress"

    def test_save_evaluation_validates(self, store: EvaluationStore) -> None:
        """Test that save_evaluation validates data by default."""
        with pytest.raises(ValueError, match="Missing required field"):
            store.save_evaluation(
                run_id=1,
                document_id=123,
                evaluation_type=EvaluationType.RELEVANCE_SCORE,
                evaluation_data={"rationale": "No score field"},
                validate=True,
            )

    def test_save_evaluation_skip_validation(
        self, store: EvaluationStore, mock_db: Mock
    ) -> None:
        """Test that validation can be skipped."""
        # Setup mock
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        # Should not raise even with invalid data
        eval_id = store.save_evaluation(
            run_id=1,
            document_id=123,
            evaluation_type=EvaluationType.RELEVANCE_SCORE,
            evaluation_data={"rationale": "No score field"},
            validate=False,
        )
        assert eval_id == 1

    def test_save_evaluation_auto_extract_score(
        self, store: EvaluationStore, mock_db: Mock
    ) -> None:
        """Test that primary score is auto-extracted if not provided."""
        # Setup mock
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db.get_connection.return_value.__enter__.return_value = mock_conn

        store.save_evaluation(
            run_id=1,
            document_id=123,
            evaluation_type=EvaluationType.RELEVANCE_SCORE,
            evaluation_data={"score": 4.5, "rationale": "Good"},
            primary_score=None,  # Should be auto-extracted
        )

        # Verify the SQL was called with the extracted score
        call_args = mock_cursor.execute.call_args[0]
        # The 4th positional arg in the VALUES should be 4.5
        assert call_args[1][3] == 4.5


# ============================================================================
# Integration-style Tests (still mocked but testing interactions)
# ============================================================================

class TestEvaluationWorkflow:
    """Test typical evaluation workflow patterns."""

    def test_evaluation_data_roundtrip(self) -> None:
        """Test that evaluation data can be validated and score extracted."""
        # Simulate a typical evaluation workflow
        eval_data: RelevanceScoreData = {
            "score": 4.5,
            "rationale": "Highly relevant study on cardiovascular health",
            "inclusion_decision": "include",
        }

        # Validate
        is_valid, error = validate_evaluation_data(
            EvaluationType.RELEVANCE_SCORE.value, eval_data
        )
        assert is_valid is True

        # Extract score
        score = extract_primary_score(
            EvaluationType.RELEVANCE_SCORE.value, eval_data
        )
        assert score == 4.5

    def test_quality_assessment_workflow(self) -> None:
        """Test quality assessment data workflow."""
        eval_data: QualityAssessmentData = {
            "study_design": "RCT",
            "methodology_score": 8.5,
            "bias_risk_score": 2.0,
            "sample_size_score": 7.0,
            "recency_score": 9.0,
            "replication_status": "replicated",
            "composite_score": 82.5,
            "weights_used": {
                "methodology": 0.3,
                "bias_risk": 0.2,
                "sample_size": 0.2,
                "recency": 0.15,
                "replication": 0.15,
            },
        }

        # Validate
        is_valid, error = validate_evaluation_data(
            EvaluationType.QUALITY_ASSESSMENT.value, eval_data
        )
        assert is_valid is True

        # Extract score
        score = extract_primary_score(
            EvaluationType.QUALITY_ASSESSMENT.value, eval_data
        )
        assert score == 82.5

    def test_prisma_assessment_workflow(self) -> None:
        """Test PRISMA assessment data workflow."""
        eval_data: PRISMAAssessmentData = {
            "is_suitable": True,
            "suitability_confidence": 0.95,
            "item_scores": {str(i): 2 for i in range(1, 28)},  # All items fully met
            "item_explanations": {str(i): f"Item {i} met" for i in range(1, 28)},
            "overall_compliance_score": 54.0,  # 27 items * 2
            "overall_compliance_percentage": 100.0,
            "missing_items": [],
            "partial_items": [],
            "fully_reported_items": [str(i) for i in range(1, 28)],
        }

        # Validate
        is_valid, error = validate_evaluation_data(
            EvaluationType.PRISMA_ASSESSMENT.value, eval_data
        )
        assert is_valid is True

        # Extract score
        score = extract_primary_score(
            EvaluationType.PRISMA_ASSESSMENT.value, eval_data
        )
        assert score == 100.0
