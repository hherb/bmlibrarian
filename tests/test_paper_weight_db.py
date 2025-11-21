"""
Tests for paper_weight_db.py

Tests cover:
- Replication score calculation
- Database function signatures (mocked)
- Edge cases for scoring logic
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from bmlibrarian.agents.paper_weight_db import (
    REPLICATION_SCORE_SINGLE_COMPARABLE,
    REPLICATION_SCORE_SINGLE_HIGHER,
    REPLICATION_SCORE_MULTIPLE_COMPARABLE,
    REPLICATION_SCORE_MULTIPLE_HIGHER,
    REPLICATION_SCORE_LOWER_QUALITY,
    _calculate_replication_score,
    _reconstruct_result_from_db,
)
from bmlibrarian.agents.paper_weight_models import (
    DimensionScore,
    PaperWeightResult,
    DIMENSION_STUDY_DESIGN,
    DIMENSION_SAMPLE_SIZE,
    DIMENSION_METHODOLOGICAL_QUALITY,
    DIMENSION_RISK_OF_BIAS,
    DIMENSION_REPLICATION_STATUS,
)


class TestCalculateReplicationScore:
    """Tests for _calculate_replication_score function."""

    def test_single_replication_comparable(self):
        """Test score for single replication of comparable quality."""
        score = _calculate_replication_score(1, 'comparable')
        assert score == REPLICATION_SCORE_SINGLE_COMPARABLE
        assert score == 5.0

    def test_single_replication_higher(self):
        """Test score for single replication of higher quality."""
        score = _calculate_replication_score(1, 'higher')
        assert score == REPLICATION_SCORE_SINGLE_HIGHER
        assert score == 8.0

    def test_multiple_replications_comparable(self):
        """Test score for multiple replications of comparable quality."""
        score = _calculate_replication_score(2, 'comparable')
        assert score == REPLICATION_SCORE_MULTIPLE_COMPARABLE
        assert score == 8.0

        # Test with more than 2
        score = _calculate_replication_score(5, 'comparable')
        assert score == REPLICATION_SCORE_MULTIPLE_COMPARABLE

    def test_multiple_replications_higher(self):
        """Test score for multiple replications of higher quality."""
        score = _calculate_replication_score(2, 'higher')
        assert score == REPLICATION_SCORE_MULTIPLE_HIGHER
        assert score == 10.0

        # Test with more than 2
        score = _calculate_replication_score(10, 'higher')
        assert score == REPLICATION_SCORE_MULTIPLE_HIGHER

    def test_lower_quality_replications(self):
        """Test score for lower quality replications."""
        score = _calculate_replication_score(1, 'lower')
        assert score == REPLICATION_SCORE_LOWER_QUALITY
        assert score == 3.0

        score = _calculate_replication_score(3, 'lower')
        assert score == REPLICATION_SCORE_LOWER_QUALITY

    def test_unknown_quality(self):
        """Test score for unknown quality (defaults to lower)."""
        score = _calculate_replication_score(1, 'unknown')
        assert score == REPLICATION_SCORE_LOWER_QUALITY


class TestReconstructResultFromDb:
    """Tests for _reconstruct_result_from_db function."""

    def test_basic_reconstruction(self):
        """Test basic reconstruction from database rows."""
        assessment_row = (
            1,  # assessment_id
            12345,  # document_id
            datetime(2024, 1, 15, 10, 30, 0),  # assessed_at
            '1.0.0',  # assessor_version
            8.0,  # study_design_score
            7.5,  # sample_size_score
            6.5,  # methodological_quality_score
            7.0,  # risk_of_bias_score
            5.0,  # replication_status_score
            7.2,  # final_weight
            '{"study_design": 0.25, "sample_size": 0.15}',  # dimension_weights (JSON string)
            'rct',  # study_type
            450  # sample_size
        )
        
        detail_rows = [
            (DIMENSION_STUDY_DESIGN, 'study_type', 'rct', 8.0, 'evidence', 'reasoning'),
            (DIMENSION_SAMPLE_SIZE, 'extracted_n', '450', 5.3, 'n=450', 'log calculation'),
        ]
        
        result = _reconstruct_result_from_db(assessment_row, detail_rows)
        
        assert isinstance(result, PaperWeightResult)
        assert result.document_id == 12345
        assert result.assessor_version == '1.0.0'
        assert result.study_design.score == 8.0
        assert result.sample_size.score == 7.5
        assert result.final_weight == 7.2
        assert result.study_type == 'rct'
        assert result.sample_size_n == 450
        
        # Check details were reconstructed
        assert len(result.study_design.details) == 1
        assert result.study_design.details[0].extracted_value == 'rct'
        assert len(result.sample_size.details) == 1

    def test_reconstruction_with_dict_weights(self):
        """Test reconstruction when dimension_weights is already a dict."""
        assessment_row = (
            1, 12345, datetime.now(), '1.0.0',
            8.0, 7.5, 6.5, 7.0, 5.0, 7.2,
            {'study_design': 0.25},  # Already a dict
            'rct', 450
        )
        
        result = _reconstruct_result_from_db(assessment_row, [])
        
        assert result.dimension_weights == {'study_design': 0.25}

    def test_reconstruction_with_no_details(self):
        """Test reconstruction with empty details."""
        assessment_row = (
            1, 12345, datetime.now(), '1.0.0',
            5.0, 5.0, 5.0, 5.0, 0.0, 4.0,
            '{}', None, None
        )
        
        result = _reconstruct_result_from_db(assessment_row, [])
        
        assert result.study_type is None
        assert result.sample_size_n is None
        assert len(result.study_design.details) == 0

    def test_reconstruction_filters_unknown_dimensions(self):
        """Test that unknown dimension details are filtered out."""
        assessment_row = (
            1, 12345, datetime.now(), '1.0.0',
            5.0, 5.0, 5.0, 5.0, 0.0, 4.0,
            '{}', None, None
        )
        
        detail_rows = [
            (DIMENSION_STUDY_DESIGN, 'study_type', 'rct', 8.0, '', ''),
            ('unknown_dimension', 'component', 'value', 1.0, '', ''),  # Should be ignored
        ]
        
        result = _reconstruct_result_from_db(assessment_row, detail_rows)
        
        # Only study_design should have details
        total_details = len(result.get_all_details())
        assert total_details == 1

    def test_reconstruction_handles_none_score_contribution(self):
        """Test that None score_contribution is handled."""
        assessment_row = (
            1, 12345, datetime.now(), '1.0.0',
            5.0, 5.0, 5.0, 5.0, 0.0, 4.0,
            '{}', None, None
        )
        
        detail_rows = [
            (DIMENSION_STUDY_DESIGN, 'study_type', 'unknown', None, '', ''),  # None score
        ]
        
        result = _reconstruct_result_from_db(assessment_row, detail_rows)
        
        assert result.study_design.details[0].score_contribution == 0.0


class TestConstants:
    """Tests for module constants."""

    def test_replication_score_constants(self):
        """Test replication score constant values."""
        assert REPLICATION_SCORE_SINGLE_COMPARABLE == 5.0
        assert REPLICATION_SCORE_SINGLE_HIGHER == 8.0
        assert REPLICATION_SCORE_MULTIPLE_COMPARABLE == 8.0
        assert REPLICATION_SCORE_MULTIPLE_HIGHER == 10.0
        assert REPLICATION_SCORE_LOWER_QUALITY == 3.0

    def test_score_constants_are_in_valid_range(self):
        """Test that all score constants are in 0-10 range."""
        constants = [
            REPLICATION_SCORE_SINGLE_COMPARABLE,
            REPLICATION_SCORE_SINGLE_HIGHER,
            REPLICATION_SCORE_MULTIPLE_COMPARABLE,
            REPLICATION_SCORE_MULTIPLE_HIGHER,
            REPLICATION_SCORE_LOWER_QUALITY,
        ]
        for const in constants:
            assert 0.0 <= const <= 10.0
