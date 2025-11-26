"""
Unit Tests for Benchmark Utilities

Tests the core benchmark utility functions including:
- Data model serialization/deserialization
- PMID/DOI/title normalization
- Paper matching logic
- Recall/precision calculation
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from .benchmark_utils import (
    GroundTruthPaper,
    CochraneGroundTruth,
    PaperMatch,
    BenchmarkResult,
    normalize_doi,
    normalize_pmid,
    normalize_title,
    calculate_title_similarity,
    match_paper_to_result,
    match_papers,
    calculate_recall_precision,
    load_ground_truth,
    save_ground_truth,
    MIN_TITLE_SIMILARITY_THRESHOLD,
    TARGET_RECALL_RATE,
)


# =============================================================================
# Tests: GroundTruthPaper
# =============================================================================

class TestGroundTruthPaper:
    """Tests for GroundTruthPaper data model."""

    def test_create_with_pmid(self):
        """Test creating paper with PMID."""
        paper = GroundTruthPaper(pmid="12345678")
        assert paper.pmid == "12345678"

    def test_create_with_doi(self):
        """Test creating paper with DOI."""
        paper = GroundTruthPaper(doi="10.1000/test")
        assert paper.doi == "10.1000/test"

    def test_create_with_title(self):
        """Test creating paper with title only."""
        paper = GroundTruthPaper(title="Test Paper Title")
        assert paper.title == "Test Paper Title"

    def test_create_without_identifier_raises(self):
        """Test that paper without any identifier raises error."""
        with pytest.raises(ValueError, match="at least one identifier"):
            GroundTruthPaper()

    def test_pmid_normalization(self):
        """Test PMID is normalized (leading zeros stripped)."""
        paper = GroundTruthPaper(pmid="00012345")
        assert paper.pmid == "12345"

    def test_doi_normalization(self):
        """Test DOI is normalized (lowercase, stripped)."""
        paper = GroundTruthPaper(doi="  10.1000/TEST  ")
        assert paper.doi == "10.1000/test"

    def test_to_dict(self):
        """Test serialization to dict."""
        paper = GroundTruthPaper(
            pmid="12345",
            doi="10.1000/test",
            title="Test Paper",
            authors=["Author A"],
            year=2020,
        )
        data = paper.to_dict()
        assert data["pmid"] == "12345"
        assert data["doi"] == "10.1000/test"
        assert data["title"] == "Test Paper"

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "pmid": "12345",
            "title": "Test Paper",
            "year": 2020,
        }
        paper = GroundTruthPaper.from_dict(data)
        assert paper.pmid == "12345"
        assert paper.title == "Test Paper"
        assert paper.year == 2020

    def test_get_display_name_with_title(self):
        """Test display name prefers title."""
        paper = GroundTruthPaper(pmid="12345", title="A Long Title Here")
        assert "A Long Title Here" in paper.get_display_name()

    def test_get_display_name_fallback_pmid(self):
        """Test display name falls back to PMID."""
        paper = GroundTruthPaper(pmid="12345")
        assert paper.get_display_name() == "PMID:12345"


# =============================================================================
# Tests: CochraneGroundTruth
# =============================================================================

class TestCochraneGroundTruth:
    """Tests for CochraneGroundTruth data model."""

    def test_create_valid(self):
        """Test creating valid ground truth."""
        gt = CochraneGroundTruth(
            cochrane_id="CD000001",
            title="Test Review",
            research_question="Does X improve Y?",
            included_studies=[
                GroundTruthPaper(pmid="12345"),
            ],
        )
        assert gt.cochrane_id == "CD000001"
        assert gt.study_count == 1

    def test_create_without_id_raises(self):
        """Test that missing cochrane_id raises error."""
        with pytest.raises(ValueError, match="Cochrane ID is required"):
            CochraneGroundTruth(
                cochrane_id="",
                title="Test",
                research_question="Test?",
                included_studies=[GroundTruthPaper(pmid="12345")],
            )

    def test_create_without_studies_raises(self):
        """Test that empty studies raises error."""
        with pytest.raises(ValueError, match="(?i)at least one included study"):
            CochraneGroundTruth(
                cochrane_id="CD000001",
                title="Test",
                research_question="Test?",
                included_studies=[],
            )

    def test_to_dict_and_back(self):
        """Test round-trip serialization."""
        original = CochraneGroundTruth(
            cochrane_id="CD000001",
            title="Test Review",
            research_question="Does X improve Y?",
            included_studies=[
                GroundTruthPaper(pmid="12345", title="Study 1"),
                GroundTruthPaper(doi="10.1000/test", title="Study 2"),
            ],
            pico={"population": "adults", "intervention": "treatment"},
            date_range=(2010, 2020),
        )

        data = original.to_dict()
        restored = CochraneGroundTruth.from_dict(data)

        assert restored.cochrane_id == original.cochrane_id
        assert restored.study_count == original.study_count
        assert restored.date_range == original.date_range

    def test_to_search_criteria_dict(self):
        """Test conversion to SearchCriteria format."""
        gt = CochraneGroundTruth(
            cochrane_id="CD000001",
            title="Test Review",
            research_question="Does X improve Y?",
            included_studies=[GroundTruthPaper(pmid="12345")],
            inclusion_criteria=["RCTs", "Adults"],
            exclusion_criteria=["Animal studies"],
            date_range=(2010, 2020),
        )

        criteria = gt.to_search_criteria_dict()

        assert criteria["research_question"] == "Does X improve Y?"
        assert criteria["inclusion_criteria"] == ["RCTs", "Adults"]
        assert criteria["exclusion_criteria"] == ["Animal studies"]
        assert criteria["date_range"] == [2010, 2020]


# =============================================================================
# Tests: Normalization Functions
# =============================================================================

class TestNormalization:
    """Tests for identifier normalization functions."""

    def test_normalize_doi_basic(self):
        """Test basic DOI normalization."""
        assert normalize_doi("10.1000/test") == "10.1000/test"

    def test_normalize_doi_lowercase(self):
        """Test DOI lowercase conversion."""
        assert normalize_doi("10.1000/TEST") == "10.1000/test"

    def test_normalize_doi_strip_whitespace(self):
        """Test DOI whitespace stripping."""
        assert normalize_doi("  10.1000/test  ") == "10.1000/test"

    def test_normalize_doi_remove_url_prefix(self):
        """Test DOI URL prefix removal."""
        assert normalize_doi("https://doi.org/10.1000/test") == "10.1000/test"
        assert normalize_doi("http://doi.org/10.1000/test") == "10.1000/test"
        assert normalize_doi("doi.org/10.1000/test") == "10.1000/test"
        assert normalize_doi("doi:10.1000/test") == "10.1000/test"

    def test_normalize_doi_none(self):
        """Test None DOI handling."""
        assert normalize_doi(None) is None
        assert normalize_doi("") is None

    def test_normalize_pmid_basic(self):
        """Test basic PMID normalization."""
        assert normalize_pmid("12345678") == "12345678"

    def test_normalize_pmid_strip_zeros(self):
        """Test PMID leading zero removal."""
        assert normalize_pmid("00012345") == "12345"

    def test_normalize_pmid_extract_number(self):
        """Test PMID number extraction."""
        assert normalize_pmid("PMID: 12345") == "12345"

    def test_normalize_pmid_none(self):
        """Test None PMID handling."""
        assert normalize_pmid(None) is None
        assert normalize_pmid("") is None

    def test_normalize_title_lowercase(self):
        """Test title lowercase conversion."""
        assert normalize_title("TEST TITLE") == "test title"

    def test_normalize_title_punctuation(self):
        """Test title punctuation removal."""
        assert normalize_title("Test: A Study.") == "test a study"

    def test_normalize_title_whitespace(self):
        """Test title whitespace collapsing."""
        assert normalize_title("Test   Multiple    Spaces") == "test multiple spaces"


# =============================================================================
# Tests: Title Similarity
# =============================================================================

class TestTitleSimilarity:
    """Tests for title similarity calculation."""

    def test_identical_titles(self):
        """Test identical titles have similarity 1.0."""
        similarity = calculate_title_similarity("Test Title", "Test Title")
        assert similarity == 1.0

    def test_case_insensitive(self):
        """Test similarity is case-insensitive."""
        similarity = calculate_title_similarity("TEST TITLE", "test title")
        assert similarity == 1.0

    def test_punctuation_ignored(self):
        """Test punctuation differences are ignored."""
        similarity = calculate_title_similarity(
            "Test: A Study",
            "Test - A Study"
        )
        assert similarity > 0.9

    def test_minor_differences(self):
        """Test minor differences still give high similarity."""
        similarity = calculate_title_similarity(
            "Effect of Treatment A on Disease B",
            "Effects of Treatment A on Disease B"
        )
        assert similarity > MIN_TITLE_SIMILARITY_THRESHOLD

    def test_completely_different(self):
        """Test completely different titles have low similarity."""
        similarity = calculate_title_similarity(
            "Study of Cardiovascular Disease",
            "Analysis of Machine Learning Algorithms"
        )
        # Similarity should be well below the matching threshold (0.85)
        assert similarity < 0.5


# =============================================================================
# Tests: Paper Matching
# =============================================================================

class TestPaperMatching:
    """Tests for paper matching logic."""

    def test_match_by_pmid(self):
        """Test matching by PMID (highest priority)."""
        gt = GroundTruthPaper(pmid="12345", doi="10.1000/other")
        papers = [
            {"document_id": 1, "pmid": "12345", "doi": "10.1000/different", "title": "Paper 1"},
        ]

        match = match_paper_to_result(gt, papers, {1})

        assert match.found is True
        assert match.match_method == "pmid"
        assert match.match_confidence == 1.0

    def test_match_by_doi(self):
        """Test matching by DOI."""
        gt = GroundTruthPaper(doi="10.1000/test")
        papers = [
            {"document_id": 1, "pmid": "99999", "doi": "10.1000/test", "title": "Paper 1"},
        ]

        match = match_paper_to_result(gt, papers, {1})

        assert match.found is True
        assert match.match_method == "doi"

    def test_match_by_title_fuzzy(self):
        """Test matching by fuzzy title."""
        gt = GroundTruthPaper(title="Effect of Treatment on Disease Outcomes")
        papers = [
            {
                "document_id": 1,
                "pmid": None,
                "doi": None,
                "title": "Effects of Treatment on Disease Outcomes"
            },
        ]

        match = match_paper_to_result(gt, papers, {1})

        assert match.found is True
        assert match.match_method == "title_fuzzy"
        assert match.match_confidence >= MIN_TITLE_SIMILARITY_THRESHOLD

    def test_no_match(self):
        """Test no match found."""
        gt = GroundTruthPaper(pmid="12345")
        papers = [
            {"document_id": 1, "pmid": "99999", "doi": None, "title": "Unrelated Paper"},
        ]

        match = match_paper_to_result(gt, papers, {1})

        assert match.found is False
        assert match.matched_document_id is None

    def test_found_but_not_included(self):
        """Test paper found but not in included set."""
        gt = GroundTruthPaper(pmid="12345")
        papers = [
            {"document_id": 1, "pmid": "12345", "title": "Paper 1"},
        ]

        # Empty included set - paper found but not included
        match = match_paper_to_result(gt, papers, set())

        assert match.found is True
        assert match.is_in_included is False
        assert match.found_and_included is False


# =============================================================================
# Tests: Recall/Precision Calculation
# =============================================================================

class TestRecallPrecision:
    """Tests for recall/precision calculation."""

    def test_perfect_recall(self):
        """Test 100% recall scenario."""
        gt = CochraneGroundTruth(
            cochrane_id="CD000001",
            title="Test",
            research_question="Test?",
            included_studies=[
                GroundTruthPaper(pmid="123"),
                GroundTruthPaper(pmid="456"),
            ],
        )

        agent_included = [
            {"document_id": 1, "pmid": "123", "title": "Paper 1"},
            {"document_id": 2, "pmid": "456", "title": "Paper 2"},
            {"document_id": 3, "pmid": "789", "title": "Extra Paper"},
        ]

        result = calculate_recall_precision(gt, agent_included, [])

        assert result.recall == 1.0
        assert result.passed is True
        assert result.papers_found_and_included == 2

    def test_partial_recall(self):
        """Test partial recall scenario."""
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

        assert result.recall == pytest.approx(1/3, rel=0.01)
        assert result.passed is False
        assert result.papers_found == 2
        assert result.papers_found_and_included == 1
        assert result.papers_not_found == 1
        assert result.papers_found_but_excluded == 1

    def test_zero_recall(self):
        """Test zero recall (no papers found)."""
        gt = CochraneGroundTruth(
            cochrane_id="CD000001",
            title="Test",
            research_question="Test?",
            included_studies=[
                GroundTruthPaper(pmid="123"),
                GroundTruthPaper(pmid="456"),
            ],
        )

        result = calculate_recall_precision(gt, [], [])

        assert result.recall == 0.0
        assert result.passed is False
        assert result.papers_not_found == 2

    def test_precision_calculation(self):
        """Test precision is calculated correctly."""
        gt = CochraneGroundTruth(
            cochrane_id="CD000001",
            title="Test",
            research_question="Test?",
            included_studies=[
                GroundTruthPaper(pmid="123"),
            ],
        )

        agent_included = [
            {"document_id": 1, "pmid": "123", "title": "Paper 1"},  # In GT
            {"document_id": 2, "pmid": "999", "title": "Extra 1"},  # Not in GT
            {"document_id": 3, "pmid": "888", "title": "Extra 2"},  # Not in GT
        ]

        result = calculate_recall_precision(gt, agent_included, [])

        # Precision = 1 (GT paper in included) / 3 (total included) = 0.33
        assert result.precision == pytest.approx(1/3, rel=0.01)


# =============================================================================
# Tests: File I/O
# =============================================================================

class TestFileIO:
    """Tests for file I/O functions."""

    def test_save_and_load_ground_truth(self, tmp_path):
        """Test saving and loading ground truth."""
        original = CochraneGroundTruth(
            cochrane_id="CD000001",
            title="Test Review",
            research_question="Does X improve Y?",
            included_studies=[
                GroundTruthPaper(pmid="12345", title="Study 1"),
                GroundTruthPaper(doi="10.1000/test", title="Study 2"),
            ],
        )

        file_path = tmp_path / "test_gt.json"
        save_ground_truth(original, str(file_path))

        loaded = load_ground_truth(str(file_path))

        assert loaded.cochrane_id == original.cochrane_id
        assert loaded.study_count == original.study_count
        assert loaded.included_studies[0].pmid == "12345"

    def test_load_nonexistent_file(self):
        """Test loading nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            load_ground_truth("/nonexistent/path.json")
