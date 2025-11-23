"""Full-text discovery module for BMLibrarian.

Provides tools for finding and downloading PDF full-text from multiple sources,
prioritizing open access when available.

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

    # Or discover and download in one step
    from pathlib import Path
    download_result = finder.discover_and_download(
        identifiers,
        output_path=Path("paper.pdf")
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
    discover_full_text
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
]
