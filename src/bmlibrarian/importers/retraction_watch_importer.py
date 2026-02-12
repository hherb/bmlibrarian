"""
Retraction Watch Database Importer

Imports retraction data from the Retraction Watch database CSV for offline
transparency analysis. Updates retraction status in both the
transparency.document_metadata table and doi_metadata.is_retracted.

The Retraction Watch database is available as a CSV (~50MB) free for research
use via CrossRef or by request from retractionwatch.com.

Expected CSV columns (flexible - adapts to available columns):
    - Record ID, Title, DOI, PubMedID (PMID)
    - RetractionDate, RetractionNature (retraction/correction/expression of concern)
    - Reason(s), Subject(s), Institution, Journal, Country, Author

Usage:
    from bmlibrarian.importers.retraction_watch_importer import RetractionWatchImporter

    importer = RetractionWatchImporter()
    stats = importer.import_csv(Path('retraction_watch.csv'))
    print(f"Matched {stats['matched']} retractions to documents")
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# Column name variations in Retraction Watch CSV exports
DOI_COLUMNS = ("DOI", "doi", "OriginalPaperDOI", "Original Paper DOI")
PMID_COLUMNS = ("PubMedID", "PMID", "pmid", "PubMed ID", "OriginalPaperPMID")
REASON_COLUMNS = ("Reason", "Reasons", "Reason(s)", "RetractionReason")
DATE_COLUMNS = ("RetractionDate", "Retraction Date", "retraction_date", "Date")
NATURE_COLUMNS = ("RetractionNature", "Nature", "Type", "retraction_nature")
TITLE_COLUMNS = ("Title", "title", "OriginalPaperTitle", "Original Paper Title")


def _find_column(row: Dict[str, str], candidates: tuple) -> Optional[str]:
    """Find the first matching column name from a list of candidates.

    Args:
        row: CSV row as dictionary.
        candidates: Tuple of possible column names.

    Returns:
        The value from the first matching column, or None.
    """
    for col in candidates:
        if col in row and row[col]:
            return row[col].strip()
    return None


class RetractionWatchImporter:
    """Import retraction data from Retraction Watch CSV files.

    Matches retracted papers to existing documents in the database by
    DOI or PMID, and updates retraction status in the transparency schema.
    """

    def import_csv(
        self,
        csv_path: Path,
        limit: int = 0,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, int]:
        """Import retraction data from a CSV file.

        Args:
            csv_path: Path to the Retraction Watch CSV file.
            limit: Maximum number of records to process (0 = unlimited).
            progress_callback: Optional callback for progress messages.

        Returns:
            Dictionary with import statistics.

        Raises:
            FileNotFoundError: If CSV file does not exist.
            RuntimeError: If transparency schema is not available.
        """
        from bmlibrarian.database import get_db_manager

        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        db_manager = get_db_manager()
        stats = {
            "total_rows": 0,
            "matched_by_doi": 0,
            "matched_by_pmid": 0,
            "unmatched": 0,
            "errors": 0,
        }

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Check schema exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'transparency'
                        AND table_name = 'document_metadata'
                    )
                """)
                if not cur.fetchone()[0]:
                    raise RuntimeError(
                        "transparency.document_metadata table not found. "
                        "Run migration 029_create_transparency_schema.sql first."
                    )

            # Detect encoding and read CSV
            encodings_to_try = ("utf-8", "utf-8-sig", "latin-1", "cp1252")
            rows: List[Dict[str, str]] = []

            for encoding in encodings_to_try:
                try:
                    with open(csv_path, "r", encoding=encoding) as f:
                        reader = csv.DictReader(f)
                        for i, row in enumerate(reader):
                            if limit > 0 and i >= limit:
                                break
                            rows.append(row)
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue

            if not rows:
                logger.warning(f"No rows read from {csv_path}")
                return stats

            if progress_callback:
                progress_callback(f"Processing {len(rows)} retraction records...")

            with conn.cursor() as cur:
                for i, row in enumerate(rows):
                    stats["total_rows"] += 1

                    doi = _find_column(row, DOI_COLUMNS)
                    pmid = _find_column(row, PMID_COLUMNS)
                    reason = _find_column(row, REASON_COLUMNS)
                    date_str = _find_column(row, DATE_COLUMNS)
                    title = _find_column(row, TITLE_COLUMNS)

                    # Parse date
                    retraction_date = None
                    if date_str:
                        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
                            try:
                                retraction_date = datetime.strptime(date_str, fmt).date()
                                break
                            except ValueError:
                                continue

                    # Try to match by DOI first, then PMID
                    document_id = None
                    match_method = None

                    if doi:
                        try:
                            cur.execute(
                                "SELECT id FROM public.document WHERE doi = %s LIMIT 1",
                                (doi,),
                            )
                            result = cur.fetchone()
                            if result:
                                document_id = result[0]
                                match_method = "doi"
                        except Exception:
                            pass

                    if document_id is None and pmid:
                        try:
                            cur.execute(
                                "SELECT id FROM public.document WHERE external_id = %s LIMIT 1",
                                (pmid,),
                            )
                            result = cur.fetchone()
                            if result:
                                document_id = result[0]
                                match_method = "pmid"
                        except Exception:
                            pass

                    if document_id is None:
                        stats["unmatched"] += 1
                        continue

                    try:
                        # Update transparency.document_metadata
                        cur.execute(
                            """
                            INSERT INTO transparency.document_metadata (
                                document_id, is_retracted, retraction_reason,
                                retraction_date, retraction_source, source
                            ) VALUES (%s, TRUE, %s, %s, 'retraction_watch', 'retraction_watch')
                            ON CONFLICT (document_id) DO UPDATE SET
                                is_retracted = TRUE,
                                retraction_reason = COALESCE(
                                    EXCLUDED.retraction_reason,
                                    transparency.document_metadata.retraction_reason
                                ),
                                retraction_date = COALESCE(
                                    EXCLUDED.retraction_date,
                                    transparency.document_metadata.retraction_date
                                ),
                                retraction_source = 'retraction_watch',
                                imported_at = NOW()
                            """,
                            (document_id, reason, retraction_date),
                        )

                        # Also update doi_metadata.is_retracted for consistency
                        if doi:
                            cur.execute(
                                """
                                UPDATE public.doi_metadata
                                SET is_retracted = TRUE
                                WHERE doi = %s
                                """,
                                (doi,),
                            )

                        if match_method == "doi":
                            stats["matched_by_doi"] += 1
                        else:
                            stats["matched_by_pmid"] += 1

                    except Exception as e:
                        stats["errors"] += 1
                        logger.debug(f"Error storing retraction for DOI {doi}: {e}")

                    if progress_callback and (i + 1) % 1000 == 0:
                        matched = stats["matched_by_doi"] + stats["matched_by_pmid"]
                        progress_callback(
                            f"Processed {i + 1}/{len(rows)} records "
                            f"(matched: {matched})"
                        )

                conn.commit()

        matched = stats["matched_by_doi"] + stats["matched_by_pmid"]
        if progress_callback:
            progress_callback(
                f"Import complete: {stats['total_rows']} records, "
                f"{matched} matched ({stats['matched_by_doi']} by DOI, "
                f"{stats['matched_by_pmid']} by PMID), "
                f"{stats['unmatched']} unmatched"
            )

        return stats

    def lookup(
        self,
        doi: Optional[str] = None,
        pmid: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Look up retraction status for a document.

        Args:
            doi: DOI to look up.
            pmid: PMID to look up.

        Returns:
            Dictionary with retraction info, or None if not found.
        """
        from bmlibrarian.database import get_db_manager

        db_manager = get_db_manager()

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                if doi:
                    cur.execute(
                        """
                        SELECT m.is_retracted, m.retraction_reason, m.retraction_date,
                               d.title, d.doi
                        FROM transparency.document_metadata m
                        JOIN public.document d ON d.id = m.document_id
                        WHERE d.doi = %s AND m.is_retracted = TRUE
                        """,
                        (doi,),
                    )
                elif pmid:
                    cur.execute(
                        """
                        SELECT m.is_retracted, m.retraction_reason, m.retraction_date,
                               d.title, d.doi
                        FROM transparency.document_metadata m
                        JOIN public.document d ON d.id = m.document_id
                        WHERE d.external_id = %s AND m.is_retracted = TRUE
                        """,
                        (pmid,),
                    )
                else:
                    return None

                row = cur.fetchone()
                if not row:
                    return None

                return {
                    "is_retracted": row[0],
                    "retraction_reason": row[1],
                    "retraction_date": str(row[2]) if row[2] else None,
                    "title": row[3],
                    "doi": row[4],
                }

    def get_status(self) -> Dict[str, Any]:
        """Get retraction import status and statistics.

        Returns:
            Dictionary with retraction import status.
        """
        try:
            from bmlibrarian.database import get_db_manager
            db_manager = get_db_manager()

            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COUNT(*) FROM transparency.document_metadata
                        WHERE retraction_source = 'retraction_watch'
                    """)
                    rw_count = cur.fetchone()[0]

                    cur.execute("""
                        SELECT COUNT(*) FROM transparency.document_metadata
                        WHERE is_retracted = TRUE
                    """)
                    total_retracted = cur.fetchone()[0]

                    return {
                        "retraction_watch_records": rw_count,
                        "total_retracted_documents": total_retracted,
                    }
        except Exception as e:
            return {"error": str(e)}
