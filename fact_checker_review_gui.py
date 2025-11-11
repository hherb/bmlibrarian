#!/usr/bin/env python3
"""
Fact-Checker Review GUI for BMLibrarian

A graphical interface for human reviewers to annotate and review fact-checking results.
Built using the Flet framework, this application allows reviewers to:
- Load fact-check results from JSON files
- Review each statement with original and AI-generated annotations
- Provide human annotations with explanations
- View supporting citations for each statement
- Export reviewed annotations to a new JSON file
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import flet as ft

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from bmlibrarian.gui.citation_card_utils import extract_citation_data, create_citation_metadata, create_citation_publication_info
    from bmlibrarian.gui.text_highlighting import create_highlighted_abstract
    from bmlibrarian.gui.ui_builder import create_expandable_card, create_relevance_badge, create_metadata_section, create_text_content_section, truncate_text, format_authors_list
    GUI_UTILS_AVAILABLE = True
except ImportError:
    GUI_UTILS_AVAILABLE = False

# Database imports for fetching full abstracts
try:
    from bmlibrarian.database import get_db_manager
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# Fact-checker database imports
try:
    from bmlibrarian.agents.fact_checker_db import FactCheckerDB, HumanAnnotation, Annotator
    FACT_CHECKER_DB_AVAILABLE = True
except ImportError:
    FACT_CHECKER_DB_AVAILABLE = False


# Fallback helper functions if GUI utils not available
def _truncate_text_fallback(text: str, max_length: int) -> str:
    """Fallback text truncation function."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def _create_simple_badge_fallback(text: str, color: str) -> ft.Container:
    """Fallback badge creation function."""
    return ft.Container(
        content=ft.Text(text, size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE, selectable=True),
        bgcolor=color,
        padding=ft.padding.symmetric(horizontal=8, vertical=4),
        border_radius=12
    )


