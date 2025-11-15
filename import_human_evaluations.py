#!/usr/bin/env python3
"""
Import Human Evaluations

Re-imports human annotations from JSON files back into the main PostgreSQL database.
Annotations are tagged with the annotator's username for inter-rater reliability analysis.

The import process:
1. Reads JSON file(s) with human annotations
2. Creates/updates annotator records in PostgreSQL
3. Matches statements by statement_id (with statement_text validation)
4. Inserts/updates human annotations (one per annotator per statement)
5. Reports statistics

Usage:
    # Import single file
    python import_human_evaluations.py alice_evaluations.json

    # Import multiple files
    python import_human_evaluations.py alice.json bob.json charlie.json

    # Dry run (preview without committing)
    python import_human_evaluations.py alice.json --dry-run

    # Override annotator username
    python import_human_evaluations.py evaluations.json --annotator alice
"""

import argparse
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from bmlibrarian.factchecker.db.database import FactCheckerDB, Annotator, HumanAnnotation

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_json_file(json_path: str) -> Dict[str, Any]:
    """Load and validate JSON file."""
    logger.info(f"Loading JSON file: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Validate structure
    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON format in {json_path}: Expected object, got {type(data)}")

    if 'annotations' not in data:
        raise ValueError(f"Invalid JSON format in {json_path}: Missing 'annotations' field")

    if not isinstance(data['annotations'], list):
        raise ValueError(f"Invalid JSON format in {json_path}: 'annotations' must be a list")

    metadata = data.get('export_metadata', {})
    annotations = data['annotations']

    logger.info(f"  Metadata: {metadata.get('annotator_username', 'unknown')} @ {metadata.get('export_date', 'unknown')[:10]}")
    logger.info(f"  Annotations: {len(annotations)}")

    return data


def import_annotations_from_json(
    json_data: Dict[str, Any],
    pg_db: FactCheckerDB,
    annotator_override: Optional[str] = None,
    dry_run: bool = False
) -> Dict[str, int]:
    """
    Import annotations from JSON data into PostgreSQL.

    Args:
        json_data: Loaded JSON data with annotations
        pg_db: PostgreSQL database instance
        annotator_override: Override annotator username from JSON metadata
        dry_run: If True, don't commit changes

    Returns:
        Dictionary with import statistics
    """
    stats = {
        'total_annotations': 0,
        'inserted': 0,
        'updated': 0,
        'skipped_no_match': 0,
        'skipped_validation_failed': 0,
        'errors': 0
    }

    metadata = json_data.get('export_metadata', {})
    annotations = json_data['annotations']

    stats['total_annotations'] = len(annotations)

    # Get annotator username
    annotator_username = annotator_override or metadata.get('annotator_username')
    if not annotator_username or annotator_username == 'all':
        logger.error("Annotator username must be specified (in JSON metadata or via --annotator)")
        raise ValueError("No annotator username specified")

    # Create or get annotator record
    logger.info(f"Creating/updating annotator record for: {annotator_username}")
    annotator = Annotator(username=annotator_username)
    annotator_id = pg_db.insert_or_get_annotator(annotator)
    logger.info(f"  Annotator ID: {annotator_id}")

    # Import annotations
    logger.info(f"Importing {len(annotations)} annotations...")

    for i, annot in enumerate(annotations, 1):
        try:
            statement_id = annot.get('statement_id')
            statement_text = annot.get('statement_text', '')
            annotation = annot.get('annotation')
            explanation = annot.get('explanation', '')
            confidence = annot.get('confidence')
            review_duration = annot.get('review_duration_seconds')

            if not statement_id:
                logger.warning(f"  [{i}/{len(annotations)}] Skipping: No statement_id")
                stats['errors'] += 1
                continue

            if not annotation:
                logger.warning(f"  [{i}/{len(annotations)}] Skipping statement {statement_id}: No annotation")
                stats['errors'] += 1
                continue

            # Validate annotation value
            if annotation not in ('yes', 'no', 'maybe', 'unclear'):
                logger.warning(f"  [{i}/{len(annotations)}] Invalid annotation value for statement {statement_id}: {annotation}")
                stats['errors'] += 1
                continue

            # Get statement from database to validate
            stmt = pg_db.get_statement(statement_id)
            if not stmt:
                logger.warning(f"  [{i}/{len(annotations)}] Statement not found in database: {statement_id}")
                stats['skipped_no_match'] += 1
                continue

            # Validate statement text matches (prevent mismatches)
            if stmt.statement_text != statement_text:
                logger.warning(f"  [{i}/{len(annotations)}] Statement text mismatch for ID {statement_id}")
                logger.warning(f"      JSON: {statement_text[:100]}...")
                logger.warning(f"      DB:   {stmt.statement_text[:100]}...")
                stats['skipped_validation_failed'] += 1
                continue

            # Create annotation record
            human_annotation = HumanAnnotation(
                statement_id=statement_id,
                annotator_id=annotator_id,
                annotation=annotation,
                explanation=explanation,
                confidence=confidence,
                review_duration_seconds=review_duration,
                session_id=f"import_{datetime.now().strftime('%Y%m%d')}"
            )

            # Check if annotation already exists
            existing_annotations = pg_db.get_human_annotations(statement_id)
            annotation_exists = any(a.annotator_id == annotator_id for a in existing_annotations)

            if not dry_run:
                # Insert or update
                pg_db.insert_human_annotation(human_annotation)

            if annotation_exists:
                stats['updated'] += 1
                logger.debug(f"  [{i}/{len(annotations)}] Updated annotation for statement {statement_id}")
            else:
                stats['inserted'] += 1
                logger.debug(f"  [{i}/{len(annotations)}] Inserted annotation for statement {statement_id}")

        except Exception as e:
            logger.error(f"  [{i}/{len(annotations)}] Error importing annotation for statement {annot.get('statement_id')}: {e}")
            stats['errors'] += 1
            continue

    return stats


def import_multiple_files(
    json_files: List[str],
    annotator_override: Optional[str] = None,
    dry_run: bool = False
) -> None:
    """
    Import human evaluations from multiple JSON files.

    Args:
        json_files: List of JSON file paths
        annotator_override: Override annotator username
        dry_run: If True, don't commit changes
    """
    # Connect to PostgreSQL
    logger.info("Connecting to PostgreSQL...")
    pg_db = FactCheckerDB()

    total_stats = {
        'files_processed': 0,
        'total_annotations': 0,
        'inserted': 0,
        'updated': 0,
        'skipped_no_match': 0,
        'skipped_validation_failed': 0,
        'errors': 0
    }

    # Process each file
    for json_file in json_files:
        logger.info("=" * 60)
        logger.info(f"Processing file: {json_file}")
        logger.info("=" * 60)

        try:
            # Load JSON
            json_data = load_json_file(json_file)

            # Import annotations
            file_stats = import_annotations_from_json(
                json_data,
                pg_db,
                annotator_override,
                dry_run
            )

            # Update totals
            total_stats['files_processed'] += 1
            for key in file_stats:
                if key in total_stats:
                    total_stats[key] += file_stats[key]

            # Report file stats
            logger.info(f"File statistics:")
            logger.info(f"  Total annotations: {file_stats['total_annotations']}")
            logger.info(f"  Inserted: {file_stats['inserted']}")
            logger.info(f"  Updated: {file_stats['updated']}")
            logger.info(f"  Skipped (no match): {file_stats['skipped_no_match']}")
            logger.info(f"  Skipped (validation failed): {file_stats['skipped_validation_failed']}")
            logger.info(f"  Errors: {file_stats['errors']}")

        except Exception as e:
            logger.error(f"Failed to process file {json_file}: {e}")
            import traceback
            traceback.print_exc()
            continue

    # Report overall statistics
    logger.info("=" * 60)
    logger.info("IMPORT COMPLETE" + (" (DRY RUN)" if dry_run else ""))
    logger.info("=" * 60)
    logger.info(f"Files processed: {total_stats['files_processed']}/{len(json_files)}")
    logger.info(f"Total annotations: {total_stats['total_annotations']}")
    logger.info(f"Successfully inserted: {total_stats['inserted']}")
    logger.info(f"Successfully updated: {total_stats['updated']}")
    logger.info(f"Skipped (no match): {total_stats['skipped_no_match']}")
    logger.info(f"Skipped (validation failed): {total_stats['skipped_validation_failed']}")
    logger.info(f"Errors: {total_stats['errors']}")
    logger.info("=" * 60)

    if dry_run:
        logger.info("DRY RUN: No changes were committed to the database")
    else:
        logger.info("All changes committed to PostgreSQL database")


def main():
    parser = argparse.ArgumentParser(
        description="Import human evaluations from JSON files into PostgreSQL database"
    )
    parser.add_argument(
        'json_files',
        nargs='+',
        help='JSON file(s) containing human evaluations'
    )
    parser.add_argument(
        '--annotator',
        type=str,
        help='Override annotator username (if not in JSON metadata)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview import without committing changes'
    )

    args = parser.parse_args()

    # Validate JSON files
    for json_file in args.json_files:
        json_path = Path(json_file)
        if not json_path.exists():
            logger.error(f"JSON file not found: {json_file}")
            return 1
        if json_path.suffix != '.json':
            logger.error(f"File must have .json extension: {json_file}")
            return 1

    try:
        import_multiple_files(
            json_files=args.json_files,
            annotator_override=args.annotator,
            dry_run=args.dry_run
        )

        return 0

    except Exception as e:
        logger.error(f"Import failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
