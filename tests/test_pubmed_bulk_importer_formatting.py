"""
Unit tests for PubMed Bulk Importer formatting enhancements.

Tests the new Markdown formatting capabilities added to pubmed_bulk_importer.py:
- _get_element_text_with_formatting(): Inline formatting conversion
- _format_abstract_markdown(): Structured abstract formatting
"""

import xml.etree.ElementTree as ET
import pytest
from unittest.mock import Mock, patch
from src.bmlibrarian.importers.pubmed_bulk_importer import PubMedBulkImporter


class TestTextFormattingExtraction:
    """Test _get_element_text_with_formatting() method."""

    @pytest.fixture
    def importer(self, tmp_path):
        """Create PubMedBulkImporter instance for testing."""
        # Mock the database manager and source_id lookup
        with patch('src.bmlibrarian.importers.pubmed_bulk_importer.get_db_manager') as mock_db:
            mock_db.return_value = Mock()
            mock_db.return_value.get_connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = [1]
            importer = PubMedBulkImporter(data_dir=str(tmp_path), use_tracking=False)
            return importer

    def test_simple_text_no_formatting(self, importer):
        """Test extraction of plain text without any formatting."""
        xml_str = '<title>Simple text without formatting</title>'
        elem = ET.fromstring(xml_str)
        result = importer._get_element_text_with_formatting(elem)
        assert result == 'Simple text without formatting'

    def test_bold_formatting(self, importer):
        """Test conversion of <b> and <bold> tags to Markdown."""
        # Test <b> tag
        xml_str = '<title>Text with <b>bold</b> word</title>'
        elem = ET.fromstring(xml_str)
        result = importer._get_element_text_with_formatting(elem)
        assert result == 'Text with **bold** word'

        # Test <bold> tag
        xml_str = '<title>Text with <bold>bold</bold> word</title>'
        elem = ET.fromstring(xml_str)
        result = importer._get_element_text_with_formatting(elem)
        assert result == 'Text with **bold** word'

    def test_italic_formatting(self, importer):
        """Test conversion of <i> and <italic> tags to Markdown."""
        # Test <i> tag
        xml_str = '<title>Text with <i>italic</i> word</title>'
        elem = ET.fromstring(xml_str)
        result = importer._get_element_text_with_formatting(elem)
        assert result == 'Text with *italic* word'

        # Test <italic> tag
        xml_str = '<title>Text with <italic>italic</italic> word</title>'
        elem = ET.fromstring(xml_str)
        result = importer._get_element_text_with_formatting(elem)
        assert result == 'Text with *italic* word'

    def test_superscript_formatting(self, importer):
        """Test conversion of <sup> tags to Markdown."""
        xml_str = '<title>Area in m<sup>2</sup> units</title>'
        elem = ET.fromstring(xml_str)
        result = importer._get_element_text_with_formatting(elem)
        assert result == 'Area in m^2^ units'

    def test_subscript_formatting(self, importer):
        """Test conversion of <sub> tags to Markdown."""
        xml_str = '<title>Water molecule H<sub>2</sub>O</title>'
        elem = ET.fromstring(xml_str)
        result = importer._get_element_text_with_formatting(elem)
        assert result == 'Water molecule H~2~O'

    def test_underline_formatting(self, importer):
        """Test conversion of <u> and <underline> tags to Markdown."""
        # Test <u> tag
        xml_str = '<title>Text with <u>underlined</u> word</title>'
        elem = ET.fromstring(xml_str)
        result = importer._get_element_text_with_formatting(elem)
        assert result == 'Text with __underlined__ word'

        # Test <underline> tag
        xml_str = '<title>Text with <underline>underlined</underline> word</title>'
        elem = ET.fromstring(xml_str)
        result = importer._get_element_text_with_formatting(elem)
        assert result == 'Text with __underlined__ word'

    def test_nested_formatting(self, importer):
        """Test nested formatting tags."""
        xml_str = '<title>Text with <b><i>bold italic</i></b> words</title>'
        elem = ET.fromstring(xml_str)
        result = importer._get_element_text_with_formatting(elem)
        assert result == 'Text with ***bold italic*** words'

    def test_multiple_formatting_elements(self, importer):
        """Test multiple different formatting elements in one string."""
        xml_str = '<title>CO<sub>2</sub> levels and m<sup>2</sup> with <b>bold</b> text</title>'
        elem = ET.fromstring(xml_str)
        result = importer._get_element_text_with_formatting(elem)
        assert result == 'CO~2~ levels and m^2^ with **bold** text'

    def test_unknown_tag(self, importer):
        """Test that unknown tags preserve their text content."""
        xml_str = '<title>Text with <unknown>content</unknown> preserved</title>'
        elem = ET.fromstring(xml_str)
        result = importer._get_element_text_with_formatting(elem)
        assert result == 'Text with content preserved'

    def test_empty_element(self, importer):
        """Test handling of empty elements."""
        result = importer._get_element_text_with_formatting(None)
        assert result == ''

    def test_element_with_tail_text(self, importer):
        """Test elements with tail text after closing tags."""
        xml_str = '<title>Before <b>bold</b> after <i>italic</i> end</title>'
        elem = ET.fromstring(xml_str)
        result = importer._get_element_text_with_formatting(elem)
        assert result == 'Before **bold** after *italic* end'

    def test_scientific_notation_example(self, importer):
        """Test real-world scientific notation example."""
        xml_str = '''<title>
            Effect of γ-tocotrienol in acetaminophen-induced liver injury:
            measurement in CO<sub>2</sub> over 25m<sup>2</sup> area
        </title>'''
        elem = ET.fromstring(xml_str)
        result = importer._get_element_text_with_formatting(elem)
        assert 'CO~2~' in result
        assert '25m^2^' in result


