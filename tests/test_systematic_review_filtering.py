"""
Unit tests for SystematicReviewAgent Phase 3: Filtering and Scoring.

Tests cover:
- InitialFilter: Fast heuristic-based filtering
  - Date range filtering
  - Exclusion keyword matching
  - Study type keyword detection
  - Minimum content requirements
  - Batch filtering with statistics

- InclusionEvaluator: LLM-based inclusion/exclusion (mocked)
  - Criteria evaluation parsing
  - Decision status mapping
  - Batch evaluation

- RelevanceScorer: Wrapper around DocumentScoringAgent
  - Paper scoring with batch support
  - Relevance threshold filtering
  - Score-based inclusion decisions

- CompositeScorer: Weighted composite scoring
  - Score normalization
  - Weighted calculation
  - Quality gate filtering
  - Paper ranking
"""

import json
import pytest
from datetime import datetime
from typing import Dict, List, Any
from unittest.mock import MagicMock, patch

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
    # Phase 3: Filtering
    InitialFilter,
    InclusionEvaluator,
    FilterResult,
    BatchFilterResult,
    STUDY_TYPE_KEYWORDS,
    DEFAULT_EXCLUSION_KEYWORDS,
    DEFINITIVE_TITLE_PATTERNS,
    NEGATIVE_CONTEXT_PATTERNS,
    # Phase 3: Scoring
    RelevanceScorer,
    CompositeScorer,
    ScoringResult,
    BatchScoringResult,
    # Configuration
    SystematicReviewConfig,
    get_default_config,
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
            "Cardiovascular disease outcomes",
        ],
        exclusion_criteria=[
            "Animal studies",
            "Pediatric-only populations",
            "Case reports",
        ],
        target_study_types=[
            StudyTypeFilter.RCT,
            StudyTypeFilter.META_ANALYSIS,
            StudyTypeFilter.SYSTEMATIC_REVIEW,
        ],
        date_range=(2010, 2024),
        language="English",
    )


@pytest.fixture
def sample_weights() -> ScoringWeights:
    """Create sample ScoringWeights for testing."""
    return ScoringWeights(
        relevance=0.30,
        study_quality=0.25,
        methodological_rigor=0.20,
        sample_size=0.10,
        recency=0.10,
        replication_status=0.05,
    )


@pytest.fixture
def sample_paper() -> PaperData:
    """Create sample PaperData for testing."""
    return PaperData(
        document_id=12345,
        title="Efficacy of Statins in Primary Prevention of Cardiovascular Disease: A Randomized Controlled Trial",
        authors=["Smith J", "Johnson A", "Williams B"],
        year=2023,
        journal="Lancet",
        abstract=(
            "Background: Statins are widely used for cardiovascular disease prevention. "
            "This randomized controlled trial evaluated the efficacy of statins in primary "
            "prevention of cardiovascular events in adults with elevated cholesterol. "
            "Methods: We enrolled 10,000 participants aged 40-75 years. "
            "Results: Statin therapy reduced cardiovascular events by 25%."
        ),
        doi="10.1000/example.doi",
        pmid="12345678",
        source="pubmed",
    )


@pytest.fixture
def old_paper() -> PaperData:
    """Create an old paper outside date range."""
    return PaperData(
        document_id=99999,
        title="Early Studies on Cholesterol",
        authors=["Old Author"],
        year=1995,
        journal="Old Journal",
        abstract="This early study examined cholesterol.",
    )


@pytest.fixture
def animal_study_paper() -> PaperData:
    """Create a paper about animal studies."""
    return PaperData(
        document_id=88888,
        title="Statin Effects in Mouse Model",
        authors=["Mouse Researcher"],
        year=2022,
        journal="Animal Research Journal",
        abstract=(
            "This animal study investigated statin effects in a mouse model. "
            "We used C57BL/6 mice to evaluate cardiovascular outcomes."
        ),
    )


@pytest.fixture
def case_report_paper() -> PaperData:
    """Create a case report paper."""
    return PaperData(
        document_id=77777,
        title="Case Report: Unusual Statin Reaction",
        authors=["Clinician A"],
        year=2023,
        journal="Case Reports in Medicine",
        abstract=(
            "We present a case report of an unusual adverse reaction to statin therapy "
            "in a single patient with rare comorbidities."
        ),
    )


@pytest.fixture
def minimal_abstract_paper() -> PaperData:
    """Create a paper with minimal abstract."""
    return PaperData(
        document_id=66666,
        title="Statin Study",
        authors=["Short Author"],
        year=2023,
        journal="Brief Journal",
        abstract="Brief.",
    )


@pytest.fixture
def sample_papers(
    sample_paper: PaperData,
    old_paper: PaperData,
    animal_study_paper: PaperData,
    case_report_paper: PaperData,
) -> List[PaperData]:
    """Create a list of sample papers for batch testing."""
    return [sample_paper, old_paper, animal_study_paper, case_report_paper]


@pytest.fixture
def sample_scored_paper(sample_paper: PaperData) -> ScoredPaper:
    """Create a sample ScoredPaper."""
    return ScoredPaper(
        paper=sample_paper,
        relevance_score=4.5,
        relevance_rationale="Directly addresses research question",
        inclusion_decision=InclusionDecision.create_included(
            stage=ExclusionStage.RELEVANCE_SCORING,
            rationale="High relevance",
            criteria_matched=["Human studies", "Statin intervention"],
        ),
    )


@pytest.fixture
def sample_assessed_paper(sample_scored_paper: ScoredPaper) -> AssessedPaper:
    """Create a sample AssessedPaper with all assessments."""
    return AssessedPaper(
        scored_paper=sample_scored_paper,
        study_assessment={
            "overall_quality": 8.0,
            "methodological_rigor": 7.5,
            "sample_size": 10000,
            "bias_risk": "low",
        },
        paper_weight={
            "replication_status": "replicated",
            "evidence_weight": 9.0,
        },
    )


