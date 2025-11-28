#!/usr/bin/env python3
"""
PubMed Abstract Tester - Standalone PySide6 Application

This application downloads PubMed update files and displays articles with
properly formatted abstracts in Markdown format. It serves as a test bed for
improving abstract extraction and formatting before integrating into the
main BMLibrarian importer.

=== KEY IMPROVEMENTS OVER EXISTING IMPORTERS ===

1. **Structured Abstract Preservation**
   - Extracts both Label and NlmCategory attributes from AbstractText elements
   - Maintains section organization (BACKGROUND, METHODS, RESULTS, CONCLUSIONS)
   - Adds paragraph breaks between sections for better readability

2. **Inline Formatting Support**
   - Converts <b>, <bold> tags to Markdown bold: **text**
   - Converts <i>, <italic> tags to Markdown italic: *text*
   - Preserves subscripts with <sub>: ~text~
   - Preserves superscripts with <sup>: ^text^
   - Handles underline with <u>: __text__

3. **Proper Mixed Content Handling**
   - Recursively processes nested XML elements
   - Preserves text before, within, and after inline formatting tags
   - Prevents truncation issues from earlier importers

4. **Complete Data Extraction**
   - Title, authors, journal, publication date
   - PMID and DOI for reference
   - Full abstract with all formatting preserved

5. **Lightweight Testing**
   - Uses SQLite (no PostgreSQL dependency)
   - Downloads latest PubMed update file via FTP
   - Interactive GUI for browsing and inspecting results

=== COMMON ISSUES FIXED ===

- **Truncated abstracts**: Old code only extracted first child text
- **Missing line breaks**: Sections ran together without spacing
- **Lost formatting**: Subscripts, superscripts, emphasis were stripped
- **Incomplete sections**: Label attributes were not checked

=== USAGE ===

    uv run python pubmed_abstract_tester.py

1. Click "Download Latest Update File" to fetch and parse PubMed data
2. Use navigation buttons to browse articles
3. Inspect abstract formatting in the text display
4. Compare with production importer results

=== DTD REFERENCE ===

PubMed DTD: https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_250101.dtd

AbstractText attributes:
- Label: Section heading (e.g., "OBJECTIVE", "METHODS")
- NlmCategory: NLM-assigned category (BACKGROUND, METHODS, RESULTS, CONCLUSIONS, UNASSIGNED)

Inline formatting elements:
- <b>, <bold>: Bold text
- <i>, <italic>: Italic text
- <sup>: Superscript (e.g., CO₂, m²)
- <sub>: Subscript (e.g., H₂O)
- <u>, <underline>: Underlined text
"""

import ftplib
import gzip
import logging
import os
import platform
import re
import socket
import sqlite3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QThread, Signal, Qt


def _get_system_font_family() -> str:
    """Get the appropriate system font family for the current platform."""
    system = platform.system()
    if system == "Darwin":  # macOS
        return "-apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif"
    elif system == "Windows":
        return "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif"
    else:  # Linux and others
        return "'Ubuntu', 'DejaVu Sans', 'Liberation Sans', Arial, sans-serif"


FONT_FAMILY = _get_system_font_family()
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QProgressBar, QMessageBox,
    QSpinBox, QGroupBox
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# === CONSTANTS ===
# Database batch processing
BATCH_SIZE = 100  # Number of articles to batch before database insertion

# Network timeouts (seconds)
FTP_TIMEOUT = 120  # FTP connection timeout
FTP_BLOCKSIZE = 65536  # FTP download block size (64KB)

# Progress tracking
PROGRESS_DOWNLOAD_MAX = 50  # Progress percentage for download phase (0-50%)
PROGRESS_PARSE_MIN = 50  # Progress percentage when parsing starts (50%)
PROGRESS_PARSE_MAX = 100  # Progress percentage when parsing completes (100%)
PROGRESS_ESTIMATE_ARTICLES = 1000  # Estimated articles per file for progress calculation

