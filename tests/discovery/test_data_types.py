"""Tests for discovery data types."""

import pytest
from datetime import datetime

from bmlibrarian.discovery.data_types import (
    SourceType, AccessType, ResolutionStatus,
    PDFSource, ResolutionResult, DocumentIdentifiers,
    DiscoveryResult, DownloadResult
)


class TestDocumentIdentifiers:
    """Tests for DocumentIdentifiers dataclass."""

    def test_has_identifiers_with_doi(self):
        """Test has_identifiers returns True when DOI is present."""
        ids = DocumentIdentifiers(doi="10.1234/test")
        assert ids.has_identifiers() is True

    def test_has_identifiers_with_pmid(self):
        """Test has_identifiers returns True when PMID is present."""
        ids = DocumentIdentifiers(pmid="12345678")
        assert ids.has_identifiers() is True

    def test_has_identifiers_with_pmcid(self):
        """Test has_identifiers returns True when PMCID is present."""
        ids = DocumentIdentifiers(pmcid="PMC1234567")
        assert ids.has_identifiers() is True

    def test_has_identifiers_with_title(self):
        """Test has_identifiers returns True when title is present."""
        ids = DocumentIdentifiers(title="Test Paper")
        assert ids.has_identifiers() is True

    def test_has_identifiers_empty(self):
        """Test has_identifiers returns False when no identifiers."""
        ids = DocumentIdentifiers()
        assert ids.has_identifiers() is False

    def test_has_identifiers_only_pdf_url(self):
        """Test has_identifiers returns False with only pdf_url."""
        ids = DocumentIdentifiers(pdf_url="https://example.com/paper.pdf")
        assert ids.has_identifiers() is False

    def test_from_dict(self):
        """Test creating identifiers from dictionary."""
        data = {
            'id': 123,
            'doi': '10.1234/test',
            'pmid': '12345678',
            'title': 'Test Paper',
            'pdf_url': 'https://example.com/paper.pdf'
        }
        ids = DocumentIdentifiers.from_dict(data)

        assert ids.doc_id == 123
        assert ids.doi == '10.1234/test'
        assert ids.pmid == '12345678'
        assert ids.title == 'Test Paper'
        assert ids.pdf_url == 'https://example.com/paper.pdf'

    def test_from_dict_with_pubmed_id(self):
        """Test creating identifiers with pubmed_id alias."""
        data = {'pubmed_id': '12345678'}
        ids = DocumentIdentifiers.from_dict(data)
        assert ids.pmid == '12345678'


class TestPDFSource:
    """Tests for PDFSource dataclass."""

    def test_create_source(self):
        """Test creating a PDF source."""
        source = PDFSource(
            url="https://example.com/paper.pdf",
            source_type=SourceType.PMC,
            access_type=AccessType.OPEN,
            priority=5
        )

        assert source.url == "https://example.com/paper.pdf"
        assert source.source_type == SourceType.PMC
        assert source.access_type == AccessType.OPEN
        assert source.priority == 5

    def test_source_ordering(self):
        """Test that sources can be sorted by priority."""
        source1 = PDFSource(
            url="https://example.com/1.pdf",
            source_type=SourceType.PMC,
            access_type=AccessType.OPEN,
            priority=5
        )
        source2 = PDFSource(
            url="https://example.com/2.pdf",
            source_type=SourceType.DOI_REDIRECT,
            access_type=AccessType.UNKNOWN,
            priority=20
        )
        source3 = PDFSource(
            url="https://example.com/3.pdf",
            source_type=SourceType.UNPAYWALL,
            access_type=AccessType.OPEN,
            priority=1
        )

        sorted_sources = sorted([source1, source2, source3])

        assert sorted_sources[0].priority == 1
        assert sorted_sources[1].priority == 5
        assert sorted_sources[2].priority == 20