class TestAbstractMarkdownFormatting:
    """Test _format_abstract_markdown() method."""

    @pytest.fixture
    def importer(self, tmp_path):
        """Create PubMedBulkImporter instance for testing."""
        # Mock the database manager and source_id lookup
        with patch('src.bmlibrarian.importers.pubmed_bulk_importer.get_db_manager') as mock_db:
            mock_db.return_value = Mock()
            mock_db.return_value.get_connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = [1]
            importer = PubMedBulkImporter(data_dir=str(tmp_path), use_tracking=False)
            return importer

    def test_unstructured_abstract(self, importer):
        """Test formatting of unstructured abstract (no labels)."""
        xml_str = '''<Abstract>
            <AbstractText>This is a simple unstructured abstract without section labels.</AbstractText>
        </Abstract>'''
        elem = ET.fromstring(xml_str)
        result = importer._format_abstract_markdown(elem)
        assert result == 'This is a simple unstructured abstract without section labels.'

    def test_structured_abstract_with_label(self, importer):
        """Test formatting of structured abstract with Label attributes."""
        xml_str = '''<Abstract>
            <AbstractText Label="OBJECTIVE">To study the effects of treatment.</AbstractText>
            <AbstractText Label="METHODS">We conducted a randomized trial.</AbstractText>
            <AbstractText Label="RESULTS">Treatment showed significant improvement.</AbstractText>
            <AbstractText Label="CONCLUSIONS">This treatment is effective.</AbstractText>
        </Abstract>'''
        elem = ET.fromstring(xml_str)
        result = importer._format_abstract_markdown(elem)

        assert '**OBJECTIVE:** To study the effects of treatment.' in result
        assert '**METHODS:** We conducted a randomized trial.' in result
        assert '**RESULTS:** Treatment showed significant improvement.' in result
        assert '**CONCLUSIONS:** This treatment is effective.' in result
        assert '\n\n' in result  # Check for paragraph breaks

    def test_structured_abstract_with_nlmcategory(self, importer):
        """Test formatting with NlmCategory attribute as fallback."""
        xml_str = '''<Abstract>
            <AbstractText NlmCategory="BACKGROUND">Background information here.</AbstractText>
            <AbstractText NlmCategory="METHODS">Methods information here.</AbstractText>
        </Abstract>'''
        elem = ET.fromstring(xml_str)
        result = importer._format_abstract_markdown(elem)

        assert '**BACKGROUND:** Background information here.' in result
        assert '**METHODS:** Methods information here.' in result

    def test_nlmcategory_unassigned_filtered(self, importer):
        """Test that UNASSIGNED and UNLABELLED categories are filtered out."""
        xml_str = '''<Abstract>
            <AbstractText NlmCategory="UNASSIGNED">This should have no label.</AbstractText>
            <AbstractText NlmCategory="UNLABELLED">This should also have no label.</AbstractText>
        </Abstract>'''
        elem = ET.fromstring(xml_str)
        result = importer._format_abstract_markdown(elem)

        assert '**UNASSIGNED:**' not in result
        assert '**UNLABELLED:**' not in result
        assert 'This should have no label.' in result
        assert 'This should also have no label.' in result

    def test_label_preferred_over_nlmcategory(self, importer):
        """Test that Label attribute takes precedence over NlmCategory."""
        xml_str = '''<Abstract>
            <AbstractText Label="OBJECTIVE" NlmCategory="BACKGROUND">Should use OBJECTIVE.</AbstractText>
        </Abstract>'''
        elem = ET.fromstring(xml_str)
        result = importer._format_abstract_markdown(elem)

        assert '**OBJECTIVE:**' in result
        assert '**BACKGROUND:**' not in result

    def test_abstract_with_inline_formatting(self, importer):
        """Test abstract with inline formatting preserved."""
        xml_str = '''<Abstract>
            <AbstractText Label="RESULTS">
                CO<sub>2</sub> levels increased by 25% in <b>treated</b> group.
            </AbstractText>
        </Abstract>'''
        elem = ET.fromstring(xml_str)
        result = importer._format_abstract_markdown(elem)

        assert '**RESULTS:**' in result
        assert 'CO~2~' in result
        assert '**treated**' in result

    def test_mixed_labeled_unlabeled_sections(self, importer):
        """Test abstract with mix of labeled and unlabeled sections."""
        xml_str = '''<Abstract>
            <AbstractText Label="BACKGROUND">Background text here.</AbstractText>
            <AbstractText>Unlabeled middle section.</AbstractText>
            <AbstractText Label="CONCLUSIONS">Conclusions here.</AbstractText>
        </Abstract>'''
        elem = ET.fromstring(xml_str)
        result = importer._format_abstract_markdown(elem)

        assert '**BACKGROUND:**' in result
        assert 'Unlabeled middle section.' in result
        assert '**CONCLUSIONS:**' in result

    def test_empty_abstract(self, importer):
        """Test handling of empty abstract."""
        result = importer._format_abstract_markdown(None)
        assert result == ''

    def test_abstract_without_abstracttext_elements(self, importer):
        """Test abstract element without any AbstractText children."""
        xml_str = '<Abstract></Abstract>'
        elem = ET.fromstring(xml_str)
        result = importer._format_abstract_markdown(elem)
        assert result == ''

    def test_paragraph_breaks_between_sections(self, importer):
        """Test that sections are separated by double newlines."""
        xml_str = '''<Abstract>
            <AbstractText Label="BACKGROUND">Section one.</AbstractText>
            <AbstractText Label="METHODS">Section two.</AbstractText>
            <AbstractText Label="RESULTS">Section three.</AbstractText>
        </Abstract>'''
        elem = ET.fromstring(xml_str)
        result = importer._format_abstract_markdown(elem)

        # Should have 2 paragraph breaks for 3 sections
        assert result.count('\n\n') == 2

    def test_real_world_structured_abstract(self, importer):
        """Test a realistic structured abstract example."""
        xml_str = '''<Abstract>
            <AbstractText Label="BACKGROUND" NlmCategory="BACKGROUND">
                Acetaminophen (APAP) overdose is the most common cause of acute liver
                failure in the Western world.
            </AbstractText>
            <AbstractText Label="OBJECTIVE" NlmCategory="OBJECTIVE">
                We examined the protective effect of γ-tocotrienol (γ-T<sub>3</sub>),
                a member of the vitamin E family, against APAP overdose-induced liver
                injury in mice.
            </AbstractText>
            <AbstractText Label="METHODS" NlmCategory="METHODS">
                Male C57BL/6 mice were pretreated with γ-T<sub>3</sub> or vehicle.
            </AbstractText>
            <AbstractText Label="RESULTS" NlmCategory="RESULTS">
                γ-T<sub>3</sub> pretreatment <b>significantly</b> reduced liver injury.
            </AbstractText>
            <AbstractText Label="CONCLUSIONS" NlmCategory="CONCLUSIONS">
                γ-T<sub>3</sub> protects against APAP-induced liver injury.
            </AbstractText>
        </Abstract>'''
        elem = ET.fromstring(xml_str)
        result = importer._format_abstract_markdown(elem)

        # Check labels
        assert '**BACKGROUND:**' in result
        assert '**OBJECTIVE:**' in result
        assert '**METHODS:**' in result
        assert '**RESULTS:**' in result
        assert '**CONCLUSIONS:**' in result

        # Check inline formatting
        assert 'γ-T~3~' in result
        assert '**significantly**' in result

        # Check paragraph breaks
        assert '\n\n' in result


class TestMemoryManagement:
    """Test that memory management fix doesn't cause errors."""

    @pytest.fixture
    def importer(self, tmp_path):
        """Create PubMedBulkImporter instance for testing."""
        # Mock the database manager and source_id lookup
        with patch('src.bmlibrarian.importers.pubmed_bulk_importer.get_db_manager') as mock_db:
            mock_db.return_value = Mock()
            mock_db.return_value.get_connection.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value.fetchone.return_value = [1]
            importer = PubMedBulkImporter(data_dir=str(tmp_path), use_tracking=False)
            return importer

    def test_elem_clear_works(self, importer):
        """Test that elem.clear() works without AttributeError."""
        xml_str = '''<PubmedArticle>
            <MedlineCitation>
                <PMID>12345678</PMID>
                <Article>
                    <ArticleTitle>Test Title</ArticleTitle>
                </Article>
            </MedlineCitation>
        </PubmedArticle>'''
        elem = ET.fromstring(xml_str)

        # This should not raise AttributeError
        elem.clear()

        # After clearing, element should be empty
        assert len(list(elem)) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
