"""
Unit tests for iterative document search functionality.

Tests the QueryAgent's find_abstracts_iterative() method which implements
a two-phase search strategy to find a minimum number of relevant documents.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from typing import List, Dict

from bmlibrarian.agents.query_agent import QueryAgent
from bmlibrarian.agents.scoring_agent import DocumentScoringAgent


# Mock document factory
def create_mock_document(doc_id: int, title: str = None) -> Dict:
    """Create a mock document for testing."""
    return {
        'id': doc_id,
        'title': title or f'Document {doc_id}',
        'abstract': f'Abstract for document {doc_id}',
        'authors': 'Test Author',
        'year': 2023
    }


# Mock scoring result factory
def create_mock_score(score: int, reasoning: str = None) -> Dict:
    """Create a mock scoring result."""
    return {
        'score': score,
        'reasoning': reasoning or f'Scored {score} because...'
    }


class TestIterativeSearch:
    """Tests for iterative document search functionality."""

    @pytest.fixture
    def query_agent(self):
        """Create a QueryAgent instance for testing."""
        agent = QueryAgent(show_model_info=False)
        return agent

    @pytest.fixture
    def scoring_agent(self):
        """Create a mock DocumentScoringAgent for testing."""
        agent = Mock(spec=DocumentScoringAgent)
        return agent

    def test_early_stop_when_min_relevant_met(self, query_agent, scoring_agent):
        """Test that search stops early when min_relevant documents are found."""
        # Setup: First batch has enough high-scoring documents
        batch1_docs = [create_mock_document(i) for i in range(1, 6)]

        # Mock convert_question
        query_agent.convert_question = Mock(return_value='test & query')

        # Mock find_abstracts to return batch1 on first call, empty on second
        query_agent.find_abstracts = Mock(side_effect=[batch1_docs, []])

        # Mock scoring: all docs score above threshold
        def mock_evaluate(question, doc):
            return create_mock_score(4)  # All docs score 4
        scoring_agent.evaluate_document = Mock(side_effect=mock_evaluate)

        # Execute with min_relevant=3
        all_docs, scored_docs = query_agent.find_abstracts_iterative(
            question="test question",
            min_relevant=3,
            score_threshold=2.5,
            max_retry=3,
            batch_size=5,
            scoring_agent=scoring_agent
        )

        # Verify: Should stop after first batch
        assert len(all_docs) == 5
        assert len(scored_docs) == 5
        assert query_agent.find_abstracts.call_count == 1

        # All should be above threshold
        high_scoring = [s for d, s in scored_docs if s['score'] >= 2.5]
        assert len(high_scoring) == 5

    def test_offset_based_pagination(self, query_agent, scoring_agent):
        """Test offset-based pagination when first batch insufficient."""
        # Setup: Multiple batches needed
        batch1 = [create_mock_document(i) for i in range(1, 4)]  # 3 docs
        batch2 = [create_mock_document(i) for i in range(4, 7)]  # 3 more docs

        query_agent.convert_question = Mock(return_value='test & query')
        query_agent.find_abstracts = Mock(side_effect=[batch1, batch2, []])

        # Mock scoring: First batch has 2 high-scoring, second batch has 3 high-scoring
        def mock_evaluate(question, doc):
            if doc['id'] <= 2:
                return create_mock_score(3)  # First 2 docs: score 3
            elif doc['id'] <= 3:
                return create_mock_score(2)  # Doc 3: score 2 (below threshold)
            else:
                return create_mock_score(4)  # Batch 2: all score 4
        scoring_agent.evaluate_document = Mock(side_effect=mock_evaluate)

        # Execute with min_relevant=5
        all_docs, scored_docs = query_agent.find_abstracts_iterative(
            question="test question",
            min_relevant=5,
            score_threshold=2.5,
            max_retry=3,
            batch_size=3,
            scoring_agent=scoring_agent
        )

        # Verify: Should fetch 2 batches
        assert len(all_docs) == 6
        assert query_agent.find_abstracts.call_count == 2

        # Check high-scoring count
        high_scoring = [s for d, s in scored_docs if s['score'] >= 2.5]
        assert len(high_scoring) == 5  # 2 from batch1 + 3 from batch2

    def test_query_modification_when_offset_exhausted(self, query_agent, scoring_agent):
        """Test query modification when offset pagination is exhausted."""
        # Setup: Small initial result set
        batch1 = [create_mock_document(i) for i in range(1, 3)]  # 2 docs
        modified_batch = [create_mock_document(i) for i in range(10, 15)]  # 5 new docs

        query_agent.convert_question = Mock(return_value='test & query')

        # First call returns batch1, second returns empty (exhausted),
        # then modified query returns new docs
        query_agent.find_abstracts = Mock(side_effect=[batch1, []])

        # Mock _generate_broader_query
        query_agent._generate_broader_query = Mock(return_value='broader | query')

        # Mock database call for modified query
        with patch('bmlibrarian.agents.query_agent.find_abstracts') as mock_db_find:
            mock_db_find.return_value = modified_batch

            # Mock scoring: batch1 has 1 high-scoring, modified batch has 4
            def mock_evaluate(question, doc):
                if doc['id'] < 10:
                    return create_mock_score(1 if doc['id'] == 2 else 3)
                else:
                    return create_mock_score(4)
            scoring_agent.evaluate_document = Mock(side_effect=mock_evaluate)

            # Execute
            all_docs, scored_docs = query_agent.find_abstracts_iterative(
                question="test question",
                min_relevant=4,
                score_threshold=2.5,
                max_retry=3,
                batch_size=2,
                scoring_agent=scoring_agent
            )

            # Verify: Should try query modification
            assert query_agent._generate_broader_query.call_count >= 1
            assert len(all_docs) >= 2  # At least the initial batch

    def test_progress_callback_invoked(self, query_agent, scoring_agent):
        """Test that progress callback is called during search."""
        batch1 = [create_mock_document(i) for i in range(1, 4)]

        query_agent.convert_question = Mock(return_value='test & query')
        query_agent.find_abstracts = Mock(return_value=batch1)

        scoring_agent.evaluate_document = Mock(return_value=create_mock_score(4))

        # Create progress callback mock
        progress_callback = Mock()

        # Execute
        query_agent.find_abstracts_iterative(
            question="test question",
            min_relevant=3,
            score_threshold=2.5,
            max_retry=3,
            batch_size=3,
            scoring_agent=scoring_agent,
            progress_callback=progress_callback
        )

        # Verify callback was called
        assert progress_callback.call_count > 0

        # Check that at least one call mentions success
        calls_text = [str(call) for call in progress_callback.call_args_list]
        assert any('Success' in str(call) or 'complete' in str(call).lower() for call in calls_text)

    def test_deduplication_of_documents(self, query_agent, scoring_agent):
        """Test that duplicate documents are not processed multiple times."""
        # Setup: Overlapping batches (simulating duplicates)
        batch1 = [create_mock_document(1), create_mock_document(2)]
        batch2 = [create_mock_document(2), create_mock_document(3)]  # Doc 2 is duplicate

        query_agent.convert_question = Mock(return_value='test & query')
        query_agent.find_abstracts = Mock(side_effect=[batch1, batch2, []])

        # Mock the database find_abstracts as well (for Phase 2 query modification)
        with patch('bmlibrarian.agents.query_agent.find_abstracts') as mock_db_find:
            mock_db_find.return_value = iter([])  # Return empty iterator for Phase 2

            scoring_agent.evaluate_document = Mock(return_value=create_mock_score(2))

            # Execute
            all_docs, scored_docs = query_agent.find_abstracts_iterative(
                question="test question",
                min_relevant=5,  # More than we can find to test exhaustion
                score_threshold=1.5,
                max_retry=3,
                batch_size=2,
                scoring_agent=scoring_agent
            )

        # Verify: Should only have unique docs
        doc_ids = [doc['id'] for doc in all_docs]
        assert len(doc_ids) == len(set(doc_ids))  # All unique
        assert len(all_docs) == 3  # Only 3 unique docs

    def test_scoring_failure_handling(self, query_agent, scoring_agent):
        """Test graceful handling of scoring failures."""
        batch1 = [create_mock_document(i) for i in range(1, 4)]

        query_agent.convert_question = Mock(return_value='test & query')
        query_agent.find_abstracts = Mock(return_value=batch1)

        # Mock scoring to fail for doc 2
        def mock_evaluate(question, doc):
            if doc['id'] == 2:
                raise Exception("Scoring failed")
            return create_mock_score(4)

        scoring_agent.evaluate_document = Mock(side_effect=mock_evaluate)

        # Execute - should not raise exception
        all_docs, scored_docs = query_agent.find_abstracts_iterative(
            question="test question",
            min_relevant=2,
            score_threshold=2.5,
            max_retry=3,
            batch_size=3,
            scoring_agent=scoring_agent
        )

        # Verify: Should have all docs but only 2 scored successfully
        assert len(all_docs) == 3
        assert len(scored_docs) == 2  # Only docs 1 and 3

    def test_no_scoring_agent_raises_error(self, query_agent):
        """Test that missing scoring_agent raises ValueError."""
        with pytest.raises(ValueError, match="scoring_agent is required"):
            query_agent.find_abstracts_iterative(
                question="test question",
                min_relevant=5,
                score_threshold=2.5,
                scoring_agent=None
            )

    def test_insufficient_documents_warning(self, query_agent, scoring_agent):
        """Test behavior when database has fewer than min_relevant docs."""
        # Setup: Only 2 docs available
        batch1 = [create_mock_document(1), create_mock_document(2)]

        query_agent.convert_question = Mock(return_value='test & query')
        query_agent.find_abstracts = Mock(side_effect=[batch1, [], []])
        query_agent._generate_broader_query = Mock(return_value='broader | query')

        # Mock database returns nothing for broader query
        with patch('bmlibrarian.agents.query_agent.find_abstracts') as mock_db_find:
            mock_db_find.return_value = []

            scoring_agent.evaluate_document = Mock(return_value=create_mock_score(4))

            # Execute with min_relevant=10 (more than available)
            all_docs, scored_docs = query_agent.find_abstracts_iterative(
                question="test question",
                min_relevant=10,
                score_threshold=2.5,
                max_retry=3,
                batch_size=2,
                scoring_agent=scoring_agent
            )

            # Verify: Returns what's available
            assert len(all_docs) == 2
            assert len(scored_docs) == 2

    def test_max_retry_limits_applied(self, query_agent, scoring_agent):
        """Test that max_retry limits are properly enforced."""
        # Setup: Always return empty to test retry exhaustion
        query_agent.convert_question = Mock(return_value='test & query')
        query_agent.find_abstracts = Mock(return_value=[])
        query_agent._generate_broader_query = Mock(return_value='broader | query')

        with patch('bmlibrarian.agents.query_agent.find_abstracts') as mock_db_find:
            mock_db_find.return_value = []

            # Execute with max_retry=2
            all_docs, scored_docs = query_agent.find_abstracts_iterative(
                question="test question",
                min_relevant=10,
                score_threshold=2.5,
                max_retry=2,
                batch_size=5,
                scoring_agent=scoring_agent
            )

            # Verify: Should not exceed max_retry attempts
            # Phase 1: 2 offset-based attempts
            # Phase 2: 2*2=4 query modification attempts
            # Total find_abstracts calls should be <= 2 (offset phase)
            assert query_agent.find_abstracts.call_count <= 2

            # Should have tried query modification up to max_retry*max_retry times
            assert query_agent._generate_broader_query.call_count <= 4


class TestBroaderQueryGeneration:
    """Tests for _generate_broader_query helper method."""

    @pytest.fixture
    def query_agent(self):
        """Create a QueryAgent instance for testing."""
        agent = QueryAgent(show_model_info=False)
        return agent

    def test_broader_query_generation(self, query_agent):
        """Test successful broader query generation."""
        # Mock LLM response via _make_ollama_request
        query_agent._make_ollama_request = Mock(return_value='(aspirin | antiplatelet) & heart')

        broader = query_agent._generate_broader_query(
            original_query='aspirin & heart',
            user_question='aspirin and heart disease',
            attempt=1
        )

        # Note: fix_tsquery_syntax removes spaces, which is correct for PostgreSQL
        assert broader == '(aspirin|antiplatelet)&heart'
        assert query_agent._make_ollama_request.call_count == 1

    def test_broader_query_fallback_on_error(self, query_agent):
        """Test fallback to original query on error."""
        # Mock LLM to raise exception
        query_agent._make_ollama_request = Mock(side_effect=Exception("LLM error"))

        original = 'aspirin & heart'
        broader = query_agent._generate_broader_query(
            original_query=original,
            user_question='aspirin and heart disease',
            attempt=1
        )

        # Should fall back to original
        assert broader == original

    def test_broader_query_invalid_response(self, query_agent):
        """Test handling of invalid LLM response."""
        # Mock LLM to return empty/invalid response
        query_agent._make_ollama_request = Mock(return_value='')

        original = 'aspirin & heart'
        broader = query_agent._generate_broader_query(
            original_query=original,
            user_question='aspirin and heart disease',
            attempt=1
        )

        # Should fall back to original
        assert broader == original

    def test_progressive_broadening_instructions(self, query_agent):
        """Test that attempt number affects broadening strategy."""
        query_agent._make_ollama_request = Mock(return_value='broader query')

        # Call with different attempt numbers
        for attempt in [1, 2, 3]:
            query_agent._generate_broader_query(
                original_query='test & query',
                user_question='test question',
                attempt=attempt
            )

        # Verify _make_ollama_request was called 3 times
        assert query_agent._make_ollama_request.call_count == 3

        # Check that prompts mention the attempt number
        for call_args in query_agent._make_ollama_request.call_args_list:
            # The prompt is in messages[0]['content']
            messages = call_args[0][0]  # First positional arg
            prompt = messages[0]['content']
            assert 'Broadening Attempt:' in prompt or 'attempt' in prompt.lower()
