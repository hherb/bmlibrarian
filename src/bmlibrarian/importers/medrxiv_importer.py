"""
MedRxiv Importer for BMLibrarian

This module provides functionality to import biomedical preprints from medRxiv
using their API, download PDFs, and extract full text.

Example usage:
    from bmlibrarian.importers import MedRxivImporter

    importer = MedRxivImporter()
    importer.update_database(download_pdfs=True, days_to_fetch=30)
    importer.fetch_missing_pdfs(limit=100)
"""

import os
import sys
import time
import logging
import requests
import multiprocessing
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Tuple, Callable
from pathlib import Path

# Import bmlibrarian components
from bmlibrarian.database import get_db_manager

# Configure logging
logger = logging.getLogger(__name__)

try:
    import pymupdf4llm
except ImportError:
    logger.warning("pymupdf4llm not installed. PDF text extraction will not be available.")
    pymupdf4llm = None

try:
    from tqdm import tqdm
except ImportError:
    # Fallback if tqdm is not installed
    logger.warning("tqdm not installed. Progress bars will not be displayed.")
    tqdm = None


# Timeout constant for PDF extraction (seconds)
PDF_EXTRACTION_TIMEOUT_SECONDS = 60

# Use 'spawn' start method on macOS to avoid fork-related issues
# This must be set before any multiprocessing operations
try:
    multiprocessing.set_start_method('spawn', force=False)
except RuntimeError:
    # Already set - this is fine
    pass


def _extract_pdf_in_subprocess(pdf_path: str, result_queue: multiprocessing.Queue) -> None:
    """
    Worker function to extract PDF content in a subprocess.

    This isolates potential segfaults in pymupdf4llm from crashing the main process.

    Args:
        pdf_path: Full path to the PDF file
        result_queue: Queue to put the result (markdown text or empty string on error)
    """
    try:
        import pymupdf4llm
        markdown_text = pymupdf4llm.to_markdown(pdf_path)
        result_queue.put(markdown_text)
    except Exception as e:
        # Log error and return empty string
        result_queue.put("")


