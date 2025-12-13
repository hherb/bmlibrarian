"""
Unit tests for PubMed search client.

Tests the PubMedSearchClient class for API interactions.
"""

import pytest
from unittest.mock import patch, MagicMock
import json

from bmlibrarian.pubmed_search.search_client import PubMedSearchClient
from bmlibrarian.pubmed_search.data_types import PubMedQuery, ArticleMetadata


class TestPubMedSearchClientInit:
    """Tests for PubMedSearchClient initialization."""

    def test_init_with_email(self) -> None:
        """Test initialization with email."""
        client = PubMedSearchClient(email="test@example.com")
        assert client.email == "test@example.com"

    def test_init_with_api_key(self) -> None:
        """Test initialization with API key sets faster rate limit."""
        client = PubMedSearchClient(api_key="test_key")
        assert client.api_key == "test_key"
        assert client.request_delay == 0.1  # Faster with API key

    def test_init_without_api_key(self) -> None:
        """Test initialization without API key sets slower rate limit."""
        client = PubMedSearchClient()
        assert client.request_delay == 0.34  # Slower without key


class TestPubMedSearchClientSearch:
    """Tests for search functionality."""

    @pytest.fixture
    def client(self) -> PubMedSearchClient:
        """Create a test client."""
        return PubMedSearchClient(email="test@example.com")

    @pytest.fixture
    def sample_query(self) -> PubMedQuery:
        """Create a sample query."""
        return PubMedQuery(
            original_question="What are cardiovascular benefits of exercise?",
            query_string='"Exercise"[MeSH] AND "Cardiovascular"[tiab]',
        )

    @patch.object(PubMedSearchClient, "_make_request")
    def test_search_success(
        self,
        mock_request: MagicMock,
        client: PubMedSearchClient,
        sample_query: PubMedQuery,
    ) -> None:
        """Test successful search."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "esearchresult": {
                "count": "100",
                "idlist": ["12345678", "23456789", "34567890"],
            }
        }
        mock_request.return_value = mock_response

        result = client.search(sample_query, max_results=10)

        assert result.total_count == 100
        assert result.retrieved_count == 3
        assert len(result.pmids) == 3

    @patch.object(PubMedSearchClient, "_make_request")
    def test_search_no_results(
        self,
        mock_request: MagicMock,
        client: PubMedSearchClient,
        sample_query: PubMedQuery,
    ) -> None:
        """Test search with no results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "esearchresult": {
                "count": "0",
                "idlist": [],
            }
        }
        mock_request.return_value = mock_response

        result = client.search(sample_query)

        assert result.total_count == 0
        assert result.retrieved_count == 0
        assert len(result.pmids) == 0

    @patch.object(PubMedSearchClient, "_make_request")
    def test_search_api_failure(
        self,
        mock_request: MagicMock,
        client: PubMedSearchClient,
        sample_query: PubMedQuery,
    ) -> None:
        """Test search when API fails."""
        mock_request.return_value = None

        result = client.search(sample_query)

        assert result.total_count == 0
        assert result.retrieved_count == 0

    def test_search_simple(self, client: PubMedSearchClient) -> None:
        """Test simple search creates query object."""
        with patch.object(client, "search") as mock_search:
            mock_search.return_value = MagicMock(total_count=0)
            client.search_simple('"Exercise"[MeSH]', max_results=10)
            mock_search.assert_called_once()


class TestPubMedSearchClientFetch:
    """Tests for article fetching."""

    @pytest.fixture
    def client(self) -> PubMedSearchClient:
        """Create a test client."""
        return PubMedSearchClient(email="test@example.com")

    @pytest.fixture
    def sample_xml(self) -> bytes:
        """Sample PubMed XML response."""
        return b"""<?xml version="1.0" ?>
        <PubmedArticleSet>
            <PubmedArticle>
                <MedlineCitation>
                    <PMID>12345678</PMID>
                    <Article>
                        <ArticleTitle>Test Article Title</ArticleTitle>
                        <Abstract>
                            <AbstractText>This is the abstract text.</AbstractText>
                        </Abstract>
                        <AuthorList>
                            <Author>
                                <LastName>Smith</LastName>
                                <ForeName>John</ForeName>
                            </Author>
                        </AuthorList>
                        <Journal>
                            <Title>Test Journal</Title>
                        </Journal>
                    </Article>
                </MedlineCitation>
                <PubmedData>
                    <ArticleIdList>
                        <ArticleId IdType="doi">10.1234/test</ArticleId>
                    </ArticleIdList>
                </PubmedData>
            </PubmedArticle>
        </PubmedArticleSet>
        """

    @patch.object(PubMedSearchClient, "_make_request")
    def test_fetch_articles(
        self,
        mock_request: MagicMock,
        client: PubMedSearchClient,
        sample_xml: bytes,
    ) -> None:
        """Test fetching article metadata."""
        mock_response = MagicMock()
        mock_response.content = sample_xml
        mock_request.return_value = mock_response

        articles = client.fetch_articles(["12345678"])

        assert len(articles) == 1
        assert articles[0].pmid == "12345678"
        assert articles[0].title == "Test Article Title"
        assert "Smith John" in articles[0].authors
        assert articles[0].doi == "10.1234/test"

    @patch.object(PubMedSearchClient, "_make_request")
    def test_fetch_articles_empty_list(
        self,
        mock_request: MagicMock,
        client: PubMedSearchClient,
    ) -> None:
        """Test fetching with empty PMID list."""
        articles = client.fetch_articles([])
        assert articles == []
        mock_request.assert_not_called()

    @patch.object(PubMedSearchClient, "_make_request")
    def test_fetch_articles_batching(
        self,
        mock_request: MagicMock,
        client: PubMedSearchClient,
        sample_xml: bytes,
    ) -> None:
        """Test that large lists are batched."""
        mock_response = MagicMock()
        mock_response.content = sample_xml
        mock_request.return_value = mock_response

        # Create list larger than batch size
        pmids = [str(i) for i in range(300)]
        client.fetch_articles(pmids, batch_size=200)

        # Should make 2 requests
        assert mock_request.call_count == 2


