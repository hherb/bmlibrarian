#!/usr/bin/env python3
"""
Export Markdown to PDF - BMLibrarian

Convert markdown files to professional PDF documents using ReportLab.

Usage:
    uv run python export_to_pdf.py report.md -o report.pdf
    uv run python export_to_pdf.py report.md -o report.pdf --title "Research Report"
    uv run python export_to_pdf.py report.md -o report.pdf --title "Study" --author "Dr. Smith" --letter

Examples:
    # Basic export (uses A4 paper size by default - international standard)
    uv run python export_to_pdf.py my_report.md -o output.pdf

    # With custom title and author
    uv run python export_to_pdf.py research.md -o research.pdf --title "COVID-19 Study" --author "Research Team"

    # Use US Letter paper size with larger font
    uv run python export_to_pdf.py report.md -o report.pdf --letter --font-size 12

    # From BMLibrarian research report
    uv run python export_to_pdf.py reports/cardiovascular_2025.md -o cardiovascular.pdf --research-report
"""

import argparse
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4, letter

from bmlibrarian.exporters import PDFExporter, PDFExportConfig, PDFExportError


def main():
    """Main entry point for markdown to PDF conversion"""
    parser = argparse.ArgumentParser(
        description='Export markdown files to professional PDF documents',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s report.md -o report.pdf
  %(prog)s report.md -o report.pdf --title "Research Report" --author "Dr. Smith"
  %(prog)s report.md -o report.pdf --letter --font-size 12
  %(prog)s report.md -o report.pdf --research-report
        """
    )

    # Required arguments
    parser.add_argument(
        'input',
        type=Path,
        help='Input markdown file'
    )
    parser.add_argument(
        '-o', '--output',
        type=Path,
        required=True,
        help='Output PDF file path'
    )

    # Metadata options
    parser.add_argument(
        '--title',
        help='Document title (appears in PDF metadata and header)'
    )
    parser.add_argument(
        '--author',
        default='BMLibrarian',
        help='Author name (default: BMLibrarian)'
    )
    parser.add_argument(
        '--subject',
        help='Document subject/topic'
    )
    parser.add_argument(
        '--keywords',
        help='Comma-separated keywords for PDF metadata'
    )

    # Page settings
    parser.add_argument(
        '--letter',
        action='store_true',
        help='Use US Letter paper size instead of A4 (international default)'
    )
    parser.add_argument(
        '--font-size',
        type=int,
        default=11,
        help='Base font size in points (default: 11)'
    )
    parser.add_argument(
        '--margin',
        type=float,
        help='Uniform margin in inches (overrides individual margins)'
    )

    # Content options
    parser.add_argument(
        '--no-page-numbers',
        action='store_true',
        help='Disable page numbers in footer'
    )
    parser.add_argument(
        '--no-timestamp',
        action='store_true',
        help='Disable generation timestamp'
    )
    parser.add_argument(
        '--no-header',
        action='store_true',
        help='Disable header on pages'
    )

    # BMLibrarian specific
    parser.add_argument(
        '--research-report',
        action='store_true',
        help='Format as BMLibrarian research report (adds metadata section)'
    )
    parser.add_argument(
        '--citation-count',
        type=int,
        help='Number of citations (for research reports)'
    )
    parser.add_argument(
        '--document-count',
        type=int,
        help='Number of documents analyzed (for research reports)'
    )

    # Parse arguments
    args = parser.parse_args()

    # Validate input file
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        return 1

    if not args.input.is_file():
        print(f"Error: Input path is not a file: {args.input}", file=sys.stderr)
        return 1

    # Read markdown content
    try:
        markdown_content = args.input.read_text(encoding='utf-8')
    except Exception as e:
        print(f"Error: Failed to read input file: {e}", file=sys.stderr)
        return 1

    # Configure exporter
    config = PDFExportConfig(
        page_size=letter if args.letter else A4,
        base_font_size=args.font_size,
        title=args.title,
        author=args.author,
        subject=args.subject,
        keywords=args.keywords.split(',') if args.keywords else None,
        include_page_numbers=not args.no_page_numbers,
        include_timestamp=not args.no_timestamp,
        include_header=not args.no_header
    )

    # Apply uniform margin if specified
    if args.margin is not None:
        from reportlab.lib.units import inch
        margin = args.margin * inch
        config.margin_left = margin
        config.margin_right = margin
        config.margin_top = margin
        config.margin_bottom = margin

    # Create exporter
    exporter = PDFExporter(config)

    # Export to PDF
    try:
        print(f"Converting {args.input} to PDF...")

        if args.research_report:
            # Use research report export method
            output_path = exporter.export_report(
                report_content=markdown_content,
                output_path=args.output,
                research_question=args.title,
                citation_count=args.citation_count,
                document_count=args.document_count
            )
        else:
            # Use standard markdown export
            metadata = {
                'title': args.title,
                'author': args.author,
                'subject': args.subject
            }
            output_path = exporter.markdown_to_pdf(
                markdown_content=markdown_content,
                output_path=args.output,
                metadata=metadata
            )

        print(f"✓ PDF created successfully: {output_path}")
        print(f"  File size: {output_path.stat().st_size:,} bytes")

        return 0

    except PDFExportError as e:
        print(f"Error: PDF export failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
