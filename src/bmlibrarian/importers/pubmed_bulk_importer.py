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
import json
import logging
import os
import queue
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List, Tuple, Callable
import backoff

from bmlibrarian.database import get_db_manager

logger = logging.getLogger(__name__)

# Type alias for progress callback: (message: str) -> None
ProgressCallback = Callable[[str], None]

# Type alias for cancel check: () -> bool
CancelCheck = Callable[[], bool]


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


class ImportQueue:
    """Thread-safe queue ensuring sequential file processing by file number.

    PubMed baseline files are numbered sequentially (pubmed25n0001.xml.gz,
    pubmed25n0002.xml.gz, etc.) and must be imported in order because later
    files may contain corrections/retractions that supersede earlier versions.

    This queue accepts files in any order but only releases them for import
    when they are the next expected sequential file.
    """

    # Regex pattern to extract file number from PubMed filenames
    # Matches: pubmed25n0001.xml.gz, pubmed24n1274.xml.gz, etc.
    FILE_NUMBER_PATTERN = r'pubmed\d+n(\d+)\.xml\.gz$'

    def __init__(self, start_from: int = 1):
        """
        Initialize the import queue.

        Args:
            start_from: First file number to expect (1-indexed)
        """
        import re
        self._pattern = re.compile(self.FILE_NUMBER_PATTERN)
        self._queue: Dict[int, Path] = {}  # file_number -> filepath
        self._next_to_import: int = start_from
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._download_complete = False
        self._total_files = 0
        self._imported_count = 0
        self._skipped_files: set = set()  # Track files that were skipped (already processed)

    def _extract_file_number(self, filepath: Path) -> Optional[int]:
        """Extract the sequential file number from a PubMed filename.

        Args:
            filepath: Path to the file

        Returns:
            The file number (1-indexed) or None if not a valid filename
        """
        match = self._pattern.search(filepath.name)
        if match:
            return int(match.group(1))
        return None

    def set_total_files(self, total: int) -> None:
        """Set the total number of files expected."""
        with self._lock:
            self._total_files = total

    def add_downloaded(self, filepath: Path) -> bool:
        """
        Add a downloaded file to the queue.

        Args:
            filepath: Path to the downloaded file

        Returns:
            True if added successfully, False if invalid filename
        """
        file_num = self._extract_file_number(filepath)
        if file_num is None:
            logger.warning(f"Could not extract file number from: {filepath.name}")
            return False

        with self._condition:
            self._queue[file_num] = filepath
            logger.debug(f"Added to queue: {filepath.name} (file #{file_num})")
            self._condition.notify_all()
            return True

    def mark_skipped(self, filepath: Path) -> None:
        """Mark a file as skipped (already processed)."""
        file_num = self._extract_file_number(filepath)
        if file_num is not None:
            with self._lock:
                self._skipped_files.add(file_num)

    def get_next_for_import(self, timeout: float = 5.0) -> Optional[Path]:
        """
        Get the next file for import if it's the expected sequence number.

        This method blocks until:
        - The next sequential file is available
        - The timeout expires
        - All downloads are complete and no more files expected

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            Path to the next file to import, or None if should wait/stop
        """
        with self._condition:
            deadline = time.time() + timeout

            while True:
                # Skip any files that were marked as already processed
                while self._next_to_import in self._skipped_files:
                    logger.debug(f"Skipping file #{self._next_to_import} (already processed)")
                    self._next_to_import += 1

                # Check if next file is available
                if self._next_to_import in self._queue:
                    filepath = self._queue.pop(self._next_to_import)
                    self._next_to_import += 1
                    self._imported_count += 1
                    return filepath

                # Check if we're done
                if self._download_complete and not self._queue:
                    return None

                # Wait for more files or timeout
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None

                self._condition.wait(timeout=remaining)

    def mark_download_complete(self) -> None:
        """Signal that all downloads are finished."""
        with self._condition:
            self._download_complete = True
            self._condition.notify_all()

    def is_complete(self) -> bool:
        """Check if all downloads are complete and queue is empty."""
        with self._lock:
            return self._download_complete and not self._queue

    def get_status(self) -> Dict:
        """Get current queue status for progress reporting."""
        with self._lock:
            return {
                'next_expected': self._next_to_import,
                'queued_count': len(self._queue),
                'imported_count': self._imported_count,
                'total_files': self._total_files,
                'download_complete': self._download_complete,
                'queued_numbers': sorted(self._queue.keys())[:10]  # First 10 for display
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

    def _download_file(
        self,
        ftp: ftplib.FTP,
        filename: str,
        dest_path: Path,
        expected_size: int,
        max_retries: int = 5,
        current_path: str = None,
        progress_callback: Optional[ProgressCallback] = None
    ) -> Tuple[bool, ftplib.FTP]:
        """
        Download file from FTP with resume capability.

        Args:
            ftp: FTP connection
            filename: Name of file to download
            dest_path: Local destination path
            expected_size: Expected file size in bytes
            max_retries: Maximum retry attempts
            current_path: Current FTP directory path for reconnection
            progress_callback: Optional callback for progress messages

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
                if start_pos > 0:
                    start_mb = start_pos / (1024 * 1024)
                    msg = f"{filename}: Resuming from {start_mb:.1f} MB"
                    logger.info(msg)
                    if progress_callback:
                        progress_callback(f"[DOWNLOAD] {msg}")
                else:
                    logger.info(f"{filename}: Downloading ({expected_size} bytes)")

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

                # Verify gzip integrity by reading entire file (checks CRC32)
                try:
                    with gzip.open(dest_path, 'rb') as gz:
                        while gz.read(65536):  # Read in 64KB chunks to verify full file
                            pass
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
                    msg = f"{filename}: Connection error, retrying in {retry_delay}s ({attempt + 2}/{max_retries})"
                    logger.info(msg)
                    if progress_callback:
                        progress_callback(f"[DOWNLOAD ERROR] {msg}")
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
                    msg = f"{filename}: Error, retrying in {retry_delay}s ({attempt + 2}/{max_retries})"
                    logger.info(msg)
                    if progress_callback:
                        progress_callback(f"[DOWNLOAD ERROR] {msg}")
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

    def download_baseline(
        self,
        skip_existing: bool = True,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[CancelCheck] = None
    ) -> int:
        """
        Download PubMed baseline files.

        Args:
            skip_existing: Skip files already downloaded (default: True)
            progress_callback: Optional callback for progress messages
            cancel_check: Optional callback to check if operation should be cancelled

        Returns:
            Number of files downloaded
        """
        logger.info("Starting baseline download")
        if progress_callback:
            progress_callback("[DOWNLOAD] Connecting to NCBI FTP server...")

        ftp = self._create_ftp_connection()
        ftp.cwd(self.BASELINE_PATH)
        downloaded = 0

        try:
            files = self._get_remote_file_list(ftp, self.BASELINE_PATH)
            total_files = len(files)
            logger.info(f"Found {total_files} baseline files")
            if progress_callback:
                progress_callback(f"[INIT] Found {total_files} baseline files on server")

            for idx, (filename, size) in enumerate(files, 1):
                # Check for cancellation
                if cancel_check and cancel_check():
                    if progress_callback:
                        progress_callback("[DOWNLOAD] Cancelled by user")
                    break

                if skip_existing and self.tracker and self.tracker.is_file_downloaded(filename):
                    logger.debug(f"{filename}: Already downloaded, skipping")
                    continue

                # Format size for display
                size_mb = size / (1024 * 1024)
                if progress_callback:
                    progress_callback(f"[DOWNLOAD] {idx}/{total_files}: {filename} ({size_mb:.1f} MB)")

                dest_path = self.baseline_dir / filename
                success, ftp = self._download_file(
                    ftp, filename, dest_path, size,
                    current_path=self.BASELINE_PATH,
                    progress_callback=progress_callback
                )
                if success:
                    checksum = self._calculate_checksum(dest_path)
                    if self.tracker:
                        self.tracker.mark_downloaded(filename, 'baseline', size, checksum)
                    downloaded += 1
                    if progress_callback:
                        progress_callback(f"[DOWNLOAD] {filename}: Complete (verified)")
                else:
                    logger.error(f"{filename}: Download failed after all retries")
                    if progress_callback:
                        progress_callback(f"[DOWNLOAD ERROR] {filename}: Failed after all retries")

        finally:
            try:
                ftp.quit()
            except Exception:
                pass

        logger.info(f"Baseline download complete: {downloaded} files downloaded")
        if progress_callback:
            progress_callback(f"[DOWNLOAD] Complete: {downloaded} files downloaded")
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

    def _extract_transparency_metadata(
        self,
        article: ET.Element,
        medline: ET.Element,
        pubmed_article: ET.Element,
    ) -> Dict:
        """Extract transparency-related metadata from PubMed XML.

        Parses grants, publication types, retraction status, and author
        affiliations from PubMed XML elements. This data is used by the
        TransparencyAgent for offline bias risk assessment.

        Args:
            article: The Article element within MedlineCitation.
            medline: The MedlineCitation element.
            pubmed_article: The top-level PubmedArticle element.

        Returns:
            Dictionary with transparency metadata fields.
        """
        metadata: Dict = {}

        # 1. Extract grants from <GrantList>
        grants = []
        for grant in article.findall('.//GrantList/Grant'):
            grant_data: Dict[str, Optional[str]] = {}
            grant_id = grant.findtext('GrantID')
            agency = grant.findtext('Agency')
            country = grant.findtext('Country')
            if agency or grant_id:
                grant_data['agency'] = agency
                grant_data['grant_id'] = grant_id
                grant_data['country'] = country
                grants.append(grant_data)
        if grants:
            metadata['grants'] = grants

        # 2. Extract publication types from <PublicationTypeList>
        pub_types = []
        is_retracted = False
        for pub_type in article.findall('.//PublicationTypeList/PublicationType'):
            if pub_type.text:
                pub_types.append(pub_type.text)
                if pub_type.text.lower() in (
                    'retracted publication',
                    'retraction of publication',
                ):
                    is_retracted = True
        if pub_types:
            metadata['publication_types'] = pub_types
        metadata['is_retracted'] = is_retracted

        # 3. Check <CommentsCorrectionsList> for retraction references
        pubmed_data = pubmed_article.find('.//PubmedData')
        if pubmed_data is not None:
            for correction in pubmed_data.findall(
                './/CommentsCorrectionsList/CommentsCorrections'
            ):
                ref_type = correction.get('RefType', '')
                if ref_type.lower() in ('retractionin', 'retractionof'):
                    is_retracted = True
                    metadata['is_retracted'] = True

        # 4. Extract author affiliations from <AffiliationInfo>
        author_affiliations = []
        for author in article.findall('.//AuthorList/Author'):
            last = author.findtext('LastName', '')
            first = author.findtext('ForeName', '')
            name = f'{last} {first}'.strip()
            if not name:
                continue

            affiliations = []
            for aff_info in author.findall('.//AffiliationInfo/Affiliation'):
                if aff_info.text:
                    affiliations.append(aff_info.text)

            if affiliations:
                author_affiliations.append({
                    'author': name,
                    'affiliations': affiliations,
                })

        if author_affiliations:
            metadata['author_affiliations'] = author_affiliations

        return metadata

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

            # Extract transparency metadata (grants, publication types, affiliations)
            transparency_metadata = self._extract_transparency_metadata(
                article, medline, article_elem
            )

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
                'keywords': keywords,
                'transparency_metadata': transparency_metadata,
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

        # Store transparency metadata for articles that have it
        self._store_transparency_metadata_batch(articles, conn if 'conn' in dir() else None)

        return inserted + updated

    def _store_transparency_metadata_batch(
        self,
        articles: List[Dict],
        conn: Optional[Any] = None,
    ) -> int:
        """Store transparency metadata extracted from PubMed XML.

        Inserts grants, publication types, retraction status, and author
        affiliations into the transparency.document_metadata table.
        This is additive and does not affect the main document import.

        Args:
            articles: List of article dictionaries with transparency_metadata.
            conn: Optional existing database connection.

        Returns:
            Number of metadata records stored.
        """
        stored = 0
        close_conn = False

        try:
            if conn is None:
                conn = self.db_manager.get_connection().__enter__()
                close_conn = True

            # Check if transparency schema exists
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'transparency'
                        AND table_name = 'document_metadata'
                    )
                """)
                schema_exists = cur.fetchone()[0]

            if not schema_exists:
                logger.debug("transparency.document_metadata table not found, skipping metadata storage")
                return 0

            with conn.cursor() as cur:
                for article in articles:
                    metadata = article.get('transparency_metadata')
                    if not metadata:
                        continue

                    pmid = article.get('pmid')
                    if not pmid:
                        continue

                    # Look up document_id by pmid
                    cur.execute(
                        "SELECT id FROM document WHERE source_id = %s AND external_id = %s",
                        (self.source_id, pmid),
                    )
                    row = cur.fetchone()
                    if not row:
                        continue

                    document_id = row[0]
                    grants = metadata.get('grants')
                    pub_types = metadata.get('publication_types')
                    is_retracted = metadata.get('is_retracted', False)
                    author_affiliations = metadata.get('author_affiliations')

                    # Skip if no meaningful metadata
                    if not grants and not pub_types and not is_retracted and not author_affiliations:
                        continue

                    try:
                        cur.execute(
                            """
                            INSERT INTO transparency.document_metadata (
                                document_id, grants, publication_types,
                                is_retracted, author_affiliations, source
                            ) VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (document_id)
                            DO UPDATE SET
                                grants = COALESCE(EXCLUDED.grants, transparency.document_metadata.grants),
                                publication_types = COALESCE(EXCLUDED.publication_types, transparency.document_metadata.publication_types),
                                is_retracted = EXCLUDED.is_retracted OR transparency.document_metadata.is_retracted,
                                author_affiliations = COALESCE(EXCLUDED.author_affiliations, transparency.document_metadata.author_affiliations),
                                imported_at = NOW()
                            """,
                            (
                                document_id,
                                json.dumps(grants) if grants else None,
                                pub_types,
                                is_retracted,
                                json.dumps(author_affiliations) if author_affiliations else None,
                                'pubmed_bulk',
                            ),
                        )
                        stored += 1
                    except Exception as e:
                        logger.debug(f"Could not store transparency metadata for PMID {pmid}: {e}")

                conn.commit()

        except Exception as e:
            logger.debug(f"Transparency metadata storage skipped: {e}")
        finally:
            if close_conn and conn:
                try:
                    conn.__exit__(None, None, None)
                except Exception:
                    pass

        if stored > 0:
            logger.debug(f"Stored transparency metadata for {stored} articles")

        return stored

    def import_file(
        self,
        filepath: Path,
        batch_size: int = 100,
        progress_callback: Optional[ProgressCallback] = None
    ) -> Dict:
        """
        Import articles from XML file using memory-efficient streaming.

        Args:
            filepath: Path to .xml.gz file
            batch_size: Number of articles to batch before database insertion
            progress_callback: Optional callback for progress messages

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
                                    msg = f"{filepath.name}: Processed {stats['articles_parsed']:,} articles"
                                    logger.info(msg)
                                    if progress_callback:
                                        progress_callback(f"[IMPORT] {msg}")
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

    def import_all_files(
        self,
        file_type: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[CancelCheck] = None
    ) -> Dict:
        """
        Import all downloaded files.

        Args:
            file_type: 'baseline', 'update', or None for both
            progress_callback: Optional callback for progress messages
            cancel_check: Optional callback to check if operation should be cancelled

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

        # Collect all files to process
        all_files = []
        for directory in dirs_to_process:
            all_files.extend(sorted(directory.glob('*.xml.gz')))
        total_files = len(all_files)

        for idx, filepath in enumerate(all_files, 1):
            # Check for cancellation
            if cancel_check and cancel_check():
                if progress_callback:
                    progress_callback("[IMPORT] Cancelled by user")
                break

            # Skip if already processed
            if self.tracker and self.tracker.is_file_processed(filepath.name):
                logger.info(f"{filepath.name}: Already processed, skipping")
                continue

            if progress_callback:
                progress_callback(f"[IMPORT] {idx}/{total_files}: {filepath.name}")

            stats = self.import_file(filepath, progress_callback=progress_callback)
            overall_stats['files_processed'] += 1
            overall_stats['total_articles'] += stats['articles_imported']
            overall_stats['total_errors'] += stats['errors']

            if progress_callback:
                progress_callback(
                    f"[IMPORT] {filepath.name}: {stats['articles_imported']} articles imported"
                )

        return overall_stats

    def _import_worker(
        self,
        import_queue: ImportQueue,
        progress_callback: Optional[ProgressCallback],
        cancel_check: Optional[CancelCheck],
        stats: Dict
    ) -> None:
        """
        Worker thread that imports files sequentially from the queue.

        This worker runs in a separate thread and imports files in sequential
        order (by file number) as they become available in the queue.

        Args:
            import_queue: The ImportQueue to get files from
            progress_callback: Optional callback for progress messages
            cancel_check: Optional callback to check if operation should be cancelled
            stats: Shared statistics dictionary (thread-safe updates)
        """
        logger.info("Import worker started")

        while True:
            # Check for cancellation
            if cancel_check and cancel_check():
                if progress_callback:
                    progress_callback("[IMPORT] Cancelled by user")
                break

            # Get next file from queue
            filepath = import_queue.get_next_for_import(timeout=5.0)

            if filepath is None:
                if import_queue.is_complete():
                    logger.info("Import worker: All files processed")
                    break

                # Still waiting for files - report status
                status = import_queue.get_status()
                if progress_callback and status['queued_count'] > 0:
                    progress_callback(
                        f"[IMPORT] Waiting for file #{status['next_expected']} "
                        f"({status['queued_count']} files queued, waiting for sequence)"
                    )
                continue

            # Import the file
            if progress_callback:
                status = import_queue.get_status()
                progress_callback(
                    f"[IMPORT] {status['imported_count']}/{status['total_files']}: {filepath.name}"
                )

            try:
                file_stats = self.import_file(filepath, progress_callback=progress_callback)

                # Update shared statistics
                with threading.Lock():
                    stats['files_processed'] += 1
                    stats['total_articles'] += file_stats['articles_imported']
                    stats['total_errors'] += file_stats['errors']

                if progress_callback:
                    progress_callback(
                        f"[IMPORT] {filepath.name}: {file_stats['articles_imported']:,} articles imported"
                    )
                    # Periodic summary
                    if stats['files_processed'] % 10 == 0:
                        progress_callback(
                            f"[STATS] Imported: {stats['files_processed']} files, "
                            f"{stats['total_articles']:,} articles"
                        )

            except Exception as e:
                logger.error(f"Import worker error on {filepath.name}: {e}", exc_info=True)
                if progress_callback:
                    progress_callback(f"[IMPORT ERROR] {filepath.name}: {e}")
                with threading.Lock():
                    stats['total_errors'] += 1

        logger.info("Import worker finished")

    def download_and_import_baseline(
        self,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[CancelCheck] = None,
        skip_existing: bool = True
    ) -> Dict:
        """
        Download and import baseline files in parallel.

        Downloads happen in the main thread while imports process sequentially
        in a separate thread. Files are imported in file-number order regardless
        of download completion order.

        This method handles:
        - Pre-existing downloaded but unprocessed files
        - Resume of partial downloads
        - Sequential import order (critical for corrections/retractions)
        - Graceful cancellation

        Args:
            progress_callback: Optional callback for progress messages
            cancel_check: Optional callback to check if operation should be cancelled
            skip_existing: Skip files already downloaded (default: True)

        Returns:
            Dict with overall statistics including:
            - files_downloaded: Number of files newly downloaded
            - files_processed: Number of files imported
            - total_articles: Total articles imported
            - total_errors: Total errors encountered
        """
        logger.info("Starting parallel download and import")

        stats = {
            'files_downloaded': 0,
            'files_processed': 0,
            'total_articles': 0,
            'total_errors': 0,
            'pre_existing_queued': 0
        }

        if progress_callback:
            progress_callback("[INIT] Connecting to NCBI FTP server...")

        # Get list of remote files
        ftp = self._create_ftp_connection()
        try:
            remote_files = self._get_remote_file_list(ftp, self.BASELINE_PATH)
            total_files = len(remote_files)
            logger.info(f"Found {total_files} baseline files on server")
            if progress_callback:
                progress_callback(f"[INIT] Found {total_files} baseline files on server")
        except Exception as e:
            logger.error(f"Failed to get file list: {e}")
            if progress_callback:
                progress_callback(f"[ERROR] Failed to get file list: {e}")
            try:
                ftp.quit()
            except Exception:
                pass
            raise

        # Create import queue
        import_queue = ImportQueue(start_from=1)
        import_queue.set_total_files(total_files)

        # Queue pre-existing downloaded but unprocessed files
        if progress_callback:
            progress_callback("[INIT] Checking for pre-existing downloaded files...")

        pre_existing = 0
        already_processed = 0
        for filepath in sorted(self.baseline_dir.glob('*.xml.gz')):
            if self.tracker:
                if self.tracker.is_file_processed(filepath.name):
                    # Already processed - mark as skipped in queue
                    import_queue.mark_skipped(filepath)
                    already_processed += 1
                elif self.tracker.is_file_downloaded(filepath.name):
                    # Downloaded but not processed - add to queue
                    import_queue.add_downloaded(filepath)
                    pre_existing += 1
            else:
                # No tracker - assume file needs processing
                import_queue.add_downloaded(filepath)
                pre_existing += 1

        stats['pre_existing_queued'] = pre_existing

        if progress_callback:
            if already_processed > 0:
                progress_callback(f"[INIT] {already_processed} files already processed (skipping)")
            if pre_existing > 0:
                progress_callback(f"[INIT] {pre_existing} pre-downloaded files queued for import")

        # Start import worker thread
        import_thread = threading.Thread(
            target=self._import_worker,
            args=(import_queue, progress_callback, cancel_check, stats),
            name="PubMed-ImportWorker",
            daemon=True
        )
        import_thread.start()
        logger.info("Import worker thread started")

        # Download files in main thread
        try:
            downloaded = 0
            for idx, (filename, size) in enumerate(remote_files, 1):
                # Check for cancellation
                if cancel_check and cancel_check():
                    if progress_callback:
                        progress_callback("[DOWNLOAD] Cancelled by user")
                    break

                # Skip if already downloaded
                if skip_existing and self.tracker and self.tracker.is_file_downloaded(filename):
                    logger.debug(f"{filename}: Already downloaded, skipping")
                    continue

                # Report download progress
                size_mb = size / (1024 * 1024)
                if progress_callback:
                    progress_callback(f"[DOWNLOAD] {idx}/{total_files}: {filename} ({size_mb:.1f} MB)")

                dest_path = self.baseline_dir / filename
                success, ftp = self._download_file(
                    ftp, filename, dest_path, size,
                    current_path=self.BASELINE_PATH,
                    progress_callback=progress_callback
                )

                if success:
                    checksum = self._calculate_checksum(dest_path)
                    if self.tracker:
                        self.tracker.mark_downloaded(filename, 'baseline', size, checksum)
                    downloaded += 1
                    stats['files_downloaded'] += 1

                    # Add to import queue
                    import_queue.add_downloaded(dest_path)

                    if progress_callback:
                        progress_callback(f"[DOWNLOAD] {filename}: Complete (queued for import)")
                else:
                    logger.error(f"{filename}: Download failed after all retries")
                    if progress_callback:
                        progress_callback(f"[DOWNLOAD ERROR] {filename}: Failed after all retries")
                    stats['total_errors'] += 1

        finally:
            # Close FTP connection
            try:
                ftp.quit()
            except Exception:
                pass

            # Signal download completion
            import_queue.mark_download_complete()
            if progress_callback:
                progress_callback(f"[DOWNLOAD] All downloads complete: {stats['files_downloaded']} files")

        # Wait for import to finish
        if progress_callback:
            progress_callback("[IMPORT] Waiting for import to complete...")

        import_thread.join()

        # Final summary
        if progress_callback:
            progress_callback(
                f"[COMPLETE] Downloaded: {stats['files_downloaded']}, "
                f"Imported: {stats['files_processed']} files, "
                f"{stats['total_articles']:,} articles, "
                f"{stats['total_errors']} errors"
            )

        logger.info(
            f"Parallel download/import complete: {stats['files_downloaded']} downloaded, "
            f"{stats['files_processed']} imported, {stats['total_articles']} articles"
        )

        return stats
