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

        # Database mode (always use PostgreSQL now)
        self.using_database: bool = True
        self.fact_checker_db: Optional[FactCheckerDB] = None

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

        # Register annotator in database
        if self.fact_checker_db:
            annotator = Annotator(**annotator_info)
            self.annotator_id = self.fact_checker_db.insert_or_get_annotator(annotator)
            print(f"✓ Annotator registered: {self.annotator_username} (ID: {self.annotator_id})")

    def load_from_database(self, skip_incremental_filter: bool = False):
        """
        Load results from PostgreSQL database.

        Args:
            skip_incremental_filter: If True, don't apply incremental filtering even if incremental mode is on
        """
        print(f"DEBUG: load_from_database called, incremental={self.incremental}, skip_filter={skip_incremental_filter}")
        self.fact_checker_db = FactCheckerDB()
        print(f"DEBUG: FactCheckerDB initialized")
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

        self.input_file_path = "PostgreSQL Database"

    def load_from_json(self, json_path: str):
        """
        Load results from JSON file and import into PostgreSQL database.

        Args:
            json_path: Path to JSON file
        """
        json_file = Path(json_path)

        print(f"ℹ️  Importing JSON data into PostgreSQL database...")

        # Create/connect to database
        self.fact_checker_db = FactCheckerDB()
        self.using_database = True

        # Import JSON data (intelligently merges with existing data)
        import_stats = self.fact_checker_db.import_json_results(
            json_file=str(json_path),
            skip_existing=True  # Don't overwrite existing evaluations/annotations
        )

        # Report import statistics
        print(f"✓ JSON import complete:")
        print(f"  - New statements added: {import_stats['new_statements']}")
        print(f"  - Existing statements skipped: {import_stats['skipped_existing']}")
        print(f"  - Total in JSON file: {import_stats['total_in_file']}")
        if import_stats['errors'] > 0:
            print(f"  - Errors: {import_stats['errors']}")

        # Now load from the database (which has all the data)
        # IMPORTANT: Skip incremental filtering when loading from JSON import
        # The user wants to see ALL statements (including ones they already annotated)
        # to verify the import worked correctly
        self.load_from_database(skip_incremental_filter=True)

        if self.incremental:
            print(f"ℹ️  Incremental mode: Showing ALL {len(self.results)} statements from JSON import (incremental filtering disabled for imports)")

    def save_annotation(self, index: int, annotation: str, explanation: str = ""):
        """
        Save annotation for a statement.

        Args:
            index: Statement index
            annotation: Annotation value (yes/no/maybe/unclear) or n/a to skip saving
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

                # Don't save if no statement_id or if annotation is empty/None/N/A
                # Valid annotations: 'yes', 'no', 'maybe', 'unclear' (per database constraint)
                if not statement_id or not annotation or annotation.lower() in ('n/a', 'na'):
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
