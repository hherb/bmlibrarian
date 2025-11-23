"""Tests for discovery resolvers."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from bmlibrarian.discovery.data_types import (
    DocumentIdentifiers, ResolutionStatus, SourceType, AccessType
)
from bmlibrarian.discovery.resolvers import (
    DirectURLResolver, DOIResolver, PMCResolver,
    UnpaywallResolver, OpenAthensResolver
)


class TestDirectURLResolver:
    """Tests for DirectURLResolver."""

    def test_resolve_with_url(self):
        """Test resolving when pdf_url is present."""
        resolver = DirectURLResolver()
        identifiers = DocumentIdentifiers(
            pdf_url="https://example.com/paper.pdf"
        )

        result = resolver.resolve(identifiers)

        assert result.status == ResolutionStatus.SUCCESS
        assert len(result.sources) == 1
        assert result.sources[0].url == "https://example.com/paper.pdf"
        assert result.sources[0].source_type == SourceType.DIRECT_URL

    def test_resolve_without_url(self):
        """Test resolving when pdf_url is missing."""
        resolver = DirectURLResolver()
        identifiers = DocumentIdentifiers(doi="10.1234/test")

        result = resolver.resolve(identifiers)

        assert result.status == ResolutionStatus.NOT_FOUND
        assert len(result.sources) == 0

    def test_resolve_invalid_url(self):
        """Test resolving with invalid URL format."""
        resolver = DirectURLResolver()
        identifiers = DocumentIdentifiers(pdf_url="not-a-valid-url")

        result = resolver.resolve(identifiers)

        assert result.status == ResolutionStatus.ERROR
        assert "Invalid URL" in result.error_message


class TestDOIResolver:
    """Tests for DOIResolver."""

    def test_normalize_doi(self):
        """Test DOI normalization."""
        resolver = DOIResolver()

        assert resolver._normalize_doi("10.1234/test") == "10.1234/test"
        assert resolver._normalize_doi("https://doi.org/10.1234/test") == "10.1234/test"
        assert resolver._normalize_doi("doi:10.1234/test") == "10.1234/test"
        assert resolver._normalize_doi("  10.1234/test  ") == "10.1234/test"

    def test_resolve_without_doi(self):
        """Test resolving when DOI is missing."""
        resolver = DOIResolver()
        identifiers = DocumentIdentifiers(pmid="12345678")

        result = resolver.resolve(identifiers)

        assert result.status == ResolutionStatus.SKIPPED


class TestPMCResolver:
    """Tests for PMCResolver."""

    def test_normalize_pmcid(self):
        """Test PMCID normalization."""
        resolver = PMCResolver()

        assert resolver._normalize_pmcid("PMC1234567") == "PMC1234567"
        assert resolver._normalize_pmcid("pmc1234567") == "PMC1234567"
        assert resolver._normalize_pmcid("1234567") == "PMC1234567"

    def test_resolve_without_identifiers(self):
        """Test resolving when no PMC-related identifiers."""
        resolver = PMCResolver()
        identifiers = DocumentIdentifiers(title="Some Paper")

        result = resolver.resolve(identifiers)

        assert result.status == ResolutionStatus.NOT_FOUND


class TestUnpaywallResolver:
    """Tests for UnpaywallResolver."""

    def test_resolve_without_doi(self):
        """Test resolving when DOI is missing."""
        resolver = UnpaywallResolver(email="test@example.com")
        identifiers = DocumentIdentifiers(pmid="12345678")

        result = resolver.resolve(identifiers)

        assert result.status == ResolutionStatus.SKIPPED

    @patch('bmlibrarian.discovery.resolvers.requests.Session.get')
    def test_resolve_with_oa_result(self, mock_get):
        """Test resolving when Unpaywall returns OA location."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'is_oa': True,
            'oa_status': 'gold',
            'best_oa_location': {
                'url_for_pdf': 'https://example.com/oa.pdf',
                'license': 'cc-by',
                'version': 'publishedVersion',
                'host_type': 'publisher'
            },
            'oa_locations': []
        }
        mock_get.return_value = mock_response

        resolver = UnpaywallResolver(email="test@example.com")
        identifiers = DocumentIdentifiers(doi="10.1234/test")

        result = resolver.resolve(identifiers)

        assert result.status == ResolutionStatus.SUCCESS
        assert len(result.sources) == 1
        assert result.sources[0].url == "https://example.com/oa.pdf"
        assert result.sources[0].access_type == AccessType.OPEN
        assert result.sources[0].is_best_oa is True

    @patch('bmlibrarian.discovery.resolvers.requests.Session.get')
    def test_resolve_not_found(self, mock_get):
        """Test resolving when article not in Unpaywall."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        resolver = UnpaywallResolver(email="test@example.com")
        identifiers = DocumentIdentifiers(doi="10.1234/test")

        result = resolver.resolve(identifiers)

        assert result.status == ResolutionStatus.NOT_FOUND


class TestOpenAthensResolver:
    """Tests for OpenAthensResolver."""

    def test_construct_proxy_url(self):
        """Test OpenAthens proxy URL construction."""
        resolver = OpenAthensResolver(proxy_base_url="https://proxy.example.com")

        proxy_url = resolver._construct_proxy_url("https://publisher.com/paper.pdf")

        assert proxy_url.startswith("https://proxy.example.com/login?url=")
        assert "publisher.com" in proxy_url

    def test_resolve_with_doi(self):
        """Test resolving with DOI constructs proxy URL."""
        resolver = OpenAthensResolver(proxy_base_url="https://proxy.example.com")
        identifiers = DocumentIdentifiers(doi="10.1234/test")

        result = resolver.resolve(identifiers)

        assert result.status == ResolutionStatus.SUCCESS
        assert len(result.sources) == 1
        assert result.sources[0].source_type == SourceType.OPENATHENS
        assert result.sources[0].access_type == AccessType.INSTITUTIONAL
        assert "doi.org" in result.sources[0].url

    def test_resolve_with_pdf_url(self):
        """Test resolving with existing PDF URL uses that URL."""
        resolver = OpenAthensResolver(proxy_base_url="https://proxy.example.com")
        identifiers = DocumentIdentifiers(
            pdf_url="https://publisher.com/paper.pdf"
        )

        result = resolver.resolve(identifiers)

        assert result.status == ResolutionStatus.SUCCESS
        assert "publisher.com" in result.sources[0].metadata['original_url']

    def test_resolve_without_identifiers(self):
        """Test resolving without usable identifiers."""
        resolver = OpenAthensResolver(proxy_base_url="https://proxy.example.com")
        identifiers = DocumentIdentifiers(title="Some Paper")

        result = resolver.resolve(identifiers)

        assert result.status == ResolutionStatus.SKIPPED
