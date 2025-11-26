# SystematicReviewAgent Validation Strategy

This document outlines the comprehensive testing and validation approach for the SystematicReviewAgent.

## Validation Goals

1. **Correctness**: The agent produces accurate, defensible results
2. **Reproducibility**: Same inputs produce consistent outputs
3. **Robustness**: The agent handles edge cases gracefully
4. **Performance**: The agent scales to realistic workloads
5. **Usability**: The output is useful for researchers

## Testing Pyramid

```
                    ┌───────────────┐
                    │  Benchmarks   │  ← Gold standard comparison
                    │  (2-3 tests)  │
                    └───────────────┘
               ┌─────────────────────────┐
               │   Integration Tests     │  ← Full workflow tests
               │      (10-15 tests)      │
               └─────────────────────────┘
          ┌───────────────────────────────────┐
          │         Component Tests           │  ← Individual components
          │         (30-50 tests)             │
          └───────────────────────────────────┘
     ┌─────────────────────────────────────────────┐
     │              Unit Tests                      │  ← Data models, utilities
     │              (50-100 tests)                  │
     └─────────────────────────────────────────────┘
```

## Unit Testing

### Data Model Tests

**File**: `tests/test_systematic_review_data_models.py`

```python
class TestSearchCriteria:
    """Test SearchCriteria dataclass."""

    def test_valid_criteria(self):
        """Test valid criteria creation."""
        criteria = SearchCriteria(
            research_question="What is the effect of X on Y?",
            purpose="Systematic review for clinical guidelines",
            inclusion_criteria=["RCT", "Human subjects", "Published 2015-2024"],
            exclusion_criteria=["Animal studies", "Case reports"],
        )
        assert criteria.research_question == "What is the effect of X on Y?"
        assert len(criteria.inclusion_criteria) == 3

    def test_empty_research_question_validation(self):
        """Test that empty research question is flagged."""
        criteria = SearchCriteria(
            research_question="",
            purpose="Test",
            inclusion_criteria=["Any"],
            exclusion_criteria=[],
        )
        errors = validate_search_criteria(criteria)
        assert "Research question cannot be empty" in errors

    def test_no_inclusion_criteria_validation(self):
        """Test that missing inclusion criteria is flagged."""
        criteria = SearchCriteria(
            research_question="Test question",
            purpose="Test",
            inclusion_criteria=[],
            exclusion_criteria=[],
        )
        errors = validate_search_criteria(criteria)
        assert "At least one inclusion criterion is required" in errors

    def test_invalid_date_range(self):
        """Test that invalid date range is flagged."""
        criteria = SearchCriteria(
            research_question="Test",
            purpose="Test",
            inclusion_criteria=["Any"],
            exclusion_criteria=[],
            date_range=(2024, 2020),  # End before start
        )
        errors = validate_search_criteria(criteria)
        assert any("date range" in e.lower() for e in errors)

    def test_serialization_roundtrip(self):
        """Test JSON serialization and deserialization."""
        original = SearchCriteria(
            research_question="Test",
            purpose="Test purpose",
            inclusion_criteria=["A", "B"],
            exclusion_criteria=["C"],
            date_range=(2020, 2024),
        )
        data = original.to_dict()
        # Reconstruct from dict
        reconstructed = SearchCriteria(**data)
        assert reconstructed.research_question == original.research_question


class TestScoringWeights:
    """Test ScoringWeights dataclass."""

    def test_default_weights_sum_to_one(self):
        """Test that default weights sum to 1.0."""
        weights = ScoringWeights()
        assert weights.validate()

    def test_custom_weights_validation(self):
        """Test custom weight validation."""
        weights = ScoringWeights(
            relevance=0.5,
            study_quality=0.5,
            methodological_rigor=0.0,
            sample_size=0.0,
            recency=0.0,
            replication_status=0.0,
        )
        assert weights.validate()

    def test_invalid_weights_detected(self):
        """Test that invalid weights are detected."""
        weights = ScoringWeights(
            relevance=0.5,
            study_quality=0.3,
            methodological_rigor=0.1,
            sample_size=0.1,
            recency=0.1,
            replication_status=0.1,  # Sum = 1.2
        )
        assert not weights.validate()


class TestInclusionDecision:
    """Test InclusionDecision dataclass."""

    def test_included_paper(self):
        """Test creating an inclusion decision."""
        decision = InclusionDecision(
            status=InclusionStatus.INCLUDED,
            stage=ExclusionStage.INCLUSION_CRITERIA,
            reasons=["Meets all criteria"],
            rationale="RCT with adequate sample size studying intervention of interest.",
            confidence=0.95,
            criteria_matched=["RCT", "Human subjects", "Relevant intervention"],
        )
        assert decision.status == InclusionStatus.INCLUDED
        assert decision.confidence == 0.95

    def test_excluded_paper(self):
        """Test creating an exclusion decision."""
        decision = InclusionDecision(
            status=InclusionStatus.EXCLUDED,
            stage=ExclusionStage.EXCLUSION_CRITERIA,
            reasons=["Animal study"],
            rationale="Study was conducted in mice, not humans.",
            exclusion_matched=["Animal studies"],
        )
        assert decision.status == InclusionStatus.EXCLUDED
        assert "Animal studies" in decision.exclusion_matched
```

