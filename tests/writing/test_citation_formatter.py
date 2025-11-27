"""
Tests for the citation formatter module.

Tests formatting of bibliographic references in different citation styles
(Vancouver, APA, Harvard, Chicago).
"""

import pytest
from bmlibrarian.writing.citation_formatter import (
    CitationFormatter, VancouverFormatter, APAFormatter,
    HarvardFormatter, ChicagoFormatter
)
from bmlibrarian.writing.models import DocumentMetadata, FormattedReference, CitationStyle


@pytest.fixture
def sample_metadata() -> DocumentMetadata:
    """Create sample document metadata for testing."""
    return DocumentMetadata(
        document_id=12345,
        title="Effects of Exercise on Cardiovascular Health",
        authors=["Smith, John", "Johnson, Anna", "Williams, Brian"],
        journal="Journal of Medicine",
        year=2023,
        volume="45",
        issue="2",
        pages="123-134",
        doi="10.1234/example.12345",
        pmid="12345678"
    )


@pytest.fixture
def single_author_metadata() -> DocumentMetadata:
    """Create metadata with single author."""
    return DocumentMetadata(
        document_id=1,
        title="A Solo Study",
        authors=["Brown, Alice"],
        journal="Science Journal",
        year=2022,
        volume="10",
        pages="1-10"
    )


@pytest.fixture
def no_optional_fields_metadata() -> DocumentMetadata:
    """Create metadata with minimal fields."""
    return DocumentMetadata(
        document_id=2,
        title="Minimal Study",
        authors=["Unknown"]
    )


class TestVancouverFormatter:
    """Test suite for Vancouver citation style."""

    @pytest.fixture
    def formatter(self) -> VancouverFormatter:
        """Create a VancouverFormatter instance."""
        return VancouverFormatter()

    def test_format_reference_basic(
        self,
        formatter: VancouverFormatter,
        sample_metadata: DocumentMetadata
    ) -> None:
        """Test basic reference formatting."""
        result = formatter.format_reference(sample_metadata, number=1)

        assert "1." in result
        assert "Smith" in result
        assert "Effects of Exercise on Cardiovascular Health" in result
        assert "Journal of Medicine" in result
        assert "2023" in result

    def test_format_reference_with_doi(
        self,
        formatter: VancouverFormatter,
        sample_metadata: DocumentMetadata
    ) -> None:
        """Test that DOI is included."""
        result = formatter.format_reference(sample_metadata, number=1)

        assert "doi:10.1234/example.12345" in result

    def test_format_inline_citation(
        self,
        formatter: VancouverFormatter,
        sample_metadata: DocumentMetadata
    ) -> None:
        """Test inline citation format."""
        result = formatter.format_inline_citation(sample_metadata, number=5)

        assert result == "[5]"

    def test_format_author_with_et_al(self, formatter: VancouverFormatter) -> None:
        """Test author formatting with many authors."""
        metadata = DocumentMetadata(
            document_id=1,
            title="Big Study",
            authors=[f"Author{i}, Name" for i in range(10)],
            year=2023
        )
        result = formatter.format_reference(metadata, number=1)

        assert "et al" in result


class TestAPAFormatter:
    """Test suite for APA citation style."""

    @pytest.fixture
    def formatter(self) -> APAFormatter:
        """Create an APAFormatter instance."""
        return APAFormatter()

    def test_format_reference_basic(
        self,
        formatter: APAFormatter,
        sample_metadata: DocumentMetadata
    ) -> None:
        """Test basic reference formatting."""
        result = formatter.format_reference(sample_metadata)

        assert "(2023)" in result
        assert "Smith" in result
        assert "Effects of Exercise on Cardiovascular Health" in result

    def test_format_inline_citation_single_author(
        self,
        formatter: APAFormatter,
        single_author_metadata: DocumentMetadata
    ) -> None:
        """Test inline citation with single author."""
        result = formatter.format_inline_citation(single_author_metadata)

        assert result == "(Brown, 2022)"

    def test_format_inline_citation_two_authors(
        self,
        formatter: APAFormatter
    ) -> None:
        """Test inline citation with two authors."""
        metadata = DocumentMetadata(
            document_id=1,
            title="Test",
            authors=["Smith, John", "Jones, Mary"],
            year=2023
        )
        result = formatter.format_inline_citation(metadata)

        assert "&" in result
        assert "Smith" in result
        assert "Jones" in result

    def test_format_inline_citation_many_authors(
        self,
        formatter: APAFormatter,
        sample_metadata: DocumentMetadata
    ) -> None:
        """Test inline citation with many authors uses et al."""
        result = formatter.format_inline_citation(sample_metadata)

        assert "et al." in result
        assert "Smith" in result


class TestHarvardFormatter:
    """Test suite for Harvard citation style."""

    @pytest.fixture
    def formatter(self) -> HarvardFormatter:
        """Create a HarvardFormatter instance."""
        return HarvardFormatter()

    def test_format_reference_has_quotes(
        self,
        formatter: HarvardFormatter,
        sample_metadata: DocumentMetadata
    ) -> None:
        """Test that Harvard style uses quotes around title."""
        result = formatter.format_reference(sample_metadata)

        assert "'" in result  # Harvard uses single quotes

    def test_format_inline_citation_two_authors(
        self,
        formatter: HarvardFormatter
    ) -> None:
        """Test inline citation with two authors uses 'and'."""
        metadata = DocumentMetadata(
            document_id=1,
            title="Test",
            authors=["Smith, John", "Jones, Mary"],
            year=2023
        )
        result = formatter.format_inline_citation(metadata)

        # Harvard uses 'and' instead of '&'
        assert "and" in result or "&" not in result


