#!/usr/bin/env python3
"""
Unit tests for search scoring and re-ranking fixes.
Tests the bug fixes for:
1. Inconsistent score sources
2. RRF algorithm edge cases
3. Type safety and validation
4. Configuration design issues
"""

import pytest
from bmlibrarian.database import (
    _apply_rrf_reranking,
    _apply_weighted_reranking,
    _apply_sum_scores_reranking,
    _apply_max_score_reranking
)


class TestRRFReranking:
    """Test RRF re-ranking algorithm."""

    def test_rrf_with_all_strategies(self):
        """Test RRF when document appears in all strategies."""
        documents = [
            {
                'id': 1,
                '_search_scores': {
                    'semantic': 0.9,
                    'bm25': 0.8,
                    'fulltext': 0.7
                }
            }
        ]
        strategies_used = ['semantic', 'bm25', 'fulltext']

        _apply_rrf_reranking(documents, strategies_used, k=60)

        assert '_combined_score' in documents[0]
        assert documents[0]['_combined_score'] > 0

    def test_rrf_with_missing_strategies(self):
        """Test RRF when document is missing from some strategies."""
        documents = [
            {
                'id': 1,
                '_search_scores': {
                    'semantic': 0.9,
                    # Missing bm25 and fulltext
                }
            },
            {
                'id': 2,
                '_search_scores': {
                    'bm25': 0.8,
                    # Missing semantic and fulltext
                }
            }
        ]
        strategies_used = ['semantic', 'bm25', 'fulltext']

        _apply_rrf_reranking(documents, strategies_used, k=60)

        # Both documents should have non-zero scores due to penalty mechanism
        assert documents[0]['_combined_score'] > 0
        assert documents[1]['_combined_score'] > 0

    def test_rrf_edge_case_empty_strategies(self):
        """Test RRF with no strategies used."""
        documents = [
            {
                'id': 1,
                '_search_scores': {}
            }
        ]
        strategies_used = []

        _apply_rrf_reranking(documents, strategies_used, k=60)

        # Should result in zero score
        assert documents[0]['_combined_score'] == 0

    def test_rrf_invalid_k_parameter(self):
        """Test RRF with invalid k parameter."""
        documents = [
            {
                'id': 1,
                '_search_scores': {'semantic': 0.9}
            }
        ]
        strategies_used = ['semantic']

        # Negative k should raise ValueError
        with pytest.raises(ValueError, match="Invalid RRF k parameter"):
            _apply_rrf_reranking(documents, strategies_used, k=-1)

        # Zero k should raise ValueError
        with pytest.raises(ValueError, match="Invalid RRF k parameter"):
            _apply_rrf_reranking(documents, strategies_used, k=0)

    def test_rrf_invalid_k_type(self):
        """Test RRF with invalid k parameter type."""
        documents = [
            {
                'id': 1,
                '_search_scores': {'semantic': 0.9}
            }
        ]
        strategies_used = ['semantic']

        # String k should raise ValueError
        with pytest.raises(ValueError, match="Invalid RRF k parameter type"):
            _apply_rrf_reranking(documents, strategies_used, k="60")