# =============================================================================
# InitialFilter Tests
# =============================================================================

class TestInitialFilter:
    """Tests for InitialFilter class."""

    def test_initialization(self, sample_criteria: SearchCriteria) -> None:
        """Test InitialFilter initialization."""
        filter_obj = InitialFilter(sample_criteria)

        # Should have default exclusion keywords plus criteria-derived ones
        assert len(filter_obj._exclusion_keywords) > len(DEFAULT_EXCLUSION_KEYWORDS)

    def test_filter_passes_good_paper(
        self, sample_criteria: SearchCriteria, sample_paper: PaperData
    ) -> None:
        """Test that a good paper passes the filter."""
        filter_obj = InitialFilter(sample_criteria)
        result = filter_obj.filter_paper(sample_paper)

        assert result.passed is True
        assert result.stage == ExclusionStage.INITIAL_FILTER

    def test_filter_rejects_old_paper(
        self, sample_criteria: SearchCriteria, old_paper: PaperData
    ) -> None:
        """Test that a paper outside date range is rejected."""
        filter_obj = InitialFilter(sample_criteria)
        result = filter_obj.filter_paper(old_paper)

        assert result.passed is False
        assert "year" in result.reason.lower() or "date" in result.reason.lower()
        assert "1995" in result.reason

    def test_filter_rejects_animal_study(
        self, sample_criteria: SearchCriteria, animal_study_paper: PaperData
    ) -> None:
        """Test that animal studies are rejected by exclusion keywords."""
        filter_obj = InitialFilter(sample_criteria)
        result = filter_obj.filter_paper(animal_study_paper)

        assert result.passed is False
        assert "exclusion keyword" in result.reason.lower()

    def test_filter_rejects_case_report(
        self, sample_criteria: SearchCriteria, case_report_paper: PaperData
    ) -> None:
        """Test that case reports are rejected by exclusion keywords."""
        filter_obj = InitialFilter(sample_criteria)
        result = filter_obj.filter_paper(case_report_paper)

        assert result.passed is False
        assert "case report" in result.reason.lower()

    def test_filter_rejects_short_abstract(
        self, sample_criteria: SearchCriteria, minimal_abstract_paper: PaperData
    ) -> None:
        """Test that papers with too short abstracts are rejected."""
        filter_obj = InitialFilter(sample_criteria)
        result = filter_obj.filter_paper(minimal_abstract_paper)

        assert result.passed is False
        assert "short" in result.reason.lower() or "abstract" in result.reason.lower()

    def test_filter_batch(
        self, sample_criteria: SearchCriteria, sample_papers: List[PaperData]
    ) -> None:
        """Test batch filtering."""
        filter_obj = InitialFilter(sample_criteria)
        result = filter_obj.filter_batch(sample_papers)

        assert isinstance(result, BatchFilterResult)
        assert result.total_processed == len(sample_papers)
        # Only sample_paper should pass
        assert len(result.passed) == 1
        assert len(result.rejected) == 3

    def test_filter_batch_with_progress_callback(
        self, sample_criteria: SearchCriteria, sample_papers: List[PaperData]
    ) -> None:
        """Test batch filtering with progress callback."""
        filter_obj = InitialFilter(sample_criteria)
        progress_calls: List[tuple] = []

        def callback(current: int, total: int) -> None:
            progress_calls.append((current, total))

        result = filter_obj.filter_batch(sample_papers, progress_callback=callback)

        assert len(progress_calls) == len(sample_papers)
        assert progress_calls[-1] == (len(sample_papers), len(sample_papers))

    def test_filter_result_to_inclusion_decision_passed(
        self, sample_criteria: SearchCriteria, sample_paper: PaperData
    ) -> None:
        """Test converting passed FilterResult to InclusionDecision."""
        filter_obj = InitialFilter(sample_criteria)
        result = filter_obj.filter_paper(sample_paper)
        decision = result.to_inclusion_decision()

        assert decision.status == InclusionStatus.INCLUDED

    def test_filter_result_to_inclusion_decision_failed(
        self, sample_criteria: SearchCriteria, old_paper: PaperData
    ) -> None:
        """Test converting failed FilterResult to InclusionDecision."""
        filter_obj = InitialFilter(sample_criteria)
        result = filter_obj.filter_paper(old_paper)
        decision = result.to_inclusion_decision()

        assert decision.status == InclusionStatus.EXCLUDED
        assert decision.stage == ExclusionStage.INITIAL_FILTER

    def test_filter_statistics(
        self, sample_criteria: SearchCriteria, sample_papers: List[PaperData]
    ) -> None:
        """Test filter statistics collection."""
        filter_obj = InitialFilter(sample_criteria)
        result = filter_obj.filter_batch(sample_papers)
        stats = filter_obj.get_filter_statistics(result)

        assert stats["total_papers"] == len(sample_papers)
        assert stats["passed"] == 1
        assert stats["rejected"] == 3
        assert "rejection_reasons" in stats

    def test_custom_exclusion_keywords(self, sample_criteria: SearchCriteria) -> None:
        """Test custom exclusion keywords."""
        custom_keywords = ["custom_keyword", "another_keyword"]
        filter_obj = InitialFilter(
            sample_criteria, custom_exclusion_keywords=custom_keywords
        )

        paper = PaperData(
            document_id=11111,
            title="Study with Custom Keyword",
            authors=["Author"],
            year=2023,
            journal="Journal",
            abstract="This paper contains custom_keyword which should be excluded.",
        )

        result = filter_obj.filter_paper(paper)
        assert result.passed is False
        assert "custom_keyword" in result.reason.lower()

    def test_no_date_range_passes_old_papers(self, sample_paper: PaperData) -> None:
        """Test that papers pass when no date range is specified."""
        criteria = SearchCriteria(
            research_question="Test question",
            purpose="Test purpose",
            inclusion_criteria=["Human studies"],
            exclusion_criteria=[],
            date_range=None,  # No date filter
        )
        filter_obj = InitialFilter(criteria)

        old_paper_local = PaperData(
            document_id=99999,
            title="Very Old Study",
            authors=["Old Author"],
            year=1950,
            journal="Ancient Journal",
            abstract="This is a sufficiently long abstract to pass content checks. " * 3,
        )

        result = filter_obj.filter_paper(old_paper_local)
        assert result.passed is True


