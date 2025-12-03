"""
Unit tests for SystematicReviewAgent Reporter component.

Tests cover:
- JSON report generation
- Markdown report formatting
- CSV export functionality
- PRISMA flow diagram data generation
- Report metadata construction
- Search strategy formatting
- Statistics calculation
"""

import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List

from bmlibrarian.agents.systematic_review import (
    # Enums
    StudyTypeFilter,
    QueryType,
    InclusionStatus,
    ExclusionStage,
    # Input models
    SearchCriteria,
    ScoringWeights,
    # Search planning models
    PlannedQuery,
    SearchPlan,
    ExecutedQuery,
    # Paper data models
    PaperData,
    InclusionDecision,
    ScoredPaper,
    AssessedPaper,
    # Output models
    ReviewStatistics,
    SystematicReviewResult,
    # Documenter
    Documenter,
)
from bmlibrarian.agents.systematic_review.reporter import (
    Reporter,
    REPORT_FORMAT_VERSION,
    CSV_COLUMNS_INCLUDED,
    CSV_COLUMNS_EXCLUDED,
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
            "Case reports"
        ],
        target_study_types=[
            StudyTypeFilter.RCT,
            StudyTypeFilter.META_ANALYSIS,
        ],
        date_range=(2010, 2024),
    )


@pytest.fixture
def sample_weights() -> ScoringWeights:
    """Create sample ScoringWeights for testing."""
    return ScoringWeights(
        relevance=0.30,
        study_quality=0.25,
        paper_weight=0.25,
        recency=0.10,
        source_reliability=0.10,
    )


@pytest.fixture
def sample_paper() -> PaperData:
    """Create sample PaperData for testing."""
    return PaperData(
        document_id=12345,
        title="Effect of Statins on Cardiovascular Outcomes: A Meta-Analysis",
        abstract="Background: Statins are widely used... Results: Significant reduction...",
        authors=["Smith J", "Johnson A", "Williams B"],
        year=2022,
        journal="JAMA Cardiology",
        doi="10.1001/jamacardio.2022.1234",
        pmid="34567890",
        source="pubmed",
    )


@pytest.fixture
def sample_scored_paper(sample_paper: PaperData) -> ScoredPaper:
    """Create sample ScoredPaper for testing."""
    return ScoredPaper(
        paper=sample_paper,
        relevance_score=4.5,
        relevance_rationale="Directly addresses statin efficacy for CVD prevention",
        inclusion_decision=InclusionDecision.create_included(
            stage=ExclusionStage.QUALITY_GATE,
            rationale="Meets all inclusion criteria",
            criteria_matched=["Human studies", "Statin intervention"],
        ),
        search_provenance=["semantic_001", "keyword_002"],
    )


@pytest.fixture
def sample_assessed_paper(sample_scored_paper: ScoredPaper) -> AssessedPaper:
    """Create sample AssessedPaper for testing."""
    return AssessedPaper(
        scored_paper=sample_scored_paper,
        study_assessment={
            "study_type": "meta_analysis",
            "quality_score": 8.5,
            "strengths": ["Large sample size", "Rigorous methodology"],
            "limitations": ["Publication bias possible"],
        },
        paper_weight={
            "composite_score": 7.5,
            "dimensions": [
                {"name": "sample_size", "score": 8.0},
                {"name": "methodology", "score": 7.0},
            ],
        },
        pico_components=None,
        prisma_assessment=None,
        final_rank=1,
    )


@pytest.fixture
def sample_excluded_paper() -> ScoredPaper:
    """Create sample excluded ScoredPaper for testing."""
    paper = PaperData(
        document_id=23456,
        title="Statin Effects in Rat Models",
        abstract="Animal study examining statin effects...",
        authors=["Brown C", "Davis D"],
        year=2021,
        journal="Animal Research",
        source="pubmed",
    )
    return ScoredPaper(
        paper=paper,
        relevance_score=2.0,
        relevance_rationale="Animal study, not human research",
        inclusion_decision=InclusionDecision.create_excluded(
            stage=ExclusionStage.INITIAL_FILTER,
            reasons=["Animal study"],
            rationale="Excluded per exclusion criteria: Animal studies",
        ),
    )


@pytest.fixture
def sample_search_plan() -> SearchPlan:
    """Create sample SearchPlan for testing."""
    queries = [
        PlannedQuery(
            query_id="semantic_001",
            query_text="statin cardiovascular disease prevention efficacy",
            query_type=QueryType.SEMANTIC,
            purpose="Primary semantic search",
            expected_coverage="Broad semantic similarity",
            priority=1,
            estimated_results=100,
        ),
        PlannedQuery(
            query_id="keyword_002",
            query_text="statin & (cardiovascular | CVD) & prevention",
            query_type=QueryType.KEYWORD,
            purpose="Keyword search with key terms",
            expected_coverage="Documents containing all key terms",
            priority=2,
            estimated_results=50,
        ),
    ]
    return SearchPlan(
        queries=queries,
        total_estimated_yield=150,
        search_rationale="Multi-strategy search for comprehensive coverage",
        iteration=1,
        coverage_analysis="Semantic and keyword search combined",
    )


