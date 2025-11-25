"""PDF Download Logging Module.

Provides functions to log PDF download history to the database,
enabling audit trails and debugging of incorrect PDF matches.

Requires migration 019_create_pdf_download_history.sql to be applied.
"""

import logging
from typing import Optional, Dict, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    import psycopg

from .data_types import DownloadResult, PDFSource

logger = logging.getLogger(__name__)


def log_download_to_database(
    conn: "psycopg.Connection",
    document_id: int,
    result: DownloadResult,
    source: Optional[PDFSource] = None
) -> Optional[int]:
    """Log a PDF download to the database.

    Uses the log_pdf_download function created by migration 019.

    Args:
        conn: Database connection (psycopg connection)
        document_id: ID of the document
        result: DownloadResult from the download
        source: Optional PDFSource (uses result.source if not provided)

    Returns:
        History record ID if logged, None on error
    """
    source = source or result.source

    if source is None:
        source_type = 'unknown'
        source_url = None
        access_type = None
    else:
        source_type = source.source_type.value
        source_url = source.url
        access_type = source.access_type.value if source.access_type else None

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT log_pdf_download(
                    %s,  -- p_document_id
                    %s,  -- p_source_type
                    %s,  -- p_source_url
                    %s,  -- p_access_type
                    %s,  -- p_pdf_filename
                    %s,  -- p_pdf_file_path
                    %s,  -- p_file_size_bytes
                    %s,  -- p_verified
                    %s,  -- p_verification_confidence
                    %s,  -- p_verification_match_type
                    %s,  -- p_extracted_doi
                    %s,  -- p_extracted_pmid
                    %s,  -- p_extracted_title
                    %s   -- p_notes
                )
            """, (
                document_id,
                source_type,
                source_url,
                access_type,
                result.file_path.split('/')[-1] if result.file_path else None,
                result.file_path,
                result.file_size if result.file_size else None,
                result.verified,
                result.verification_confidence,
                result.verification_match_type,
                None,  # extracted_doi - would need to get from verifier
                None,  # extracted_pmid
                None,  # extracted_title
                "; ".join(result.verification_warnings) if result.verification_warnings else None
            ))

            history_id = cur.fetchone()[0]
            conn.commit()

            logger.debug(f"Logged download for document {document_id}, history_id={history_id}")
            return history_id

    except Exception as e:
        logger.warning(f"Failed to log download history (migration may not be applied): {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return None


def log_download_with_verification(
    conn: "psycopg.Connection",
    document_id: int,
    result: DownloadResult,
    verification_result: Optional[Dict[str, Any]] = None
) -> Optional[int]:
    """Log a PDF download with detailed verification results.

    Args:
        conn: Database connection
        document_id: ID of the document
        result: DownloadResult from the download
        verification_result: Optional dict with verification details:
            - extracted_doi: DOI found in PDF
            - extracted_pmid: PMID found in PDF
            - extracted_title: Title found in PDF

    Returns:
        History record ID if logged, None on error
    """
    source = result.source

    if source is None:
        source_type = 'unknown'
        source_url = None
        access_type = None
    else:
        source_type = source.source_type.value
        source_url = source.url
        access_type = source.access_type.value if source.access_type else None

    # Extract verification details
    extracted_doi = None
    extracted_pmid = None
    extracted_title = None
    if verification_result:
        extracted_doi = verification_result.get('extracted_doi')
        extracted_pmid = verification_result.get('extracted_pmid')
        extracted_title = verification_result.get('extracted_title')

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT log_pdf_download(
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                document_id,
                source_type,
                source_url,
                access_type,
                result.file_path.split('/')[-1] if result.file_path else None,
                result.file_path,
                result.file_size if result.file_size else None,
                result.verified,
                result.verification_confidence,
                result.verification_match_type,
                extracted_doi,
                extracted_pmid,
                extracted_title,  # Full title preserved - database column is TEXT type
                "; ".join(result.verification_warnings) if result.verification_warnings else None
            ))

            history_id = cur.fetchone()[0]
            conn.commit()

            logger.debug(f"Logged download with verification for document {document_id}")
            return history_id

    except Exception as e:
        logger.warning(f"Failed to log download history: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return None


def get_download_history(
    conn: "psycopg.Connection",
    document_id: int,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Get download history for a document.

    Args:
        conn: Database connection
        document_id: ID of the document
        limit: Maximum number of records to return

    Returns:
        List of download history records
    """
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id, document_id, downloaded_at, source_type, source_url,
                    access_type, pdf_filename, pdf_file_path, file_size_bytes,
                    verified, verification_confidence, verification_match_type,
                    extracted_doi, extracted_pmid, extracted_title,
                    status, notes
                FROM pdf_download_history
                WHERE document_id = %s
                ORDER BY downloaded_at DESC
                LIMIT %s
            """, (document_id, limit))

            rows = cur.fetchall()
            columns = [
                'id', 'document_id', 'downloaded_at', 'source_type', 'source_url',
                'access_type', 'pdf_filename', 'pdf_file_path', 'file_size_bytes',
                'verified', 'verification_confidence', 'verification_match_type',
                'extracted_doi', 'extracted_pmid', 'extracted_title',
                'status', 'notes'
            ]

            return [dict(zip(columns, row)) for row in rows]

    except Exception as e:
        logger.warning(f"Failed to get download history: {e}")
        return []


def get_mismatched_downloads(
    conn: "psycopg.Connection",
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get documents with mismatched PDF downloads.

    Args:
        conn: Database connection
        limit: Maximum number of records to return

    Returns:
        List of document records with mismatches
    """
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    document_id, pdf_status, last_download_source,
                    verification_match_type, open_issues,
                    doi, title
                FROM v_document_pdf_status
                WHERE pdf_status = 'MISMATCH'
                ORDER BY document_id DESC
                LIMIT %s
            """, (limit,))

            rows = cur.fetchall()
            columns = [
                'document_id', 'pdf_status', 'last_download_source',
                'verification_match_type', 'open_issues', 'doi', 'title'
            ]

            return [dict(zip(columns, row)) for row in rows]

    except Exception as e:
        logger.warning(f"Failed to get mismatched downloads: {e}")
        return []


def check_migration_applied(conn: "psycopg.Connection") -> bool:
    """Check if the download history migration has been applied.

    Args:
        conn: Database connection

    Returns:
        True if pdf_download_history table exists
    """
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'pdf_download_history'
                )
            """)
            return cur.fetchone()[0]
    except Exception:
        return False