class TestStudyTypeKeywords:
    """Tests for study type keyword detection."""

    def test_rct_keywords_present(self) -> None:
        """Test RCT keywords are defined."""
        assert StudyTypeFilter.RCT in STUDY_TYPE_KEYWORDS
        keywords = STUDY_TYPE_KEYWORDS[StudyTypeFilter.RCT]
        assert "randomized controlled trial" in keywords
        assert "rct" in keywords

    def test_meta_analysis_keywords_present(self) -> None:
        """Test meta-analysis keywords are defined."""
        assert StudyTypeFilter.META_ANALYSIS in STUDY_TYPE_KEYWORDS
        keywords = STUDY_TYPE_KEYWORDS[StudyTypeFilter.META_ANALYSIS]
        assert "meta-analysis" in keywords

    def test_systematic_review_keywords_present(self) -> None:
        """Test systematic review keywords are defined."""
        assert StudyTypeFilter.SYSTEMATIC_REVIEW in STUDY_TYPE_KEYWORDS
        keywords = STUDY_TYPE_KEYWORDS[StudyTypeFilter.SYSTEMATIC_REVIEW]
        assert "systematic review" in keywords


# =============================================================================
# Context-Aware Filtering Tests
# =============================================================================

class TestContextAwareFiltering:
    """Tests for context-aware exclusion keyword filtering.

    These tests verify that the filter correctly handles edge cases where
    exclusion keywords appear in non-exclusionary contexts:
    - Systematic reviews that mention excluding certain study types
    - Human studies that reference prior animal experiments
    - Papers that compare to or discuss excluded study types
    """

    @pytest.fixture
    def simple_criteria(self) -> SearchCriteria:
        """Create minimal criteria for testing context-aware filtering."""
        return SearchCriteria(
            research_question="Test question about human studies",
            purpose="Testing context-aware filtering",
            inclusion_criteria=["Human studies"],
            exclusion_criteria=["Animal studies", "Case reports"],
            date_range=(2010, 2025),
        )

    def test_rejects_definitive_case_report_title(
        self, simple_criteria: SearchCriteria
    ) -> None:
        """Test that papers with definitive case report titles are rejected."""
        paper = PaperData(
            document_id=1001,
            title="Case Report: Rare Adverse Reaction to Treatment",
            authors=["Author A"],
            year=2023,
            journal="Case Reports Journal",
            abstract=(
                "We present a detailed case report of a patient who experienced "
                "an unusual adverse reaction. The patient was a 45-year-old male."
            ),
        )
        filter_obj = InitialFilter(simple_criteria)
        result = filter_obj.filter_paper(paper)

        assert result.passed is False
        assert "case report" in result.reason.lower()

    def test_passes_systematic_review_excluding_case_reports(
        self, simple_criteria: SearchCriteria
    ) -> None:
        """Test that systematic reviews mentioning excluded case reports pass.

        A systematic review that says 'we excluded case reports' should NOT
        be excluded just because it contains 'case report'.
        """
        paper = PaperData(
            document_id=1002,
            title="Systematic Review of Treatment Efficacy in Adults",
            authors=["Reviewer A", "Reviewer B"],
            year=2023,
            journal="Systematic Reviews Journal",
            abstract=(
                "Background: We conducted a systematic review of randomized trials. "
                "Methods: We searched PubMed and Cochrane databases. We excluded case reports "
                "and case series from our analysis. Only randomized controlled trials with "
                "human participants were included. Results: 45 studies met inclusion criteria."
            ),
        )
        filter_obj = InitialFilter(simple_criteria)
        result = filter_obj.filter_paper(paper)

        assert result.passed is True, f"Paper should pass but was rejected: {result.reason}"

    def test_passes_human_study_mentioning_prior_animal_experiments(
        self, simple_criteria: SearchCriteria
    ) -> None:
        """Test that human studies mentioning prior animal work pass.

        A human clinical trial that says 'following prior animal experiments'
        should NOT be excluded for containing 'animal'.
        """
        paper = PaperData(
            document_id=1003,
            title="Randomized Trial of Novel Treatment in Human Patients",
            authors=["Clinical A", "Clinical B"],
            year=2023,
            journal="Clinical Trials Journal",
            abstract=(
                "Background: Following prior animal model studies that demonstrated "
                "efficacy, we conducted a randomized controlled trial in human adults. "
                "Unlike earlier animal experiments, our study enrolled 500 human participants. "
                "Methods: This was a double-blind RCT. Results: Treatment was effective."
            ),
        )
        filter_obj = InitialFilter(simple_criteria)
        result = filter_obj.filter_paper(paper)

        assert result.passed is True, f"Paper should pass but was rejected: {result.reason}"

    def test_rejects_actual_animal_study(
        self, simple_criteria: SearchCriteria
    ) -> None:
        """Test that actual animal studies are still rejected."""
        paper = PaperData(
            document_id=1004,
            title="Treatment Effects in a Mouse Model of Disease",
            authors=["Animal Researcher"],
            year=2023,
            journal="Animal Research Journal",
            abstract=(
                "We investigated treatment effects using a mouse model. Mice were "
                "randomized to treatment or control groups. The animal study demonstrated "
                "significant improvements in outcomes."
            ),
        )
        filter_obj = InitialFilter(simple_criteria)
        result = filter_obj.filter_paper(paper)

        assert result.passed is False
        # Should be rejected due to definitive title pattern or exclusion keyword
        assert "animal" in result.reason.lower() or "mouse" in result.reason.lower()

    def test_passes_review_comparing_to_animal_studies(
        self, simple_criteria: SearchCriteria
    ) -> None:
        """Test that papers comparing human and animal findings pass."""
        paper = PaperData(
            document_id=1005,
            title="Meta-Analysis of Treatment Efficacy in Human Trials",
            authors=["Meta A"],
            year=2023,
            journal="Meta Analysis Journal",
            abstract=(
                "We conducted a meta-analysis of human clinical trials. In contrast to "
                "animal model studies, human trials showed moderate effect sizes. "
                "Compared to in vitro studies, clinical outcomes differed significantly. "
                "Our analysis included only human randomized controlled trials."
            ),
        )
        filter_obj = InitialFilter(simple_criteria)
        result = filter_obj.filter_paper(paper)

        assert result.passed is True, f"Paper should pass but was rejected: {result.reason}"

    def test_rejects_title_with_in_rats(self, simple_criteria: SearchCriteria) -> None:
        """Test that titles explicitly stating 'in rats' are rejected."""
        paper = PaperData(
            document_id=1006,
            title="Cardiovascular Effects of Treatment in Rats",
            authors=["Rat Researcher"],
            year=2023,
            journal="Animal Research",
            abstract=(
                "This study examined the cardiovascular effects of treatment in rats. "
                "We used Sprague-Dawley rats for all experiments."
            ),
        )
        filter_obj = InitialFilter(simple_criteria)
        result = filter_obj.filter_paper(paper)

        assert result.passed is False
        assert "animal" in result.reason.lower() or "rat" in result.reason.lower()

    def test_rejects_title_with_in_mice(self, simple_criteria: SearchCriteria) -> None:
        """Test that titles explicitly stating 'in mice' are rejected."""
        paper = PaperData(
            document_id=1007,
            title="Neuroprotective Effects in Mice After Treatment",
            authors=["Mouse Researcher"],
            year=2023,
            journal="Mouse Models",
            abstract=(
                "We evaluated neuroprotective effects of treatment in mice. "
                "C57BL/6 mice were used throughout the study."
            ),
        )
        filter_obj = InitialFilter(simple_criteria)
        result = filter_obj.filter_paper(paper)

        assert result.passed is False

    def test_passes_human_study_with_limitation_mention(
        self, simple_criteria: SearchCriteria
    ) -> None:
        """Test that studies discussing animal model limitations pass."""
        paper = PaperData(
            document_id=1008,
            title="Clinical Trial of Novel Therapy in Adult Patients",
            authors=["Clinical Team"],
            year=2023,
            journal="Clinical Medicine",
            abstract=(
                "This randomized controlled trial enrolled 200 adult patients. "
                "Limitations of prior animal model research necessitated human validation. "
                "Our results differ from mouse model predictions, suggesting species-specific "
                "effects. All participants were human adults aged 18-65."
            ),
        )
        filter_obj = InitialFilter(simple_criteria)
        result = filter_obj.filter_paper(paper)

        assert result.passed is True, f"Paper should pass but was rejected: {result.reason}"

    def test_passes_study_reviewing_excluded_literature(
        self, simple_criteria: SearchCriteria
    ) -> None:
        """Test that reviews discussing why certain study types were excluded pass."""
        paper = PaperData(
            document_id=1009,
            title="Evidence Synthesis of Treatment in Adults",
            authors=["Evidence Team"],
            year=2023,
            journal="Evidence Synthesis",
            abstract=(
                "We synthesized evidence from human trials. Case report literature was "
                "reviewed but excluded from quantitative analysis. Animal studies were "
                "also excluded as they have limited generalizability to humans. "
                "Our synthesis included 30 randomized controlled trials."
            ),
        )
        filter_obj = InitialFilter(simple_criteria)
        result = filter_obj.filter_paper(paper)

        assert result.passed is True, f"Paper should pass but was rejected: {result.reason}"

    def test_definitive_patterns_list_not_empty(self) -> None:
        """Test that definitive title patterns list is defined."""
        assert len(DEFINITIVE_TITLE_PATTERNS) > 0
        # Should include case report patterns
        assert any("case report" in p for p in DEFINITIVE_TITLE_PATTERNS)

    def test_negative_context_patterns_list_not_empty(self) -> None:
        """Test that negative context patterns list is defined."""
        assert len(NEGATIVE_CONTEXT_PATTERNS) > 0
        # Should include patterns for "excluded", "prior", "unlike"
        patterns_str = " ".join(NEGATIVE_CONTEXT_PATTERNS)
        assert "exclud" in patterns_str
        assert "prior" in patterns_str or "previous" in patterns_str


