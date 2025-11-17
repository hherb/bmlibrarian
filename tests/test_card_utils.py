"""
Unit tests for document and citation card utilities.

Tests formatting functions, type validation, and data normalization.
"""

import pytest
import sys
import os
from importlib.util import spec_from_file_location, module_from_spec

# Directly load the card_utils module to avoid PySide6 imports
module_path = os.path.join(
    os.path.dirname(__file__),
    '..',
    'src',
    'bmlibrarian',
    'gui',
    'qt',
    'widgets',
    'card_utils.py'
)

spec = spec_from_file_location("card_utils", module_path)
card_utils = module_from_spec(spec)
spec.loader.exec_module(card_utils)

# Import functions from the loaded module
validate_document_data = card_utils.validate_document_data
validate_citation_data = card_utils.validate_citation_data
extract_year = card_utils.extract_year
format_authors = card_utils.format_authors
format_journal_year = card_utils.format_journal_year
format_document_ids = card_utils.format_document_ids
truncate_text = card_utils.truncate_text
html_escape = card_utils.html_escape
format_relevance_score = card_utils.format_relevance_score


class TestValidateDocumentData:
    """Test document data validation."""

    def test_valid_document_data(self):
        """Test validation with valid document data."""
        data = {
            "title": "Test Document",
            "authors": ["Smith J", "Jones A"],
            "journal": "Nature",
            "year": 2023
        }
        result = validate_document_data(data)
        assert result == data

    def test_minimal_document_data(self):
        """Test validation with minimal required fields."""
        data = {"title": "Test"}
        result = validate_document_data(data)
        assert result == data

        data2 = {"document_id": 123}
        result2 = validate_document_data(data2)
        assert result2 == data2

    def test_invalid_type(self):
        """Test validation with invalid type."""
        with pytest.raises(TypeError):
            validate_document_data("not a dict")

        with pytest.raises(TypeError):
            validate_document_data([1, 2, 3])

    def test_missing_required_fields(self):
        """Test validation with missing required fields."""
        with pytest.raises(ValueError):
            validate_document_data({})

        with pytest.raises(ValueError):
            validate_document_data({"authors": ["Smith J"]})


class TestValidateCitationData:
    """Test citation data validation."""

    def test_valid_citation_data(self):
        """Test validation with valid citation data."""
        data = {
            "title": "Test Citation",
            "authors": ["Smith J"],
            "passage": "This is a passage.",
            "year": 2023
        }
        result = validate_citation_data(data)
        assert result == data

    def test_quote_instead_of_passage(self):
        """Test validation with quote field instead of passage."""
        data = {
            "title": "Test Citation",
            "quote": "This is a quote."
        }
        result = validate_citation_data(data)
        assert result == data

    def test_invalid_type(self):
        """Test validation with invalid type."""
        with pytest.raises(TypeError):
            validate_citation_data("not a dict")

    def test_missing_title(self):
        """Test validation with missing title."""
        with pytest.raises(ValueError):
            validate_citation_data({"passage": "text"})

    def test_missing_passage_and_quote(self):
        """Test validation with missing passage and quote."""
        with pytest.raises(ValueError):
            validate_citation_data({"title": "Test"})


class TestExtractYear:
    """Test year extraction function."""

    def test_integer_year(self):
        """Test with integer year."""
        assert extract_year(2023) == "2023"
        assert extract_year(1999) == "1999"
        assert extract_year(2000) == "2000"

    def test_string_year(self):
        """Test with string year."""
        assert extract_year("2023") == "2023"
        assert extract_year("1999") == "1999"

    def test_date_string(self):
        """Test with date string."""
        assert extract_year("2023-01-15") == "2023"
        assert extract_year("2023-12-31") == "2023"
        assert extract_year("1999-06-15") == "1999"

    def test_year_in_text(self):
        """Test with year embedded in text."""
        assert extract_year("Published in 2023") == "2023"
        assert extract_year("(2023)") == "2023"

    def test_none_and_empty(self):
        """Test with None and empty values."""
        assert extract_year(None) == ""
        assert extract_year("") == ""
        assert extract_year("unknown") == ""


class TestFormatAuthors:
    """Test author formatting function."""

    def test_author_list(self):
        """Test with list of authors."""
        authors = ["Smith J", "Jones A", "Brown B"]
        assert format_authors(authors, max_authors=3) == "Smith J, Jones A, Brown B"

    def test_author_list_with_truncation(self):
        """Test with truncated author list."""
        authors = ["Smith J", "Jones A", "Brown B", "Davis C"]
        result = format_authors(authors, max_authors=2)
        assert result == "Smith J, Jones A et al."

    def test_author_list_no_et_al(self):
        """Test with truncation but no et al."""
        authors = ["Smith J", "Jones A", "Brown B"]
        result = format_authors(authors, max_authors=2, et_al=False)
        assert result == "Smith J, Jones A"

    def test_author_string(self):
        """Test with author string."""
        authors = "Smith J, Jones A"
        assert format_authors(authors) == "Smith J, Jones A"

    def test_empty_author_list(self):
        """Test with empty author list."""
        assert format_authors([]) == "Unknown authors"
        assert format_authors(None) == "Unknown authors"

    def test_single_author(self):
        """Test with single author."""
        assert format_authors(["Smith J"]) == "Smith J"


