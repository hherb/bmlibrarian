"""
PubMed Bulk Importer - FTP-based complete mirror system

This module provides FTP-based bulk downloading and importing of PubMed
baseline and update files for maintaining a complete local PubMed mirror.

Unlike the E-utilities importer (pubmed_importer.py) which is designed for
targeted imports, this bulk importer:
- Downloads complete PubMed baseline (all ~38M articles)
- Downloads daily update files (new articles + metadata updates)
- Detects and applies metadata updates to existing records
- Supports offline operation after initial download
- Handles multi-GB XML files efficiently with streaming parsing
- Preserves abstract structure and inline formatting as Markdown

Abstract Formatting Features:
- Structured abstracts: Preserves section labels (BACKGROUND, METHODS, RESULTS, CONCLUSIONS)
- Inline formatting: Converts XML tags to Markdown (bold, italic, subscript, superscript)
- Scientific notation: Preserves chemical formulas (H₂O → H~2~O) and units (m² → m^2^)
- Paragraph breaks: Maintains section separation with double newlines

Usage:
    from bmlibrarian.importers import PubMedBulkImporter

    importer = PubMedBulkImporter(data_dir='/path/to/pubmed_data')

    # Download baseline files
    importer.download_baseline()

    # Download update files
    importer.download_updates()

    # Import downloaded files
    importer.import_files()
"""

import ftplib
import gzip
import hashlib
import logging
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import backoff

from bmlibrarian.database import get_db_manager

logger = logging.getLogger(__name__)