class TestDefinitiveTitlePatterns:
    """Tests specifically for definitive title pattern matching."""

    @pytest.fixture
    def minimal_criteria(self) -> SearchCriteria:
        """Create minimal criteria without date restrictions."""
        return SearchCriteria(
            research_question="Test",
            purpose="Test",
            inclusion_criteria=["Studies"],
            exclusion_criteria=[],
            date_range=(1900, 2100),
        )

    def test_case_report_colon_at_start(self, minimal_criteria: SearchCriteria) -> None:
        """Test 'Case Report: ...' pattern."""
        paper = PaperData(
            document_id=2001,
            title="Case Report: Unusual Presentation of Disease",
            authors=["A"],
            year=2023,
            abstract="Sufficient abstract content here for testing purposes.",
        )
        filter_obj = InitialFilter(minimal_criteria)
        result = filter_obj.filter_paper(paper)

        assert result.passed is False
        assert "case report" in result.reason.lower()

    def test_a_case_of_pattern(self, minimal_criteria: SearchCriteria) -> None:
        """Test 'A case of ...' pattern."""
        paper = PaperData(
            document_id=2002,
            title="A case of severe complications following treatment",
            authors=["A"],
            year=2023,
            abstract="This paper describes a single patient case with complications.",
        )
        filter_obj = InitialFilter(minimal_criteria)
        result = filter_obj.filter_paper(paper)

        assert result.passed is False

    def test_editorial_colon_at_start(self, minimal_criteria: SearchCriteria) -> None:
        """Test 'Editorial: ...' pattern."""
        paper = PaperData(
            document_id=2003,
            title="Editorial: The Future of Treatment Research",
            authors=["Editor A"],
            year=2023,
            abstract="This editorial discusses the future directions of research in this field.",
        )
        filter_obj = InitialFilter(minimal_criteria)
        result = filter_obj.filter_paper(paper)

        assert result.passed is False
        assert "editorial" in result.reason.lower()

    def test_retracted_at_end(self, minimal_criteria: SearchCriteria) -> None:
        """Test '... [Retracted]' pattern."""
        paper = PaperData(
            document_id=2004,
            title="Original Study Title RETRACTED",
            authors=["Disgraced Author"],
            year=2023,
            abstract="This paper has been retracted due to data fabrication concerns.",
        )
        filter_obj = InitialFilter(minimal_criteria)
        result = filter_obj.filter_paper(paper)

        assert result.passed is False
        assert "retracted" in result.reason.lower()

    def test_in_vivo_study_title(self, minimal_criteria: SearchCriteria) -> None:
        """Test 'in vivo study' pattern."""
        paper = PaperData(
            document_id=2005,
            title="Therapeutic Efficacy: An In Vivo Study",
            authors=["Lab Researcher"],
            year=2023,
            abstract="We conducted an in vivo study to evaluate therapeutic efficacy.",
        )
        filter_obj = InitialFilter(minimal_criteria)
        result = filter_obj.filter_paper(paper)

        assert result.passed is False