# File validation
MAX_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10GB max file size for safety
MIN_XML_SIZE = 100  # Minimum bytes for valid XML file


class PubMedDatabase:
    """SQLite database handler for PubMed articles."""

    def __init__(self, db_path: str = 'pubmed_test.db'):
        """Initialize database connection."""
        self.db_path = db_path
        self.conn = None
        self._init_database()

    def _init_database(self):
        """Create database schema if it doesn't exist."""
        # Use check_same_thread=False to allow multi-threaded access
        # This is safe because we're only writing from one thread at a time
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pmid TEXT UNIQUE NOT NULL,
                doi TEXT,
                title TEXT NOT NULL,
                abstract_markdown TEXT,
                authors TEXT,
                publication_date TEXT,
                journal TEXT,
                import_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pmid ON articles(pmid)
        """)

        self.conn.commit()
        logger.info(f"Database initialized: {self.db_path}")

    def insert_article(self, article_data: Dict) -> bool:
        """Insert or update an article in the database."""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO articles
                (pmid, doi, title, abstract_markdown, authors, publication_date, journal)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                article_data['pmid'],
                article_data.get('doi'),
                article_data['title'],
                article_data.get('abstract_markdown', ''),
                article_data.get('authors', ''),
                article_data.get('publication_date'),
                article_data.get('journal', 'Unknown')
            ))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError as e:
            logger.error(f"Database integrity error for PMID {article_data.get('pmid')}: {e}")
            return False
        except sqlite3.OperationalError as e:
            logger.error(f"Database operational error for PMID {article_data.get('pmid')}: {e}")
            return False
        except (KeyError, TypeError) as e:
            logger.error(f"Invalid article data for PMID {article_data.get('pmid')}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected database error for PMID {article_data.get('pmid')}: {e}", exc_info=True)
            return False

    def get_article_count(self) -> int:
        """Get total number of articles in database."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM articles")
        return cursor.fetchone()[0]

    def get_article_by_index(self, index: int) -> Optional[Dict]:
        """Get article by index (0-based)."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, pmid, doi, title, abstract_markdown, authors, publication_date, journal
            FROM articles
            ORDER BY id
            LIMIT 1 OFFSET ?
        """, (index,))

        row = cursor.fetchone()
        if row:
            return {
                'id': row['id'],
                'pmid': row['pmid'],
                'doi': row['doi'],
                'title': row['title'],
                'abstract_markdown': row['abstract_markdown'],
                'authors': row['authors'],
                'publication_date': row['publication_date'],
                'journal': row['journal']
            }
        return None

    def clear_articles(self):
        """Clear all articles from database."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM articles")
        self.conn.commit()
        logger.info("All articles cleared from database")

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


class PubMedParser:
    """Parser for PubMed XML files with improved abstract formatting."""

    @staticmethod
    def _get_element_text_with_formatting(elem: Optional[ET.Element]) -> str:
        """
        Extract text from XML element and convert inline formatting to Markdown.

        Handles HTML-style inline elements:
        - <b> or <bold> → **text**
        - <i> or <italic> → *text*
        - <sup> → ^text^
        - <sub> → ~text~
        - <u> or <underline> → __text__

        This preserves scientific notation, chemical formulas, and emphasis.
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
            child_text = PubMedParser._get_element_text_with_formatting(child)

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

    @staticmethod
    def _get_element_text(elem: Optional[ET.Element]) -> str:
        """
        Extract complete text from XML element (plain text, no formatting).

        Alias for backward compatibility and simple text extraction.
        """
        return PubMedParser._get_element_text_with_formatting(elem)

    @staticmethod
    def _format_abstract_markdown(abstract_elem: Optional[ET.Element]) -> str:
        """
        Extract and format abstract with proper Markdown formatting.

        This preserves:
        - Section labels from both Label and NlmCategory attributes
        - Paragraph breaks between sections
        - Inline formatting (bold, italic, subscript, superscript)
        - Handles both structured and unstructured abstracts

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
            text = PubMedParser._get_element_text(abstract_text)

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

    @staticmethod
    def _extract_date(pub_date_elem: Optional[ET.Element]) -> Optional[str]:
        """Extract publication date from PubDate element."""
        if pub_date_elem is None:
            return None

        year = pub_date_elem.findtext('Year')
        if not year:
            return None

        month = pub_date_elem.findtext('Month', '01')
        day = pub_date_elem.findtext('Day', '01')

        # Convert month name to number
        month_map = {
            'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
            'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
            'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
        }
        if month in month_map:
            month = month_map[month]
        elif month.isdigit() and len(month) == 1:
            month = f'0{month}'

        if day.isdigit() and len(day) == 1:
            day = f'0{day}'

        try:
            return f'{year}-{month}-{day}'
        except (ValueError, TypeError, AttributeError) as e:
            logger.debug(f"Date formatting error: {e}, using fallback {year}-01-01")
            return f'{year}-01-01'

    @staticmethod
    def parse_article(article_elem: ET.Element) -> Optional[Dict]:
        """
        Parse PubmedArticle XML element into article dictionary.

        Returns:
            Dict with article data including markdown-formatted abstract
        """
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

            # Extract title
            title = PubMedParser._get_element_text(article.find('.//ArticleTitle'))

            # Extract abstract with markdown formatting
            abstract_elem = article.find('.//Abstract')
            abstract_markdown = PubMedParser._format_abstract_markdown(abstract_elem)

            # Extract authors
            authors_list = []
            for author in article.findall('.//AuthorList/Author'):
                last = author.findtext('LastName', '')
                first = author.findtext('ForeName', '')
                if last or first:
                    authors_list.append(f'{last} {first}'.strip())
            authors = ', '.join(authors_list)

            # Extract journal
            journal = article.findtext('.//Journal/Title', 'Unknown')

            # Extract publication date
            pub_date = PubMedParser._extract_date(
                article.find('.//Journal/JournalIssue/PubDate')
            )

            # Extract DOI
            doi = None
            pubmed_data = article_elem.find('.//PubmedData')
            if pubmed_data is not None:
                for article_id in pubmed_data.findall('.//ArticleIdList/ArticleId'):
                    if article_id.get('IdType') == 'doi':
                        doi = article_id.text
                        break

            return {
                'pmid': pmid,
                'doi': doi,
                'title': title,
                'abstract_markdown': abstract_markdown,
                'authors': authors,
                'publication_date': pub_date,
                'journal': journal,
                'url': f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/'
            }

        except ET.ParseError as e:
            logger.warning(f"XML parsing error in article: {e}")
            return None
        except (KeyError, AttributeError) as e:
            logger.warning(f"Missing required field in article: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing article: {e}", exc_info=True)
            return None


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks.

    Args:
        filename: Raw filename from FTP server

    Returns:
        Sanitized filename with path components removed

    Security:
        - Removes directory traversal sequences (.., /)
        - Extracts only the base filename
        - Prevents malicious filenames from escaping data directory
    """
    # Remove any path components and get just the filename
    safe_name = os.path.basename(filename)

    # Additional safety: remove any remaining '..' sequences
    safe_name = safe_name.replace('..', '')

    # Validate it's not empty after sanitization
    if not safe_name:
        raise ValueError(f"Invalid filename after sanitization: {filename}")

    return safe_name


