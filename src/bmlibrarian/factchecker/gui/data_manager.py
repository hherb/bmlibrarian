"""
Data manager for Fact Checker Review GUI.

Handles loading/saving fact-check results from database or JSON files.
Supports incremental processing and multi-user annotations.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import asdict

from ..db.database import FactCheckerDB, Annotator, HumanAnnotation


class FactCheckDataManager:
    """Manages data loading and saving for fact-check review GUI."""

    def __init__(self, incremental: bool = False):
        """
        Initialize data manager.

        Args:
            incremental: If True, only load statements without AI evaluations
        """
        self.results: List[Dict[str, Any]] = []
        self.reviews: List[Dict[str, Any]] = []
        self.input_file_path: str = ""
        self.incremental: bool = incremental

        # Database mode
        self.using_database: bool = False
        self.fact_checker_db: Optional[FactCheckerDB] = None
        self.db_path: Optional[str] = None

        # Annotator information
        self.annotator_id: Optional[int] = None
        self.annotator_username: Optional[str] = None
        self.annotator_info: Optional[Dict[str, Any]] = None

    def set_annotator(self, annotator_info: Dict[str, Any]):
        """
        Set annotator information.

        Args:
            annotator_info: Dictionary with username, full_name, email, expertise_level
        """
        self.annotator_info = annotator_info
        self.annotator_username = annotator_info.get('username')

        # Register annotator in database if using database mode
        if self.using_database and self.fact_checker_db:
            annotator = Annotator(**annotator_info)
            self.annotator_id = self.fact_checker_db.insert_or_get_annotator(annotator)
            print(f"✓ Annotator registered: {self.annotator_username} (ID: {self.annotator_id})")

    def load_from_database(self, db_path: str, skip_incremental_filter: bool = False):
        """
        Load results from SQLite database.

        Args:
            db_path: Path to SQLite database file
            skip_incremental_filter: If True, don't apply incremental filtering even if incremental mode is on
        """
        self.fact_checker_db = FactCheckerDB(db_path)
        self.db_path = db_path
        self.using_database = True

        # Register annotator if info is available
        if self.annotator_info:
            annotator = Annotator(**self.annotator_info)
            self.annotator_id = self.fact_checker_db.insert_or_get_annotator(annotator)

        # Load all statements with evaluations
        all_data = self.fact_checker_db.get_all_statements_with_evaluations()

        if not all_data:
            raise ValueError("No statements found in database")

        # Note: Incremental filtering happens AFTER loading human annotations
        # so we can check which statements this user has already annotated

        # Convert database format to display format
        self.results = []
        for row in all_data:
            result = {
                'statement_id': row['id'],
                'statement': row['statement_text'],
                'expected_answer': row['expected_answer'],
                'evaluation': row.get('evaluation'),
                'reason': row.get('reason'),
                'confidence': row.get('confidence'),
                'evidence_list': [],
                'human_annotations': row.get('human_annotations', [])
            }

            # Convert evidence to expected format
            for ev in row.get('evidence', []):
                result['evidence_list'].append({
                    'citation': ev.get('citation_text', ''),
                    'pmid': f"PMID:{ev.get('pmid')}" if ev.get('pmid') else '',
                    'doi': f"DOI:{ev.get('doi')}" if ev.get('doi') else '',
                    'document_id': ev.get('document_id'),
                    'relevance_score': ev.get('relevance_score'),
                    'stance': ev.get('supports_statement', 'neutral')
                })

            self.results.append(result)

        # Initialize reviews list (load existing annotations)
        self.reviews = [{}] * len(self.results)
        for i, result in enumerate(self.results):
            # Find this annotator's existing annotation if any
            for annot in result.get('human_annotations', []):
                if annot.get('annotator_id') == self.annotator_id:
                    self.reviews[i] = {
                        'human_annotation': annot.get('annotation'),
                        'human_explanation': annot.get('explanation', '')
                    }
                    break

        # Apply incremental mode filtering (only show statements without human annotations by this user)
        # BUT: Skip filtering if explicitly disabled (e.g., when loading from JSON import)
        if self.incremental and not skip_incremental_filter:
            filtered_results = []
            filtered_reviews = []
            for i, result in enumerate(self.results):
                # Check if this user has annotated this statement
                has_user_annotation = bool(self.reviews[i].get('human_annotation'))
                if not has_user_annotation:
                    filtered_results.append(result)
                    filtered_reviews.append(self.reviews[i])

            if not filtered_results:
                raise ValueError(f"No unannotated statements found in database (you have already annotated all {len(self.results)} statements)")

            self.results = filtered_results
            self.reviews = filtered_reviews
            print(f"ℹ️  Incremental mode: Showing {len(self.results)} statements without your annotations (out of {len(all_data)} total)")

        self.input_file_path = db_path

    def load_from_json(self, json_path: str, auto_create_db: bool = True):
        """
        Load results from JSON file, optionally creating/updating a database.

        When auto_create_db is True (default for GUI):
        1. Check if corresponding .db file exists (same name as JSON)
        2. If .db exists: Load from DB and import new statements from JSON
        3. If .db doesn't exist: Create new DB and import all JSON data
        4. Always use database mode after this process

        Args:
            json_path: Path to JSON file
            auto_create_db: If True, automatically create/update database (default: True)
        """
        json_file = Path(json_path)
        db_path = json_file.parent / f"{json_file.stem}.db"

        if auto_create_db:
            # Determine if database already exists
            db_exists = db_path.exists()

            if db_exists:
                print(f"ℹ️  Found existing database: {db_path.name}")
                print(f"ℹ️  Importing new statements from JSON into database...")
            else:
                print(f"ℹ️  Creating new database: {db_path.name}")

            # Create/open database
            self.fact_checker_db = FactCheckerDB(str(db_path))
            self.db_path = str(db_path)
            self.using_database = True

            # Import JSON data (intelligently merges with existing data)
            import_stats = self.fact_checker_db.import_json_results(
                json_file=str(json_path),
                skip_existing=True  # Don't overwrite existing evaluations/annotations
            )

            # Report import statistics
            if db_exists:
                print(f"✓ JSON import complete:")
                print(f"  - New statements added: {import_stats['new_statements']}")
                print(f"  - Existing statements skipped: {import_stats['skipped_existing']}")
                print(f"  - Total in JSON file: {import_stats['total_in_file']}")
                if import_stats['errors'] > 0:
                    print(f"  - Errors: {import_stats['errors']}")
            else:
                print(f"✓ Database created with {import_stats['new_statements']} statements")

            # Now load from the database (which has all the data)
            # IMPORTANT: Skip incremental filtering when loading from JSON import
            # The user wants to see ALL statements (including ones they already annotated)
            # to verify the import worked correctly
            self.load_from_database(str(db_path), skip_incremental_filter=True)

            if self.incremental:
                print(f"ℹ️  Incremental mode: Showing ALL {len(self.results)} statements from JSON import (incremental filtering disabled for imports)")

        else:
            # Legacy JSON-only mode (no database)
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Extract results array
            if isinstance(data, dict) and 'results' in data:
                self.results = data['results']
            elif isinstance(data, list):
                self.results = data
            else:
                raise ValueError("Invalid JSON format: expected 'results' array or direct array")

            if not self.results:
                raise ValueError("No results found in file")

            # Filter for incremental mode (only show statements without AI evaluations)
            if self.incremental:
                self.results = [r for r in self.results if not r.get('evaluation')]
                if not self.results:
                    raise ValueError("No unevaluated statements found in JSON file (all statements have AI evaluations)")
                print(f"ℹ️  Incremental mode: Showing {len(self.results)} unevaluated statements")

            # Initialize reviews list
            self.reviews = [{}] * len(self.results)
            self.using_database = False
            self.input_file_path = json_path

    def save_annotation(self, index: int, annotation: str, explanation: str = ""):
        """
        Save annotation for a statement.

        Args:
            index: Statement index
            annotation: Annotation value (yes/no/maybe)
            explanation: Optional explanation text
        """
        if index >= len(self.reviews):
            return

        # Update in-memory reviews
        self.reviews[index] = {
            'human_annotation': annotation,
            'human_explanation': explanation
        }

        # Save to database immediately if in database mode
        if self.using_database and self.fact_checker_db and self.annotator_id:
            try:
                result = self.results[index]
                statement_id = result.get('statement_id')

                # Don't save if no statement_id or if annotation is empty/None (N/A selection)
                if not statement_id or not annotation:
                    return

                human_annotation = HumanAnnotation(
                    statement_id=statement_id,
                    annotator_id=self.annotator_id,
                    annotation=annotation,
                    explanation=explanation,
                    confidence=None,
                    session_id=f"gui_session_{datetime.now().strftime('%Y%m%d')}"
                )

                self.fact_checker_db.insert_human_annotation(human_annotation)
                print(f"✓ Saved annotation for statement {statement_id}")

            except Exception as e:
                print(f"Error saving annotation to database: {e}")

    def export_to_json(self, output_path: str):
        """
        Export reviews to JSON file.

        Args:
            output_path: Path to output file
        """
        output_data = {
            "reviewed_statements": [],
            "metadata": {
                "source_file": self.input_file_path,
                "review_date": datetime.now().isoformat(),
                "total_statements": len(self.results),
                "reviewed_count": sum(1 for r in self.reviews if r.get('human_annotation')),
                "annotator": self.annotator_username
            }
        }

        for i, result in enumerate(self.results):
            review = self.reviews[i] if i < len(self.reviews) else {}

            reviewed_item = {
                "statement": result.get('statement'),
                "original_annotation": result.get('expected_answer'),
                "ai_annotation": result.get('evaluation'),
                "ai_rationale": result.get('reason'),
                "human_annotation": review.get('human_annotation', ''),
                "human_explanation": review.get('human_explanation', ''),
                "evidence_count": len(result.get('evidence_list', [])),
                "matches_expected": result.get('matches_expected')
            }

            # Include input statement ID if present
            if 'input_statement_id' in result:
                reviewed_item['input_statement_id'] = result['input_statement_id']

            output_data["reviewed_statements"].append(reviewed_item)

        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

    def get_default_output_path(self) -> str:
        """Generate default output file path."""
        if self.input_file_path:
            input_path = Path(self.input_file_path)
            return str(input_path.parent / f"{input_path.stem}_annotated.json")
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"fact_check_annotated_{timestamp}.json"

    def get_reviewed_count(self) -> int:
        """Get count of reviewed statements."""
        return sum(1 for r in self.reviews if r.get('human_annotation'))
