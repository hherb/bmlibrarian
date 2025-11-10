"""
Tests for FactCheckerAgent

Tests fact-checking workflow, statement evaluation, and evidence synthesis.
"""

import json
import unittest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timezone
from typing import Dict, Any, List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bmlibrarian.agents.fact_checker_agent import (
    FactCheckerAgent,
    FactCheckResult,
    EvidenceReference
)
from bmlibrarian.agents.citation_agent import Citation


class TestFactCheckerAgent(unittest.TestCase):
    """Test cases for FactCheckerAgent functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_orchestrator = Mock()

        # Create agent with mocked sub-agents
        with patch('bmlibrarian.agents.fact_checker_agent.QueryAgent'), \
             patch('bmlibrarian.agents.fact_checker_agent.DocumentScoringAgent'), \
             patch('bmlibrarian.agents.fact_checker_agent.CitationFinderAgent'):

            self.agent = FactCheckerAgent(
                model="test-model",
                host="http://test:11434",
                orchestrator=self.mock_orchestrator,
                show_model_info=False,
                score_threshold=2.5,
                max_search_results=50,
                max_citations=10
            )

        # Sample documents for testing
        self.sample_documents = [
            {
                'id': 12345678,
                'title': 'Childhood Ulcerative Colitis Treatment Study',
                'abstract': 'Most childhood UC cases can be managed medically. Only severe, refractory cases require colectomy.',
                'authors': ['Smith, J.', 'Johnson, A.'],
                'publication_date': '2023-01-15',
                'pmid': '12345678',
                'doi': '10.1234/test.2023.001'
            },
            {
                'id': 23456789,
                'title': 'Long-term Outcomes in Pediatric IBD',
                'abstract': 'Study of 500 pediatric UC patients showed 85% achieved remission with medical therapy.',
                'authors': ['Brown, K.', 'Davis, L.'],
                'publication_date': '2022-06-20',
                'pmid': '23456789',
                'doi': '10.1234/test.2022.002'
            }
        ]

        # Sample citations
        self.sample_citations = [
            Citation(
                passage="Most childhood UC cases can be managed medically without surgery.",
                summary="Medical management is effective for most pediatric UC cases",
                relevance_score=0.9,
                document_id="12345678",
                document_title="Childhood Ulcerative Colitis Treatment Study",
                authors=["Smith, J.", "Johnson, A."],
                publication_date="2023-01-15",
                pmid="12345678",
                doi="10.1234/test.2023.001"
            ),
            Citation(
                passage="85% of pediatric UC patients achieved remission with medical therapy.",
                summary="High success rate with medical treatment in children",
                relevance_score=0.85,
                document_id="23456789",
                document_title="Long-term Outcomes in Pediatric IBD",
                authors=["Brown, K.", "Davis, L."],
                publication_date="2022-06-20",
                pmid="23456789",
                doi="10.1234/test.2022.002"
            )
        ]

        self.test_statement = "All cases of childhood ulcerative colitis require colectomy"

    def test_agent_initialization(self):
        """Test FactCheckerAgent initialization."""
        self.assertEqual(self.agent.get_agent_type(), "FactCheckerAgent")
        self.assertEqual(self.agent.model, "test-model")
        self.assertEqual(self.agent.score_threshold, 2.5)
        self.assertEqual(self.agent.max_search_results, 50)
        self.assertEqual(self.agent.max_citations, 10)

    def test_evidence_reference_creation(self):
        """Test EvidenceReference dataclass creation."""
        ref = EvidenceReference(
            citation_text="Test citation text",
            pmid="12345678",
            doi="10.1234/test",
            document_id="12345678",
            relevance_score=4.5,
            supports_statement=True
        )

        self.assertEqual(ref.citation_text, "Test citation text")
        self.assertEqual(ref.pmid, "12345678")
        self.assertEqual(ref.doi, "10.1234/test")
        self.assertEqual(ref.relevance_score, 4.5)
        self.assertTrue(ref.supports_statement)

    def test_evidence_reference_to_dict(self):
        """Test EvidenceReference conversion to dictionary."""
        ref = EvidenceReference(
            citation_text="Test citation",
            pmid="12345678",
            doi="10.1234/test",
            relevance_score=4.5,
            supports_statement=True
        )

        result = ref.to_dict()

        self.assertEqual(result['citation'], "Test citation")
        self.assertEqual(result['pmid'], "PMID:12345678")
        self.assertEqual(result['doi'], "DOI:10.1234/test")
        self.assertEqual(result['relevance_score'], 4.5)
        self.assertEqual(result['stance'], "supports")

    def test_fact_check_result_creation(self):
        """Test FactCheckResult dataclass creation."""
        evidence_refs = [
            EvidenceReference(
                citation_text="Test citation",
                pmid="12345678",
                supports_statement=False
            )
        ]

        result = FactCheckResult(
            statement=self.test_statement,
            evaluation="no",
            reason="Literature shows medical management is effective",
            evidence_list=evidence_refs,
            confidence="high",
            documents_reviewed=10,
            supporting_citations=0,
            contradicting_citations=1,
            neutral_citations=0,
            expected_answer="no",
            matches_expected=True
        )

        self.assertEqual(result.statement, self.test_statement)
        self.assertEqual(result.evaluation, "no")
        self.assertEqual(result.confidence, "high")
        self.assertTrue(result.matches_expected)
        self.assertIsNotNone(result.timestamp)

    def test_fact_check_result_to_dict(self):
        """Test FactCheckResult conversion to dictionary."""
        evidence_refs = [
            EvidenceReference(
                citation_text="Test citation",
                pmid="12345678",
                supports_statement=False
            )
        ]

        result = FactCheckResult(
            statement=self.test_statement,
            evaluation="no",
            reason="Evidence contradicts statement",
            evidence_list=evidence_refs,
            confidence="high",
            documents_reviewed=5,
            supporting_citations=0,
            contradicting_citations=1,
            neutral_citations=0,
            expected_answer="no",
            matches_expected=True
        )

        result_dict = result.to_dict()

        self.assertEqual(result_dict['statement'], self.test_statement)
        self.assertEqual(result_dict['evaluation'], "no")
        self.assertEqual(result_dict['reason'], "Evidence contradicts statement")
        self.assertEqual(result_dict['confidence'], "high")
        self.assertEqual(result_dict['expected_answer'], "no")
        self.assertTrue(result_dict['matches_expected'])
        self.assertIn('metadata', result_dict)
        self.assertEqual(result_dict['metadata']['documents_reviewed'], 5)

    def test_statement_to_question_conversion(self):
        """Test conversion of statements to questions."""
        # Test yes/no statement
        statement1 = "All cases of ulcerative colitis require surgery"
        question1 = self.agent._statement_to_question(statement1)
        self.assertIn("?", question1)

        # Test already a question
        statement2 = "Does vitamin D help with IBD?"
        question2 = self.agent._statement_to_question(statement2)
        self.assertEqual(question2, statement2)

        # Test general statement
        statement3 = "Vitamin D and IBD outcomes"
        question3 = self.agent._statement_to_question(statement3)
        self.assertIn("?", question3)

    def test_prepare_evidence_summary(self):
        """Test evidence summary preparation."""
        summary = self.agent._prepare_evidence_summary(self.sample_citations)

        self.assertIn("Most childhood UC cases", summary)
        self.assertIn("PMID:12345678", summary)
        self.assertIn("85% of pediatric UC patients", summary)
        self.assertIn("[1]", summary)
        self.assertIn("[2]", summary)

    def test_create_evaluation_prompt(self):
        """Test evaluation prompt creation."""
        evidence_summary = self.agent._prepare_evidence_summary(self.sample_citations)
        prompt = self.agent._create_evaluation_prompt(
            self.test_statement,
            evidence_summary
        )

        self.assertIn(self.test_statement, prompt)
        self.assertIn(evidence_summary, prompt)
        self.assertIn("yes|no|maybe", prompt)
        self.assertIn("JSON", prompt)

    def test_parse_evaluation_response_valid(self):
        """Test parsing of valid evaluation response."""
        response = json.dumps({
            "evaluation": "no",
            "reason": "Evidence shows most cases don't require surgery",
            "citation_stances": {
                "1": "contradicts",
                "2": "contradicts"
            }
        })

        result = self.agent._parse_evaluation_response(response)

        self.assertEqual(result['evaluation'], 'no')
        self.assertIn('reason', result)
        self.assertIn('citation_stances', result)
        self.assertEqual(result['citation_stances']['1'], 'contradicts')

    def test_parse_evaluation_response_with_markdown(self):
        """Test parsing of response wrapped in markdown code blocks."""
        response = '''```json
{
    "evaluation": "yes",
    "reason": "Evidence supports the statement",
    "citation_stances": {"1": "supports"}
}
```'''

        result = self.agent._parse_evaluation_response(response)

        self.assertEqual(result['evaluation'], 'yes')
        self.assertIn('reason', result)

    def test_parse_evaluation_response_invalid_value(self):
        """Test parsing with invalid evaluation value."""
        response = json.dumps({
            "evaluation": "unknown",
            "reason": "Test reason"
        })

        result = self.agent._parse_evaluation_response(response)

        # Should default to "maybe" for invalid values
        self.assertEqual(result['evaluation'], 'maybe')

    def test_fallback_evaluation(self):
        """Test fallback evaluation when LLM fails."""
        result = self.agent._fallback_evaluation(
            self.test_statement,
            self.sample_citations
        )

        self.assertEqual(result['evaluation'], 'maybe')
        self.assertIn('reason', result)
        self.assertIn('citation_stances', result)

    def test_citations_to_evidence_refs(self):
        """Test conversion of Citations to EvidenceReferences."""
        scored_docs = [
            (self.sample_documents[0], 4.5),
            (self.sample_documents[1], 4.0)
        ]

        citation_stances = {
            "1": "contradicts",
            "2": "contradicts"
        }

        evidence_refs = self.agent._citations_to_evidence_refs(
            self.sample_citations,
            scored_docs,
            citation_stances
        )

        self.assertEqual(len(evidence_refs), 2)
        self.assertFalse(evidence_refs[0].supports_statement)
        self.assertFalse(evidence_refs[1].supports_statement)
        self.assertEqual(evidence_refs[0].pmid, "12345678")
        self.assertEqual(evidence_refs[0].relevance_score, 4.5)

    def test_determine_confidence_high(self):
        """Test confidence determination - high confidence case."""
        confidence = self.agent._determine_confidence(
            evaluation="no",
            supporting=0,
            contradicting=5,
            neutral=0,
            total_docs=10
        )

        self.assertEqual(confidence, "high")

    def test_determine_confidence_medium(self):
        """Test confidence determination - medium confidence case."""
        confidence = self.agent._determine_confidence(
            evaluation="yes",
            supporting=4,
            contradicting=2,
            neutral=0,
            total_docs=8
        )

        self.assertEqual(confidence, "medium")

    def test_determine_confidence_low(self):
        """Test confidence determination - low confidence case."""
        confidence = self.agent._determine_confidence(
            evaluation="maybe",
            supporting=1,
            contradicting=1,
            neutral=1,
            total_docs=3
        )

        self.assertEqual(confidence, "low")

    @patch.object(FactCheckerAgent, '_initialize_agents')
    @patch.object(FactCheckerAgent, '_search_documents')
    def test_check_statement_no_documents(self, mock_search, mock_init):
        """Test fact-checking when no documents are found."""
        mock_search.return_value = []

        result = self.agent.check_statement(
            statement=self.test_statement,
            expected_answer="no"
        )

        self.assertEqual(result.evaluation, "maybe")
        self.assertEqual(result.confidence, "low")
        self.assertEqual(result.documents_reviewed, 0)
        self.assertIn("No relevant documents", result.reason)
        self.assertFalse(result.matches_expected)

    @patch.object(FactCheckerAgent, '_initialize_agents')
    @patch.object(FactCheckerAgent, '_search_documents')
    @patch.object(FactCheckerAgent, '_score_documents')
    def test_check_statement_no_scored_documents(self, mock_score, mock_search, mock_init):
        """Test fact-checking when no documents meet threshold."""
        mock_search.return_value = self.sample_documents
        mock_score.return_value = []

        result = self.agent.check_statement(
            statement=self.test_statement
        )

        self.assertEqual(result.evaluation, "maybe")
        self.assertEqual(result.confidence, "low")
        self.assertIn("threshold", result.reason.lower())

    @patch.object(FactCheckerAgent, '_initialize_agents')
    @patch.object(FactCheckerAgent, '_search_documents')
    @patch.object(FactCheckerAgent, '_score_documents')
    @patch.object(FactCheckerAgent, '_extract_citations')
    def test_check_statement_no_citations(self, mock_extract, mock_score, mock_search, mock_init):
        """Test fact-checking when no citations are extracted."""
        mock_search.return_value = self.sample_documents
        mock_score.return_value = [(self.sample_documents[0], 4.5)]
        mock_extract.return_value = []

        result = self.agent.check_statement(
            statement=self.test_statement
        )

        self.assertEqual(result.evaluation, "maybe")
        self.assertEqual(result.confidence, "low")
        self.assertIn("no relevant citations", result.reason.lower())

    @patch.object(FactCheckerAgent, '_initialize_agents')
    @patch.object(FactCheckerAgent, '_search_documents')
    @patch.object(FactCheckerAgent, '_score_documents')
    @patch.object(FactCheckerAgent, '_extract_citations')
    @patch.object(FactCheckerAgent, '_evaluate_statement')
    def test_check_statement_success(
        self,
        mock_evaluate,
        mock_extract,
        mock_score,
        mock_search,
        mock_init
    ):
        """Test successful fact-checking workflow."""
        # Setup mocks
        mock_search.return_value = self.sample_documents
        mock_score.return_value = [
            (self.sample_documents[0], 4.5),
            (self.sample_documents[1], 4.0)
        ]
        mock_extract.return_value = self.sample_citations

        expected_result = FactCheckResult(
            statement=self.test_statement,
            evaluation="no",
            reason="Evidence contradicts the statement",
            evidence_list=[
                EvidenceReference(
                    citation_text="Test citation",
                    pmid="12345678",
                    supports_statement=False
                )
            ],
            confidence="high",
            documents_reviewed=2,
            supporting_citations=0,
            contradicting_citations=2,
            neutral_citations=0,
            expected_answer="no",
            matches_expected=True
        )
        mock_evaluate.return_value = expected_result

        # Execute
        result = self.agent.check_statement(
            statement=self.test_statement,
            expected_answer="no"
        )

        # Verify
        self.assertEqual(result.evaluation, "no")
        self.assertEqual(result.confidence, "high")
        self.assertTrue(result.matches_expected)
        mock_init.assert_called_once()
        mock_search.assert_called_once()
        mock_score.assert_called_once()
        mock_extract.assert_called_once()
        mock_evaluate.assert_called_once()

    def test_generate_summary(self):
        """Test summary generation for batch results."""
        results = [
            FactCheckResult(
                statement="Statement 1",
                evaluation="yes",
                reason="Test",
                evidence_list=[],
                confidence="high",
                documents_reviewed=5,
                supporting_citations=3,
                contradicting_citations=0,
                neutral_citations=0,
                expected_answer="yes",
                matches_expected=True
            ),
            FactCheckResult(
                statement="Statement 2",
                evaluation="no",
                reason="Test",
                evidence_list=[],
                confidence="medium",
                documents_reviewed=4,
                supporting_citations=0,
                contradicting_citations=2,
                neutral_citations=0,
                expected_answer="no",
                matches_expected=True
            ),
            FactCheckResult(
                statement="Statement 3",
                evaluation="maybe",
                reason="Test",
                evidence_list=[],
                confidence="low",
                documents_reviewed=2,
                supporting_citations=1,
                contradicting_citations=1,
                neutral_citations=0,
                expected_answer="yes",
                matches_expected=False
            )
        ]

        summary = self.agent._generate_summary(results)

        self.assertEqual(summary['total_statements'], 3)
        self.assertEqual(summary['evaluations']['yes'], 1)
        self.assertEqual(summary['evaluations']['no'], 1)
        self.assertEqual(summary['evaluations']['maybe'], 1)
        self.assertEqual(summary['confidences']['high'], 1)
        self.assertEqual(summary['confidences']['medium'], 1)
        self.assertEqual(summary['confidences']['low'], 1)
        self.assertIn('validation', summary)
        self.assertEqual(summary['validation']['matches'], 2)
        self.assertEqual(summary['validation']['mismatches'], 1)
        self.assertAlmostEqual(summary['validation']['accuracy'], 0.667, places=2)

    @patch.object(FactCheckerAgent, 'check_statement')
    @patch.object(FactCheckerAgent, '_save_results')
    def test_check_batch(self, mock_save, mock_check):
        """Test batch processing of statements."""
        statements = [
            {"statement": "Statement 1", "answer": "yes"},
            {"statement": "Statement 2", "answer": "no"}
        ]

        mock_result1 = FactCheckResult(
            statement="Statement 1",
            evaluation="yes",
            reason="Test",
            evidence_list=[],
            confidence="high",
            documents_reviewed=5
        )
        mock_result2 = FactCheckResult(
            statement="Statement 2",
            evaluation="no",
            reason="Test",
            evidence_list=[],
            confidence="high",
            documents_reviewed=4
        )

        mock_check.side_effect = [mock_result1, mock_result2]

        results = self.agent.check_batch(statements, output_file="test_output.json")

        self.assertEqual(len(results), 2)
        self.assertEqual(mock_check.call_count, 2)
        mock_save.assert_called_once()

    def test_filter_agent_params(self):
        """Test filtering of agent configuration parameters."""
        config = {
            'temperature': 0.1,
            'top_p': 0.9,
            'max_tokens': 1000,
            'unsupported_param': 'value',
            'another_bad_param': 123
        }

        filtered = self.agent._filter_agent_params(config)

        self.assertIn('temperature', filtered)
        self.assertIn('top_p', filtered)
        self.assertIn('max_tokens', filtered)
        self.assertNotIn('unsupported_param', filtered)
        self.assertNotIn('another_bad_param', filtered)


if __name__ == '__main__':
    unittest.main()