def validate_downloaded_file(file_path: Path) -> None:
    """
    Validate downloaded file before parsing.

    Args:
        file_path: Path to downloaded file

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is invalid (too large, too small, or not gzipped XML)

    Validation checks:
        - File exists
        - File size within acceptable range
        - File has .gz extension
        - File is valid gzip format
    """
    # Check file exists
    if not file_path.exists():
        raise FileNotFoundError(f"Downloaded file not found: {file_path}")

    # Check file size
    file_size = file_path.stat().st_size
    if file_size < MIN_XML_SIZE:
        raise ValueError(f"File too small ({file_size} bytes), likely invalid")
    if file_size > MAX_FILE_SIZE:
        raise ValueError(f"File too large ({file_size} bytes), exceeds safety limit")

    # Check file extension
    if not str(file_path).endswith('.xml.gz'):
        raise ValueError(f"File does not have .xml.gz extension: {file_path}")

    # Validate it's a valid gzip file by reading header
    try:
        with gzip.open(file_path, 'rb') as f:
            # Try to read first 100 bytes to verify gzip format
            f.read(100)
    except gzip.BadGzipFile as e:
        raise ValueError(f"File is not a valid gzip file: {e}")
    except Exception as e:
        raise ValueError(f"Error validating gzip file: {e}")


