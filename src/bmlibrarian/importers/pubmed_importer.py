"""
PubMed Importer for BMLibrarian

This module provides functionality to import biomedical articles from PubMed
using the NCBI E-utilities API.

Example usage:
    from bmlibrarian.importers import PubMedImporter

    importer = PubMedImporter()

    # Import by search query
    stats = importer.import_by_search("COVID-19 vaccine", max_results=100)

    # Import by PMID list
    stats = importer.import_by_pmids([12345678, 23456789])
"""

import os
import sys
import time
import logging
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

from bmlibrarian.database import get_db_manager

logger = logging.getLogger(__name__)

try:
    from tqdm import tqdm
except ImportError:
    logger.warning("tqdm not installed. Progress bars will not be displayed.")
    tqdm = None


class PubMedImporter:
    """
    Importer for PubMed biomedical articles.

    Uses NCBI E-utilities API to fetch and import articles into BMLibrarian.
    """

    EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    ESEARCH_URL = f"{EUTILS_BASE}/esearch.fcgi"
    EFETCH_URL = f"{EUTILS_BASE}/efetch.fcgi"

    def __init__(self, email: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize the PubMed importer.

        Args:
            email: Email for NCBI (recommended but not required)
            api_key: NCBI API key for higher rate limits (optional)
        """
        self.db_manager = get_db_manager()
        self.email = email or os.environ.get('NCBI_EMAIL', '')
        self.api_key = api_key or os.environ.get('NCBI_API_KEY', '')

        # Rate limiting: 3 requests/second without key, 10/second with key
        self.request_delay = 0.1 if self.api_key else 0.34

        # Get source_id for PubMed
        self.source_id = self._get_source_id('pubmed')
        if not self.source_id:
            raise ValueError("PubMed source not found in database. Please ensure 'sources' table contains 'pubmed' entry.")

        logger.info(f"PubMed importer initialized (rate limit: {1/self.request_delay:.1f} req/s)")

    def _get_source_id(self, source_name: str) -> Optional[int]:
        """Get the source ID for a given source name."""
        cached_ids = self.db_manager.get_cached_source_ids()
        if cached_ids and source_name.lower() in cached_ids:
            return cached_ids[source_name.lower()]

        # Fallback: query database directly
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM sources WHERE LOWER(name) LIKE %s", (f'%{source_name.lower()}%',))
                result = cur.fetchone()
                return result[0] if result else None

    def _make_request(self, url: str, params: Dict[str, Any], retries: int = 3) -> Optional[requests.Response]:
        """
        Make an HTTP request to NCBI E-utilities with retry logic.

        Args:
            url: API endpoint URL
            params: Query parameters
            retries: Number of retry attempts

        Returns:
            Response object or None if failed
        """
        # Add email and API key if available
        if self.email:
            params['email'] = self.email
        if self.api_key:
            params['api_key'] = self.api_key

        for attempt in range(retries):
            try:
                time.sleep(self.request_delay)  # Rate limiting
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"Request failed after {retries} attempts")
                    return None

        return None

    def search_pubmed(self, query: str, max_results: int = 100,
                     min_date: Optional[str] = None, max_date: Optional[str] = None) -> List[str]:
        """
        Search PubMed and return list of PMIDs.

        Args:
            query: PubMed search query
            max_results: Maximum number of results to return
            min_date: Minimum date (YYYY/MM/DD format)
            max_date: Maximum date (YYYY/MM/DD format)

        Returns:
            List of PMIDs
        """
        params = {
            'db': 'pubmed',
            'term': query,
            'retmax': max_results,
            'retmode': 'json'
        }

        if min_date:
            params['mindate'] = min_date
        if max_date:
            params['maxdate'] = max_date

        response = self._make_request(self.ESEARCH_URL, params)
        if not response:
            return []

        try:
            data = response.json()
            pmids = data.get('esearchresult', {}).get('idlist', [])
            logger.info(f"Search found {len(pmids)} articles")
            return pmids
        except Exception as e:
            logger.error(f"Error parsing search results: {e}")
            return []

    def fetch_articles(self, pmids: List[str], batch_size: int = 200) -> List[ET.Element]:
        """
        Fetch article details from PubMed in batches.

        Args:
            pmids: List of PMIDs to fetch
            batch_size: Number of articles per request

        Returns:
            List of article XML elements
        """
        all_articles = []

        # Process in batches
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i + batch_size]
            pmid_str = ','.join(batch)

            params = {
                'db': 'pubmed',
                'id': pmid_str,
                'retmode': 'xml'
            }

            response = self._make_request(self.EFETCH_URL, params)
            if not response:
                logger.warning(f"Failed to fetch batch {i//batch_size + 1}")
                continue

            try:
                # Parse XML
                root = ET.fromstring(response.content)
                articles = root.findall('.//PubmedArticle')
                all_articles.extend(articles)
                logger.debug(f"Fetched batch {i//batch_size + 1}: {len(articles)} articles")
            except Exception as e:
                logger.error(f"Error parsing XML batch: {e}")

        logger.info(f"Fetched {len(all_articles)} articles total")
        return all_articles

    def _get_element_text(self, elem) -> str:
        """
        Get complete text from an XML element, handling mixed content.
        """
        if elem is None:
            return ""

        # If element has no children, just return its text
        if not list(elem):
            return elem.text or ""

        # Build text from element text + all child text + tail text
        text = elem.text or ""
        for child in elem:
            text += self._get_element_text(child)
            if child.tail:
                text += child.tail

        return text

    def _extract_date(self, date_elem) -> Optional[str]:
        """Extract date from a PubMed date element."""
        if date_elem is None:
            return None

        year = date_elem.find('Year')
        month = date_elem.find('Month')
        day = date_elem.find('Day')

        if year is not None and year.text:
            year_text = year.text

            # Handle month
            month_text = "01"
            if month is not None and month.text:
                month_val = month.text.strip()
                month_map = {
                    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                }
                month_text = month_map.get(month_val, month_val.zfill(2) if month_val.isdigit() else "01")

            day_text = day.text.zfill(2) if day is not None and day.text and day.text.isdigit() else "01"

            try:
                return f"{year_text}-{month_text}-{day_text}"
            except:
                return year_text

        return None

    def _parse_article(self, article_elem: ET.Element) -> Optional[Dict[str, Any]]:
        """
        Parse a PubmedArticle XML element.

        Args:
            article_elem: XML element for a PubmedArticle

        Returns:
            Dictionary with article data or None if error
        """
        try:
            # Extract PMID
            pmid_elem = article_elem.find('.//PMID')
            if pmid_elem is None or not pmid_elem.text:
                return None

            pmid = pmid_elem.text

            # Extract title
            title_elem = article_elem.find('.//ArticleTitle')
            title = self._get_element_text(title_elem) if title_elem is not None else ""

            # Extract abstract
            abstract_texts = article_elem.findall('.//AbstractText')
            abstract_parts = []
            for t in abstract_texts:
                text = self._get_element_text(t)
                if text:
                    abstract_parts.append(text)
            abstract = " ".join(abstract_parts)

            # Extract authors
            author_elems = article_elem.findall('.//Author')
            authors = []
            for author in author_elems:
                last_name = author.find('.//LastName')
                fore_name = author.find('.//ForeName')

                author_name = ""
                if last_name is not None:
                    author_name = self._get_element_text(last_name)
                if fore_name is not None:
                    fore_text = self._get_element_text(fore_name)
                    author_name = f"{author_name} {fore_text}" if author_name else fore_text

                if author_name:
                    authors.append(author_name)

            # Extract publication date
            pubdate_elem = article_elem.find('.//PubDate')
            publication_date = self._extract_date(pubdate_elem)

            # Extract journal name
            journal_elem = article_elem.find('.//Journal/Title')
            journal = self._get_element_text(journal_elem) if journal_elem is not None else "PubMed"

            # Extract DOI
            doi = None
            for article_id in article_elem.findall('.//ArticleId'):
                if article_id.get('IdType') == 'doi':
                    doi = article_id.text
                    break

            # Extract MeSH terms
            mesh_terms = []
            for descriptor in article_elem.findall('.//MeshHeading/DescriptorName'):
                mesh_term = self._get_element_text(descriptor)
                if mesh_term:
                    mesh_terms.append(mesh_term)

            # Extract keywords
            keywords = []
            for keyword in article_elem.findall('.//Keyword'):
                kw = self._get_element_text(keyword)
                if kw:
                    keywords.append(kw)

            # Construct URL
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

            return {
                'pmid': pmid,
                'doi': doi,
                'title': title,
                'abstract': abstract,
                'authors': authors,
                'publication': journal,
                'publication_date': publication_date,
                'url': url,
                'mesh_terms': mesh_terms,
                'keywords': keywords
            }

        except Exception as e:
            logger.error(f"Error parsing article: {e}")
            return None

    def _store_articles(self, articles: List[Dict[str, Any]]) -> int:
        """
        Store articles in the database.

        Args:
            articles: List of article dictionaries

        Returns:
            Number of articles successfully stored
        """
        success_count = 0

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                for article in articles:
                    try:
                        pmid = article['pmid']

                        # Check if already exists
                        cur.execute("""
                            SELECT id FROM document
                            WHERE source_id = %s AND external_id = %s
                        """, (self.source_id, pmid))

                        if cur.fetchone():
                            logger.debug(f"Article PMID:{pmid} already exists")
                            continue

                        # Insert article
                        cur.execute("""
                            INSERT INTO document (
                                source_id, external_id, doi, title, abstract,
                                authors, publication, publication_date,
                                url, mesh_terms, keywords
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING id
                        """, (
                            self.source_id,
                            pmid,
                            article.get('doi'),
                            article['title'],
                            article['abstract'],
                            article['authors'],
                            article['publication'],
                            article.get('publication_date'),
                            article['url'],
                            article.get('mesh_terms', []),
                            article.get('keywords', [])
                        ))

                        doc_id = cur.fetchone()[0]
                        logger.debug(f"Inserted article ID {doc_id} (PMID:{pmid})")
                        success_count += 1

                    except Exception as e:
                        logger.error(f"Error storing article PMID:{article.get('pmid', 'unknown')}: {e}")
                        conn.rollback()
                        continue

        return success_count

    def import_by_search(self, query: str, max_results: int = 100,
                        min_date: Optional[str] = None, max_date: Optional[str] = None) -> Dict[str, int]:
        """
        Import articles by PubMed search query.

        Args:
            query: PubMed search query
            max_results: Maximum number of articles to import
            min_date: Minimum date (YYYY/MM/DD format)
            max_date: Maximum date (YYYY/MM/DD format)

        Returns:
            Dictionary with statistics
        """
        logger.info(f"Importing articles for query: {query}")

        # Search for PMIDs
        pmids = self.search_pubmed(query, max_results, min_date, max_date)
        if not pmids:
            logger.warning("No articles found")
            return {'total_found': 0, 'imported': 0}

        # Fetch articles
        article_elements = self.fetch_articles(pmids)

        # Parse articles
        if tqdm:
            progress = tqdm(article_elements, desc="Parsing articles", unit="article")
        else:
            progress = article_elements

        articles = []
        for elem in progress:
            article = self._parse_article(elem)
            if article:
                articles.append(article)

        logger.info(f"Parsed {len(articles)} articles")

        # Store in database
        imported = self._store_articles(articles)

        logger.info(f"Import complete: {imported} articles imported")

        return {
            'total_found': len(pmids),
            'parsed': len(articles),
            'imported': imported
        }

    def import_by_pmids(self, pmids: List[str]) -> Dict[str, int]:
        """
        Import articles by PMID list.

        Args:
            pmids: List of PMIDs to import

        Returns:
            Dictionary with statistics
        """
        logger.info(f"Importing {len(pmids)} articles by PMID")

        # Fetch articles
        article_elements = self.fetch_articles(pmids)

        # Parse articles
        if tqdm:
            progress = tqdm(article_elements, desc="Parsing articles", unit="article")
        else:
            progress = article_elements

        articles = []
        for elem in progress:
            article = self._parse_article(elem)
            if article:
                articles.append(article)

        logger.info(f"Parsed {len(articles)} articles")

        # Store in database
        imported = self._store_articles(articles)

        logger.info(f"Import complete: {imported} articles imported")

        return {
            'total_requested': len(pmids),
            'parsed': len(articles),
            'imported': imported
        }