### Documenter Tests

**File**: `tests/test_systematic_review_documenter.py`

```python
class TestDocumenter:
    """Test Documenter component."""

    def test_log_step(self):
        """Test step logging."""
        doc = Documenter()
        step = doc.log_step(
            action="execute_search",
            tool="SemanticQueryAgent",
            input_summary="Query: cardiovascular disease",
            output_summary="Found 150 documents",
            decision_rationale="Initial broad search",
            metrics={"documents_found": 150},
        )
        assert step.step_number == 1
        assert step.action == "execute_search"
        assert len(doc.steps) == 1

    def test_step_numbering(self):
        """Test that steps are numbered sequentially."""
        doc = Documenter()
        for i in range(5):
            step = doc.log_step(
                action=f"step_{i}",
                tool=None,
                input_summary="",
                output_summary="",
                decision_rationale="",
                metrics={},
            )
            assert step.step_number == i + 1

    def test_checkpoint_logging(self):
        """Test checkpoint creation."""
        doc = Documenter()
        checkpoint = doc.log_checkpoint(
            checkpoint_type="strategy_approval",
            phase="planning",
            state_snapshot={"queries": ["q1", "q2"]},
            user_decision="approved",
        )
        assert checkpoint.checkpoint_type == "strategy_approval"
        assert len(doc.checkpoints) == 1

    def test_process_log_generation(self):
        """Test process log serialization."""
        doc = Documenter()
        doc.log_step("test", None, "in", "out", "why", {})
        log = doc.generate_process_log()
        assert isinstance(log, list)
        assert len(log) == 1
        assert log[0]["action"] == "test"
```

## Component Testing

### Planner Tests

**File**: `tests/test_systematic_review_planner.py`

```python
class TestPlanner:
    """Test Planner component."""

    @pytest.fixture
    def planner(self):
        """Create planner instance."""
        return Planner(
            model="gpt-oss:20b",
            host="http://localhost:11434",
            config={"max_query_variations": 3},
        )

    def test_generate_search_plan(self, planner, mocker):
        """Test search plan generation."""
        # Mock LLM response
        mocker.patch.object(
            planner, "_generate_query_variations",
            return_value=["query1", "query2", "query3"],
        )

        criteria = SearchCriteria(
            research_question="Effect of exercise on cardiovascular health",
            purpose="Systematic review",
            inclusion_criteria=["RCT", "Adults"],
            exclusion_criteria=["Children"],
        )

        plan = planner.generate_search_plan(criteria)

        assert isinstance(plan, SearchPlan)
        assert len(plan.queries) >= 1
        assert plan.search_rationale is not None

    def test_query_type_diversity(self, planner, mocker):
        """Test that plan includes diverse query types."""
        mocker.patch.object(
            planner, "_generate_query_variations",
            return_value=["semantic query"],
        )

        criteria = SearchCriteria(
            research_question="Test",
            purpose="Test",
            inclusion_criteria=["Any"],
            exclusion_criteria=[],
        )

        plan = planner.generate_search_plan(criteria)

        query_types = [q.query_type for q in plan.queries]
        # Should have both semantic and keyword at minimum
        assert QueryType.SEMANTIC in query_types or QueryType.HYBRID in query_types

    def test_should_iterate_insufficient_results(self, planner):
        """Test iteration decision with insufficient results."""
        should_continue, reason = planner.should_iterate(
            current_results=5,
            target_minimum=20,
            iteration=1,
        )
        assert should_continue is True
        assert "insufficient" in reason.lower()

    def test_should_iterate_max_iterations(self, planner):
        """Test iteration stops at max iterations."""
        should_continue, reason = planner.should_iterate(
            current_results=5,
            target_minimum=20,
            iteration=3,  # Max iterations reached
        )
        assert should_continue is False
```

