"""
ClinicalTrials.gov Bulk Importer

Downloads and imports clinical trial metadata from ClinicalTrials.gov bulk
data for offline transparency analysis. Extracts sponsor classification
(NIH/Industry/Other/FedGov), trial status, and NCT IDs, then matches
against existing documents in the database.

The bulk data is available at:
    https://clinicaltrials.gov/AllPublicXML.zip (~10GB)

Usage:
    from bmlibrarian.importers.clinicaltrials_importer import ClinicalTrialsBulkImporter

    importer = ClinicalTrialsBulkImporter(data_dir=Path('~/clinicaltrials'))
    importer.download()
    stats = importer.import_trials()
    importer.match_to_documents(limit=1000)
"""

import json
import logging
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

BULK_DOWNLOAD_URL = "https://clinicaltrials.gov/AllPublicXML.zip"
DEFAULT_DATA_DIR = "~/clinicaltrials"

# NCT pattern for matching in document text
NCT_PATTERN = re.compile(r'NCT\d{8}')


@dataclass
class ClinicalTrial:
    """Parsed clinical trial metadata from ClinicalTrials.gov XML."""

    nct_id: str
    brief_title: str
    official_title: Optional[str] = None
    lead_sponsor_name: Optional[str] = None
    lead_sponsor_class: Optional[str] = None  # NIH, Industry, Other, FedGov
    collaborator_names: List[str] = field(default_factory=list)
    overall_status: Optional[str] = None  # Completed, Recruiting, etc.
    has_results: bool = False