class TestDiscoveryResult:
    """Tests for DiscoveryResult dataclass."""

    def test_has_open_access_true(self):
        """Test has_open_access returns True when OA source exists."""
        result = DiscoveryResult(
            identifiers=DocumentIdentifiers(doi="10.1234/test"),
            sources=[
                PDFSource(
                    url="https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/",
                    source_type=SourceType.PMC,
                    access_type=AccessType.OPEN,
                    priority=5
                )
            ]
        )

        assert result.has_open_access() is True

    def test_has_open_access_false(self):
        """Test has_open_access returns False when no OA source."""
        result = DiscoveryResult(
            identifiers=DocumentIdentifiers(doi="10.1234/test"),
            sources=[
                PDFSource(
                    url="https://example.com/paper.pdf",
                    source_type=SourceType.DIRECT_URL,
                    access_type=AccessType.SUBSCRIPTION,
                    priority=10
                )
            ]
        )

        assert result.has_open_access() is False

    def test_get_open_access_sources(self):
        """Test filtering to only OA sources."""
        result = DiscoveryResult(
            identifiers=DocumentIdentifiers(doi="10.1234/test"),
            sources=[
                PDFSource(
                    url="https://pmc.ncbi.nlm.nih.gov/pdf",
                    source_type=SourceType.PMC,
                    access_type=AccessType.OPEN,
                    priority=5
                ),
                PDFSource(
                    url="https://publisher.com/pdf",
                    source_type=SourceType.DOI_REDIRECT,
                    access_type=AccessType.SUBSCRIPTION,
                    priority=20
                ),
                PDFSource(
                    url="https://unpaywall.org/pdf",
                    source_type=SourceType.UNPAYWALL,
                    access_type=AccessType.OPEN,
                    priority=1
                )
            ]
        )

        oa_sources = result.get_open_access_sources()

        assert len(oa_sources) == 2
        assert all(s.access_type == AccessType.OPEN for s in oa_sources)

    def test_select_best_source_prefers_open_access(self):
        """Test that select_best_source prefers OA over other types."""
        result = DiscoveryResult(
            identifiers=DocumentIdentifiers(doi="10.1234/test"),
            sources=[
                PDFSource(
                    url="https://pmc.ncbi.nlm.nih.gov/pdf",
                    source_type=SourceType.PMC,
                    access_type=AccessType.OPEN,
                    priority=5
                ),
                PDFSource(
                    url="https://proxy.example.com/pdf",
                    source_type=SourceType.OPENATHENS,
                    access_type=AccessType.INSTITUTIONAL,
                    priority=1  # Lower priority number = higher priority
                )
            ]
        )

        best = result.select_best_source()

        # Even though institutional has lower priority number,
        # OA should be preferred
        assert best.access_type == AccessType.OPEN

    def test_select_best_source_empty(self):
        """Test select_best_source returns None when no sources."""
        result = DiscoveryResult(
            identifiers=DocumentIdentifiers(doi="10.1234/test"),
            sources=[]
        )

        assert result.select_best_source() is None


class TestResolutionResult:
    """Tests for ResolutionResult dataclass."""

    def test_create_result(self):
        """Test creating a resolution result."""
        result = ResolutionResult(
            resolver_name="pmc",
            status=ResolutionStatus.SUCCESS,
            sources=[
                PDFSource(
                    url="https://pmc.ncbi.nlm.nih.gov/pdf",
                    source_type=SourceType.PMC,
                    access_type=AccessType.OPEN,
                    priority=5
                )
            ],
            duration_ms=150.5
        )

        assert result.resolver_name == "pmc"
        assert result.status == ResolutionStatus.SUCCESS
        assert len(result.sources) == 1
        assert result.duration_ms == 150.5


class TestDownloadResult:
    """Tests for DownloadResult dataclass."""

    def test_success_result(self):
        """Test creating a successful download result."""
        source = PDFSource(
            url="https://pmc.ncbi.nlm.nih.gov/pdf",
            source_type=SourceType.PMC,
            access_type=AccessType.OPEN,
            priority=5
        )

        result = DownloadResult(
            success=True,
            source=source,
            file_path="/tmp/paper.pdf",
            file_size=1024000
        )

        assert result.success is True
        assert result.file_size == 1024000
        assert result.error_message is None

    def test_failure_result(self):
        """Test creating a failed download result."""
        result = DownloadResult(
            success=False,
            error_message="Access denied"
        )

        assert result.success is False
        assert result.error_message == "Access denied"
        assert result.file_path is None
