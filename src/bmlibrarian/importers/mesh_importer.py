"""
MeSH (Medical Subject Headings) Importer.

Downloads and imports the MeSH vocabulary from NLM into the local PostgreSQL database.
Supports full descriptors, supplementary concept records (SCRs), and qualifiers.

Example usage:
    from bmlibrarian.importers import MeSHImporter

    importer = MeSHImporter()

    # Download and import full MeSH
    stats = importer.import_mesh(year=2025)
    print(f"Imported {stats.descriptors} descriptors")

    # Import supplementary concepts only
    stats = importer.import_supplementary_concepts(year=2025)
"""

import gzip
import logging
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterator, Callable, IO
from urllib.parse import urljoin
import requests

from bmlibrarian.database import get_db_manager

logger = logging.getLogger(__name__)


# NLM FTP/HTTPS URLs for MeSH data
# Note: MESH_FILES/xmlmesh/ contains the actual XML files, not {year}/xmlmesh/
MESH_BASE_URL = "https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/"
MESH_FTP_URL = "ftp://nlmpubs.nlm.nih.gov/online/mesh/"

# File names - download XML directly (server auto-decompresses .gz files)
DESCRIPTOR_FILE = "desc{year}.xml"
QUALIFIER_FILE = "qual{year}.xml"
SUPPLEMENTARY_FILE = "supp{year}.xml"

# Default download directory
DEFAULT_DOWNLOAD_DIR = Path.home() / ".bmlibrarian" / "downloads" / "mesh"

# Batch sizes for database operations
DESCRIPTOR_BATCH_SIZE = 100
TERM_BATCH_SIZE = 1000
SCR_BATCH_SIZE = 500

# Request settings
REQUEST_TIMEOUT_SECONDS = 60
REQUEST_CHUNK_SIZE = 8192
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


@dataclass
class MeSHDescriptor:
    """Parsed MeSH descriptor record."""

    descriptor_ui: str
    descriptor_name: str
    scope_note: Optional[str] = None
    annotation: Optional[str] = None
    history_note: Optional[str] = None
    public_mesh_note: Optional[str] = None
    nlm_classification: Optional[str] = None
    date_created: Optional[str] = None
    date_revised: Optional[str] = None
    date_established: Optional[str] = None
    concepts: List[Dict[str, Any]] = field(default_factory=list)
    tree_numbers: List[str] = field(default_factory=list)
    allowable_qualifiers: List[str] = field(default_factory=list)


@dataclass
class MeSHQualifier:
    """Parsed MeSH qualifier record."""

    qualifier_ui: str
    qualifier_name: str
    abbreviation: str
    scope_note: Optional[str] = None
    annotation: Optional[str] = None


@dataclass
class MeSHSupplementary:
    """Parsed MeSH supplementary concept record."""

    supplemental_ui: str
    supplemental_name: str
    note: Optional[str] = None
    cas_registry_number: Optional[str] = None
    frequency: Optional[int] = None
    heading_mapped_to: List[str] = field(default_factory=list)
    indexing_information: Optional[str] = None


@dataclass
class ImportStats:
    """Statistics from a MeSH import operation."""

    mesh_year: int
    import_type: str
    descriptors: int = 0
    concepts: int = 0
    terms: int = 0
    tree_numbers: int = 0
    qualifiers: int = 0
    supplementary_concepts: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    status: str = "in_progress"
    error_message: Optional[str] = None

    def mark_completed(self) -> None:
        """Mark import as completed and calculate duration."""
        self.completed_at = datetime.now()
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        self.status = "completed"

    def mark_failed(self, error: str) -> None:
        """Mark import as failed with error message."""
        self.completed_at = datetime.now()
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        self.status = "failed"
        self.error_message = error


