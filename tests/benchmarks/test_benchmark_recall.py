"""
Benchmark Tests: Paper-Level Recall and Precision

Tests the SystematicReviewAgent against Cochrane systematic reviews
to validate that it can find all papers cited in the review.

Target: 100% recall - every paper in the Cochrane review must be:
1. Found in our database
2. Scored as relevant by the agent (included in final results)

Usage:
    # Run all benchmarks
    pytest tests/benchmarks/test_benchmark_recall.py -v

    # Run specific benchmark
    pytest tests/benchmarks/test_benchmark_recall.py::test_benchmark_cd000001 -v

    # Run with detailed output
    pytest tests/benchmarks/test_benchmark_recall.py -v --tb=short
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from .benchmark_utils import (
    CochraneGroundTruth,
    BenchmarkResult,
    calculate_recall_precision,
    load_ground_truth,
    save_benchmark_result,
    TARGET_RECALL_RATE,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Directory containing ground truth JSON files
GROUND_TRUTH_DIR = Path(__file__).parent / "data"

# Directory for benchmark results output
RESULTS_DIR = Path(__file__).parent / "results"

# Skip benchmarks if no ground truth files exist
SKIP_IF_NO_DATA = True


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def systematic_review_agent():
    """
    Create SystematicReviewAgent for benchmark tests.

    Uses module scope so agent is reused across tests in this file.
    """
    try:
        from bmlibrarian.agents.systematic_review import SystematicReviewAgent
        agent = SystematicReviewAgent(show_model_info=False)
        return agent
    except Exception as e:
        pytest.skip(f"Could not create SystematicReviewAgent: {e}")


@pytest.fixture(scope="module")
def database_manager():
    """
    Create DatabaseManager for checking paper existence.
    """
    try:
        from bmlibrarian.database import DatabaseManager
        db = DatabaseManager()
        return db
    except Exception as e:
        pytest.skip(f"Could not connect to database: {e}")


def get_ground_truth_files() -> List[Path]:
    """Get all ground truth JSON files in the data directory."""
    if not GROUND_TRUTH_DIR.exists():
        return []

    return list(GROUND_TRUTH_DIR.glob("*.json"))


def load_all_ground_truths() -> List[CochraneGroundTruth]:
    """Load all ground truth datasets."""
    ground_truths = []
    for file_path in get_ground_truth_files():
        try:
            gt = load_ground_truth(str(file_path))
            ground_truths.append(gt)
        except Exception as e:
            logger.warning(f"Failed to load {file_path}: {e}")
    return ground_truths


# =============================================================================
# Helper Functions
# =============================================================================

def run_benchmark(
    agent,
    ground_truth: CochraneGroundTruth,
    save_results: bool = True,
) -> BenchmarkResult:
    """
    Run a benchmark test against a Cochrane ground truth.

    Args:
        agent: SystematicReviewAgent instance
        ground_truth: Cochrane ground truth to test against
        save_results: Whether to save results to file

    Returns:
        BenchmarkResult with detailed metrics
    """
    from bmlibrarian.agents.systematic_review.data_models import SearchCriteria

    # Build search criteria from ground truth
    criteria_dict = ground_truth.to_search_criteria_dict()
    criteria = SearchCriteria.from_dict(criteria_dict)

    # Run the systematic review
    logger.info(f"Running benchmark for {ground_truth.cochrane_id}")
    result = agent.run_review(
        criteria=criteria,
        interactive=False,  # Non-interactive for benchmarks
    )

    # Extract papers for comparison
    agent_included = result.included_papers
    agent_excluded = result.excluded_papers

    # Calculate metrics
    benchmark_result = calculate_recall_precision(
        ground_truth=ground_truth,
        agent_included=agent_included,
        agent_excluded=agent_excluded,
    )

    # Save results
    if save_results:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        result_path = RESULTS_DIR / f"benchmark_{ground_truth.cochrane_id}.json"
        save_benchmark_result(benchmark_result, str(result_path))

    return benchmark_result


def check_papers_in_database(
    db_manager,
    ground_truth: CochraneGroundTruth,
) -> Dict[str, Any]:
    """
    Pre-check which ground truth papers exist in the database.

    This helps identify if test failures are due to missing data
    vs. agent logic issues.

    Args:
        db_manager: DatabaseManager instance
        ground_truth: Ground truth to check

    Returns:
        Dict with found/missing paper counts and details
    """
    from .benchmark_utils import normalize_pmid, normalize_doi

    found_papers = []
    missing_papers = []

    for paper in ground_truth.included_studies:
        found = False

        # Check by PMID
        if paper.pmid:
            norm_pmid = normalize_pmid(paper.pmid)
            if norm_pmid:
                query = "SELECT id, title FROM document WHERE pmid = %s LIMIT 1"
                result = db_manager.execute_query(query, (norm_pmid,))
                if result:
                    found_papers.append({
                        "ground_truth": paper.to_dict(),
                        "document_id": result[0]["id"],
                        "match_method": "pmid",
                    })
                    found = True

        # Check by DOI if not found by PMID
        if not found and paper.doi:
            norm_doi = normalize_doi(paper.doi)
            if norm_doi:
                query = "SELECT id, title FROM document WHERE LOWER(doi) = %s LIMIT 1"
                result = db_manager.execute_query(query, (norm_doi,))
                if result:
                    found_papers.append({
                        "ground_truth": paper.to_dict(),
                        "document_id": result[0]["id"],
                        "match_method": "doi",
                    })
                    found = True

        if not found:
            missing_papers.append(paper.to_dict())

    return {
        "total": len(ground_truth.included_studies),
        "found": len(found_papers),
        "missing": len(missing_papers),
        "found_papers": found_papers,
        "missing_papers": missing_papers,
        "coverage": len(found_papers) / len(ground_truth.included_studies)
        if ground_truth.included_studies else 0.0,
    }


# =============================================================================
# Test Classes
# =============================================================================

class TestBenchmarkUtilities:
    """Unit tests for benchmark utility functions."""

    def test_load_ground_truth_valid(self, tmp_path):
        """Test loading a valid ground truth file."""
        # Create test file
        data = {
            "cochrane_id": "CD000001",
            "title": "Test Review",
            "research_question": "Does X improve Y?",
            "included_studies": [
                {"pmid": "12345678", "title": "Study 1"},
                {"doi": "10.1000/test", "title": "Study 2"},
            ],
        }
        file_path = tmp_path / "test_gt.json"
        with open(file_path, "w") as f:
            json.dump(data, f)

        # Load and verify
        gt = load_ground_truth(str(file_path))
        assert gt.cochrane_id == "CD000001"
        assert len(gt.included_studies) == 2
        assert gt.included_studies[0].pmid == "12345678"

    def test_load_ground_truth_missing_file(self):
        """Test loading a non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            load_ground_truth("/nonexistent/path.json")

    def test_recall_calculation_perfect(self):
        """Test recall calculation with perfect matching."""
        gt = CochraneGroundTruth(
            cochrane_id="CD000001",
            title="Test",
            research_question="Test?",
            included_studies=[
                __import__("tests.benchmarks.benchmark_utils", fromlist=["GroundTruthPaper"]).GroundTruthPaper(pmid="123"),
                __import__("tests.benchmarks.benchmark_utils", fromlist=["GroundTruthPaper"]).GroundTruthPaper(pmid="456"),
            ],
        )

        agent_included = [
            {"document_id": 1, "pmid": "123", "title": "Paper 1"},
            {"document_id": 2, "pmid": "456", "title": "Paper 2"},
        ]

        result = calculate_recall_precision(gt, agent_included, [])

        assert result.recall == 1.0
        assert result.passed is True
        assert result.papers_found_and_included == 2

    def test_recall_calculation_partial(self):
        """Test recall calculation with partial matching."""
        from .benchmark_utils import GroundTruthPaper

        gt = CochraneGroundTruth(
            cochrane_id="CD000001",
            title="Test",
            research_question="Test?",
            included_studies=[
                GroundTruthPaper(pmid="123"),
                GroundTruthPaper(pmid="456"),
                GroundTruthPaper(pmid="789"),
            ],
        )

        agent_included = [
            {"document_id": 1, "pmid": "123", "title": "Paper 1"},
        ]
        agent_excluded = [
            {"document_id": 2, "pmid": "456", "title": "Paper 2"},
        ]

        result = calculate_recall_precision(gt, agent_included, agent_excluded)

        # Only 1 of 3 found and included
        assert result.recall == pytest.approx(1/3, rel=0.01)
        assert result.passed is False
        assert result.papers_found == 2  # 123 and 456 found
        assert result.papers_found_and_included == 1  # only 123 included
        assert result.papers_not_found == 1  # 789 not found


