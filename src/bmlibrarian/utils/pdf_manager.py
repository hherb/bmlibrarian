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

    def __init__(self, base_dir: Optional[str] = None, db_conn=None):
        """Initialize PDF manager.

        Args:
            base_dir: Base directory for PDF storage. If None, reads from environment.
            db_conn: Optional database connection for migration operations.
        """
        if base_dir is None:
            # Read from environment
            from dotenv import load_dotenv
            load_dotenv()
            base_dir = os.getenv('PDF_BASE_DIR', '~/knowledgebase/pdf')

        self.base_dir = Path(base_dir).expanduser()
        self.db_conn = db_conn

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

        # Extract year from publication_date
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

    def download_pdf(self, document: Dict[str, Any], timeout: int = 30) -> Optional[Path]:
        """Download PDF from URL and save to organized storage.

        Args:
            document: Document dictionary with pdf_url
            timeout: Download timeout in seconds

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

        # Download the file
        try:
            logger.info(f"Downloading PDF from {pdf_url}")
            response = requests.get(pdf_url, timeout=timeout, stream=True)
            response.raise_for_status()

            # Save to file
            with open(pdf_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"PDF saved to {pdf_path}")
            return pdf_path

        except requests.RequestException as e:
            logger.error(f"Failed to download PDF: {e}")
            return None
        except IOError as e:
            logger.error(f"Failed to save PDF: {e}")
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

            # Download PDF
            pdf_path = self.download_pdf(doc, timeout=timeout)

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
