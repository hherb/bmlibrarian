"""
PubMed Bulk Importer - complete local PubMed mirror

This module downloads (over HTTPS, MD5-verified and resumable; see
ncbi_https.py for why not FTP) and imports PubMed baseline and update files
for maintaining a complete local PubMed mirror.

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

import gzip
import hashlib
import multiprocessing
import json
import logging
import os
import queue
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List, Sequence, Tuple, Callable
from psycopg.types.json import Jsonb

from bmlibrarian.database import get_db_manager
from .ncbi_https import NCBI_HTTPS_BASE_URL, HttpsDownloader

logger = logging.getLogger(__name__)

# CommentsCorrections/@RefType values (lower-cased) that mark a retraction link:
# RetractionIn on the retracted article, RetractionOf on the retraction notice.
RETRACTION_REF_TYPES = ('retractionin', 'retractionof')

# ---------------------------------------------------------------------------
# COPY-based, revision-aware, resumable write path (one transaction per file)
# ---------------------------------------------------------------------------

LEDGER_SOURCE = 'pubmed_bulk'
METADATA_SOURCE = 'pubmed_bulk'
SHA256_CHUNK_BYTES = 1 << 20
ISO_DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')

STAGE_DOCUMENT_COLUMNS = (
    'ord', 'external_id', 'doi', 'title', 'abstract', 'authors', 'publication',
    'publication_date', 'url', 'mesh_terms', 'keywords', 'date_revised',
)
STAGE_METADATA_COLUMNS = (
    'ord', 'external_id', 'date_revised', 'grants', 'publication_types',
    'is_retracted', 'author_affiliations',
)

STAGING_DDL = (
    """CREATE TEMP TABLE stage_document (
        ord integer, external_id text, doi text, title text, abstract text,
        authors text[], publication text, publication_date date, url text,
        mesh_terms text[], keywords text[], date_revised date) ON COMMIT DROP""",
    """CREATE TEMP TABLE stage_metadata (
        ord integer, external_id text, date_revised date, grants jsonb,
        publication_types text[], is_retracted boolean, author_affiliations jsonb) ON COMMIT DROP""",
)

# The newest revision of a PMID wins: within the file (DISTINCT ON ordered by
# date_revised, then file order) and against the stored row (the update only
# applies when the incoming revision is not older). COALESCE semantics for
# doi/abstract/publication/date are kept from the row-by-row importer.
MERGE_DOCUMENTS_SQL = """
INSERT INTO document (
    source_id, external_id, doi, title, abstract, authors, publication,
    publication_date, url, mesh_terms, keywords, date_revised)
SELECT DISTINCT ON (external_id)
    %(source_id)s, external_id, doi, title, abstract, authors, publication,
    publication_date, url, mesh_terms, keywords, date_revised
FROM stage_document
ORDER BY external_id, date_revised DESC NULLS LAST, ord DESC
ON CONFLICT (source_id, external_id) DO UPDATE SET
    doi = COALESCE(EXCLUDED.doi, document.doi),
    title = EXCLUDED.title,
    abstract = COALESCE(EXCLUDED.abstract, document.abstract),
    authors = EXCLUDED.authors,
    publication = COALESCE(EXCLUDED.publication, document.publication),
    publication_date = COALESCE(EXCLUDED.publication_date, document.publication_date),
    mesh_terms = EXCLUDED.mesh_terms,
    keywords = EXCLUDED.keywords,
    date_revised = COALESCE(EXCLUDED.date_revised, document.date_revised),
    updated_date = CURRENT_TIMESTAMP
WHERE EXCLUDED.date_revised IS NULL
   OR document.date_revised IS NULL
   OR EXCLUDED.date_revised >= document.date_revised
"""

# Metadata follows the revision that won the document merge.
MERGE_METADATA_SQL = """
INSERT INTO transparency.document_metadata (
    document_id, grants, publication_types, is_retracted, author_affiliations, source)
SELECT DISTINCT ON (d.id)
    d.id, m.grants, m.publication_types, m.is_retracted, m.author_affiliations, %(source)s
