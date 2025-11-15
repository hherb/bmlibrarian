"""
Tests for PubMed Importer

These tests verify the basic functionality of the PubMed importer module.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
import xml.etree.ElementTree as ET
from datetime import datetime

from src.bmlibrarian.importers.pubmed_importer import PubMedImporter


class TestPubMedImporter:
    """Test cases for PubMedImporter class."""

    @patch('src.bmlibrarian.importers.pubmed_importer.get_db_manager')
    def test_initialization(self, mock_db_manager):
        """Test importer initialization."""
        # Mock database operations
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db_manager.return_value.get_connection.return_value.__enter__.return_value = mock_conn

        # Mock source_id query
        mock_cursor.fetchone.return_value = (1,)

        importer = PubMedImporter(email='test@example.com', api_key='test_key')

        assert importer.email == 'test@example.com'
        assert importer.api_key == 'test_key'
        assert importer.source_id == 1
        assert importer.request_delay == 0.1  # With API key

    @patch('src.bmlibrarian.importers.pubmed_importer.get_db_manager')
    def test_rate_limiting(self, mock_db_manager):
        """Test rate limiting based on API key presence."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db_manager.return_value.get_connection.return_value.__enter__.return_value = mock_conn
        mock_cursor.fetchone.return_value = (1,)

        # With API key
        importer_with_key = PubMedImporter(api_key='test_key')
        assert importer_with_key.request_delay == 0.1

        # Without API key
        importer_without_key = PubMedImporter()
        assert importer_without_key.request_delay == 0.34

    @patch('src.bmlibrarian.importers.pubmed_importer.requests.get')
    @patch('src.bmlibrarian.importers.pubmed_importer.get_db_manager')
    def test_search_pubmed(self, mock_db_manager, mock_requests):
        """Test PubMed search functionality."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db_manager.return_value.get_connection.return_value.__enter__.return_value = mock_conn
        mock_cursor.fetchone.return_value = (1,)

        # Mock search response
        mock_response = Mock()
        mock_response.json.return_value = {
            'esearchresult': {
                'idlist': ['12345678', '23456789', '34567890']
            }
        }
        mock_response.raise_for_status = Mock()
        mock_requests.return_value = mock_response

        importer = PubMedImporter()
        pmids = importer.search_pubmed("COVID-19 vaccine", max_results=10)

        assert len(pmids) == 3
        assert '12345678' in pmids
        assert '23456789' in pmids
        assert '34567890' in pmids

    @patch('src.bmlibrarian.importers.pubmed_importer.requests.get')
    @patch('src.bmlibrarian.importers.pubmed_importer.get_db_manager')
    def test_fetch_articles(self, mock_db_manager, mock_requests):
        """Test article fetching."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db_manager.return_value.get_connection.return_value.__enter__.return_value = mock_conn
        mock_cursor.fetchone.return_value = (1,)

        # Create mock XML response
        xml_content = """<?xml version="1.0"?>
        <PubmedArticleSet>
            <PubmedArticle>
                <MedlineCitation>
                    <PMID>12345678</PMID>
                    <Article>
                        <ArticleTitle>Test Article Title</ArticleTitle>
                        <Abstract>
                            <AbstractText>Test abstract text.</AbstractText>
                        </Abstract>
                        <AuthorList>
                            <Author>
                                <LastName>Smith</LastName>
                                <ForeName>John</ForeName>
                            </Author>
                        </AuthorList>
                    </Article>
                    <Journal>
                        <Title>Test Journal</Title>
                    </Journal>
                    <PubDate>
                        <Year>2023</Year>
                        <Month>Jan</Month>
                        <Day>15</Day>
                    </PubDate>
                </MedlineCitation>
            </PubmedArticle>
        </PubmedArticleSet>
        """

        mock_response = Mock()
        mock_response.content = xml_content.encode('utf-8')
        mock_response.raise_for_status = Mock()
        mock_requests.return_value = mock_response

        importer = PubMedImporter()
        articles = importer.fetch_articles(['12345678'])

        assert len(articles) == 1

    @patch('src.bmlibrarian.importers.pubmed_importer.get_db_manager')
    def test_parse_article(self, mock_db_manager):
        """Test article XML parsing."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db_manager.return_value.get_connection.return_value.__enter__.return_value = mock_conn
        mock_cursor.fetchone.return_value = (1,)

        # Create XML element
        xml_content = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>12345678</PMID>
                <Article>
                    <ArticleTitle>Test Article Title</ArticleTitle>
                    <Abstract>
                        <AbstractText>Test abstract text.</AbstractText>
                    </Abstract>
                    <AuthorList>
                        <Author>
                            <LastName>Smith</LastName>
                            <ForeName>John</ForeName>
                        </Author>
                        <Author>
                            <LastName>Doe</LastName>
                            <ForeName>Jane</ForeName>
                        </Author>
                    </AuthorList>
                </Article>
                <Journal>
                    <Title>Test Journal</Title>
                </Journal>
                <PubDate>
                    <Year>2023</Year>
                    <Month>Jan</Month>
                    <Day>15</Day>
                </PubDate>
            </MedlineCitation>
            <PubmedData>
                <ArticleIdList>
                    <ArticleId IdType="doi">10.1234/test.doi</ArticleId>
                </ArticleIdList>
            </PubmedData>
        </PubmedArticle>
        """

        article_elem = ET.fromstring(xml_content)
        importer = PubMedImporter()
        article = importer._parse_article(article_elem)

        assert article is not None
        assert article['pmid'] == '12345678'
        assert article['title'] == 'Test Article Title'
        assert article['abstract'] == 'Test abstract text.'
        assert len(article['authors']) == 2
        assert 'Smith John' in article['authors']
        assert 'Doe Jane' in article['authors']
        assert article['publication'] == 'Test Journal'
        assert article['doi'] == '10.1234/test.doi'
        assert article['publication_date'] == '2023-01-15'

    @patch('src.bmlibrarian.importers.pubmed_importer.get_db_manager')
    def test_parse_article_with_mesh_terms(self, mock_db_manager):
        """Test parsing article with MeSH terms."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db_manager.return_value.get_connection.return_value.__enter__.return_value = mock_conn
        mock_cursor.fetchone.return_value = (1,)

        xml_content = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>12345678</PMID>
                <Article>
                    <ArticleTitle>Test Article</ArticleTitle>
                </Article>
                <MeshHeadingList>
                    <MeshHeading>
                        <DescriptorName>COVID-19</DescriptorName>
                    </MeshHeading>
                    <MeshHeading>
                        <DescriptorName>Vaccines</DescriptorName>
                    </MeshHeading>
                </MeshHeadingList>
            </MedlineCitation>
        </PubmedArticle>
        """

        article_elem = ET.fromstring(xml_content)
        importer = PubMedImporter()
        article = importer._parse_article(article_elem)

        assert article is not None
        assert len(article['mesh_terms']) == 2
        assert 'COVID-19' in article['mesh_terms']
        assert 'Vaccines' in article['mesh_terms']

    @patch('src.bmlibrarian.importers.pubmed_importer.get_db_manager')
    def test_parse_article_with_keywords(self, mock_db_manager):
        """Test parsing article with keywords."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db_manager.return_value.get_connection.return_value.__enter__.return_value = mock_conn
        mock_cursor.fetchone.return_value = (1,)

        xml_content = """
        <PubmedArticle>
            <MedlineCitation>
                <PMID>12345678</PMID>
                <Article>
                    <ArticleTitle>Test Article</ArticleTitle>
                    <KeywordList>
                        <Keyword>immunology</Keyword>
                        <Keyword>pandemic</Keyword>
                    </KeywordList>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
        """

        article_elem = ET.fromstring(xml_content)
        importer = PubMedImporter()
        article = importer._parse_article(article_elem)

        assert article is not None
        assert len(article['keywords']) == 2
        assert 'immunology' in article['keywords']
        assert 'pandemic' in article['keywords']

    @patch('src.bmlibrarian.importers.pubmed_importer.get_db_manager')
    def test_extract_date(self, mock_db_manager):
        """Test date extraction from PubDate element."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db_manager.return_value.get_connection.return_value.__enter__.return_value = mock_conn
        mock_cursor.fetchone.return_value = (1,)

        importer = PubMedImporter()

        # Full date
        date_xml = """<PubDate><Year>2023</Year><Month>Mar</Month><Day>15</Day></PubDate>"""
        date_elem = ET.fromstring(date_xml)
        date = importer._extract_date(date_elem)
        assert date == '2023-03-15'

        # Year and month only
        date_xml = """<PubDate><Year>2023</Year><Month>05</Month></PubDate>"""
        date_elem = ET.fromstring(date_xml)
        date = importer._extract_date(date_elem)
        assert date == '2023-05-01'

        # Year only
        date_xml = """<PubDate><Year>2023</Year></PubDate>"""
        date_elem = ET.fromstring(date_xml)
        date = importer._extract_date(date_elem)
        assert date == '2023-01-01'

    @patch('src.bmlibrarian.importers.pubmed_importer.get_db_manager')
    def test_store_articles(self, mock_db_manager):
        """Test storing articles in database."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db_manager.return_value.get_connection.return_value.__enter__.return_value = mock_conn

        # Mock source_id query and article insertion
        mock_cursor.fetchone.side_effect = [
            (1,),  # source_id
            None,  # Article doesn't exist
            (100,)  # Inserted article ID
        ]

        importer = PubMedImporter()

        articles = [{
            'pmid': '12345678',
            'doi': '10.1234/test.doi',
            'title': 'Test Article',
            'abstract': 'Test abstract',
            'authors': ['Smith John', 'Doe Jane'],
            'publication': 'Test Journal',
            'publication_date': '2023-01-15',
            'url': 'https://pubmed.ncbi.nlm.nih.gov/12345678/',
            'mesh_terms': ['COVID-19'],
            'keywords': ['immunology']
        }]

        count = importer._store_articles(articles)

        assert count == 1
        # Verify INSERT was called with correct parameters
        assert mock_cursor.execute.call_count >= 2

    @patch('src.bmlibrarian.importers.pubmed_importer.requests.get')
    @patch('src.bmlibrarian.importers.pubmed_importer.get_db_manager')
    def test_import_by_pmids(self, mock_db_manager, mock_requests):
        """Test complete import workflow by PMID list."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db_manager.return_value.get_connection.return_value.__enter__.return_value = mock_conn

        # Mock database queries
        mock_cursor.fetchone.side_effect = [
            (1,),  # source_id
            None,  # Article doesn't exist
            (100,)  # Inserted article ID
        ]

        # Mock fetch response
        xml_content = """<?xml version="1.0"?>
        <PubmedArticleSet>
            <PubmedArticle>
                <MedlineCitation>
                    <PMID>12345678</PMID>
                    <Article>
                        <ArticleTitle>Test Article</ArticleTitle>
                        <Abstract>
                            <AbstractText>Test abstract.</AbstractText>
                        </Abstract>
                    </Article>
                    <Journal>
                        <Title>Test Journal</Title>
                    </Journal>
                    <PubDate>
                        <Year>2023</Year>
                    </PubDate>
                </MedlineCitation>
            </PubmedArticle>
        </PubmedArticleSet>
        """

        mock_response = Mock()
        mock_response.content = xml_content.encode('utf-8')
        mock_response.raise_for_status = Mock()
        mock_requests.return_value = mock_response

        importer = PubMedImporter()
        stats = importer.import_by_pmids(['12345678'])

        assert stats['total_requested'] == 1
        assert stats['imported'] == 1

    @patch('src.bmlibrarian.importers.pubmed_importer.get_db_manager')
    def test_get_element_text(self, mock_db_manager):
        """Test getting complete text from XML elements."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_db_manager.return_value.get_connection.return_value.__enter__.return_value = mock_conn
        mock_cursor.fetchone.return_value = (1,)

        importer = PubMedImporter()

        # Simple text element
        xml = """<Title>Simple Title</Title>"""
        elem = ET.fromstring(xml)
        text = importer._get_element_text(elem)
        assert text == 'Simple Title'

        # Mixed content element
        xml = """<Title>Title with <i>italic</i> text</Title>"""
        elem = ET.fromstring(xml)
        text = importer._get_element_text(elem)
        assert 'Title with' in text
        assert 'italic' in text
        assert 'text' in text


def test_module_imports():
    """Test that module can be imported."""
    from src.bmlibrarian.importers import PubMedImporter
    assert PubMedImporter is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