class DownloadTracker:
    """Tracks PubMed file downloads and processing status in PostgreSQL."""

    def __init__(self):
        """Initialize download tracker."""
        self.db_manager = get_db_manager()
        self._ensure_tracking_table()

    def _ensure_tracking_table(self):
        """Create pubmed_download_log table if it doesn't exist.

        Note: This table schema must match the existing database schema:
        - file_name VARCHAR(255) NOT NULL UNIQUE
        - file_type VARCHAR(50) NOT NULL
        - download_date TIMESTAMP NOT NULL
        - processed BOOLEAN DEFAULT FALSE
        - process_date TIMESTAMP
        - file_size BIGINT
        - checksum VARCHAR(64)
        - status VARCHAR(20) DEFAULT 'downloaded'
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pubmed_download_log (
                        id SERIAL PRIMARY KEY,
                        file_name VARCHAR(255) UNIQUE NOT NULL,
                        file_type VARCHAR(50) NOT NULL,
                        download_date TIMESTAMP NOT NULL,
                        processed BOOLEAN DEFAULT FALSE,
                        process_date TIMESTAMP,
                        file_size BIGINT,
                        checksum VARCHAR(64),
                        status VARCHAR(20) DEFAULT 'downloaded'
                    )
                """)
                conn.commit()

    def is_file_downloaded(self, filename: str) -> bool:
        """Check if file has been downloaded."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pubmed_download_log WHERE file_name = %s",
                    (filename,)
                )
                return cur.fetchone() is not None

    def is_file_processed(self, filename: str) -> bool:
        """Check if file has been processed."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT processed FROM pubmed_download_log WHERE file_name = %s",
                    (filename,)
                )
                result = cur.fetchone()
                return result[0] if result else False

    def mark_downloaded(self, filename: str, file_type: str, file_size: int, checksum: str):
        """Mark file as downloaded."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO pubmed_download_log
                    (file_name, file_type, download_date, file_size, checksum, status)
                    VALUES (%s, %s, %s, %s, %s, 'downloaded')
                    ON CONFLICT (file_name) DO UPDATE SET
                        download_date = EXCLUDED.download_date,
                        file_size = EXCLUDED.file_size,
                        checksum = EXCLUDED.checksum,
                        status = EXCLUDED.status
                """, (filename, file_type, datetime.now(), file_size, checksum))
                conn.commit()

    def mark_processed(self, filename: str, articles_count: int = 0, error: Optional[str] = None):
        """Mark file as processed.

        Note: articles_count and error are accepted for API compatibility but
        not stored (columns don't exist in current schema).
        """
        status = 'error' if error else 'processed'
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE pubmed_download_log
                    SET processed = %s,
                        process_date = %s,
                        status = %s
                    WHERE file_name = %s
                """, (not error, datetime.now(), status, filename))
                conn.commit()

    def get_unprocessed_files(self) -> List[str]:
        """Get list of downloaded but unprocessed files."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT file_name FROM pubmed_download_log
                    WHERE processed = FALSE
                    ORDER BY file_name
                """)
                return [row[0] for row in cur.fetchall()]

    def get_stats(self) -> Dict:
        """Get download and processing statistics."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) as total_files,
                        COUNT(*) FILTER (WHERE processed = TRUE) as processed_files,
                        COUNT(*) FILTER (WHERE file_type = 'baseline') as baseline_files,
                        COUNT(*) FILTER (WHERE file_type = 'update') as update_files,
                        SUM(file_size) as total_size,
                        SUM(articles_count) FILTER (WHERE processed = TRUE) as total_articles
                    FROM pubmed_download_log
                """)
                row = cur.fetchone()
                return {
                    'total_files': row[0] or 0,
                    'processed_files': row[1] or 0,
                    'baseline_files': row[2] or 0,
                    'update_files': row[3] or 0,
                    'total_size_bytes': row[4] or 0,
                    'total_articles': row[5] or 0
                }


class PubMedBulkImporter:
    """FTP-based PubMed bulk downloader and importer."""

    FTP_HOST = 'ftp.ncbi.nlm.nih.gov'
    BASELINE_PATH = '/pubmed/baseline'
    UPDATE_PATH = '/pubmed/updatefiles'

    def __init__(self, data_dir: Optional[str] = None, use_tracking: bool = True):
        """
        Initialize PubMed bulk importer.

        Args:
            data_dir: Directory for storing downloaded files (default: ~/knowledgebase/pubmed_data)
            use_tracking: Whether to use database tracking (default: True)
        """
        self.data_dir = Path(data_dir or os.path.expanduser('~/knowledgebase/pubmed_data'))
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.baseline_dir = self.data_dir / 'baseline'
        self.update_dir = self.data_dir / 'updatefiles'
        self.baseline_dir.mkdir(exist_ok=True)
        self.update_dir.mkdir(exist_ok=True)

        self.use_tracking = use_tracking
        self.tracker = DownloadTracker() if use_tracking else None
        self.db_manager = get_db_manager()

        # Get PubMed source_id
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM sources WHERE LOWER(name) LIKE '%pubmed%' LIMIT 1")
                result = cur.fetchone()
                if not result:
                    raise ValueError("PubMed source not found in sources table")
                self.source_id = result[0]

        logger.info(f"Initialized PubMed bulk importer with data_dir: {self.data_dir}")

    @backoff.on_exception(
        backoff.expo,
        (ftplib.error_temp, EOFError, ConnectionResetError, TimeoutError),
        max_tries=3
    )
    def _create_ftp_connection(self) -> ftplib.FTP:
        """Create FTP connection with retry logic."""
        logger.debug(f"Connecting to {self.FTP_HOST}")
        ftp = ftplib.FTP(self.FTP_HOST, timeout=120)
        ftp.login()  # Anonymous login
        ftp.set_pasv(True)

        # Set socket keepalive (platform-specific options)
        import socket
        import sys
        sock = ftp.sock
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        # TCP keepalive options differ between platforms
        if sys.platform == 'darwin':
            # macOS: TCP_KEEPALIVE sets the idle time before keepalive probes
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, 60)
        elif sys.platform.startswith('linux'):
            # Linux: TCP_KEEPIDLE, TCP_KEEPINTVL, TCP_KEEPCNT
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        # Windows: keepalive options set differently, SO_KEEPALIVE alone is sufficient

        return ftp

    def _get_remote_file_list(self, ftp: ftplib.FTP, path: str) -> List[Tuple[str, int]]:
        """Get list of XML files from FTP directory."""
        ftp.cwd(path)
        files = []

        # Parse MLSD output for file names and sizes
        for name, facts in ftp.mlsd():
            if name.endswith('.xml.gz') and name.startswith('pubmed'):
                size = int(facts.get('size', 0))
                files.append((name, size))

        return sorted(files)

    def _calculate_checksum(self, filepath: Path) -> str:
        """Calculate MD5 checksum of file."""
        md5 = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return md5.hexdigest()

    def _download_file(self, ftp: ftplib.FTP, filename: str, dest_path: Path,
                      expected_size: int, max_retries: int = 5,
                      current_path: str = None) -> Tuple[bool, ftplib.FTP]:
        """
        Download file from FTP with resume capability.

        Args:
            ftp: FTP connection
            filename: Name of file to download
            dest_path: Local destination path
            expected_size: Expected file size in bytes
            max_retries: Maximum retry attempts
            current_path: Current FTP directory path for reconnection

        Returns:
            Tuple of (success: bool, ftp: FTP connection - may be new if reconnected)
        """
        for attempt in range(max_retries):
            try:
                # Test connection health before attempting download
                try:
                    ftp.voidcmd('NOOP')
                except Exception:
                    logger.info(f"{filename}: Connection stale, reconnecting...")
                    try:
                        ftp.quit()
                    except Exception:
                        pass
                    ftp = self._create_ftp_connection()
                    if current_path:
                        ftp.cwd(current_path)
                # Check if partial download exists
                start_pos = dest_path.stat().st_size if dest_path.exists() else 0

                if start_pos == expected_size:
                    logger.info(f"{filename}: Already downloaded ({expected_size} bytes)")
                    return True, ftp
                elif start_pos > expected_size:
                    logger.warning(f"{filename}: Local file larger than expected, redownloading")
                    dest_path.unlink()
                    start_pos = 0

                # Open file for appending
                mode = 'ab' if start_pos > 0 else 'wb'
                logger.info(f"{filename}: Downloading (resume from {start_pos}/{expected_size} bytes)")

                with open(dest_path, mode) as f:
                    # Resume from position - must be in binary mode
                    if start_pos > 0:
                        ftp.voidcmd('TYPE I')  # Switch to binary mode for REST
                        ftp.sendcmd(f'REST {start_pos}')

                    # Download with progress
                    downloaded = start_pos

                    def callback(chunk):
                        nonlocal downloaded
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded % (1024 * 1024 * 10) == 0:  # Every 10MB
                            logger.debug(f"{filename}: {downloaded}/{expected_size} bytes")

                    ftp.retrbinary(f'RETR {filename}', callback, blocksize=65536)
                    f.flush()
                    os.fsync(f.fileno())

                # Verify size
                actual_size = dest_path.stat().st_size
                if actual_size != expected_size:
                    logger.error(f"{filename}: Size mismatch ({actual_size} != {expected_size})")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying download (attempt {attempt + 2}/{max_retries})")
                        time.sleep(5 * (attempt + 1))  # Exponential backoff
                        continue
                    return False, ftp

                # Verify gzip integrity
                try:
                    with gzip.open(dest_path, 'rb') as gz:
                        gz.read(1)  # Try to read first byte
                    logger.info(f"{filename}: Download complete and verified")
                    return True, ftp
                except Exception as e:
                    logger.error(f"{filename}: Gzip verification failed: {e}")
                    if attempt < max_retries - 1:
                        dest_path.unlink()
                        time.sleep(5 * (attempt + 1))  # Exponential backoff
                        continue
                    return False, ftp

            except (BrokenPipeError, ConnectionResetError, EOFError, TimeoutError,
                    ftplib.error_temp, ftplib.error_reply) as e:
                # Connection-related errors - always reconnect
                logger.error(f"{filename}: Connection error: {e}")
                if attempt < max_retries - 1:
                    retry_delay = 10 * (attempt + 1)  # Exponential backoff: 10, 20, 30, 40 seconds
                    logger.info(f"Reconnecting and retrying in {retry_delay}s (attempt {attempt + 2}/{max_retries})")
                    time.sleep(retry_delay)
                    # Create fresh connection
                    try:
                        ftp.quit()
                    except Exception:
                        pass
                    ftp = self._create_ftp_connection()
                    if current_path:
                        ftp.cwd(current_path)
                    continue
                return False, ftp

            except Exception as e:
                logger.error(f"{filename}: Download error: {e}")
                if attempt < max_retries - 1:
                    retry_delay = 5 * (attempt + 1)
                    logger.info(f"Retrying in {retry_delay}s (attempt {attempt + 2}/{max_retries})")
                    time.sleep(retry_delay)
                    # Create fresh connection for safety
                    try:
                        ftp.quit()
                    except Exception:
                        pass
                    ftp = self._create_ftp_connection()
                    if current_path:
                        ftp.cwd(current_path)
                    continue
                return False, ftp

        return False, ftp

    def download_baseline(self, skip_existing: bool = True) -> int:
        """
        Download PubMed baseline files.

        Args:
            skip_existing: Skip files already downloaded (default: True)

        Returns:
            Number of files downloaded
        """
        logger.info("Starting baseline download")
        ftp = self._create_ftp_connection()
        ftp.cwd(self.BASELINE_PATH)
        downloaded = 0

        try:
            files = self._get_remote_file_list(ftp, self.BASELINE_PATH)
            logger.info(f"Found {len(files)} baseline files")

            for filename, size in files:
                if skip_existing and self.tracker and self.tracker.is_file_downloaded(filename):
                    logger.debug(f"{filename}: Already downloaded, skipping")
                    continue

                dest_path = self.baseline_dir / filename
                success, ftp = self._download_file(
                    ftp, filename, dest_path, size,
                    current_path=self.BASELINE_PATH
                )
                if success:
                    checksum = self._calculate_checksum(dest_path)
                    if self.tracker:
                        self.tracker.mark_downloaded(filename, 'baseline', size, checksum)
                    downloaded += 1
                else:
                    logger.error(f"{filename}: Download failed after all retries")

        finally:
            try:
                ftp.quit()
            except Exception:
                pass

        logger.info(f"Baseline download complete: {downloaded} files downloaded")
        return downloaded

    def download_updates(self, skip_existing: bool = True) -> int:
        """
        Download PubMed update files.

        Args:
            skip_existing: Skip files already downloaded (default: True)

        Returns:
            Number of files downloaded
        """
        logger.info("Starting update files download")
        ftp = self._create_ftp_connection()
        ftp.cwd(self.UPDATE_PATH)
        downloaded = 0

        try:
            files = self._get_remote_file_list(ftp, self.UPDATE_PATH)
            logger.info(f"Found {len(files)} update files")

            for filename, size in files:
                if skip_existing and self.tracker and self.tracker.is_file_downloaded(filename):
                    logger.debug(f"{filename}: Already downloaded, skipping")
                    continue

                dest_path = self.update_dir / filename
                success, ftp = self._download_file(
                    ftp, filename, dest_path, size,
                    current_path=self.UPDATE_PATH
                )
                if success:
                    checksum = self._calculate_checksum(dest_path)
                    if self.tracker:
                        self.tracker.mark_downloaded(filename, 'update', size, checksum)
                    downloaded += 1
                else:
                    logger.error(f"{filename}: Download failed after all retries")

        finally:
            try:
                ftp.quit()
            except Exception:
                pass

        logger.info(f"Update files download complete: {downloaded} files downloaded")
        return downloaded

    def _get_element_text(self, elem: Optional[ET.Element]) -> str:
        """
        Get complete text from XML element including nested elements.

        This properly extracts text from elements that contain both text and
        child elements (like subscripts, superscripts, etc.) by combining:
        - Element text (before first child)
        - Recursive child element text
        - Child tail text (after each child)

        Critical for avoiding truncation of titles/abstracts with special formatting.
        """
        if elem is None:
            return ''

        # Optimization for leaf nodes (no children)
        if not list(elem):
            return elem.text or ''

        # Handle mixed content (text + nested elements)
        text = elem.text or ''
        for child in elem:
            child_text = self._get_element_text(child)
            text += child_text
            if child.tail:
                text += child.tail

        return text

    def _get_element_text_with_formatting(self, elem: Optional[ET.Element]) -> str:
        """
        Extract text from XML element and convert inline formatting to Markdown.

        Handles HTML-style inline elements:
        - <b> or <bold> → **text**
        - <i> or <italic> → *text*
        - <sup> → ^text^
        - <sub> → ~text~
        - <u> or <underline> → __text__

        This preserves scientific notation, chemical formulas, and emphasis.

        Args:
            elem: XML element to extract text from

        Returns:
            Text with inline formatting converted to Markdown
        """
        if elem is None:
            return ''

        # Leaf node optimization (no children)
        if not list(elem):
            return (elem.text or '').strip()

        # Handle mixed content (text + nested formatting elements)
        parts = []

        # Add element's direct text (before first child)
        if elem.text:
            parts.append(elem.text)

        # Process each child element
        for child in elem:
            tag = child.tag.lower()
            child_text = self._get_element_text_with_formatting(child)

            # Convert HTML/XML tags to Markdown
            if tag in ('b', 'bold'):
                parts.append(f'**{child_text}**')
            elif tag in ('i', 'italic'):
                parts.append(f'*{child_text}*')
            elif tag == 'sup':
                parts.append(f'^{child_text}^')
            elif tag == 'sub':
                parts.append(f'~{child_text}~')
            elif tag in ('u', 'underline'):
                parts.append(f'__{child_text}__')
            else:
                # Unknown tag - just keep the text
                parts.append(child_text)

            # Add tail text (text after closing tag)
            if child.tail:
                parts.append(child.tail)

        return ''.join(parts).strip()

    def _format_abstract_markdown(self, abstract_elem: Optional[ET.Element]) -> str:
        """
        Extract and format abstract with proper Markdown formatting.

        This preserves:
        - Section labels from both Label and NlmCategory attributes
        - Paragraph breaks between sections
        - Inline formatting (bold, italic, subscript, superscript)
        - Handles both structured and unstructured abstracts

        Args:
            abstract_elem: Abstract XML element

        Returns:
            Markdown-formatted abstract with section headers and paragraph breaks
        """
        if abstract_elem is None:
            return ''

        # Find all AbstractText elements
        abstract_texts = abstract_elem.findall('.//AbstractText')
        if not abstract_texts:
            return ''

        markdown_parts = []

        for abstract_text in abstract_texts:
            # Get label attributes (prefer Label, fallback to NlmCategory)
            label = abstract_text.get('Label', '').strip()
            if not label:
                nlm_category = abstract_text.get('NlmCategory', '').strip()
                if nlm_category and nlm_category not in ('UNASSIGNED', 'UNLABELLED'):
                    label = nlm_category

            # Get text content with inline formatting
            text = self._get_element_text_with_formatting(abstract_text)

            if not text:
                continue

            # Format with label as header if present
            if label:
                # Capitalize label for consistency
                label_formatted = label.upper()
                markdown_parts.append(f"**{label_formatted}:** {text}")
            else:
                # Unstructured abstract
                markdown_parts.append(text)

        # Join sections with double newline for paragraph breaks
        return '\n\n'.join(markdown_parts)

    def _extract_date(self, pub_date_elem: Optional[ET.Element]) -> Optional[str]:
        """Extract publication date from PubDate element."""
        if pub_date_elem is None:
            return None

        year = pub_date_elem.findtext('Year')
        if not year:
            return None

        month = pub_date_elem.findtext('Month', '01')
        day = pub_date_elem.findtext('Day', '01')

        # Convert month name to number if necessary
        month_map = {
            'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
            'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
            'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
        }
        if month in month_map:
            month = month_map[month]
        elif len(month) == 1:
            month = f'0{month}'

        if len(day) == 1:
            day = f'0{day}'

        try:
            return f'{year}-{month}-{day}'
        except:
            return f'{year}-01-01'

    def _parse_article(self, article_elem: ET.Element) -> Optional[Dict]:
        """Parse PubmedArticle XML element into article dict."""
        try:
            medline = article_elem.find('.//MedlineCitation')
            if medline is None:
                return None

            pmid = medline.findtext('.//PMID')
            if not pmid:
                return None

            article = medline.find('.//Article')
            if article is None:
                return None

            # Extract title with inline formatting preservation
            title = self._get_element_text_with_formatting(article.find('.//ArticleTitle'))

            # Extract abstract with markdown formatting (structured sections + inline formatting)
            abstract_elem = article.find('.//Abstract')
            abstract = self._format_abstract_markdown(abstract_elem)

            # Authors
            authors = []
            for author in article.findall('.//AuthorList/Author'):
                last = author.findtext('LastName', '')
                first = author.findtext('ForeName', '')
                if last or first:
                    authors.append(f'{last} {first}'.strip())

            # Journal
            journal = article.findtext('.//Journal/Title')

            # Publication date
            pub_date = self._extract_date(article.find('.//Journal/JournalIssue/PubDate'))

            # DOI
            doi = None
            pubmed_data = article_elem.find('.//PubmedData')
            if pubmed_data is not None:
                for article_id in pubmed_data.findall('.//ArticleIdList/ArticleId'):
                    if article_id.get('IdType') == 'doi':
                        doi = article_id.text
                        break

            # MeSH terms
            mesh_terms = []
            for mesh in medline.findall('.//MeshHeadingList/MeshHeading/DescriptorName'):
                if mesh.text:
                    mesh_terms.append(mesh.text)

            # Keywords
            keywords = []
            for keyword in article.findall('.//KeywordList/Keyword'):
                if keyword.text:
                    keywords.append(keyword.text)

            return {
                'pmid': pmid,
                'doi': doi,
                'title': title,
                'abstract': abstract,
                'authors': authors,
                'publication': journal,
                'publication_date': pub_date,
                'url': f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/',
                'mesh_terms': mesh_terms,
                'keywords': keywords
            }

        except Exception as e:
            logger.error(f"Error parsing article: {e}")
            return None

    def _store_article_batch(self, articles: List[Dict]) -> int:
        """Store batch of articles in database with upsert logic."""
        if not articles:
            return 0

        inserted = 0
        updated = 0

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                for article in articles:
                    pmid = article['pmid']

                    # Check if article exists
                    cur.execute("""
                        SELECT id FROM document
                        WHERE source_id = %s AND external_id = %s
                    """, (self.source_id, pmid))

                    existing = cur.fetchone()

                    if existing:
                        # Update existing record (metadata may have changed)
                        # Convert empty strings to None for proper NULL handling
                        abstract = article.get('abstract') or None
                        doi = article.get('doi') or None
                        publication = article.get('publication') or None
                        pub_date = article.get('publication_date') or None

                        cur.execute("""
                            UPDATE document SET
                                doi = COALESCE(%s, doi),
                                title = %s,
                                abstract = COALESCE(%s, abstract),
                                authors = %s,
                                publication = COALESCE(%s, publication),
                                publication_date = COALESCE(%s, publication_date),
                                mesh_terms = %s,
                                keywords = %s,
                                updated_date = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (
                            doi,
                            article['title'],
                            abstract,
                            article.get('authors', []),
                            publication,
                            pub_date,
                            article.get('mesh_terms', []),
                            article.get('keywords', []),
                            existing[0]
                        ))
                        updated += 1
                    else:
                        # Insert new record
                        # Convert empty strings to None for proper NULL handling
                        abstract = article.get('abstract') or None
                        doi = article.get('doi') or None
                        publication = article.get('publication') or None
                        pub_date = article.get('publication_date') or None

                        cur.execute("""
                            INSERT INTO document (
                                source_id, external_id, doi, title, abstract,
                                authors, publication, publication_date,
                                url, mesh_terms, keywords
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            self.source_id,
                            pmid,
                            doi,
                            article['title'],
                            abstract,
                            article.get('authors', []),
                            publication,
                            pub_date,
                            article.get('url'),
                            article.get('mesh_terms', []),
                            article.get('keywords', [])
                        ))
                        inserted += 1

                conn.commit()

        logger.debug(f"Batch stored: {inserted} inserted, {updated} updated")
        return inserted + updated

    def import_file(self, filepath: Path, batch_size: int = 100) -> Dict:
        """
        Import articles from XML file using memory-efficient streaming.

        Args:
            filepath: Path to .xml.gz file
            batch_size: Number of articles to batch before database insertion

        Returns:
            Dict with import statistics
        """
        logger.info(f"Importing {filepath.name}")

        stats = {
            'filename': filepath.name,
            'articles_parsed': 0,
            'articles_imported': 0,
            'articles_updated': 0,
            'errors': 0
        }

        batch = []

        try:
            with gzip.open(filepath, 'rb') as gz_file:
                # Use iterparse for memory efficiency
                context = ET.iterparse(gz_file, events=('end',))

                for event, elem in context:
                    if elem.tag == 'PubmedArticle':
                        article = self._parse_article(elem)
                        if article:
                            batch.append(article)
                            stats['articles_parsed'] += 1

                            if len(batch) >= batch_size:
                                count = self._store_article_batch(batch)
                                stats['articles_imported'] += count
                                batch = []

                                if stats['articles_parsed'] % 1000 == 0:
                                    logger.info(f"{filepath.name}: Processed {stats['articles_parsed']} articles")
                        else:
                            stats['errors'] += 1

                        # Clear element to free memory
                        # Note: Standard library ElementTree doesn't support getparent()/getprevious()
                        # (those are lxml-specific methods), so we just clear the element itself
                        elem.clear()

                # Process remaining batch
                if batch:
                    count = self._store_article_batch(batch)
                    stats['articles_imported'] += count

            logger.info(f"{filepath.name}: Import complete - {stats['articles_parsed']} parsed, {stats['articles_imported']} imported")

            # Mark as processed in tracker
            if self.tracker:
                self.tracker.mark_processed(filepath.name, stats['articles_parsed'])

        except gzip.BadGzipFile as e:
            # Must catch BadGzipFile before OSError (it's a subclass)
            logger.error(f"{filepath.name}: Gzip decompression error: {e}")
            if self.tracker:
                self.tracker.mark_processed(filepath.name, 0, f"Invalid gzip file: {e}")
            stats['errors'] += 1

        except ET.ParseError as e:
            logger.error(f"{filepath.name}: XML parsing error: {e}")
            if self.tracker:
                self.tracker.mark_processed(filepath.name, 0, f"Invalid XML format: {e}")
            stats['errors'] += 1

        except (OSError, IOError) as e:
            logger.error(f"{filepath.name}: File system error: {e}")
            if self.tracker:
                self.tracker.mark_processed(filepath.name, 0, f"File system error: {e}")
            stats['errors'] += 1

        except Exception as e:
            logger.error(f"{filepath.name}: Import error: {e}", exc_info=True)
            if self.tracker:
                self.tracker.mark_processed(filepath.name, 0, str(e))
            stats['errors'] += 1

        return stats

    def import_all_files(self, file_type: Optional[str] = None) -> Dict:
        """
        Import all downloaded files.

        Args:
            file_type: 'baseline', 'update', or None for both

        Returns:
            Dict with overall statistics
        """
        overall_stats = {
            'files_processed': 0,
            'total_articles': 0,
            'total_errors': 0
        }

        # Determine which directories to process
        dirs_to_process = []
        if file_type in (None, 'baseline'):
            dirs_to_process.append(self.baseline_dir)
        if file_type in (None, 'update'):
            dirs_to_process.append(self.update_dir)

        for directory in dirs_to_process:
            for filepath in sorted(directory.glob('*.xml.gz')):
                # Skip if already processed
                if self.tracker and self.tracker.is_file_processed(filepath.name):
                    logger.info(f"{filepath.name}: Already processed, skipping")
                    continue

                stats = self.import_file(filepath)
                overall_stats['files_processed'] += 1
                overall_stats['total_articles'] += stats['articles_imported']
                overall_stats['total_errors'] += stats['errors']

        return overall_stats
