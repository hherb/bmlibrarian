"""
Test PDF Export Module

Tests the PDF exporter functionality with various markdown content types.
"""

import tempfile
from pathlib import Path

import pytest

from bmlibrarian.exporters import PDFExporter, PDFExportConfig, PDFExportError
from reportlab.lib.pagesizes import A4, letter


class TestPDFExporter:
    """Test suite for PDF export functionality"""

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary directory for test outputs"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def basic_markdown(self):
        """Sample markdown content"""
        return """
# Research Report

## Summary
This is a test research report with various markdown features.

## Methods
We analyzed the following:
- Item 1
- Item 2
- Item 3

## Results
Our findings include:

1. First finding
2. Second finding
3. Third finding

## Data Table

| Study | Sample Size | Effect Size |
|-------|-------------|-------------|
| Smith 2023 | 1,000 | 0.45 |
| Jones 2024 | 500 | 0.38 |

## Code Example

```python
def example():
    return "Hello, World!"
```

## Conclusion
This demonstrates **bold text**, *italic text*, and `inline code`.

> This is a blockquote with important information.

For more information, see [this link](https://example.com).
"""

    def test_basic_export(self, basic_markdown, temp_output_dir):
        """Test basic PDF export"""
        exporter = PDFExporter()
        output_path = temp_output_dir / "test_report.pdf"

        result = exporter.markdown_to_pdf(
            markdown_content=basic_markdown,
            output_path=output_path
        )

        assert result.exists()
        assert result.stat().st_size > 0
        assert result.suffix == '.pdf'

    def test_export_with_metadata(self, basic_markdown, temp_output_dir):
        """Test PDF export with custom metadata"""
        exporter = PDFExporter()
        output_path = temp_output_dir / "test_with_metadata.pdf"

        metadata = {
            'title': 'Test Research Report',
            'author': 'Test Author',
            'subject': 'Medical Research',
            'keywords': ['test', 'medical', 'research']
        }

        result = exporter.markdown_to_pdf(
            markdown_content=basic_markdown,
            output_path=output_path,
            metadata=metadata
        )

        assert result.exists()
        assert result.stat().st_size > 0

    def test_custom_configuration(self, basic_markdown, temp_output_dir):
        """Test PDF export with custom configuration"""
        config = PDFExportConfig(
            page_size=A4,
            base_font_size=12,
            include_page_numbers=True,
            include_timestamp=True
        )

        exporter = PDFExporter(config)
        output_path = temp_output_dir / "test_custom_config.pdf"

        result = exporter.markdown_to_pdf(
            markdown_content=basic_markdown,
            output_path=output_path
        )

        assert result.exists()
        assert result.stat().st_size > 0

    def test_research_report_export(self, basic_markdown, temp_output_dir):
        """Test BMLibrarian research report export"""
        exporter = PDFExporter()
        output_path = temp_output_dir / "test_research_report.pdf"

        result = exporter.export_report(
            report_content=basic_markdown,
            output_path=output_path,
            research_question="What are the effects of exercise?",
            citation_count=25,
            document_count=100
        )

        assert result.exists()
        assert result.stat().st_size > 0

    def test_empty_markdown(self, temp_output_dir):
        """Test export with empty markdown"""
        exporter = PDFExporter()
        output_path = temp_output_dir / "test_empty.pdf"

        result = exporter.markdown_to_pdf(
            markdown_content="",
            output_path=output_path
        )

        assert result.exists()
        # Should still create a valid PDF, even if minimal
        assert result.stat().st_size > 0

    def test_markdown_with_headings(self, temp_output_dir):
        """Test various heading levels"""
        markdown = """
# Heading 1
## Heading 2
### Heading 3
#### Heading 4

Some content under headings.
"""
        exporter = PDFExporter()
        output_path = temp_output_dir / "test_headings.pdf"

        result = exporter.markdown_to_pdf(
            markdown_content=markdown,
            output_path=output_path
        )

        assert result.exists()
        assert result.stat().st_size > 0

    def test_markdown_with_lists(self, temp_output_dir):
        """Test bullet and numbered lists"""
        markdown = """
## Bullet List
- First item
- Second item
- Third item

## Numbered List
1. First item
2. Second item
3. Third item

## Nested List
- Item 1
  - Nested 1a
  - Nested 1b
- Item 2
"""
        exporter = PDFExporter()
        output_path = temp_output_dir / "test_lists.pdf"

        result = exporter.markdown_to_pdf(
            markdown_content=markdown,
            output_path=output_path
        )

        assert result.exists()
        assert result.stat().st_size > 0

    def test_markdown_with_code_blocks(self, temp_output_dir):
        """Test code block rendering"""
        markdown = """
## Python Code

```python
def hello_world():
    print("Hello, World!")
    return True
```

## SQL Code

```sql
SELECT * FROM documents
WHERE year > 2020;
```
"""
        exporter = PDFExporter()
        output_path = temp_output_dir / "test_code.pdf"

        result = exporter.markdown_to_pdf(
            markdown_content=markdown,
            output_path=output_path
        )

        assert result.exists()
        assert result.stat().st_size > 0

    def test_markdown_with_tables(self, temp_output_dir):
        """Test table rendering"""
        markdown = """
## Data Table

| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| A1       | B1       | C1       |
| A2       | B2       | C2       |
| A3       | B3       | C3       |
"""
        exporter = PDFExporter()
        output_path = temp_output_dir / "test_tables.pdf"

        result = exporter.markdown_to_pdf(
            markdown_content=markdown,
            output_path=output_path
        )

        assert result.exists()
        assert result.stat().st_size > 0

    def test_invalid_output_path(self, basic_markdown):
        """Test error handling for invalid output path"""
        exporter = PDFExporter()
        # Try to write to a directory that doesn't exist and can't be created
        output_path = Path("/invalid/path/that/does/not/exist/test.pdf")

        with pytest.raises(PDFExportError):
            exporter.markdown_to_pdf(
                markdown_content=basic_markdown,
                output_path=output_path
            )

    def test_output_directory_creation(self, basic_markdown, temp_output_dir):
        """Test that output directories are created automatically"""
        exporter = PDFExporter()
        # Use nested directory that doesn't exist yet
        output_path = temp_output_dir / "subdir1" / "subdir2" / "test.pdf"

        result = exporter.markdown_to_pdf(
            markdown_content=basic_markdown,
            output_path=output_path
        )

        assert result.exists()
        assert result.parent.exists()
        assert result.stat().st_size > 0

    def test_default_page_size_is_a4(self):
        """Test that default page size is A4 (international standard)"""
        config = PDFExportConfig()
        assert config.page_size == A4, "Default page size should be A4"

    def test_letter_vs_a4_page_size(self, basic_markdown, temp_output_dir):
        """Test different page sizes"""
        # Letter size
        config_letter = PDFExportConfig(page_size=letter)
        exporter_letter = PDFExporter(config_letter)
        output_letter = temp_output_dir / "test_letter.pdf"

        result_letter = exporter_letter.markdown_to_pdf(
            markdown_content=basic_markdown,
            output_path=output_letter
        )

        # A4 size
        config_a4 = PDFExportConfig(page_size=A4)
        exporter_a4 = PDFExporter(config_a4)
        output_a4 = temp_output_dir / "test_a4.pdf"

        result_a4 = exporter_a4.markdown_to_pdf(
            markdown_content=basic_markdown,
            output_path=output_a4
        )

        assert result_letter.exists()
        assert result_a4.exists()
        # File sizes might differ slightly due to page size
        assert result_letter.stat().st_size > 0
        assert result_a4.stat().st_size > 0

    def test_font_size_variations(self, basic_markdown, temp_output_dir):
        """Test different font sizes"""
        for font_size in [10, 11, 12, 14]:
            config = PDFExportConfig(base_font_size=font_size)
            exporter = PDFExporter(config)
            output_path = temp_output_dir / f"test_font_{font_size}.pdf"

            result = exporter.markdown_to_pdf(
                markdown_content=basic_markdown,
                output_path=output_path
            )

            assert result.exists()
            assert result.stat().st_size > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