# =============================================================================
# InclusionEvaluator Tests (Mocked)
# =============================================================================

class TestInclusionEvaluator:
    """Tests for InclusionEvaluator class (with mocked LLM calls)."""

    def test_initialization(self, sample_criteria: SearchCriteria) -> None:
        """Test InclusionEvaluator initialization."""
        evaluator = InclusionEvaluator(sample_criteria)

        assert evaluator.criteria == sample_criteria
        assert evaluator.model is not None
        assert evaluator._system_prompt is not None

    def test_system_prompt_contains_criteria(
        self, sample_criteria: SearchCriteria
    ) -> None:
        """Test system prompt includes inclusion/exclusion criteria."""
        evaluator = InclusionEvaluator(sample_criteria)

        assert sample_criteria.research_question in evaluator._system_prompt
        assert "Human studies" in evaluator._system_prompt
        assert "Animal studies" in evaluator._system_prompt

    @patch("bmlibrarian.agents.systematic_review.filters.ollama.chat")
    def test_evaluate_returns_included(
        self,
        mock_chat: MagicMock,
        sample_criteria: SearchCriteria,
        sample_paper: PaperData,
    ) -> None:
        """Test evaluation returns INCLUDED decision."""
        mock_chat.return_value = {
            "message": {
                "content": json.dumps({
                    "decision": "INCLUDE",
                    "confidence": 0.95,
                    "inclusion_criteria_met": ["Human studies", "Statin intervention"],
                    "inclusion_criteria_failed": [],
                    "exclusion_criteria_matched": [],
                    "rationale": "Paper meets all inclusion criteria",
                })
            }
        }

        evaluator = InclusionEvaluator(sample_criteria)
        decision = evaluator.evaluate(sample_paper)

        assert decision.status == InclusionStatus.INCLUDED
        assert decision.confidence == 0.95
        assert len(decision.criteria_matched) == 2

    @patch("bmlibrarian.agents.systematic_review.filters.ollama.chat")
    def test_evaluate_returns_excluded(
        self,
        mock_chat: MagicMock,
        sample_criteria: SearchCriteria,
        animal_study_paper: PaperData,
    ) -> None:
        """Test evaluation returns EXCLUDED decision."""
        mock_chat.return_value = {
            "message": {
                "content": json.dumps({
                    "decision": "EXCLUDE",
                    "confidence": 0.9,
                    "inclusion_criteria_met": [],
                    "inclusion_criteria_failed": ["Human studies"],
                    "exclusion_criteria_matched": ["Animal studies"],
                    "rationale": "This is an animal study",
                })
            }
        }

        evaluator = InclusionEvaluator(sample_criteria)
        decision = evaluator.evaluate(animal_study_paper)

        assert decision.status == InclusionStatus.EXCLUDED
        assert "Animal studies" in decision.exclusion_matched

    @patch("bmlibrarian.agents.systematic_review.filters.ollama.chat")
    def test_evaluate_returns_uncertain(
        self,
        mock_chat: MagicMock,
        sample_criteria: SearchCriteria,
        sample_paper: PaperData,
    ) -> None:
        """Test evaluation returns UNCERTAIN decision."""
        mock_chat.return_value = {
            "message": {
                "content": json.dumps({
                    "decision": "UNCERTAIN",
                    "confidence": 0.4,
                    "inclusion_criteria_met": ["Statin intervention"],
                    "inclusion_criteria_failed": [],
                    "exclusion_criteria_matched": [],
                    "rationale": "Unclear if study is human-only",
                })
            }
        }

        evaluator = InclusionEvaluator(sample_criteria)
        decision = evaluator.evaluate(sample_paper)

        assert decision.status == InclusionStatus.UNCERTAIN
        assert decision.confidence == 0.4

    @patch("bmlibrarian.agents.systematic_review.filters.ollama.chat")
    def test_evaluate_handles_error(
        self,
        mock_chat: MagicMock,
        sample_criteria: SearchCriteria,
        sample_paper: PaperData,
    ) -> None:
        """Test evaluation handles LLM errors gracefully."""
        mock_chat.side_effect = Exception("LLM connection failed")

        evaluator = InclusionEvaluator(sample_criteria)
        decision = evaluator.evaluate(sample_paper)

        assert decision.status == InclusionStatus.UNCERTAIN
        assert decision.confidence == 0.0
        assert "error" in decision.rationale.lower() or "unable" in decision.rationale.lower()

    @patch("bmlibrarian.agents.systematic_review.filters.ollama.chat")
    def test_evaluate_batch(
        self,
        mock_chat: MagicMock,
        sample_criteria: SearchCriteria,
        sample_papers: List[PaperData],
    ) -> None:
        """Test batch evaluation."""
        mock_chat.return_value = {
            "message": {
                "content": json.dumps({
                    "decision": "INCLUDE",
                    "confidence": 0.8,
                    "inclusion_criteria_met": ["All"],
                    "inclusion_criteria_failed": [],
                    "exclusion_criteria_matched": [],
                    "rationale": "Meets criteria",
                })
            }
        }

        evaluator = InclusionEvaluator(sample_criteria)
        results = evaluator.evaluate_batch(sample_papers[:2])

        assert len(results) == 2
        assert all(isinstance(r[1], InclusionDecision) for r in results)

    @patch("bmlibrarian.agents.systematic_review.filters.ollama.chat")
    def test_evaluation_statistics(
        self,
        mock_chat: MagicMock,
        sample_criteria: SearchCriteria,
        sample_papers: List[PaperData],
    ) -> None:
        """Test evaluation statistics collection."""
        # Alternate between INCLUDE and EXCLUDE
        responses = [
            {"decision": "INCLUDE", "confidence": 0.9},
            {"decision": "EXCLUDE", "confidence": 0.8},
        ]

        call_count = [0]

        def side_effect(*args: Any, **kwargs: Any) -> Dict[str, Any]:
            result = responses[call_count[0] % 2]
            call_count[0] += 1
            return {
                "message": {
                    "content": json.dumps({
                        **result,
                        "inclusion_criteria_met": [],
                        "inclusion_criteria_failed": [],
                        "exclusion_criteria_matched": [],
                        "rationale": "Test",
                    })
                }
            }

        mock_chat.side_effect = side_effect

        evaluator = InclusionEvaluator(sample_criteria)
        results = evaluator.evaluate_batch(sample_papers[:2])
        stats = evaluator.get_evaluation_statistics(results)

        assert stats["total_evaluated"] == 2
        assert "status_counts" in stats
        assert "average_confidence" in stats