@pytest.fixture
def sample_executed_queries(sample_search_plan: SearchPlan) -> List[ExecutedQuery]:
    """Create sample ExecutedQuery list for testing."""
    return [
        ExecutedQuery(
            planned_query=sample_search_plan.queries[0],
            document_ids=[12345, 23456, 34567],
            execution_time_seconds=1.5,
            actual_results=3,
        ),
        ExecutedQuery(
            planned_query=sample_search_plan.queries[1],
            document_ids=[12345, 45678],
            execution_time_seconds=0.8,
            actual_results=2,
        ),
    ]


@pytest.fixture
def sample_statistics() -> ReviewStatistics:
    """Create sample ReviewStatistics for testing."""
    return ReviewStatistics(
        total_considered=100,
        passed_initial_filter=80,
        passed_relevance_threshold=50,
        passed_quality_gate=30,
        final_included=25,
        final_excluded=70,
        uncertain_for_review=5,
        processing_time_seconds=120.5,
        total_llm_calls=150,
        total_tokens_used=50000,
    )


@pytest.fixture
def documenter() -> Documenter:
    """Create Documenter for testing."""
    return Documenter(review_id="test-review-001")


@pytest.fixture
def reporter(
    documenter: Documenter,
    sample_criteria: SearchCriteria,
    sample_weights: ScoringWeights,
) -> Reporter:
    """Create Reporter for testing."""
    documenter.start_review()
    return Reporter(
        documenter=documenter,
        criteria=sample_criteria,
        weights=sample_weights,
    )


# =============================================================================
# Test Reporter Initialization
# =============================================================================

class TestReporterInit:
    """Tests for Reporter initialization."""

    def test_reporter_init_basic(self, documenter: Documenter):
        """Test basic Reporter initialization."""
        reporter = Reporter(documenter=documenter)

        assert reporter.documenter is documenter
        assert reporter.criteria is None
        assert reporter.weights is not None

    def test_reporter_init_with_criteria(
        self,
        documenter: Documenter,
        sample_criteria: SearchCriteria,
        sample_weights: ScoringWeights,
    ):
        """Test Reporter initialization with criteria and weights."""
        reporter = Reporter(
            documenter=documenter,
            criteria=sample_criteria,
            weights=sample_weights,
        )

        assert reporter.criteria is sample_criteria
        assert reporter.weights is sample_weights


# =============================================================================
# Test JSON Report Generation
# =============================================================================

