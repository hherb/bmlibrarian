"""
Integration tests for SystematicReviewAgent Phase 2.

These tests verify the integration between:
- Planner and SearchExecutor components
- Data models and workflow
- Agent coordination

Note: These tests mock database and LLM calls to allow running without
external dependencies. Full integration tests with real services should
be run separately.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any

from bmlibrarian.agents.systematic_review import (
    # Main agent (Phase 1)
    SystematicReviewAgent,
    # Configuration
    SystematicReviewConfig,
    get_systematic_review_config,
    # Input models
    SearchCriteria,
    ScoringWeights,
    StudyTypeFilter,
    # Search models
    PlannedQuery,
    SearchPlan,
    ExecutedQuery,
    QueryType,
    # Paper models
    PaperData,
    ScoredPaper,
    InclusionDecision,
    InclusionStatus,
    ExclusionStage,
    # Phase 2 components
    Planner,
    PICOComponents,
    SearchExecutor,
    SearchResult,
    AggregatedResults,
    # Documenter
    Documenter,
    ACTION_GENERATE_SEARCH_PLAN,
    ACTION_EXECUTE_SEARCH,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def clinical_criteria() -> SearchCriteria:
    """Create clinical SearchCriteria (suitable for PICO extraction)."""
    return SearchCriteria(
        research_question="What is the efficacy of metformin versus lifestyle intervention for type 2 diabetes prevention?",
        purpose="Clinical guideline development",
        inclusion_criteria=[
            "Randomized controlled trials",
            "Adult participants",
            "Pre-diabetic population",
            "Metformin intervention",
            "Diabetes incidence outcomes",
        ],
        exclusion_criteria=[
            "Pediatric studies",
            "Animal studies",
            "Studies without control group",
        ],
        target_study_types=[
            StudyTypeFilter.RCT,
            StudyTypeFilter.META_ANALYSIS,
        ],
        date_range=(2000, 2024),
    )


@pytest.fixture
def basic_criteria() -> SearchCriteria:
    """Create basic non-clinical SearchCriteria."""
    return SearchCriteria(
        research_question="What are the environmental impacts of electric vehicles?",
        purpose="Literature review for policy analysis",
        inclusion_criteria=["Peer-reviewed studies", "Quantitative data"],
        exclusion_criteria=["Opinion pieces"],
    )


@pytest.fixture
def mock_paper_database() -> List[Dict[str, Any]]:
    """Create mock paper database records."""
    return [
        {
            "id": 1001,
            "title": "Metformin for Diabetes Prevention: A Randomized Trial",
            "authors": '["Smith J", "Johnson A", "Williams B"]',
            "publication_year": 2020,
            "journal_name": "New England Journal of Medicine",
            "abstract": "Background: Metformin has been shown to reduce diabetes risk...",
            "doi": "10.1056/NEJMoa2001",
            "pmid": "30001001",
            "source": "pubmed",
        },
        {
            "id": 1002,
            "title": "Lifestyle Intervention vs Pharmacotherapy in Pre-diabetes",
            "authors": '["Brown C", "Davis D"]',
            "publication_year": 2021,
            "journal_name": "Lancet Diabetes",
            "abstract": "Methods: We conducted a meta-analysis of RCTs comparing...",
            "doi": "10.1016/S2213-8587(21)00002",
            "pmid": "30001002",
            "source": "pubmed",
        },
        {
            "id": 1003,
            "title": "Cost-Effectiveness of Diabetes Prevention Strategies",
            "authors": '["Garcia E", "Martinez F"]',
            "publication_year": 2022,
            "journal_name": "Value in Health",
            "abstract": "Objective: To assess the cost-effectiveness of metformin...",
            "doi": "10.1016/j.jval.2022.001",
            "pmid": "30001003",
            "source": "pubmed",
        },
    ]


@pytest.fixture
def mock_pico_response() -> Dict[str, Any]:
    """Create mock PICO extraction response."""
    return {
        "response": json.dumps({
            "is_clinical": True,
            "population": "Adults with pre-diabetes or impaired glucose tolerance",
            "intervention": "Metformin therapy",
            "comparison": "Lifestyle intervention (diet and exercise)",
            "outcome": "Type 2 diabetes incidence and prevention",
        })
    }


@pytest.fixture
def mock_query_variations_response() -> Dict[str, Any]:
    """Create mock query variations response."""
    return {
        "response": json.dumps([
            {
                "query_text": "metformin diabetes prevention efficacy pre-diabetic",
                "query_type": "semantic",
                "purpose": "Core intervention and outcome focus",
                "expected_coverage": "Primary prevention studies"
            },
            {
                "query_text": "lifestyle intervention glucose intolerance prevention",
                "query_type": "semantic",
                "purpose": "Comparator focus",
                "expected_coverage": "Lifestyle intervention studies"
            },
        ])
    }


# =============================================================================
# Planner-Executor Integration Tests
# =============================================================================

class TestPlannerExecutorIntegration:
    """Tests for Planner and SearchExecutor integration."""

    @patch('bmlibrarian.agents.systematic_review.planner.ollama.generate')
    def test_clinical_question_pico_extraction(
        self,
        mock_generate: MagicMock,
        clinical_criteria: SearchCriteria,
        mock_pico_response: Dict[str, Any],
    ) -> None:
        """Test PICO extraction for clinical questions."""
        mock_generate.return_value = mock_pico_response

        planner = Planner()
        pico = planner._extract_pico(clinical_criteria.research_question)

        assert pico.is_clinical
        assert "pre-diabetes" in pico.population.lower()
        assert "metformin" in pico.intervention.lower()
        assert "lifestyle" in pico.comparison.lower()
        assert "diabetes" in pico.outcome.lower()

    @patch('bmlibrarian.agents.systematic_review.planner.ollama.generate')
    def test_search_plan_query_diversity(
        self,
        mock_generate: MagicMock,
        clinical_criteria: SearchCriteria,
        mock_pico_response: Dict[str, Any],
        mock_query_variations_response: Dict[str, Any],
    ) -> None:
        """Test that search plans have diverse query types."""
        mock_generate.side_effect = [
            mock_pico_response,
            mock_query_variations_response,
        ]

        planner = Planner()
        plan = planner.generate_search_plan(
            clinical_criteria,
            num_query_variations=2,
            include_hyde=True,
        )

        # Collect query types
        query_types = {q.query_type for q in plan.queries}

        # Should have multiple types
        assert len(query_types) >= 2

        # Should have at least semantic queries
        assert QueryType.SEMANTIC in query_types

    @patch('bmlibrarian.database.fetch_documents_by_ids')
    @patch('bmlibrarian.database.search_with_semantic')
    @patch('bmlibrarian.database.find_abstracts')
    @patch('bmlibrarian.database.search_hybrid')
    @patch('bmlibrarian.agents.utils.query_syntax.fix_tsquery_syntax')
    def test_plan_execution_deduplication(
        self,
        mock_fix_syntax: MagicMock,
        mock_hybrid: MagicMock,
        mock_keyword: MagicMock,
        mock_semantic: MagicMock,
        mock_fetch: MagicMock,
        mock_paper_database: List[Dict[str, Any]],
    ) -> None:
        """Test that plan execution properly deduplicates results."""
        # Set up mocks - each search finds overlapping results
        mock_semantic.return_value = iter([mock_paper_database[0], mock_paper_database[1]])
        mock_keyword.return_value = [mock_paper_database[1], mock_paper_database[2]]
        mock_hybrid.return_value = (
            [mock_paper_database[0], mock_paper_database[2]],
            {"strategy": "hybrid"}
        )
        mock_fix_syntax.return_value = "test"
        mock_fetch.return_value = mock_paper_database

        # Create a simple plan
        plan = SearchPlan(
            queries=[
                PlannedQuery(
                    query_id="q1",
                    query_text="test",
                    query_type=QueryType.SEMANTIC,
                    purpose="Test",
                    expected_coverage="Test",
                ),
                PlannedQuery(
                    query_id="q2",
                    query_text="test",
                    query_type=QueryType.KEYWORD,
                    purpose="Test",
                    expected_coverage="Test",
                ),
                PlannedQuery(
                    query_id="q3",
                    query_text="test",
                    query_type=QueryType.HYBRID,
                    purpose="Test",
                    expected_coverage="Test",
                ),
            ],
            total_estimated_yield=300,
            search_rationale="Test plan",
        )

        executor = SearchExecutor()
        results = executor.execute_plan(plan)

        # Total before dedup: 2 + 2 + 2 = 6
        assert results.total_before_dedup == 6

        # Unique papers: 1001, 1002, 1003 = 3
        assert len(results.paper_sources) == 3

        # Verify source tracking
        assert 1001 in results.paper_sources
        assert 1002 in results.paper_sources
        assert 1003 in results.paper_sources

        # Paper 1001 should be found by q1 and q3
        assert "q1" in results.paper_sources[1001]
        assert "q3" in results.paper_sources[1001]

        # Paper 1002 should be found by q1 and q2
        assert "q1" in results.paper_sources[1002]
        assert "q2" in results.paper_sources[1002]

    def test_iteration_decision_logic(self, clinical_criteria: SearchCriteria) -> None:
        """Test iteration decision logic."""
        planner = Planner()

        # Scenario 1: Not enough results
        should_iterate, reason = planner.should_iterate(
            current_results=10,
            target_minimum=100,
            iteration=1,
            max_iterations=3,
        )
        assert should_iterate
        assert "10/100" in reason

        # Scenario 2: Enough results
        should_iterate, reason = planner.should_iterate(
            current_results=150,
            target_minimum=100,
            iteration=1,
            max_iterations=3,
        )
        assert not should_iterate
        assert "meeting target" in reason

        # Scenario 3: Max iterations reached
        should_iterate, reason = planner.should_iterate(
            current_results=10,
            target_minimum=100,
            iteration=3,
            max_iterations=3,
        )
        assert not should_iterate
        assert "maximum iterations" in reason


# =============================================================================
# End-to-End Workflow Tests
# =============================================================================

class TestEndToEndWorkflow:
    """End-to-end workflow tests with mocked dependencies."""

    @patch('bmlibrarian.agents.systematic_review.planner.ollama.generate')
    @patch('bmlibrarian.database.fetch_documents_by_ids')
    @patch('bmlibrarian.database.search_with_semantic')
    def test_complete_search_workflow(
        self,
        mock_search: MagicMock,
        mock_fetch: MagicMock,
        mock_llm: MagicMock,
        clinical_criteria: SearchCriteria,
        mock_paper_database: List[Dict[str, Any]],
        mock_pico_response: Dict[str, Any],
    ) -> None:
        """Test complete workflow from criteria to aggregated results."""
        # Set up mocks
        mock_llm.return_value = mock_pico_response
        mock_search.return_value = iter(mock_paper_database)
        mock_fetch.return_value = mock_paper_database

        # Step 1: Plan
        planner = Planner()
        plan = planner.generate_search_plan(
            clinical_criteria,
            num_query_variations=1,
            include_hyde=False,
        )

        assert len(plan.queries) >= 1
        assert plan.iteration == 1

        # Step 2: Execute
        executor = SearchExecutor()
        results = executor.execute_plan(plan)

        assert results.count > 0
        assert len(results.executed_queries) == len(plan.queries)

        # Step 3: Verify results
        for query_result in results.executed_queries:
            assert query_result.planned_query.query_id
            assert query_result.execution_time_seconds >= 0

    @patch('bmlibrarian.agents.systematic_review.planner.ollama.generate')
    def test_workflow_with_documenter(
        self,
        mock_llm: MagicMock,
        clinical_criteria: SearchCriteria,
        mock_pico_response: Dict[str, Any],
    ) -> None:
        """Test workflow with Documenter audit trail."""
        mock_llm.return_value = mock_pico_response

        # Set up documenter
        documenter = Documenter(review_id="test_workflow")
        documenter.start_review()

        # Step 1: Plan with documentation
        planner = Planner()

        with documenter.log_step_with_timer(
            action=ACTION_GENERATE_SEARCH_PLAN,
            tool="Planner",
            input_summary=f"Criteria: {clinical_criteria.research_question[:50]}...",
            decision_rationale="Generating comprehensive search plan",
        ) as timer:
            plan = planner.generate_search_plan(
                clinical_criteria,
                num_query_variations=1,
                include_hyde=False,
            )
            timer.set_output(f"Generated {len(plan.queries)} queries")
            timer.add_metrics({
                "query_count": len(plan.queries),
                "estimated_yield": plan.total_estimated_yield,
            })

        # Verify documenter recorded the step
        assert len(documenter.steps) == 1
        step = documenter.steps[0]
        assert step.action == ACTION_GENERATE_SEARCH_PLAN
        assert step.success
        assert step.metrics["query_count"] == len(plan.queries)

    def test_callback_flow(self, basic_criteria: SearchCriteria) -> None:
        """Test that callbacks are called correctly through workflow."""
        events: List[tuple] = []

        def callback(event: str, data: str) -> None:
            events.append((event, data))

        with patch('bmlibrarian.agents.systematic_review.planner.ollama.generate') as mock:
            mock.return_value = {"response": "{}"}

            planner = Planner(callback=callback)
            plan = planner.generate_search_plan(
                basic_criteria,
                num_query_variations=1,
                include_hyde=False,
            )

        # Verify planning callbacks
        event_types = [e[0] for e in events]
        assert "planning_started" in event_types
        assert "planning_completed" in event_types


# =============================================================================
# Data Flow Tests
# =============================================================================

class TestDataFlow:
    """Tests for data flow between components."""

    def test_search_criteria_to_plan(
        self, clinical_criteria: SearchCriteria
    ) -> None:
        """Test data flow from SearchCriteria to SearchPlan."""
        with patch('bmlibrarian.agents.systematic_review.planner.ollama.generate') as mock:
            mock.return_value = {"response": "{}"}

            planner = Planner()
            plan = planner.generate_search_plan(
                clinical_criteria,
                num_query_variations=1,
                include_hyde=False,
            )

        # Verify plan contains criteria-based content
        for query in plan.queries:
            # Query should relate to research question or derived terms
            assert query.query_text  # Not empty
            assert query.query_type in QueryType
            assert query.query_id  # Has ID

    def test_plan_to_executed_queries(self) -> None:
        """Test data flow from SearchPlan to ExecutedQuery records."""
        plan = SearchPlan(
            queries=[
                PlannedQuery(
                    query_id="test_q1",
                    query_text="test query",
                    query_type=QueryType.SEMANTIC,
                    purpose="Test purpose",
                    expected_coverage="Test coverage",
                    priority=1,
                ),
            ],
            total_estimated_yield=100,
            search_rationale="Test",
        )

        with patch.object(SearchExecutor, '_execute_single_query') as mock:
            mock.return_value = SearchResult(
                query_id="test_q1",
                document_ids={1, 2, 3},
                success=True,
                execution_time_seconds=1.5,
            )
            with patch.object(SearchExecutor, '_fetch_paper_data') as mock_fetch:
                mock_fetch.return_value = []

                executor = SearchExecutor()
                results = executor.execute_plan(plan)

        # Verify ExecutedQuery matches PlannedQuery
        assert len(results.executed_queries) == 1
        eq = results.executed_queries[0]
        assert eq.planned_query.query_id == "test_q1"
        assert eq.actual_results == 3
        assert eq.success

    def test_aggregated_results_to_summary(
        self, mock_paper_database: List[Dict[str, Any]]
    ) -> None:
        """Test data flow from AggregatedResults to summary."""
        # Create papers from mock database
        papers = [PaperData.from_database_row(row) for row in mock_paper_database]

        test_query1 = PlannedQuery(
            query_id="q1",
            query_text="test1",
            query_type=QueryType.SEMANTIC,
            purpose="Test",
            expected_coverage="Test",
        )
        test_query2 = PlannedQuery(
            query_id="q2",
            query_text="test2",
            query_type=QueryType.KEYWORD,
            purpose="Test",
            expected_coverage="Test",
        )
        results = AggregatedResults(
            papers=papers,
            paper_sources={
                1001: ["q1", "q2"],
                1002: ["q1"],
                1003: ["q2"],
            },
            total_before_dedup=5,
            executed_queries=[
                ExecutedQuery(
                    planned_query=test_query1,
                    document_ids=[1001, 1002],
                    execution_time_seconds=1.0,
                    actual_results=3,
                ),
                ExecutedQuery(
                    planned_query=test_query2,
                    document_ids=[1001, 1003],
                    execution_time_seconds=0.8,
                    actual_results=2,
                ),
            ],
            execution_time_seconds=2.5,
        )

        executor = SearchExecutor()
        summary = executor.get_execution_summary(results)

        # Verify summary contains key information
        assert "3" in summary  # Total unique papers
        assert "5" in summary  # Before dedup
        assert "q1" in summary
        assert "q2" in summary
        assert "2.5" in summary  # Execution time


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Tests for error handling in integration."""

    def test_planner_handles_llm_failure(
        self, basic_criteria: SearchCriteria
    ) -> None:
        """Test that Planner gracefully handles LLM failures."""
        with patch('bmlibrarian.agents.systematic_review.planner.ollama.generate') as mock:
            mock.side_effect = Exception("LLM connection failed")

            planner = Planner()
            plan = planner.generate_search_plan(
                basic_criteria,
                num_query_variations=1,
                include_hyde=False,
            )

        # Should still produce a plan with basic queries
        assert len(plan.queries) > 0

    def test_executor_handles_query_failure(self) -> None:
        """Test that Executor handles individual query failures."""
        plan = SearchPlan(
            queries=[
                PlannedQuery(
                    query_id="q1",
                    query_text="test",
                    query_type=QueryType.SEMANTIC,
                    purpose="Test",
                    expected_coverage="Test",
                ),
                PlannedQuery(
                    query_id="q2",
                    query_text="test",
                    query_type=QueryType.KEYWORD,
                    purpose="Test",
                    expected_coverage="Test",
                ),
            ],
            total_estimated_yield=200,
            search_rationale="Test",
        )

        with patch.object(SearchExecutor, '_execute_single_query') as mock:
            # First query succeeds, second fails
            mock.side_effect = [
                SearchResult(query_id="q1", document_ids={1, 2}, success=True),
                SearchResult(
                    query_id="q2",
                    success=False,
                    error_message="Database error",
                ),
            ]
            with patch.object(SearchExecutor, '_fetch_paper_data') as mock_fetch:
                mock_fetch.return_value = []

                executor = SearchExecutor()
                results = executor.execute_plan(plan)

        # Should have results from successful query
        assert len(results.executed_queries) == 2
        assert results.executed_queries[0].success
        assert not results.executed_queries[1].success
        assert "Database error" in results.executed_queries[1].error

    def test_executor_handles_empty_plan(self) -> None:
        """Test that Executor handles empty plan gracefully."""
        plan = SearchPlan(
            queries=[],
            total_estimated_yield=0,
            search_rationale="Empty test",
        )

        executor = SearchExecutor()
        with patch.object(SearchExecutor, '_fetch_paper_data') as mock_fetch:
            mock_fetch.return_value = []
            results = executor.execute_plan(plan)

        assert results.count == 0
        assert len(results.executed_queries) == 0


# =============================================================================
# Configuration Tests
# =============================================================================

class TestConfiguration:
    """Tests for configuration propagation."""

    def test_config_propagates_to_planner(self) -> None:
        """Test that configuration is properly propagated to Planner."""
        config = SystematicReviewConfig(
            model="custom-model",
            host="http://custom-host:11434",
            temperature=0.5,
        )

        planner = Planner(config=config)

        assert planner.model == "custom-model"
        assert planner.host == "http://custom-host:11434"

    def test_config_propagates_to_executor(self) -> None:
        """Test that configuration is properly propagated to Executor."""
        config = SystematicReviewConfig(
            model="custom-model",
            host="http://custom-host:11434",
        )

        executor = SearchExecutor(
            config=config,
            results_per_query=50,
            similarity_threshold=0.4,
        )

        assert executor.results_per_query == 50
        assert executor.similarity_threshold == 0.4

    def test_planner_temperature_override(self) -> None:
        """Test temperature can be overridden in Planner."""
        planner1 = Planner(temperature=0.1)
        planner2 = Planner(temperature=0.9)

        assert planner1.temperature == 0.1
        assert planner2.temperature == 0.9