class MedRxivImporter:
    """
    Importer for medRxiv biomedical preprints.

    This class handles fetching metadata from the medRxiv API, downloading PDFs,
    extracting full text, and storing documents in the BMLibrarian database.
    """

    MEDRXIV_API_BASE = "https://api.biorxiv.org/details/medrxiv"
    MEDRXIV_LAUNCH_DATE = "2019-06-06"

    def __init__(self, pdf_base_dir: Optional[str] = None):
        """
        Initialize the MedRxiv importer.

        Args:
            pdf_base_dir: Base directory for PDF storage. If None, uses PDF_BASE_DIR
                         environment variable or defaults to ~/knowledgebase/pdf
        """
        self.db_manager = get_db_manager()

        # Set up PDF storage directory
        if pdf_base_dir:
            self.pdf_base_dir = Path(pdf_base_dir).expanduser()
        else:
            pdf_dir = os.environ.get('PDF_BASE_DIR', '~/knowledgebase/pdf')
            self.pdf_base_dir = Path(pdf_dir).expanduser()

        # Ensure PDF directory exists
        self.pdf_base_dir.mkdir(parents=True, exist_ok=True)

        # Get source_id for medRxiv
        self.source_id = self._get_source_id('medrxiv')
        if not self.source_id:
            raise ValueError("MedRxiv source not found in database. Please ensure 'sources' table contains 'medrxiv' entry.")

        logger.info(f"MedRxiv importer initialized with PDF directory: {self.pdf_base_dir}")

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

    def _format_abstract_markdown(self, abstract: str) -> str:
        """
        Format medRxiv abstract with Markdown styling for readability.

        CRITICAL: This function performs ONLY aesthetic changes:
        1. Adds paragraph breaks (double newlines) before section headers
        2. Makes recognized section headers bold using Markdown **syntax**

        It NEVER:
        - Truncates or removes any content
        - Changes wording or alters the original text
        - Removes punctuation or modifies sentences
        - Deletes any characters from the original

        Section headers are recognized when they:
        1. Appear at the absolute start of the abstract, OR
        2. Appear after a newline, OR
        3. Appear immediately after ". " (period + space = sentence boundary)

        Headers can be followed by:
        - A colon (e.g., "Background:")
        - Directly by uppercase letter (e.g., "BackgroundAustralia")

        Args:
            abstract: Raw abstract text from medRxiv API

        Returns:
            Abstract with Markdown formatting (bold headers, paragraph breaks)
            Original content is fully preserved.
        """
        import re

        if not abstract:
            return ''

        # Section header keywords (case-insensitive)
        # Only the main IMRaD sections
        header_keywords = (
            r'Background|Introduction|Context|Rationale|'
            r'Objectives?|Aims?|Purpose|'
            r'Methods?|Methodology|Materials and Methods|'
            r'Results?|Findings?|'
            r'Conclusions?|Discussion|'
            r'Trial Registration|Funding'
        )

        # Pattern 1a: Header at start followed by colon
        start_colon_pattern = re.compile(
            r'^(' + header_keywords + r')(\s*:)',
            re.IGNORECASE
        )

        # Pattern 1b: Header at start followed directly by uppercase (no space/colon)
        # e.g., "BackgroundAustralia" -> "**BACKGROUND**Australia"
        start_nospace_pattern = re.compile(
            r'^(' + header_keywords + r')(?=[A-Z])',
            re.IGNORECASE
        )

        # Pattern 2a: Header after sentence boundary followed by colon
        sentence_colon_pattern = re.compile(
            r'(\. )(' + header_keywords + r')(\s*:)',
            re.IGNORECASE
        )

        # Pattern 2b: Header after sentence boundary followed directly by uppercase
        # e.g., ". MethodsNational" -> ". \n\n**METHODS**National"
        sentence_nospace_pattern = re.compile(
            r'(\.\s*)(' + header_keywords + r')(?=[A-Z])',
            re.IGNORECASE
        )

        # Pattern 3: Header after newline followed by uppercase (no colon)
        newline_nospace_pattern = re.compile(
            r'(\n)(' + header_keywords + r')(?=[A-Z])',
            re.IGNORECASE
        )

        def replace_start_colon(match: re.Match) -> str:
            """Replace header at start (with colon) with bold version."""
            header_word = match.group(1)
            colon_part = match.group(2)
            return f'**{header_word.upper()}**{colon_part}'

        def replace_start_nospace(match: re.Match) -> str:
            """Replace header at start (no colon) with bold version + space."""
            header_word = match.group(1)
            return f'**{header_word.upper()}** '

        def replace_sentence_colon(match: re.Match) -> str:
            """Replace header after sentence (with colon) with bold + paragraph break."""
            period_space = match.group(1)
            header_word = match.group(2)
            colon_part = match.group(3)
            return f'{period_space}\n\n**{header_word.upper()}**{colon_part}'

        def replace_sentence_nospace(match: re.Match) -> str:
            """Replace header after sentence (no colon) with bold + paragraph break."""
            period_part = match.group(1)  # Could be ". " or ".\n" etc.
            header_word = match.group(2)
            return f'{period_part}\n\n**{header_word.upper()}** '

        def replace_newline_nospace(match: re.Match) -> str:
            """Replace header after newline (no colon) with bold."""
            newline = match.group(1)
            header_word = match.group(2)
            return f'{newline}**{header_word.upper()}** '

        # Apply patterns in order of specificity
        formatted = abstract

        # Start patterns
        formatted = start_colon_pattern.sub(replace_start_colon, formatted)
        formatted = start_nospace_pattern.sub(replace_start_nospace, formatted)

        # Sentence boundary patterns
        formatted = sentence_colon_pattern.sub(replace_sentence_colon, formatted)
        formatted = sentence_nospace_pattern.sub(replace_sentence_nospace, formatted)

        # Newline patterns
        formatted = newline_nospace_pattern.sub(replace_newline_nospace, formatted)

        return formatted

    def _split_date_range_into_weeks(self, start_date: str, end_date: str) -> List[Tuple[str, str]]:
        """
        Split a date range into weekly chunks to avoid overwhelming the API.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            List of (start, end) date tuples for each week
        """
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        date_ranges = []
        current = start

        while current <= end:
            week_end = min(current + timedelta(days=6), end)
            date_ranges.append((
                current.strftime('%Y-%m-%d'),
                week_end.strftime('%Y-%m-%d')
            ))
            current = week_end + timedelta(days=1)

        return date_ranges

    def fetch_metadata(self, start_date: Optional[str] = None, end_date: Optional[str] = None,
                      batch_size: int = 100, max_retries: int = 5) -> List[Dict[str, Any]]:
        """
        Fetch medRxiv metadata using their API.

        API documentation: https://api.biorxiv.org/

        Args:
            start_date: Start date in YYYY-MM-DD format (defaults to medRxiv launch)
            end_date: End date in YYYY-MM-DD format (defaults to today)
            batch_size: Number of papers per API request
            max_retries: Maximum number of retry attempts for failed requests

        Returns:
            List of paper metadata dictionaries
        """
        if not start_date:
            start_date = self.MEDRXIV_LAUNCH_DATE
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')

        all_papers = []
        cursor = 0

        # First request to get total count
        try:
            response = requests.get(
                f"{self.MEDRXIV_API_BASE}/{start_date}/{end_date}/0",
                timeout=(10, 30)
            )
            response.raise_for_status()
            data = response.json()
            total_count = int(data.get('messages', [{}])[0].get('total', 0))

            if total_count == 0:
                logger.info("No papers found in the specified date range.")
                return all_papers

            logger.info(f"Found {total_count} papers from {start_date} to {end_date}")

            # Create progress bar if tqdm is available
            if tqdm:
                progress = tqdm(total=total_count, desc="Fetching papers", unit="papers")
            else:
                progress = None

        except Exception as e:
            logger.error(f"Error getting paper count: {e}")
            total_count = None
            progress = None

        # Fetch papers in batches
        while True:
            url = f"{self.MEDRXIV_API_BASE}/{start_date}/{end_date}/{cursor}"

            # Retry logic with exponential backoff
            retry_count = 0
            success = False

            while retry_count < max_retries and not success:
                try:
                    response = requests.get(url, timeout=(10, 30))
                    response.raise_for_status()
                    success = True
                except (requests.exceptions.ConnectionError,
                       requests.exceptions.Timeout) as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        logger.error(f"Failed to connect to {url} after {max_retries} attempts")
                        return all_papers

                    wait_time = 2 ** retry_count
                    logger.warning(f"Connection failed. Retrying in {wait_time}s... (Attempt {retry_count}/{max_retries})")
                    time.sleep(wait_time)
                except Exception as e:
                    logger.error(f"Unexpected error: {e}")
                    return all_papers

            if not success:
                break

            try:
                data = response.json()
                collection = data.get('collection', [])

                if not collection:
                    break

                all_papers.extend(collection)

                if progress:
                    progress.update(len(collection))

                cursor += batch_size

                # Check if we've reached the end
                if len(collection) < batch_size:
                    break

                # Be nice to the API
                time.sleep(1)

            except Exception as e:
                logger.error(f"Error processing API response: {e}")
                break

        if progress:
            progress.close()

        logger.info(f"Fetched {len(all_papers)} papers total")
        return all_papers

    def download_pdf(self, paper: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """
        Download the PDF for a paper.

        Args:
            paper: Paper metadata dict containing 'doi' and 'version'

        Returns:
            Tuple of (filename, was_downloaded) where:
            - filename is the name of the PDF file or None if download failed
            - was_downloaded is True if newly downloaded, False if already existed
        """
        doi = paper.get('doi', '')
        version = paper.get('version', '1')

        # Create safe filename from DOI
        safe_filename = doi.replace('/', '_') + '.pdf'
        local_path = self.pdf_base_dir / safe_filename

        # Skip if already downloaded
        if local_path.exists():
            logger.debug(f"PDF already exists: {safe_filename}")
            return safe_filename, False

        # Construct PDF URL
        pdf_url = f"https://www.medrxiv.org/content/{doi}v{version}.full.pdf"

        try:
            response = requests.get(pdf_url, stream=True, timeout=30)
            if response.status_code == 200:
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info(f"Downloaded {pdf_url}")
                return safe_filename, True
            else:
                logger.warning(f"Failed to download {pdf_url}: HTTP {response.status_code}")
                return None, False
        except Exception as e:
            logger.error(f"Error downloading {pdf_url}: {e}")
            return None, False

    def extract_full_text(self, filename: str, timeout_seconds: int = PDF_EXTRACTION_TIMEOUT_SECONDS) -> str:
        """
        Extract content from PDF as markdown using subprocess isolation.

        This method runs pymupdf4llm in a separate subprocess to prevent segfaults
        from crashing the main process. This is necessary because PyMuPDF can
        occasionally crash on malformed PDFs, especially on macOS ARM.

        Args:
            filename: Filename of the PDF (not full path)
            timeout_seconds: Maximum time to spend on conversion

        Returns:
            Markdown formatted text extracted from the PDF or empty string if conversion fails
        """
        if not pymupdf4llm:
            logger.warning("pymupdf4llm not available. Cannot extract text from PDF.")
            return ""

        pdf_path = self.pdf_base_dir / filename

        if not pdf_path.exists():
            logger.error(f"PDF file not found: {pdf_path}")
            return ""

        try:
            import shutil

            # Use subprocess to isolate potential segfaults
            result_queue: multiprocessing.Queue = multiprocessing.Queue()
            process = multiprocessing.Process(
                target=_extract_pdf_in_subprocess,
                args=(str(pdf_path), result_queue)
            )
            process.start()
            process.join(timeout=timeout_seconds)

            if process.is_alive():
                # Process timed out - terminate it
                logger.warning(f"PDF processing timed out after {timeout_seconds} seconds for {filename}")
                process.terminate()
                process.join(timeout=5)  # Give it 5 seconds to terminate gracefully
                if process.is_alive():
                    process.kill()  # Force kill if still alive
                    process.join()

                # Move problematic PDF to 'failed' subdirectory
                failed_dir = self.pdf_base_dir / 'failed'
                failed_dir.mkdir(exist_ok=True)
                failed_path = failed_dir / filename
                if pdf_path.exists():  # Check it wasn't already moved
                    shutil.move(str(pdf_path), str(failed_path))
                    logger.info(f"Moved problematic PDF {filename} to {failed_dir}")
                return ""

            # Check if process crashed (non-zero exit code indicates crash/segfault)
            if process.exitcode != 0:
                logger.warning(f"PDF extraction subprocess crashed (exit code {process.exitcode}) for {filename}")
                # Move problematic PDF to 'failed' subdirectory
                failed_dir = self.pdf_base_dir / 'failed'
                failed_dir.mkdir(exist_ok=True)
                failed_path = failed_dir / filename
                if pdf_path.exists():
                    shutil.move(str(pdf_path), str(failed_path))
                    logger.info(f"Moved problematic PDF {filename} to {failed_dir}")
                return ""

            # Get result from queue
            try:
                markdown_text = result_queue.get_nowait()
                if markdown_text:
                    logger.debug(f"Successfully converted {filename} to markdown")
                return markdown_text
            except Exception:
                logger.warning(f"No result from PDF extraction subprocess for {filename}")
                return ""

        except Exception as e:
            logger.error(f"Error extracting text from {filename}: {e}")
            return ""

    def _process_papers(self, papers: List[Dict[str, Any]], download_pdfs: bool = True) -> int:
        """
        Process and store papers in the database.

        Args:
            papers: List of paper metadata dicts
            download_pdfs: Whether to download PDFs for each paper

        Returns:
            Number of papers successfully processed
        """
        success_count = 0

        if tqdm:
            progress = tqdm(papers, desc="Processing papers", unit="paper")
        else:
            progress = papers

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                for paper in progress:
                    try:
                        doi = paper.get('doi', '')

                        # Set progress description
                        if tqdm:
                            progress.set_description(f"Processing {doi}")

                        # Check if already exists
                        cur.execute(
                            "SELECT id FROM document WHERE source_id = %s AND doi = %s",
                            (self.source_id, doi)
                        )
                        existing = cur.fetchone()

                        if existing:
                            logger.debug(f"Paper already exists: {doi}")
                            continue

                        # Handle authors
                        authors_list = paper.get('authors', [])
                        if isinstance(authors_list, list):
                            author_names = []
                            for author in authors_list:
                                if isinstance(author, dict) and 'author' in author:
                                    author_names.append(author['author'])
                                elif isinstance(author, str):
                                    author_names.append(author)
                            authors = author_names
                        else:
                            authors = [str(authors_list)] if authors_list else []

                        # Download PDF and extract text if requested
                        pdf_filename = ""
                        full_text = ""

                        if download_pdfs:
                            filename, was_downloaded = self.download_pdf(paper)
                            if filename:
                                pdf_filename = filename
                                # Extract text only if newly downloaded
                                if was_downloaded:
                                    full_text = self.extract_full_text(filename)

                        # Prepare data for insertion
                        title = paper.get('title', '')
                        # Format abstract with Markdown section headers
                        abstract = self._format_abstract_markdown(paper.get('abstract', ''))
                        date_posted = paper.get('date', '').split()[0] if ' ' in paper.get('date', '') else paper.get('date', '')
                        category = paper.get('category', '')
                        version = paper.get('version', '1')

                        pdf_url = f"https://www.medrxiv.org/content/{doi}v{version}.full.pdf"
                        url = f"https://www.medrxiv.org/content/{doi}"

                        # Insert document
                        cur.execute("""
                            INSERT INTO document (
                                source_id, external_id, doi, title, abstract,
                                authors, publication, publication_date,
                                url, pdf_url, pdf_filename, full_text
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING id
                        """, (
                            self.source_id,
                            doi,  # external_id
                            doi,
                            title,
                            abstract,
                            authors,
                            'medRxiv',  # publication name
                            date_posted or None,
                            url,
                            pdf_url,
                            pdf_filename,
                            full_text
                        ))

                        doc_id = cur.fetchone()[0]
                        logger.debug(f"Inserted document ID {doc_id} for DOI {doi}")
                        success_count += 1

                    except Exception as e:
                        logger.error(f"Error processing paper {paper.get('doi', 'unknown')}: {e}")
                        conn.rollback()
                        continue

        return success_count

    def get_latest_date(self) -> Optional[str]:
        """
        Get the latest publication date for medRxiv preprints in the database.

        Returns:
            Latest date in YYYY-MM-DD format or None if database is empty
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT publication_date
                    FROM document
                    WHERE source_id = %s
                    ORDER BY publication_date DESC
                    LIMIT 1
                """, (self.source_id,))

                result = cur.fetchone()
                if result and result[0]:
                    date_str = str(result[0])
                    return date_str.split()[0] if ' ' in date_str else date_str
                return None

    def get_resume_date(self, days_back: int = 1) -> Optional[str]:
        """
        Get the date from which to resume data collection.

        Args:
            days_back: Number of days to go back from the latest date

        Returns:
            Date string in YYYY-MM-DD format or None if no data
        """
        latest_date = self.get_latest_date()
        if not latest_date:
            return None

        try:
            date_obj = datetime.strptime(latest_date, '%Y-%m-%d')
            resume_date = date_obj - timedelta(days=days_back)
            return resume_date.strftime('%Y-%m-%d')
        except Exception as e:
            logger.error(f"Error parsing date: {e}")
            return None

    def update_database(self, download_pdfs: bool = False, max_retries: int = 5,
                       start_date_override: Optional[str] = None,
                       days_to_fetch: int = 1095, end_date: Optional[str] = None,
                       progress_callback: Optional[Callable[[str], None]] = None,
                       cancel_check: Optional[Callable[[], bool]] = None) -> Dict[str, int]:
        """
        Main function to update the medRxiv database.

        Args:
            download_pdfs: Whether to download PDFs for each paper
            max_retries: Maximum number of retry attempts for API requests
            start_date_override: Force a specific start date (format: YYYY-MM-DD)
            days_to_fetch: Number of days back to fetch if no items in database
            end_date: Optional end date (format: YYYY-MM-DD), defaults to today
            progress_callback: Optional callback function to report progress messages
            cancel_check: Optional callback function that returns True if operation should cancel

        Returns:
            Dictionary with statistics: {'total_processed': int, 'dates_processed': int}
        """
        # Helper to report progress to both logger and callback
        def report_progress(message: str) -> None:
            logger.info(message)
            if progress_callback:
                progress_callback(message)

        # Helper to check if operation should be cancelled
        def should_cancel() -> bool:
            return cancel_check() if cancel_check else False

        # Determine start date
        if start_date_override:
            start_date = start_date_override
        else:
            resume_date = self.get_resume_date(days_back=1)
            if resume_date:
                report_progress(f"Resuming from last imported date: {resume_date}")
                start_date = resume_date
            else:
                start_date = (datetime.now() - timedelta(days=days_to_fetch)).strftime('%Y-%m-%d')
                report_progress(f"No data in database. Starting from {days_to_fetch} days ago ({start_date})")

        # Clamp start date to medRxiv launch date (no papers exist before this)
        if start_date < self.MEDRXIV_LAUNCH_DATE:
            report_progress(f"Note: medRxiv launched {self.MEDRXIV_LAUNCH_DATE}. Clamping start date from {start_date} to {self.MEDRXIV_LAUNCH_DATE}")
            start_date = self.MEDRXIV_LAUNCH_DATE

        # Use provided end_date or default to today
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        report_progress(f"End date for fetch: {end_date}")

        # Split date range into weekly chunks
        date_ranges = self._split_date_range_into_weeks(start_date, end_date)
        report_progress(f"Splitting request into {len(date_ranges)} weekly chunks")

        # Track stats
        total_processed = 0
        dates_processed = set()

        # Process each week
        if tqdm:
            chunks_progress = tqdm(date_ranges, desc="Downloading weekly chunks", unit="week")
        else:
            chunks_progress = date_ranges

        for week_start, week_end in chunks_progress:
            # Check for cancellation
            if should_cancel():
                report_progress("Import cancelled by user")
                break

            if tqdm:
                chunks_progress.set_description(f"Downloading {week_start} to {week_end}")

            report_progress(f"Fetching medRxiv papers from {week_start} to {week_end}...")
            week_papers = self.fetch_metadata(week_start, week_end, max_retries=max_retries)

            if week_papers:
                report_progress(f"Found {len(week_papers)} papers for {week_start} to {week_end}")

                # Group papers by date
                papers_by_date = {}
                for paper in week_papers:
                    date_posted = paper.get('date', '').split()[0] if ' ' in paper.get('date', '') else paper.get('date', '')
                    if date_posted not in papers_by_date:
                        papers_by_date[date_posted] = []
                    papers_by_date[date_posted].append(paper)

                # Process papers by date
                for date_str in sorted(papers_by_date.keys()):
                    # Check for cancellation between dates
                    if should_cancel():
                        report_progress("Import cancelled by user")
                        break

                    current_papers = papers_by_date[date_str]
                    report_progress(f"Processing date {date_str} ({len(current_papers)} papers)")

                    # Process in batches for better memory management
                    batch_size = 100
                    for i in range(0, len(current_papers), batch_size):
                        batch = current_papers[i:i+batch_size]
                        processed = self._process_papers(batch, download_pdfs)
                        total_processed += processed

                    dates_processed.add(date_str)

                # Break outer loop if cancelled
                if should_cancel():
                    break
            else:
                report_progress(f"No papers found for {week_start} to {week_end}")

            # Sleep between weekly batches
            if week_end != end_date:
                time.sleep(2)

        report_progress(f"medRxiv database update complete! Processed {total_processed} papers across {len(dates_processed)} dates.")

        return {
            'total_processed': total_processed,
            'dates_processed': len(dates_processed)
        }

    def get_preprints_without_pdfs(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get medRxiv preprints without downloaded PDFs.

        Args:
            limit: Maximum number of results to return

        Returns:
            List of preprints without downloaded PDFs
        """
        query = """
            SELECT d.id, d.doi, d.title, d.publication_date, d.pdf_url
            FROM document d
            WHERE d.source_id = %s
            AND (d.pdf_filename = '' OR d.pdf_filename IS NULL)
            ORDER BY d.publication_date DESC
        """

        params = [self.source_id]

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                columns = [desc[0] for desc in cur.description]
                results = []
                for row in cur.fetchall():
                    results.append(dict(zip(columns, row)))
                return results

    def fetch_missing_pdfs(self, max_retries: int = 5, limit: Optional[int] = None,
                          convert_to_markdown: bool = True) -> int:
        """
        Fetch missing PDF files for papers in the database.

        Args:
            max_retries: Maximum number of retry attempts for failed downloads
            limit: Maximum number of PDFs to fetch (None for no limit)
            convert_to_markdown: Whether to convert PDFs to markdown text

        Returns:
            Number of successfully downloaded PDFs
        """
        records = self.get_preprints_without_pdfs(limit)

        if not records:
            logger.info("No missing PDFs found in the database.")
            return 0

        logger.info(f"Found {len(records)} papers without downloaded PDFs")

        success_count = 0

        if tqdm:
            progress = tqdm(records, desc="Downloading PDFs", unit="paper")
        else:
            progress = records

        for record in progress:
            doi = record['doi']
            pdf_url = record.get('pdf_url', '')

            if tqdm:
                progress.set_description(f"Processing {doi}")

            # Extract version from PDF URL
            version = "1"
            try:
                if pdf_url and "v" in pdf_url:
                    version = pdf_url.split("v")[-1].split(".")[0]
            except:
                pass

            paper = {
                'doi': doi,
                'title': record.get('title', ''),
                'date': record.get('publication_date', ''),
                'version': version
            }

            # Download PDF
            filename, was_downloaded = self.download_pdf(paper)

            if filename:
                full_text = ""
                if was_downloaded and convert_to_markdown:
                    full_text = self.extract_full_text(filename)

                # Update database
                try:
                    with self.db_manager.get_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE document
                                SET pdf_filename = %s, full_text = %s, updated_date = CURRENT_TIMESTAMP
                                WHERE source_id = %s AND doi = %s
                            """, (filename, full_text, self.source_id, doi))

                    success_count += 1
                    logger.debug(f"Updated PDF path for {doi}")
                except Exception as e:
                    logger.error(f"Error updating PDF path for {doi}: {e}")

        logger.info(f"Downloaded {success_count} missing PDFs")
        return success_count