class MeSHImporter:
    """
    Importer for MeSH (Medical Subject Headings) vocabulary.

    Downloads MeSH XML files from NLM and imports them into the mesh schema.
    Supports descriptors, qualifiers, and supplementary concept records.
    """

    def __init__(
        self,
        download_dir: Optional[Path] = None,
        keep_downloads: bool = True,
    ) -> None:
        """
        Initialize MeSH importer.

        Args:
            download_dir: Directory for downloaded files (default: ~/.bmlibrarian/downloads/mesh)
            keep_downloads: Whether to keep downloaded files after import
        """
        self.db_manager = get_db_manager()
        self.download_dir = download_dir or DEFAULT_DOWNLOAD_DIR
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.keep_downloads = keep_downloads

        logger.info(f"MeSH importer initialized, download dir: {self.download_dir}")

    def _download_file(
        self,
        url: str,
        output_path: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> bool:
        """
        Download a file with progress tracking.

        Args:
            url: URL to download
            output_path: Local path to save file
            progress_callback: Optional callback(downloaded_bytes, total_bytes)

        Returns:
            True if download succeeded
        """
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Downloading {url} (attempt {attempt + 1}/{MAX_RETRIES})")

                response = requests.get(
                    url,
                    stream=True,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    headers={"User-Agent": "BMLibrarian/1.0"},
                )
                response.raise_for_status()

                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0

                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=REQUEST_CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback:
                                progress_callback(downloaded, total_size)

                logger.info(f"Downloaded {output_path.name} ({downloaded:,} bytes)")
                return True

            except requests.exceptions.RequestException as e:
                logger.warning(f"Download failed: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS)
                else:
                    logger.error(f"Download failed after {MAX_RETRIES} attempts")
                    return False

        return False

    def _get_download_url(self, year: int, file_type: str) -> str:
        """
        Get download URL for a MeSH file.

        NLM stores MeSH XML files at:
        https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/

        Files are named desc{year}.gz, qual{year}.gz, supp{year}.gz

        Args:
            year: MeSH year (e.g., 2025)
            file_type: 'descriptor', 'qualifier', or 'supplementary'

        Returns:
            Full URL for downloading
        """
        if file_type == "descriptor":
            filename = DESCRIPTOR_FILE.format(year=year)
        elif file_type == "qualifier":
            filename = QUALIFIER_FILE.format(year=year)
        elif file_type == "supplementary":
            filename = SUPPLEMENTARY_FILE.format(year=year)
        else:
            raise ValueError(f"Unknown file type: {file_type}")

        # Download XML files directly (server auto-decompresses .gz files anyway)
        return urljoin(MESH_BASE_URL, filename)

    def download_mesh_files(
        self,
        year: int,
        include_supplementary: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Dict[str, Path]:
        """
        Download MeSH XML files for a given year.

        Args:
            year: MeSH year to download
            include_supplementary: Whether to download supplementary concepts
            progress_callback: Optional callback(file_type, downloaded, total)

        Returns:
            Dictionary mapping file type to local path
        """
        downloaded_files = {}

        # Download descriptors
        desc_url = self._get_download_url(year, "descriptor")
        desc_path = self.download_dir / f"desc{year}.xml"
        if self._download_file(
            desc_url,
            desc_path,
            lambda d, t: progress_callback("descriptor", d, t) if progress_callback else None,
        ):
            downloaded_files["descriptor"] = desc_path

        # Download qualifiers
        qual_url = self._get_download_url(year, "qualifier")
        qual_path = self.download_dir / f"qual{year}.xml"
        if self._download_file(
            qual_url,
            qual_path,
            lambda d, t: progress_callback("qualifier", d, t) if progress_callback else None,
        ):
            downloaded_files["qualifier"] = qual_path

        # Download supplementary concepts
        if include_supplementary:
            supp_url = self._get_download_url(year, "supplementary")
            supp_path = self.download_dir / f"supp{year}.xml"
            if self._download_file(
                supp_url,
                supp_path,
                lambda d, t: progress_callback("supplementary", d, t) if progress_callback else None,
            ):
                downloaded_files["supplementary"] = supp_path

        return downloaded_files

    def _parse_descriptor(self, elem: ET.Element) -> MeSHDescriptor:
        """
        Parse a DescriptorRecord XML element.

        Args:
            elem: XML element for DescriptorRecord

        Returns:
            Parsed MeSHDescriptor
        """
        descriptor = MeSHDescriptor(
            descriptor_ui=self._get_text(elem, "DescriptorUI") or "",
            descriptor_name=self._get_text(elem, "DescriptorName/String") or "",
        )

        # Parse optional fields
        descriptor.scope_note = self._get_text(elem, ".//ScopeNote")
        descriptor.annotation = self._get_text(elem, "Annotation")
        descriptor.history_note = self._get_text(elem, "HistoryNote")
        descriptor.public_mesh_note = self._get_text(elem, "PublicMeSHNote")
        descriptor.nlm_classification = self._get_text(elem, "NLMClassificationNumber")
        descriptor.date_created = self._get_text(elem, "DateCreated/Year")
        descriptor.date_revised = self._get_text(elem, "DateRevised/Year")
        descriptor.date_established = self._get_text(elem, "DateEstablished/Year")

        # Parse tree numbers
        for tree_elem in elem.findall(".//TreeNumber"):
            if tree_elem.text:
                descriptor.tree_numbers.append(tree_elem.text)

        # Parse concepts and terms
        for concept_elem in elem.findall(".//Concept"):
            concept = self._parse_concept(concept_elem)
            descriptor.concepts.append(concept)

        # Parse allowable qualifiers
        for qual_elem in elem.findall(".//AllowableQualifier/QualifierReferredTo/QualifierUI"):
            if qual_elem.text:
                descriptor.allowable_qualifiers.append(qual_elem.text)

        return descriptor

    def _parse_concept(self, elem: ET.Element) -> Dict[str, Any]:
        """
        Parse a Concept XML element.

        Args:
            elem: XML element for Concept

        Returns:
            Dictionary with concept data
        """
        concept = {
            "concept_ui": self._get_text(elem, "ConceptUI") or "",
            "concept_name": self._get_text(elem, "ConceptName/String") or "",
            "is_preferred": elem.get("PreferredConceptYN") == "Y",
            "scope_note": self._get_text(elem, "ScopeNote"),
            "cas_registry_number": self._get_text(elem, "CASN1Name"),
            "terms": [],
        }

        # Parse terms
        for term_elem in elem.findall(".//Term"):
            term = {
                "term_ui": self._get_text(term_elem, "TermUI") or "",
                "term_text": self._get_text(term_elem, "String") or "",
                "is_preferred": term_elem.get("ConceptPreferredTermYN") == "Y",
                "is_permuted": term_elem.get("IsPermutedTermYN") == "Y",
                "lexical_tag": term_elem.get("LexicalTag"),
                "entry_combination": self._get_text(term_elem, "EntryVersion"),
                "sort_version": self._get_text(term_elem, "SortVersion"),
            }
            concept["terms"].append(term)

        return concept

    def _parse_qualifier(self, elem: ET.Element) -> MeSHQualifier:
        """
        Parse a QualifierRecord XML element.

        Args:
            elem: XML element for QualifierRecord

        Returns:
            Parsed MeSHQualifier
        """
        return MeSHQualifier(
            qualifier_ui=self._get_text(elem, "QualifierUI") or "",
            qualifier_name=self._get_text(elem, "QualifierName/String") or "",
            abbreviation=self._get_text(elem, "Abbreviation") or "",
            scope_note=self._get_text(elem, ".//ScopeNote"),
            annotation=self._get_text(elem, "Annotation"),
        )

    def _parse_supplementary(self, elem: ET.Element) -> MeSHSupplementary:
        """
        Parse a SupplementalRecord XML element.

        Args:
            elem: XML element for SupplementalRecord

        Returns:
            Parsed MeSHSupplementary
        """
        scr = MeSHSupplementary(
            supplemental_ui=self._get_text(elem, "SupplementalRecordUI") or "",
            supplemental_name=self._get_text(elem, "SupplementalRecordName/String") or "",
        )

        scr.note = self._get_text(elem, "Note")
        scr.indexing_information = self._get_text(elem, "IndexingInformation")

        # Parse frequency
        freq_text = self._get_text(elem, "Frequency")
        if freq_text:
            try:
                scr.frequency = int(freq_text)
            except ValueError:
                pass

        # Parse mapped headings
        for mapping in elem.findall(".//HeadingMappedTo/DescriptorReferredTo/DescriptorUI"):
            if mapping.text:
                scr.heading_mapped_to.append(mapping.text)

        # Parse CAS number from concepts
        cas = self._get_text(elem, ".//CASN1Name")
        if cas:
            scr.cas_registry_number = cas

        return scr

    def _get_text(self, elem: ET.Element, path: str) -> Optional[str]:
        """
        Get text content from an XML element by path.

        Args:
            elem: Parent XML element
            path: XPath to child element

        Returns:
            Text content or None
        """
        child = elem.find(path)
        if child is not None and child.text:
            return child.text.strip()
        return None

    @contextmanager
    def _open_xml_file(self, file_path: Path) -> Iterator[IO[bytes]]:
        """
        Open an XML file (gzipped or plain) using context manager.

        Args:
            file_path: Path to XML or XML.gz file

        Yields:
            File handle for reading
        """
        if file_path.suffix == ".gz":
            with gzip.open(file_path, "rb") as f:
                yield f
        else:
            with open(file_path, "rb") as f:
                yield f

    def _iter_xml_records(
        self,
        file_path: Path,
        record_tag: str,
    ) -> Iterator[ET.Element]:
        """
        Iterate over XML records in a (possibly gzipped) file.

        Uses iterparse for memory-efficient streaming with proper resource
        management via context managers.

        Args:
            file_path: Path to XML or XML.gz file
            record_tag: XML tag name for records

        Yields:
            XML elements for each record
        """
        with self._open_xml_file(file_path) as f:
            context = ET.iterparse(f, events=("end",))
            for event, elem in context:
                if elem.tag == record_tag:
                    yield elem
                    # Clear element to save memory
                    elem.clear()

    def _store_descriptor(
        self,
        descriptor: MeSHDescriptor,
        mesh_year: int,
        conn: Any,
    ) -> int:
        """
        Store a descriptor and its concepts/terms in the database.

        Args:
            descriptor: Parsed descriptor
            mesh_year: MeSH year
            conn: Database connection

        Returns:
            Number of terms stored
        """
        terms_count = 0

        with conn.cursor() as cur:
            # Insert descriptor
            cur.execute(
                """
                INSERT INTO mesh.descriptors (
                    descriptor_ui, descriptor_name, scope_note, annotation,
                    history_note, public_mesh_note, nlm_classification,
                    date_created, date_revised, date_established, mesh_year
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (descriptor_ui) DO UPDATE SET
                    descriptor_name = EXCLUDED.descriptor_name,
                    scope_note = EXCLUDED.scope_note,
                    annotation = EXCLUDED.annotation,
                    history_note = EXCLUDED.history_note,
                    public_mesh_note = EXCLUDED.public_mesh_note,
                    nlm_classification = EXCLUDED.nlm_classification,
                    date_revised = EXCLUDED.date_revised,
                    mesh_year = EXCLUDED.mesh_year,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    descriptor.descriptor_ui,
                    descriptor.descriptor_name,
                    descriptor.scope_note,
                    descriptor.annotation,
                    descriptor.history_note,
                    descriptor.public_mesh_note,
                    descriptor.nlm_classification,
                    self._parse_date(descriptor.date_created),
                    self._parse_date(descriptor.date_revised),
                    self._parse_date(descriptor.date_established),
                    mesh_year,
                ),
            )
            descriptor_id = cur.fetchone()[0]

            # Delete existing tree numbers (for clean update)
            cur.execute(
                "DELETE FROM mesh.tree_numbers WHERE descriptor_id = %s",
                (descriptor_id,),
            )

            # Insert tree numbers
            for tree_num in descriptor.tree_numbers:
                level = tree_num.count(".") + 1
                cur.execute(
                    """
                    INSERT INTO mesh.tree_numbers (descriptor_id, tree_number, tree_level)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (descriptor_id, tree_number) DO NOTHING
                    """,
                    (descriptor_id, tree_num, level),
                )

            # Insert concepts and terms
            for concept_data in descriptor.concepts:
                cur.execute(
                    """
                    INSERT INTO mesh.concepts (
                        concept_ui, concept_name, descriptor_id, is_preferred,
                        scope_note, cas_registry_number
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (concept_ui) DO UPDATE SET
                        concept_name = EXCLUDED.concept_name,
                        is_preferred = EXCLUDED.is_preferred,
                        scope_note = EXCLUDED.scope_note
                    RETURNING id
                    """,
                    (
                        concept_data["concept_ui"],
                        concept_data["concept_name"],
                        descriptor_id,
                        concept_data["is_preferred"],
                        concept_data.get("scope_note"),
                        concept_data.get("cas_registry_number"),
                    ),
                )
                concept_id = cur.fetchone()[0]

                # Insert terms
                for term_data in concept_data.get("terms", []):
                    cur.execute(
                        """
                        INSERT INTO mesh.terms (
                            term_ui, term_text, concept_id, is_preferred,
                            is_permuted, lexical_tag, entry_combination, sort_version
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            term_data["term_ui"],
                            term_data["term_text"],
                            concept_id,
                            term_data["is_preferred"],
                            term_data["is_permuted"],
                            term_data.get("lexical_tag"),
                            term_data.get("entry_combination"),
                            term_data.get("sort_version"),
                        ),
                    )
                    terms_count += 1

        return terms_count

    def _parse_date(self, year_str: Optional[str]) -> Optional[str]:
        """
        Parse a year string to a date.

        Args:
            year_str: Year string (e.g., "2025")

        Returns:
            Date string or None
        """
        if year_str:
            try:
                return f"{int(year_str)}-01-01"
            except ValueError:
                pass
        return None

    def import_descriptors(
        self,
        file_path: Path,
        mesh_year: int,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> ImportStats:
        """
        Import MeSH descriptors from XML file.

        Args:
            file_path: Path to descriptor XML file
            mesh_year: MeSH year
            progress_callback: Optional callback(processed, total)

        Returns:
            Import statistics
        """
        stats = ImportStats(mesh_year=mesh_year, import_type="full")

        try:
            # Count total records first (for progress)
            total_records = sum(1 for _ in self._iter_xml_records(file_path, "DescriptorRecord"))
            logger.info(f"Found {total_records:,} descriptor records")

            # Process records
            with self.db_manager.get_connection() as conn:
                for i, elem in enumerate(self._iter_xml_records(file_path, "DescriptorRecord")):
                    descriptor = self._parse_descriptor(elem)
                    terms_count = self._store_descriptor(descriptor, mesh_year, conn)

                    stats.descriptors += 1
                    stats.concepts += len(descriptor.concepts)
                    stats.terms += terms_count
                    stats.tree_numbers += len(descriptor.tree_numbers)

                    if progress_callback and (i + 1) % 100 == 0:
                        progress_callback(i + 1, total_records)

                conn.commit()

            stats.mark_completed()
            logger.info(
                f"Imported {stats.descriptors:,} descriptors, "
                f"{stats.concepts:,} concepts, {stats.terms:,} terms"
            )

        except Exception as e:
            logger.error(f"Error importing descriptors: {e}")
            stats.mark_failed(str(e))
            raise

        return stats

    def import_qualifiers(
        self,
        file_path: Path,
        mesh_year: int,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> ImportStats:
        """
        Import MeSH qualifiers from XML file.

        Args:
            file_path: Path to qualifier XML file
            mesh_year: MeSH year
            progress_callback: Optional callback(processed, total)

        Returns:
            Import statistics
        """
        stats = ImportStats(mesh_year=mesh_year, import_type="full")

        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    for elem in self._iter_xml_records(file_path, "QualifierRecord"):
                        qualifier = self._parse_qualifier(elem)

                        cur.execute(
                            """
                            INSERT INTO mesh.qualifiers (
                                qualifier_ui, qualifier_name, abbreviation,
                                scope_note, annotation, mesh_year
                            ) VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (qualifier_ui) DO UPDATE SET
                                qualifier_name = EXCLUDED.qualifier_name,
                                abbreviation = EXCLUDED.abbreviation,
                                scope_note = EXCLUDED.scope_note,
                                annotation = EXCLUDED.annotation,
                                mesh_year = EXCLUDED.mesh_year
                            """,
                            (
                                qualifier.qualifier_ui,
                                qualifier.qualifier_name,
                                qualifier.abbreviation,
                                qualifier.scope_note,
                                qualifier.annotation,
                                mesh_year,
                            ),
                        )
                        stats.qualifiers += 1

                        if progress_callback:
                            progress_callback(stats.qualifiers, 0)

                conn.commit()

            stats.mark_completed()
            logger.info(f"Imported {stats.qualifiers:,} qualifiers")

        except Exception as e:
            logger.error(f"Error importing qualifiers: {e}")
            stats.mark_failed(str(e))
            raise

        return stats

    def import_supplementary_concepts(
        self,
        file_path: Path,
        mesh_year: int,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> ImportStats:
        """
        Import MeSH supplementary concept records from XML file.

        Args:
            file_path: Path to supplementary XML file
            mesh_year: MeSH year
            progress_callback: Optional callback(processed, total)

        Returns:
            Import statistics
        """
        stats = ImportStats(mesh_year=mesh_year, import_type="supplementary")

        try:
            # Count total records
            total_records = sum(
                1 for _ in self._iter_xml_records(file_path, "SupplementalRecord")
            )
            logger.info(f"Found {total_records:,} supplementary records")

            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    for i, elem in enumerate(
                        self._iter_xml_records(file_path, "SupplementalRecord")
                    ):
                        scr = self._parse_supplementary(elem)

                        cur.execute(
                            """
                            INSERT INTO mesh.supplementary_concepts (
                                supplemental_ui, supplemental_name, note,
                                cas_registry_number, frequency, heading_mapped_to,
                                indexing_information, mesh_year
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (supplemental_ui) DO UPDATE SET
                                supplemental_name = EXCLUDED.supplemental_name,
                                note = EXCLUDED.note,
                                cas_registry_number = EXCLUDED.cas_registry_number,
                                frequency = EXCLUDED.frequency,
                                heading_mapped_to = EXCLUDED.heading_mapped_to,
                                indexing_information = EXCLUDED.indexing_information,
                                mesh_year = EXCLUDED.mesh_year
                            """,
                            (
                                scr.supplemental_ui,
                                scr.supplemental_name,
                                scr.note,
                                scr.cas_registry_number,
                                scr.frequency,
                                scr.heading_mapped_to,
                                scr.indexing_information,
                                mesh_year,
                            ),
                        )
                        stats.supplementary_concepts += 1

                        if progress_callback and (i + 1) % 1000 == 0:
                            progress_callback(i + 1, total_records)

                conn.commit()

            stats.mark_completed()
            logger.info(f"Imported {stats.supplementary_concepts:,} supplementary concepts")

        except Exception as e:
            logger.error(f"Error importing supplementary concepts: {e}")
            stats.mark_failed(str(e))
            raise

        return stats

    def _record_import(self, stats: ImportStats) -> int:
        """
        Record import in history table.

        Args:
            stats: Import statistics

        Returns:
            Import history ID
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO mesh.import_history (
                        mesh_year, import_type, descriptors_imported,
                        concepts_imported, terms_imported, tree_numbers_imported,
                        qualifiers_imported, scrs_imported, import_status,
                        started_at, completed_at, error_message
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        stats.mesh_year,
                        stats.import_type,
                        stats.descriptors,
                        stats.concepts,
                        stats.terms,
                        stats.tree_numbers,
                        stats.qualifiers,
                        stats.supplementary_concepts,
                        stats.status,
                        stats.started_at,
                        stats.completed_at,
                        stats.error_message,
                    ),
                )
                import_id = cur.fetchone()[0]
            conn.commit()
        return import_id

    def import_mesh(
        self,
        year: int,
        include_supplementary: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> ImportStats:
        """
        Download and import complete MeSH vocabulary for a year.

        Args:
            year: MeSH year to import
            include_supplementary: Whether to include supplementary concepts
            progress_callback: Optional callback(phase, processed, total)

        Returns:
            Combined import statistics
        """
        total_stats = ImportStats(mesh_year=year, import_type="full")

        try:
            # Download files
            logger.info(f"Downloading MeSH {year} files...")
            if progress_callback:
                progress_callback("download", 0, 3 if include_supplementary else 2)

            files = self.download_mesh_files(year, include_supplementary)

            if "descriptor" not in files:
                raise ValueError("Failed to download descriptor file")

            # Import descriptors
            logger.info("Importing descriptors...")
            desc_stats = self.import_descriptors(
                files["descriptor"],
                year,
                lambda p, t: progress_callback("descriptors", p, t)
                if progress_callback
                else None,
            )
            total_stats.descriptors = desc_stats.descriptors
            total_stats.concepts = desc_stats.concepts
            total_stats.terms = desc_stats.terms
            total_stats.tree_numbers = desc_stats.tree_numbers

            # Import qualifiers
            if "qualifier" in files:
                logger.info("Importing qualifiers...")
                qual_stats = self.import_qualifiers(
                    files["qualifier"],
                    year,
                    lambda p, t: progress_callback("qualifiers", p, t)
                    if progress_callback
                    else None,
                )
                total_stats.qualifiers = qual_stats.qualifiers

            # Import supplementary concepts
            if include_supplementary and "supplementary" in files:
                logger.info("Importing supplementary concepts...")
                supp_stats = self.import_supplementary_concepts(
                    files["supplementary"],
                    year,
                    lambda p, t: progress_callback("supplementary", p, t)
                    if progress_callback
                    else None,
                )
                total_stats.supplementary_concepts = supp_stats.supplementary_concepts

            # Clean up downloads if requested
            if not self.keep_downloads:
                for file_path in files.values():
                    try:
                        file_path.unlink()
                    except Exception as e:
                        logger.warning(f"Could not delete {file_path}: {e}")

            total_stats.mark_completed()
            self._record_import(total_stats)

            logger.info(
                f"MeSH {year} import complete: "
                f"{total_stats.descriptors:,} descriptors, "
                f"{total_stats.concepts:,} concepts, "
                f"{total_stats.terms:,} terms, "
                f"{total_stats.qualifiers:,} qualifiers, "
                f"{total_stats.supplementary_concepts:,} SCRs"
            )

        except Exception as e:
            logger.error(f"MeSH import failed: {e}")
            total_stats.mark_failed(str(e))
            self._record_import(total_stats)
            raise

        return total_stats

    def get_import_history(self) -> List[Dict[str, Any]]:
        """
        Get import history from database.

        Returns:
            List of import history records
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id, mesh_year, import_type,
                        descriptors_imported, concepts_imported, terms_imported,
                        tree_numbers_imported, qualifiers_imported, scrs_imported,
                        import_status, started_at, completed_at, error_message
                    FROM mesh.import_history
                    ORDER BY started_at DESC
                    """
                )
                columns = [
                    "id",
                    "mesh_year",
                    "import_type",
                    "descriptors",
                    "concepts",
                    "terms",
                    "tree_numbers",
                    "qualifiers",
                    "scrs",
                    "status",
                    "started_at",
                    "completed_at",
                    "error_message",
                ]
                return [dict(zip(columns, row)) for row in cur.fetchall()]

    def get_statistics(self) -> Dict[str, int]:
        """
        Get current MeSH database statistics.

        Returns:
            Dictionary with counts of each entity type
        """
        with self.db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM mesh.get_statistics()")
                return {row[0]: row[1] for row in cur.fetchall()}