class TestBenchmarkRecall:
    """
    Main benchmark tests comparing agent against Cochrane reviews.

    Each test loads a ground truth file and runs the full systematic
    review workflow, comparing results against the expected papers.
    """

    @pytest.mark.skipif(
        not get_ground_truth_files(),
        reason="No ground truth files found in tests/benchmarks/data/"
    )
    @pytest.mark.parametrize(
        "ground_truth_file",
        get_ground_truth_files(),
        ids=lambda f: f.stem,
    )
    def test_benchmark_against_cochrane(
        self,
        systematic_review_agent,
        ground_truth_file: Path,
    ):
        """
        Test agent against a Cochrane review ground truth.

        This is the main benchmark test. It:
        1. Loads ground truth from JSON
        2. Runs the systematic review agent
        3. Compares results against ground truth
        4. Asserts 100% recall

        Args:
            systematic_review_agent: Agent fixture
            ground_truth_file: Path to ground truth JSON
        """
        # Load ground truth
        ground_truth = load_ground_truth(str(ground_truth_file))

        logger.info(
            f"Running benchmark: {ground_truth.cochrane_id} "
            f"({ground_truth.study_count} studies)"
        )

        # Run benchmark
        result = run_benchmark(
            agent=systematic_review_agent,
            ground_truth=ground_truth,
            save_results=True,
        )

        # Log results
        logger.info(result.get_summary())

        if not result.passed:
            logger.error(result.get_missing_papers_report())

        # Assert 100% recall
        assert result.passed, (
            f"Benchmark failed for {ground_truth.cochrane_id}:\n"
            f"{result.get_summary()}\n\n"
            f"{result.get_missing_papers_report()}"
        )