# =============================================================================
# RelevanceScorer Tests (Mocked)
# =============================================================================

class TestRelevanceScorer:
    """Tests for RelevanceScorer class (with mocked scoring agent)."""

    @patch("bmlibrarian.agents.systematic_review.scorer.RelevanceScorer._get_scoring_agent")
    def test_score_paper(
        self,
        mock_get_agent: MagicMock,
        sample_paper: PaperData,
    ) -> None:
        """Test scoring a single paper."""
        mock_agent = MagicMock()
        mock_agent.evaluate_document.return_value = {
            "score": 4,
            "reasoning": "Highly relevant to research question",
        }
        mock_get_agent.return_value = mock_agent

        scorer = RelevanceScorer(
            research_question="What is the efficacy of statins?",
        )
        scored_paper = scorer.score_paper(sample_paper, evaluate_inclusion=False)

        assert scored_paper.relevance_score == 4.0
        assert "relevant" in scored_paper.relevance_rationale.lower()

    @patch("bmlibrarian.agents.systematic_review.scorer.RelevanceScorer._get_scoring_agent")
    def test_score_batch(
        self,
        mock_get_agent: MagicMock,
        sample_papers: List[PaperData],
    ) -> None:
        """Test batch scoring."""
        mock_agent = MagicMock()
        mock_agent.evaluate_document.return_value = {
            "score": 3,
            "reasoning": "Moderately relevant",
        }
        mock_get_agent.return_value = mock_agent

        scorer = RelevanceScorer(
            research_question="What is the efficacy of statins?",
        )
        result = scorer.score_batch(sample_papers[:2], evaluate_inclusion=False)

        assert isinstance(result, BatchScoringResult)
        assert len(result.scored_papers) == 2
        assert result.average_score == 3.0

    @patch("bmlibrarian.agents.systematic_review.scorer.RelevanceScorer._get_scoring_agent")
    def test_apply_relevance_threshold(
        self,
        mock_get_agent: MagicMock,
        sample_papers: List[PaperData],
    ) -> None:
        """Test applying relevance threshold."""
        mock_agent = MagicMock()
        # Return alternating scores
        scores = [4, 2, 5, 1]
        call_count = [0]

        def side_effect(*args: Any, **kwargs: Any) -> Dict[str, Any]:
            result = {"score": scores[call_count[0] % 4], "reasoning": "Test"}
            call_count[0] += 1
            return result

        mock_agent.evaluate_document.side_effect = side_effect
        mock_get_agent.return_value = mock_agent

        scorer = RelevanceScorer(
            research_question="Test question",
        )
        result = scorer.score_batch(sample_papers, evaluate_inclusion=False)

        above, below = scorer.apply_relevance_threshold(
            result.scored_papers, threshold=3.0
        )

        # Papers with scores 4 and 5 should be above threshold
        assert len(above) == 2
        assert len(below) == 2
        assert all(p.relevance_score >= 3.0 for p in above)
        assert all(p.relevance_score < 3.0 for p in below)

    @patch("bmlibrarian.agents.systematic_review.scorer.RelevanceScorer._get_scoring_agent")
    def test_score_based_decision_included(
        self,
        mock_get_agent: MagicMock,
        sample_paper: PaperData,
    ) -> None:
        """Test score-based inclusion decision for high score."""
        mock_agent = MagicMock()
        mock_agent.evaluate_document.return_value = {
            "score": 4,
            "reasoning": "Relevant",
        }
        mock_get_agent.return_value = mock_agent

        config = get_default_config()
        config.relevance_threshold = 2.5

        scorer = RelevanceScorer(
            research_question="Test",
            config=config,
        )
        scored_paper = scorer.score_paper(sample_paper, evaluate_inclusion=False)

        assert scored_paper.inclusion_decision.status == InclusionStatus.INCLUDED

    @patch("bmlibrarian.agents.systematic_review.scorer.RelevanceScorer._get_scoring_agent")
    def test_score_based_decision_excluded(
        self,
        mock_get_agent: MagicMock,
        sample_paper: PaperData,
    ) -> None:
        """Test score-based exclusion decision for low score."""
        mock_agent = MagicMock()
        mock_agent.evaluate_document.return_value = {
            "score": 1,
            "reasoning": "Not relevant",
        }
        mock_get_agent.return_value = mock_agent

        config = get_default_config()
        config.relevance_threshold = 2.5

        scorer = RelevanceScorer(
            research_question="Test",
            config=config,
        )
        scored_paper = scorer.score_paper(sample_paper, evaluate_inclusion=False)

        assert scored_paper.inclusion_decision.status == InclusionStatus.EXCLUDED

    @patch("bmlibrarian.agents.systematic_review.scorer.RelevanceScorer._get_scoring_agent")
    def test_scoring_statistics(
        self,
        mock_get_agent: MagicMock,
        sample_papers: List[PaperData],
    ) -> None:
        """Test scoring statistics collection."""
        mock_agent = MagicMock()
        mock_agent.evaluate_document.return_value = {
            "score": 3,
            "reasoning": "Moderate",
        }
        mock_get_agent.return_value = mock_agent

        scorer = RelevanceScorer(research_question="Test")
        result = scorer.score_batch(sample_papers[:2], evaluate_inclusion=False)
        stats = scorer.get_scoring_statistics(result)

        assert stats["total_papers"] == 2
        assert stats["successfully_scored"] == 2
        assert "average_score" in stats
        assert "score_distribution" in stats


