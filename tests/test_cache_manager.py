"""
Unit tests for ResultsCacheManager.

Tests cover:
- Version registration and uniqueness
- Cache hit/miss behavior
- Force recompute flag
- Cache failure graceful degradation
- Paper weight caching
- Suitability check caching
- Cache statistics

This test suite uses mocking to avoid database access.
"""

import json
import pytest
from datetime import datetime
from typing import Dict, Any
from unittest.mock import MagicMock, patch, Mock

from bmlibrarian.agents.systematic_review.cache_manager import ResultsCacheManager


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db_manager():
    """Create mock database manager."""
    db_manager = MagicMock()
    connection = MagicMock()
    cursor = MagicMock()

    # Set up context managers
    db_manager.get_connection.return_value.__enter__ = Mock(return_value=connection)
    db_manager.get_connection.return_value.__exit__ = Mock(return_value=False)
    connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
    connection.cursor.return_value.__exit__ = Mock(return_value=False)

    return db_manager, cursor


@pytest.fixture
def cache_manager(mock_db_manager):
    """Create cache manager with mocked database."""
    db_manager, _ = mock_db_manager
    return ResultsCacheManager(db_manager=db_manager)


@pytest.fixture
def sample_study_assessment() -> Dict[str, Any]:
    """Create sample study assessment result."""
    return {
        "study_type": "randomized controlled trial",
        "study_design": "prospective, double-blinded",
        "quality_score": 8.5,
        "strengths": ["Large sample size", "Double-blinded design"],
        "limitations": ["Single geographic region"],
        "overall_confidence": 0.85,
        "confidence_explanation": "High-quality RCT",
        "evidence_level": "Level 1 (high)",
        "document_id": "12345",
        "document_title": "Example Study",
    }


@pytest.fixture
def sample_pico_extraction() -> Dict[str, Any]:
    """Create sample PICO extraction result."""
    return {
        "population": "Adults aged 40-75 with elevated cholesterol",
        "intervention": "Atorvastatin 20mg daily",
        "comparison": "Placebo",
        "outcome": "Cardiovascular events",
        "document_id": "12345",
        "document_title": "Example Study",
        "extraction_confidence": 0.90,
        "study_type": "RCT",
        "sample_size": "N=10,000",
    }


@pytest.fixture
def sample_prisma_assessment() -> Dict[str, Any]:
    """Create sample PRISMA assessment result."""
    return {
        "document_id": 54321,
        "is_suitable": True,
        "overall_score": 22.5,
        "reporting_completeness": 0.83,
        "items_assessed": 27,
        "items_compliant": 22,
    }


@pytest.fixture
def sample_paper_weight() -> Dict[str, Any]:
    """Create sample paper weight result."""
    return {
        "document_id": 12345,
        "composite_score": 7.8,
        "dimensions": [
            {"dimension": "study_design", "score": 9.0, "weight": 0.25},
            {"dimension": "sample_size", "score": 8.0, "weight": 0.15},
        ],
        "assessment_id": 100,
    }


@pytest.fixture
def sample_suitability_check() -> Dict[str, Any]:
    """Create sample suitability check result."""
    return {
        "is_suitable": True,
        "confidence": 0.92,
        "rationale": "Document describes an intervention study with comparison group",
        "study_type": "randomized controlled trial",
    }


# =============================================================================
# Version Registration Tests
# =============================================================================