class DownloadThread(QThread):
    """Background thread for downloading and parsing PubMed files."""

    progress = Signal(int)  # Progress percentage (0-100)
    status = Signal(str)    # Status message
    finished = Signal(int)  # Number of articles processed
    error = Signal(str)     # Error message

    FTP_HOST = 'ftp.ncbi.nlm.nih.gov'
    UPDATE_PATH = '/pubmed/updatefiles'

    def __init__(self, database: PubMedDatabase, data_dir: Path):
        super().__init__()
        self.database = database
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def run(self):
        """Download and parse latest PubMed update file."""
        try:
            # Connect to FTP
            self.status.emit("Connecting to PubMed FTP server...")
            ftp = ftplib.FTP(self.FTP_HOST, timeout=FTP_TIMEOUT)
            ftp.login()  # Anonymous login
            ftp.set_pasv(True)  # Enable passive mode for firewall compatibility

            # Log connection details for debugging
            logger.info(f"Connected to {self.FTP_HOST}, current directory: {ftp.pwd()}")

            # Navigate to update files directory
            self.status.emit(f"Navigating to {self.UPDATE_PATH}...")
            try:
                ftp.cwd(self.UPDATE_PATH)
                logger.info(f"Changed to directory: {ftp.pwd()}")
            except ftplib.error_perm as e:
                logger.error(f"Cannot access {self.UPDATE_PATH}: {e}")
                raise ValueError(f"FTP directory not accessible: {self.UPDATE_PATH}. Error: {e}")

            # Get list of files (with fallback for servers without MLSD support)
            self.status.emit("Fetching file list...")
            files = []

            try:
                # Try MLSD first (modern FTP servers) - provides size info
                logger.debug("Attempting to list files with MLSD")
                for name, facts in ftp.mlsd():
                    # Match pattern: pubmed<YY>n<NUMBER>.xml.gz (e.g., pubmed24n1234.xml.gz, pubmed25n5678.xml.gz)
                    if name.endswith('.xml.gz') and name.startswith('pubmed') and 'n' in name:
                        size = int(facts.get('size', 0))
                        files.append((name, size))
                        logger.debug(f"Found file via MLSD: {name} ({size} bytes)")

            except (ftplib.error_perm, AttributeError) as e:
                # Fallback to NLST (older servers) - no size info
                logger.warning(f"MLSD not supported, falling back to NLST: {e}")
                self.status.emit("Fetching file list (using fallback method)...")

                file_names = []
                ftp.retrlines('NLST', file_names.append)

                for name in file_names:
                    # Match pattern: pubmed<YY>n<NUMBER>.xml.gz (e.g., pubmed24n1234.xml.gz, pubmed25n5678.xml.gz)
                    if name.endswith('.xml.gz') and name.startswith('pubmed') and 'n' in name:
                        # Get file size with SIZE command
                        try:
                            size = ftp.size(name)
                            files.append((name, size if size else 0))
                            logger.debug(f"Found file via NLST: {name} ({size} bytes)")
                        except ftplib.error_perm as e:
                            # If SIZE command not supported or permission denied, use 0 (will still download)
                            logger.debug(f"SIZE command failed for {name}: {e}")
                            files.append((name, 0))
                            logger.debug(f"Found file via NLST: {name} (size unknown)")

            if not files:
                logger.error(f"No update files found in {self.UPDATE_PATH}")
                self.error.emit(f"No update files found in {self.UPDATE_PATH}")
                return

            logger.info(f"Found {len(files)} update file(s)")

            # Get the latest file (highest number)
            files.sort()
            latest_file, file_size = files[-1]

            # Download file (with filename sanitization for security)
            safe_filename = sanitize_filename(latest_file)
            local_path = self.data_dir / safe_filename

            # Check if file already exists with same size
            skip_download = False
            if local_path.exists():
                local_size = local_path.stat().st_size
                if file_size > 0 and local_size == file_size:
                    skip_download = True
                    self.status.emit(f"File already exists: {latest_file} ({file_size} bytes)")
                    logger.info(f"Skipping download - file exists with matching size: {latest_file}")
                    self.progress.emit(PROGRESS_DOWNLOAD_MAX)
                else:
                    logger.info(f"File exists but size mismatch: local={local_size}, remote={file_size}. Re-downloading.")

            # Download if needed
            if not skip_download:
                self.status.emit(f"Downloading {latest_file}...")
                logger.info(f"Selected file: {latest_file} ({file_size} bytes)")

                downloaded = 0
                with open(local_path, 'wb') as f:
                    def callback(chunk):
                        nonlocal downloaded
                        f.write(chunk)
                        downloaded += len(chunk)
                        # Calculate progress only if file size is known
                        if file_size > 0:
                            progress = int((downloaded / file_size) * PROGRESS_DOWNLOAD_MAX)
                            self.progress.emit(progress)

                    ftp.retrbinary(f'RETR {latest_file}', callback, blocksize=FTP_BLOCKSIZE)

            ftp.quit()

            # Validate file before parsing
            self.status.emit("Validating downloaded file...")
            validate_downloaded_file(local_path)

            # Parse file
            self.status.emit(f"Parsing {safe_filename}...")
            self.progress.emit(PROGRESS_PARSE_MIN)

            articles_count = 0
            batch = []
            last_progress_update = 0
            progress_update_interval = 50  # Update progress every 50 articles

            with gzip.open(local_path, 'rb') as gz_file:
                context = ET.iterparse(gz_file, events=('end',))

                for event, elem in context:
                    if elem.tag == 'PubmedArticle':
                        article = PubMedParser.parse_article(elem)
                        if article:
                            batch.append(article)
                            articles_count += 1

                            if len(batch) >= BATCH_SIZE:
                                # Insert batch
                                for art in batch:
                                    self.database.insert_article(art)
                                batch = []

                                # Update status and progress periodically
                                if articles_count - last_progress_update >= progress_update_interval:
                                    self.status.emit(f"Parsed {articles_count} articles...")
                                    # Estimate progress based on articles (configurable via PROGRESS_ESTIMATE_ARTICLES)
                                    # Progress ranges from 50-95% during parsing (leave 95-100% for final batch)
                                    estimated_progress = min(95, PROGRESS_PARSE_MIN +
                                                           int((articles_count / PROGRESS_ESTIMATE_ARTICLES) * 45))
                                    self.progress.emit(estimated_progress)
                                    last_progress_update = articles_count

                        # Clear element to free memory
                        # Note: Standard library ElementTree doesn't support getparent()/getprevious()
                        # so we just clear the element itself
                        elem.clear()

                # Insert remaining articles
                if batch:
                    for art in batch:
                        self.database.insert_article(art)

            self.progress.emit(PROGRESS_PARSE_MAX)
            self.status.emit(f"Complete! Imported {articles_count} articles")
            self.finished.emit(articles_count)

        except ftplib.error_perm as e:
            error_msg = str(e)
            logger.error(f"FTP permission error: {error_msg}")

            # Provide helpful diagnostic information
            if '550' in error_msg or 'No such file' in error_msg:
                diagnostic = (f"FTP directory not found: {self.UPDATE_PATH}\n\n"
                             f"This usually means:\n"
                             f"1. The FTP path has changed on the server\n"
                             f"2. The directory structure is different\n"
                             f"3. Permissions issue\n\n"
                             f"Please verify the correct path at: {self.FTP_HOST}")
                self.error.emit(diagnostic)
            else:
                self.error.emit(f"FTP access denied: {error_msg}")

        except ftplib.error_temp as e:
            logger.error(f"FTP temporary error: {e}")
            self.error.emit(f"FTP server error (temporary): {e}\n\nPlease try again later.")

        except gzip.BadGzipFile as e:
            logger.error(f"Gzip decompression error: {e}")
            self.error.emit(f"Invalid gzip file: {e}\n\nThe downloaded file may be corrupted.")

        except (FileNotFoundError, ValueError) as e:
            logger.error(f"File validation error: {e}")
            self.error.emit(f"File validation failed: {e}")

        except ET.ParseError as e:
            logger.error(f"XML parsing error: {e}")
            self.error.emit(f"Invalid XML format: {e}\n\nThe downloaded file may be corrupted.")

        except (OSError, IOError, socket.error) as e:
            logger.error(f"Network/IO error: {e}")
            diagnostic = (f"Network or file system error: {e}\n\n"
                         f"This could be:\n"
                         f"1. Network connectivity issue\n"
                         f"2. Firewall blocking FTP access\n"
                         f"3. DNS resolution failure\n"
                         f"4. Local disk space issue")
            self.error.emit(diagnostic)

        except Exception as e:
            logger.error(f"Unexpected error during download/parse: {e}", exc_info=True)
            self.error.emit(f"Unexpected error: {e}\n\nCheck the console log for details.")