class TestPubMedSearchClientParsing:
    """Tests for XML parsing."""

    @pytest.fixture
    def client(self) -> PubMedSearchClient:
        """Create a test client."""
        return PubMedSearchClient()

    def test_parse_structured_abstract(self, client: PubMedSearchClient) -> None:
        """Test parsing structured abstract with sections."""
        xml = b"""<?xml version="1.0" ?>
        <PubmedArticleSet>
            <PubmedArticle>
                <MedlineCitation>
                    <PMID>12345</PMID>
                    <Article>
                        <ArticleTitle>Test</ArticleTitle>
                        <Abstract>
                            <AbstractText Label="BACKGROUND">Background text.</AbstractText>
                            <AbstractText Label="METHODS">Methods text.</AbstractText>
                            <AbstractText Label="RESULTS">Results text.</AbstractText>
                            <AbstractText Label="CONCLUSIONS">Conclusions text.</AbstractText>
                        </Abstract>
                    </Article>
                </MedlineCitation>
            </PubmedArticle>
        </PubmedArticleSet>
        """

        articles = client._parse_articles_xml(xml)
        assert len(articles) == 1

        abstract = articles[0].abstract
        assert "**BACKGROUND:**" in abstract
        assert "**METHODS:**" in abstract
        assert "**RESULTS:**" in abstract
        assert "**CONCLUSIONS:**" in abstract

    def test_parse_mesh_terms(self, client: PubMedSearchClient) -> None:
        """Test parsing MeSH terms from XML."""
        xml = b"""<?xml version="1.0" ?>
        <PubmedArticleSet>
            <PubmedArticle>
                <MedlineCitation>
                    <PMID>12345</PMID>
                    <Article>
                        <ArticleTitle>Test</ArticleTitle>
                    </Article>
                    <MeshHeadingList>
                        <MeshHeading>
                            <DescriptorName>Exercise</DescriptorName>
                        </MeshHeading>
                        <MeshHeading>
                            <DescriptorName>Cardiovascular Diseases</DescriptorName>
                        </MeshHeading>
                    </MeshHeadingList>
                </MedlineCitation>
            </PubmedArticle>
        </PubmedArticleSet>
        """

        articles = client._parse_articles_xml(xml)
        assert len(articles) == 1
        assert "Exercise" in articles[0].mesh_terms
        assert "Cardiovascular Diseases" in articles[0].mesh_terms

    def test_parse_pmc_id(self, client: PubMedSearchClient) -> None:
        """Test parsing PMC ID from XML."""
        xml = b"""<?xml version="1.0" ?>
        <PubmedArticleSet>
            <PubmedArticle>
                <MedlineCitation>
                    <PMID>12345</PMID>
                    <Article><ArticleTitle>Test</ArticleTitle></Article>
                </MedlineCitation>
                <PubmedData>
                    <ArticleIdList>
                        <ArticleId IdType="pmc">PMC1234567</ArticleId>
                    </ArticleIdList>
                </PubmedData>
            </PubmedArticle>
        </PubmedArticleSet>
        """

        articles = client._parse_articles_xml(xml)
        assert len(articles) == 1
        assert articles[0].pmc_id == "PMC1234567"


class TestPubMedSearchClientConnection:
    """Tests for connection testing."""

    @patch.object(PubMedSearchClient, "_make_request")
    def test_connection_success(self, mock_request: MagicMock) -> None:
        """Test successful connection test."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        client = PubMedSearchClient()
        assert client.test_connection() is True

    @patch.object(PubMedSearchClient, "_make_request")
    def test_connection_failure(self, mock_request: MagicMock) -> None:
        """Test failed connection test."""
        mock_request.return_value = None

        client = PubMedSearchClient()
        assert client.test_connection() is False


class TestPubMedSearchClientCount:
    """Tests for count-only queries."""

    @patch.object(PubMedSearchClient, "_make_request")
    def test_get_count(self, mock_request: MagicMock) -> None:
        """Test getting result count without PMIDs."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "esearchresult": {"count": "12345"}
        }
        mock_request.return_value = mock_response

        client = PubMedSearchClient()
        query = PubMedQuery(original_question="test", query_string="test")

        count = client.get_count(query)
        assert count == 12345