FROM stage_metadata m
JOIN document d ON d.source_id = %(source_id)s AND d.external_id = m.external_id
WHERE m.date_revised IS NOT DISTINCT FROM d.date_revised
ORDER BY d.id, m.ord DESC
ON CONFLICT (document_id) DO UPDATE SET
    grants = COALESCE(EXCLUDED.grants, transparency.document_metadata.grants),
    publication_types = COALESCE(EXCLUDED.publication_types, transparency.document_metadata.publication_types),
    is_retracted = EXCLUDED.is_retracted OR transparency.document_metadata.is_retracted,
    author_affiliations = COALESCE(EXCLUDED.author_affiliations, transparency.document_metadata.author_affiliations),
    imported_at = NOW()
"""

LEDGER_UPSERT_SQL = """
INSERT INTO ingest.ledger (source, file, sha256, records, seconds)
VALUES (%(source)s, %(file)s, %(sha256)s, %(records)s, %(seconds)s)
ON CONFLICT (source, file) DO UPDATE SET
    sha256 = EXCLUDED.sha256, records = EXCLUDED.records,
    seconds = EXCLUDED.seconds, finished_at = clock_timestamp()
"""

# Withdrawals (DeleteCitation, migration 032): record the PMIDs, then mark the
# documents. Marking runs for the file's deletions *and* for its staged records,
# so a deletion imported before its record still applies (any file order).
RECORD_WITHDRAWN_SQL = """
INSERT INTO ingest.withdrawn_pmid (pmid, file)
SELECT DISTINCT unnest(%(pmids)s::text[]), %(file)s
ON CONFLICT (pmid) DO NOTHING
"""

MARK_WITHDRAWN_SQL = """
UPDATE document d SET withdrawn = w.withdrawn
FROM ingest.withdrawn_pmid w
WHERE d.source_id = %(source_id)s AND d.external_id = w.pmid
  AND d.withdrawn IS NULL AND w.pmid = ANY(%(pmids)s::text[])
"""

MARK_STAGED_WITHDRAWN_SQL = """
UPDATE document d SET withdrawn = w.withdrawn
FROM stage_document s
JOIN ingest.withdrawn_pmid w ON w.pmid = s.external_id
WHERE d.source_id = %(source_id)s AND d.external_id = s.external_id
  AND d.withdrawn IS NULL
"""

PMID_PATTERN = re.compile(r'^[0-9]+$')

TRANSPARENCY_TABLE_EXISTS_SQL = """
SELECT EXISTS (SELECT FROM information_schema.tables
               WHERE table_schema = 'transparency' AND table_name = 'document_metadata')