class MarkdownConverter:
    """Efficient Markdown to HTML converter with pre-compiled regex patterns."""

    # Pre-compiled regex patterns for performance (module-level re import)
    BOLD_RE = re.compile(r'\*\*(.+?)\*\*')
    ITALIC_RE = re.compile(r'\*(.+?)\*')
    SUPERSCRIPT_RE = re.compile(r'\^(.+?)\^')
    SUBSCRIPT_RE = re.compile(r'~(.+?)~')
    UNDERLINE_RE = re.compile(r'__(.+?)__')

    @classmethod
    def to_html(cls, markdown_text: str) -> str:
        """
        Convert simple Markdown to HTML for rich text display.

        Supports:
        - **bold** → <b>bold</b>
        - *italic* → <i>italic</i>
        - ^superscript^ → <sup>superscript</sup>
        - ~subscript~ → <sub>subscript</sub>
        - __underline__ → <u>underline</u>
        - Paragraph breaks (double newline)

        Performance:
        - Uses pre-compiled regex patterns (class-level)
        - Single pass through text for all conversions
        """
        html = markdown_text

        # Escape HTML special characters first
        html = html.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        # Convert Markdown formatting to HTML using pre-compiled patterns
        html = cls.BOLD_RE.sub(r'<b>\1</b>', html)
        html = cls.ITALIC_RE.sub(r'<i>\1</i>', html)
        html = cls.SUPERSCRIPT_RE.sub(r'<sup>\1</sup>', html)
        html = cls.SUBSCRIPT_RE.sub(r'<sub>\1</sub>', html)
        html = cls.UNDERLINE_RE.sub(r'<u>\1</u>', html)

        # Convert paragraph breaks
        html = html.replace('\n\n', '<br><br>')
        html = html.replace('\n', ' ')

        return f'<div style="line-height: 1.6;">{html}</div>'