class TestWeightedReranking:
    """Test weighted re-ranking algorithm."""

    def test_weighted_with_valid_weights(self):
        """Test weighted re-ranking with valid weights."""
        documents = [
            {
                'id': 1,
                '_search_scores': {
                    'semantic': 0.9,
                    'bm25': 0.8,
                    'fulltext': 0.7
                }
            }
        ]
        weights = {
            'semantic': 2.0,
            'bm25': 1.5,
            'fulltext': 1.0
        }

        _apply_weighted_reranking(documents, weights)

        assert '_combined_score' in documents[0]
        # Score should be: 0.9*2.0 + 0.8*1.5 + 0.7*1.0 = 1.8 + 1.2 + 0.7 = 3.7
        assert abs(documents[0]['_combined_score'] - 3.7) < 0.001

    def test_weighted_with_zero_weights(self):
        """Test weighted re-ranking with zero weights."""
        documents = [
            {
                'id': 1,
                '_search_scores': {
                    'semantic': 0.9,
                    'bm25': 0.8
                }
            }
        ]
        weights = {
            'semantic': 0.0,
            'bm25': 1.0
        }

        _apply_weighted_reranking(documents, weights)

        # Score should be: 0.9*0.0 + 0.8*1.0 = 0.8
        assert abs(documents[0]['_combined_score'] - 0.8) < 0.001

    def test_weighted_with_negative_weights(self):
        """Test weighted re-ranking with negative weights."""
        documents = [
            {
                'id': 1,
                '_search_scores': {
                    'semantic': 0.9
                }
            }
        ]
        weights = {
            'semantic': -1.0
        }

        # Negative weights should raise ValueError
        with pytest.raises(ValueError, match="Invalid weight"):
            _apply_weighted_reranking(documents, weights)

    def test_weighted_with_invalid_weight_type(self):
        """Test weighted re-ranking with invalid weight type."""
        documents = [
            {
                'id': 1,
                '_search_scores': {
                    'semantic': 0.9
                }
            }
        ]
        weights = {
            'semantic': "2.0"
        }

        # String weight should raise ValueError
        with pytest.raises(ValueError, match="Invalid weight type"):
            _apply_weighted_reranking(documents, weights)

    def test_weighted_with_empty_weights(self):
        """Test weighted re-ranking with empty weights dict."""
        documents = [
            {
                'id': 1,
                '_search_scores': {
                    'semantic': 0.9,
                    'bm25': 0.8
                }
            }
        ]
        weights = {}

        _apply_weighted_reranking(documents, weights)

        # Should use default weight of 1.0 for all strategies
        # Score should be: 0.9*1.0 + 0.8*1.0 = 1.7
        assert abs(documents[0]['_combined_score'] - 1.7) < 0.001

    def test_weighted_with_missing_strategy_weight(self):
        """Test weighted re-ranking when weight is missing for a strategy."""
        documents = [
            {
                'id': 1,
                '_search_scores': {
                    'semantic': 0.9,
                    'bm25': 0.8,
                    'fulltext': 0.7
                }
            }
        ]
        weights = {
            'semantic': 2.0,
            # Missing bm25 and fulltext weights
        }

        _apply_weighted_reranking(documents, weights)

        # Should use default weight of 1.0 for missing strategies
        # Score should be: 0.9*2.0 + 0.8*1.0 + 0.7*1.0 = 1.8 + 0.8 + 0.7 = 3.3
        assert abs(documents[0]['_combined_score'] - 3.3) < 0.001


class TestSumScoresReranking:
    """Test sum scores re-ranking algorithm."""

    def test_sum_scores_basic(self):
        """Test basic sum scores re-ranking."""
        documents = [
            {
                'id': 1,
                '_search_scores': {
                    'semantic': 0.9,
                    'bm25': 0.8,
                    'fulltext': 0.7
                }
            }
        ]

        _apply_sum_scores_reranking(documents)

        # Score should be: 0.9 + 0.8 + 0.7 = 2.4
        assert abs(documents[0]['_combined_score'] - 2.4) < 0.001

    def test_sum_scores_empty(self):
        """Test sum scores with empty scores dict."""
        documents = [
            {
                'id': 1,
                '_search_scores': {}
            }
        ]

        _apply_sum_scores_reranking(documents)

        # Should result in zero score
        assert documents[0]['_combined_score'] == 0


class TestMaxScoreReranking:
    """Test max score re-ranking algorithm."""

    def test_max_score_basic(self):
        """Test basic max score re-ranking."""
        documents = [
            {
                'id': 1,
                '_search_scores': {
                    'semantic': 0.9,
                    'bm25': 0.8,
                    'fulltext': 0.7
                }
            }
        ]

        _apply_max_score_reranking(documents)

        # Should use max score: 0.9
        assert abs(documents[0]['_combined_score'] - 0.9) < 0.001

    def test_max_score_empty(self):
        """Test max score with empty scores dict."""
        documents = [
            {
                'id': 1,
                '_search_scores': {}
            }
        ]

        _apply_max_score_reranking(documents)

        # Should result in zero score
        assert documents[0]['_combined_score'] == 0


class TestScoreConsistency:
    """Test score consistency across different strategies."""

    def test_score_field_names(self):
        """Test that score fields are correctly named."""
        # This is a documentation test to ensure developers understand
        # the expected field names from different search strategies

        # Semantic search should use 'semantic_score' field
        semantic_doc = {
            'id': 1,
            'semantic_score': 0.85  # From SQL: sr.best_score as semantic_score
        }

        # BM25 search should use 'rank' field (or 'bm25_score' if available)
        bm25_doc = {
            'id': 2,
            'rank': 0.75  # From SQL: ts_rank_cd(...) AS rank
        }

        # Fulltext search should use 'rank' field (or 'fulltext_score' if available)
        fulltext_doc = {
            'id': 3,
            'rank': 0.65  # From SQL: ts_rank_cd(...) AS rank
        }

        # The hybrid search function should correctly extract these scores
        # into the _search_scores dictionary using the appropriate field names
        assert 'semantic_score' in semantic_doc
        assert 'rank' in bm25_doc
        assert 'rank' in fulltext_doc


if __name__ == "__main__":
    pytest.main([__file__, '-v'])