### Filter Tests

**File**: `tests/test_systematic_review_filters.py`

```python
class TestInitialFilter:
    """Test InitialFilter component."""

    @pytest.fixture
    def filter_with_date_range(self):
        """Create filter with date range."""
        criteria = SearchCriteria(
            research_question="Test",
            purpose="Test",
            inclusion_criteria=["Any"],
            exclusion_criteria=["animal", "in vitro"],
            date_range=(2015, 2024),
        )
        return InitialFilter(criteria)

    def test_date_range_filtering(self, filter_with_date_range):
        """Test papers outside date range are excluded."""
        old_paper = PaperData(
            document_id=1,
            title="Old Study",
            authors=["Smith"],
            year=2010,
        )
        new_paper = PaperData(
            document_id=2,
            title="New Study",
            authors=["Jones"],
            year=2020,
        )

        passed, rejected = filter_with_date_range.filter_batch([old_paper, new_paper])

        assert len(passed) == 1
        assert passed[0].document_id == 2
        assert len(rejected) == 1
        assert rejected[0][0].document_id == 1

    def test_exclusion_keyword_filtering(self, filter_with_date_range):
        """Test exclusion keyword matching."""
        animal_paper = PaperData(
            document_id=1,
            title="Mouse Study of Disease",
            authors=["Smith"],
            year=2020,
            abstract="We studied disease progression in animal models.",
        )
        human_paper = PaperData(
            document_id=2,
            title="Clinical Trial",
            authors=["Jones"],
            year=2020,
            abstract="Randomized controlled trial in adults.",
        )

        passed, rejected = filter_with_date_range.filter_batch([animal_paper, human_paper])

        assert len(passed) == 1
        assert passed[0].document_id == 2


class TestInclusionEvaluator:
    """Test InclusionEvaluator component."""

    @pytest.fixture
    def evaluator(self, mocker):
        """Create evaluator with mocked LLM."""
        criteria = SearchCriteria(
            research_question="Effect of statins on heart disease",
            purpose="Clinical guidelines",
            inclusion_criteria=[
                "Randomized controlled trial",
                "Adult humans",
                "Statin intervention",
            ],
            exclusion_criteria=[
                "Animal studies",
                "Pediatric population",
            ],
        )
        evaluator = InclusionEvaluator(
            model="gpt-oss:20b",
            host="http://localhost:11434",
            criteria=criteria,
        )

        # Mock the LLM call
        mock_response = json.dumps({
            "status": "included",
            "criteria_matched": ["RCT", "Adults", "Statin"],
            "criteria_failed": [],
            "rationale": "Study meets all inclusion criteria.",
            "confidence": 0.9,
        })
        mocker.patch.object(
            evaluator, "_call_llm",
            return_value=mock_response,
        )

        return evaluator

    def test_evaluate_included_paper(self, evaluator):
        """Test evaluation of a paper that should be included."""
        paper = PaperData(
            document_id=1,
            title="Statin Therapy in Adults: An RCT",
            authors=["Smith"],
            year=2020,
            abstract="Randomized controlled trial of statin therapy in adults.",
        )

        decision = evaluator.evaluate(paper, relevance_score=4.5)

        assert decision.status == InclusionStatus.INCLUDED
        assert decision.confidence >= 0.8
```

### Quality Assessor Tests

**File**: `tests/test_systematic_review_quality.py`

