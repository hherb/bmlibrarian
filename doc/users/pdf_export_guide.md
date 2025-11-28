# PDF Export Guide

This guide covers how to export BMLibrarian research reports to professional PDF documents.

## Overview

BMLibrarian includes a PDF export system that converts markdown-formatted research reports into publication-quality PDF files. The system uses **ReportLab** (BSD-licensed, free for commercial use and redistribution) to produce professional documents suitable for sharing, archiving, and publication.

## Quick Start

### Basic Export

```python
from pathlib import Path
from bmlibrarian.exporters import PDFExporter

# Create exporter with default settings
exporter = PDFExporter()

# Export markdown report to PDF
markdown_content = """
# Research Report

## Summary
This study examined...

## Methods
We analyzed...

## Results
- Finding 1
- Finding 2

## Conclusion
Our analysis demonstrates...
"""

output_path = exporter.markdown_to_pdf(
    markdown_content=markdown_content,
    output_path=Path("research_report.pdf"),
    metadata={
        'title': 'Cardiovascular Benefits of Exercise',
        'author': 'BMLibrarian',
        'subject': 'Medical Literature Review'
    }
)

print(f"PDF created: {output_path}")
```

### Export BMLibrarian Report

The `export_report()` method is optimized for BMLibrarian research reports:

```python
from bmlibrarian.exporters import PDFExporter

exporter = PDFExporter()

# Export with research metadata
output_path = exporter.export_report(
    report_content=final_report,  # Markdown-formatted report
    output_path=Path("reports/cardiovascular_exercise_2025.pdf"),
    research_question="What are the cardiovascular benefits of regular exercise?",
    citation_count=45,
    document_count=128
)
```

This automatically adds:
- Research question at the top
- Document and citation counts
- Generation timestamp
- Professional formatting

## Configuration

### Custom Settings

```python
from bmlibrarian.exporters import PDFExporter, PDFExportConfig
from reportlab.lib.pagesizes import A4

# Create custom configuration
config = PDFExportConfig(
    # Page settings
    page_size=A4,  # Use A4 instead of Letter
    margin_left=1.0 * inch,
    margin_right=1.0 * inch,

    # Styling
    base_font_size=12,
    heading_color=(0.1, 0.1, 0.3),  # Dark blue headings
    link_color=(0.0, 0.3, 0.7),  # Blue links

    # Features
    include_toc=True,
    include_page_numbers=True,
    include_timestamp=True,
    highlight_citations=True
)

exporter = PDFExporter(config)
```

### Available Configuration Options

#### Page Settings
- `page_size`: `letter` (default) or `A4`
- `margin_left`, `margin_right`, `margin_top`, `margin_bottom`: Margins in inches
- Default margins: 0.75" left/right, 1.0" top, 0.75" bottom

#### Document Metadata
- `title`: Document title (appears in PDF metadata and header)
- `author`: Author name (default: "BMLibrarian")
- `subject`: Subject/topic description
- `keywords`: List of keywords for PDF metadata

#### Styling Options
- `base_font_size`: Base font size in points (default: 11)
- `heading_color`: RGB tuple for heading colors (default: (0.2, 0.2, 0.4))
- `link_color`: RGB tuple for hyperlink colors (default: (0.0, 0.2, 0.6))
- `code_background`: RGB tuple for code block background (default: (0.95, 0.95, 0.95))

#### Content Options
- `include_toc`: Include table of contents (default: True)
- `include_header`: Show header on pages (default: True)
- `include_footer`: Show footer on pages (default: True)
- `include_page_numbers`: Add page numbers to footer (default: True)
- `include_timestamp`: Add generation timestamp (default: True)

#### Medical Report Specific
- `show_confidence_indicators`: Highlight confidence levels (default: True)
- `highlight_citations`: Apply special formatting to citations (default: True)

## Supported Markdown Features

The PDF exporter supports GitHub-flavored markdown:

### Headings
```markdown
# Heading 1
## Heading 2
### Heading 3
#### Heading 4
```

### Text Formatting
```markdown
**Bold text**
*Italic text*
`Inline code`
```

### Lists
```markdown
- Bullet point 1
- Bullet point 2
  - Nested bullet

1. Numbered item 1
2. Numbered item 2
```

### Code Blocks
````markdown
```python
def example():
    return "Hello"
```
````

### Tables
```markdown
| Header 1 | Header 2 |
|----------|----------|
| Cell 1   | Cell 2   |
| Cell 3   | Cell 4   |
```

### Links
```markdown
[Link text](https://example.com)
```

### Blockquotes
```markdown
> This is a quote from a research paper.
> It can span multiple lines.
```

### Horizontal Rules
```markdown
---
```

## Integration with Research Workflow

### From CLI

```python
# In bmlibrarian_cli.py workflow
from bmlibrarian.exporters import PDFExporter

# After generating report
exporter = PDFExporter()
pdf_path = exporter.export_report(
    report_content=comprehensive_report,
    output_path=Path(f"reports/report_{datetime.now():%Y%m%d_%H%M%S}.pdf"),
    research_question=user_question,
    citation_count=len(citations),
    document_count=len(scored_documents)
)

print(f"\nPDF report saved to: {pdf_path}")
```

### From GUI

The Research GUI can integrate PDF export:

```python
# In bmlibrarian_research_gui.py
def export_to_pdf(self):
    """Export current report to PDF"""
    if not self.final_report:
        QMessageBox.warning(self, "No Report", "Generate a report first")
        return

    # Get save location
    file_path, _ = QFileDialog.getSaveFileName(
        self,
        "Save PDF Report",
        "research_report.pdf",
        "PDF Files (*.pdf)"
    )

    if file_path:
        try:
            exporter = PDFExporter()
            exporter.export_report(
                report_content=self.final_report,
                output_path=Path(file_path),
                research_question=self.research_question,
                citation_count=self.citation_count,
                document_count=self.document_count
            )
            QMessageBox.information(self, "Success", f"PDF saved to:\n{file_path}")
        except PDFExportError as e:
            QMessageBox.critical(self, "Export Failed", str(e))
```

