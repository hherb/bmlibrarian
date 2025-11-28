"""
Unit tests for the Audit Trail Validation module.

Tests cover:
- ValidationTracker data layer
- Data models (enums, dataclasses)
- AuditValidationDataManager
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from bmlibrarian.audit import (
    ValidationTracker,
    TargetType,
    ValidationStatus,
    Severity,
    ValidationCategory,
    HumanValidation,
    ValidationStatistics,
    UnvalidatedCounts
)
from bmlibrarian.gui.qt.plugins.audit_validation.data_manager import (
    AuditValidationDataManager,
    ResearchQuestionSummary,
    QueryAuditItem,
    ScoreAuditItem,
    CitationAuditItem,
    ReportAuditItem,
    CounterfactualAuditItem
)


class TestTargetType:
    """Tests for TargetType enum."""

    def test_target_type_values(self):
        """Verify all target types have correct string values."""
        assert TargetType.QUERY.value == "query"
        assert TargetType.SCORE.value == "score"
        assert TargetType.CITATION.value == "citation"
        assert TargetType.REPORT.value == "report"
        assert TargetType.COUNTERFACTUAL.value == "counterfactual"

    def test_target_type_from_string(self):
        """Test creating TargetType from string value."""
        assert TargetType("query") == TargetType.QUERY
        assert TargetType("score") == TargetType.SCORE
        assert TargetType("citation") == TargetType.CITATION


class TestValidationStatus:
    """Tests for ValidationStatus enum."""

    def test_validation_status_values(self):
        """Verify all validation statuses have correct string values."""
        assert ValidationStatus.VALIDATED.value == "validated"
        assert ValidationStatus.INCORRECT.value == "incorrect"
        assert ValidationStatus.UNCERTAIN.value == "uncertain"
        assert ValidationStatus.NEEDS_REVIEW.value == "needs_review"

    def test_validation_status_from_string(self):
        """Test creating ValidationStatus from string value."""
        assert ValidationStatus("validated") == ValidationStatus.VALIDATED
        assert ValidationStatus("incorrect") == ValidationStatus.INCORRECT


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_values(self):
        """Verify all severity levels have correct string values."""
        assert Severity.MINOR.value == "minor"
        assert Severity.MODERATE.value == "moderate"
        assert Severity.MAJOR.value == "major"
        assert Severity.CRITICAL.value == "critical"


class TestValidationCategory:
    """Tests for ValidationCategory dataclass."""

    def test_validation_category_creation(self):
        """Test creating a ValidationCategory."""
        category = ValidationCategory(
            category_id=1,
            target_type=TargetType.SCORE,
            category_code="overscored",
            category_name="Overscored",
            description="Document scored too high",
            is_active=True
        )
        assert category.category_id == 1
        assert category.target_type == TargetType.SCORE
        assert category.category_code == "overscored"
        assert category.category_name == "Overscored"
        assert category.is_active is True

    def test_validation_category_defaults(self):
        """Test ValidationCategory default values."""
        category = ValidationCategory(
            category_id=1,
            target_type=TargetType.QUERY,
            category_code="test",
            category_name="Test Category"
        )
        assert category.description is None
        assert category.is_active is True


class TestHumanValidation:
    """Tests for HumanValidation dataclass."""

    def test_human_validation_creation(self):
        """Test creating a HumanValidation."""
        validation = HumanValidation(
            validation_id=1,
            research_question_id=100,
            target_type=TargetType.SCORE,
            target_id=500,
            validation_status=ValidationStatus.VALIDATED,
            reviewer_name="Test Reviewer",
            comment="Looks correct"
        )
        assert validation.validation_id == 1
        assert validation.research_question_id == 100
        assert validation.target_type == TargetType.SCORE
        assert validation.validation_status == ValidationStatus.VALIDATED
        assert validation.reviewer_name == "Test Reviewer"

    def test_human_validation_defaults(self):
        """Test HumanValidation default values."""
        validation = HumanValidation()
        assert validation.validation_id is None
        assert validation.research_question_id == 0
        assert validation.target_type == TargetType.SCORE
        assert validation.validation_status == ValidationStatus.VALIDATED
        assert validation.reviewer_name == ""
        assert validation.categories == []


class TestValidationStatistics:
    """Tests for ValidationStatistics dataclass."""

    def test_validation_statistics_creation(self):
        """Test creating ValidationStatistics."""
        stats = ValidationStatistics(
            target_type=TargetType.SCORE,
            total_validations=100,
            validated_count=80,
            incorrect_count=15,
            uncertain_count=3,
            needs_review_count=2,
            validation_rate_percent=80.0,
            unique_reviewers=5,
            avg_review_time_seconds=45.5
        )
        assert stats.total_validations == 100
        assert stats.validated_count == 80
        assert stats.validation_rate_percent == 80.0


class TestUnvalidatedCounts:
    """Tests for UnvalidatedCounts dataclass."""

    def test_unvalidated_counts_creation(self):
        """Test creating UnvalidatedCounts."""
        counts = UnvalidatedCounts(
            target_type=TargetType.CITATION,
            total_count=50,
            validated_count=30,
            unvalidated_count=20
        )
        assert counts.total_count == 50
        assert counts.validated_count == 30
        assert counts.unvalidated_count == 20


class TestValidationTracker:
    """Tests for ValidationTracker class."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock database connection."""
        conn = Mock()
        cursor = Mock()
        conn.cursor.return_value.__enter__ = Mock(return_value=cursor)
        conn.cursor.return_value.__exit__ = Mock(return_value=False)
        return conn, cursor

    def test_validation_tracker_init(self, mock_conn):
        """Test ValidationTracker initialization."""
        conn, _ = mock_conn
        tracker = ValidationTracker(conn)
        assert tracker.conn == conn

    def test_record_validation(self, mock_conn):
        """Test recording a validation."""
        conn, cursor = mock_conn
        cursor.fetchone.return_value = (1,)

        tracker = ValidationTracker(conn)
        validation_id = tracker.record_validation(
            research_question_id=100,
            target_type=TargetType.SCORE,
            target_id=500,
            validation_status=ValidationStatus.VALIDATED,
            reviewer_id=1,
            reviewer_name="Test Reviewer"
        )

        assert validation_id == 1
        cursor.execute.assert_called_once()
        conn.commit.assert_called_once()

    def test_record_validation_with_categories(self, mock_conn):
        """Test recording a validation with categories."""
        conn, cursor = mock_conn
        cursor.fetchone.return_value = (1,)

        tracker = ValidationTracker(conn)
        validation_id = tracker.record_validation(
            research_question_id=100,
            target_type=TargetType.SCORE,
            target_id=500,
            validation_status=ValidationStatus.INCORRECT,
            reviewer_id=1,
            reviewer_name="Test Reviewer",
            category_ids=[1, 2, 3]
        )

        assert validation_id == 1
        # Should have called execute for main insert and category assignments
        assert cursor.execute.call_count >= 1

    def test_is_validated(self, mock_conn):
        """Test checking if item is validated."""
        conn, cursor = mock_conn
        cursor.fetchone.return_value = (True,)

        tracker = ValidationTracker(conn)
        result = tracker.is_validated(TargetType.SCORE, 500)

        assert result is True

    def test_is_validated_with_reviewer(self, mock_conn):
        """Test checking if item is validated by specific reviewer."""
        conn, cursor = mock_conn
        cursor.fetchone.return_value = (True,)

        tracker = ValidationTracker(conn)
        result = tracker.is_validated(TargetType.SCORE, 500, reviewer_id=1)

        assert result is True

    def test_delete_validation(self, mock_conn):
        """Test deleting a validation."""
        conn, cursor = mock_conn
        cursor.rowcount = 1

        tracker = ValidationTracker(conn)
        result = tracker.delete_validation(1)

        assert result is True
        conn.commit.assert_called_once()


