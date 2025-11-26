"""
Unit tests for SystematicReviewAgent Phase 2: Planner and SearchExecutor.

Tests cover:
- Planner initialization and configuration
- PICO component extraction
- Search plan generation
- Query type diversity
- Query deduplication
- SearchExecutor initialization
- SearchResult and AggregatedResults dataclasses
- Execution summary generation
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

from bmlibrarian.agents.systematic_review import (
    # Phase 1 models
    SearchCriteria,
    ScoringWeights,
    StudyTypeFilter,
    QueryType,
    PlannedQuery,
    SearchPlan,
    ExecutedQuery,
    PaperData,
    # Phase 2 components
    Planner,
    PICOComponents,
    SearchExecutor,
    SearchResult,
    AggregatedResults,
    # Configuration
    SystematicReviewConfig,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_criteria() -> SearchCriteria:
    """Create sample SearchCriteria for testing."""
    return SearchCriteria(
        research_question="What is the efficacy of statins for CVD prevention?",
        purpose="Systematic review for clinical guidelines",
        inclusion_criteria=[
            "Human studies",
            "Statin intervention",
            "Cardiovascular disease outcomes"
        ],
        exclusion_criteria=[
            "Animal studies",
            "Pediatric-only populations",
        ],
        target_study_types=[
            StudyTypeFilter.RCT,
            StudyTypeFilter.META_ANALYSIS,
        ],
        date_range=(2010, 2024),
    )


@pytest.fixture
def simple_criteria() -> SearchCriteria:
    """Create minimal SearchCriteria for testing."""
    return SearchCriteria(
        research_question="Effect of exercise on health",
        purpose="Literature overview",
        inclusion_criteria=["Human studies"],
        exclusion_criteria=[],
    )


@pytest.fixture
def mock_ollama_response():
    """Mock ollama.generate response."""
    return {
        "response": json.dumps({
            "is_clinical": True,
            "population": "Adults with cardiovascular disease",
            "intervention": "Statin therapy",
            "comparison": "Placebo or no treatment",
            "outcome": "CVD events and mortality"
        })
    }


@pytest.fixture
def mock_query_variations_response():
    """Mock LLM response for query variations."""
    return {
        "response": json.dumps([
            {
                "query_text": "statin cardiovascular prevention efficacy",
                "query_type": "semantic",
                "purpose": "Find papers on statin efficacy",
                "expected_coverage": "Primary intervention studies"
            },
            {
                "query_text": "HMG-CoA reductase inhibitors heart disease",
                "query_type": "keyword",
                "purpose": "Alternative terminology",
                "expected_coverage": "Papers using technical terminology"
            },
        ])
    }


@pytest.fixture
def sample_planner() -> Planner:
    """Create Planner with test configuration."""
    config = SystematicReviewConfig(
        model="test-model",
        host="http://localhost:11434",
    )
    return Planner(config=config)


@pytest.fixture
def sample_executor() -> SearchExecutor:
    """Create SearchExecutor with test configuration."""
    config = SystematicReviewConfig(
        model="test-model",
        host="http://localhost:11434",
    )
    return SearchExecutor(config=config)


@pytest.fixture
def sample_search_plan() -> SearchPlan:
    """Create sample SearchPlan for testing."""
    queries = [
        PlannedQuery(
            query_id="q1_semantic",
            query_text="statin cardiovascular prevention",
            query_type=QueryType.SEMANTIC,
            purpose="Primary semantic search",
            expected_coverage="Broad semantic matching",
            priority=1,
        ),
        PlannedQuery(
            query_id="q2_keyword",
            query_text="statin & cardiovascular & prevention",
            query_type=QueryType.KEYWORD,
            purpose="Keyword search",
            expected_coverage="Exact term matching",
            priority=2,
        ),
    ]
    return SearchPlan(
        queries=queries,
        total_estimated_yield=200,
        search_rationale="Testing search plan",
    )


@pytest.fixture
def sample_paper_data() -> PaperData:
    """Create sample PaperData for testing."""
    return PaperData(
        document_id=12345,
        title="Efficacy of Statins in Primary Prevention",
        authors=["Smith J", "Johnson A"],
        year=2023,
        journal="Lancet",
        abstract="Background: Statins are widely used...",
        doi="10.1000/example.doi",
        pmid="12345678",
        source="pubmed",
    )


# =============================================================================
# PICOComponents Tests
# =============================================================================

class TestPICOComponents:
    """Tests for PICOComponents dataclass."""

    def test_creation_default(self) -> None:
        """Test creating PICOComponents with defaults."""
        pico = PICOComponents()
        assert not pico.is_clinical
        assert pico.population == ""
        assert pico.intervention == ""
        assert pico.comparison == ""
        assert pico.outcome == ""

    def test_creation_with_values(self) -> None:
        """Test creating PICOComponents with values."""
        pico = PICOComponents(
            is_clinical=True,
            population="Adults with hypertension",
            intervention="Statin therapy",
            comparison="Placebo",
            outcome="Blood pressure reduction",
        )
        assert pico.is_clinical
        assert "hypertension" in pico.population

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        pico = PICOComponents(
            is_clinical=True,
            population="Test population",
            intervention="Test intervention",
            comparison="Test comparison",
            outcome="Test outcome",
        )
        data = pico.to_dict()
        assert data["is_clinical"] is True
        assert data["population"] == "Test population"

    def test_from_dict(self) -> None:
        """Test from_dict deserialization."""
        data = {
            "is_clinical": True,
            "population": "Adults",
            "intervention": "Drug A",
            "comparison": "Placebo",
            "outcome": "Survival",
        }
        pico = PICOComponents.from_dict(data)
        assert pico.is_clinical
        assert pico.population == "Adults"

    def test_generate_query_terms(self) -> None:
        """Test generating query terms from PICO components."""
        pico = PICOComponents(
            is_clinical=True,
            population="Adults with diabetes",
            intervention="Metformin",
            comparison="",  # Empty comparison
            outcome="HbA1c levels",
        )
        terms = pico.generate_query_terms()
        assert len(terms) == 3  # Population, Intervention, Outcome
        assert "Adults with diabetes" in terms
        assert "Metformin" in terms
        assert "HbA1c levels" in terms


# =============================================================================
# Planner Tests
# =============================================================================

class TestPlanner:
    """Tests for Planner class."""

    def test_initialization_default(self) -> None:
        """Test Planner initialization with defaults."""
        planner = Planner()
        assert planner.model is not None
        assert planner.host is not None
        assert planner.temperature == 0.3
        assert planner.top_p == 0.9

    def test_initialization_with_config(self, sample_planner: Planner) -> None:
        """Test Planner initialization with config."""
        assert sample_planner.model == "test-model"
        assert sample_planner.host == "http://localhost:11434"

    def test_callback_registration(self) -> None:
        """Test callback registration."""
        events = []

        def callback(event: str, data: str) -> None:
            events.append((event, data))

        planner = Planner(callback=callback)
        planner._call_callback("test_event", "test_data")

        assert len(events) == 1
        assert events[0] == ("test_event", "test_data")

    def test_extract_key_terms(self, sample_planner: Planner) -> None:
        """Test key term extraction."""
        text = "What is the effect of aspirin on cardiovascular disease prevention?"
        terms = sample_planner._extract_key_terms(text)

        # Should extract meaningful terms
        assert len(terms) > 0
        assert "aspirin" in terms
        assert "cardiovascular" in terms

        # Should not include stop words
        assert "what" not in terms
        assert "the" not in terms

    def test_deduplicate_queries(self, sample_planner: Planner) -> None:
        """Test query deduplication."""
        queries = [
            PlannedQuery(
                query_id="q1",
                query_text="statin cardiovascular",
                query_type=QueryType.SEMANTIC,
                purpose="Test 1",
                expected_coverage="Test",
            ),
            PlannedQuery(
                query_id="q2",
                query_text="Statin Cardiovascular",  # Same, different case
                query_type=QueryType.KEYWORD,
                purpose="Test 2",
                expected_coverage="Test",
            ),
            PlannedQuery(
                query_id="q3",
                query_text="different query",
                query_type=QueryType.SEMANTIC,
                purpose="Test 3",
                expected_coverage="Test",
            ),
        ]

        deduped = sample_planner._deduplicate_queries(queries)
        assert len(deduped) == 2  # First statin query + different query

    def test_prioritize_queries_diversity(self, sample_planner: Planner) -> None:
        """Test that prioritization maintains type diversity."""
        queries = [
            PlannedQuery(query_id="s1", query_text="q1", query_type=QueryType.SEMANTIC, purpose="", expected_coverage=""),
            PlannedQuery(query_id="s2", query_text="q2", query_type=QueryType.SEMANTIC, purpose="", expected_coverage=""),
            PlannedQuery(query_id="k1", query_text="q3", query_type=QueryType.KEYWORD, purpose="", expected_coverage=""),
            PlannedQuery(query_id="h1", query_text="q4", query_type=QueryType.HYBRID, purpose="", expected_coverage=""),
            PlannedQuery(query_id="y1", query_text="q5", query_type=QueryType.HYDE, purpose="", expected_coverage=""),
        ]

        prioritized = sample_planner._prioritize_queries(queries, max_queries=3)

        # Should get one of each type (up to 3)
        types = {q.query_type for q in prioritized}
        assert len(types) >= 3

    def test_generate_semantic_queries(
        self, sample_planner: Planner, sample_criteria: SearchCriteria
    ) -> None:
        """Test semantic query generation."""
        pico = PICOComponents()
        queries = sample_planner._generate_semantic_queries(
            sample_criteria, pico, num_variations=2
        )

        assert len(queries) > 0
        assert all(q.query_type == QueryType.SEMANTIC for q in queries)
        assert all(q.query_id.startswith("semantic_") for q in queries)

    def test_generate_keyword_queries(
        self, sample_planner: Planner, sample_criteria: SearchCriteria
    ) -> None:
        """Test keyword query generation."""
        pico = PICOComponents()
        queries = sample_planner._generate_keyword_queries(
            sample_criteria, pico, num_variations=2
        )

        assert len(queries) > 0
        assert all(q.query_type == QueryType.KEYWORD for q in queries)

    def test_generate_hybrid_queries(
        self, sample_planner: Planner, sample_criteria: SearchCriteria
    ) -> None:
        """Test hybrid query generation."""
        pico = PICOComponents()
        queries = sample_planner._generate_hybrid_queries(sample_criteria, pico)

        assert len(queries) == 1
        assert queries[0].query_type == QueryType.HYBRID

    def test_generate_hyde_query(
        self, sample_planner: Planner, sample_criteria: SearchCriteria
    ) -> None:
        """Test HyDE query generation."""
        query = sample_planner._generate_hyde_query(sample_criteria)

        assert query is not None
        assert query.query_type == QueryType.HYDE

    @patch('bmlibrarian.agents.systematic_review.planner.ollama.generate')
    def test_extract_pico_success(
        self,
        mock_generate: MagicMock,
        sample_planner: Planner,
        mock_ollama_response: dict,
    ) -> None:
        """Test PICO extraction with LLM."""
        mock_generate.return_value = mock_ollama_response

        pico = sample_planner._extract_pico(
            "What is the efficacy of statins for CVD prevention?"
        )

        assert pico.is_clinical
        assert "cardiovascular" in pico.population.lower()
        assert "statin" in pico.intervention.lower()

    @patch('bmlibrarian.agents.systematic_review.planner.ollama.generate')
    def test_extract_pico_cache(
        self,
        mock_generate: MagicMock,
        sample_planner: Planner,
        mock_ollama_response: dict,
    ) -> None:
        """Test PICO extraction caching."""
        mock_generate.return_value = mock_ollama_response

        question = "Test question for caching"

        # First call
        pico1 = sample_planner._extract_pico(question)
        # Second call (should use cache)
        pico2 = sample_planner._extract_pico(question)

        # Should only call LLM once
        assert mock_generate.call_count == 1
        assert pico1.is_clinical == pico2.is_clinical

    @patch('bmlibrarian.agents.systematic_review.planner.ollama.generate')
    def test_extract_pico_invalid_json(
        self, mock_generate: MagicMock, sample_planner: Planner
    ) -> None:
        """Test PICO extraction handles invalid JSON."""
        mock_generate.return_value = {"response": "not valid json"}

        pico = sample_planner._extract_pico("Test question")

        # Should return empty PICO on parse failure
        assert not pico.is_clinical

    @patch('bmlibrarian.agents.systematic_review.planner.ollama.generate')
    def test_generate_search_plan_without_llm(
        self,
        mock_generate: MagicMock,
        sample_planner: Planner,
        simple_criteria: SearchCriteria,
    ) -> None:
        """Test search plan generation without LLM calls."""
        # Mock LLM to fail gracefully
        mock_generate.side_effect = Exception("LLM unavailable")

        plan = sample_planner.generate_search_plan(
            simple_criteria,
            num_query_variations=1,
            include_hyde=False,
        )

        # Should still generate basic queries
        assert len(plan.queries) >= 2  # At least semantic and keyword
        assert plan.iteration == 1
        assert plan.search_rationale != ""

    @patch('bmlibrarian.agents.systematic_review.planner.ollama.generate')
    def test_generate_search_plan_with_llm(
        self,
        mock_generate: MagicMock,
        sample_planner: Planner,
        sample_criteria: SearchCriteria,
        mock_ollama_response: dict,
        mock_query_variations_response: dict,
    ) -> None:
        """Test full search plan generation with LLM."""
        # Set up mock to return PICO then variations
        mock_generate.side_effect = [
            mock_ollama_response,
            mock_query_variations_response,
        ]

        plan = sample_planner.generate_search_plan(
            sample_criteria,
            num_query_variations=2,
            include_hyde=True,
        )

        assert len(plan.queries) > 0
        assert plan.total_estimated_yield > 0

        # Should have diverse query types
        types = {q.query_type for q in plan.queries}
        assert len(types) >= 2

    def test_should_iterate_enough_results(self, sample_planner: Planner) -> None:
        """Test iteration decision with enough results."""
        should_iterate, reason = sample_planner.should_iterate(
            current_results=100,
            target_minimum=50,
            iteration=1,
        )
        assert not should_iterate
        assert "meeting target" in reason

    def test_should_iterate_need_more(self, sample_planner: Planner) -> None:
        """Test iteration decision when more needed."""
        should_iterate, reason = sample_planner.should_iterate(
            current_results=25,
            target_minimum=50,
            iteration=1,
        )
        assert should_iterate
        assert "more queries needed" in reason

    def test_should_iterate_max_reached(self, sample_planner: Planner) -> None:
        """Test iteration decision at max iterations."""
        should_iterate, reason = sample_planner.should_iterate(
            current_results=25,
            target_minimum=50,
            iteration=3,
            max_iterations=3,
        )
        assert not should_iterate
        assert "maximum iterations" in reason


# =============================================================================
# SearchResult Tests
# =============================================================================

class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_creation_empty(self) -> None:
        """Test creating empty SearchResult."""
        result = SearchResult(query_id="test")
        assert result.count == 0
        assert result.success
        assert result.error_message == ""

    def test_creation_with_documents(self) -> None:
        """Test creating SearchResult with documents."""
        result = SearchResult(
            query_id="test",
            documents=[{"id": 1}, {"id": 2}],
            document_ids={1, 2},
            execution_time_seconds=1.5,
        )
        assert result.count == 2
        assert result.success

    def test_creation_with_error(self) -> None:
        """Test creating SearchResult with error."""
        result = SearchResult(
            query_id="test",
            success=False,
            error_message="Database connection failed",
        )
        assert not result.success
        assert "Database" in result.error_message


# =============================================================================
# AggregatedResults Tests
# =============================================================================

class TestAggregatedResults:
    """Tests for AggregatedResults dataclass."""

    def test_creation_empty(self) -> None:
        """Test creating empty AggregatedResults."""
        results = AggregatedResults()
        assert results.count == 0
        assert results.total_before_dedup == 0
        assert results.deduplication_rate == 0.0

    def test_count_property(self, sample_paper_data: PaperData) -> None:
        """Test count property."""
        results = AggregatedResults(
            papers=[sample_paper_data, sample_paper_data],
        )
        assert results.count == 2

    def test_deduplication_rate(self) -> None:
        """Test deduplication rate calculation."""
        results = AggregatedResults(
            papers=[],  # 0 after dedup
            total_before_dedup=100,
        )
        # Empty papers but 100 before = 100% dedup
        assert results.deduplication_rate == 1.0

        results2 = AggregatedResults(
            papers=[PaperData(document_id=1, title="T", authors=[], year=2023, source="test")] * 50,
            total_before_dedup=100,
        )
        assert results2.deduplication_rate == 0.5

    def test_to_dict(self, sample_paper_data: PaperData) -> None:
        """Test to_dict serialization."""
        results = AggregatedResults(
            papers=[sample_paper_data],
            paper_sources={12345: ["q1", "q2"]},
            total_before_dedup=3,
            execution_time_seconds=2.5,
        )
        data = results.to_dict()

        assert data["total_papers"] == 1
        assert data["total_before_dedup"] == 3
        assert data["execution_time_seconds"] == 2.5
        assert "12345" in data["paper_sources"]


# =============================================================================
# SearchExecutor Tests
# =============================================================================

class TestSearchExecutor:
    """Tests for SearchExecutor class."""

    def test_initialization_default(self) -> None:
        """Test SearchExecutor initialization with defaults."""
        executor = SearchExecutor()
        assert executor.results_per_query > 0
        assert executor.similarity_threshold > 0

    def test_initialization_with_config(self, sample_executor: SearchExecutor) -> None:
        """Test SearchExecutor initialization with config."""
        assert sample_executor.config.model == "test-model"

    def test_callback_registration(self) -> None:
        """Test callback registration."""
        events = []

        def callback(event: str, data: str) -> None:
            events.append((event, data))

        executor = SearchExecutor(callback=callback)
        executor._call_callback("test_event", "test_data")

        assert len(events) == 1

    def test_results_per_query_limits(self) -> None:
        """Test results_per_query respects limits."""
        # Too low
        executor_low = SearchExecutor(results_per_query=1)
        assert executor_low.results_per_query >= 10

        # Too high
        executor_high = SearchExecutor(results_per_query=10000)
        assert executor_high.results_per_query <= 500

    @patch('bmlibrarian.agents.systematic_review.executor.semantic_search')
    def test_execute_semantic_query(
        self,
        mock_search: MagicMock,
        sample_executor: SearchExecutor,
    ) -> None:
        """Test semantic query execution."""
        mock_search.return_value = [
            {"id": 1, "title": "Paper 1"},
            {"id": 2, "title": "Paper 2"},
        ]

        query = PlannedQuery(
            query_id="test",
            query_text="test query",
            query_type=QueryType.SEMANTIC,
            purpose="Test",
            expected_coverage="Test",
        )

        result = sample_executor._execute_semantic_query(
            query, use_pubmed=True, use_medrxiv=True, use_others=True
        )

        assert result.success
        assert result.count == 2
        assert 1 in result.document_ids
        assert 2 in result.document_ids

    @patch('bmlibrarian.agents.systematic_review.executor.find_abstracts')
    def test_execute_keyword_query(
        self,
        mock_search: MagicMock,
        sample_executor: SearchExecutor,
    ) -> None:
        """Test keyword query execution."""
        mock_search.return_value = [
            {"id": 3, "title": "Paper 3"},
        ]

        query = PlannedQuery(
            query_id="test",
            query_text="statin & cardiovascular",
            query_type=QueryType.KEYWORD,
            purpose="Test",
            expected_coverage="Test",
        )

        result = sample_executor._execute_keyword_query(
            query, use_pubmed=True, use_medrxiv=True, use_others=True
        )

        assert result.success
        assert 3 in result.document_ids

    @patch('bmlibrarian.agents.systematic_review.executor.search_hybrid')
    def test_execute_hybrid_query(
        self,
        mock_search: MagicMock,
        sample_executor: SearchExecutor,
    ) -> None:
        """Test hybrid query execution."""
        mock_search.return_value = (
            [{"id": 4, "title": "Paper 4"}, {"id": 5, "title": "Paper 5"}],
            {"strategy": "hybrid"},
        )

        query = PlannedQuery(
            query_id="test",
            query_text="test query",
            query_type=QueryType.HYBRID,
            purpose="Test",
            expected_coverage="Test",
        )

        result = sample_executor._execute_hybrid_query(
            query, use_pubmed=True, use_medrxiv=True, use_others=True
        )

        assert result.success
        assert result.count == 2

    def test_execute_single_query_error_handling(
        self, sample_executor: SearchExecutor
    ) -> None:
        """Test error handling in single query execution."""
        query = PlannedQuery(
            query_id="test",
            query_text="test",
            query_type=QueryType.SEMANTIC,
            purpose="Test",
            expected_coverage="Test",
        )

        # Mock to raise exception
        with patch.object(
            sample_executor, '_execute_semantic_query',
            side_effect=Exception("Test error")
        ):
            result = sample_executor._execute_single_query(
                query, use_pubmed=True, use_medrxiv=True, use_others=True
            )

        assert not result.success
        assert "Test error" in result.error_message

    @patch.object(SearchExecutor, '_execute_single_query')
    @patch.object(SearchExecutor, '_fetch_paper_data')
    def test_execute_plan(
        self,
        mock_fetch: MagicMock,
        mock_execute: MagicMock,
        sample_executor: SearchExecutor,
        sample_search_plan: SearchPlan,
        sample_paper_data: PaperData,
    ) -> None:
        """Test full plan execution."""
        # Mock query execution
        mock_execute.side_effect = [
            SearchResult(query_id="q1", document_ids={1, 2}, success=True),
            SearchResult(query_id="q2", document_ids={2, 3}, success=True),  # ID 2 is duplicate
        ]

        # Mock paper fetch
        mock_fetch.return_value = [sample_paper_data]

        results = sample_executor.execute_plan(sample_search_plan)

        assert len(results.executed_queries) == 2
        assert results.total_before_dedup == 4  # 2 + 2
        # Unique IDs should be {1, 2, 3}
        assert 1 in results.paper_sources
        assert 2 in results.paper_sources
        assert 3 in results.paper_sources
        # ID 2 should be found by both queries
        assert len(results.paper_sources[2]) == 2

    def test_get_execution_summary(
        self, sample_executor: SearchExecutor, sample_paper_data: PaperData
    ) -> None:
        """Test execution summary generation."""
        results = AggregatedResults(
            papers=[sample_paper_data],
            paper_sources={12345: ["q1"]},
            total_before_dedup=5,
            executed_queries=[
                ExecutedQuery(
                    query_id="q1",
                    actual_query_text="test",
                    results_count=5,
                    new_documents_found=1,
                    execution_time_seconds=1.0,
                    success=True,
                ),
            ],
            execution_time_seconds=1.5,
        )

        summary = sample_executor.get_execution_summary(results)

        assert "Search Execution Summary" in summary
        assert "1" in summary  # Total unique papers
        assert "5" in summary  # Before dedup
        assert "q1" in summary  # Query ID


# =============================================================================
# Integration Tests (without database)
# =============================================================================

class TestPlannerExecutorIntegration:
    """Integration tests for Planner and SearchExecutor."""

    @patch('bmlibrarian.agents.systematic_review.planner.ollama.generate')
    def test_plan_and_execute_flow(
        self,
        mock_generate: MagicMock,
        sample_criteria: SearchCriteria,
    ) -> None:
        """Test complete flow from planning to execution setup."""
        # Mock LLM
        mock_generate.return_value = {"response": json.dumps({
            "is_clinical": False,
            "population": "",
            "intervention": "",
            "comparison": "",
            "outcome": "",
        })}

        # Create planner and executor
        planner = Planner()
        executor = SearchExecutor()

        # Generate plan
        plan = planner.generate_search_plan(
            sample_criteria,
            num_query_variations=1,
            include_hyde=False,
        )

        # Verify plan is valid for executor
        assert len(plan.queries) > 0
        for query in plan.queries:
            assert query.query_id
            assert query.query_text
            assert query.query_type in QueryType

    def test_iteration_workflow(
        self, sample_criteria: SearchCriteria
    ) -> None:
        """Test iteration workflow logic."""
        planner = Planner()

        # Initial plan
        with patch('bmlibrarian.agents.systematic_review.planner.ollama.generate') as mock:
            mock.return_value = {"response": "{}"}
            plan1 = planner.generate_search_plan(
                sample_criteria,
                num_query_variations=1,
                include_hyde=False,
            )

        # Check iteration decision
        should_iterate, reason = planner.should_iterate(
            current_results=5,
            target_minimum=50,
            iteration=1,
        )
        assert should_iterate

        # Generate additional queries
        with patch('bmlibrarian.agents.systematic_review.planner.ollama.generate') as mock:
            mock.return_value = {"response": "{}"}
            plan2 = planner.generate_additional_queries(
                sample_criteria,
                plan1,
                target_additional=2,
            )

        assert plan2.iteration == 2
        assert len(plan2.queries) >= len(plan1.queries)