class TestVersionRegistration:
    """Tests for version registration functionality."""

    def test_register_version_creates_new_entry(self, cache_manager, mock_db_manager):
        """Test that register_version creates new version entry."""
        _, cursor = mock_db_manager
        cursor.fetchone.return_value = (1,)  # Return version_id = 1

        version_id = cache_manager.register_version(
            assessment_type="study_assessment",
            model_name="gpt-oss:20b",
            agent_version="1.0.0",
            parameters={"temperature": 0.1, "top_p": 0.9}
        )

        assert version_id == 1
        cursor.execute.assert_called_once()
        call_args = cursor.execute.call_args
        assert "get_or_create_version" in call_args[0][0]

    def test_register_version_caches_result(self, cache_manager, mock_db_manager):
        """Test that register_version caches the result in memory."""
        _, cursor = mock_db_manager
        cursor.fetchone.return_value = (5,)

        # First call
        version_id1 = cache_manager.register_version(
            assessment_type="pico",
            model_name="medgemma:latest",
            agent_version="1.0.0",
            parameters={"temperature": 0.1}
        )

        # Second call with same parameters
        version_id2 = cache_manager.register_version(
            assessment_type="pico",
            model_name="medgemma:latest",
            agent_version="1.0.0",
            parameters={"temperature": 0.1}
        )

        assert version_id1 == version_id2
        # Should only call database once due to caching
        assert cursor.execute.call_count == 1

    def test_register_version_different_params_creates_new(self, cache_manager, mock_db_manager):
        """Test that different parameters create different versions."""
        _, cursor = mock_db_manager
        cursor.fetchone.side_effect = [(1,), (2,)]

        # First version
        version_id1 = cache_manager.register_version(
            assessment_type="study_assessment",
            model_name="gpt-oss:20b",
            agent_version="1.0.0",
            parameters={"temperature": 0.1}
        )

        # Second version with different temperature
        version_id2 = cache_manager.register_version(
            assessment_type="study_assessment",
            model_name="gpt-oss:20b",
            agent_version="1.0.0",
            parameters={"temperature": 0.2}
        )

        assert version_id1 != version_id2
        assert cursor.execute.call_count == 2

    def test_register_version_handles_db_error(self, cache_manager, mock_db_manager):
        """Test that register_version handles database errors gracefully."""
        _, cursor = mock_db_manager
        cursor.execute.side_effect = Exception("Database connection failed")

        with pytest.raises(RuntimeError) as excinfo:
            cache_manager.register_version(
                assessment_type="study_assessment",
                model_name="gpt-oss:20b",
                agent_version="1.0.0",
                parameters={}
            )

        assert "Version registration failed" in str(excinfo.value)


# =============================================================================
# Study Assessment Caching Tests
# =============================================================================

class TestStudyAssessmentCaching:
    """Tests for study assessment caching."""

    def test_get_study_assessment_cache_hit(
        self, cache_manager, mock_db_manager, sample_study_assessment
    ):
        """Test cache hit for study assessment."""
        _, cursor = mock_db_manager
        cursor.fetchone.return_value = (sample_study_assessment, datetime.now())

        result = cache_manager.get_study_assessment(document_id=12345, version_id=1)

        assert result == sample_study_assessment
        cursor.execute.assert_called_once()

    def test_get_study_assessment_cache_miss(self, cache_manager, mock_db_manager):
        """Test cache miss for study assessment."""
        _, cursor = mock_db_manager
        cursor.fetchone.return_value = None

        result = cache_manager.get_study_assessment(document_id=12345, version_id=1)

        assert result is None

    def test_store_study_assessment_success(
        self, cache_manager, mock_db_manager, sample_study_assessment
    ):
        """Test storing study assessment in cache."""
        _, cursor = mock_db_manager

        result = cache_manager.store_study_assessment(
            document_id=12345,
            version_id=1,
            result=sample_study_assessment,
            execution_time_ms=1500
        )

        assert result is True
        cursor.execute.assert_called_once()
        call_args = cursor.execute.call_args
        assert "INSERT INTO results_cache.study_assessments" in call_args[0][0]

    def test_store_study_assessment_handles_error(
        self, cache_manager, mock_db_manager, sample_study_assessment
    ):
        """Test that store handles errors gracefully."""
        _, cursor = mock_db_manager
        cursor.execute.side_effect = Exception("Database error")

        result = cache_manager.store_study_assessment(
            document_id=12345,
            version_id=1,
            result=sample_study_assessment
        )

        assert result is False  # Should return False, not raise


# =============================================================================
# PICO Extraction Caching Tests
# =============================================================================

