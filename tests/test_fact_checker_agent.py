"""
Tests for FactCheckerAgent

Tests fact-checking workflow, statement evaluation, and evidence synthesis.
"""

import unittest
from unittest.mock import Mock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import json

from bmlibrarian.factchecker.agent.fact_checker_agent import (
    EVALUATION_ERROR,
    EVALUATION_VALIDATION_ATTEMPTS,
    STAGE_CITATIONS,
    STAGE_EVALUATION,
    STAGE_SCORING,
    STAGE_SEARCH,
    FactCheckerAgent,
    FactCheckResult,
    FactCheckStageError,
    failed_search_strategies,
    EvidenceReference
)
from bmlibrarian.agents.citation_agent import Citation


class TestFactCheckerAgent(unittest.TestCase):
    """Test cases for FactCheckerAgent functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_orchestrator = Mock()

        # Create agent with mocked sub-agents
        with patch('bmlibrarian.factchecker.agent.fact_checker_agent.QueryAgent'), \
             patch('bmlibrarian.factchecker.agent.fact_checker_agent.DocumentScoringAgent'), \
             patch('bmlibrarian.factchecker.agent.fact_checker_agent.CitationFinderAgent'):

            self.agent = FactCheckerAgent(
                model="test-model",
                host="http://test:11434",
                orchestrator=self.mock_orchestrator,
                show_model_info=False,
                score_threshold=2.5,
                max_search_results=50,
                max_citations=None,  # None = no limit, use all scored documents
                # One attempt: these tests drive the stage logic with failing
                # mocks; backoff retries are tested in
                # test_fact_checker_failure_handling.py.
                transient_retry_attempts=1
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
        self.assertIsNone(self.agent.max_citations)  # None = no limit

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

    def test_validate_evaluation_response_valid(self):
        """Test validation of a valid (already parsed) evaluation response."""
        response = {
            "evaluation": "no",
            "reason": "Evidence shows most cases don't require surgery",
            "citation_stances": {
                "1": "contradicts",
                "2": "contradicts"
            }
        }

        result = self.agent._validate_evaluation_response(response, citation_count=2)

        self.assertEqual(result['evaluation'], 'no')
        self.assertIn('reason', result)
        self.assertIn('citation_stances', result)
        self.assertEqual(result['citation_stances']['1'], 'contradicts')

    def test_validate_evaluation_response_normalizes(self):
        """Evaluation is lower-cased/stripped; no citations need no stances."""
        result = self.agent._validate_evaluation_response({
            "evaluation": "  YES ",
            "reason": "Evidence supports the statement",
        }, citation_count=0)

        self.assertEqual(result['evaluation'], 'yes')
        self.assertEqual(result['citation_stances'], {})

    def test_validate_evaluation_response_missing_fields(self):
        """A response without evaluation/reason is rejected."""
        with self.assertRaises(ValueError):
            self.agent._validate_evaluation_response({"evaluation": "yes"}, citation_count=0)

    def test_validate_evaluation_response_invalid_value(self):
        """An invalid verdict is rejected, never coerced to 'maybe'."""
        with self.assertRaises(ValueError):
            self.agent._validate_evaluation_response(
                {"evaluation": "unknown", "reason": "Test reason"}, citation_count=0
            )

    def test_validate_evaluation_response_rejects_malformed_responses(self):
        """Non-object responses, non-string verdicts and empty reasons are invalid."""
        for response in (
            ["yes", "reason"],
            {"evaluation": None, "reason": "r"},
            {"evaluation": ["yes"], "reason": "r"},
            {"evaluation": "yes", "reason": "   "},
            {"evaluation": "yes", "reason": None},
        ):
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.agent._validate_evaluation_response(response, citation_count=0)

    def test_validate_evaluation_response_rejects_non_dict_stances(self):
        """A non-object citation_stances is invalid, never replaced by {} (neutral)."""
        with self.assertRaises(ValueError):
            self.agent._validate_evaluation_response(
                {"evaluation": "no", "reason": "r", "citation_stances": ["supports"]},
                citation_count=1,
            )

    def test_request_evaluation_retries_an_invalid_verdict(self):
        """An invalid verdict is requested again; a valid retry is used."""
        with patch.object(self.agent, '_chat_and_parse_json', side_effect=[
            {"evaluation": "unknown", "reason": "r"},
            {"evaluation": "No", "reason": "Contradicted"},
        ]) as chat:
            result = self.agent._request_evaluation("prompt", citation_count=0)

        self.assertEqual(chat.call_count, 2)
        self.assertEqual(result['evaluation'], 'no')

    def test_request_evaluation_fails_after_repeated_invalid_verdicts(self):
        """Repeatedly invalid responses fail the stage instead of becoming 'maybe'."""
        with patch.object(
            self.agent, '_chat_and_parse_json',
            return_value={"evaluation": "probably", "reason": "r"},
        ) as chat:
            with self.assertRaises(FactCheckStageError) as ctx:
                self.agent._request_evaluation("prompt", citation_count=0)

        self.assertEqual(chat.call_count, EVALUATION_VALIDATION_ATTEMPTS)
        self.assertEqual(ctx.exception.stage, STAGE_EVALUATION)
        self.assertIn("probably", str(ctx.exception))

    def test_request_evaluation_llm_failure_is_a_stage_error(self):
        """A connection error or unparseable output is not a 'maybe' verdict."""
        for error in (
            ConnectionError("Ollama unreachable"),
            json.JSONDecodeError("Expecting value", "", 0),
        ):
            with self.subTest(error=type(error).__name__), patch.object(
                self.agent, '_chat_and_parse_json', side_effect=error
            ):
                with self.assertRaises(FactCheckStageError) as ctx:
                    self.agent._request_evaluation("prompt", citation_count=0)
                self.assertEqual(ctx.exception.stage, STAGE_EVALUATION)
                self.assertIs(ctx.exception.__cause__, error)

    def test_citations_to_evidence_refs(self):
        """Test conversion of Citations to EvidenceReferences."""
        scored_docs = [
            (self.sample_documents[0], {'score': 4.5}),
            (self.sample_documents[1], {'score': 4.0})
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
    def test_check_statement_explicit_zero_overrides_are_honoured(
        self, mock_score, mock_search, mock_init
    ):
        """Explicit 0 / 0.0 overrides must not fall back to the defaults."""
        mock_search.return_value = self.sample_documents
        mock_score.return_value = []

        self.agent.check_statement(
            statement=self.test_statement, max_documents=0, score_threshold=0.0
        )

        self.assertEqual(mock_search.call_args.args[:2], (self.test_statement, 0))
        self.assertEqual(mock_score.call_args.args[2], 0.0)

    @patch.object(FactCheckerAgent, '_initialize_agents')
    @patch.object(FactCheckerAgent, '_search_documents')
    @patch.object(FactCheckerAgent, '_score_documents')
    def test_threshold_override_reaches_citation_extraction(
        self, mock_score, mock_search, mock_init
    ):
        """A per-call threshold below the default is not undone at extraction."""
        low_scored = (self.sample_documents[0], {'score': 1.0, 'reasoning': 'weak'})
        mock_search.return_value = self.sample_documents
        mock_score.return_value = [low_scored]
        self.agent.citation_agent = Mock()
        self.agent.citation_agent.process_scored_documents_for_citations.return_value = []
        self.agent.citation_agent.get_validation_stats.return_value = {'errors': 0}

        self.agent.check_statement(statement=self.test_statement, score_threshold=0.0)

        extract_call = self.agent.citation_agent.process_scored_documents_for_citations.call_args
        self.assertEqual(extract_call.kwargs['score_threshold'], 0.0)
        self.assertEqual(extract_call.kwargs['scored_documents'], [low_scored])

    def test_check_statement_rejects_negative_max_documents(self):
        """A negative document limit is a caller error, not 'no limit'."""
        with self.assertRaises(ValueError):
            self.agent.check_statement(statement=self.test_statement, max_documents=-1)

    @patch.object(FactCheckerAgent, '_initialize_agents')
    @patch.object(FactCheckerAgent, '_search_documents')
    @patch.object(FactCheckerAgent, '_score_documents')
    def test_check_statement_none_overrides_use_defaults(
        self, mock_score, mock_search, mock_init
    ):
        """Omitted overrides fall back to the agent's configured defaults."""
        mock_search.return_value = self.sample_documents
        mock_score.return_value = []

        self.agent.check_statement(statement=self.test_statement)

        self.assertEqual(mock_search.call_args.args[:2], (self.test_statement, 50))
        self.assertEqual(mock_score.call_args.args[2], 2.5)

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

    @patch.object(FactCheckerAgent, 'check_statement')
    @patch.object(FactCheckerAgent, 'export_database_to_json')
    def test_check_batch(self, mock_export, mock_check):
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
        mock_export.assert_called_once_with("test_output.json", export_type="full")

    # ---- Failures are stage errors, not "insufficient evidence" (#273) ----

    def test_search_failure_is_a_stage_error(self):
        """A search outage raises instead of reporting 'no documents found'."""
        self.agent.query_agent = Mock()
        self.agent.query_agent.find_abstracts.side_effect = ConnectionError("db down")

        with self.assertRaises(FactCheckStageError) as ctx:
            self.agent._search_documents(self.test_statement, 10)

        self.assertEqual(ctx.exception.stage, STAGE_SEARCH)
        self.assertIn("db down", str(ctx.exception))

    def _query_agent(self, documents: list, failed: list) -> Mock:
        """A query agent returning ``documents`` with ``failed`` strategies."""
        agent = Mock()
        agent.find_abstracts.return_value = iter(documents)
        agent.last_search_metadata = {'strategies_used': [], 'strategies_failed': failed}
        return agent

    def test_empty_search_with_failed_strategies_is_a_stage_error(self):
        """search_hybrid swallows strategy errors; an outage is not 'no documents'."""
        self.agent.query_agent = self._query_agent(
            [], [{'strategy': 'bm25', 'error': 'connection refused'}]
        )

        with self.assertRaises(FactCheckStageError) as ctx:
            self.agent._search_documents(self.test_statement, 10)

        self.assertEqual(ctx.exception.stage, STAGE_SEARCH)
        self.assertIn("bm25: connection refused", str(ctx.exception))

    def test_failed_strategy_alongside_documents_keeps_the_documents(self):
        """Documents from the strategies that worked are still used."""
        self.agent.query_agent = self._query_agent(
            self.sample_documents, [{'strategy': 'semantic', 'error': 'no embedder'}]
        )

        documents = self.agent._search_documents(self.test_statement, 10)

        self.assertEqual(documents, self.sample_documents)

    def test_empty_search_without_failures_is_insufficient_evidence(self):
        """Every strategy ran and matched nothing: an empty result."""
        self.agent.query_agent = self._query_agent([], [])

        self.assertEqual(self.agent._search_documents(self.test_statement, 10), [])

    def test_failed_search_strategies_tolerates_missing_or_odd_metadata(self):
        """Metadata without failure information means no recorded failures."""
        for metadata in (None, {}, {'strategies_failed': None}, "text"):
            with self.subTest(metadata=metadata):
                self.assertEqual(failed_search_strategies(metadata), [])
        self.assertEqual(
            failed_search_strategies({'strategies_failed': [{'strategy': 'bm25'}, 'odd']}),
            ['bm25: unknown error', 'odd'],
        )

    def _scoring_agent(self, outcomes: list) -> Mock:
        """A scoring agent returning or raising each outcome in turn."""
        agent = Mock()
        agent.evaluate_document.side_effect = outcomes
        return agent

    def test_scoring_failures_with_nothing_above_threshold_are_a_stage_error(self):
        """If any document failed and none passed, the evidence was not examined."""
        for outcomes, expected in (
            ([ConnectionError("ollama down"), ConnectionError("ollama down")], "2 of 2"),
            ([ConnectionError("ollama down"), {'score': 1, 'reasoning': 'weak'}], "1 of 2"),
        ):
            with self.subTest(expected=expected):
                self.agent.scoring_agent = self._scoring_agent(outcomes)
                with self.assertRaises(FactCheckStageError) as ctx:
                    self.agent._score_documents(
                        self.test_statement, self.sample_documents, 2.5
                    )
                self.assertEqual(ctx.exception.stage, STAGE_SCORING)
                self.assertIn(expected, str(ctx.exception))
                self.assertIn("ollama down", str(ctx.exception))

    def test_scoring_partial_failure_keeps_the_documents_that_passed(self):
        """A failed document is skipped when others reached the threshold."""
        self.agent.scoring_agent = self._scoring_agent(
            [ConnectionError("timeout"), {'score': 4, 'reasoning': 'relevant'}]
        )

        scored = self.agent._score_documents(self.test_statement, self.sample_documents, 2.5)

        self.assertEqual([doc['id'] for doc, _ in scored], [self.sample_documents[1]['id']])

    def test_scoring_without_failures_can_be_empty(self):
        """Every document scored below the threshold: genuinely no evidence."""
        self.agent.scoring_agent = self._scoring_agent(
            [{'score': 1, 'reasoning': 'weak'}, {'score': 2, 'reasoning': 'weak'}]
        )

        self.assertEqual(
            self.agent._score_documents(self.test_statement, self.sample_documents, 2.5), []
        )

    def _citation_agent(self, citations: list, new_errors: int) -> Mock:
        """A citation agent whose extraction records ``new_errors`` failed documents.

        Its statistics change when extraction runs, like the real agent's, so
        the test does not depend on how often they are read.
        """
        stats = {'errors': 3, 'failed_citations': [], 'errored_documents': [
            {'document_id': 0, 'error': 'earlier batch'}] * 3}

        def extract(**_kwargs):
            """Record the errors and return the citations."""
            stats['errors'] += new_errors
            stats['errored_documents'] += [
                {'document_id': doc['id'], 'error': 'ollama down'}
                for doc in self.sample_documents[:new_errors]
            ]
            return citations

        agent = Mock()
        agent.get_validation_stats.side_effect = lambda: stats
        agent.process_scored_documents_for_citations.side_effect = extract
        return agent

    def _qualifying(self) -> list:
        """Two scored documents above the default threshold."""
        return [(doc, {'score': 4, 'reasoning': 'r'}) for doc in self.sample_documents]

    def test_citation_errors_with_no_citations_are_a_stage_error(self):
        """No citation because extraction failed is not 'no relevant citations'."""
        self.agent.citation_agent = self._citation_agent([], new_errors=2)

        with self.assertRaises(FactCheckStageError) as ctx:
            self.agent._extract_citations(self.test_statement, self._qualifying())

        self.assertEqual(ctx.exception.stage, STAGE_CITATIONS)
        self.assertIn("2 of 2", str(ctx.exception))

    def test_citation_errors_alongside_citations_keep_the_citations(self):
        """A partial extraction failure still uses the citations obtained."""
        self.agent.citation_agent = self._citation_agent(self.sample_citations[:1], new_errors=1)

        citations = self.agent._extract_citations(self.test_statement, self._qualifying())

        self.assertEqual(citations, self.sample_citations[:1])

    def test_no_citations_without_errors_is_insufficient_evidence(self):
        """Documents examined, nothing relevant extracted: an empty result."""
        self.agent.citation_agent = self._citation_agent([], new_errors=0)

        self.assertEqual(
            self.agent._extract_citations(self.test_statement, self._qualifying()), []
        )

    def test_citation_extraction_exception_is_a_stage_error(self):
        """An exception from the citation agent is not swallowed into []."""
        self.agent.citation_agent = Mock()
        self.agent.citation_agent.get_validation_stats.return_value = {'errors': 0}
        self.agent.citation_agent.process_scored_documents_for_citations.side_effect = (
            RuntimeError("boom")
        )

        with self.assertRaises(FactCheckStageError) as ctx:
            self.agent._extract_citations(self.test_statement, self._qualifying())

        self.assertEqual(ctx.exception.stage, STAGE_CITATIONS)

    @patch.object(FactCheckerAgent, '_initialize_agents')
    @patch.object(FactCheckerAgent, '_search_documents')
    def test_check_statement_propagates_stage_errors(self, mock_search, mock_init):
        """check_statement does not turn a stage failure into a verdict."""
        mock_search.side_effect = FactCheckStageError(STAGE_SEARCH, "db down")

        with self.assertRaises(FactCheckStageError):
            self.agent.check_statement(statement=self.test_statement)

    @patch.object(FactCheckerAgent, 'check_statement')
    def test_check_batch_does_not_store_failed_checks(self, mock_check):
        """A failed statement is reported as an error, counted and not stored."""
        ok = FactCheckResult(
            statement="Statement 1", evaluation="yes", reason="Supported",
            evidence_list=[], confidence="high", documents_reviewed=5,
        )
        mock_check.side_effect = [ok, FactCheckStageError(STAGE_SCORING, "ollama down")]
        self.agent.db = Mock()
        statements = [
            {"id": "1", "question": "Statement 1", "answer": "yes"},
            {"id": "2", "question": "Statement 2", "answer": "no"},
        ]

        with patch.object(self.agent, '_store_result_in_database') as store:
            results = self.agent.check_batch(statements)

        self.assertEqual([r.evaluation for r in results], ["yes", EVALUATION_ERROR])
        failed = results[1]
        self.assertTrue(failed.is_error)
        self.assertFalse(results[0].is_error)
        self.assertIsNone(failed.matches_expected)
        self.assertEqual(failed.input_statement_id, "2")
        self.assertIn("ollama down", failed.reason)
        self.assertEqual(self.agent.check_failures, 1)
        store.assert_called_once_with(ok, None)

        session_update = self.agent.db.update_processing_session.call_args.args[1]
        self.assertEqual(session_update['processed_statements'], 1)
        self.assertIn("1 statement(s) failed", session_update['error_message'])

    @patch.object(FactCheckerAgent, 'check_statement')
    def test_check_batch_resets_failure_count(self, mock_check):
        """check_failures counts the current batch only."""
        mock_check.side_effect = [RuntimeError("bug"), FactCheckResult(
            statement="s", evaluation="no", reason="r", evidence_list=[],
        )]

        self.agent.check_batch([{"statement": "a"}])
        self.assertEqual(self.agent.check_failures, 1)
        self.agent.check_batch([{"statement": "b"}])
        self.assertEqual(self.agent.check_failures, 0)

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
        # Sub-agents (query/scoring/citation) do not accept max_tokens
        self.assertNotIn('max_tokens', filtered)
        self.assertNotIn('unsupported_param', filtered)
        self.assertNotIn('another_bad_param', filtered)


if __name__ == '__main__':
    unittest.main()
