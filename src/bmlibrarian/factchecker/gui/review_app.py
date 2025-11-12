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

    def __init__(self, incremental: bool = False, default_username: Optional[str] = None, blind_mode: bool = False):
        """
        Initialize the review application.

        Args:
            incremental: If True, only show statements you haven't annotated yet
            default_username: If provided, use this username and skip login dialog
            blind_mode: If True, hide original and AI annotations from human annotator
        """
        self.page: Optional[ft.Page] = None
        self.incremental = incremental
        self.default_username = default_username
        self.blind_mode = blind_mode
        self.current_index = 0

        # Initialize components
        self.data_manager = FactCheckDataManager(incremental=incremental)
        self.statement_display = StatementDisplay(blind_mode=blind_mode)
        self.annotation_manager = AnnotationManager(on_annotation_change=self._on_annotation_change)
        self.citation_display = CitationDisplay()

        # UI components
        self.status_text = None
        self.citations_list = None
        self.prev_button = None
        self.next_button = None
        self.review_content = None

    def main(self, page: ft.Page):
        """Main application entry point."""
        self.page = page
        self._setup_page()
        self._build_ui()

        # Show annotator dialog or use default username
        if self.default_username:
            # Skip dialog, use default username
            annotator_info = {
                'username': self.default_username,
                'full_name': self.default_username,
                'email': None,
                'expertise_level': None
            }
            self._on_annotator_complete(annotator_info)
        else:
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
                    "Review and annotate AI-generated fact-checking results from PostgreSQL database",
                    size=14,
                    color=ft.Colors.GREY_700
                )
            ], spacing=5),
            padding=ft.padding.only(bottom=20)
        )

        # Database status section
        self.status_text = ft.Text(
            "Loading from database...",
            size=12,
            color=ft.Colors.GREY_600,
            italic=True
        )

        status_section = ft.Container(
            content=self.status_text,
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
            status_section,
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

        # Auto-save indicator
        auto_save_text = ft.Text(
            "✓ Annotations saved automatically to database",
            size=12,
            color=ft.Colors.GREEN_700,
            italic=True
        )

        navigation_section = ft.Row([
            self.prev_button,
            self.next_button,
            ft.Container(expand=True),
            auto_save_text
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

        # Always load from PostgreSQL database (input files should be imported via CLI)
        self._load_from_database()

    def _load_from_database(self):
        """Load fact-check results directly from PostgreSQL database."""
        try:
            self.data_manager.load_from_database()

            # Update UI
            mode_indicator = " [INCREMENTAL MODE]" if self.incremental else ""
            self.status_text.value = f"✓ Loaded {len(self.data_manager.results)} statements from PostgreSQL{mode_indicator}"
            self.status_text.italic = False
            self.status_text.color = ft.Colors.GREEN_700

            # Show review interface
            self.current_index = 0
            self.review_content.visible = True
            self._display_current_statement()

            self.page.update()

        except Exception as ex:
            import traceback
            error_details = traceback.format_exc()
            print(f"ERROR in _load_from_database:")
            print(error_details)
            show_error_dialog(self.page, f"Error loading from database:\n\n{str(ex)}\n\nCheck console for details.")

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