class TestPICOExtractionCaching:
    """Tests for PICO extraction caching."""

    def test_get_pico_extraction_cache_hit(
        self, cache_manager, mock_db_manager, sample_pico_extraction
    ):
        """Test cache hit for PICO extraction."""
        _, cursor = mock_db_manager
        cursor.fetchone.return_value = (sample_pico_extraction, datetime.now())

        result = cache_manager.get_pico_extraction(document_id=12345, version_id=1)

        assert result == sample_pico_extraction

    def test_store_pico_extraction_success(
        self, cache_manager, mock_db_manager, sample_pico_extraction
    ):
        """Test storing PICO extraction in cache."""
        _, cursor = mock_db_manager

        result = cache_manager.store_pico_extraction(
            document_id=12345,
            version_id=1,
            result=sample_pico_extraction,
            execution_time_ms=2000
        )

        assert result is True
        call_args = cursor.execute.call_args
        assert "INSERT INTO results_cache.pico_extractions" in call_args[0][0]


# =============================================================================
# PRISMA Assessment Caching Tests
# =============================================================================

class TestPRISMAAssessmentCaching:
    """Tests for PRISMA assessment caching."""

    def test_get_prisma_assessment_cache_hit(
        self, cache_manager, mock_db_manager, sample_prisma_assessment
    ):
        """Test cache hit for PRISMA assessment."""
        _, cursor = mock_db_manager
        cursor.fetchone.return_value = (sample_prisma_assessment, datetime.now())

        result = cache_manager.get_prisma_assessment(document_id=54321, version_id=1)

        assert result == sample_prisma_assessment

    def test_store_prisma_assessment_success(
        self, cache_manager, mock_db_manager, sample_prisma_assessment
    ):
        """Test storing PRISMA assessment in cache."""
        _, cursor = mock_db_manager

        result = cache_manager.store_prisma_assessment(
            document_id=54321,
            version_id=1,
            result=sample_prisma_assessment,
            execution_time_ms=3000
        )

        assert result is True
        call_args = cursor.execute.call_args
        assert "INSERT INTO results_cache.prisma_assessments" in call_args[0][0]


# =============================================================================
# Paper Weight Caching Tests
# =============================================================================

class TestPaperWeightCaching:
    """Tests for paper weight caching."""

    def test_get_paper_weight_cache_hit(
        self, cache_manager, mock_db_manager, sample_paper_weight
    ):
        """Test cache hit for paper weight."""
        _, cursor = mock_db_manager
        cursor.fetchone.return_value = (sample_paper_weight, datetime.now())

        result = cache_manager.get_paper_weight(document_id=12345, version_id=1)

        assert result == sample_paper_weight

    def test_get_paper_weight_cache_miss(self, cache_manager, mock_db_manager):
        """Test cache miss for paper weight."""
        _, cursor = mock_db_manager
        cursor.fetchone.return_value = None

        result = cache_manager.get_paper_weight(document_id=12345, version_id=1)

        assert result is None

    def test_store_paper_weight_success(
        self, cache_manager, mock_db_manager, sample_paper_weight
    ):
        """Test storing paper weight in cache."""
        _, cursor = mock_db_manager

        result = cache_manager.store_paper_weight(
            document_id=12345,
            version_id=1,
            result=sample_paper_weight,
            paper_weight_assessment_id=100,
            execution_time_ms=2500
        )

        assert result is True
        call_args = cursor.execute.call_args
        assert "INSERT INTO results_cache.paper_weight_cache" in call_args[0][0]

    def test_store_paper_weight_handles_error(
        self, cache_manager, mock_db_manager, sample_paper_weight
    ):
        """Test that store handles errors gracefully."""
        _, cursor = mock_db_manager
        cursor.execute.side_effect = Exception("Database error")

        result = cache_manager.store_paper_weight(
            document_id=12345,
            version_id=1,
            result=sample_paper_weight
        )

        assert result is False


# =============================================================================
# Suitability Check Caching Tests
# =============================================================================

