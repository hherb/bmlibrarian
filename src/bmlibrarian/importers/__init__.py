"""
Importers for external data sources (medRxiv, PubMed, MeSH, etc.)
"""

from .medrxiv_importer import MedRxivImporter
from .pubmed_importer import PubMedImporter
from .pubmed_bulk_importer import PubMedBulkImporter
from .mesh_importer import MeSHImporter, ImportStats as MeSHImportStats
from .pdf_matcher import PDFMatcher, DocumentStatus, ExtractedIdentifiers
from .pdf_converter import (
    PDFConverter,
    PyMuPDFConverter,
    ConversionResult,
    get_converter,
    list_converters,
)
from .pdf_ingestor import (
    PDFIngestor,
    IngestResult,
)
from .europe_pmc_bulk_downloader import (
    EuropePMCBulkDownloader,
    EuropePMCPackageInfo,
    DownloadProgress as EuropePMCDownloadProgress,
)
from .europe_pmc_importer import (
    EuropePMCImporter,
    EuropePMCXMLParser,
    ArticleMetadata as EuropePMCArticleMetadata,
    ImportProgress as EuropePMCImportProgress,
)

__all__ = [
    'MedRxivImporter',
    'PubMedImporter',
    'PubMedBulkImporter',
    'MeSHImporter',
    'MeSHImportStats',
    'PDFMatcher',
    'DocumentStatus',
    'ExtractedIdentifiers',
    'PDFConverter',
    'PyMuPDFConverter',
    'ConversionResult',
    'get_converter',
    'list_converters',
    'PDFIngestor',
    'IngestResult',
    'EuropePMCBulkDownloader',
    'EuropePMCPackageInfo',
    'EuropePMCDownloadProgress',
    'EuropePMCImporter',
    'EuropePMCXMLParser',
    'EuropePMCArticleMetadata',
    'EuropePMCImportProgress',
]
