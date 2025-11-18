"""PDF Management Utility

Handles PDF storage organization by publication year and provides utilities
for fetching, storing, and retrieving full-text PDFs.
"""

import os
import logging
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import requests

logger = logging.getLogger(__name__)


class PDFManager:
    """Manages PDF storage and retrieval with year-based organization."""

    def __init__(
        self,
        base_dir: Optional[str] = None,
        db_conn=None,
        openathens_auth=None,
        openathens_config: Optional[Dict[str, Any]] = None  # Deprecated, for backward compatibility
    ):
        """Initialize PDF manager.

        Args:
            base_dir: Base directory for PDF storage. If None, reads from environment.
            db_conn: Optional database connection for migration operations.
            openathens_auth: Optional OpenAthensAuth instance for authenticated downloads (recommended).
            openathens_config: Optional dict with OpenAthens config (deprecated, use openathens_auth instead).
                If provided, creates OpenAthensAuth instance internally.
                Dict keys: enabled, institution_url, session_timeout_hours
        """
        if base_dir is None:
            # Read from environment
            from dotenv import load_dotenv
            load_dotenv()
            base_dir = os.getenv('PDF_BASE_DIR', '~/knowledgebase/pdf')

        self.base_dir = Path(base_dir).expanduser()
        self.db_conn = db_conn

        # Handle backward compatibility with old openathens_config dict
        if openathens_config is not None and openathens_auth is None:
            import warnings
            warnings.warn(
                "openathens_config dict parameter is deprecated. "
                "Use openathens_auth parameter with OpenAthensAuth instance instead:\n"
                "  from bmlibrarian.utils.openathens_auth import OpenAthensConfig, OpenAthensAuth\n"
                "  config = OpenAthensConfig(institution_url='...')\n"
                "  auth = OpenAthensAuth(config=config)\n"
                "  pdf_manager = PDFManager(openathens_auth=auth)",
                DeprecationWarning,
                stacklevel=2
            )

            if openathens_config.get('enabled', False):
                try:
                    from .openathens_auth import OpenAthensAuth
                    institution_url = openathens_config.get('institution_url')
                    if institution_url:
                        # Use deprecated API for backward compatibility
                        self.openathens_auth = OpenAthensAuth(
                            institution_url=institution_url,
                            session_timeout_hours=openathens_config.get('session_timeout_hours', 24)
                        )
                    else:
                        logger.warning("OpenAthens enabled but no institution_url provided")
                        self.openathens_auth = None
                except ImportError:
                    logger.warning("OpenAthens requested but openathens_auth module not available")
                    self.openathens_auth = None
            else:
                self.openathens_auth = None
        else:
            # New API - use provided auth instance
            self.openathens_auth = openathens_auth

    def get_pdf_path(self, document: Dict[str, Any], create_dirs: bool = False) -> Optional[Path]:
        """Get the expected PDF path for a document.

        Uses year-based subdirectory organization: base_dir/YYYY/filename.pdf

        Args:
            document: Document dictionary with publication_date and pdf_filename
            create_dirs: If True, create year subdirectory if it doesn't exist

        Returns:
            Path to PDF file, or None if pdf_filename is missing
        """
        pdf_filename = document.get('pdf_filename')
        if not pdf_filename:
            return None

        # Check if pdf_filename already includes a path (year/filename.pdf)
        # If so, use it directly relative to base_dir
        if '/' in pdf_filename:
            # Already has directory structure - use as-is
            full_path = self.base_dir / pdf_filename
            if create_dirs:
                full_path.parent.mkdir(parents=True, exist_ok=True)
            return full_path

        # Extract year from publication_date for flat filenames
        year = self._extract_year(document)
        if year:
            year_dir = self.base_dir / str(year)
        else:
            # Fallback to 'unknown' subdirectory if no year available
            year_dir = self.base_dir / 'unknown'

        if create_dirs:
            year_dir.mkdir(parents=True, exist_ok=True)

        return year_dir / pdf_filename

    def pdf_exists(self, document: Dict[str, Any]) -> bool:
        """Check if PDF file exists for a document.

        Args:
            document: Document dictionary

        Returns:
            True if PDF exists on filesystem, False otherwise
        """
        pdf_path = self.get_pdf_path(document)
        if pdf_path is None:
            return False
        return pdf_path.exists()

    def download_pdf(
        self,
        document: Dict[str, Any],
        timeout: int = 30,
        max_retries: int = 3,
        use_browser_fallback: bool = True
    ) -> Optional[Path]:
        """Download PDF from URL and save to organized storage with retry logic.

        Args:
            document: Document dictionary with pdf_url
            timeout: Download timeout in seconds
            max_retries: Maximum number of retry attempts
            use_browser_fallback: If True, use browser automation when regular download fails

        Returns:
            Path to downloaded file, or None if download failed
        """
        pdf_url = document.get('pdf_url')
        if not pdf_url:
            logger.warning(f"No pdf_url for document {document.get('id')}")
            return None

        # Generate filename if not present
        if not document.get('pdf_filename'):
            document['pdf_filename'] = self._generate_filename(document)

        pdf_path = self.get_pdf_path(document, create_dirs=True)
        if pdf_path is None:
            return None

        # Try download with retries
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt + 1}/{max_retries} for {pdf_url}")
                else:
                    logger.info(f"Downloading PDF from {pdf_url}")

                # Prepare headers and cookies
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                    'Accept': 'application/pdf,*/*'
                }

                cookies = {}

                # Use OpenAthens authentication if available
                if self.openathens_auth and self.openathens_auth.is_authenticated():
                    # Get user agent from session
                    session_user_agent = self.openathens_auth.get_user_agent()
                    if session_user_agent:
                        headers['User-Agent'] = session_user_agent

                    # Convert cookies to requests format
                    session_cookies = self.openathens_auth.get_cookies()
                    for cookie in session_cookies:
                        cookies[cookie['name']] = cookie['value']

                    logger.info("Using OpenAthens authenticated session")

                response = requests.get(
                    pdf_url,
                    timeout=timeout,
                    stream=True,
                    headers=headers,
                    cookies=cookies,
                    allow_redirects=True
                )
                response.raise_for_status()

                # Verify content type if available
                content_type = response.headers.get('content-type', '').lower()
                if content_type and 'pdf' not in content_type and 'octet-stream' not in content_type:
                    logger.warning(f"Unexpected content type: {content_type} for {pdf_url}")

                # Save to file with progress tracking
                total_size = 0
                with open(pdf_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:  # filter out keep-alive new chunks
                            f.write(chunk)
                            total_size += len(chunk)

                # Verify file was actually written
                if total_size == 0:
                    logger.error(f"Downloaded file is empty: {pdf_url}")
                    if pdf_path.exists():
                        pdf_path.unlink()
                    if attempt < max_retries - 1:
                        continue
                    return None

                logger.info(f"PDF saved to {pdf_path} ({total_size} bytes)")
                return pdf_path

            except requests.exceptions.Timeout as e:
                logger.error(f"Download timeout for {pdf_url}: {e}")
                if attempt < max_retries - 1:
                    continue
                return None

            except requests.exceptions.HTTPError as e:
                # Don't retry on 403 Forbidden or 404 Not Found
                if e.response.status_code in [403, 404, 401]:
                    logger.error(f"HTTP {e.response.status_code} error (no retry): {pdf_url}")
                    return None
                logger.error(f"HTTP error downloading PDF: {e}")
                if attempt < max_retries - 1:
                    continue
                return None

            except requests.exceptions.ChunkedEncodingError as e:
                logger.error(f"Incomplete download (chunked encoding error): {e}")
                # Clean up partial file
                if pdf_path.exists():
                    pdf_path.unlink()
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2)  # Wait before retry
                    continue
                return None

            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error: {e}")
                if pdf_path.exists():
                    pdf_path.unlink()
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2)
                    continue
                return None

            except requests.RequestException as e:
                logger.error(f"Failed to download PDF: {e}")
                if pdf_path.exists():
                    pdf_path.unlink()
                if attempt < max_retries - 1:
                    continue
                return None

            except IOError as e:
                logger.error(f"Failed to save PDF: {e}")
                return None

        # All retries failed - try browser-based download if enabled
        if use_browser_fallback:
            logger.info(f"Regular download failed, attempting browser-based download for: {pdf_url}")
            try:
                from .browser_downloader import download_pdf_with_browser

                result = download_pdf_with_browser(
                    url=pdf_url,
                    save_path=pdf_path,
                    headless=True,
                    timeout=timeout * 1000  # Convert to milliseconds
                )

                if result['status'] == 'success':
                    logger.info(f"Browser download successful: {result['path']} ({result['size']} bytes)")
                    return pdf_path
                else:
                    logger.error(f"Browser download failed: {result.get('error', 'Unknown error')}")

            except ImportError:
                logger.warning(
                    "Browser downloader not available. Install with: "
                    "uv add playwright && uv run python -m playwright install chromium"
                )
            except Exception as e:
                logger.error(f"Browser download exception: {e}")

        return None

    def get_or_download_pdf(self, document: Dict[str, Any]) -> Optional[Path]:
        """Get PDF path if it exists, otherwise download it.

        Args:
            document: Document dictionary

        Returns:
            Path to PDF file, or None if not available
        """
        # Check if already exists
        if self.pdf_exists(document):
            return self.get_pdf_path(document)

        # Try to download
        return self.download_pdf(document)

    def _extract_year(self, document: Dict[str, Any]) -> Optional[int]:
        """Extract publication year from document.

        Args:
            document: Document dictionary

        Returns:
            Year as integer, or None if not found
        """
        # Try publication_date field (date object or string)
        pub_date = document.get('publication_date')
        if pub_date:
            if isinstance(pub_date, datetime):
                return pub_date.year
            elif isinstance(pub_date, str):
                try:
                    # Try parsing YYYY-MM-DD format
                    if '-' in pub_date:
                        year_str = pub_date.split('-')[0]
                        return int(year_str)
                    # Try parsing just YYYY
                    elif len(pub_date) >= 4:
                        return int(pub_date[:4])
                except (ValueError, IndexError):
                    pass

        # Try year field
        year = document.get('year')
        if year and isinstance(year, int):
            return year

        return None

    def _generate_filename(self, document: Dict[str, Any]) -> str:
        """Generate PDF filename from document metadata.

        Args:
            document: Document dictionary

        Returns:
            Generated filename string
        """
        doc_id = document.get('id', 'unknown')
        doi = document.get('doi', '')

        if doi:
            # Use DOI as filename (replace slashes with underscores)
            safe_doi = doi.replace('/', '_').replace('\\', '_')
            return f"{safe_doi}.pdf"
        else:
            # Use document ID
            return f"doc_{doc_id}.pdf"

    def get_relative_pdf_path(self, document: Dict[str, Any]) -> Optional[str]:
        """Get relative PDF path (without base directory) for database storage.

        Args:
            document: Document dictionary

        Returns:
            Relative path string (e.g., "2023/paper.pdf" or "unknown/paper.pdf")
        """
        pdf_filename = document.get('pdf_filename')
        if not pdf_filename:
            return None

        # Extract just the filename if it's already a path
        filename_only = Path(pdf_filename).name

        year = self._extract_year(document)
        if year:
            return f"{year}/{filename_only}"
        else:
            return f"unknown/{filename_only}"

    def update_database_pdf_path(self, doc_id: int, relative_path: str) -> bool:
        """Update pdf_filename in database to relative path.

        Args:
            doc_id: Document ID
            relative_path: Relative path (e.g., "2023/paper.pdf")

        Returns:
            True if successful, False otherwise
        """
        if not self.db_conn:
            logger.error("No database connection available")
            return False

        try:
            with self.db_conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE document SET pdf_filename = %s WHERE id = %s",
                    (relative_path, doc_id)
                )
                self.db_conn.commit()
                logger.info(f"Updated document {doc_id} pdf_filename to: {relative_path}")
                return True
        except Exception as e:
            logger.error(f"Failed to update database for document {doc_id}: {e}")
            self.db_conn.rollback()
            return False

    def migrate_pdfs_to_year_structure(
        self,
        dry_run: bool = True,
        update_database: bool = True
    ) -> Dict[str, Any]:
        """Migrate existing PDFs from flat or absolute paths to year-based structure.

        This function:
        1. Queries database for all documents with pdf_filename
        2. Checks if PDF exists at current path
        3. Moves PDF to year-based directory structure
        4. Updates database with relative path (omitting base_dir)

        Args:
            dry_run: If True, only report what would be done without making changes
            update_database: If True, update pdf_filename in database to relative paths

        Returns:
            Dictionary with migration statistics and details
        """
        if not self.db_conn:
            logger.error("Database connection required for migration")
            return {
                'error': 'No database connection',
                'total': 0,
                'migrated': 0,
                'failed': 0,
                'skipped': 0
            }

        stats = {
            'total': 0,
            'migrated': 0,
            'failed': 0,
            'skipped': 0,
            'already_organized': 0,
            'not_found': 0,
            'details': []
        }

        try:
            # Query all documents with pdf_filename
            with self.db_conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, pdf_filename, publication_date, doi, title
                    FROM document
                    WHERE pdf_filename IS NOT NULL
                    ORDER BY id
                """)
                documents = cursor.fetchall()

            logger.info(f"Found {len(documents)} documents with pdf_filename")

            for doc_id, pdf_filename, pub_date, doi, title in documents:
                stats['total'] += 1

                # Create document dict for helper methods
                doc = {
                    'id': doc_id,
                    'pdf_filename': pdf_filename,
                    'publication_date': str(pub_date) if pub_date else None,
                    'doi': doi,
                    'title': title
                }

                # Determine current and target paths
                result = self._migrate_single_pdf(doc, dry_run, update_database)

                # Update stats
                if result['status'] == 'migrated':
                    stats['migrated'] += 1
                elif result['status'] == 'failed':
                    stats['failed'] += 1
                elif result['status'] == 'skipped':
                    stats['skipped'] += 1
                elif result['status'] == 'already_organized':
                    stats['already_organized'] += 1
                elif result['status'] == 'not_found':
                    stats['not_found'] += 1

                stats['details'].append(result)

                # Log progress every 100 documents
                if stats['total'] % 100 == 0:
                    logger.info(f"Progress: {stats['total']} processed, "
                              f"{stats['migrated']} migrated, {stats['failed']} failed")

        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            stats['error'] = str(e)

        return stats

    def _migrate_single_pdf(
        self,
        doc: Dict[str, Any],
        dry_run: bool,
        update_database: bool
    ) -> Dict[str, Any]:
        """Migrate a single PDF file.

        Args:
            doc: Document dictionary
            dry_run: If True, don't actually move files or update database
            update_database: If True, update database with new relative path

        Returns:
            Dictionary with migration result details
        """
        doc_id = doc['id']
        pdf_filename = doc['pdf_filename']

        # Determine current PDF path
        current_path = self._find_current_pdf_path(pdf_filename)

        if current_path is None:
            return {
                'status': 'not_found',
                'doc_id': doc_id,
                'current_path': pdf_filename,
                'message': 'PDF file not found'
            }

        # Determine target path
        relative_path = self.get_relative_pdf_path(doc)
        if relative_path is None:
            return {
                'status': 'failed',
                'doc_id': doc_id,
                'message': 'Could not determine target path'
            }

        target_path = self.base_dir / relative_path

        # Check if already in correct location
        if current_path.resolve() == target_path.resolve():
            return {
                'status': 'already_organized',
                'doc_id': doc_id,
                'path': str(relative_path)
            }

        # Check if already has relative path format (YYYY/filename or unknown/filename)
        if '/' in pdf_filename and not pdf_filename.startswith('/'):
            # Already using relative path format
            if current_path.exists():
                return {
                    'status': 'already_organized',
                    'doc_id': doc_id,
                    'path': pdf_filename
                }

        # Perform migration
        if not dry_run:
            try:
                # Create target directory
                target_path.parent.mkdir(parents=True, exist_ok=True)

                # Move file
                shutil.move(str(current_path), str(target_path))
                logger.info(f"Moved: {current_path} -> {target_path}")

                # Update database
                if update_database:
                    success = self.update_database_pdf_path(doc_id, relative_path)
                    if not success:
                        # Try to move file back
                        shutil.move(str(target_path), str(current_path))
                        return {
                            'status': 'failed',
                            'doc_id': doc_id,
                            'message': 'Database update failed, file moved back'
                        }

                return {
                    'status': 'migrated',
                    'doc_id': doc_id,
                    'from': str(current_path),
                    'to': str(relative_path)
                }

            except Exception as e:
                logger.error(f"Failed to migrate document {doc_id}: {e}")
                return {
                    'status': 'failed',
                    'doc_id': doc_id,
                    'error': str(e)
                }
        else:
            # Dry run - just report what would happen
            return {
                'status': 'would_migrate',
                'doc_id': doc_id,
                'from': str(current_path),
                'to': str(relative_path)
            }

    def _find_current_pdf_path(self, pdf_filename: str) -> Optional[Path]:
        """Find current location of PDF file.

        Checks multiple possible locations:
        1. Relative to base_dir (already organized)
        2. Directly in base_dir (flat structure)
        3. Absolute path (if pdf_filename is absolute)

        Args:
            pdf_filename: PDF filename or path from database

        Returns:
            Path object if found, None otherwise
        """
        # Try as relative path from base_dir
        relative_path = self.base_dir / pdf_filename
        if relative_path.exists():
            return relative_path

        # Try as absolute path
        if pdf_filename.startswith('/'):
            abs_path = Path(pdf_filename)
            if abs_path.exists():
                return abs_path

        # Try in base directory (flat structure)
        filename_only = Path(pdf_filename).name
        flat_path = self.base_dir / filename_only
        if flat_path.exists():
            return flat_path

        return None

    def download_missing_pdfs(
        self,
        batch_size: int = 100,
        max_batches: Optional[int] = None,
        timeout: int = 30,
        update_database: bool = True,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Download missing PDFs in batches.

        Finds documents that have pdf_url but no local PDF file, then downloads them
        in batches.

        Args:
            batch_size: Number of PDFs to download per batch (default: 100)
            max_batches: Maximum number of batches to process (None = all)
            timeout: Download timeout in seconds per PDF
            update_database: If True, update pdf_filename in database after download
            progress_callback: Optional callback(current, total, doc_id, status)

        Returns:
            Dictionary with download statistics and details
        """
        if not self.db_conn:
            logger.error("Database connection required for batch downloads")
            return {
                'error': 'No database connection',
                'total': 0,
                'downloaded': 0,
                'failed': 0,
                'skipped': 0
            }

        stats = {
            'total_missing': 0,
            'processed': 0,
            'downloaded': 0,
            'failed': 0,
            'already_exists': 0,
            'no_url': 0,
            'details': []
        }

        try:
            # Query documents with pdf_url but check if PDF exists
            with self.db_conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, pdf_url, pdf_filename, publication_date, doi, title
                    FROM document
                    WHERE pdf_url IS NOT NULL
                    ORDER BY id
                """)
                all_candidates = cursor.fetchall()

            logger.info(f"Found {len(all_candidates)} documents with pdf_url")

            # Filter to only those missing local PDF
            missing_pdfs = []
            for doc_id, pdf_url, pdf_filename, pub_date, doi, title in all_candidates:
                doc = {
                    'id': doc_id,
                    'pdf_url': pdf_url,
                    'pdf_filename': pdf_filename,
                    'publication_date': str(pub_date) if pub_date else None,
                    'doi': doi,
                    'title': title
                }

                # Check if PDF already exists
                if pdf_filename:
                    existing_path = self._find_current_pdf_path(pdf_filename)
                    if existing_path:
                        stats['already_exists'] += 1
                        continue

                missing_pdfs.append(doc)

            stats['total_missing'] = len(missing_pdfs)
            logger.info(f"Found {stats['total_missing']} missing PDFs to download")

            # Process in batches
            batch_num = 0
            for i in range(0, len(missing_pdfs), batch_size):
                batch = missing_pdfs[i:i + batch_size]
                batch_num += 1

                # Check max_batches limit
                if max_batches and batch_num > max_batches:
                    logger.info(f"Reached max_batches limit ({max_batches})")
                    break

                logger.info(f"Processing batch {batch_num} ({len(batch)} documents)")

                # Download each PDF in batch
                for j, doc in enumerate(batch):
                    stats['processed'] += 1
                    doc_id = doc['id']

                    # Progress callback
                    if progress_callback:
                        progress_callback(stats['processed'], stats['total_missing'],
                                        doc_id, 'downloading')

                    # Download PDF
                    result = self._download_single_pdf(doc, timeout, update_database)

                    # Update stats
                    if result['status'] == 'downloaded':
                        stats['downloaded'] += 1
                    elif result['status'] == 'failed':
                        stats['failed'] += 1

                    stats['details'].append(result)

                    # Log progress within batch
                    if (j + 1) % 10 == 0:
                        logger.info(f"  Batch progress: {j + 1}/{len(batch)} "
                                  f"(success: {stats['downloaded']}, failed: {stats['failed']})")

                # Log batch completion
                logger.info(f"Completed batch {batch_num}: "
                          f"downloaded {stats['downloaded']}, failed {stats['failed']}")

        except Exception as e:
            logger.error(f"Download process failed: {e}", exc_info=True)
            stats['error'] = str(e)

        return stats

    def _download_single_pdf(
        self,
        doc: Dict[str, Any],
        timeout: int,
        update_database: bool
    ) -> Dict[str, Any]:
        """Download a single PDF and optionally update database.

        Args:
            doc: Document dictionary
            timeout: Download timeout in seconds
            update_database: If True, update database with pdf_filename

        Returns:
            Dictionary with download result details
        """
        doc_id = doc['id']
        pdf_url = doc.get('pdf_url')

        if not pdf_url:
            return {
                'status': 'failed',
                'doc_id': doc_id,
                'reason': 'no_url'
            }

        try:
            # Generate filename if not present
            if not doc.get('pdf_filename'):
                doc['pdf_filename'] = self._generate_filename(doc)

            # Download PDF with retry logic
            pdf_path = self.download_pdf(doc, timeout=timeout, max_retries=3)

            if not pdf_path:
                return {
                    'status': 'failed',
                    'doc_id': doc_id,
                    'reason': 'download_failed',
                    'url': pdf_url
                }

            # Update database with relative path
            if update_database:
                relative_path = self.get_relative_pdf_path(doc)
                if relative_path:
                    success = self.update_database_pdf_path(doc_id, relative_path)
                    if not success:
                        logger.warning(f"Downloaded PDF but failed to update database for doc {doc_id}")
                        return {
                            'status': 'downloaded',
                            'doc_id': doc_id,
                            'path': str(pdf_path),
                            'db_updated': False
                        }

            return {
                'status': 'downloaded',
                'doc_id': doc_id,
                'path': str(pdf_path),
                'db_updated': update_database
            }

        except Exception as e:
            logger.error(f"Failed to download PDF for document {doc_id}: {e}")
            return {
                'status': 'failed',
                'doc_id': doc_id,
                'reason': 'exception',
                'error': str(e)
            }

    def reconstruct_doi_from_filename(self, filename: str) -> Optional[str]:
        """Reconstruct DOI from PDF filename.

        Reverses the DOI-to-filename conversion where slashes were replaced
        with underscores OR hyphens.

        Args:
            filename: PDF filename (e.g., "10.1234_example.pdf" or "10.1234-example.pdf")

        Returns:
            Reconstructed DOI (e.g., "10.1234/example") or None if not DOI-like
        """
        # Remove .pdf extension
        name_without_ext = filename.replace('.pdf', '')

        # Check if it looks like a DOI (starts with "10.")
        if not name_without_ext.startswith('10.'):
            return None

        # Some filenames use hyphens instead of underscores
        # Try underscores first (most common)
        if '_' in name_without_ext:
            reconstructed_doi = name_without_ext.replace('_', '/')
        elif '-' in name_without_ext:
            # Fallback to hyphens (less common but exists)
            reconstructed_doi = name_without_ext.replace('-', '/')
        else:
            # No separators - probably not a DOI format we can reconstruct
            return None

        return reconstructed_doi

    def find_document_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """Find document in database by DOI.

        Args:
            doi: DOI to search for

        Returns:
            Document dictionary if found, None otherwise
        """
        if not self.db_conn:
            logger.error("No database connection available")
            return None

        try:
            with self.db_conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, doi, title, publication_date, pdf_filename, pdf_url
                    FROM document
                    WHERE doi = %s
                """, (doi,))
                result = cursor.fetchone()

                if result:
                    doc_id, doi, title, pub_date, pdf_filename, pdf_url = result
                    return {
                        'id': doc_id,
                        'doi': doi,
                        'title': title,
                        'publication_date': str(pub_date) if pub_date else None,
                        'pdf_filename': pdf_filename,
                        'pdf_url': pdf_url
                    }

        except Exception as e:
            logger.error(f"Failed to query database for DOI {doi}: {e}")

        return None

    def match_orphaned_pdfs(
        self,
        directory: Optional[Path] = None,
        dry_run: bool = True,
        include_subdirs: bool = True
    ) -> Dict[str, Any]:
        """Match orphaned PDFs to documents by reconstructing DOI from filename.

        Finds PDF files in the specified directory (or base_dir), attempts to
        reconstruct DOI from filename, searches database for matching document,
        and optionally links the PDF to the document.

        Args:
            directory: Directory to search for orphaned PDFs (default: base_dir)
            dry_run: If True, only report matches without updating database
            include_subdirs: If True, also search 'failed' and 'unknown' subdirs

        Returns:
            Dictionary with matching statistics and details
        """
        if directory is None:
            directory = self.base_dir

        if not directory.exists():
            logger.error(f"Directory does not exist: {directory}")
            return {
                'error': f'Directory not found: {directory}',
                'total': 0,
                'matched': 0,
                'linked': 0,
                'failed': 0
            }

        stats = {
            'total_pdfs': 0,
            'doi_reconstructed': 0,
            'matched': 0,
            'linked': 0,
            'already_linked': 0,
            'replaced': 0,
            'duplicates_deleted': 0,
            'no_match': 0,
            'not_doi_format': 0,
            'failed': 0,
            'details': []
        }

        # Determine directories to search
        search_dirs = [directory]

        if include_subdirs:
            # Also search common orphan directories
            failed_dir = directory / 'failed'
            unknown_dir = directory / 'unknown'

            if failed_dir.exists():
                search_dirs.append(failed_dir)
                logger.info(f"Will also search: {failed_dir}")

            if unknown_dir.exists():
                search_dirs.append(unknown_dir)
                logger.info(f"Will also search: {unknown_dir}")

        # Collect all PDF files from all search directories
        pdf_files = []
        for search_dir in search_dirs:
            logger.info(f"Searching for orphaned PDFs in: {search_dir}")
            dir_pdfs = list(search_dir.glob('*.pdf'))
            pdf_files.extend(dir_pdfs)
            logger.info(f"  Found {len(dir_pdfs)} PDFs")

        stats['total_pdfs'] = len(pdf_files)
        logger.info(f"Total PDFs found: {stats['total_pdfs']}")

        for pdf_file in pdf_files:
            filename = pdf_file.name

            # Try to reconstruct DOI from filename
            doi = self.reconstruct_doi_from_filename(filename)

            if not doi:
                stats['not_doi_format'] += 1
                stats['details'].append({
                    'filename': filename,
                    'status': 'not_doi_format'
                })
                continue

            stats['doi_reconstructed'] += 1

            # Search database for document with this DOI
            doc = self.find_document_by_doi(doi)

            if not doc:
                stats['no_match'] += 1
                stats['details'].append({
                    'filename': filename,
                    'doi': doi,
                    'status': 'no_match'
                })
                continue

            stats['matched'] += 1

            # Check if document already has a pdf_filename
            if doc.get('pdf_filename'):
                # First, check if file exists at the CORRECT year-based location
                correct_path = self.get_pdf_path(doc)

                if correct_path and correct_path.exists():
                    # File exists at correct location
                    # Check if orphaned file is the same or different
                    if correct_path.resolve() == pdf_file.resolve():
                        # Same file - already in correct location, just skip
                        stats['already_linked'] += 1
                        stats['details'].append({
                            'filename': filename,
                            'doi': doi,
                            'doc_id': doc['id'],
                            'status': 'already_in_correct_location',
                            'path': str(correct_path)
                        })
                        continue
                    else:
                        # Different file - orphaned is a duplicate
                        # Compare file dates, keep newer
                        orphaned_mtime = pdf_file.stat().st_mtime
                        correct_mtime = correct_path.stat().st_mtime

                        if orphaned_mtime > correct_mtime:
                            # Orphaned is newer - replace correct file
                            logger.info(f"Orphaned PDF {pdf_file} is newer than {correct_path} - replacing")
                            if not dry_run:
                                correct_path.unlink()  # Delete older file
                                # Will move orphaned below and count as replacement
                                stats['replaced'] += 1
                            stats['details'].append({
                                'filename': filename,
                                'doi': doi,
                                'doc_id': doc['id'],
                                'status': 'will_replace_older' if dry_run else 'replaced_older',
                                'newer': str(pdf_file),
                                'deleted': str(correct_path)
                            })
                        else:
                            # Correct file is newer - delete orphaned
                            logger.info(f"Orphaned PDF {pdf_file} is older than {correct_path} - deleting")
                            if not dry_run:
                                pdf_file.unlink()
                            stats['duplicates_deleted'] += 1
                            stats['details'].append({
                                'filename': filename,
                                'doi': doi,
                                'doc_id': doc['id'],
                                'status': 'duplicate_deleted_older',
                                'kept': str(correct_path),
                                'deleted': str(pdf_file)
                            })
                            continue
                else:
                    # File NOT at correct location - need to move orphaned file there
                    logger.info(f"Document {doc['id']} has pdf_filename but not at correct location - will move {pdf_file}")

            # Link PDF to document (moves to correct location and updates DB)
            if not dry_run:
                result = self._link_orphaned_pdf(pdf_file, doc)
                if result['status'] == 'linked':
                    stats['linked'] += 1
                else:
                    stats['failed'] += 1
                stats['details'].append(result)
            else:
                stats['details'].append({
                    'filename': filename,
                    'doi': doi,
                    'doc_id': doc['id'],
                    'doc_title': doc.get('title', 'Unknown'),
                    'status': 'would_link',
                    'current_location': str(pdf_file)
                })

        return stats

    def _link_orphaned_pdf(
        self,
        pdf_file: Path,
        doc: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Link an orphaned PDF file to a document.

        Moves the PDF to the year-based directory structure and updates
        the database.

        Args:
            pdf_file: Path to orphaned PDF file
            doc: Document dictionary

        Returns:
            Dictionary with link result details
        """
        doc_id = doc['id']
        filename = pdf_file.name

        try:
            # Set pdf_filename in document for path calculation
            doc['pdf_filename'] = filename

            # Determine target path (year-based)
            relative_path = self.get_relative_pdf_path(doc)
            if not relative_path:
                return {
                    'filename': filename,
                    'doi': doc.get('doi'),
                    'doc_id': doc_id,
                    'status': 'failed',
                    'reason': 'Could not determine target path'
                }

            target_path = self.base_dir / relative_path

            # Create year directory if needed
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Move file
            shutil.move(str(pdf_file), str(target_path))
            logger.info(f"Moved orphaned PDF: {pdf_file} -> {target_path}")

            # Update database
            success = self.update_database_pdf_path(doc_id, relative_path)

            if not success:
                # Try to move file back
                shutil.move(str(target_path), str(pdf_file))
                return {
                    'filename': filename,
                    'doi': doc.get('doi'),
                    'doc_id': doc_id,
                    'status': 'failed',
                    'reason': 'Database update failed, file moved back'
                }

            return {
                'filename': filename,
                'doi': doc.get('doi'),
                'doc_id': doc_id,
                'doc_title': doc.get('title', 'Unknown'),
                'status': 'linked',
                'from': str(pdf_file),
                'to': str(relative_path)
            }

        except Exception as e:
            logger.error(f"Failed to link orphaned PDF {filename} to document {doc_id}: {e}")
            return {
                'filename': filename,
                'doi': doc.get('doi'),
                'doc_id': doc_id,
                'status': 'failed',
                'reason': str(e)
            }
