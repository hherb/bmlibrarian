"""
Unit tests for pubmed_search data types.

Tests the dataclasses and enums used throughout the PubMed search module.
"""

import pytest
from datetime import date, datetime

from bmlibrarian.pubmed_search.data_types import (
    PublicationType,
    SearchStatus,
    MeSHTerm,
    QueryConcept,
    DateRange,
    PubMedQuery,
    SearchResult,
    ArticleMetadata,
    ImportResult,
    SearchSession,
    QueryConversionResult,
)


class TestPublicationType:
    """Tests for PublicationType enum."""

    def test_all_types_have_values(self) -> None:
        """All publication types should have string values."""
        for pt in PublicationType:
            assert isinstance(pt.value, str)
            assert len(pt.value) > 0

    def test_to_pubmed_filter(self) -> None:
        """Test conversion to PubMed filter syntax."""
        rct = PublicationType.RCT
        filter_str = rct.to_pubmed_filter()
        assert "[Publication Type]" in filter_str
        assert "Randomized Controlled Trial" in filter_str

    def test_meta_analysis_filter(self) -> None:
        """Test meta-analysis filter format."""
        ma = PublicationType.META_ANALYSIS
        filter_str = ma.to_pubmed_filter()
        assert '"Meta-Analysis"[Publication Type]' == filter_str


class TestSearchStatus:
    """Tests for SearchStatus enum."""

    def test_all_statuses_exist(self) -> None:
        """Verify all expected statuses exist."""
        expected = {"pending", "in_progress", "completed", "failed", "cancelled"}
        actual = {s.value for s in SearchStatus}
        assert expected == actual


class TestMeSHTerm:
    """Tests for MeSHTerm dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic MeSHTerm creation."""
        term = MeSHTerm(
            descriptor_ui="D006331",
            descriptor_name="Heart Diseases",
        )
        assert term.descriptor_ui == "D006331"
        assert term.descriptor_name == "Heart Diseases"
        assert term.is_valid is True

    def test_to_pubmed_syntax_with_explosion(self) -> None:
        """Test conversion to PubMed syntax with term explosion."""
        term = MeSHTerm(
            descriptor_ui="D002318",
            descriptor_name="Cardiovascular Diseases",
        )
        result = term.to_pubmed_syntax(explode=True)
        assert '"Cardiovascular Diseases"[MeSH Terms]' == result

    def test_to_pubmed_syntax_without_explosion(self) -> None:
        """Test conversion to PubMed syntax without term explosion."""
        term = MeSHTerm(
            descriptor_ui="D002318",
            descriptor_name="Cardiovascular Diseases",
        )
        result = term.to_pubmed_syntax(explode=False)
        assert '"Cardiovascular Diseases"[MeSH Terms:noexp]' == result

    def test_invalid_term(self) -> None:
        """Test creation of invalid term."""
        term = MeSHTerm(
            descriptor_ui="",
            descriptor_name="Invalid Term",
            is_valid=False,
        )
        assert term.is_valid is False


class TestQueryConcept:
    """Tests for QueryConcept dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic QueryConcept creation."""
        concept = QueryConcept(
            name="Exercise",
            mesh_terms=["Exercise", "Physical Activity"],
            keywords=["workout", "physical exercise"],
        )
        assert concept.name == "Exercise"
        assert len(concept.mesh_terms) == 2
        assert len(concept.keywords) == 2

    def test_to_pubmed_clause_with_mesh(self) -> None:
        """Test conversion to PubMed clause with MeSH terms."""
        concept = QueryConcept(
            name="Exercise",
            mesh_terms=["Exercise"],
            keywords=["workout"],
        )
        clause = concept.to_pubmed_clause()
        assert '"Exercise"[MeSH Terms]' in clause
        assert "workout[Title/Abstract]" in clause
        assert " OR " in clause

    def test_to_pubmed_clause_multiword_keyword(self) -> None:
        """Test that multi-word keywords are quoted."""
        concept = QueryConcept(
            name="Age",
            keywords=["older adults", "elderly"],
        )
        clause = concept.to_pubmed_clause()
        assert '"older adults"[Title/Abstract]' in clause
        assert "elderly[Title/Abstract]" in clause

    def test_to_pubmed_clause_empty(self) -> None:
        """Test empty concept returns empty string."""
        concept = QueryConcept(name="Empty")
        clause = concept.to_pubmed_clause()
        assert clause == ""

    def test_pico_component(self) -> None:
        """Test PICO component marking."""
        concept = QueryConcept(
            name="Elderly",
            pico_role="population",
            is_pico_component=True,
        )
        assert concept.is_pico_component is True
        assert concept.pico_role == "population"