class ClinicalTrialsBulkImporter:
    """Import clinical trial metadata from ClinicalTrials.gov bulk data.

    Downloads the AllPublicXML.zip file, parses trial metadata, and
    stores sponsor classification and trial IDs in the
    transparency.document_metadata table for offline transparency analysis.
    """

    def __init__(
        self,
        data_dir: Optional[Path] = None,
    ):
        """Initialize the ClinicalTrials.gov bulk importer.

        Args:
            data_dir: Directory for downloaded data. Defaults to ~/clinicaltrials.
        """
        if data_dir is None:
            data_dir = Path(DEFAULT_DATA_DIR).expanduser()
        self.data_dir = Path(data_dir).expanduser()
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def download(
        self,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Path:
        """Download the ClinicalTrials.gov bulk data ZIP.

        Uses requests with streaming to handle the large file (~10GB)
        with resumable downloads.

        Args:
            progress_callback: Optional callback for progress messages.

        Returns:
            Path to the downloaded ZIP file.

        Raises:
            ImportError: If requests library is not installed.
            RuntimeError: If download fails.
        """
        try:
            import requests
        except ImportError:
            raise ImportError(
                "requests library required for download. Install with: uv add requests"
            )

        zip_path = self.data_dir / "AllPublicXML.zip"

        if progress_callback:
            progress_callback(f"Downloading ClinicalTrials.gov bulk data to {zip_path}")

        # Support resume by checking existing file size
        headers: Dict[str, str] = {}
        existing_size = 0
        if zip_path.exists():
            existing_size = zip_path.stat().st_size
            headers["Range"] = f"bytes={existing_size}-"
            if progress_callback:
                progress_callback(f"Resuming download from {existing_size / (1024**3):.1f} GB")

        response = requests.get(BULK_DOWNLOAD_URL, headers=headers, stream=True, timeout=60)
        if response.status_code == 416:
            # Range not satisfiable = file already complete
            if progress_callback:
                progress_callback("Download already complete")
            return zip_path

        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0)) + existing_size
        downloaded = existing_size

        mode = "ab" if existing_size > 0 else "wb"
        chunk_size = 8 * 1024 * 1024  # 8MB chunks

        with open(zip_path, mode) as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        pct = downloaded / total_size * 100
                        progress_callback(
                            f"Downloaded {downloaded / (1024**3):.1f} / "
                            f"{total_size / (1024**3):.1f} GB ({pct:.0f}%)"
                        )

        if progress_callback:
            progress_callback(f"Download complete: {zip_path}")

        return zip_path

    def parse_trial_xml(self, xml_content: str) -> Optional[ClinicalTrial]:
        """Parse a single clinical trial XML file.

        Args:
            xml_content: XML content string.

        Returns:
            ClinicalTrial object or None if parsing fails.
        """
        try:
            root = ET.fromstring(xml_content)

            nct_id = root.findtext('.//id_info/nct_id')
            if not nct_id:
                return None

            brief_title = root.findtext('.//brief_title', '')
            official_title = root.findtext('.//official_title')

            # Sponsor info
            lead_sponsor = root.find('.//sponsors/lead_sponsor')
            lead_name = None
            lead_class = None
            if lead_sponsor is not None:
                lead_name = lead_sponsor.findtext('agency')
                lead_class = lead_sponsor.findtext('agency_class')

            # Collaborators
            collaborators = []
            for collab in root.findall('.//sponsors/collaborator'):
                name = collab.findtext('agency')
                if name:
                    collaborators.append(name)

            # Status
            status = root.findtext('.//overall_status')

            # Check if results have been posted
            has_results = root.find('.//clinical_results') is not None

            return ClinicalTrial(
                nct_id=nct_id,
                brief_title=brief_title,
                official_title=official_title,
                lead_sponsor_name=lead_name,
                lead_sponsor_class=lead_class,
                collaborator_names=collaborators,
                overall_status=status,
                has_results=has_results,
            )

        except ET.ParseError as e:
            logger.debug(f"XML parse error: {e}")
            return None

    def import_trials(
        self,
        zip_path: Optional[Path] = None,
        limit: int = 0,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, int]:
        """Import clinical trial metadata from the downloaded ZIP.

        Streams through the ZIP file, parsing each trial XML and storing
        the metadata in the transparency.document_metadata table.

        Args:
            zip_path: Path to ZIP file. Defaults to data_dir/AllPublicXML.zip.
            limit: Maximum number of trials to import (0 = unlimited).
            progress_callback: Optional callback for progress messages.

        Returns:
            Dictionary with import statistics.
        """
        from bmlibrarian.database import get_db_manager

        if zip_path is None:
            zip_path = self.data_dir / "AllPublicXML.zip"

        if not zip_path.exists():
            raise FileNotFoundError(f"ZIP file not found: {zip_path}")

        db_manager = get_db_manager()
        stats = {"parsed": 0, "stored": 0, "errors": 0, "skipped": 0}

        with zipfile.ZipFile(zip_path, 'r') as zf:
            xml_files = [n for n in zf.namelist() if n.endswith('.xml')]
            total = min(len(xml_files), limit) if limit > 0 else len(xml_files)

            if progress_callback:
                progress_callback(f"Processing {total} trial XML files...")

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

                    for i, xml_name in enumerate(xml_files):
                        if limit > 0 and i >= limit:
                            break

                        try:
                            with zf.open(xml_name) as xml_file:
                                content = xml_file.read().decode('utf-8')

                            trial = self.parse_trial_xml(content)
                            if trial is None:
                                stats["skipped"] += 1
                                continue

                            stats["parsed"] += 1

                            # Store in transparency.document_metadata
                            # We don't know the document_id yet - that's done in match step
                            # For now, store in a staging approach via the nct_id column
                            cur.execute(
                                """
                                INSERT INTO transparency.document_metadata (
                                    document_id, clinical_trial_id, trial_sponsor,
                                    trial_sponsor_class, trial_status, source
                                )
                                SELECT d.id, %s, %s, %s, %s, 'clinicaltrials_bulk'
                                FROM public.document d
                                WHERE d.full_text LIKE %s
                                   OR d.abstract LIKE %s
                                LIMIT 1
                                ON CONFLICT (document_id) DO UPDATE SET
                                    clinical_trial_id = EXCLUDED.clinical_trial_id,
                                    trial_sponsor = EXCLUDED.trial_sponsor,
                                    trial_sponsor_class = EXCLUDED.trial_sponsor_class,
                                    trial_status = EXCLUDED.trial_status,
                                    imported_at = NOW()
                                """,
                                (
                                    trial.nct_id,
                                    trial.lead_sponsor_name,
                                    trial.lead_sponsor_class,
                                    trial.overall_status,
                                    f'%{trial.nct_id}%',
                                    f'%{trial.nct_id}%',
                                ),
                            )
                            if cur.rowcount > 0:
                                stats["stored"] += 1

                        except Exception as e:
                            stats["errors"] += 1
                            logger.debug(f"Error processing {xml_name}: {e}")

                        if progress_callback and (i + 1) % 10000 == 0:
                            progress_callback(
                                f"Processed {i + 1}/{total} trials "
                                f"(stored: {stats['stored']})"
                            )

                    conn.commit()

        if progress_callback:
            progress_callback(
                f"Import complete: {stats['parsed']} parsed, "
                f"{stats['stored']} matched to documents, "
                f"{stats['errors']} errors"
            )

        return stats

    def get_status(self) -> Dict[str, Any]:
        """Get import status and statistics.

        Returns:
            Dictionary with download and import status.
        """
        zip_path = self.data_dir / "AllPublicXML.zip"

        status: Dict[str, Any] = {
            "data_dir": str(self.data_dir),
            "zip_exists": zip_path.exists(),
            "zip_size_gb": zip_path.stat().st_size / (1024**3) if zip_path.exists() else 0,
        }

        try:
            from bmlibrarian.database import get_db_manager
            db_manager = get_db_manager()
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COUNT(*) FROM transparency.document_metadata
                        WHERE source = 'clinicaltrials_bulk'
                    """)
                    status["matched_documents"] = cur.fetchone()[0]

                    cur.execute("""
                        SELECT trial_sponsor_class, COUNT(*)
                        FROM transparency.document_metadata
                        WHERE trial_sponsor_class IS NOT NULL
                        GROUP BY trial_sponsor_class
                    """)
                    status["sponsor_distribution"] = dict(cur.fetchall())
        except Exception as e:
            status["db_error"] = str(e)

        return status
