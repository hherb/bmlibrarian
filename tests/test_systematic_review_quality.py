"""
Unit tests for SystematicReviewAgent Phase 4: Quality Assessment.

Tests cover:
- QualityAssessor: Orchestration of quality assessment tools
  - Study assessment integration
  - Paper weight assessment integration
  - PICO extraction conditional logic
  - PRISMA assessment conditional logic
  - Batch processing with error handling
  - Assessment statistics generation

- CompositeScorer: Already tested in test_systematic_review_filtering.py
  - Composite score calculation
  - Quality gate filtering
  - Paper ranking

This test suite uses mocking to avoid LLM calls and database access.
"""

import json
import pytest
from datetime import datetime
from typing import Dict, List, Any
from unittest.mock import MagicMock, patch, Mock

from bmlibrarian.agents.systematic_review import (
    # Enums
    StudyTypeFilter,
    InclusionStatus,
    ExclusionStage,
    # Input models
    SearchCriteria,
    ScoringWeights,
    # Paper data models
    PaperData,
    ScoredPaper,
    AssessedPaper,
    InclusionDecision,
    # Phase 4: Quality assessment
    QualityAssessor,
    QualityAssessmentResult,
    # Configuration
    SystematicReviewConfig,
    get_systematic_review_config,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_paper() -> PaperData:
    """Create sample PaperData for testing."""
    return PaperData(
        document_id=12345,
        title="Efficacy of Statins in Primary Prevention of CVD: A Randomized Controlled Trial",
        authors=["Smith J", "Johnson A", "Williams B"],
        year=2023,
        journal="Lancet",
        abstract=(
            "Background: Statins are widely used for cardiovascular disease prevention. "
            "This randomized controlled trial evaluated the efficacy of statins in primary "
            "prevention of cardiovascular events in adults with elevated cholesterol. "
            "Methods: We enrolled 10,000 participants aged 40-75 years with LDL >130 mg/dL. "
            "Intervention: Participants were randomized to atorvastatin 20mg or placebo. "
            "Results: Statin therapy reduced cardiovascular events by 25% (HR 0.75, p<0.001). "
            "Conclusion: Statin therapy is effective for primary prevention."
        ),
        doi="10.1000/example.doi",
        pmid="12345678",
        source="pubmed",
    )


@pytest.fixture
def systematic_review_paper() -> PaperData:
    """Create sample systematic review paper."""
    return PaperData(
        document_id=54321,
        title="Systematic Review and Meta-Analysis of Statin Efficacy",
        authors=["Meta Author", "Review Author"],
        year=2024,
        journal="Cochrane Database Syst Rev",
        abstract=(
            "Background: We conducted a systematic review of RCTs evaluating statin efficacy. "
            "Methods: We searched MEDLINE, Embase, and Cochrane Central. "
            "Selection: Two reviewers independently screened 1,543 records. "
            "Data: We extracted data on cardiovascular outcomes. "
            "Results: Pooled analysis of 25 RCTs (n=150,000) showed 28% risk reduction. "
            "Conclusion: High-quality evidence supports statin use."
        ),
        doi="10.1002/example.doi",
        pmid="54321987",
        source="pubmed",
    )


@pytest.fixture
def case_report_paper() -> PaperData:
    """Create sample case report paper."""
    return PaperData(
        document_id=11111,
        title="Case Report: Unusual Statin Side Effect",
        authors=["Case Author"],
        year=2022,
        journal="Case Reports Journal",
        abstract=(
            "We report an unusual case of a patient experiencing "
            "reversible memory loss after starting statin therapy."
        ),
        doi="10.1000/case.doi",
        pmid="11111111",
        source="pubmed",
    )


@pytest.fixture
def scored_rct_paper(sample_paper) -> ScoredPaper:
    """Create scored RCT paper."""
    return ScoredPaper(
        paper=sample_paper,
        relevance_score=4.5,
        relevance_rationale="Highly relevant RCT on statin efficacy",
        inclusion_decision=InclusionDecision.create_included(
            stage=ExclusionStage.RELEVANCE_SCORING,
            rationale="Meets all inclusion criteria",
            criteria_matched=["Human study", "Statin intervention", "CVD outcomes"],
            confidence=0.95,
        ),
    )


@pytest.fixture
def scored_systematic_review(systematic_review_paper) -> ScoredPaper:
    """Create scored systematic review paper."""
    return ScoredPaper(
        paper=systematic_review_paper,
        relevance_score=5.0,
        relevance_rationale="Comprehensive systematic review",
        inclusion_decision=InclusionDecision.create_included(
            stage=ExclusionStage.RELEVANCE_SCORING,
            rationale="High-quality systematic review",
            criteria_matched=["Systematic review", "Meta-analysis", "CVD outcomes"],
            confidence=0.98,
        ),
    )


@pytest.fixture
def scored_case_report(case_report_paper) -> ScoredPaper:
    """Create scored case report paper."""
    return ScoredPaper(
        paper=case_report_paper,
        relevance_score=2.0,
        relevance_rationale="Case report, low evidence level",
        inclusion_decision=InclusionDecision.create_excluded(
            stage=ExclusionStage.INITIAL_FILTER,
            reasons=["Case report excluded"],
            rationale="Case reports not eligible for systematic review",
            confidence=1.0,
        ),
    )


@pytest.fixture
def mock_study_assessment() -> Dict[str, Any]:
    """Create mock StudyAssessment output."""
    return {
        "study_type": "randomized controlled trial",
        "study_design": "prospective, double-blinded, multi-center",
        "quality_score": 8.5,
        "strengths": [
            "Large sample size (N=10,000)",
            "Double-blinded design",
            "Multi-center recruitment",
            "Long follow-up period",
        ],
        "limitations": [
            "Single geographic region",
            "Exclusion of high-risk patients",
        ],
        "overall_confidence": 0.85,
        "confidence_explanation": "High-quality RCT with robust methodology",
        "evidence_level": "Level 1 (high)",
        "document_id": "12345",
        "document_title": "Efficacy of Statins...",
        "is_randomized": True,
        "is_controlled": True,
        "is_double_blinded": True,
        "sample_size": "10,000",
    }


@pytest.fixture
def mock_paper_weight() -> Dict[str, Any]:
    """Create mock PaperWeightResult output."""
    return {
        "document_id": 12345,
        "composite_score": 7.8,
        "dimensions": [
            {
                "dimension": "study_design",
                "score": 9.0,
                "weight": 0.25,
                "explanation": "RCT with excellent design",
            },
            {
                "dimension": "sample_size",
                "score": 8.0,
                "weight": 0.15,
                "explanation": "Large sample (N=10,000)",
            },
            {
                "dimension": "methodological_quality",
                "score": 8.5,
                "weight": 0.30,
                "explanation": "Rigorous methodology",
            },
        ],
    }


@pytest.fixture
def mock_pico_extraction() -> Dict[str, Any]:
    """Create mock PICOExtraction output."""
    return {
        "population": "Adults aged 40-75 with elevated LDL cholesterol (>130 mg/dL)",
        "intervention": "Atorvastatin 20mg daily",
        "comparison": "Placebo",
        "outcome": "Cardiovascular events (MI, stroke, cardiac death)",
        "document_id": "12345",
        "document_title": "Efficacy of Statins...",
        "extraction_confidence": 0.90,
        "study_type": "randomized controlled trial",
        "sample_size": "N=10,000",
        "population_confidence": 0.95,
        "intervention_confidence": 0.92,
        "comparison_confidence": 0.88,
        "outcome_confidence": 0.93,
    }


@pytest.fixture
def mock_prisma_assessment() -> Dict[str, Any]:
    """Create mock PRISMA2020Assessment output."""
    return {
        "document_id": 54321,
        "is_suitable": True,
        "suitability_reason": "Identified as systematic review and meta-analysis",
        "overall_compliance_score": 22.5,
        "max_possible_score": 27.0,
        "compliance_percentage": 83.3,
        "items_assessed": 27,
        "items_compliant": 22,
        "items_partial": 3,
        "items_non_compliant": 2,
    }


# =============================================================================
# QualityAssessor Tests
# =============================================================================

class TestQualityAssessor:
    """Tests for QualityAssessor orchestration."""

    def test_initialization(self):
        """Test QualityAssessor initialization."""
        assessor = QualityAssessor()

        assert assessor is not None
        assert assessor._config is not None
        assert assessor._study_agent is None  # Lazy loading
        assert assessor._weight_agent is None  # Lazy loading
        assert assessor._pico_agent is None  # Lazy loading
        assert assessor._prisma_agent is None  # Lazy loading

    def test_should_run_pico_for_rct(self):
        """Test that PICO runs for RCTs."""
        assessor = QualityAssessor()

        assert assessor._should_run_pico("randomized controlled trial") is True
        assert assessor._should_run_pico("rct") is True
        assert assessor._should_run_pico("clinical trial") is True
        assert assessor._should_run_pico("cohort study") is True
        assert assessor._should_run_pico("case-control study") is True

    def test_should_not_run_pico_for_review(self):
        """Test that PICO doesn't run for reviews."""
        assessor = QualityAssessor()

        assert assessor._should_run_pico("systematic review") is False
        assert assessor._should_run_pico("meta-analysis") is False
        assert assessor._should_run_pico("narrative review") is False
        assert assessor._should_run_pico("case report") is False

    def test_should_run_prisma_for_systematic_review(self):
        """Test that PRISMA runs for systematic reviews."""
        assessor = QualityAssessor()

        assert assessor._should_run_prisma("systematic review") is True
        assert assessor._should_run_prisma("meta-analysis") is True
        assert assessor._should_run_prisma("systematic review and meta-analysis") is True

    def test_should_not_run_prisma_for_rct(self):
        """Test that PRISMA doesn't run for RCTs."""
        assessor = QualityAssessor()

        assert assessor._should_run_prisma("randomized controlled trial") is False
        assert assessor._should_run_prisma("rct") is False
        assert assessor._should_run_prisma("cohort study") is False
        assert assessor._should_run_prisma("case report") is False

    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._get_study_agent')
    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._get_weight_agent')
    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._get_pico_agent')
    def test_assess_single_rct(
        self,
        mock_get_pico,
        mock_get_weight,
        mock_get_study,
        scored_rct_paper,
        mock_study_assessment,
        mock_paper_weight,
        mock_pico_extraction,
    ):
        """Test assessing a single RCT paper."""
        # Mock agents
        mock_study_agent = Mock()
        mock_study_result = Mock()
        mock_study_result.to_dict.return_value = mock_study_assessment
        mock_study_agent.assess_study.return_value = mock_study_result
        mock_get_study.return_value = mock_study_agent

        mock_weight_agent = Mock()
        mock_weight_result = Mock()
        mock_weight_result.to_dict.return_value = mock_paper_weight
        mock_weight_agent.assess_paper.return_value = mock_weight_result
        mock_get_weight.return_value = mock_weight_agent

        mock_pico_agent = Mock()
        mock_pico_result = Mock()
        mock_pico_result.to_dict.return_value = mock_pico_extraction
        mock_pico_agent.extract_pico.return_value = mock_pico_result
        mock_get_pico.return_value = mock_pico_agent

        # Run assessment
        assessor = QualityAssessor()
        assessed = assessor._assess_single(scored_rct_paper)

        # Verify result
        assert isinstance(assessed, AssessedPaper)
        assert assessed.scored_paper == scored_rct_paper
        assert assessed.study_assessment == mock_study_assessment
        assert assessed.paper_weight == mock_paper_weight
        assert assessed.pico_components == mock_pico_extraction  # PICO ran for RCT
        assert assessed.prisma_assessment is None  # PRISMA didn't run for RCT

    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._get_study_agent')
    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._get_weight_agent')
    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._get_prisma_agent')
    def test_assess_single_systematic_review(
        self,
        mock_get_prisma,
        mock_get_weight,
        mock_get_study,
        scored_systematic_review,
        mock_study_assessment,
        mock_paper_weight,
        mock_prisma_assessment,
    ):
        """Test assessing a systematic review paper."""
        # Modify mock study assessment for systematic review
        sr_assessment = mock_study_assessment.copy()
        sr_assessment["study_type"] = "systematic review"
        sr_assessment["study_design"] = "comprehensive literature synthesis"

        # Mock agents
        mock_study_agent = Mock()
        mock_study_result = Mock()
        mock_study_result.to_dict.return_value = sr_assessment
        mock_study_agent.assess_study.return_value = mock_study_result
        mock_get_study.return_value = mock_study_agent

        mock_weight_agent = Mock()
        mock_weight_result = Mock()
        mock_weight_result.to_dict.return_value = mock_paper_weight
        mock_weight_agent.assess_paper.return_value = mock_weight_result
        mock_get_weight.return_value = mock_weight_agent

        mock_prisma_agent = Mock()
        mock_prisma_result = Mock()
        mock_prisma_result.to_dict.return_value = mock_prisma_assessment
        mock_prisma_agent.assess_document.return_value = mock_prisma_result
        mock_get_prisma.return_value = mock_prisma_agent

        # Run assessment
        assessor = QualityAssessor()
        assessed = assessor._assess_single(scored_systematic_review)

        # Verify result
        assert isinstance(assessed, AssessedPaper)
        assert assessed.scored_paper == scored_systematic_review
        assert assessed.study_assessment == sr_assessment
        assert assessed.paper_weight == mock_paper_weight
        assert assessed.pico_components is None  # PICO didn't run for systematic review
        assert assessed.prisma_assessment == mock_prisma_assessment  # PRISMA ran

    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._assess_single')
    def test_assess_batch(
        self,
        mock_assess_single,
        scored_rct_paper,
        scored_systematic_review,
        mock_study_assessment,
        mock_paper_weight,
    ):
        """Test batch assessment of multiple papers."""
        # Create mock assessed papers
        assessed_rct = AssessedPaper(
            scored_paper=scored_rct_paper,
            study_assessment=mock_study_assessment,
            paper_weight=mock_paper_weight,
            pico_components={"population": "test"},
            prisma_assessment=None,
        )

        sr_assessment = mock_study_assessment.copy()
        sr_assessment["study_type"] = "systematic review"
        assessed_sr = AssessedPaper(
            scored_paper=scored_systematic_review,
            study_assessment=sr_assessment,
            paper_weight=mock_paper_weight,
            pico_components=None,
            prisma_assessment={"overall_compliance_score": 22.5},
        )

        # Mock _assess_single to return different results
        mock_assess_single.side_effect = [assessed_rct, assessed_sr]

        # Run batch assessment
        assessor = QualityAssessor()
        papers = [scored_rct_paper, scored_systematic_review]
        result = assessor.assess_batch(papers)

        # Verify result
        assert isinstance(result, QualityAssessmentResult)
        assert len(result.assessed_papers) == 2
        assert len(result.failed_papers) == 0
        assert result.total_processed == 2
        assert result.success_rate == 1.0

        # Check statistics
        stats = result.assessment_statistics
        assert stats["study_assessments"] == 2
        assert stats["weight_assessments"] == 2
        assert stats["pico_assessments"] == 1  # Only RCT
        assert stats["prisma_assessments"] == 1  # Only systematic review

    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._assess_single')
    def test_assess_batch_with_failures(
        self,
        mock_assess_single,
        scored_rct_paper,
        scored_case_report,
    ):
        """Test batch assessment with some failures."""
        # First paper succeeds
        assessed = AssessedPaper(
            scored_paper=scored_rct_paper,
            study_assessment={"study_type": "rct"},
            paper_weight={"composite_score": 7.0},
        )

        # Second paper fails
        mock_assess_single.side_effect = [
            assessed,
            Exception("Assessment failed"),
        ]

        # Run batch assessment
        assessor = QualityAssessor()
        papers = [scored_rct_paper, scored_case_report]
        result = assessor.assess_batch(papers)

        # Verify result
        assert len(result.assessed_papers) == 1
        assert len(result.failed_papers) == 1
        assert result.total_processed == 2
        assert result.success_rate == 0.5

    def test_get_assessment_statistics(
        self,
        scored_rct_paper,
        mock_study_assessment,
        mock_paper_weight,
    ):
        """Test assessment statistics generation."""
        # Create assessed papers
        assessed1 = AssessedPaper(
            scored_paper=scored_rct_paper,
            study_assessment=mock_study_assessment,
            paper_weight=mock_paper_weight,
            pico_components={"population": "test"},
        )

        assessed2 = AssessedPaper(
            scored_paper=scored_rct_paper,
            study_assessment=mock_study_assessment,
            paper_weight=mock_paper_weight,
        )

        result = QualityAssessmentResult(
            assessed_papers=[assessed1, assessed2],
            failed_papers=[],
            total_processed=2,
            execution_time_seconds=10.5,
            assessment_statistics={
                "study_assessments": 2,
                "weight_assessments": 2,
                "pico_assessments": 1,
                "prisma_assessments": 0,
            },
        )

        assessor = QualityAssessor()
        stats = assessor.get_assessment_statistics(result)

        # Verify statistics
        assert stats["total_papers"] == 2
        assert stats["successfully_assessed"] == 2
        assert stats["failed"] == 0
        assert stats["success_rate_percent"] == 100.0
        assert stats["average_quality_score"] == 8.5
        assert stats["execution_time_seconds"] == 10.5
        assert "study_type_distribution" in stats
        assert "papers_per_second" in stats

    def test_paper_to_document_conversion(self, sample_paper):
        """Test PaperData to document dict conversion."""
        assessor = QualityAssessor()
        document = assessor._paper_to_document(sample_paper)

        assert document["id"] == sample_paper.document_id
        assert document["title"] == sample_paper.title
        assert document["abstract"] == sample_paper.abstract
        assert document["authors"] == sample_paper.authors
        assert document["doi"] == sample_paper.doi
        assert document["pmid"] == sample_paper.pmid

    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._get_study_agent')
    def test_run_study_assessment_error_handling(
        self,
        mock_get_study,
        sample_paper,
    ):
        """Test study assessment error handling."""
        # Mock agent to raise error
        mock_study_agent = Mock()
        mock_study_agent.assess_study.side_effect = Exception("LLM error")
        mock_get_study.return_value = mock_study_agent

        assessor = QualityAssessor()
        document = assessor._paper_to_document(sample_paper)
        result = assessor._run_study_assessment(document)

        # Should return minimal assessment with error
        assert result["study_type"] == "unknown"
        assert result["quality_score"] == 5.0
        assert result["overall_confidence"] == 0.0
        assert any("failed" in lim.lower() for lim in result["limitations"])

    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._get_pico_agent')
    def test_run_pico_extraction_error_handling(
        self,
        mock_get_pico,
        sample_paper,
    ):
        """Test PICO extraction error handling."""
        # Mock agent to raise error
        mock_pico_agent = Mock()
        mock_pico_agent.extract_pico.side_effect = Exception("Extraction error")
        mock_get_pico.return_value = mock_pico_agent

        assessor = QualityAssessor()
        document = assessor._paper_to_document(sample_paper)
        result = assessor._run_pico_extraction(document)

        # Should return None on error
        assert result is None


# =============================================================================
# Integration with CompositeScorer Tests
# =============================================================================

class TestQualityAssessmentIntegration:
    """Test integration between QualityAssessor and CompositeScorer."""

    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._assess_single')
    def test_assessed_papers_ready_for_composite_scoring(
        self,
        mock_assess_single,
        scored_rct_paper,
        mock_study_assessment,
        mock_paper_weight,
    ):
        """Test that assessed papers are ready for composite scoring."""
        from bmlibrarian.agents.systematic_review import CompositeScorer

        # Create assessed paper
        assessed = AssessedPaper(
            scored_paper=scored_rct_paper,
            study_assessment=mock_study_assessment,
            paper_weight=mock_paper_weight,
        )

        mock_assess_single.return_value = assessed

        # Run assessment
        assessor = QualityAssessor()
        result = assessor.assess_batch([scored_rct_paper])

        # Use CompositeScorer on results
        scorer = CompositeScorer()
        ranked = scorer.score_and_rank(result.assessed_papers)

        # Verify composite scoring worked
        assert len(ranked) == 1
        assert ranked[0].composite_score is not None
        assert ranked[0].final_rank == 1


# =============================================================================
# End-to-End Tests
# =============================================================================

class TestQualityAssessmentEndToEnd:
    """End-to-end tests for complete quality assessment workflow."""

    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._get_study_agent')
    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._get_weight_agent')
    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._get_pico_agent')
    @patch('bmlibrarian.agents.systematic_review.quality.QualityAssessor._get_prisma_agent')
    def test_full_quality_assessment_workflow(
        self,
        mock_get_prisma,
        mock_get_pico,
        mock_get_weight,
        mock_get_study,
        scored_rct_paper,
        scored_systematic_review,
        mock_study_assessment,
        mock_paper_weight,
        mock_pico_extraction,
        mock_prisma_assessment,
    ):
        """Test complete quality assessment workflow."""
        from bmlibrarian.agents.systematic_review import CompositeScorer, ScoringWeights

        # Set up mocks for RCT
        mock_study_agent = Mock()
        mock_study_result = Mock()
        mock_study_result.to_dict.return_value = mock_study_assessment
        mock_study_agent.assess_study.return_value = mock_study_result
        mock_get_study.return_value = mock_study_agent

        mock_weight_agent = Mock()
        mock_weight_result = Mock()
        mock_weight_result.to_dict.return_value = mock_paper_weight
        mock_weight_agent.assess_paper.return_value = mock_weight_result
        mock_get_weight.return_value = mock_weight_agent

        mock_pico_agent = Mock()
        mock_pico_result = Mock()
        mock_pico_result.to_dict.return_value = mock_pico_extraction
        mock_pico_agent.extract_pico.return_value = mock_pico_result
        mock_get_pico.return_value = mock_pico_agent

        # For systematic review, modify study assessment
        sr_assessment = mock_study_assessment.copy()
        sr_assessment["study_type"] = "systematic review"

        mock_prisma_agent = Mock()
        mock_prisma_result = Mock()
        mock_prisma_result.to_dict.return_value = mock_prisma_assessment
        mock_prisma_agent.assess_document.return_value = mock_prisma_result
        mock_get_prisma.return_value = mock_prisma_agent

        # Modify mock to return different study types
        def assess_side_effect(*args, **kwargs):
            doc_id = kwargs.get('document_id') or args[2] if len(args) > 2 else None
            if doc_id == 54321:
                sr_result = Mock()
                sr_result.to_dict.return_value = sr_assessment
                return sr_result
            else:
                return mock_study_result

        mock_study_agent.assess_study.side_effect = assess_side_effect

        # Run quality assessment
        assessor = QualityAssessor()
        papers = [scored_rct_paper, scored_systematic_review]
        qa_result = assessor.assess_batch(papers)

        # Verify assessment results
        assert len(qa_result.assessed_papers) == 2
        assert qa_result.assessment_statistics["pico_assessments"] == 1
        assert qa_result.assessment_statistics["prisma_assessments"] == 1

        # Run composite scoring
        weights = ScoringWeights()
        scorer = CompositeScorer(weights)
        ranked = scorer.score_and_rank(qa_result.assessed_papers)

        # Verify final ranked output
        assert len(ranked) == 2
        assert all(p.composite_score is not None for p in ranked)
        assert all(p.final_rank is not None for p in ranked)
        assert ranked[0].final_rank == 1
        assert ranked[1].final_rank == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