class TestSuitabilityCheckCaching:
    """Tests for suitability check caching."""

    def test_get_suitability_check_pico_hit(
        self, cache_manager, mock_db_manager, sample_suitability_check
    ):
        """Test cache hit for PICO suitability check."""
        _, cursor = mock_db_manager
        cursor.fetchone.return_value = (sample_suitability_check, datetime.now())

        result = cache_manager.get_suitability_check(
            document_id=12345,
            check_type="pico",
            version_id=1
        )

        assert result == sample_suitability_check

    def test_get_suitability_check_prisma_hit(
        self, cache_manager, mock_db_manager
    ):
        """Test cache hit for PRISMA suitability check."""
        prisma_suitability = {
            "is_suitable": True,
            "confidence": 0.95,
            "rationale": "Systematic review with meta-analysis",
            "study_type": "systematic review",
        }
        _, cursor = mock_db_manager
        cursor.fetchone.return_value = (prisma_suitability, datetime.now())

        result = cache_manager.get_suitability_check(
            document_id=54321,
            check_type="prisma",
            version_id=1
        )

        assert result == prisma_suitability

    def test_store_suitability_check_success(
        self, cache_manager, mock_db_manager, sample_suitability_check
    ):
        """Test storing suitability check in cache."""
        _, cursor = mock_db_manager

        result = cache_manager.store_suitability_check(
            document_id=12345,
            check_type="pico",
            version_id=1,
            result=sample_suitability_check,
            execution_time_ms=500
        )

        assert result is True
        call_args = cursor.execute.call_args
        assert "INSERT INTO results_cache.suitability_checks" in call_args[0][0]


# =============================================================================
# Cache Statistics Tests
# =============================================================================

class TestCacheStatistics:
    """Tests for cache statistics."""

    def test_get_cache_statistics_success(self, cache_manager, mock_db_manager):
        """Test getting cache statistics."""
        _, cursor = mock_db_manager
        cursor.fetchone.return_value = (100, 50, 25, 75, 30, 10)  # Include paper_weight_count

        stats = cache_manager.get_cache_statistics()

        assert stats["study_assessments_cached"] == 100
        assert stats["pico_extractions_cached"] == 50
        assert stats["prisma_assessments_cached"] == 25
        assert stats["suitability_checks_cached"] == 75
        assert stats["paper_weight_cached"] == 30
        assert stats["total_versions"] == 10

    def test_get_cache_statistics_handles_error(self, cache_manager, mock_db_manager):
        """Test that statistics handles errors gracefully."""
        _, cursor = mock_db_manager
        cursor.execute.side_effect = Exception("Database error")

        stats = cache_manager.get_cache_statistics()

        assert stats == {}  # Should return empty dict on error


# =============================================================================
# Graceful Degradation Tests
# =============================================================================

class TestGracefulDegradation:
    """Tests for graceful degradation on cache failures."""

    def test_cache_miss_returns_none_not_error(self, cache_manager, mock_db_manager):
        """Test that cache miss returns None, not an error."""
        _, cursor = mock_db_manager
        cursor.fetchone.return_value = None

        # All get methods should return None on miss
        assert cache_manager.get_study_assessment(1, 1) is None
        assert cache_manager.get_pico_extraction(1, 1) is None
        assert cache_manager.get_prisma_assessment(1, 1) is None
        assert cache_manager.get_paper_weight(1, 1) is None
        assert cache_manager.get_suitability_check(1, "pico", 1) is None

    def test_db_error_on_get_returns_none(self, cache_manager, mock_db_manager):
        """Test that database error on get returns None."""
        _, cursor = mock_db_manager
        cursor.execute.side_effect = Exception("Connection lost")

        # Should return None, not raise exception
        assert cache_manager.get_study_assessment(1, 1) is None
        assert cache_manager.get_pico_extraction(1, 1) is None
        assert cache_manager.get_prisma_assessment(1, 1) is None
        assert cache_manager.get_paper_weight(1, 1) is None
        assert cache_manager.get_suitability_check(1, "pico", 1) is None

    def test_db_error_on_store_returns_false(
        self, cache_manager, mock_db_manager, sample_study_assessment
    ):
        """Test that database error on store returns False."""
        _, cursor = mock_db_manager
        cursor.execute.side_effect = Exception("Connection lost")

        # Should return False, not raise exception
        assert cache_manager.store_study_assessment(1, 1, sample_study_assessment) is False
        assert cache_manager.store_pico_extraction(1, 1, {}) is False
        assert cache_manager.store_prisma_assessment(1, 1, {}) is False
        assert cache_manager.store_paper_weight(1, 1, {}) is False
        assert cache_manager.store_suitability_check(1, "pico", 1, {}) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
