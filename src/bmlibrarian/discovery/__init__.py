"""Full-text discovery module for BMLibrarian.

Provides tools for finding and downloading PDF full-text from multiple sources,
prioritizing open access when available.

Supports a two-phase download approach:
1. Direct HTTP downloads (fast, works for OA and properly configured sites)
2. Browser-based fallback (handles Cloudflare, anti-bot protections, embedded viewers)

Example usage:
    from bmlibrarian.discovery import FullTextFinder, DocumentIdentifiers

    # Create finder
    finder = FullTextFinder(unpaywall_email="your@email.com")

    # Discover PDF sources
    identifiers = DocumentIdentifiers(doi="10.1234/example")
    result = finder.discover(identifiers)

    # Get best source
    if result.best_source:
        print(f"Best source: {result.best_source.url}")
        print(f"Access type: {result.best_source.access_type.value}")

    # Or discover and download in one step (with automatic browser fallback)
    from pathlib import Path
    download_result = finder.discover_and_download(
        identifiers,
        output_path=Path("paper.pdf"),
        use_browser_fallback=True  # Try browser if HTTP fails
    )

    # For document dictionaries, use the convenience method
    document = {'doi': '10.1234/example', 'id': 123, 'publication_date': '2024'}
    result = finder.download_for_document(document, output_dir=Path('pdfs'))

    # Or use the standalone convenience function
    from bmlibrarian.discovery import download_pdf_for_document
    result = download_pdf_for_document(
        document={'doi': '10.1234/example'},
        output_dir=Path('pdfs'),
        unpaywall_email='your@email.com'
    )
"""

from .data_types import (
    SourceType,
    AccessType,
    ResolutionStatus,
    PDFSource,
    ResolutionResult,
    DocumentIdentifiers,
    DiscoveryResult,
    DownloadResult
)

from .resolvers import (
    BaseResolver,
    DirectURLResolver,
    DOIResolver,
    PMCResolver,
    UnpaywallResolver,
    OpenAthensResolver
)

from .full_text_finder import (
    FullTextFinder,
    discover_full_text,
    download_pdf_for_document
)

__all__ = [
    # Data types
    'SourceType',
    'AccessType',
    'ResolutionStatus',
    'PDFSource',
    'ResolutionResult',
    'DocumentIdentifiers',
    'DiscoveryResult',
    'DownloadResult',
    # Resolvers
    'BaseResolver',
    'DirectURLResolver',
    'DOIResolver',
    'PMCResolver',
    'UnpaywallResolver',
    'OpenAthensResolver',
    # Main classes
    'FullTextFinder',
    # Convenience functions
    'discover_full_text',
    'download_pdf_for_document',
]
