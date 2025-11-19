#!/usr/bin/env python3
"""
Import PubMedQA abstracts (CONTEXTS and LONG_ANSWER) into factcheck.statements table.

This script updates existing factcheck.statements records with context and long_answer
fields from the PubMedQA dataset without modifying any other existing data.

Usage:
    python import_pubmedqa_abstracts.py <json_file>
    python import_pubmedqa_abstracts.py src/bmlibrarian/factchecker/ori_pqal.json
    python import_pubmedqa_abstracts.py ori_pqal.json --dry-run
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import psycopg
from dotenv import load_dotenv


class PubMedQAImporter:
    """Import PubMedQA abstracts into factcheck.statements table."""

    def __init__(self, host: str, port: str, user: str, password: str, database: str):
        """Initialize the importer with database connection parameters."""
        self.conn_params = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "dbname": database
        }

    @classmethod
    def from_env(cls) -> 'PubMedQAImporter':
        """Create PubMedQAImporter from environment variables."""
        load_dotenv()

        user = os.getenv("POSTGRES_USER")
        password = os.getenv("POSTGRES_PASSWORD")

        if not user or not password:
            raise ValueError("Missing POSTGRES_USER or POSTGRES_PASSWORD in environment")

        return cls(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            user=user,
            password=password,
            database=os.getenv("POSTGRES_DB", "knowledgebase")
        )

    def _get_connection(self) -> psycopg.Connection:
        """Get a database connection."""
        return psycopg.connect(**self.conn_params)

    def validate_table_structure(self) -> Tuple[bool, str]:
        """
        Validate that factcheck.statements table has required columns.

        Returns:
            Tuple of (success, message)
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Check if factcheck schema exists
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.schemata
                            WHERE schema_name = 'factcheck'
                        )
                    """)
                    if not cur.fetchone()[0]:
                        return False, "factcheck schema does not exist"

                    # Check if statements table exists
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_schema = 'factcheck' AND table_name = 'statements'
                        )
                    """)
                    if not cur.fetchone()[0]:
                        return False, "factcheck.statements table does not exist"

                    # Check for required columns
                    cur.execute("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'factcheck' AND table_name = 'statements'
                        ORDER BY column_name
                    """)
                    columns = {row[0] for row in cur.fetchall()}

                    required_columns = {
                        'statement_id', 'statement_text', 'input_statement_id',
                        'expected_answer', 'created_at', 'source_file', 'review_status',
                        'context', 'long_answer'  # New columns from migration 009
                    }

                    missing_columns = required_columns - columns
                    if missing_columns:
                        return False, f"Missing columns: {', '.join(missing_columns)}. Run migration 009 first."

                    return True, "Table structure validated successfully"

        except Exception as e:
            return False, f"Validation error: {e}"

    def count_existing_rows(self) -> int:
        """Count existing rows in factcheck.statements table."""
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM factcheck.statements")
                return cur.fetchone()[0]

    def validate_json_structure(self, json_data: Dict) -> Tuple[bool, str]:
        """
        Validate that JSON data matches expected PubMedQA format.

        Expected format:
        {
            "PMID": {
                "QUESTION": "...",
                "CONTEXTS": ["...", "..."],
                "LONG_ANSWER": "...",
                "final_decision": "yes|no|maybe",
                ...
            },
            ...
        }

        Returns:
            Tuple of (success, message)
        """
        if not isinstance(json_data, dict):
            return False, "JSON data must be a dictionary"

        if len(json_data) == 0:
            return False, "JSON data is empty"

        # Validate structure of first few entries
        sample_size = min(5, len(json_data))
        for pmid, entry in list(json_data.items())[:sample_size]:
            if not isinstance(entry, dict):
                return False, f"Entry for PMID {pmid} is not a dictionary"

            required_fields = ['QUESTION', 'CONTEXTS', 'LONG_ANSWER', 'final_decision']
            missing_fields = [f for f in required_fields if f not in entry]
            if missing_fields:
                return False, f"Entry for PMID {pmid} missing fields: {', '.join(missing_fields)}"

            if not isinstance(entry['CONTEXTS'], list):
                return False, f"CONTEXTS for PMID {pmid} must be a list"

            if not isinstance(entry['QUESTION'], str):
                return False, f"QUESTION for PMID {pmid} must be a string"

            if not isinstance(entry['LONG_ANSWER'], str):
                return False, f"LONG_ANSWER for PMID {pmid} must be a string"

            if entry['final_decision'] not in ['yes', 'no', 'maybe']:
                return False, f"final_decision for PMID {pmid} must be yes/no/maybe"

        return True, f"JSON structure validated successfully ({len(json_data)} entries)"

    def import_data(self, json_data: Dict, dry_run: bool = False) -> Tuple[int, int, int, List[str]]:
        """
        Import or update data from JSON into factcheck.statements.

        This method:
        1. If table is empty: INSERT all records
        2. If table has data: UPDATE existing records by matching statement_text,
           only updating context and long_answer fields without modifying other data

        Args:
            json_data: Dictionary with PubMedQA data
            dry_run: If True, don't actually modify the database

        Returns:
            Tuple of (inserted_count, updated_count, skipped_count, errors)
        """
        inserted_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []

        existing_row_count = self.count_existing_rows()

        if existing_row_count == 0:
            # Table is empty - use INSERT
            print(f"\nTable is empty. Inserting {len(json_data)} new records...")
            return self._insert_data(json_data, dry_run)
        else:
            # Table has data - use UPDATE (upsert)
            print(f"\nTable has {existing_row_count} existing rows. Updating records...")
            return self._update_data(json_data, dry_run)

    def _insert_data(self, json_data: Dict, dry_run: bool) -> Tuple[int, int, int, List[str]]:
        """Insert new records into empty table."""
        inserted_count = 0
        skipped_count = 0
        errors = []

        if dry_run:
            print("  [DRY RUN] Would insert records...")
            return len(json_data), 0, 0, []

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for pmid, entry in json_data.items():
                    try:
                        # Join CONTEXTS array into single text
                        context = '\n\n'.join(entry['CONTEXTS']) if entry['CONTEXTS'] else None
                        long_answer = entry.get('LONG_ANSWER')
                        question = entry['QUESTION']
                        expected_answer = entry['final_decision']

                        cur.execute("""
                            INSERT INTO factcheck.statements
                            (statement_text, input_statement_id, expected_answer, source_file, context, long_answer)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (statement_text) DO NOTHING
                        """, (question, pmid, expected_answer, 'ori_pqal.json', context, long_answer))

                        if cur.rowcount > 0:
                            inserted_count += 1
                        else:
                            skipped_count += 1

                    except Exception as e:
                        errors.append(f"PMID {pmid}: {e}")

                conn.commit()

        return inserted_count, 0, skipped_count, errors

    def _update_data(self, json_data: Dict, dry_run: bool) -> Tuple[int, int, int, List[str]]:
        """Update existing records with context and long_answer."""
        inserted_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []

        if dry_run:
            print("  [DRY RUN] Would update records...")
            # Show what would be updated
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    for pmid, entry in list(json_data.items())[:5]:  # Sample first 5
                        question = entry['QUESTION']
                        cur.execute("""
                            SELECT statement_id, context IS NOT NULL, long_answer IS NOT NULL
                            FROM factcheck.statements
                            WHERE statement_text = %s
                        """, (question,))
                        result = cur.fetchone()
                        if result:
                            stmt_id, has_context, has_long_answer = result
                            print(f"  [DRY RUN] Would update statement_id={stmt_id} (PMID {pmid})")
                            print(f"    Current: context={'SET' if has_context else 'NULL'}, "
                                  f"long_answer={'SET' if has_long_answer else 'NULL'}")
                        else:
                            print(f"  [DRY RUN] Would insert new record (PMID {pmid})")
            return 0, 0, 0, []

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                for pmid, entry in json_data.items():
                    try:
                        # Join CONTEXTS array into single text
                        context = '\n\n'.join(entry['CONTEXTS']) if entry['CONTEXTS'] else None
                        long_answer = entry.get('LONG_ANSWER')
                        question = entry['QUESTION']
                        expected_answer = entry['final_decision']

                        # Try UPDATE first
                        cur.execute("""
                            UPDATE factcheck.statements
                            SET context = %s,
                                long_answer = %s
                            WHERE statement_text = %s
                        """, (context, long_answer, question))

                        if cur.rowcount > 0:
                            updated_count += 1
                        else:
                            # Record doesn't exist - INSERT it
                            cur.execute("""
                                INSERT INTO factcheck.statements
                                (statement_text, input_statement_id, expected_answer, source_file, context, long_answer)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """, (question, pmid, expected_answer, 'ori_pqal.json', context, long_answer))

                            if cur.rowcount > 0:
                                inserted_count += 1
                            else:
                                skipped_count += 1

                    except Exception as e:
                        errors.append(f"PMID {pmid}: {e}")

                conn.commit()

        return inserted_count, updated_count, skipped_count, errors


def main():
    """Main entry point for import script."""
    parser = argparse.ArgumentParser(
        description="Import PubMedQA abstracts (CONTEXTS and LONG_ANSWER) into factcheck.statements",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Import from PubMedQA dataset file
  python import_pubmedqa_abstracts.py src/bmlibrarian/factchecker/ori_pqal.json

  # Dry run to preview changes
  python import_pubmedqa_abstracts.py ori_pqal.json --dry-run

Note: Run migration 009 first to add required columns:
  python -m src.bmlibrarian.migrations
        """
    )

    parser.add_argument(
        'json_file',
        type=str,
        help='Path to PubMedQA JSON file (ori_pqal.json)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying database'
    )

    args = parser.parse_args()

    # Validate input file
    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"\n✗ Error: Input file not found: {args.json_file}")
        return 1

    print("=" * 80)
    print("PubMedQA Abstract Importer")
    print("=" * 80)

    # Load JSON data
    print(f"\nLoading JSON file: {json_path}")
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    except Exception as e:
        print(f"\n✗ Error loading JSON file: {e}")
        return 1

    # Create importer
    try:
        importer = PubMedQAImporter.from_env()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("  Please ensure database credentials are set in .env file")
        return 1

    # Validate table structure
    print("\n1. Validating table structure...")
    success, message = importer.validate_table_structure()
    if not success:
        print(f"  ✗ {message}")
        print("\n  Please run migration 009 first:")
        print("    uv run python -c \"from src.bmlibrarian.migrations import MigrationManager; "
              "mm = MigrationManager.from_env(); mm.apply_pending_migrations('migrations')\"")
        return 1
    print(f"  ✓ {message}")

    # Validate JSON structure
    print("\n2. Validating JSON structure...")
    success, message = importer.validate_json_structure(json_data)
    if not success:
        print(f"  ✗ {message}")
        return 1
    print(f"  ✓ {message}")

    # Import data
    print("\n3. Importing data...")
    if args.dry_run:
        print("  [DRY RUN MODE - No changes will be made]")

    inserted, updated, skipped, errors = importer.import_data(json_data, dry_run=args.dry_run)

    # Print summary
    print("\n" + "=" * 80)
    print("Import Summary")
    print("=" * 80)
    print(f"  Total records in JSON:  {len(json_data)}")
    print(f"  Inserted (new):         {inserted}")
    print(f"  Updated (existing):     {updated}")
    print(f"  Skipped:                {skipped}")
    print(f"  Errors:                 {len(errors)}")

    if errors:
        print("\nErrors:")
        for error in errors[:10]:  # Show first 10 errors
            print(f"  ✗ {error}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more errors")

    if args.dry_run:
        print("\n[DRY RUN] No changes were made to the database.")
        print("Run without --dry-run to apply changes.")
    else:
        print("\n✓ Import completed successfully!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