```python
class TestQualityAssessor:
    """Test QualityAssessor component."""

    @pytest.fixture
    def assessor(self, mocker):
        """Create assessor with mocked child agents."""
        assessor = QualityAssessor(config={})

        # Mock child agents
        mocker.patch.object(
            assessor.study_agent, "assess_study",
            return_value=StudyAssessment(
                study_type="RCT",
                study_design="Randomized, double-blind",
                quality_score=7.5,
                strengths=["Large sample"],
                limitations=["Short follow-up"],
                overall_confidence=0.8,
                confidence_explanation="Good methodology",
                evidence_level="Level 1",
                document_id="1",
                document_title="Test",
            ),
        )

        return assessor

    def test_conditional_pico_execution(self, assessor, mocker):
        """Test PICO is only run for applicable study types."""
        pico_mock = mocker.patch.object(
            assessor.pico_agent, "extract_pico",
        )

        # RCT should trigger PICO
        rct_paper = create_mock_scored_paper(study_type="RCT")
        assessor._assess_single(rct_paper)
        assert pico_mock.called

        pico_mock.reset_mock()

        # Case report should not trigger PICO
        case_paper = create_mock_scored_paper(study_type="case_report")
        assessor._assess_single(case_paper)
        assert not pico_mock.called

    def test_conditional_prisma_execution(self, assessor, mocker):
        """Test PRISMA is only run for systematic reviews."""
        prisma_mock = mocker.patch.object(
            assessor.prisma_agent, "assess",
        )

        # Systematic review should trigger PRISMA
        sr_paper = create_mock_scored_paper(study_type="systematic_review")
        assessor._assess_single(sr_paper)
        assert prisma_mock.called

        prisma_mock.reset_mock()

        # RCT should not trigger PRISMA
        rct_paper = create_mock_scored_paper(study_type="RCT")
        assessor._assess_single(rct_paper)
        assert not prisma_mock.called


class TestCompositeScorer:
    """Test CompositeScorer component."""

    def test_default_weights(self):
        """Test scoring with default weights."""
        weights = ScoringWeights()
        scorer = CompositeScorer(weights)

        paper = create_mock_assessed_paper(
            relevance_score=4.0,  # Out of 5
            quality_score=8.0,   # Out of 10
            methodological_score=7.0,  # Out of 10
        )

        score = scorer.score(paper)

        # Score should be between 0 and 10
        assert 0 <= score <= 10

    def test_ranking_order(self):
        """Test that papers are ranked correctly."""
        weights = ScoringWeights()
        scorer = CompositeScorer(weights)

        papers = [
            create_mock_assessed_paper(relevance_score=3.0, quality_score=6.0),
            create_mock_assessed_paper(relevance_score=5.0, quality_score=9.0),
            create_mock_assessed_paper(relevance_score=4.0, quality_score=7.0),
        ]

        ranked = scorer.rank(papers)

        # Best paper should be first
        assert ranked[0].scored_paper.relevance_score == 5.0
        assert ranked[-1].scored_paper.relevance_score == 3.0

    def test_quality_gate(self):
        """Test quality gate filtering."""
        weights = ScoringWeights()
        scorer = CompositeScorer(weights)

        papers = [
            create_mock_assessed_paper(quality_score=8.0),
            create_mock_assessed_paper(quality_score=3.0),
            create_mock_assessed_paper(quality_score=6.0),
        ]

        passed, rejected = scorer.apply_quality_gate(papers, threshold=5.0)

        assert len(passed) == 2
        assert len(rejected) == 1
```

## Integration Testing

### Full Workflow Test

**File**: `tests/test_systematic_review_integration.py`