class TestFormatJournalYear:
    """Test journal and year formatting."""

    def test_journal_and_year(self):
        """Test with both journal and year."""
        assert format_journal_year("Nature", 2023) == "Nature (2023)"
        assert format_journal_year("Science", "2023") == "Science (2023)"

    def test_journal_only(self):
        """Test with journal only."""
        assert format_journal_year("Nature", None) == "Nature"

    def test_year_only(self):
        """Test with year only."""
        assert format_journal_year(None, 2023) == "(2023)"

    def test_neither(self):
        """Test with neither journal nor year."""
        assert format_journal_year(None, None) == ""

    def test_year_extraction(self):
        """Test with year that needs extraction."""
        assert format_journal_year("Nature", "2023-01-15") == "Nature (2023)"


class TestFormatDocumentIds:
    """Test document ID formatting."""

    def test_pmid_and_doi(self):
        """Test with both PMID and DOI."""
        result = format_document_ids(pmid=12345678, doi="10.1234/example")
        assert result == "PMID: 12345678 | DOI: 10.1234/example"

    def test_pmid_only(self):
        """Test with PMID only."""
        assert format_document_ids(pmid=12345678) == "PMID: 12345678"

    def test_doi_only(self):
        """Test with DOI only."""
        assert format_document_ids(doi="10.1234/example") == "DOI: 10.1234/example"

    def test_doc_id_without_pmid(self):
        """Test with internal doc ID when no PMID."""
        assert format_document_ids(doc_id=123) == "ID: 123"

    def test_doc_id_with_pmid(self):
        """Test that doc ID is hidden when PMID is present."""
        result = format_document_ids(pmid=87654321, doc_id=999)
        # Should only show PMID, not the internal doc ID
        assert result == "PMID: 87654321"

    def test_custom_separator(self):
        """Test with custom separator."""
        result = format_document_ids(
            pmid=12345678,
            doi="10.1234/example",
            separator=" / "
        )
        assert result == "PMID: 12345678 / DOI: 10.1234/example"

    def test_no_ids(self):
        """Test with no IDs."""
        assert format_document_ids() == ""


class TestTruncateText:
    """Test text truncation function."""

    def test_short_text(self):
        """Test with text shorter than max length."""
        text = "Short text"
        assert truncate_text(text, max_length=100) == text

    def test_long_text(self):
        """Test with text longer than max length."""
        text = "This is a very long text that needs to be truncated"
        result = truncate_text(text, max_length=20)
        assert len(result) == 20
        assert result.endswith("...")

    def test_custom_suffix(self):
        """Test with custom suffix."""
        text = "This is a very long text"
        result = truncate_text(text, max_length=15, suffix="…")
        assert result.endswith("…")
        assert len(result) == 15

    def test_empty_text(self):
        """Test with empty text."""
        assert truncate_text("") == ""
        assert truncate_text(None) == None


class TestHtmlEscape:
    """Test HTML escaping function."""

    def test_special_characters(self):
        """Test escaping of special HTML characters."""
        assert html_escape("<script>") == "&lt;script&gt;"
        assert html_escape("A & B") == "A &amp; B"
        assert html_escape('"quoted"') == "&quot;quoted&quot;"
        assert html_escape("'single'") == "&#39;single&#39;"

    def test_normal_text(self):
        """Test with normal text."""
        text = "Normal text without special characters"
        assert html_escape(text) == text

    def test_empty_text(self):
        """Test with empty text."""
        assert html_escape("") == ""
        assert html_escape(None) == ""


class TestFormatRelevanceScore:
    """Test relevance score formatting."""

    def test_valid_score(self):
        """Test with valid score."""
        assert format_relevance_score(4.5) == "Relevance Score: 4.5/5"
        assert format_relevance_score(3.0) == "Relevance Score: 3.0/5"
        assert format_relevance_score(1.2) == "Relevance Score: 1.2/5"

    def test_custom_max_score(self):
        """Test with custom max score."""
        result = format_relevance_score(7.5, max_score=10.0)
        assert result == "Relevance Score: 7.5/10"

    def test_none_score(self):
        """Test with None score."""
        assert format_relevance_score(None) == ""

    def test_edge_cases(self):
        """Test with edge case scores."""
        assert format_relevance_score(0.0) == "Relevance Score: 0.0/5"
        assert format_relevance_score(5.0) == "Relevance Score: 5.0/5"