"""


def valid_iso_date(value: Optional[str]) -> Optional[str]:
    """Return ``value`` if it is a real YYYY-MM-DD date, else None.

    _extract_date passes through month names it does not know (e.g. seasons),
    which a date column would reject; such values are stored as NULL.
    """
    if not value or not ISO_DATE_PATTERN.match(value):
        return None
    try:
        datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        return None
    return value


def parse_deleted_pmids(elem: ET.Element) -> List[str]:
    """PMIDs listed in a ``<DeleteCitation>`` element (non-numeric values are dropped).

    Args:
        elem: The DeleteCitation element.

    Returns:
        The withdrawn PMIDs, in file order.
    """
    pmids = []
    for pmid in elem.findall('PMID'):
        text = (pmid.text or '').strip()
        if PMID_PATTERN.match(text):
            pmids.append(text)
        else:
            logger.warning(f"Ignoring invalid PMID in DeleteCitation: {text!r}")
    return pmids


def has_transparency_metadata(meta: Dict) -> bool:
    """Same filter as the row-by-row path: store only meaningful metadata."""
    return bool(meta.get('grants') or meta.get('publication_types')
                or meta.get('is_retracted') or meta.get('author_affiliations'))


def to_staging_rows(articles: List[Dict]) -> Tuple[List[tuple], List[tuple]]:
    """Convert parsed articles into COPY rows for the staging tables.

    Empty strings become NULL (as in the row-by-row importer); invalid dates
    become NULL. Column order follows STAGE_DOCUMENT_COLUMNS and
    STAGE_METADATA_COLUMNS.

    Args:
        articles: Articles as returned by PubMedBulkImporter._parse_article.

    Returns:
        (document rows, metadata rows).
    """
    docs: List[tuple] = []
    metas: List[tuple] = []
    for ord_, a in enumerate(articles):
        revised = valid_iso_date(a.get('date_revised'))
        docs.append((
            ord_, a['pmid'], a.get('doi') or None, a.get('title'), a.get('abstract') or None,
            a.get('authors', []), a.get('publication') or None,
            valid_iso_date(a.get('publication_date')), a.get('url'),
            a.get('mesh_terms', []), a.get('keywords', []), revised,
        ))
        meta = a.get('transparency_metadata') or {}
        if has_transparency_metadata(meta):
            metas.append((
                ord_, a['pmid'], revised,
                Jsonb(meta['grants']) if meta.get('grants') else None,
                meta.get('publication_types') or None,
                bool(meta.get('is_retracted', False)),
                Jsonb(meta['author_affiliations']) if meta.get('author_affiliations') else None,
            ))
    return docs, metas


def file_sha256(path: Path) -> str:
    """SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(SHA256_CHUNK_BYTES), b''):
            digest.update(chunk)
    return digest.hexdigest()


# Per-process importer for parallel imports (set by _init_import_worker).
_WORKER_IMPORTER: Optional['PubMedBulkImporter'] = None


def _init_import_worker(data_dir: str, conninfo: str) -> None:
    """Process-pool initializer: an importer bound to exactly the parent's database.

    A fresh process re-imports bmlibrarian.database, which loads the default env
    file; passing the parent's conninfo explicitly guarantees the worker writes
    to the same database as the parent (never to whatever that file names).
    """
    global _WORKER_IMPORTER
    from bmlibrarian.database import DatabaseManager

    db = DatabaseManager(auto_migrate=False, conninfo=conninfo)
    _WORKER_IMPORTER = PubMedBulkImporter(data_dir=data_dir, use_tracking=False, db_manager=db)