class TestDatabaseCoverage:
    """
    Pre-flight tests to check database coverage before running benchmarks.

    These tests help identify if benchmark failures are due to missing
    papers in the database vs. agent logic issues.
    """

    @pytest.mark.skipif(
        not get_ground_truth_files(),
        reason="No ground truth files found"
    )
    @pytest.mark.parametrize(
        "ground_truth_file",
        get_ground_truth_files(),
        ids=lambda f: f.stem,
    )
    def test_database_coverage(
        self,
        database_manager,
        ground_truth_file: Path,
    ):
        """
        Check what percentage of ground truth papers exist in database.

        This is a diagnostic test - it doesn't assert pass/fail but
        reports coverage statistics to help understand benchmark results.
        """
        ground_truth = load_ground_truth(str(ground_truth_file))

        coverage = check_papers_in_database(database_manager, ground_truth)

        logger.info(
            f"Database coverage for {ground_truth.cochrane_id}: "
            f"{coverage['found']}/{coverage['total']} "
            f"({coverage['coverage']:.1%})"
        )

        if coverage['missing_papers']:
            logger.warning(
                f"Missing papers:\n" +
                "\n".join(
                    f"  - PMID:{p.get('pmid')} DOI:{p.get('doi')} {p.get('title', '')[:50]}"
                    for p in coverage['missing_papers']
                )
            )

        # Report but don't fail - this is diagnostic
        # The actual benchmark test will fail if coverage is insufficient


# =============================================================================
# Manual Benchmark Runner
# =============================================================================

def run_all_benchmarks():
    """
    Run all benchmarks and generate summary report.

    Can be called directly for manual testing outside pytest.
    """
    from bmlibrarian.agents.systematic_review import SystematicReviewAgent

    agent = SystematicReviewAgent(show_model_info=False)
    ground_truths = load_all_ground_truths()

    if not ground_truths:
        print("No ground truth files found in tests/benchmarks/data/")
        return

    results = []
    for gt in ground_truths:
        print(f"\nRunning benchmark: {gt.cochrane_id}")
        result = run_benchmark(agent, gt, save_results=True)
        results.append(result)
        print(result.get_summary())

    # Summary
    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)
    passed = sum(1 for r in results if r.passed)
    print(f"Passed: {passed}/{len(results)}")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.ground_truth.cochrane_id}: recall={r.recall:.1%}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_all_benchmarks()