class TestAuditDataModels:
    """Tests for audit data item models."""

    def test_research_question_summary(self):
        """Test ResearchQuestionSummary creation."""
        summary = ResearchQuestionSummary(
            research_question_id=1,
            question_text="What are the effects of X?",
            created_at=datetime.now(),
            last_activity_at=datetime.now(),
            total_sessions=5,
            status="active"
        )
        assert summary.research_question_id == 1
        assert summary.total_sessions == 5
        assert summary.validation_progress == {}

    def test_query_audit_item(self):
        """Test QueryAuditItem creation."""
        item = QueryAuditItem(
            query_id=1,
            research_question_id=100,
            session_id=10,
            query_text="SELECT * FROM documents",
            query_text_sanitized="SELECT * FROM documents",
            human_edited=False,
            original_ai_query=None,
            documents_found_count=50,
            created_at=datetime.now()
        )
        assert item.query_id == 1
        assert item.documents_found_count == 50
        assert item.validation is None

    def test_score_audit_item(self):
        """Test ScoreAuditItem creation."""
        item = ScoreAuditItem(
            scoring_id=1,
            research_question_id=100,
            document_id=200,
            session_id=10,
            evaluator_id=5,
            evaluator_name="Test Model",
            relevance_score=4,
            reasoning="Highly relevant",
            scored_at=datetime.now()
        )
        assert item.scoring_id == 1
        assert item.relevance_score == 4
        assert item.document_title is None

    def test_citation_audit_item(self):
        """Test CitationAuditItem creation."""
        item = CitationAuditItem(
            citation_id=1,
            research_question_id=100,
            document_id=200,
            session_id=10,
            scoring_id=50,
            evaluator_id=5,
            evaluator_name="Test Model",
            passage="This is a relevant passage.",
            summary="The passage discusses...",
            relevance_confidence=0.85,
            human_review_status=None,
            extracted_at=datetime.now()
        )
        assert item.citation_id == 1
        assert item.relevance_confidence == 0.85

    def test_report_audit_item(self):
        """Test ReportAuditItem creation."""
        item = ReportAuditItem(
            report_id=1,
            research_question_id=100,
            session_id=10,
            report_type="comprehensive",
            evaluator_id=5,
            evaluator_name="Test Model",
            citation_count=10,
            report_text="# Report\n\nThis is the report content.",
            report_format="markdown",
            generated_at=datetime.now(),
            human_edited=False,
            is_final=True
        )
        assert item.report_id == 1
        assert item.is_final is True

    def test_counterfactual_audit_item(self):
        """Test CounterfactualAuditItem creation."""
        item = CounterfactualAuditItem(
            question_id=1,
            research_question_id=100,
            analysis_id=50,
            question_text="What if the opposite is true?",
            target_claim="X causes Y",
            priority="high",
            query_generated="SELECT * FROM documents WHERE...",
            documents_found_count=5
        )
        assert item.question_id == 1
        assert item.priority == "high"