class TestJSONReportGeneration:
    """Tests for JSON report generation."""

    def test_build_json_result(
        self,
        reporter: Reporter,
        sample_assessed_paper: AssessedPaper,
        sample_excluded_paper: ScoredPaper,
        sample_search_plan: SearchPlan,
        sample_executed_queries: List[ExecutedQuery],
        sample_statistics: ReviewStatistics,
    ):
        """Test building JSON result."""
        result = reporter.build_json_result(
            included_papers=[sample_assessed_paper],
            excluded_papers=[sample_excluded_paper],
            uncertain_papers=[],
            search_plan=sample_search_plan,
            executed_queries=sample_executed_queries,
            statistics=sample_statistics,
        )

        assert isinstance(result, SystematicReviewResult)
        assert len(result.included_papers) == 1
        assert len(result.excluded_papers) == 1
        assert len(result.uncertain_papers) == 0

    def test_json_result_metadata(
        self,
        reporter: Reporter,
        sample_assessed_paper: AssessedPaper,
        sample_statistics: ReviewStatistics,
    ):
        """Test JSON result contains correct metadata."""
        result = reporter.build_json_result(
            included_papers=[sample_assessed_paper],
            excluded_papers=[],
            uncertain_papers=[],
            statistics=sample_statistics,
        )

        assert "generated_at" in result.metadata
        assert result.metadata["report_format_version"] == REPORT_FORMAT_VERSION
        assert "research_question" in result.metadata

    def test_json_result_search_strategy(
        self,
        reporter: Reporter,
        sample_search_plan: SearchPlan,
        sample_executed_queries: List[ExecutedQuery],
        sample_statistics: ReviewStatistics,
    ):
        """Test JSON result contains search strategy."""
        result = reporter.build_json_result(
            included_papers=[],
            excluded_papers=[],
            uncertain_papers=[],
            search_plan=sample_search_plan,
            executed_queries=sample_executed_queries,
            statistics=sample_statistics,
        )

        assert len(result.search_strategy["queries_planned"]) == 2
        assert len(result.search_strategy["queries_executed"]) == 2
        assert result.search_strategy["total_papers_found"] == 5  # 3 + 2

    def test_generate_json_report_file(
        self,
        reporter: Reporter,
        sample_assessed_paper: AssessedPaper,
        sample_statistics: ReviewStatistics,
    ):
        """Test JSON report file generation."""
        result = reporter.build_json_result(
            included_papers=[sample_assessed_paper],
            excluded_papers=[],
            uncertain_papers=[],
            statistics=sample_statistics,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_report.json"
            reporter.generate_json_report(result, str(output_path))

            assert output_path.exists()

            # Verify JSON is valid and contains expected data
            with open(output_path) as f:
                data = json.load(f)

            assert "metadata" in data
            assert "included_papers" in data
            assert len(data["included_papers"]) == 1


# =============================================================================
# Test Markdown Report Generation
# =============================================================================

class TestMarkdownReportGeneration:
    """Tests for Markdown report generation."""

    def test_generate_markdown_report(
        self,
        reporter: Reporter,
        sample_assessed_paper: AssessedPaper,
        sample_excluded_paper: ScoredPaper,
        sample_statistics: ReviewStatistics,
    ):
        """Test Markdown report generation."""
        result = reporter.build_json_result(
            included_papers=[sample_assessed_paper],
            excluded_papers=[sample_excluded_paper],
            uncertain_papers=[],
            statistics=sample_statistics,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_report.md"
            reporter.generate_markdown_report(result, str(output_path))

            assert output_path.exists()

            content = output_path.read_text()

            # Check for key sections
            assert "# Systematic Literature Review Report" in content
            assert "## Review Information" in content
            assert "## Executive Summary" in content
            assert "## Included Papers" in content

    def test_markdown_includes_paper_details(
        self,
        reporter: Reporter,
        sample_assessed_paper: AssessedPaper,
        sample_statistics: ReviewStatistics,
    ):
        """Test Markdown includes paper details."""
        result = reporter.build_json_result(
            included_papers=[sample_assessed_paper],
            excluded_papers=[],
            uncertain_papers=[],
            statistics=sample_statistics,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_report.md"
            reporter.generate_markdown_report(result, str(output_path))

            content = output_path.read_text()

            # Check paper details are present
            assert "Effect of Statins" in content
            assert "Smith J" in content
            assert "2022" in content

    def test_markdown_prisma_section(
        self,
        reporter: Reporter,
        sample_statistics: ReviewStatistics,
    ):
        """Test Markdown includes PRISMA flow diagram."""
        result = reporter.build_json_result(
            included_papers=[],
            excluded_papers=[],
            uncertain_papers=[],
            statistics=sample_statistics,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_report.md"
            reporter.generate_markdown_report(result, str(output_path))

            content = output_path.read_text()

            assert "PRISMA 2020 Flow Diagram" in content
            assert "IDENTIFICATION" in content
            assert "SCREENING" in content
            assert "INCLUDED" in content


# =============================================================================
# Test CSV Export
# =============================================================================

class TestCSVExport:
    """Tests for CSV export functionality."""

    def test_csv_columns_defined(self):
        """Test CSV column definitions exist."""
        assert len(CSV_COLUMNS_INCLUDED) > 0
        assert len(CSV_COLUMNS_EXCLUDED) > 0

        # Check expected columns
        assert "title" in CSV_COLUMNS_INCLUDED
        assert "document_id" in CSV_COLUMNS_INCLUDED
        assert "relevance_score" in CSV_COLUMNS_INCLUDED

    def test_generate_csv_export(
        self,
        reporter: Reporter,
        sample_assessed_paper: AssessedPaper,
        sample_excluded_paper: ScoredPaper,
    ):
        """Test CSV export generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_export.csv"

            reporter.generate_csv_export(
                papers=[sample_assessed_paper],
                output_path=str(output_path),
                include_excluded=True,
                excluded_papers=[sample_excluded_paper],
            )

            # Check main CSV
            assert output_path.exists()

            content = output_path.read_text()
            lines = content.strip().split("\n")

            # Header + 1 data row
            assert len(lines) == 2

            # Check excluded CSV
            excluded_path = output_path.with_stem(output_path.stem + "_excluded")
            assert excluded_path.exists()


# =============================================================================
# Test PRISMA Flow Diagram
# =============================================================================

class TestPRISMAFlowDiagram:
    """Tests for PRISMA flow diagram data generation."""

    def test_generate_prisma_flowchart(
        self,
        reporter: Reporter,
        sample_statistics: ReviewStatistics,
    ):
        """Test PRISMA flow diagram data generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "prisma_flow.json"

            reporter.generate_prisma_flowchart(
                statistics=sample_statistics,
                output_path=str(output_path),
            )

            assert output_path.exists()

            with open(output_path) as f:
                data = json.load(f)

            # Check PRISMA 2020 structure
            assert data["format"] == "PRISMA_2020"
            assert "identification" in data
            assert "screening" in data
            assert "eligibility" in data
            assert "included" in data

    def test_prisma_data_values(
        self,
        reporter: Reporter,
        sample_statistics: ReviewStatistics,
    ):
        """Test PRISMA data contains correct values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "prisma_flow.json"

            reporter.generate_prisma_flowchart(
                statistics=sample_statistics,
                output_path=str(output_path),
            )

            with open(output_path) as f:
                data = json.load(f)

            # Check values match statistics
            assert data["identification"]["databases"]["records_identified"] == 100
            assert data["included"]["studies_included"] == 25
            assert data["included"]["for_human_review"] == 5


# =============================================================================
# Test Export All
# =============================================================================

class TestExportAll:
    """Tests for combined export functionality."""

    def test_export_all_creates_files(
        self,
        reporter: Reporter,
        sample_assessed_paper: AssessedPaper,
        sample_statistics: ReviewStatistics,
    ):
        """Test export_all creates all output files."""
        result = reporter.build_json_result(
            included_papers=[sample_assessed_paper],
            excluded_papers=[],
            uncertain_papers=[],
            statistics=sample_statistics,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = reporter.export_all(
                result=result,
                output_dir=tmpdir,
                base_name="test_review",
            )

            # Check paths returned
            assert "json" in paths
            assert "markdown" in paths
            assert "prisma" in paths

            # Check files created
            assert Path(paths["json"]).exists()
            assert Path(paths["markdown"]).exists()
            assert Path(paths["prisma"]).exists()


# =============================================================================
# Test Statistics Calculation
# =============================================================================

class TestStatisticsCalculation:
    """Tests for statistics calculation."""

    def test_calculate_statistics(
        self,
        reporter: Reporter,
        sample_assessed_paper: AssessedPaper,
        sample_excluded_paper: ScoredPaper,
    ):
        """Test statistics are calculated correctly."""
        result = reporter.build_json_result(
            included_papers=[sample_assessed_paper],
            excluded_papers=[sample_excluded_paper],
            uncertain_papers=[],
        )

        stats = result.statistics

        assert stats.final_included == 1
        assert stats.final_excluded == 1
        assert stats.uncertain_for_review == 0


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_papers(self, reporter: Reporter, sample_statistics: ReviewStatistics):
        """Test handling of empty paper lists."""
        result = reporter.build_json_result(
            included_papers=[],
            excluded_papers=[],
            uncertain_papers=[],
            statistics=sample_statistics,
        )

        assert len(result.included_papers) == 0
        assert len(result.excluded_papers) == 0

    def test_no_search_plan(self, reporter: Reporter, sample_statistics: ReviewStatistics):
        """Test handling when no search plan provided."""
        result = reporter.build_json_result(
            included_papers=[],
            excluded_papers=[],
            uncertain_papers=[],
            search_plan=None,
            executed_queries=None,
            statistics=sample_statistics,
        )

        # Should still generate valid result
        assert result.search_strategy is not None
        assert len(result.search_strategy["queries_planned"]) == 0

    def test_long_title_truncation(
        self,
        reporter: Reporter,
        sample_statistics: ReviewStatistics,
    ):
        """Test handling of very long titles in reports."""
        paper = PaperData(
            document_id=99999,
            title="A" * 500,  # Very long title
            abstract="Short abstract",
            authors=["Test Author"],
            year=2023,
            source="test",
        )

        scored = ScoredPaper(
            paper=paper,
            relevance_score=4.0,
            relevance_rationale="Test",
            inclusion_decision=InclusionDecision.create_included(
                stage=ExclusionStage.QUALITY_GATE,
                rationale="Test",
                criteria_matched=[],
            ),
        )

        assessed = AssessedPaper(
            scored_paper=scored,
            study_assessment={"study_type": "unknown", "quality_score": 5.0},
            paper_weight={"composite_score": 5.0},
            final_rank=1,
        )

        result = reporter.build_json_result(
            included_papers=[assessed],
            excluded_papers=[],
            uncertain_papers=[],
            statistics=sample_statistics,
        )

        # Should handle long title without error
        assert len(result.included_papers) == 1
