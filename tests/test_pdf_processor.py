"""
Simple command-line test script for the PDF Processor library.

Usage:
    uv run python test_pdf_processor.py <path_to_pdf>
"""

import sys
from pathlib import Path
import os
from bmlibrarian.pdf_processor import PDFExtractor, SectionSegmenter


def validate_output_path(pdf_path: str) -> Path:
    """
    Validate and sanitize the output file path to prevent path injection.

    Args:
        pdf_path: Path to the input PDF file

    Returns:
        Safe output path for the markdown file

    Raises:
        ValueError: If the path is unsafe or invalid
    """
    pdf_path_obj = Path(pdf_path).resolve()

    # Ensure the PDF path is not trying to traverse directories maliciously
    if not pdf_path_obj.exists():
        raise ValueError(f"Input file does not exist: {pdf_path}")

    # Create output path in the same directory as the input PDF
    # Use resolve() to get the absolute path and prevent directory traversal
    output_path = pdf_path_obj.with_suffix('.md')

    # Verify the output path is in an expected location
    # (same directory as input or subdirectory)
    if not str(output_path.resolve()).startswith(str(pdf_path_obj.parent.resolve())):
        raise ValueError("Output path would be outside the expected directory")

    return output_path


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python test_pdf_processor.py <path_to_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    if not Path(pdf_path).exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    print(f"Processing: {pdf_path}")
    print("=" * 80)

    try:
        # Extract text blocks
        print("\n1. Extracting text blocks with layout information...")
        with PDFExtractor(pdf_path) as extractor:
            blocks = extractor.extract_text_blocks()
            metadata = extractor.extract_metadata()
            metadata['file_path'] = pdf_path

            print(f"   - Extracted {len(blocks)} text blocks")
            print(f"   - Total pages: {metadata.get('num_pages', 'Unknown')}")
            if metadata.get('title'):
                print(f"   - Metadata title: {metadata['title']}")

        # Segment into sections
        print("\n2. Segmenting document into sections...")
        segmenter = SectionSegmenter()
        document = segmenter.segment_document(blocks, metadata)

        print(f"   - Found {len(document.sections)} sections")

        # Display sections
        print("\n3. Sections found:")
        print("=" * 80)

        for i, section in enumerate(document.sections, 1):
            print(f"\n{i}. {section.title.upper()}")
            print(f"   Type: {section.section_type.value}")
            print(f"   Pages: {section.page_start + 1}-{section.page_end + 1}")
            print(f"   Confidence: {section.confidence:.1%}")
            print(f"   Content length: {len(section.content)} characters")
            print(f"   Preview: {section.content[:200]}..." if len(section.content) > 200 else f"   Content: {section.content}")

        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        section_types = [s.section_type.value for s in document.sections]
        print(f"Total sections: {len(document.sections)}")
        print(f"Section types: {', '.join(section_types)}")
        print(f"Total pages: {metadata.get('num_pages', 'Unknown')}")

        # Export to markdown
        print("\n4. Exporting to markdown...")
        markdown_path = validate_output_path(pdf_path)
        markdown_content = document.to_markdown()

        with open(markdown_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        print(f"   - Saved to: {markdown_path}")

        print("\n✓ Processing complete!")

    except Exception as e:
        print(f"\n✗ Error processing PDF: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
