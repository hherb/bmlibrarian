#!/usr/bin/env python3
"""
MeSH XML Importer CLI for BMLibrarian Thesaurus.

Imports MeSH (Medical Subject Headings) descriptors, terms, and hierarchies
into the thesaurus database schema.
"""

import sys
import logging
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Iterator, Generator, Any
from datetime import datetime
from dataclasses import dataclass

import psycopg

from bmlibrarian.database import DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants (golden rule #2: no magic numbers)
PROGRESS_LOG_INTERVAL = 1000  # Log progress every N descriptors during validation
STREAMING_THRESHOLD_MB = 100  # Use streaming parser for files larger than this size
BYTES_PER_MB = 1024 * 1024  # Conversion factor for megabytes


@dataclass
class ImportStats:
    """Statistics for MeSH import operation."""
    concepts_imported: int = 0
    terms_imported: int = 0
    hierarchies_imported: int = 0
    errors: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def duration_seconds(self) -> int:
        """Calculate import duration in seconds."""
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time).total_seconds())
        return 0


class MeshImporter:
    """
    Imports MeSH XML descriptors into thesaurus database schema.

    Parses MeSH XML format and populates thesaurus.concepts, thesaurus.terms,
    and thesaurus.concept_hierarchies tables.
    """

    # MeSH lexical tag to term type mapping
    LEXICAL_TAG_MAPPING = {
        'NON': 'preferred',
        'ABB': 'abbreviation',
        'SYN': 'synonym',
        'TRD': 'trade_name',
        'OBS': 'obsolete'
    }

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        use_streaming: bool = True
    ):
        """
        Initialize the MeSH importer.

        Args:
            db_manager: Optional DatabaseManager instance (creates new if None)
            use_streaming: Whether to use streaming parser for large files (default: True)
        """
        self.db = db_manager or DatabaseManager()
        self.stats = ImportStats()
        self.use_streaming = use_streaming

    def import_mesh_xml(
        self,
        xml_path: Path,
        source_version: str = "2025",
        dry_run: bool = False,
        batch_size: int = 100
    ) -> ImportStats:
        """
        Import MeSH descriptors from XML file.

        Args:
            xml_path: Path to MeSH descriptor XML file (desc2025.xml)
            source_version: MeSH version identifier (default: "2025")
            dry_run: If True, parse XML but don't write to database
            batch_size: Number of concepts to import per transaction

        Returns:
            ImportStats with import statistics

        Raises:
            FileNotFoundError: If XML file doesn't exist
            ValueError: If XML is malformed or invalid
            RuntimeError: If database operations fail
        """
        if not xml_path.exists():
            raise FileNotFoundError(f"MeSH XML file not found: {xml_path}")

        logger.info(f"Starting MeSH import from: {xml_path}")
        logger.info(f"Source version: {source_version}")
        logger.info(f"Dry run: {dry_run}")

        self.stats.start_time = datetime.now()

        # Determine if we should use streaming based on file size
        file_size_mb = xml_path.stat().st_size / BYTES_PER_MB
        should_stream = self.use_streaming and file_size_mb > STREAMING_THRESHOLD_MB

        if should_stream:
            logger.info(f"File size: {file_size_mb:.1f} MB - using streaming parser for memory efficiency")
        else:
            logger.info(f"File size: {file_size_mb:.1f} MB - using standard parser")

        try:
            if should_stream:
                # Use streaming parser for large files
                if dry_run:
                    logger.info("Dry run mode - skipping database import")
                    self._dry_run_validation_streaming(xml_path)
                else:
                    self._import_descriptors_streaming(
                        xml_path,
                        source_version,
                        batch_size
                    )
            else:
                # Use standard parser for smaller files
                logger.info("Parsing XML file...")
                tree = ET.parse(xml_path)
                root = tree.getroot()

                descriptors = root.findall('.//DescriptorRecord')
                total_descriptors = len(descriptors)
                logger.info(f"Found {total_descriptors} descriptors to import")

                if dry_run:
                    logger.info("Dry run mode - skipping database import")
                    self._dry_run_validation(descriptors)
                else:
                    self._import_descriptors_batch(
                        descriptors,
                        source_version,
                        batch_size
                    )

            self.stats.end_time = datetime.now()

            # Record import history
            if not dry_run:
                self._record_import_history(source_version, xml_path)

            logger.info("Import completed successfully")
            self._print_stats()

            return self.stats

        except ET.ParseError as e:
            logger.error(f"XML parsing error: {e}")
            raise ValueError(f"Invalid MeSH XML format: {e}")
        except Exception as e:
            logger.error(f"Import failed: {e}")
            raise RuntimeError(f"MeSH import failed: {e}")

    def _dry_run_validation(self, descriptors: List[ET.Element]) -> None:
        """Validate XML structure without importing to database."""
        logger.info("Validating XML structure...")

        for i, descriptor in enumerate(descriptors, 1):
            try:
                # Extract descriptor ID and name
                desc_ui = descriptor.find('DescriptorUI')
                desc_name = descriptor.find('DescriptorName/String')

                if desc_ui is None or desc_name is None:
                    logger.warning(f"Descriptor {i}: Missing required fields")
                    self.stats.errors += 1
                    continue

                # Extract terms
                terms = descriptor.findall('.//Term')
                term_count = len(terms)

                # Extract tree numbers
                tree_numbers = descriptor.findall('.//TreeNumber')
                tree_count = len(tree_numbers)

                if i % PROGRESS_LOG_INTERVAL == 0:
                    logger.info(f"Validated {i}/{len(descriptors)} descriptors")

                self.stats.concepts_imported += 1
                self.stats.terms_imported += term_count
                self.stats.hierarchies_imported += tree_count

            except Exception as e:
                logger.warning(f"Error validating descriptor {i}: {e}")
                self.stats.errors += 1

        logger.info("Validation complete")

    def _import_descriptors_batch(
        self,
        descriptors: List[ET.Element],
        source_version: str,
        batch_size: int
    ) -> None:
        """Import descriptors in batches for better performance."""
        total = len(descriptors)

        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            batch = descriptors[batch_start:batch_end]

            try:
                with self.db.get_connection() as conn:
                    with conn.cursor() as cur:
                        for descriptor in batch:
                            self._import_descriptor(descriptor, source_version, cur)

                        # Commit batch
                        conn.commit()

                logger.info(f"Imported {batch_end}/{total} descriptors "
                           f"({self.stats.concepts_imported} concepts, "
                           f"{self.stats.terms_imported} terms, "
                           f"{self.stats.hierarchies_imported} hierarchies)")

            except Exception as e:
                logger.error(f"Batch import failed at {batch_start}-{batch_end}: {e}")
                self.stats.errors += len(batch)
                # Continue with next batch
                continue

    def _stream_descriptors(self, xml_path: Path) -> Generator[ET.Element, None, None]:
        """
        Stream DescriptorRecord elements from XML file using iterparse.

        This is memory-efficient as elements are yielded one at a time
        and cleared after processing.

        Args:
            xml_path: Path to the MeSH XML file

        Yields:
            ET.Element: Individual DescriptorRecord elements
        """
        # Use iterparse to stream the XML file
        context = ET.iterparse(str(xml_path), events=['end'])

        for event, elem in context:
            if elem.tag == 'DescriptorRecord':
                yield elem
                # Clear the element to free memory
                elem.clear()

    def _dry_run_validation_streaming(self, xml_path: Path) -> None:
        """Validate XML structure using streaming parser without loading all into memory."""
        logger.info("Validating XML structure (streaming mode)...")

        descriptor_count = 0
        for descriptor in self._stream_descriptors(xml_path):
            descriptor_count += 1
            try:
                # Extract descriptor ID and name
                desc_ui = descriptor.find('DescriptorUI')
                desc_name = descriptor.find('DescriptorName/String')

                if desc_ui is None or desc_name is None:
                    logger.warning(f"Descriptor {descriptor_count}: Missing required fields")
                    self.stats.errors += 1
                    continue

                # Extract terms
                terms = descriptor.findall('.//Term')
                term_count = len(terms)

                # Extract tree numbers
                tree_numbers = descriptor.findall('.//TreeNumber')
                tree_count = len(tree_numbers)

                if descriptor_count % PROGRESS_LOG_INTERVAL == 0:
                    logger.info(f"Validated {descriptor_count} descriptors (streaming)")

                self.stats.concepts_imported += 1
                self.stats.terms_imported += term_count
                self.stats.hierarchies_imported += tree_count

            except Exception as e:
                logger.warning(f"Error validating descriptor {descriptor_count}: {e}")
                self.stats.errors += 1

        logger.info(f"Validation complete: {descriptor_count} descriptors processed")

    def _import_descriptors_streaming(
        self,
        xml_path: Path,
        source_version: str,
        batch_size: int
    ) -> None:
        """Import descriptors using streaming parser for memory efficiency."""
        batch: List[ET.Element] = []
        batch_count = 0
        descriptor_count = 0

        for descriptor in self._stream_descriptors(xml_path):
            descriptor_count += 1
            # Make a deep copy since the element will be cleared by the generator
            batch.append(ET.fromstring(ET.tostring(descriptor)))

            if len(batch) >= batch_size:
                batch_count += 1
                try:
                    with self.db.get_connection() as conn:
                        with conn.cursor() as cur:
                            for desc in batch:
                                self._import_descriptor(desc, source_version, cur)
                            conn.commit()

                    logger.info(
                        f"Imported batch {batch_count} ({descriptor_count} total descriptors, "
                        f"{self.stats.concepts_imported} concepts, "
                        f"{self.stats.terms_imported} terms, "
                        f"{self.stats.hierarchies_imported} hierarchies)"
                    )
                except Exception as e:
                    logger.error(f"Batch {batch_count} import failed: {e}")
                    self.stats.errors += len(batch)

                batch.clear()

        # Process remaining items in the final batch
        if batch:
            batch_count += 1
            try:
                with self.db.get_connection() as conn:
                    with conn.cursor() as cur:
                        for desc in batch:
                            self._import_descriptor(desc, source_version, cur)
                        conn.commit()

                logger.info(
                    f"Imported final batch {batch_count} ({descriptor_count} total descriptors, "
                    f"{self.stats.concepts_imported} concepts, "
                    f"{self.stats.terms_imported} terms, "
                    f"{self.stats.hierarchies_imported} hierarchies)"
                )
            except Exception as e:
                logger.error(f"Final batch {batch_count} import failed: {e}")
                self.stats.errors += len(batch)

        logger.info(f"Streaming import complete: {descriptor_count} descriptors processed")

    def _import_descriptor(
        self,
        descriptor: ET.Element,
        source_version: str,
        cursor: psycopg.Cursor[Any]
    ) -> None:
        """Import a single MeSH descriptor with its terms and hierarchies."""
        try:
            # Extract descriptor metadata
            desc_ui = descriptor.find('DescriptorUI').text
            desc_name = descriptor.find('DescriptorName/String').text
            desc_class = descriptor.get('DescriptorClass', '1')

            # Extract definition (ScopeNote)
            scope_note_elem = descriptor.find('.//ScopeNote')
            definition = scope_note_elem.text if scope_note_elem is not None else None

            # Insert concept
            cursor.execute("""
                INSERT INTO thesaurus.concepts
                    (preferred_term, definition, semantic_type, source_vocabulary, source_concept_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (source_vocabulary, source_concept_id) DO UPDATE
                SET
                    preferred_term = EXCLUDED.preferred_term,
                    definition = EXCLUDED.definition,
                    semantic_type = EXCLUDED.semantic_type,
                    updated_at = NOW()
                RETURNING concept_id
            """, (desc_name, definition, desc_class, 'mesh', desc_ui))

            result = cursor.fetchone()
            concept_id = result[0] if result else None

            if concept_id is None:
                logger.warning(f"Failed to insert/update concept: {desc_ui}")
                self.stats.errors += 1
                return

            self.stats.concepts_imported += 1

            # Import terms
            terms = descriptor.findall('.//Term')
            for term in terms:
                self._import_term(term, concept_id, cursor)

            # Import tree numbers (hierarchies)
            tree_numbers = descriptor.findall('.//TreeNumber')
            for tree_elem in tree_numbers:
                self._import_tree_number(tree_elem.text, concept_id, cursor)

        except Exception as e:
            logger.warning(f"Error importing descriptor {desc_ui}: {e}")
            self.stats.errors += 1

    def _import_term(
        self,
        term_elem: ET.Element,
        concept_id: int,
        cursor: psycopg.Cursor[Any]
    ) -> None:
        """Import a single term for a concept."""
        try:
            term_ui = term_elem.find('TermUI').text
            term_string = term_elem.find('String').text
            lexical_tag = term_elem.get('LexicalTag', 'NON')

            # Map lexical tag to term type
            term_type = self.LEXICAL_TAG_MAPPING.get(lexical_tag, 'synonym')

            # Insert term
            cursor.execute("""
                INSERT INTO thesaurus.terms
                    (concept_id, term_text, term_type, lexical_tag, source_term_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (concept_id, term_string, term_type, lexical_tag, term_ui))

            self.stats.terms_imported += 1

        except Exception as e:
            logger.debug(f"Error importing term: {e}")
            self.stats.errors += 1

    def _import_tree_number(
        self,
        tree_number: str,
        concept_id: int,
        cursor: psycopg.Cursor[Any]
    ) -> None:
        """Import a tree number (hierarchy relationship) for a concept."""
        try:
            # Calculate tree level from number of dots
            tree_level = tree_number.count('.') + 1

            # Insert hierarchy
            cursor.execute("""
                INSERT INTO thesaurus.concept_hierarchies
                    (concept_id, tree_number, tree_level)
                VALUES (%s, %s, %s)
                ON CONFLICT (concept_id, tree_number) DO NOTHING
            """, (concept_id, tree_number, tree_level))

            self.stats.hierarchies_imported += 1

        except Exception as e:
            logger.debug(f"Error importing tree number {tree_number}: {e}")
            self.stats.errors += 1

    def _record_import_history(self, source_version: str, xml_path: Path) -> None:
        """Record import statistics in import_history table."""
        try:
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO thesaurus.import_history
                            (source_vocabulary, source_version, concepts_imported,
                             terms_imported, hierarchies_imported, import_duration_seconds,
                             import_status, notes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        'mesh',
                        source_version,
                        self.stats.concepts_imported,
                        self.stats.terms_imported,
                        self.stats.hierarchies_imported,
                        self.stats.duration_seconds(),
                        'completed' if self.stats.errors == 0 else 'partial',
                        f"Imported from {xml_path.name}. Errors: {self.stats.errors}"
                    ))
                    conn.commit()

        except Exception as e:
            logger.warning(f"Failed to record import history: {e}")

    def _print_stats(self) -> None:
        """Print import statistics to console."""
        duration = self.stats.duration_seconds()
        print("\n" + "="*60)
        print("MeSH IMPORT STATISTICS")
        print("="*60)
        print(f"Concepts imported:     {self.stats.concepts_imported:,}")
        print(f"Terms imported:        {self.stats.terms_imported:,}")
        print(f"Hierarchies imported:  {self.stats.hierarchies_imported:,}")
        print(f"Errors:                {self.stats.errors:,}")
        print(f"Duration:              {duration} seconds")
        if duration > 0:
            rate = self.stats.concepts_imported / duration
            print(f"Import rate:           {rate:.1f} concepts/second")
        print("="*60)


def main() -> int:
    """Main entry point for MeSH importer CLI."""
    parser = argparse.ArgumentParser(
        description="Import MeSH descriptors into BMLibrarian thesaurus schema",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import MeSH 2025 descriptors
  python thesaurus_import_cli.py desc2025.xml

  # Dry run (validate without importing)
  python thesaurus_import_cli.py desc2025.xml --dry-run

  # Import with custom version and batch size
  python thesaurus_import_cli.py desc2025.xml --version 2025 --batch-size 500

  # Verbose logging
  python thesaurus_import_cli.py desc2025.xml --verbose

  # Disable streaming parser (for small files or debugging)
  python thesaurus_import_cli.py desc2025.xml --no-streaming

Notes:
  For files larger than 100 MB, streaming parsing is automatically used
  to minimize memory consumption. Use --no-streaming to disable this.
        """
    )

    parser.add_argument(
        'xml_file',
        type=Path,
        help='Path to MeSH descriptor XML file (e.g., desc2025.xml)'
    )

    parser.add_argument(
        '--version',
        type=str,
        default='2025',
        help='MeSH version identifier (default: 2025)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate XML without importing to database'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of concepts to import per transaction (default: 100)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    parser.add_argument(
        '--no-streaming',
        action='store_true',
        help='Disable streaming parser (use standard parser for all file sizes)'
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        # Create importer with streaming option
        importer = MeshImporter(use_streaming=not args.no_streaming)

        # Import MeSH data
        stats = importer.import_mesh_xml(
            xml_path=args.xml_file,
            source_version=args.version,
            dry_run=args.dry_run,
            batch_size=args.batch_size
        )

        # Exit with error code if there were errors
        if stats.errors > 0:
            logger.warning(f"Import completed with {stats.errors} errors")
            return 1

        return 0

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return 1
    except RuntimeError as e:
        logger.error(f"Runtime error: {e}")
        return 1
    except KeyboardInterrupt:
        logger.warning("Import cancelled by user")
        return 130
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