```python
class TestFullWorkflow:
    """Integration tests for complete workflow."""

    @pytest.fixture
    def agent(self):
        """Create agent with test configuration."""
        return SystematicReviewAgent(
            model="gpt-oss:20b",
            show_model_info=False,
        )

    @pytest.fixture
    def sample_criteria(self):
        """Create sample search criteria."""
        return SearchCriteria(
            research_question="What is the effect of exercise on blood pressure?",
            purpose="Clinical guideline development",
            inclusion_criteria=[
                "Randomized controlled trial or systematic review",
                "Adult humans (≥18 years)",
                "Exercise intervention",
                "Blood pressure as primary or secondary outcome",
            ],
            exclusion_criteria=[
                "Animal studies",
                "Pediatric population",
                "Conference abstracts only",
            ],
            date_range=(2015, 2024),
        )

    @pytest.mark.integration
    def test_full_workflow_runs(self, agent, sample_criteria):
        """Test that the complete workflow executes without errors."""
        weights = ScoringWeights()

        result = agent.run_review(
            criteria=sample_criteria,
            weights=weights,
            interactive=False,  # Non-interactive for testing
        )

        # Basic sanity checks
        assert result is not None
        assert isinstance(result, SystematicReviewResult)
        assert result.statistics.total_considered >= 0
        assert len(result.process_log) > 0

    @pytest.mark.integration
    def test_excluded_papers_have_reasons(self, agent, sample_criteria):
        """Test that all excluded papers have exclusion reasons."""
        result = agent.run_review(
            criteria=sample_criteria,
            weights=ScoringWeights(),
            interactive=False,
        )

        for paper in result.excluded_papers:
            assert "exclusion_reasons" in paper
            assert len(paper["exclusion_reasons"]) > 0
            assert "exclusion_rationale" in paper

    @pytest.mark.integration
    def test_included_papers_have_scores(self, agent, sample_criteria):
        """Test that all included papers have complete scores."""
        result = agent.run_review(
            criteria=sample_criteria,
            weights=ScoringWeights(),
            interactive=False,
        )

        for paper in result.included_papers:
            assert "scores" in paper
            assert "relevance" in paper["scores"]
            assert "composite_score" in paper["scores"]
            assert "study_assessment" in paper

    @pytest.mark.integration
    def test_statistics_are_consistent(self, agent, sample_criteria):
        """Test that statistics are internally consistent."""
        result = agent.run_review(
            criteria=sample_criteria,
            weights=ScoringWeights(),
            interactive=False,
        )

        stats = result.statistics
        total_final = stats.final_included + stats.final_excluded + stats.uncertain_for_review
        assert total_final == stats.total_considered

    @pytest.mark.integration
    def test_process_log_is_complete(self, agent, sample_criteria):
        """Test that process log captures all phases."""
        result = agent.run_review(
            criteria=sample_criteria,
            weights=ScoringWeights(),
            interactive=False,
        )

        actions = [step["action"] for step in result.process_log]

        # Should have key phases
        assert any("search" in a.lower() for a in actions)
        assert any("filter" in a.lower() or "score" in a.lower() for a in actions)
```

## Benchmark Testing

### Gold Standard Comparison

**File**: `tests/benchmarks/test_gold_standard_benchmark.py`

```python
"""
Benchmark tests comparing against known systematic reviews.

These tests require access to the literature database and may take
significant time to run. Mark with @pytest.mark.benchmark.
"""

import pytest
from pathlib import Path


# Gold standard data - papers known to be included in published reviews
GOLD_STANDARDS = {
    "exercise_blood_pressure": {
        "research_question": "Effect of aerobic exercise on blood pressure in adults",
        "included_pmids": [
            "12345678", "23456789", "34567890",  # Example PMIDs
            # ... more PMIDs from published systematic review
        ],
        "source": "Cornelissen VA, Smart NA. Exercise training for blood pressure. JACC 2013",
    },
    "statin_cardiovascular": {
        "research_question": "Effect of statins on cardiovascular events",
        "included_pmids": [
            # PMIDs from Cochrane review
        ],
        "source": "Cochrane Database of Systematic Reviews",
    },
}


class TestGoldStandardBenchmarks:
    """Benchmark tests against published systematic reviews."""

    @pytest.mark.benchmark
    @pytest.mark.parametrize("benchmark_name", GOLD_STANDARDS.keys())
    def test_recall(self, benchmark_name, agent):
        """
        Measure recall: what percentage of gold standard papers did we find?

        Target: ≥ 80%
        """
        gold_standard = GOLD_STANDARDS[benchmark_name]

        criteria = SearchCriteria(
            research_question=gold_standard["research_question"],
            purpose="Benchmark comparison",
            inclusion_criteria=["RCT", "Adults"],
            exclusion_criteria=[],
        )

        result = agent.run_review(
            criteria=criteria,
            weights=ScoringWeights(),
            interactive=False,
        )

        # Get PMIDs of included papers
        included_pmids = {
            p.get("pmid") for p in result.included_papers if p.get("pmid")
        }

        # Calculate recall
        gold_pmids = set(gold_standard["included_pmids"])
        found = included_pmids & gold_pmids
        recall = len(found) / len(gold_pmids) if gold_pmids else 0

        print(f"\nBenchmark: {benchmark_name}")
        print(f"Gold standard papers: {len(gold_pmids)}")
        print(f"Found by agent: {len(found)}")
        print(f"Recall: {recall:.1%}")

        # Log missed papers for analysis
        missed = gold_pmids - included_pmids
        if missed:
            print(f"Missed PMIDs: {missed}")

        assert recall >= 0.80, f"Recall {recall:.1%} below 80% threshold"

    @pytest.mark.benchmark
    @pytest.mark.parametrize("benchmark_name", GOLD_STANDARDS.keys())
    def test_precision(self, benchmark_name, agent):
        """
        Measure precision: what percentage of our included papers are correct?

        Target: ≥ 60%
        """
        gold_standard = GOLD_STANDARDS[benchmark_name]

        criteria = SearchCriteria(
            research_question=gold_standard["research_question"],
            purpose="Benchmark comparison",
            inclusion_criteria=["RCT", "Adults"],
            exclusion_criteria=[],
        )

        result = agent.run_review(
            criteria=criteria,
            weights=ScoringWeights(),
            interactive=False,
        )

        included_pmids = {
            p.get("pmid") for p in result.included_papers if p.get("pmid")
        }
        gold_pmids = set(gold_standard["included_pmids"])

        correct = included_pmids & gold_pmids
        precision = len(correct) / len(included_pmids) if included_pmids else 0

        print(f"\nBenchmark: {benchmark_name}")
        print(f"Papers included by agent: {len(included_pmids)}")
        print(f"Correctly included: {len(correct)}")
        print(f"Precision: {precision:.1%}")

        assert precision >= 0.60, f"Precision {precision:.1%} below 60% threshold"
```