# =============================================================================
# CompositeScorer Tests
# =============================================================================

class TestCompositeScorer:
    """Tests for CompositeScorer class."""

    def test_initialization_default_weights(self) -> None:
        """Test CompositeScorer with default weights."""
        scorer = CompositeScorer()
        assert scorer.weights.validate()

    def test_initialization_custom_weights(
        self, sample_weights: ScoringWeights
    ) -> None:
        """Test CompositeScorer with custom weights."""
        scorer = CompositeScorer(weights=sample_weights)
        assert scorer.weights == sample_weights

    def test_score_calculation(self, sample_assessed_paper: AssessedPaper) -> None:
        """Test composite score calculation."""
        scorer = CompositeScorer()
        score = scorer.score(sample_assessed_paper)

        assert isinstance(score, float)
        assert 0.0 <= score <= 10.0

    def test_score_batch(self, sample_assessed_paper: AssessedPaper) -> None:
        """Test batch scoring."""
        papers = [sample_assessed_paper]
        scorer = CompositeScorer()
        result = scorer.score_batch(papers)

        assert len(result) == 1
        assert result[0].composite_score is not None

    def test_rank(self, sample_assessed_paper: AssessedPaper) -> None:
        """Test paper ranking."""
        # Create papers with different scores
        paper1 = sample_assessed_paper
        paper1.composite_score = 8.0

        paper2 = AssessedPaper(
            scored_paper=ScoredPaper(
                paper=PaperData(
                    document_id=2,
                    title="Lower ranked paper",
                    authors=["Author"],
                    year=2023,
                    abstract="Test abstract" * 5,
                ),
                relevance_score=3.0,
                relevance_rationale="Moderate",
                inclusion_decision=InclusionDecision.create_included(
                    stage=ExclusionStage.QUALITY_GATE,
                    rationale="OK",
                    criteria_matched=[],
                ),
            ),
            study_assessment={"overall_quality": 5.0},
            paper_weight={"replication_status": "unknown"},
        )
        paper2.composite_score = 5.0

        papers = [paper2, paper1]  # Lower score first
        scorer = CompositeScorer()
        ranked = scorer.rank(papers)

        assert ranked[0].composite_score == 8.0  # Higher score first
        assert ranked[0].final_rank == 1
        assert ranked[1].final_rank == 2

    def test_apply_quality_gate(self, sample_assessed_paper: AssessedPaper) -> None:
        """Test quality gate filtering."""
        sample_assessed_paper.composite_score = 6.0

        low_quality_paper = AssessedPaper(
            scored_paper=ScoredPaper(
                paper=PaperData(
                    document_id=3,
                    title="Low quality paper",
                    authors=["Author"],
                    year=2023,
                    abstract="Test abstract" * 5,
                ),
                relevance_score=2.0,
                relevance_rationale="Low",
                inclusion_decision=InclusionDecision.create_included(
                    stage=ExclusionStage.QUALITY_GATE,
                    rationale="OK",
                    criteria_matched=[],
                ),
            ),
            study_assessment={"overall_quality": 2.0},
            paper_weight={},
        )
        low_quality_paper.composite_score = 3.0

        papers = [sample_assessed_paper, low_quality_paper]
        scorer = CompositeScorer()
        passed, failed = scorer.apply_quality_gate(papers, threshold=5.0)

        assert len(passed) == 1
        assert len(failed) == 1
        assert passed[0].composite_score == 6.0
        assert failed[0].scored_paper.inclusion_decision.status == InclusionStatus.EXCLUDED

    def test_normalize_relevance_score(self) -> None:
        """Test relevance score normalization."""
        scorer = CompositeScorer()

        # Score of 1 (min) should normalize to 0
        assert scorer._normalize_relevance_score(1.0) == pytest.approx(0.0, abs=0.01)

        # Score of 5 (max) should normalize to 10
        assert scorer._normalize_relevance_score(5.0) == pytest.approx(10.0, abs=0.01)

        # Score of 3 (middle) should normalize to 5
        assert scorer._normalize_relevance_score(3.0) == pytest.approx(5.0, abs=0.01)

    def test_recency_scoring(self) -> None:
        """Test recency score calculation."""
        scorer = CompositeScorer()

        # Current year should get max score
        current_year = datetime.now().year
        assert scorer._calculate_recency_score(current_year) == 10.0

        # Very old papers should get low score
        assert scorer._calculate_recency_score(1990) < 3.0

    def test_scoring_statistics(self, sample_assessed_paper: AssessedPaper) -> None:
        """Test scoring statistics."""
        sample_assessed_paper.composite_score = 7.5

        scorer = CompositeScorer()
        stats = scorer.get_scoring_statistics([sample_assessed_paper])

        assert stats["total"] == 1
        assert stats["scored"] == 1
        assert stats["mean_score"] == 7.5