def _import_file_in_worker(path: str) -> Dict:
    """Process-pool task: import one file with this process's importer."""
    if _WORKER_IMPORTER is None:
        raise RuntimeError("import worker not initialised")
    return _WORKER_IMPORTER.import_file(Path(path))

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
        """Get download and processing statistics.

        Note: per-file article counts are not stored in the tracking schema
        (see mark_processed), so no article count is reported here; the CLI
        derives the real article count from the document table instead.
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) as total_files,
                        COUNT(*) FILTER (WHERE processed = TRUE) as processed_files,
                        COUNT(*) FILTER (WHERE file_type = 'baseline') as baseline_files,
                        COUNT(*) FILTER (WHERE file_type = 'update') as update_files,
                        SUM(file_size) as total_size
                    FROM pubmed_download_log
                """)
                row = cur.fetchone()
                return {
                    'total_files': row[0] or 0,
                    'processed_files': row[1] or 0,
                    'baseline_files': row[2] or 0,
                    'update_files': row[3] or 0,
                    'total_size_bytes': row[4] or 0
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
    """PubMed bulk downloader (HTTPS, MD5-verified) and importer."""

    BASELINE_URL = f'{NCBI_HTTPS_BASE_URL}/pubmed/baseline/'
    UPDATE_URL = f'{NCBI_HTTPS_BASE_URL}/pubmed/updatefiles/'

    def __init__(
        self,
        data_dir: Optional[str] = None,
        use_tracking: bool = True,
        db_manager: Optional[Any] = None,
        downloader: Optional[HttpsDownloader] = None,
    ):
        """
        Initialize PubMed bulk importer.

        Args:
            data_dir: Directory for storing downloaded files (default: ~/knowledgebase/pubmed_data)
            use_tracking: Whether to use database tracking (default: True)
            db_manager: DatabaseManager to use (default: the shared get_db_manager()).
            downloader: HTTPS downloader to use (default: a new HttpsDownloader).
        """
        self.data_dir = Path(data_dir or os.path.expanduser('~/knowledgebase/pubmed_data'))
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.baseline_dir = self.data_dir / 'baseline'
        self.update_dir = self.data_dir / 'updatefiles'
        self.baseline_dir.mkdir(exist_ok=True)
        self.update_dir.mkdir(exist_ok=True)

        self.use_tracking = use_tracking
        self.tracker = DownloadTracker() if use_tracking else None
        self.db_manager = db_manager if db_manager is not None else get_db_manager()
        self.downloader = downloader if downloader is not None else HttpsDownloader()

        # Get PubMed source_id
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM sources WHERE LOWER(name) LIKE '%pubmed%' LIMIT 1")
                result = cur.fetchone()
                if not result:
                    raise ValueError("PubMed source not found in sources table")
                self.source_id = result[0]

        logger.info(f"Initialized PubMed bulk importer with data_dir: {self.data_dir}")

    def _needs_download(self, filename: str, dest_path: Path, skip_existing: bool) -> bool:
        """
        Whether a remote file still has to be downloaded.

        A file is skipped only if the tracker records it as downloaded *and* it
        is still on disk (files at their final name are always MD5-verified).
        """
        if not skip_existing or not dest_path.exists():
            return True
        return not (self.tracker and self.tracker.is_file_downloaded(filename))

    def _download_one(
        self,
        filename: str,
        directory_url: str,
        dest_dir: Path,
        file_type: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Optional[Path]:
        """
        Download one file over HTTPS, verify its MD5 and record it in the tracker.

        Args:
            filename: Remote file name (from the directory listing).
            directory_url: Remote directory URL ending in ``/``.
            dest_dir: Local directory.
            file_type: 'baseline' or 'update' (tracker category).
            progress_callback: Optional callback for progress messages.

        Returns:
            The local path of the verified file, or None if the download failed.
        """
        url = directory_url + filename
        dest_path = dest_dir / filename
        try:
            expected_md5 = self.downloader.fetch_md5(url)
            if not self.downloader.download(url, dest_path, expected_md5, progress_callback):
                return None
        except Exception as e:
            logger.error(f"{filename}: download failed: {e}")
            if progress_callback:
                progress_callback(f"[DOWNLOAD ERROR] {filename}: {e}")
            return None
        if self.tracker:
            self.tracker.mark_downloaded(filename, file_type, dest_path.stat().st_size, expected_md5)
        return dest_path

    def _download_directory(
        self,
        directory_url: str,
        dest_dir: Path,
        file_type: str,
        skip_existing: bool = True,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[CancelCheck] = None,
        on_downloaded: Optional[Callable[[Path], None]] = None,
        files: Optional[List[str]] = None,
    ) -> Tuple[int, int]:
        """
        Download every data file of a remote directory that is not yet present.

        Args:
            directory_url: Remote directory URL ending in ``/``.
            dest_dir: Local directory.
            file_type: 'baseline' or 'update'.
            skip_existing: Skip files already downloaded (default: True).
            progress_callback: Optional callback for progress messages.
            cancel_check: Optional callback to check if operation should be cancelled.
            on_downloaded: Optional callback receiving each newly verified file.
            files: Remote file names if already listed (default: list the directory).

        Returns:
            (files downloaded, files failed).
        """
        if files is None:
            files = self.downloader.list_files(directory_url)
        total_files = len(files)
        logger.info(f"Found {total_files} {file_type} files at {directory_url}")
        if progress_callback:
            progress_callback(f"[INIT] Found {total_files} {file_type} files on server")

        downloaded = failed = 0
        for idx, filename in enumerate(files, 1):
            if cancel_check and cancel_check():
                if progress_callback:
                    progress_callback("[DOWNLOAD] Cancelled by user")
                break
            if not self._needs_download(filename, dest_dir / filename, skip_existing):
                logger.debug(f"{filename}: Already downloaded, skipping")
                continue
            if progress_callback:
                progress_callback(f"[DOWNLOAD] {idx}/{total_files}: {filename}")
            path = self._download_one(filename, directory_url, dest_dir, file_type, progress_callback)
            if path is None:
                failed += 1
                logger.error(f"{filename}: Download failed after all retries")
                if progress_callback:
                    progress_callback(f"[DOWNLOAD ERROR] {filename}: Failed after all retries")
                continue
            downloaded += 1
            if progress_callback:
                progress_callback(f"[DOWNLOAD] {filename}: Complete (MD5 verified)")
            if on_downloaded:
                on_downloaded(path)
        return downloaded, failed

    def download_baseline(
        self,
        skip_existing: bool = True,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[CancelCheck] = None
    ) -> int:
        """
        Download PubMed baseline files (HTTPS, MD5-verified, resumable).

        Args:
            skip_existing: Skip files already downloaded (default: True)
            progress_callback: Optional callback for progress messages
            cancel_check: Optional callback to check if operation should be cancelled

        Returns:
            Number of files downloaded
        """
        logger.info("Starting baseline download")
        downloaded, failed = self._download_directory(
            self.BASELINE_URL, self.baseline_dir, 'baseline', skip_existing,
            progress_callback, cancel_check)
        logger.info(f"Baseline download complete: {downloaded} files downloaded, {failed} failed")
        if progress_callback:
            progress_callback(f"[DOWNLOAD] Complete: {downloaded} files downloaded, {failed} failed")
        return downloaded

    def download_updates(self, skip_existing: bool = True) -> int:
        """
        Download PubMed update files (HTTPS, MD5-verified, resumable).

        Args:
            skip_existing: Skip files already downloaded (default: True)

        Returns:
            Number of files downloaded
        """
        logger.info("Starting update files download")
        downloaded, failed = self._download_directory(
            self.UPDATE_URL, self.update_dir, 'update', skip_existing)
        logger.info(f"Update files download complete: {downloaded} files downloaded, {failed} failed")
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

        # 3. Check <CommentsCorrectionsList> for retraction references.
        # Per the PubMed DTD it is a child of MedlineCitation (not PubmedData).
        for correction in medline.findall('CommentsCorrectionsList/CommentsCorrections'):
            ref_type = correction.get('RefType', '')
            if ref_type.lower() in RETRACTION_REF_TYPES:
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
                # Direct child only: './/' would also reach the DOIs of cited
                # references in ReferenceList/Reference/ArticleIdList.
                for article_id in pubmed_data.findall('ArticleIdList/ArticleId'):
                    if article_id.get('IdType') == 'doi':
                        doi = article_id.text
                        break

            # MeSH terms
            mesh_terms = []
            for mesh in medline.findall('.//MeshHeadingList/MeshHeading/DescriptorName'):
                if mesh.text:
                    mesh_terms.append(mesh.text)

            # Keywords: KeywordList is a child of MedlineCitation, not of Article.
            keywords = []
            for keyword in medline.findall('KeywordList/Keyword'):
                text = self._get_element_text(keyword).strip()
                if text:
                    keywords.append(text)

            # Revision date: orders revised records of the same PMID
            date_revised = self._extract_date(medline.find('DateRevised'))

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
                'date_revised': date_revised,
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

        # Store transparency metadata on its own fresh connection. The main
        # insert above has already committed, so the documents are visible for
        # the metadata lookups. Passing None (rather than the now returned-to-
        # pool `conn`) both fixes the use-after-return bug and keeps this
        # best-effort, additive step fully decoupled from the main import
        # transaction.
        self._store_transparency_metadata_batch(articles, None)

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
        own_cm = None

        try:
            if conn is None:
                # Acquire our own pooled connection. Keep the context manager so
                # the connection is returned to the pool in `finally` (calling
                # conn.__exit__ instead would leak it).
                own_cm = self.db_manager.get_connection()
                conn = own_cm.__enter__()

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
            if own_cm is not None:
                # Returns the connection to the pool (get_connection() commits
                # or rolls back as appropriate on exit).
                try:
                    own_cm.__exit__(None, None, None)
                except Exception:
                    pass

        if stored > 0:
            logger.debug(f"Stored transparency metadata for {stored} articles")

        return stored

    def _is_file_committed(self, filename: str) -> bool:
        """Whether ``filename`` is recorded in ingest.ledger (already imported)."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM ingest.ledger WHERE source = %s AND file = %s",
                    (LEDGER_SOURCE, filename),
                )
                return cur.fetchone() is not None

    def _store_file(self, articles: List[Dict], filename: str, sha256: str, started: float,
                    withdrawn_pmids: Sequence[str] = ()) -> int:
        """Store one file atomically: COPY, merge, withdrawals, metadata, ledger row.

        Everything happens in one transaction, so an interruption leaves either
        the whole file (including its ledger row) or none of it, and a resumed
        import repeats exactly the files that did not commit.

        Args:
            articles: Parsed articles of the file, in file order.
            filename: Source file name (ledger key).
            sha256: Checksum of the source file.
            started: perf_counter() when processing of the file began.
            withdrawn_pmids: PMIDs the file withdraws (DeleteCitation).

        Returns:
            Number of document rows inserted or updated.
        """
        docs, metas = to_staging_rows(articles)
        params = {'source_id': self.source_id, 'source': METADATA_SOURCE}
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                for ddl in STAGING_DDL:
                    cur.execute(ddl)
                with cur.copy(f"COPY stage_document ({', '.join(STAGE_DOCUMENT_COLUMNS)}) FROM STDIN") as cp:
                    for row in docs:
                        cp.write_row(row)
                with cur.copy(f"COPY stage_metadata ({', '.join(STAGE_METADATA_COLUMNS)}) FROM STDIN") as cp:
                    for row in metas:
                        cp.write_row(row)
                cur.execute(MERGE_DOCUMENTS_SQL, params)
                written = cur.rowcount
                self._apply_withdrawals(cur, list(withdrawn_pmids), filename)
                cur.execute(MARK_STAGED_WITHDRAWN_SQL, params)
                cur.execute(TRANSPARENCY_TABLE_EXISTS_SQL)
                if cur.fetchone()[0]:
                    cur.execute(MERGE_METADATA_SQL, params)
                else:
                    logger.debug("transparency.document_metadata not found, skipping metadata storage")
                cur.execute(LEDGER_UPSERT_SQL, {
                    'source': LEDGER_SOURCE, 'file': filename, 'sha256': sha256,
                    'records': len(articles), 'seconds': time.perf_counter() - started,
                })
        return written

    def _apply_withdrawals(self, cur: Any, pmids: List[str], filename: str) -> int:
        """Record withdrawn PMIDs and mark their documents (inside the caller's transaction).

        Returns:
            Number of PMIDs newly recorded.
        """
        if not pmids:
            return 0
        cur.execute(RECORD_WITHDRAWN_SQL, {'pmids': pmids, 'file': filename})
        recorded = cur.rowcount
        cur.execute(MARK_WITHDRAWN_SQL, {'pmids': pmids, 'source_id': self.source_id})
        return recorded

    def backfill_withdrawals(self, file_type: str = 'update',
                             progress_callback: Optional[ProgressCallback] = None) -> Dict[str, int]:
        """
        Apply the DeleteCitation lists of files that were imported before
        withdrawals were handled (one transaction per file; idempotent, so it
        can be stopped and re-run).

        Args:
            file_type: 'update', 'baseline' or None for both.
            progress_callback: Optional callback for progress messages.

        Returns:
            Counts: files_scanned, pmids_listed, pmids_recorded.
        """
        dirs = []
        if file_type in (None, 'baseline'):
            dirs.append(self.baseline_dir)
        if file_type in (None, 'update'):
            dirs.append(self.update_dir)
        result = {'files_scanned': 0, 'pmids_listed': 0, 'pmids_recorded': 0}
        for directory in dirs:
            for filepath in sorted(directory.glob('*.xml.gz')):
                pmids: List[str] = []
                with gzip.open(filepath, 'rb') as gz_file:
                    for _event, elem in ET.iterparse(gz_file, events=('end',)):
                        if elem.tag == 'DeleteCitation':
                            pmids.extend(parse_deleted_pmids(elem))
                            elem.clear()
                        elif elem.tag == 'PubmedArticle':
                            elem.clear()
                with self.db_manager.get_connection() as conn:
                    with conn.cursor() as cur:
                        recorded = self._apply_withdrawals(cur, pmids, filepath.name)
                result['files_scanned'] += 1
                result['pmids_listed'] += len(pmids)
                result['pmids_recorded'] += recorded
                if progress_callback and pmids:
                    progress_callback(f"[WITHDRAW] {filepath.name}: {len(pmids)} listed, {recorded} new")
        logger.info(f"Withdrawal backfill: {result}")
        return result

    def import_file(
        self,
        filepath: Path,
        progress_callback: Optional[ProgressCallback] = None,
        force: bool = False,
    ) -> Dict:
        """
        Import one PubMed XML file, resumably.

        The file is parsed completely, then stored in a single transaction
        (COPY into staging, revision-aware set-based merge, transparency
        metadata, ingest.ledger row). Files already in the ledger are skipped
        unless ``force`` is set, so stopping and restarting an import repeats
        only files that had not committed.

        Args:
            filepath: Path to .xml.gz file
            progress_callback: Optional callback for progress messages
            force: Re-import even if the file is already in the ledger

        Returns:
            Dict with import statistics (``skipped`` is True for ledger hits)
        """
        filepath = Path(filepath)
        stats = {
            'filename': filepath.name,
            'articles_parsed': 0,
            'articles_imported': 0,
            'articles_updated': 0,
            'articles_withdrawn': 0,
            'errors': 0,
            'skipped': False,
        }

        try:
            if not force and self._is_file_committed(filepath.name):
                logger.info(f"{filepath.name}: already in ingest.ledger, skipping")
                stats['skipped'] = True
                return stats

            logger.info(f"Importing {filepath.name}")
            started = time.perf_counter()
            articles: List[Dict] = []
            deleted: List[str] = []
            with gzip.open(filepath, 'rb') as gz_file:
                # Use iterparse for memory efficiency while parsing
                for event, elem in ET.iterparse(gz_file, events=('end',)):
                    if elem.tag == 'PubmedArticle':
                        article = self._parse_article(elem)
                        if article:
                            articles.append(article)
                        else:
                            stats['errors'] += 1
                        elem.clear()
                    elif elem.tag == 'DeleteCitation':
                        deleted.extend(parse_deleted_pmids(elem))
                        elem.clear()
            stats['articles_parsed'] = len(articles)
            if progress_callback:
                progress_callback(f"[IMPORT] {filepath.name}: parsed {len(articles):,} articles, storing")

            stats['articles_imported'] = self._store_file(
                articles, filepath.name, file_sha256(filepath), started, withdrawn_pmids=deleted)
            stats['articles_withdrawn'] = len(set(deleted))
            logger.info(f"{filepath.name}: Import complete - {stats['articles_parsed']} parsed, "
                        f"{stats['articles_imported']} imported")

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

    def _committed_files(self) -> set:
        """Names of all files already recorded in ingest.ledger."""
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT file FROM ingest.ledger WHERE source = %s", (LEDGER_SOURCE,))
                return {row[0] for row in cur.fetchall()}

    def import_all_files(
        self,
        file_type: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[CancelCheck] = None,
        workers: int = 1,
    ) -> Dict:
        """
        Import all downloaded files, resumably and optionally in parallel.

        Files already in ingest.ledger (or marked processed by the download
        tracker) are skipped, so re-running continues where a stopped import
        left off. With ``workers > 1`` files are imported by separate
        processes, each committing whole files; the revision-aware merge makes
        the result independent of the order in which files finish.

        Args:
            file_type: 'baseline', 'update', or None for both
            progress_callback: Optional callback for progress messages
            cancel_check: Optional callback to check if operation should be cancelled.
                Cancelling stops submitting files; files already running finish
                (each is one transaction).
            workers: Number of parallel import processes (1 = in this process)

        Returns:
            Dict with overall statistics
        """
        overall_stats = {
            'files_processed': 0,
            'files_skipped': 0,
            'total_articles': 0,
            'total_withdrawn': 0,
            'total_errors': 0
        }

        # Determine which directories to process
        dirs_to_process = []
        if file_type in (None, 'baseline'):
            dirs_to_process.append(self.baseline_dir)
        if file_type in (None, 'update'):
            dirs_to_process.append(self.update_dir)

        # Collect all files to process, minus those already committed
        all_files = []
        for directory in dirs_to_process:
            all_files.extend(sorted(directory.glob('*.xml.gz')))
        committed = self._committed_files()
        pending = []
        for filepath in all_files:
            if filepath.name in committed or (self.tracker and self.tracker.is_file_processed(filepath.name)):
                overall_stats['files_skipped'] += 1
            else:
                pending.append(filepath)
        total_files = len(pending)
        if progress_callback:
            progress_callback(f"[IMPORT] {total_files} files to import "
                              f"({overall_stats['files_skipped']} already done), {workers} worker(s)")

        def record(stats: Dict, idx: int) -> None:
            overall_stats['files_processed'] += 1
            overall_stats['total_articles'] += stats['articles_imported']
            overall_stats['total_withdrawn'] += stats.get('articles_withdrawn', 0)
            overall_stats['total_errors'] += stats['errors']
            if self.tracker and workers > 1 and stats['errors'] == 0:
                self.tracker.mark_processed(stats['filename'], stats['articles_parsed'])
            if progress_callback:
                progress_callback(f"[IMPORT] {idx}/{total_files}: {stats['filename']}: "
                                  f"{stats['articles_imported']} articles imported")

        if workers <= 1:
            for idx, filepath in enumerate(pending, 1):
                if cancel_check and cancel_check():
                    if progress_callback:
                        progress_callback("[IMPORT] Cancelled by user")
                    break
                record(self.import_file(filepath, progress_callback=progress_callback), idx)
            return overall_stats

        context = multiprocessing.get_context('spawn')
        with ProcessPoolExecutor(max_workers=workers, mp_context=context,
                                 initializer=_init_import_worker,
                                 initargs=(str(self.data_dir), self.db_manager.conninfo)) as pool:
            futures = {pool.submit(_import_file_in_worker, str(f)): f for f in pending}
            done_count = 0
            for future in as_completed(futures):
                done_count += 1
                try:
                    record(future.result(), done_count)
                except Exception as e:
                    logger.error(f"{futures[future].name}: worker failed: {e}", exc_info=True)
                    overall_stats['total_errors'] += 1
                if cancel_check and cancel_check():
                    for f in futures:
                        f.cancel()
                    if progress_callback:
                        progress_callback("[IMPORT] Cancelled by user; running files will finish")
                    break
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
            progress_callback("[INIT] Listing NCBI baseline files...")

        try:
            remote_files = self.downloader.list_files(self.BASELINE_URL)
        except Exception as e:
            logger.error(f"Failed to get file list: {e}")
            if progress_callback:
                progress_callback(f"[ERROR] Failed to get file list: {e}")
            raise
        total_files = len(remote_files)

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
        def queue_for_import(path: Path) -> None:
            stats['files_downloaded'] += 1
            import_queue.add_downloaded(path)

        try:
            _downloaded, failed = self._download_directory(
                self.BASELINE_URL, self.baseline_dir, 'baseline', skip_existing,
                progress_callback, cancel_check, on_downloaded=queue_for_import,
                files=remote_files)
            stats['total_errors'] += failed
        finally:
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