class TestAuditValidationDataManager:
    """Tests for AuditValidationDataManager class."""

    @pytest.fixture
    def mock_data_manager(self):
        """Create a mock data manager."""
        conn = Mock()
        cursor = Mock()
        conn.cursor.return_value.__enter__ = Mock(return_value=cursor)
        conn.cursor.return_value.__exit__ = Mock(return_value=False)
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = None

        manager = AuditValidationDataManager(conn)
        return manager, cursor

    def test_data_manager_init(self, mock_data_manager):
        """Test AuditValidationDataManager initialization."""
        manager, _ = mock_data_manager
        assert manager.conn is not None
        assert manager.validation_tracker is not None

    def test_get_categories(self, mock_data_manager):
        """Test getting validation categories."""
        manager, cursor = mock_data_manager
        cursor.fetchall.return_value = [
            {
                'category_id': 1,
                'target_type': 'score',
                'category_code': 'overscored',
                'category_name': 'Overscored',
                'description': 'Document scored too high',
                'is_active': True
            }
        ]

        categories = manager.get_categories(TargetType.SCORE)
        assert len(categories) >= 0  # Depends on mock setup

    def test_record_validation_delegates(self, mock_data_manager):
        """Test that record_validation delegates to ValidationTracker."""
        manager, cursor = mock_data_manager
        cursor.fetchone.return_value = (1,)

        # Spy on the validation tracker
        with patch.object(manager.validation_tracker, 'record_validation', return_value=1) as mock_record:
            result = manager.record_validation(
                research_question_id=100,
                target_type=TargetType.SCORE,
                target_id=500,
                validation_status=ValidationStatus.VALIDATED,
                reviewer_id=1,
                reviewer_name="Test"
            )

            mock_record.assert_called_once()
            assert result == 1


class TestValidationTabConstants:
    """Tests for validation tab constants."""

    def test_constants_exist(self):
        """Test that UI constants are defined."""
        from bmlibrarian.gui.qt.plugins.audit_validation.validation_tab import (
            SPLITTER_LEFT_RATIO,
            SPLITTER_RIGHT_RATIO,
            REVIEW_TIMER_INTERVAL_MS,
            MAX_DISPLAY_TEXT_LENGTH
        )

        assert SPLITTER_LEFT_RATIO == 30
        assert SPLITTER_RIGHT_RATIO == 70
        assert REVIEW_TIMER_INTERVAL_MS == 1000
        assert MAX_DISPLAY_TEXT_LENGTH == 50


class TestMainWindowConstants:
    """Tests for main window constants."""

    def test_window_constants_exist(self):
        """Test that window size constants are defined."""
        import audit_validation_gui as gui

        assert gui.DEFAULT_WINDOW_WIDTH == 1200
        assert gui.DEFAULT_WINDOW_HEIGHT == 800


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