### Reproducibility Testing

**File**: `tests/benchmarks/test_reproducibility.py`

```python
class TestReproducibility:
    """Test that results are reproducible."""

    @pytest.mark.benchmark
    def test_same_inputs_same_outputs(self, agent):
        """Test that identical inputs produce identical outputs."""
        criteria = SearchCriteria(
            research_question="Test reproducibility query",
            purpose="Reproducibility test",
            inclusion_criteria=["RCT"],
            exclusion_criteria=[],
        )
        weights = ScoringWeights()

        # Run twice
        result1 = agent.run_review(criteria, weights, interactive=False)
        result2 = agent.run_review(criteria, weights, interactive=False)

        # Compare included paper IDs
        ids1 = {p["document_id"] for p in result1.included_papers}
        ids2 = {p["document_id"] for p in result2.included_papers}

        assert ids1 == ids2, "Included papers differ between runs"

        # Compare rankings
        ranks1 = [p["document_id"] for p in result1.included_papers]
        ranks2 = [p["document_id"] for p in result2.included_papers]

        assert ranks1 == ranks2, "Rankings differ between runs"

    @pytest.mark.benchmark
    def test_deterministic_with_seed(self, agent):
        """Test that LLM randomness can be controlled."""
        # This tests that temperature=0 produces consistent results
        # Implementation depends on LLM configuration
        pass
```

## Performance Testing

**File**: `tests/benchmarks/test_performance.py`

```python
import time
import pytest


class TestPerformance:
    """Performance benchmarks."""

    @pytest.mark.benchmark
    def test_small_review_timing(self, agent):
        """Test timing for a small review (targeting 10-20 papers)."""
        criteria = SearchCriteria(
            research_question="Rare disease treatment",
            purpose="Performance test",
            inclusion_criteria=["Any study"],
            exclusion_criteria=[],
            max_results=20,
        )

        start = time.time()
        result = agent.run_review(criteria, ScoringWeights(), interactive=False)
        elapsed = time.time() - start

        print(f"\nSmall review timing:")
        print(f"Papers processed: {result.statistics.total_considered}")
        print(f"Time elapsed: {elapsed:.1f}s")
        print(f"Time per paper: {elapsed / max(1, result.statistics.total_considered):.1f}s")

        # Target: < 5 minutes for small review
        assert elapsed < 300, f"Review took too long: {elapsed:.1f}s"

    @pytest.mark.benchmark
    def test_medium_review_timing(self, agent):
        """Test timing for a medium review (targeting 100 papers)."""
        criteria = SearchCriteria(
            research_question="Common intervention effectiveness",
            purpose="Performance test",
            inclusion_criteria=["RCT"],
            exclusion_criteria=[],
            max_results=100,
        )

        start = time.time()
        result = agent.run_review(criteria, ScoringWeights(), interactive=False)
        elapsed = time.time() - start

        print(f"\nMedium review timing:")
        print(f"Papers processed: {result.statistics.total_considered}")
        print(f"Time elapsed: {elapsed:.1f}s")

        # Target: < 30 minutes for medium review
        assert elapsed < 1800, f"Review took too long: {elapsed:.1f}s"

    @pytest.mark.benchmark
    def test_memory_usage(self, agent):
        """Test memory usage during large review."""
        import tracemalloc

        tracemalloc.start()

        criteria = SearchCriteria(
            research_question="Large topic review",
            purpose="Memory test",
            inclusion_criteria=["Any"],
            exclusion_criteria=[],
            max_results=200,
        )

        result = agent.run_review(criteria, ScoringWeights(), interactive=False)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        print(f"\nMemory usage:")
        print(f"Current: {current / 1024 / 1024:.1f} MB")
        print(f"Peak: {peak / 1024 / 1024:.1f} MB")

        # Target: < 1 GB peak memory
        assert peak < 1024 * 1024 * 1024, f"Peak memory too high: {peak / 1024 / 1024:.1f} MB"
```