# =============================================================================
# BatchFilterResult and BatchScoringResult Tests
# =============================================================================

class TestBatchResults:
    """Tests for batch result dataclasses."""

    def test_batch_filter_result_pass_rate(self) -> None:
        """Test BatchFilterResult pass rate calculation."""
        result = BatchFilterResult(
            passed=[MagicMock()],
            rejected=[(MagicMock(), "reason")],
            total_processed=2,
        )
        assert result.pass_rate == 0.5

    def test_batch_filter_result_empty(self) -> None:
        """Test BatchFilterResult with no papers."""
        result = BatchFilterResult(total_processed=0)
        assert result.pass_rate == 0.0

    def test_batch_filter_result_to_dict(self) -> None:
        """Test BatchFilterResult serialization."""
        result = BatchFilterResult(
            passed=[MagicMock()],
            rejected=[(MagicMock(), "reason")],
            total_processed=2,
            execution_time_seconds=1.5,
        )
        data = result.to_dict()

        assert data["passed_count"] == 1
        assert data["rejected_count"] == 1
        assert data["total_processed"] == 2
        assert data["pass_rate"] == 50.0

    def test_batch_scoring_result_success_rate(self) -> None:
        """Test BatchScoringResult success rate calculation."""
        result = BatchScoringResult(
            scored_papers=[MagicMock()],
            failed_papers=[(MagicMock(), "error")],
            total_processed=2,
        )
        assert result.success_rate == 0.5

    def test_batch_scoring_result_to_dict(self) -> None:
        """Test BatchScoringResult serialization."""
        result = BatchScoringResult(
            scored_papers=[MagicMock()],
            failed_papers=[],
            total_processed=1,
            execution_time_seconds=2.0,
            average_score=4.0,
        )
        data = result.to_dict()

        assert data["scored_count"] == 1
        assert data["failed_count"] == 0
        assert data["average_score"] == 4.0


# =============================================================================
# Integration Tests
# =============================================================================

class TestFilteringScoringIntegration:
    """Integration tests for filtering and scoring workflow."""

    def test_filter_result_to_decision_integration(
        self, sample_criteria: SearchCriteria, sample_paper: PaperData
    ) -> None:
        """Test filter result converts to valid inclusion decision."""
        filter_obj = InitialFilter(sample_criteria)
        result = filter_obj.filter_paper(sample_paper)
        decision = result.to_inclusion_decision()

        assert isinstance(decision, InclusionDecision)
        assert decision.stage == ExclusionStage.INITIAL_FILTER

    @patch("bmlibrarian.agents.systematic_review.scorer.RelevanceScorer._get_scoring_agent")
    def test_scorer_produces_valid_scored_paper(
        self,
        mock_get_agent: MagicMock,
        sample_paper: PaperData,
    ) -> None:
        """Test scorer produces valid ScoredPaper."""
        mock_agent = MagicMock()
        mock_agent.evaluate_document.return_value = {
            "score": 4,
            "reasoning": "Good relevance",
        }
        mock_get_agent.return_value = mock_agent

        scorer = RelevanceScorer(research_question="Test")
        scored = scorer.score_paper(sample_paper, evaluate_inclusion=False)

        assert isinstance(scored, ScoredPaper)
        assert scored.paper == sample_paper
        assert 1 <= scored.relevance_score <= 5

    def test_composite_scorer_handles_missing_assessments(
        self, sample_scored_paper: ScoredPaper
    ) -> None:
        """Test CompositeScorer handles missing assessment data."""
        assessed = AssessedPaper(
            scored_paper=sample_scored_paper,
            study_assessment={},  # Empty assessment
            paper_weight={},  # Empty weight
        )

        scorer = CompositeScorer()
        score = scorer.score(assessed)

        # Should still calculate a valid score using defaults
        assert isinstance(score, float)
        assert 0.0 <= score <= 10.0