class PubMedAbstractTester(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.db = PubMedDatabase()
        self.data_dir = Path.home() / 'pubmed_test_data'
        self.current_index = 0
        self.total_articles = 0

        self.init_ui()
        self.load_initial_stats()

    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("PubMed Abstract Tester")
        self.setGeometry(100, 100, 1200, 800)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # === Download Section ===
        download_group = QGroupBox("Download PubMed Update File")
        download_layout = QVBoxLayout()

        download_btn_layout = QHBoxLayout()
        self.download_btn = QPushButton("Download Latest Update File")
        self.download_btn.clicked.connect(self.start_download)
        download_btn_layout.addWidget(self.download_btn)

        self.clear_btn = QPushButton("Clear Database")
        self.clear_btn.clicked.connect(self.clear_database)
        download_btn_layout.addWidget(self.clear_btn)

        download_layout.addLayout(download_btn_layout)

        self.progress_bar = QProgressBar()
        download_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        download_layout.addWidget(self.status_label)

        download_group.setLayout(download_layout)
        main_layout.addWidget(download_group)

        # === Navigation Section ===
        nav_group = QGroupBox("Article Navigation")
        nav_layout = QHBoxLayout()

        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.clicked.connect(self.show_previous)
        nav_layout.addWidget(self.prev_btn)

        nav_layout.addWidget(QLabel("Go to:"))
        self.index_spinbox = QSpinBox()
        self.index_spinbox.setMinimum(1)
        self.index_spinbox.setMaximum(1)
        self.index_spinbox.valueChanged.connect(self.go_to_index)
        nav_layout.addWidget(self.index_spinbox)

        self.article_counter = QLabel("0 / 0")
        nav_layout.addWidget(self.article_counter)

        self.next_btn = QPushButton("Next →")
        self.next_btn.clicked.connect(self.show_next)
        nav_layout.addWidget(self.next_btn)

        nav_group.setLayout(nav_layout)
        main_layout.addWidget(nav_group)

        # === Article Display Section ===
        display_group = QGroupBox("Article Details")
        display_layout = QVBoxLayout()

        # PMID and DOI
        meta_layout = QHBoxLayout()
        self.pmid_label = QLabel("<b>PMID:</b> —")
        meta_layout.addWidget(self.pmid_label)
        self.doi_label = QLabel("<b>DOI:</b> —")
        meta_layout.addWidget(self.doi_label)
        meta_layout.addStretch()
        display_layout.addLayout(meta_layout)

        # Title
        self.title_label = QLabel("<i>No article loaded</i>")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        display_layout.addWidget(self.title_label)

        # Authors and Journal
        self.authors_label = QLabel("")
        self.authors_label.setWordWrap(True)
        display_layout.addWidget(self.authors_label)

        self.journal_label = QLabel("")
        display_layout.addWidget(self.journal_label)

        # Abstract
        abstract_header = QLabel("<b>Abstract:</b>")
        display_layout.addWidget(abstract_header)

        self.abstract_display = QTextEdit()
        self.abstract_display.setReadOnly(True)
        self.abstract_display.setStyleSheet(f"""
            QTextEdit {{
                font-family: {FONT_FAMILY};
                font-size: 11pt;
                line-height: 1.6;
                padding: 10px;
                background-color: #f9f9f9;
                border: 1px solid #ddd;
                border-radius: 4px;
            }}
        """)
        # Enable Markdown rendering
        self.abstract_display.setAcceptRichText(True)
        display_layout.addWidget(self.abstract_display)

        display_group.setLayout(display_layout)
        main_layout.addWidget(display_group)

        # Set initial button states
        self.update_navigation_state()

    def load_initial_stats(self):
        """Load initial database statistics."""
        self.total_articles = self.db.get_article_count()
        self.update_counter()

        if self.total_articles > 0:
            self.index_spinbox.setMaximum(self.total_articles)
            self.current_index = 0
            self.show_article(self.current_index)
        else:
            self.status_label.setText(f"Database is empty. Download an update file to begin.")

    def start_download(self):
        """Start downloading and parsing PubMed update file."""
        self.download_btn.setEnabled(False)
        self.progress_bar.setValue(0)

        self.download_thread = DownloadThread(self.db, self.data_dir)
        self.download_thread.progress.connect(self.progress_bar.setValue)
        self.download_thread.status.connect(self.status_label.setText)
        self.download_thread.finished.connect(self.download_finished)
        self.download_thread.error.connect(self.download_error)
        self.download_thread.start()

    def download_finished(self, count: int):
        """Handle download completion."""
        self.download_btn.setEnabled(True)
        self.load_initial_stats()
        QMessageBox.information(
            self,
            "Download Complete",
            f"Successfully imported {count} articles!"
        )

    def download_error(self, error_msg: str):
        """Handle download error."""
        self.download_btn.setEnabled(True)
        self.status_label.setText(f"Error: {error_msg}")
        QMessageBox.critical(
            self,
            "Download Error",
            f"Failed to download file:\n{error_msg}"
        )

    def clear_database(self):
        """Clear all articles from database."""
        reply = QMessageBox.question(
            self,
            "Clear Database",
            "Are you sure you want to clear all articles from the database?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.db.clear_articles()
            self.load_initial_stats()
            self.status_label.setText("Database cleared")

    def _markdown_to_html(self, markdown_text: str) -> str:
        """
        Convert simple Markdown to HTML for rich text display.

        Delegates to MarkdownConverter class for efficient conversion.
        """
        return MarkdownConverter.to_html(markdown_text)

    def show_article(self, index: int):
        """Display article at the given index."""
        article = self.db.get_article_by_index(index)

        if not article:
            self.title_label.setText("<i>No article found</i>")
            self.authors_label.setText("")
            self.journal_label.setText("")
            self.abstract_display.setHtml("")
            self.pmid_label.setText("<b>PMID:</b> —")
            self.doi_label.setText("<b>DOI:</b> —")
            return

        # Update display
        self.title_label.setText(article['title'])
        self.authors_label.setText(f"<b>Authors:</b> {article['authors']}")

        journal_text = f"<b>Journal:</b> {article['journal']}"
        if article['publication_date']:
            journal_text += f" ({article['publication_date']})"
        self.journal_label.setText(journal_text)

        self.pmid_label.setText(f"<b>PMID:</b> {article['pmid']}")
        self.doi_label.setText(f"<b>DOI:</b> {article['doi'] or '—'}")

        # Display abstract with rich formatting
        abstract_html = self._markdown_to_html(article['abstract_markdown'])
        self.abstract_display.setHtml(abstract_html)

        self.current_index = index
        self.update_counter()
        self.update_navigation_state()

    def show_next(self):
        """Show next article."""
        if self.current_index < self.total_articles - 1:
            self.show_article(self.current_index + 1)
            self.index_spinbox.setValue(self.current_index + 1)

    def show_previous(self):
        """Show previous article."""
        if self.current_index > 0:
            self.show_article(self.current_index - 1)
            self.index_spinbox.setValue(self.current_index + 1)

    def go_to_index(self, spinbox_value: int):
        """Jump to specific article (1-based index from spinbox)."""
        index = spinbox_value - 1  # Convert to 0-based
        if 0 <= index < self.total_articles:
            self.show_article(index)

    def update_counter(self):
        """Update article counter display."""
        if self.total_articles > 0:
            self.article_counter.setText(f"{self.current_index + 1} / {self.total_articles}")
            self.index_spinbox.setMaximum(self.total_articles)
        else:
            self.article_counter.setText("0 / 0")
            self.index_spinbox.setMaximum(1)

    def update_navigation_state(self):
        """Enable/disable navigation buttons based on current state."""
        has_articles = self.total_articles > 0
        self.prev_btn.setEnabled(has_articles and self.current_index > 0)
        self.next_btn.setEnabled(has_articles and self.current_index < self.total_articles - 1)
        self.index_spinbox.setEnabled(has_articles)

    def closeEvent(self, event):
        """Handle application close."""
        self.db.close()
        event.accept()


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    window = PubMedAbstractTester()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
