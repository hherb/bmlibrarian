"""
Tests for CitationFinderAgent

Tests citation extraction, queue processing, and document verification.
"""

import json
import unittest
from unittest.mock import Mock, patch
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bmlibrarian.agents.citation_agent import CitationFinderAgent, Citation

from llm_test_support import patch_llm


class TestCitationFinderAgent(unittest.TestCase):
    """Test cases for CitationFinderAgent functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_orchestrator = Mock()
        self.agent = CitationFinderAgent(
            orchestrator=self.mock_orchestrator,
            host="http://test:11434",
            model="test-model",
            show_model_info=False
        )
        
        # Sample document for testing (using realistic database ID)
        self.sample_document = {
            'id': 12345678,  # Database-style integer ID
            'title': 'COVID-19 Vaccine Effectiveness Study',
            'abstract': 'This study shows that COVID-19 vaccines are 95% effective in preventing severe disease. We studied 10,000 participants over 6 months.',
            'authors': ['Smith, J.', 'Doe, A.'],
            'publication_date': '2023-01-15',
            'pmid': '12345678'
        }
        
        self.sample_question = "What is the effectiveness of COVID-19 vaccines?"
    
    def test_citation_creation(self):
        """Test Citation dataclass creation and validation."""
        citation = Citation(
            passage="COVID-19 vaccines are 95% effective in preventing severe disease",
            summary="Study shows high vaccine effectiveness",
            relevance_score=0.9,
            document_id="test_doc_001",
            document_title="Test Study",
            authors=["Author, A."],
            publication_date="2023-01-01"
        )
        
        self.assertEqual(citation.passage, "COVID-19 vaccines are 95% effective in preventing severe disease")
        self.assertEqual(citation.relevance_score, 0.9)
        self.assertEqual(citation.document_id, "test_doc_001")
        self.assertIsNotNone(citation.created_at)
        self.assertIsInstance(citation.created_at, datetime)
    
    def test_connection_success(self):
        """Test successful connection to Ollama with the model available."""
        with patch.object(self.agent._llm_client, 'test_provider', return_value=True), \
             patch.object(self.agent._llm_client, 'list_models',
                          return_value={'ollama': ['test-model']}):
            self.assertTrue(self.agent.test_connection())

    def test_connection_model_missing(self):
        """Test connection check fails when the model is not installed."""
        with patch.object(self.agent._llm_client, 'test_provider', return_value=True), \
             patch.object(self.agent._llm_client, 'list_models',
                          return_value={'ollama': ['other-model']}):
            self.assertFalse(self.agent.test_connection())

    def test_connection_failure(self):
        """Test failed connection to Ollama."""
        with patch.object(self.agent._llm_client, 'test_provider',
                          side_effect=Exception("Connection error")):
            self.assertFalse(self.agent.test_connection())
    
    def test_extract_citation_success(self):
        """Test successful citation extraction."""
        # Mock connection and Ollama client response
        # Model response with EXACT text from abstract
        # Abstract: 'This study shows that COVID-19 vaccines are 95% effective in preventing severe disease. We studied 10,000 participants over 6 months.'
        response = json.dumps({
            'relevant_passage': 'COVID-19 vaccines are 95% effective in preventing severe disease.',
            'summary': 'Study demonstrates high vaccine effectiveness',
            'relevance_score': 0.9,
            'has_relevant_content': True
        })
        with patch.object(self.agent, 'test_connection', return_value=True), \
             patch_llm(response):

            result = self.agent.extract_citation_from_document(
                self.sample_question,
                self.sample_document,
                min_relevance=0.7
            )

            self.assertIsNotNone(result)
            self.assertIsInstance(result, Citation)
            # Validation should extract exact text from abstract
            self.assertIn('vaccines are 95% effective', result.passage)
            self.assertEqual(result.relevance_score, 0.9)
            self.assertEqual(result.document_id, '12345678')
            self.assertEqual(result.document_title, self.sample_document['title'])
    
    def test_extract_citation_low_relevance(self):
        """Test citation extraction with low relevance score."""
        response = json.dumps({
            'relevant_passage': 'We studied 10,000 participants over 6 months.',
            'summary': 'Not very relevant',
            'relevance_score': 0.5,
            'has_relevant_content': True
        })
        with patch.object(self.agent, 'test_connection', return_value=True), \
             patch_llm(response) as mock_chat:
            result = self.agent.extract_citation_from_document(
                self.sample_question,
                self.sample_document,
                min_relevance=0.7  # Higher than returned score
            )

        self.assertIsNone(result)
        mock_chat.assert_called_once()

    def test_extract_citation_no_relevant_content(self):
        """Test citation extraction when no relevant content found."""
        response = json.dumps({
            'has_relevant_content': False,
            'relevance_score': 0.0
        })
        with patch.object(self.agent, 'test_connection', return_value=True), \
             patch_llm(response) as mock_chat:
            result = self.agent.extract_citation_from_document(
                self.sample_question,
                self.sample_document
            )

        self.assertIsNone(result)
        mock_chat.assert_called_once()
    
    def test_extract_citation_no_abstract(self):
        """Test citation extraction from document without abstract."""
        doc_no_abstract = self.sample_document.copy()
        del doc_no_abstract['abstract']
        
        result = self.agent.extract_citation_from_document(
            self.sample_question,
            doc_no_abstract
        )
        
        self.assertIsNone(result)
    
    def test_extract_citation_no_connection(self):
        """Test citation extraction without Ollama connection."""
        with patch.object(self.agent._llm_client, 'test_provider',
                          side_effect=Exception("Connection failed")), \
             patch_llm('{}') as mock_chat:
            result = self.agent.extract_citation_from_document(
                self.sample_question,
                self.sample_document
            )

        self.assertIsNone(result)
        mock_chat.assert_not_called()
    
    def test_process_scored_documents_filtering(self):
        """Test filtering of scored documents by threshold."""
        scored_documents = [
            (self.sample_document, {'score': 4.5}),
            ({'id': 'doc2', 'title': 'Low score doc', 'abstract': 'text'}, {'score': 1.5}),
            ({'id': 'doc3', 'title': 'High score doc', 'abstract': 'text'}, {'score': 3.5}),
        ]
        
        # Mock the citation extraction to return None (no Ollama connection)
        with patch.object(self.agent, 'extract_citation_from_document', return_value=None):
            citations = self.agent.process_scored_documents_for_citations(
                user_question=self.sample_question,
                scored_documents=scored_documents,
                score_threshold=3.0
            )
            
            # Should process only 2 documents above threshold 3.0
            # extract_citation_from_document should be called twice
            self.assertEqual(self.agent.extract_citation_from_document.call_count, 2)
    
    def test_submit_citation_extraction_tasks(self):
        """Test submitting citation tasks to queue."""
        scored_documents = [
            (self.sample_document, {'score': 4.5}),
            ({'id': 'doc2', 'title': 'Another doc', 'abstract': 'text'}, {'score': 3.5}),
        ]
        
        # Mock orchestrator's submit_batch_tasks
        expected_task_ids = ['task_1', 'task_2']
        self.agent.submit_batch_tasks = Mock(return_value=expected_task_ids)
        
        task_ids = self.agent.submit_citation_extraction_tasks(
            user_question=self.sample_question,
            scored_documents=scored_documents,
            score_threshold=3.0
        )
        
        self.assertEqual(task_ids, expected_task_ids)
        self.agent.submit_batch_tasks.assert_called_once()
        
        # Check the submitted data
        call_args = self.agent.submit_batch_tasks.call_args
        self.assertEqual(call_args[1]['method_name'], 'extract_citation_from_queue')
        self.assertEqual(len(call_args[1]['data_list']), 2)  # Both documents above threshold
    
    def test_submit_citation_tasks_no_qualifying_docs(self):
        """Test submitting tasks when no documents meet threshold."""
        scored_documents = [
            (self.sample_document, {'score': 1.5}),  # Below threshold
            ({'id': 'doc2'}, {'score': 2.0}),        # Below threshold
        ]
        
        task_ids = self.agent.submit_citation_extraction_tasks(
            user_question=self.sample_question,
            scored_documents=scored_documents,
            score_threshold=3.0
        )
        
        self.assertEqual(task_ids, [])
    
    def test_submit_citation_tasks_no_orchestrator(self):
        """Test submitting tasks without orchestrator."""
        agent = CitationFinderAgent()  # No orchestrator
        
        task_ids = agent.submit_citation_extraction_tasks(
            user_question=self.sample_question,
            scored_documents=[(self.sample_document, {'score': 4.0})],
        )
        
        self.assertIsNone(task_ids)
    
    def test_extract_citation_from_queue(self):
        """Test queue-compatible citation extraction method."""
        # Mock connection and Ollama client response
        # Model response with EXACT text from abstract
        response = json.dumps({
            'relevant_passage': 'We studied 10,000 participants over 6 months.',
            'summary': 'Large study with long follow-up',
            'relevance_score': 0.8,
            'has_relevant_content': True
        })
        with patch.object(self.agent, 'test_connection', return_value=True), \
             patch_llm(response):

            result = self.agent.extract_citation_from_queue(
                user_question=self.sample_question,
                document=self.sample_document,
                score_result={'score': 4.0, 'reasoning': 'Test'},
                score_threshold=2.0,
                min_relevance=0.7
            )

            self.assertTrue(result['has_citation'])
            # Validation should extract exact text from abstract
            self.assertIn('10,000 participants', result['passage'])
            self.assertEqual(result['summary'], 'Large study with long follow-up')
            self.assertEqual(result['relevance_score'], 0.8)
            self.assertEqual(result['document_id'], '12345678')
    
    def test_extract_citation_from_queue_no_citation(self):
        """Test queue method when no citation found."""
        with patch.object(self.agent, 'extract_citation_from_document', return_value=None):
            result = self.agent.extract_citation_from_queue(
                user_question=self.sample_question,
                document=self.sample_document,
                score_result={'score': 4.0, 'reasoning': 'Test'},
                score_threshold=2.0
            )
            
            self.assertFalse(result['has_citation'])
    
    def test_verify_document_exists(self):
        """Test document verification (currently always returns True)."""
        result = self.agent.verify_document_exists('12345678')
        self.assertTrue(result)
    
    def test_get_citation_stats_empty(self):
        """Test statistics calculation with no citations."""
        stats = self.agent.get_citation_stats([])
        
        expected = {
            'total_citations': 0,
            'average_relevance': 0.0,
            'unique_documents': 0,
            'date_range': None
        }
        
        self.assertEqual(stats, expected)
    
    def test_get_citation_stats_with_citations(self):
        """Test statistics calculation with citations."""
        citations = [
            Citation(
                passage="passage1", summary="summary1", relevance_score=0.9,
                document_id="doc1", document_title="title1", authors=["A1"],
                publication_date="2023-01-01"
            ),
            Citation(
                passage="passage2", summary="summary2", relevance_score=0.8,
                document_id="doc1", document_title="title1", authors=["A1"],  # Same doc
                publication_date="2023-01-01"
            ),
            Citation(
                passage="passage3", summary="summary3", relevance_score=0.7,
                document_id="doc2", document_title="title2", authors=["A2"],
                publication_date="2023-06-01"
            )
        ]
        
        stats = self.agent.get_citation_stats(citations)
        
        self.assertEqual(stats['total_citations'], 3)
        self.assertAlmostEqual(stats['average_relevance'], 0.8)  # (0.9+0.8+0.7)/3
        self.assertEqual(stats['min_relevance'], 0.7)
        self.assertEqual(stats['max_relevance'], 0.9)
        self.assertEqual(stats['unique_documents'], 2)  # doc1 and doc2
        self.assertAlmostEqual(stats['citations_per_document'], 1.5)  # 3/2
        self.assertIsNotNone(stats['date_range'])
        self.assertEqual(stats['date_range']['earliest'], '2023-01-01')
        self.assertEqual(stats['date_range']['latest'], '2023-06-01')
    
    def test_get_citation_stats_unknown_dates(self):
        """Test statistics with unknown publication dates."""
        citations = [
            Citation(
                passage="passage", summary="summary", relevance_score=0.8,
                document_id="doc1", document_title="title", authors=["A1"],
                publication_date="Unknown"
            )
        ]
        
        stats = self.agent.get_citation_stats(citations)
        
        self.assertEqual(stats['total_citations'], 1)
        self.assertNotIn('date_range', stats)  # No valid dates
    
    def test_process_citation_queue_no_orchestrator(self):
        """Test queue processing without orchestrator."""
        agent = CitationFinderAgent()  # No orchestrator
        
        result = list(agent.process_citation_queue(
            user_question=self.sample_question,
            scored_documents=[(self.sample_document, {'score': 4.0})],
        ))
        
        self.assertEqual(result, [])
    
    def test_process_citation_queue_no_qualifying_docs(self):
        """Test queue processing with no qualifying documents."""
        scored_documents = [
            (self.sample_document, {'score': 1.0})  # Below threshold
        ]
        
        result = list(self.agent.process_citation_queue(
            user_question=self.sample_question,
            scored_documents=scored_documents,
            score_threshold=3.0
        ))
        
        self.assertEqual(result, [])


class TestCitationWorkflowIntegration(unittest.TestCase):
    """Test citation workflow integration scenarios."""
    
    def setUp(self):
        """Set up integration test fixtures."""
        self.mock_orchestrator = Mock()
        self.agent = CitationFinderAgent(orchestrator=self.mock_orchestrator)
    
    def test_full_workflow_simulation(self):
        """Test simulation of full scoring -> citation workflow."""
        # Mock scored documents from previous scoring step
        scored_documents = [
            ({
                'id': 98765001,  # Database-style ID
                'title': 'Relevant Study',
                'abstract': 'This study directly addresses the research question with clear results.',
                'authors': ['Author, A.'],
                'publication_date': '2023-01-01'
            }, {'score': 4.5, 'reasoning': 'Highly relevant'}),
            ({
                'id': 98765002,  # Database-style ID
                'title': 'Irrelevant Study',
                'abstract': 'This study is about something completely different.',
                'authors': ['Other, B.'],
                'publication_date': '2023-01-01'
            }, {'score': 1.2, 'reasoning': 'Not relevant'})
        ]
        
        # Mock successful citation extraction for high-scoring doc
        def mock_extract_citation(user_question, document, min_relevance=0.7):
            if document['id'] == 98765001:  # Match the database-style ID
                return Citation(
                    passage="Key finding from the study",
                    summary="This finding directly answers the question",
                    relevance_score=0.9,
                    document_id=str(document['id']),  # Convert to string for citation
                    document_title=document['title'],
                    authors=document['authors'],
                    publication_date=document['publication_date']
                )
            return None
        
        with patch.object(self.agent, 'extract_citation_from_document', side_effect=mock_extract_citation):
            citations = self.agent.process_scored_documents_for_citations(
                user_question="Test question",
                scored_documents=scored_documents,
                score_threshold=3.0
            )
            
            # Should only process and return citation from high-scoring document
            self.assertEqual(len(citations), 1)
            self.assertEqual(citations[0].document_id, '98765001')
            self.assertEqual(citations[0].relevance_score, 0.9)


if __name__ == '__main__':
    unittest.main()