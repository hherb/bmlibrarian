"""
Tests for the citation parser module.

Tests the parsing, manipulation, and validation of citation markers
in the [@id:12345:Label] format.
"""

import pytest
from bmlibrarian.writing.citation_parser import CitationParser
from bmlibrarian.writing.models import Citation


class TestCitationParser:
    """Test suite for CitationParser."""

    @pytest.fixture
    def parser(self) -> CitationParser:
        """Create a CitationParser instance."""
        return CitationParser()

    def test_parse_single_citation(self, parser: CitationParser) -> None:
        """Test parsing a single citation."""
        text = "This is a test [@id:123:Smith2023] with one citation."
        citations = parser.parse_citations(text)

        assert len(citations) == 1
        assert citations[0].document_id == 123
        assert citations[0].label == "Smith2023"
        assert citations[0].text == "[@id:123:Smith2023]"

    def test_parse_multiple_citations(self, parser: CitationParser) -> None:
        """Test parsing multiple citations."""
        text = "Study A [@id:100:Jones2021] and study B [@id:200:Lee2022] agree."
        citations = parser.parse_citations(text)

        assert len(citations) == 2
        assert citations[0].document_id == 100
        assert citations[0].label == "Jones2021"
        assert citations[1].document_id == 200
        assert citations[1].label == "Lee2022"

    def test_parse_no_citations(self, parser: CitationParser) -> None:
        """Test parsing text with no citations."""
        text = "This text has no citations at all."
        citations = parser.parse_citations(text)

        assert len(citations) == 0

    def test_parse_citation_position(self, parser: CitationParser) -> None:
        """Test that citation positions are correct."""
        text = "Text [@id:1:A] more."
        citations = parser.parse_citations(text)

        assert citations[0].position == 5

    def test_get_unique_document_ids(self, parser: CitationParser) -> None:
        """Test getting unique document IDs."""
        text = "[@id:1:A] [@id:2:B] [@id:1:A] [@id:3:C]"
        ids = parser.get_unique_document_ids(text)

        assert ids == [1, 2, 3]

    def test_count_citations(self, parser: CitationParser) -> None:
        """Test counting total citations."""
        text = "[@id:1:A] [@id:2:B] [@id:1:A]"
        count = parser.count_citations(text)

        assert count == 3

    def test_count_unique_citations(self, parser: CitationParser) -> None:
        """Test counting unique citations."""
        text = "[@id:1:A] [@id:2:B] [@id:1:A]"
        count = parser.count_unique_citations(text)

        assert count == 2

    def test_create_citation_marker(self, parser: CitationParser) -> None:
        """Test creating citation markers."""
        marker = parser.create_citation_marker(12345, "Smith2023")

        assert marker == "[@id:12345:Smith2023]"

    def test_replace_citation_with_number(self, parser: CitationParser) -> None:
        """Test replacing a citation with a number."""
        text = "See [@id:123:Smith2023] for details."
        result = parser.replace_citation_with_number(text, 123, 1)

        assert result == "See [1] for details."

    def test_replace_all_citations_with_numbers(self, parser: CitationParser) -> None:
        """Test replacing all citations with numbers."""
        text = "First [@id:1:A], then [@id:2:B], then [@id:1:A] again."
        id_to_number = {1: 1, 2: 2}
        result = parser.replace_all_citations_with_numbers(text, id_to_number)

        assert result == "First [1], then [2], then [1] again."

    def test_get_citation_positions(self, parser: CitationParser) -> None:
        """Test getting positions for each document."""
        text = "[@id:1:A] text [@id:2:B] more [@id:1:A]"
        positions = parser.get_citation_positions(text)

        assert 1 in positions
        assert 2 in positions
        assert len(positions[1]) == 2
        assert len(positions[2]) == 1

    def test_get_citations_in_range(self, parser: CitationParser) -> None:
        """Test getting citations within a range."""
        text = "Start [@id:1:A] middle [@id:2:B] end"
        citations = parser.get_citations_in_range(text, 0, 20)

        assert len(citations) == 1
        assert citations[0].document_id == 1

    def test_find_adjacent_citations(self, parser: CitationParser) -> None:
        """Test finding adjacent citation groups."""
        text = "Text [@id:1:A][@id:2:B] more [@id:3:C]"
        groups = parser.find_adjacent_citations(text)

        assert len(groups) == 2
        assert len(groups[0]) == 2  # First group has 2 adjacent
        assert len(groups[1]) == 1  # Second group has 1

    def test_format_citation_group_simple(self, parser: CitationParser) -> None:
        """Test formatting a citation group without combining."""
        citations = [
            Citation(document_id=1, label="A", position=0, text="[@id:1:A]"),
            Citation(document_id=2, label="B", position=10, text="[@id:2:B]"),
        ]
        id_to_number = {1: 1, 2: 2}
        result = parser.format_citation_group(citations, id_to_number, combine_sequential=False)

        assert result == "[1,2]"

    def test_format_citation_group_sequential(self, parser: CitationParser) -> None:
        """Test formatting sequential citations with combining."""
        citations = [
            Citation(document_id=1, label="A", position=0, text="[@id:1:A]"),
            Citation(document_id=2, label="B", position=10, text="[@id:2:B]"),
            Citation(document_id=3, label="C", position=20, text="[@id:3:C]"),
        ]
        id_to_number = {1: 1, 2: 2, 3: 3}
        result = parser.format_citation_group(citations, id_to_number, combine_sequential=True)

        assert result == "[1-3]"

    def test_validate_citation_valid(self, parser: CitationParser) -> None:
        """Test validating a valid citation."""
        is_valid, error = parser.validate_citation("[@id:123:Smith2023]")

        assert is_valid is True
        assert error is None

    def test_validate_citation_invalid_format(self, parser: CitationParser) -> None:
        """Test validating an invalid citation format."""
        is_valid, error = parser.validate_citation("[id:123:Smith2023]")

        assert is_valid is False
        assert error is not None

    def test_validate_citation_zero_id(self, parser: CitationParser) -> None:
        """Test validating citation with zero ID."""
        is_valid, error = parser.validate_citation("[@id:0:Label]")

        assert is_valid is False

    def test_extract_label_from_citation(self, parser: CitationParser) -> None:
        """Test extracting label from citation."""
        label = parser.extract_label_from_citation("[@id:123:Smith2023]")

        assert label == "Smith2023"

    def test_extract_document_id_from_citation(self, parser: CitationParser) -> None:
        """Test extracting document ID from citation."""
        doc_id = parser.extract_document_id_from_citation("[@id:123:Smith2023]")

        assert doc_id == 123

    def test_complex_label_with_spaces(self, parser: CitationParser) -> None:
        """Test citation with complex label containing spaces."""
        text = "See [@id:456:Smith et al. 2023]."
        citations = parser.parse_citations(text)

        assert len(citations) == 1
        assert citations[0].label == "Smith et al. 2023"

    def test_citation_at_text_boundary(self, parser: CitationParser) -> None:
        """Test citations at start and end of text."""
        text = "[@id:1:A]Text[@id:2:B]"
        citations = parser.parse_citations(text)

        assert len(citations) == 2
        assert citations[0].position == 0
