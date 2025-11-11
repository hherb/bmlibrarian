"""
Main application for Fact Checker Review GUI.

Orchestrates all components for reviewing and annotating fact-check results.
"""

from typing import Optional
from pathlib import Path
import flet as ft

from .dialogs import AnnotatorDialog, show_error_dialog, show_success_dialog, show_save_dialog
from .data_manager import FactCheckDataManager
from .statement_display import StatementDisplay
from .annotation_manager import AnnotationManager
from .citation_display import CitationDisplay


class FactCheckerReviewApp:
    """Main application for reviewing fact-check results."""

    def __init__(self, input_file: Optional[str] = None, incremental: bool = False):
        """
        Initialize the review application.

        Args:
            input_file: Optional input file path provided via command line
            incremental: If True, only show unevaluated statements
        """
        self.page: Optional[ft.Page] = None
        self.initial_input_file = input_file
        self.incremental = incremental
        self.current_index = 0

        # Initialize components
        self.data_manager = FactCheckDataManager(incremental=incremental)
        self.statement_display = StatementDisplay()
        self.annotation_manager = AnnotationManager(on_annotation_change=self._on_annotation_change)
        self.citation_display = CitationDisplay()

        # UI components
        self.file_path_text = None
        self.citations_list = None
        self.prev_button = None
        self.next_button = None
        self.save_button = None
        self.review_content = None

    def main(self, page: ft.Page):
        """Main application entry point."""
        self.page = page
        self._setup_page()
        self._build_ui()

        # Show annotator dialog at startup
        annotator_dialog = AnnotatorDialog(self.page, self._on_annotator_complete)
        annotator_dialog.show()

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
        progress_section = self.statement_display.build_progress_section()

        # Statement section
        statement_section = self.statement_display.build_statement_section()

        # Annotations section
        human_annotation_section = self.annotation_manager.build_section()
        annotations_row = self.statement_display.build_annotations_section(human_annotation_section)

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

    def _on_annotator_complete(self, annotator_info: dict):
        """
        Handle annotator dialog completion.

        Args:
            annotator_info: Annotator information dictionary
        """
        self.data_manager.set_annotator(annotator_info)

        # Load initial file if provided
        if self.initial_input_file:
            self._load_fact_check_results(self.initial_input_file)

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
        """Load fact-check results from database or JSON file."""
        try:
            file_path_obj = Path(file_path)

            # Check if it's a database file
            if file_path_obj.suffix.lower() == '.db':
                self.data_manager.load_from_database(file_path)
                file_type = "Database"
                file_color = ft.Colors.BLUE_700
            elif file_path_obj.suffix.lower() == '.json':
                self.data_manager.load_from_json(file_path)
                file_type = "JSON"
                file_color = ft.Colors.GREEN_700
            else:
                raise ValueError(f"Unsupported file type: {file_path_obj.suffix}. Use .db or .json")

            # Update UI
            mode_indicator = " [INCREMENTAL MODE]" if self.incremental else ""
            self.file_path_text.value = f"{file_type}: {file_path_obj.name} ({len(self.data_manager.results)} statements){mode_indicator}"
            self.file_path_text.italic = False
            self.file_path_text.color = file_color

            # Show review interface
            self.current_index = 0
            self.review_content.visible = True
            self._display_current_statement()

            self.page.update()

        except Exception as ex:
            show_error_dialog(self.page, f"Error loading file: {str(ex)}")

    def _display_current_statement(self):
        """Display the current statement and its annotations."""
        if not self.data_manager.results or self.current_index >= len(self.data_manager.results):
            return

        result = self.data_manager.results[self.current_index]

        # Update progress
        self.statement_display.update_progress(self.current_index, len(self.data_manager.results))

        # Update statement
        self.statement_display.update_statement(result.get('statement', 'N/A'))

        # Update annotations
        self.statement_display.update_annotations(
            result.get('expected_answer', 'N/A'),
            result.get('evaluation', 'N/A'),
            result.get('reason', 'No rationale provided')
        )

        # Update human annotation from saved review
        saved_review = self.data_manager.reviews[self.current_index]
        self.annotation_manager.set_annotation(
            saved_review.get('human_annotation', ''),
            saved_review.get('human_explanation', '')
        )

        # Update citations
        self._display_citations(result.get('evidence_list', []))

        # Update navigation buttons
        self.prev_button.disabled = (self.current_index == 0)
        self.next_button.disabled = (self.current_index == len(self.data_manager.results) - 1)

        self.page.update()

    def _display_citations(self, evidence_list: list):
        """Display citations in the scrollable list."""
        self.citations_list.controls.clear()

        citations_column = self.citation_display.create_citations_list(evidence_list)
        self.citations_list.controls = citations_column.controls

    def _on_annotation_change(self, annotation: str, explanation: str):
        """Handle annotation change event."""
        self.data_manager.save_annotation(self.current_index, annotation, explanation)

    def _on_previous(self, e):
        """Navigate to previous statement."""
        if self.current_index > 0:
            self.current_index -= 1
            self._display_current_statement()

    def _on_next(self, e):
        """Navigate to next statement."""
        if self.current_index < len(self.data_manager.results) - 1:
            self.current_index += 1
            self._display_current_statement()

    def _on_save_reviews(self, e):
        """Save human reviews - to database or JSON file."""
        if not self.data_manager.results:
            show_error_dialog(self.page, "No results to save")
            return

        if self.data_manager.using_database:
            # Database mode - annotations are saved automatically
            reviewed_count = self.data_manager.get_reviewed_count()
            show_success_dialog(
                self.page,
                f"✓ All annotations saved to database\n\n"
                f"Total statements: {len(self.data_manager.results)}\n"
                f"Reviewed by you: {reviewed_count}\n"
                f"Database: {Path(self.data_manager.db_path).name}"
            )
        else:
            # JSON mode - show save dialog
            default_path = self.data_manager.get_default_output_path()

            def do_save(output_path: str):
                try:
                    self.data_manager.export_to_json(output_path)
                    show_success_dialog(self.page, f"Reviews saved successfully to:\n{output_path}")
                except Exception as ex:
                    show_error_dialog(self.page, f"Error saving reviews: {str(ex)}")

            show_save_dialog(self.page, default_path, do_save)