## Command-Line Export Tool

Create a standalone export utility:

```python
#!/usr/bin/env python3
"""
Export markdown file to PDF

Usage:
    uv run python export_to_pdf.py report.md -o report.pdf
    uv run python export_to_pdf.py report.md --title "My Research Report"
"""

import argparse
from pathlib import Path
from bmlibrarian.exporters import PDFExporter, PDFExportConfig

def main():
    parser = argparse.ArgumentParser(description='Export markdown to PDF')
    parser.add_argument('input', type=Path, help='Input markdown file')
    parser.add_argument('-o', '--output', type=Path, required=True, help='Output PDF file')
    parser.add_argument('--title', help='Document title')
    parser.add_argument('--author', default='BMLibrarian', help='Author name')
    parser.add_argument('--font-size', type=int, default=11, help='Base font size')
    parser.add_argument('--a4', action='store_true', help='Use A4 instead of Letter')

    args = parser.parse_args()

    # Read markdown content
    markdown_content = args.input.read_text()

    # Configure exporter
    config = PDFExportConfig(
        page_size=A4 if args.a4 else letter,
        base_font_size=args.font_size,
        title=args.title
    )

    # Export
    exporter = PDFExporter(config)
    output_path = exporter.markdown_to_pdf(
        markdown_content=markdown_content,
        output_path=args.output,
        metadata={
            'title': args.title,
            'author': args.author
        }
    )

    print(f"✓ PDF created: {output_path}")

if __name__ == '__main__':
    main()
```

## Best Practices

### 1. Use Meaningful Titles
```python
metadata = {
    'title': 'Cardiovascular Benefits of Exercise: A Systematic Review',
    'author': 'BMLibrarian v1.0',
    'subject': 'Medical Literature Analysis'
}
```

### 2. Structure Your Reports
Use clear heading hierarchy:
```markdown
# Main Title

## Executive Summary
Brief overview...

## Background
Context and motivation...

## Methods
Search strategy...

## Results
### Finding 1
### Finding 2

## Discussion
Interpretation...

## Conclusions
Summary of findings...

## References
Citations...
```

### 3. Format Citations Consistently
```markdown
1. Smith J, et al. (2023). Exercise and heart health. *PMID: 12345678*
2. Johnson A, et al. (2024). Cardiovascular outcomes. *DOI: 10.1234/example*
```

### 4. Use Tables for Data
```markdown
| Study | Sample Size | Effect Size | p-value |
|-------|-------------|-------------|---------|
| Smith 2023 | 1,000 | 0.45 | <0.001 |
| Jones 2024 | 500 | 0.38 | <0.01 |
```

### 5. Handle Long Documents
For very long reports, consider:
- Breaking into sections
- Using page breaks between major sections
- Keeping summaries concise

## Troubleshooting

### PDF Generation Fails

**Problem**: `PDFExportError: Failed to generate PDF`

**Solutions**:
1. Check output directory exists and is writable
2. Verify markdown content is valid
3. Ensure no special characters in file path

### Formatting Issues

**Problem**: Content doesn't appear as expected

**Solutions**:
1. Validate markdown syntax
2. Check for unsupported markdown extensions
3. Use supported features (see Supported Markdown Features)

### Large File Size

**Problem**: PDF file is very large

**Solutions**:
1. Optimize images before including
2. Reduce embedded content
3. Use external references for supplementary materials

## Advanced Usage

### Custom Styles

Create custom paragraph styles for specialized content:

```python
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER

# Add custom style to exporter
exporter = PDFExporter()
exporter.styles.add(ParagraphStyle(
    name='Highlight',
    parent=exporter.styles['Normal'],
    fontSize=12,
    textColor=colors.red,
    backColor=colors.yellow,
    alignment=TA_CENTER
))
```

### Batch Export

Export multiple reports:

```python
from pathlib import Path
from bmlibrarian.exporters import PDFExporter

reports_dir = Path("reports")
markdown_files = reports_dir.glob("*.md")

exporter = PDFExporter()

for md_file in markdown_files:
    markdown_content = md_file.read_text()
    pdf_path = md_file.with_suffix('.pdf')

    exporter.markdown_to_pdf(
        markdown_content=markdown_content,
        output_path=pdf_path
    )
    print(f"Exported: {pdf_path}")
```

## Technical Details

### Dependencies

- **reportlab**: Core PDF generation (BSD License)
- **markdown**: Markdown parsing (BSD License)
- **Pygments**: Syntax highlighting for code blocks (BSD License)

All dependencies are free for commercial use and redistribution.

### Rendering Pipeline

1. **Markdown → HTML**: Convert markdown to HTML using Python-Markdown
2. **HTML Parsing**: Parse HTML into semantic elements
3. **Flowable Creation**: Convert elements to ReportLab flowables
4. **PDF Generation**: Build PDF with custom canvas for headers/footers

### Performance

Typical performance on modern hardware:
- Small reports (<10 pages): <1 second
- Medium reports (10-50 pages): 1-3 seconds
- Large reports (50+ pages): 3-10 seconds

## License

The PDF export system uses ReportLab (BSD License), which is completely free for:
- Commercial use
- Modification
- Distribution
- Private use

No licensing fees or restrictions apply.

## See Also

- [ReportLab Documentation](https://www.reportlab.com/docs/reportlab-userguide.pdf)
- [Python-Markdown Documentation](https://python-markdown.github.io/)
- [BMLibrarian Reporting Guide](reporting_guide.md)