class TestChicagoFormatter:
    """Test suite for Chicago citation style."""

    @pytest.fixture
    def formatter(self) -> ChicagoFormatter:
        """Create a ChicagoFormatter instance."""
        return ChicagoFormatter()

    def test_format_reference_basic(
        self,
        formatter: ChicagoFormatter,
        sample_metadata: DocumentMetadata
    ) -> None:
        """Test basic reference formatting."""
        result = formatter.format_reference(sample_metadata)

        assert "2023" in result
        assert "Smith" in result
        assert '"' in result  # Chicago uses double quotes

    def test_format_inline_citation(
        self,
        formatter: ChicagoFormatter,
        sample_metadata: DocumentMetadata
    ) -> None:
        """Test inline citation format."""
        result = formatter.format_inline_citation(sample_metadata)

        # Chicago author-date style doesn't use comma between author and year
        assert "Smith" in result
        assert "2023" in result


class TestCitationFormatter:
    """Test suite for the main CitationFormatter class."""

    def test_default_style_is_vancouver(self) -> None:
        """Test that default style is Vancouver."""
        formatter = CitationFormatter()

        assert formatter.style == CitationStyle.VANCOUVER

    def test_style_can_be_changed(self) -> None:
        """Test that style can be changed."""
        formatter = CitationFormatter(CitationStyle.VANCOUVER)
        formatter.style = CitationStyle.APA

        assert formatter.style == CitationStyle.APA

    def test_get_available_styles(self) -> None:
        """Test getting available citation styles."""
        styles = CitationFormatter.get_available_styles()

        assert CitationStyle.VANCOUVER in styles
        assert CitationStyle.APA in styles
        assert CitationStyle.HARVARD in styles
        assert CitationStyle.CHICAGO in styles

    def test_get_style_description(self) -> None:
        """Test getting style descriptions."""
        desc = CitationFormatter.get_style_description(CitationStyle.VANCOUVER)

        assert "Vancouver" in desc
        assert "medical" in desc.lower() or "numbered" in desc.lower()

    def test_format_reference_list(
        self,
        sample_metadata: DocumentMetadata
    ) -> None:
        """Test formatting a complete reference list."""
        formatter = CitationFormatter()
        references = [
            FormattedReference(
                number=1,
                document_id=sample_metadata.document_id,
                formatted_text="1. Smith J, et al. Title. Journal. 2023.",
                metadata=sample_metadata
            ),
            FormattedReference(
                number=2,
                document_id=999,
                formatted_text="2. Jones A. Another Title. Journal. 2022.",
                metadata=None
            )
        ]

        result = formatter.format_reference_list(references)

        assert "## References" in result
        assert "1. Smith" in result
        assert "2. Jones" in result


class TestDocumentMetadataHelpers:
    """Test DocumentMetadata helper methods."""

    def test_get_first_author_surname_comma_format(self) -> None:
        """Test extracting surname from 'Surname, Firstname' format."""
        metadata = DocumentMetadata(
            document_id=1,
            title="Test",
            authors=["Smith, John"]
        )

        assert metadata.get_first_author_surname() == "Smith"

    def test_get_first_author_surname_space_format(self) -> None:
        """Test extracting surname from 'Firstname Surname' format."""
        metadata = DocumentMetadata(
            document_id=1,
            title="Test",
            authors=["John Smith"]
        )

        assert metadata.get_first_author_surname() == "Smith"

    def test_get_first_author_surname_no_authors(self) -> None:
        """Test extracting surname with no authors."""
        metadata = DocumentMetadata(
            document_id=1,
            title="Test",
            authors=[]
        )

        assert metadata.get_first_author_surname() == "Unknown"

    def test_generate_label(self) -> None:
        """Test generating citation label."""
        metadata = DocumentMetadata(
            document_id=1,
            title="Test",
            authors=["Smith, John"],
            year=2023
        )

        assert metadata.generate_label() == "Smith2023"

    def test_generate_label_no_year(self) -> None:
        """Test generating label without year."""
        metadata = DocumentMetadata(
            document_id=1,
            title="Test",
            authors=["Smith, John"]
        )

        assert metadata.generate_label() == "Smithn.d."

    def test_from_dict(self) -> None:
        """Test creating metadata from dictionary."""
        data = {
            'id': 123,
            'title': 'Test Title',
            'authors': ['Author One', 'Author Two'],
            'year': 2023,
            'journal': 'Test Journal'
        }

        metadata = DocumentMetadata.from_dict(data)

        assert metadata.document_id == 123
        assert metadata.title == 'Test Title'
        assert len(metadata.authors) == 2
        assert metadata.year == 2023

    def test_from_dict_with_string_authors(self) -> None:
        """Test creating metadata from dict with authors as string."""
        data = {
            'id': 123,
            'title': 'Test',
            'authors': 'Smith, John; Jones, Mary'
        }

        metadata = DocumentMetadata.from_dict(data)

        assert len(metadata.authors) == 2
        assert 'Smith' in metadata.authors[0]