class TestDateRange:
    """Tests for DateRange dataclass."""

    def test_to_pubmed_params_both_dates(self) -> None:
        """Test conversion with both start and end dates."""
        dr = DateRange(
            start_date=date(2020, 1, 1),
            end_date=date(2023, 12, 31),
        )
        params = dr.to_pubmed_params()
        assert params["mindate"] == "2020/01/01"
        assert params["maxdate"] == "2023/12/31"
        assert params["datetype"] == "pdat"

    def test_to_pubmed_params_start_only(self) -> None:
        """Test conversion with only start date."""
        dr = DateRange(start_date=date(2020, 1, 1))
        params = dr.to_pubmed_params()
        assert params["mindate"] == "2020/01/01"
        assert "maxdate" not in params

    def test_to_pubmed_params_empty(self) -> None:
        """Test conversion with no dates."""
        dr = DateRange()
        params = dr.to_pubmed_params()
        assert params == {}


class TestPubMedQuery:
    """Tests for PubMedQuery dataclass."""

    def test_basic_creation(self) -> None:
        """Test basic PubMedQuery creation."""
        query = PubMedQuery(
            original_question="What are cardiovascular benefits of exercise?",
            query_string='"Exercise"[MeSH] AND "Cardiovascular"[tiab]',
        )
        assert "exercise" in query.original_question.lower()
        assert "[MeSH]" in query.query_string

    def test_to_url_params(self) -> None:
        """Test conversion to URL parameters."""
        query = PubMedQuery(
            original_question="test",
            query_string='"Exercise"[MeSH]',
            date_range=DateRange(start_date=date(2020, 1, 1)),
        )
        params = query.to_url_params()
        assert params["db"] == "pubmed"
        assert params["term"] == '"Exercise"[MeSH]'
        assert params["mindate"] == "2020/01/01"

    def test_get_search_summary(self) -> None:
        """Test search summary generation."""
        query = PubMedQuery(
            original_question="test question",
            query_string='"Test"[MeSH]',
            humans_only=True,
            has_abstract=True,
        )
        summary = query.get_search_summary()
        assert "test question" in summary
        assert "humans only" in summary
        assert "has abstract" in summary


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_has_more_results_true(self) -> None:
        """Test has_more_results when more are available."""
        query = PubMedQuery(original_question="", query_string="")
        result = SearchResult(
            query=query,
            total_count=1000,
            retrieved_count=100,
        )
        assert result.has_more_results is True

    def test_has_more_results_false(self) -> None:
        """Test has_more_results when all retrieved."""
        query = PubMedQuery(original_question="", query_string="")
        result = SearchResult(
            query=query,
            total_count=50,
            retrieved_count=50,
        )
        assert result.has_more_results is False


class TestArticleMetadata:
    """Tests for ArticleMetadata dataclass."""

    def test_auto_url_generation(self) -> None:
        """Test automatic URL generation from PMID."""
        article = ArticleMetadata(
            pmid="12345678",
            title="Test Article",
        )
        assert article.url == "https://pubmed.ncbi.nlm.nih.gov/12345678/"

    def test_explicit_url(self) -> None:
        """Test that explicit URL is preserved."""
        explicit_url = "https://example.com/article"
        article = ArticleMetadata(
            pmid="12345678",
            title="Test Article",
            url=explicit_url,
        )
        assert article.url == explicit_url


class TestImportResult:
    """Tests for ImportResult dataclass."""

    def test_get_summary(self) -> None:
        """Test summary generation."""
        result = ImportResult(
            total_found=100,
            articles_fetched=100,
            articles_imported=75,
            articles_skipped=20,
            articles_failed=5,
        )
        summary = result.get_summary()
        assert "100" in summary
        assert "75" in summary
        assert "20" in summary
        assert "5" in summary


class TestSearchSession:
    """Tests for SearchSession dataclass."""

    def test_session_id_generated(self) -> None:
        """Test that session_id is auto-generated."""
        session = SearchSession(research_question="test")
        assert session.session_id is not None
        assert len(session.session_id) > 0

    def test_mark_completed(self) -> None:
        """Test marking session as completed."""
        session = SearchSession(research_question="test")
        assert session.status == SearchStatus.PENDING
        session.mark_completed()
        assert session.status == SearchStatus.COMPLETED
        assert session.completed_at is not None

    def test_mark_failed(self) -> None:
        """Test marking session as failed."""
        session = SearchSession(research_question="test")
        session.import_result = ImportResult()
        session.mark_failed("Test error")
        assert session.status == SearchStatus.FAILED
        assert "Test error" in session.import_result.errors


class TestQueryConversionResult:
    """Tests for QueryConversionResult dataclass."""

    def test_get_validation_summary_no_terms(self) -> None:
        """Test validation summary with no MeSH terms."""
        query = PubMedQuery(original_question="", query_string="")
        result = QueryConversionResult(primary_query=query)
        summary = result.get_validation_summary()
        assert "No MeSH terms identified" in summary

    def test_get_validation_summary_with_terms(self) -> None:
        """Test validation summary with MeSH terms."""
        query = PubMedQuery(original_question="", query_string="")
        result = QueryConversionResult(
            primary_query=query,
            mesh_terms_found=["Term1", "Term2", "Term3"],
            mesh_terms_validated=["Term1", "Term2"],
            mesh_terms_invalid=["Term3"],
        )
        summary = result.get_validation_summary()
        assert "2/3 valid" in summary
        assert "1 invalid" in summary