## Edge Case Testing

**File**: `tests/test_systematic_review_edge_cases.py`

```python
class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_search_results(self, agent):
        """Test handling when no papers are found."""
        criteria = SearchCriteria(
            research_question="xyzzy nonexistent topic 12345",
            purpose="Edge case test",
            inclusion_criteria=["Any"],
            exclusion_criteria=[],
        )

        result = agent.run_review(criteria, ScoringWeights(), interactive=False)

        assert result.statistics.total_considered == 0
        assert len(result.included_papers) == 0
        assert "no papers found" in result.process_log[-1]["output_summary"].lower()

    def test_all_papers_excluded(self, agent):
        """Test when all papers are excluded."""
        criteria = SearchCriteria(
            research_question="Common topic",
            purpose="Edge case test",
            inclusion_criteria=["Impossible criterion that matches nothing"],
            exclusion_criteria=["Any study type"],  # Excludes everything
        )

        result = agent.run_review(criteria, ScoringWeights(), interactive=False)

        assert len(result.included_papers) == 0
        assert len(result.excluded_papers) > 0
        assert all(p.get("exclusion_reasons") for p in result.excluded_papers)

    def test_very_broad_query(self, agent):
        """Test handling of overly broad queries."""
        criteria = SearchCriteria(
            research_question="medicine",  # Too broad
            purpose="Edge case test",
            inclusion_criteria=["Any"],
            exclusion_criteria=[],
            max_results=50,  # Limit for testing
        )

        result = agent.run_review(criteria, ScoringWeights(), interactive=False)

        # Should complete without error
        assert result is not None
        # Should respect max_results
        assert result.statistics.final_included <= 50

    def test_special_characters_in_query(self, agent):
        """Test handling of special characters in research question."""
        criteria = SearchCriteria(
            research_question="What is the effect of β-blockers on α-adrenergic receptors?",
            purpose="Edge case test",
            inclusion_criteria=["Any"],
            exclusion_criteria=[],
        )

        result = agent.run_review(criteria, ScoringWeights(), interactive=False)

        assert result is not None

    def test_ollama_connection_failure(self, agent, mocker):
        """Test graceful handling of LLM connection failure."""
        mocker.patch.object(
            agent, "_make_ollama_request",
            side_effect=ConnectionError("Cannot connect to Ollama"),
        )

        criteria = SearchCriteria(
            research_question="Test",
            purpose="Connection test",
            inclusion_criteria=["Any"],
            exclusion_criteria=[],
        )

        with pytest.raises(ConnectionError):
            agent.run_review(criteria, ScoringWeights(), interactive=False)

        # Alternatively, test graceful degradation
        # result = agent.run_review(criteria, ScoringWeights(), interactive=False)
        # assert "error" in result.process_log[-1]
```

## Validation Checklist

### Pre-Release Validation

- [ ] All unit tests pass
- [ ] All component tests pass
- [ ] All integration tests pass
- [ ] Benchmark recall ≥ 80%
- [ ] Benchmark precision ≥ 60%
- [ ] Performance tests within targets
- [ ] Memory usage under 1 GB
- [ ] Edge cases handled gracefully
- [ ] Documentation complete
- [ ] Code review completed

### Ongoing Validation

- [ ] Run benchmarks monthly
- [ ] Track recall/precision over time
- [ ] Monitor LLM model updates
- [ ] Update gold standards with new reviews
- [ ] Collect user feedback
- [ ] Track false positives/negatives