class FactCheckerReviewGUI:
    """Main application for reviewing fact-check results."""

    def __init__(self, input_file: Optional[str] = None):
        self.page: Optional[ft.Page] = None
        self.results: List[Dict[str, Any]] = []
        self.current_index: int = 0
        self.reviews: List[Dict[str, Any]] = []
        self.input_file_path: str = ""
        self.initial_input_file: Optional[str] = input_file  # File provided via command line
        self.db_manager = None  # PostgreSQL database manager for fetching abstracts

        # Fact-checker database (SQLite)
        self.fact_checker_db: Optional[FactCheckerDB] = None
        self.db_path: Optional[str] = None
        self.using_database: bool = False

        # Annotator information
        self.annotator_id: Optional[int] = None
        self.annotator_username: Optional[str] = None

        # UI components
        self.file_path_text = None
        self.statement_counter = None
        self.statement_text = None
        self.original_annotation = None
        self.ai_annotation = None
        self.ai_rationale = None
        self.human_annotation_dropdown = None
        self.human_explanation = None
        self.citations_list = None
        self.prev_button = None
        self.next_button = None
        self.save_button = None
        self.progress_bar = None
        self.annotator_label = None  # Display current annotator

    def main(self, page: ft.Page):
        """Main application entry point."""
        self.page = page
        self._setup_page()
        self._build_ui()

        # Initialize database manager if available
        if DB_AVAILABLE:
            self._init_database_manager()

        # Show annotator dialog at startup
        self._show_annotator_dialog()

        # If input file was provided via command line, load it after annotator is set
        if self.initial_input_file:
            # Delay loading until annotator is set
            pass  # Will be loaded after annotator dialog is closed

    def _show_annotator_dialog(self):
        """Show dialog to enter annotator information at startup."""
        username_field = ft.TextField(
            label="Your Username/ID *",
            hint_text="e.g., jsmith",
            width=300,
            autofocus=True
        )

        full_name_field = ft.TextField(
            label="Full Name (optional)",
            hint_text="e.g., John Smith",
            width=300
        )

        email_field = ft.TextField(
            label="Email (optional)",
            hint_text="e.g., john@example.com",
            width=300
        )

        expertise_dropdown = ft.Dropdown(
            label="Expertise Level (optional)",
            options=[
                ft.dropdown.Option("expert", "Expert"),
                ft.dropdown.Option("intermediate", "Intermediate"),
                ft.dropdown.Option("novice", "Novice")
            ],
            width=300
        )

        def on_continue(e):
            if not username_field.value:
                username_field.error_text = "Username is required"
                self.page.update()
                return

            self.annotator_username = username_field.value

            # Store annotator info (will be saved to database when loading a database)
            self.annotator_info = {
                'username': username_field.value,
                'full_name': full_name_field.value or None,
                'email': email_field.value or None,
                'expertise_level': expertise_dropdown.value or None
            }

            # Update UI to show annotator
            if self.annotator_label:
                self.annotator_label.value = f"Annotator: {self.annotator_username}"
                self.page.update()

            dialog.open = False
            self.page.update()

            # Load initial file if provided
            if self.initial_input_file:
                self._load_fact_check_results(self.initial_input_file)

        dialog = ft.AlertDialog(
            title=ft.Text("Annotator Information", size=20, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(
                        "Please enter your information for annotation tracking:",
                        size=13,
                        color=ft.Colors.GREY_700
                    ),
                    ft.Container(height=15),
                    username_field,
                    full_name_field,
                    email_field,
                    expertise_dropdown
                ], tight=True),
                padding=ft.padding.all(10),
                width=400
            ),
            actions=[
                ft.ElevatedButton(
                    "Continue",
                    on_click=on_continue,
                    bgcolor=ft.Colors.BLUE_700,
                    color=ft.Colors.WHITE
                )
            ],
            modal=True
        )

        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _init_database_manager(self):
        """Initialize PostgreSQL database manager for fetching full abstracts."""
        try:
            self.db_manager = get_db_manager()
            print("✓ PostgreSQL database manager initialized successfully")
        except Exception as e:
            print(f"Warning: Could not initialize PostgreSQL database manager: {e}")
            self.db_manager = None

    def _fetch_document_abstract(self, document_id: str) -> Optional[str]:
        """Fetch full abstract from database by document ID."""
        if not self.db_manager or not document_id:
            return None

        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT abstract FROM document WHERE id = %s",
                        (document_id,)
                    )
                    result = cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            print(f"Error fetching abstract for document {document_id}: {e}")
            return None

    def _fetch_abstract_by_pmid(self, pmid: str) -> Optional[str]:
        """Fetch full abstract from database using PMID (stored as external_id)."""
        if not self.db_manager:
            print(f"DEBUG: No database manager available")
            return None

        if not pmid:
            print(f"DEBUG: No PMID provided")
            return None

        # Clean PMID (remove 'PMID:' prefix if present)
        clean_pmid = pmid.replace('PMID:', '').replace('pmid:', '').strip()
        print(f"DEBUG: Fetching abstract for PMID: {pmid} -> cleaned: {clean_pmid}")

        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    # PMID is stored in external_id for PubMed documents
                    cursor.execute(
                        "SELECT abstract FROM document WHERE external_id = %s",
                        (clean_pmid,)
                    )
                    result = cursor.fetchone()
                    if result and result[0]:
                        print(f"DEBUG: Abstract found for {clean_pmid}: {len(result[0])} chars")
                        return result[0]
                    else:
                        print(f"DEBUG: No abstract found for PMID {clean_pmid}")
                        return None
        except Exception as e:
            print(f"Error fetching abstract for PMID {pmid}: {e}")
            return None

    def _fetch_abstract_by_doi(self, doi: str) -> Optional[str]:
        """Fetch full abstract from database using DOI (stored in doi column for PubMed)."""
        if not self.db_manager:
            print(f"DEBUG: No database manager available")
            return None

        if not doi:
            print(f"DEBUG: No DOI provided")
            return None

        # Clean DOI (remove 'DOI:' prefix if present)
        clean_doi = doi.replace('DOI:', '').replace('doi:', '').strip()
        print(f"DEBUG: Fetching abstract for DOI: {doi} -> cleaned: {clean_doi}")

        try:
            with self.db_manager.get_connection() as conn:
                with conn.cursor() as cursor:
                    # DOI is stored in the 'doi' column for PubMed articles
                    cursor.execute(
                        "SELECT abstract FROM document WHERE doi = %s",
                        (clean_doi,)
                    )
                    result = cursor.fetchone()
                    if result and result[0]:
                        print(f"DEBUG: Abstract found for {clean_doi}: {len(result[0])} chars")
                        return result[0]
                    else:
                        print(f"DEBUG: No abstract found for DOI {clean_doi}")
                        return None
        except Exception as e:
            print(f"Error fetching abstract for DOI {doi}: {e}")
            return None

    def _enrich_evidence_with_identifiers(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich evidence with missing identifiers by looking up in database.

        For legacy data that only has DOI, fetch the PMID and document_id from database.
        This allows abstract fetching to work with older fact-check results.
        """
        if not self.db_manager:
            return evidence

        # If we already have document_id and pmid, no need to enrich
        if evidence.get('document_id') and evidence.get('pmid'):
            return evidence

        # Try to enrich using DOI
        doi = evidence.get('doi', '')
        if doi:
            clean_doi = doi.replace('DOI:', '').replace('doi:', '').strip()
            try:
                with self.db_manager.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT id, external_id FROM document WHERE doi = %s",
                            (clean_doi,)
                        )
                        result = cursor.fetchone()
                        if result:
                            # Add document_id and pmid to evidence
                            if not evidence.get('document_id'):
                                evidence['document_id'] = str(result[0])
                                print(f"DEBUG: Enriched evidence with document_id: {result[0]}")
                            if not evidence.get('pmid') and result[1]:
                                evidence['pmid'] = f"PMID:{result[1]}"
                                print(f"DEBUG: Enriched evidence with PMID: {result[1]}")
            except Exception as e:
                print(f"Warning: Could not enrich evidence with identifiers: {e}")

        return evidence

    def _setup_page(self):
        """Configure the main page settings."""
        self.page.title = "BMLibrarian Fact-Checker Review"
        self.page.window.width = 1400
        self.page.window.height = 900
        self.page.window.min_width = 1200
        self.page.window.min_height = 700
        self.page.window.resizable = True
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.padding = 20
        self.page.scroll = ft.ScrollMode.AUTO

    def _build_ui(self):
        """Build the main user interface."""
        # Header
        header = ft.Container(
            content=ft.Column([
                ft.Text(
                    "Fact-Checker Review Interface",
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_900
                ),
                ft.Text(
                    "Review and annotate AI-generated fact-checking results",
                    size=14,
                    color=ft.Colors.GREY_700
                )
            ], spacing=5),
            padding=ft.padding.only(bottom=20)
        )

        # File selection section
        self.file_path_text = ft.Text(
            "No file loaded",
            size=12,
            color=ft.Colors.GREY_600,
            italic=True
        )

        file_section = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.ElevatedButton(
                        "Load Fact-Check Results",
                        icon=ft.Icons.FOLDER_OPEN,
                        on_click=self._on_load_file,
                        bgcolor=ft.Colors.BLUE_600,
                        color=ft.Colors.WHITE
                    ),
                    self.file_path_text
                ], spacing=15, alignment=ft.MainAxisAlignment.START)
            ]),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.BLUE_50,
            border_radius=10
        )

        # Review content (initially hidden)
        self.review_content = self._build_review_content()
        self.review_content.visible = False

        # Main layout
        main_content = ft.Column([
            header,
            file_section,
            ft.Container(height=20),
            self.review_content
        ], spacing=0, expand=True, scroll=ft.ScrollMode.AUTO)

        self.page.add(main_content)

    def _build_review_content(self) -> ft.Container:
        """Build the statement review interface."""
        # Progress section
        self.statement_counter = ft.Text(
            "Statement 0 of 0",
            size=14,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_900
        )

        self.progress_bar = ft.ProgressBar(
            value=0,
            width=400,
            color=ft.Colors.BLUE_600,
            bgcolor=ft.Colors.BLUE_100
        )

        progress_section = ft.Row([
            self.statement_counter,
            self.progress_bar
        ], spacing=20, alignment=ft.MainAxisAlignment.START)

        # Statement section
        self.statement_text = ft.Text(
            "",
            size=16,
            weight=ft.FontWeight.W_500,
            selectable=True
        )

        statement_section = ft.Container(
            content=ft.Column([
                ft.Text("Statement:", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_700),
                self.statement_text
            ], spacing=8),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.GREY_50,
            border_radius=8,
            border=ft.border.all(1, ft.Colors.GREY_300)
        )

        # Annotations section (3 columns)
        self.original_annotation = self._create_annotation_display(
            "Original Annotation",
            ft.Colors.PURPLE_100,
            ft.Colors.PURPLE_700
        )

        self.ai_annotation = self._create_annotation_display(
            "AI Fact-Checker",
            ft.Colors.BLUE_100,
            ft.Colors.BLUE_700
        )

        self.ai_rationale = ft.Text(
            "",
            size=12,
            color=ft.Colors.GREY_800,
            selectable=True
        )

        # Human annotation section
        self.human_annotation_dropdown = ft.Dropdown(
            label="Your Annotation",
            options=[
                ft.dropdown.Option("yes", "Yes"),
                ft.dropdown.Option("no", "No"),
                ft.dropdown.Option("maybe", "Maybe"),
                ft.dropdown.Option("", "-- Select --")
            ],
            value="",
            width=200,
            on_change=self._on_annotation_change
        )

        self.human_explanation = ft.TextField(
            label="Explanation for your annotation (optional)",
            multiline=True,
            min_lines=2,
            max_lines=4,
            on_change=self._on_explanation_change
        )

        human_annotation_section = ft.Container(
            content=ft.Column([
                ft.Text("Human Review", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700),
                self.human_annotation_dropdown,
                self.human_explanation
            ], spacing=10),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.GREEN_50,
            border_radius=8,
            border=ft.border.all(2, ft.Colors.GREEN_300)
        )

        # Annotations row
        annotations_row = ft.Row([
            ft.Container(
                content=self.original_annotation,
                expand=1
            ),
            ft.Container(
                content=ft.Column([
                    self.ai_annotation,
                    ft.Container(height=10),
                    ft.Container(
                        content=ft.Column([
                            ft.Text("AI Rationale:", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_700),
                            self.ai_rationale
                        ], spacing=5),
                        padding=ft.padding.all(10),
                        bgcolor=ft.Colors.GREY_50,
                        border_radius=5
                    )
                ], spacing=0),
                expand=1
            ),
            ft.Container(
                content=human_annotation_section,
                expand=1
            )
        ], spacing=15)

        # Citations section
        self.citations_list = ft.Column(
            controls=[],
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        )

        citations_section = ft.Container(
            content=ft.Column([
                ft.Text(
                    "Supporting Citations",
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.GREY_900
                ),
                ft.Container(
                    content=self.citations_list,
                    height=300,
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=8,
                    padding=ft.padding.all(10)
                )
            ], spacing=10),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.ORANGE_50,
            border_radius=8,
            border=ft.border.all(1, ft.Colors.ORANGE_200)
        )

        # Navigation buttons
        self.prev_button = ft.ElevatedButton(
            "Previous",
            icon=ft.Icons.ARROW_BACK,
            on_click=self._on_previous,
            disabled=True
        )

        self.next_button = ft.ElevatedButton(
            "Next",
            icon=ft.Icons.ARROW_FORWARD,
            on_click=self._on_next,
            disabled=True
        )

        self.save_button = ft.ElevatedButton(
            "Save Reviews",
            icon=ft.Icons.SAVE,
            on_click=self._on_save_reviews,
            bgcolor=ft.Colors.GREEN_700,
            color=ft.Colors.WHITE
        )

        navigation_section = ft.Row([
            self.prev_button,
            self.next_button,
            ft.Container(expand=True),
            self.save_button
        ], spacing=10, alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        # Combine all sections
        return ft.Container(
            content=ft.Column([
                progress_section,
                ft.Container(height=10),
                statement_section,
                ft.Container(height=15),
                annotations_row,
                ft.Container(height=15),
                citations_section,
                ft.Container(height=20),
                navigation_section
            ], spacing=0),
            padding=ft.padding.all(20),
            bgcolor=ft.Colors.WHITE,
            border_radius=10,
            border=ft.border.all(1, ft.Colors.GREY_300)
        )

    def _create_annotation_display(self, title: str, bg_color: str, text_color: str) -> ft.Column:
        """Create a standardized annotation display component."""
        annotation_badge = ft.Container(
            content=ft.Text(
                "--",
                size=14,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.WHITE
            ),
            padding=ft.padding.symmetric(horizontal=20, vertical=8),
            bgcolor=text_color,
            border_radius=20,
            alignment=ft.alignment.center
        )

        return ft.Column([
            ft.Text(title, size=12, weight=ft.FontWeight.BOLD, color=text_color),
            annotation_badge
        ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    def _on_load_file(self, e):
        """Handle load file button click."""
        def on_file_result(file_picker_result: ft.FilePickerResultEvent):
            if file_picker_result.files and len(file_picker_result.files) > 0:
                file_path = file_picker_result.files[0].path
                self._load_fact_check_results(file_path)

        # Create file picker
        file_picker = ft.FilePicker(on_result=on_file_result)
        self.page.overlay.append(file_picker)
        self.page.update()

        # Open file picker dialog
        file_picker.pick_files(
            dialog_title="Select Fact-Check Results (Database or JSON)",
            allowed_extensions=["db", "json"],
            allow_multiple=False
        )

    def _load_fact_check_results(self, file_path: str):
        """Load fact-check results from database (.db) or JSON file (.json)."""
        try:
            file_path_obj = Path(file_path)

            # Check if it's a database file
            if file_path_obj.suffix.lower() == '.db':
                if not FACT_CHECKER_DB_AVAILABLE:
                    raise ValueError("Fact-checker database module not available")
                self._load_from_database(file_path)
            elif file_path_obj.suffix.lower() == '.json':
                self._load_from_json(file_path)
            else:
                raise ValueError(f"Unsupported file type: {file_path_obj.suffix}. Use .db or .json")

        except Exception as ex:
            self._show_error_dialog(f"Error loading file: {str(ex)}")

    def _load_from_database(self, db_path: str):
        """Load results from SQLite database."""
        self.fact_checker_db = FactCheckerDB(db_path)
        self.db_path = db_path
        self.using_database = True

        # Register or get annotator ID
        if hasattr(self, 'annotator_info'):
            annotator = Annotator(**self.annotator_info)
            self.annotator_id = self.fact_checker_db.insert_or_get_annotator(annotator)
            print(f"✓ Annotator registered: {self.annotator_username} (ID: {self.annotator_id})")

        # Load all statements with evaluations
        all_data = self.fact_checker_db.get_all_statements_with_evaluations()

        if not all_data:
            raise ValueError("No statements found in database")

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

        # Update UI
        self.input_file_path = db_path
        self.file_path_text.value = f"Database: {Path(db_path).name} ({len(self.results)} statements)"
        self.file_path_text.italic = False
        self.file_path_text.color = ft.Colors.BLUE_700

        # Show review interface
        self.current_index = 0
        self.review_content.visible = True
        self._display_current_statement()

        self.page.update()

    def _load_from_json(self, json_path: str):
        """Load results from legacy JSON file."""
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

        # Initialize reviews list
        self.reviews = [{}] * len(self.results)
        self.using_database = False

        # Update UI
        self.input_file_path = json_path
        self.file_path_text.value = f"JSON: {Path(json_path).name} ({len(self.results)} statements)"
        self.file_path_text.italic = False
        self.file_path_text.color = ft.Colors.GREEN_700

        # Show review interface
        self.current_index = 0
        self.review_content.visible = True
        self._display_current_statement()

        self.page.update()

    def _display_current_statement(self):
        """Display the current statement and its annotations."""
        if not self.results or self.current_index >= len(self.results):
            return

        result = self.results[self.current_index]

        # Update progress
        self.statement_counter.value = f"Statement {self.current_index + 1} of {len(self.results)}"
        self.progress_bar.value = (self.current_index + 1) / len(self.results)

        # Update statement
        self.statement_text.value = result.get('statement', 'N/A')

        # Update original annotation
        expected_answer = result.get('expected_answer', 'N/A')
        self._update_annotation_badge(self.original_annotation, expected_answer)

        # Update AI annotation
        ai_evaluation = result.get('evaluation', 'N/A')
        self._update_annotation_badge(self.ai_annotation, ai_evaluation)

        # Update AI rationale
        self.ai_rationale.value = result.get('reason', 'No rationale provided')

        # Update human annotation from saved review (if exists)
        saved_review = self.reviews[self.current_index]
        self.human_annotation_dropdown.value = saved_review.get('human_annotation', '')
        self.human_explanation.value = saved_review.get('human_explanation', '')

        # Update citations
        self._display_citations(result.get('evidence_list', []))

        # Update navigation buttons
        self.prev_button.disabled = (self.current_index == 0)
        self.next_button.disabled = (self.current_index == len(self.results) - 1)

        self.page.update()

    def _update_annotation_badge(self, annotation_column: ft.Column, value: str):
        """Update an annotation badge with the given value."""
        # annotation_column has: [Text(title), Container(badge)]
        badge_container = annotation_column.controls[1]
        badge_text = badge_container.content

        # Update text and color based on value
        value_lower = str(value).lower()

        if value_lower == 'yes':
            badge_text.value = "YES ✓"
            badge_container.bgcolor = ft.Colors.GREEN_700
        elif value_lower == 'no':
            badge_text.value = "NO ✗"
            badge_container.bgcolor = ft.Colors.RED_700
        elif value_lower == 'maybe':
            badge_text.value = "MAYBE ?"
            badge_container.bgcolor = ft.Colors.ORANGE_700
        else:
            badge_text.value = str(value).upper()
            badge_container.bgcolor = ft.Colors.GREY_600

    def _display_citations(self, evidence_list: List[Dict[str, Any]]):
        """Display citations in the scrollable list with expandable cards."""
        self.citations_list.controls.clear()

        if not evidence_list:
            self.citations_list.controls.append(
                ft.Text("No citations available", size=12, color=ft.Colors.GREY_500, italic=True)
            )
            return

        for i, evidence in enumerate(evidence_list):
            # Enrich evidence with missing identifiers from database
            enriched_evidence = self._enrich_evidence_with_identifiers(evidence)

            if GUI_UTILS_AVAILABLE:
                # Use expandable citation cards with full abstract highlighting
                citation_card = self._create_expandable_citation_card(i, enriched_evidence)
            else:
                # Fallback to simple cards if GUI utils not available
                citation_card = self._create_simple_citation_card(i + 1, enriched_evidence)
            self.citations_list.controls.append(citation_card)

    def _create_expandable_citation_card(self, index: int, evidence: Dict[str, Any]) -> ft.ExpansionTile:
        """Create an expandable card for citation with full abstract and highlighting."""
        # Extract basic citation info
        citation_text = evidence.get('citation', 'No citation text available')
        pmid = evidence.get('pmid', '')
        doi = evidence.get('doi', '')
        document_id = evidence.get('document_id', '')
        relevance_score = evidence.get('relevance_score', 0)
        stance = evidence.get('stance', 'neutral')

        # Fetch full abstract from database
        # Try document_id first, then PMID, then DOI
        abstract = None
        if self.db_manager:
            if document_id:
                abstract = self._fetch_document_abstract(document_id)
            elif pmid:
                abstract = self._fetch_abstract_by_pmid(pmid)
            elif doi:
                abstract = self._fetch_abstract_by_doi(doi)

        # Determine stance styling
        if stance == 'supports':
            stance_badge_color = ft.Colors.GREEN_700
            stance_icon = "✓"
        elif stance == 'contradicts':
            stance_badge_color = ft.Colors.RED_700
            stance_icon = "✗"
        else:
            stance_badge_color = ft.Colors.GREY_600
            stance_icon = "?"

        # Create title with stance and relevance (use fallback if needed)
        truncated_citation = truncate_text(citation_text, 80) if GUI_UTILS_AVAILABLE else _truncate_text_fallback(citation_text, 80)
        title_text = f"{index + 1}. {truncated_citation}"

        # Create stance badge
        stance_badge = ft.Container(
            content=ft.Text(
                f"{stance_icon} {stance.upper()}",
                size=10,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.WHITE,
                selectable=True
            ),
            bgcolor=stance_badge_color,
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            border_radius=12
        )

        # Create relevance badge
        if GUI_UTILS_AVAILABLE:
            relevance_badge = create_relevance_badge(relevance_score)
        else:
            relevance_badge = _create_simple_badge_fallback(f"{relevance_score:.2f}", ft.Colors.BLUE_600)

        # Create subtitle with identifiers
        identifier_parts = []
        if pmid:
            identifier_parts.append(pmid)
        if doi:
            identifier_parts.append(doi)
        if document_id:
            identifier_parts.append(f"Doc: {document_id}")
        subtitle_text = " | ".join(identifier_parts) if identifier_parts else "No identifier"

        # Create content sections
        content_sections = []

        # Metadata section
        metadata_items = [
            ("Stance", stance.capitalize()),
            ("Relevance Score", f"{relevance_score:.3f}" if relevance_score else "N/A"),
        ]
        if pmid:
            metadata_items.append(("PMID", pmid))
        if doi:
            metadata_items.append(("DOI", doi))
        if document_id:
            metadata_items.append(("Document ID", document_id))

        if GUI_UTILS_AVAILABLE:
            content_sections.append(create_metadata_section(metadata_items, ft.Colors.BLUE_50))
        else:
            # Fallback metadata display
            metadata_text = "\n".join([f"{k}: {v}" for k, v in metadata_items])
            content_sections.append(ft.Container(
                content=ft.Text(metadata_text, size=10, selectable=True),
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.BLUE_50,
                border_radius=5
            ))

        # Citation passage section
        if GUI_UTILS_AVAILABLE:
            content_sections.append(create_text_content_section(
                "Extracted Citation:",
                citation_text,
                ft.Colors.YELLOW_100
            ))
        else:
            # Fallback citation display
            content_sections.append(ft.Container(
                content=ft.Column([
                    ft.Text("Extracted Citation:", size=10, weight=ft.FontWeight.BOLD),
                    ft.Text(citation_text, size=11, selectable=True)
                ], spacing=5),
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.YELLOW_100,
                border_radius=5
            ))

        # Abstract with highlighting if available
        if abstract:
            if GUI_UTILS_AVAILABLE:
                content_sections.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Text("Full Abstract with Highlighted Citation:",
                                   size=10, weight=ft.FontWeight.BOLD),
                            create_highlighted_abstract(abstract, citation_text)
                        ], spacing=5),
                        padding=ft.padding.all(10),
                        bgcolor=ft.Colors.GREY_50,
                        border_radius=5,
                        border=ft.border.all(1, ft.Colors.GREY_300)
                    )
                )
            else:
                # Fallback: show abstract without highlighting
                content_sections.append(ft.Container(
                    content=ft.Column([
                        ft.Text("Full Abstract:", size=10, weight=ft.FontWeight.BOLD),
                        ft.Text(abstract, size=11, selectable=True)
                    ], spacing=5),
                    padding=ft.padding.all(10),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=5
                ))
        else:
            # Show info about missing abstract
            content_sections.append(
                ft.Container(
                    content=ft.Text(
                        "ℹ️ Full abstract not available" + (" (database not connected)" if not self.db_manager else ""),
                        size=10,
                        color=ft.Colors.GREY_600,
                        italic=True
                    ),
                    padding=ft.padding.all(10)
                )
            )

        # Create expandable card
        if GUI_UTILS_AVAILABLE:
            return create_expandable_card(
                title_text,
                subtitle_text,
                content_sections,
                [stance_badge, relevance_badge]
            )
        else:
            # Fallback: create simple ExpansionTile
            return ft.ExpansionTile(
                title=ft.Row([
                    ft.Text(title_text, size=12, weight=ft.FontWeight.W_500),
                    stance_badge,
                    relevance_badge
                ], spacing=10),
                subtitle=ft.Text(subtitle_text, size=11, color=ft.Colors.GREY_600),
                controls=[
                    ft.Container(
                        content=ft.Column(content_sections, spacing=10),
                        padding=ft.padding.all(10)
                    )
                ]
            )

    def _create_simple_citation_card(self, index: int, evidence: Dict[str, Any]) -> ft.Container:
        """Create a card for displaying a single citation."""
        # Get stance color
        stance = evidence.get('stance', 'neutral')
        if stance == 'supports':
            stance_color = ft.Colors.GREEN_100
            stance_border = ft.Colors.GREEN_500
            stance_icon = ft.Icons.CHECK_CIRCLE
            stance_icon_color = ft.Colors.GREEN_700
        elif stance == 'contradicts':
            stance_color = ft.Colors.RED_100
            stance_border = ft.Colors.RED_500
            stance_icon = ft.Icons.CANCEL
            stance_icon_color = ft.Colors.RED_700
        else:
            stance_color = ft.Colors.GREY_100
            stance_border = ft.Colors.GREY_400
            stance_icon = ft.Icons.HELP_OUTLINE
            stance_icon_color = ft.Colors.GREY_700

        # Get identifiers
        pmid = evidence.get('pmid', '')
        doi = evidence.get('doi', '')
        relevance_score = evidence.get('relevance_score')

        identifier_text = []
        if pmid:
            identifier_text.append(pmid)
        if doi:
            identifier_text.append(doi)
        if relevance_score is not None:
            identifier_text.append(f"Score: {relevance_score:.1f}/5.0")

        identifier_str = " | ".join(identifier_text) if identifier_text else "No identifier"

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(stance_icon, color=stance_icon_color, size=20),
                    ft.Text(
                        f"Citation {index}",
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.GREY_900
                    ),
                    ft.Container(
                        content=ft.Text(
                            stance.upper(),
                            size=10,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.WHITE
                        ),
                        bgcolor=stance_border,
                        padding=ft.padding.symmetric(horizontal=8, vertical=2),
                        border_radius=10
                    )
                ], spacing=10),
                ft.Text(
                    identifier_str,
                    size=10,
                    color=ft.Colors.GREY_600,
                    italic=True
                ),
                ft.Container(height=5),
                ft.Text(
                    evidence.get('citation', 'No citation text available'),
                    size=12,
                    color=ft.Colors.GREY_800,
                    selectable=True
                )
            ], spacing=5),
            padding=ft.padding.all(12),
            bgcolor=stance_color,
            border_radius=8,
            border=ft.border.all(1, stance_border)
        )

    def _on_annotation_change(self, e):
        """Handle human annotation selection change."""
        if not self.reviews:
            return

        if 'human_annotation' not in self.reviews[self.current_index]:
            self.reviews[self.current_index] = {}

        self.reviews[self.current_index]['human_annotation'] = self.human_annotation_dropdown.value

        # Save to database immediately if using database mode
        if self.using_database:
            self._save_current_annotation_to_database()

    def _on_explanation_change(self, e):
        """Handle human explanation text change."""
        if not self.reviews:
            return

        if 'human_explanation' not in self.reviews[self.current_index]:
            self.reviews[self.current_index] = {}

        self.reviews[self.current_index]['human_explanation'] = self.human_explanation.value

        # Save to database immediately if using database mode
        if self.using_database:
            self._save_current_annotation_to_database()

    def _save_current_annotation_to_database(self):
        """Save the current annotation to the database."""
        if not self.fact_checker_db or not self.annotator_id:
            return

        try:
            result = self.results[self.current_index]
            review = self.reviews[self.current_index]

            # Only save if there's an annotation
            if not review.get('human_annotation'):
                return

            statement_id = result.get('statement_id')
            if not statement_id:
                return

            annotation = HumanAnnotation(
                statement_id=statement_id,
                annotator_id=self.annotator_id,
                annotation=review.get('human_annotation', ''),
                explanation=review.get('human_explanation', ''),
                confidence=None,  # Could add confidence selection in future
                session_id=f"gui_session_{datetime.now().strftime('%Y%m%d')}"
            )

            self.fact_checker_db.insert_human_annotation(annotation)
            print(f"✓ Saved annotation for statement {statement_id}")

        except Exception as e:
            print(f"Error saving annotation to database: {e}")

    def _on_previous(self, e):
        """Navigate to previous statement."""
        if self.current_index > 0:
            self.current_index -= 1
            self._display_current_statement()

    def _on_next(self, e):
        """Navigate to next statement."""
        if self.current_index < len(self.results) - 1:
            self.current_index += 1
            self._display_current_statement()

    def _on_save_reviews(self, e):
        """Save human reviews - to database or JSON file."""
        if not self.results:
            self._show_error_dialog("No results to save")
            return

        if self.using_database:
            # Database mode - annotations are saved automatically, just show confirmation
            reviewed_count = sum(1 for r in self.reviews if r.get('human_annotation'))
            self._show_success_dialog(
                f"✓ All annotations saved to database\n\n"
                f"Total statements: {len(self.results)}\n"
                f"Reviewed by you: {reviewed_count}\n"
                f"Database: {Path(self.db_path).name}"
            )
        else:
            # JSON mode - show save dialog
            save_path_field = ft.TextField(
                label="Output file path",
                value=self._get_default_output_path(),
                width=500
            )

            def on_save_confirm(e):
                output_path = save_path_field.value
                if output_path:
                    self._save_reviews_to_file(output_path)
                    dialog.open = False
                    self.page.update()

            def on_cancel(e):
                dialog.open = False
                self.page.update()

            dialog = ft.AlertDialog(
                title=ft.Text("Save Reviewed Annotations"),
                content=ft.Container(
                    content=save_path_field,
                    padding=ft.padding.all(10)
                ),
                actions=[
                    ft.TextButton("Cancel", on_click=on_cancel),
                    ft.ElevatedButton(
                        "Save",
                        on_click=on_save_confirm,
                        bgcolor=ft.Colors.GREEN_700,
                        color=ft.Colors.WHITE
                    )
                ]
            )

            self.page.overlay.append(dialog)
            dialog.open = True
            self.page.update()

    def _get_default_output_path(self) -> str:
        """Generate default output file path."""
        if self.input_file_path:
            input_path = Path(self.input_file_path)
            return str(input_path.parent / f"{input_path.stem}_annotated.json")
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"fact_check_annotated_{timestamp}.json"

    def _save_reviews_to_file(self, output_path: str):
        """Save reviews to JSON file."""
        try:
            # Combine results with reviews
            output_data = {
                "reviewed_statements": [],
                "metadata": {
                    "source_file": self.input_file_path,
                    "review_date": datetime.now().isoformat(),
                    "total_statements": len(self.results),
                    "reviewed_count": sum(1 for r in self.reviews if r.get('human_annotation'))
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

            self._show_success_dialog(f"Reviews saved successfully to:\n{output_path}")

        except Exception as ex:
            self._show_error_dialog(f"Error saving reviews: {str(ex)}")

    def _show_error_dialog(self, message: str):
        """Show error dialog."""
        dialog = ft.AlertDialog(
            title=ft.Text("Error", color=ft.Colors.RED_700),
            content=ft.Text(message),
            actions=[
                ft.TextButton("OK", on_click=lambda e: self._close_dialog(dialog))
            ]
        )
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _show_success_dialog(self, message: str):
        """Show success dialog."""
        dialog = ft.AlertDialog(
            title=ft.Text("Success", color=ft.Colors.GREEN_700),
            content=ft.Text(message),
            actions=[
                ft.TextButton("OK", on_click=lambda e: self._close_dialog(dialog))
            ]
        )
        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()

    def _close_dialog(self, dialog):
        """Close a dialog."""
        dialog.open = False
        self.page.update()


def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        description="BMLibrarian Fact-Checker Review GUI - Human annotation interface for fact-checking results"
    )
    parser.add_argument(
        "--input-file",
        type=str,
        help="Path to the input fact-check results JSON file (workaround for macOS file picker bug)"
    )

    args = parser.parse_args()

    # Validate input file if provided
    if args.input_file:
        input_path = Path(args.input_file)
        if not input_path.exists():
            print(f"Error: Input file not found: {args.input_file}")
            return
        if not input_path.suffix.lower() == '.json':
            print(f"Error: Input file must be a JSON file: {args.input_file}")
            return

    app = FactCheckerReviewGUI(input_file=args.input_file)
    ft.app(target=app.main)


if __name__ == "__main__":
    main()
