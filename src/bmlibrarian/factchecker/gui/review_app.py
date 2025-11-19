"""
Main application for Fact Checker Review GUI.

Orchestrates all components for reviewing and annotating fact-check results.
"""

from typing import Optional
from pathlib import Path
import flet as ft

from .dialogs import (
    AnnotatorDialog, show_error_dialog, show_success_dialog,
    show_save_dialog, show_statistics_dialog
)
from .data_manager import FactCheckDataManager
from .statement_display import StatementDisplay
from .annotation_manager import AnnotationManager
from .citation_display import CitationDisplay
from .timer_component import ReviewTimer


class FactCheckerReviewApp:
    """Main application for reviewing fact-check results."""

    def __init__(self, incremental: bool = False, default_username: Optional[str] = None, blind_mode: bool = False, db_file: Optional[str] = None):
        """
        Initialize the review application.

        Args:
            incremental: If True, only show statements you haven't annotated yet
            default_username: If provided, use this username and skip login dialog
            blind_mode: If True, hide original and AI annotations from human annotator
            db_file: Path to SQLite database file (None for PostgreSQL)
        """
        self.page: Optional[ft.Page] = None
        self.incremental = incremental
        self.default_username = default_username
        self.blind_mode = blind_mode
        self.db_file = db_file
        self.current_index = 0

        # Visibility state for UI sections
        self.show_reviews = True
        self.show_citations = True

        # Initialize components
        self.data_manager = FactCheckDataManager(incremental=incremental, db_file=db_file)
        self.statement_display = StatementDisplay(blind_mode=blind_mode)
        self.annotation_manager = AnnotationManager(on_annotation_change=self._on_annotation_change)
        self.timer = ReviewTimer()
        # CitationDisplay will receive database instance after data_manager loads it
        self.citation_display = None

        # UI components
        self.status_text = None
        self.citations_list = None
        self.citations_container = None
        self.prev_button = None
        self.next_button = None
        self.review_content = None
        self.annotations_row = None
        self.toggle_reviews_button = None
        self.toggle_citations_button = None

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
        # Toggle buttons for show/hide
        self.toggle_reviews_button = ft.ElevatedButton(
            "Hide Reviews",
            icon=ft.Icons.VISIBILITY_OFF,
            on_click=self._on_toggle_reviews,
            bgcolor=ft.Colors.ORANGE_700,
            color=ft.Colors.WHITE
        )

        self.toggle_citations_button = ft.ElevatedButton(
            "Hide Citations",
            icon=ft.Icons.VISIBILITY_OFF,
            on_click=self._on_toggle_citations,
            bgcolor=ft.Colors.ORANGE_700,
            color=ft.Colors.WHITE
        )

        # Statistics button
        statistics_button = ft.ElevatedButton(
            "Statistics",
            icon=ft.Icons.ANALYTICS,
            on_click=self._on_show_statistics,
            bgcolor=ft.Colors.BLUE_700,
            color=ft.Colors.WHITE
        )

        # Header
        header = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Column([
                        ft.Text(
                            "Fact-Checker Review Interface",
                            size=28,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.BLUE_900
                        ),
                        ft.Text(
                            "Review and annotate AI-generated fact-checking results" +
                            (" (SQLite Package)" if self.db_file else " (PostgreSQL Database)"),
                            size=14,
                            color=ft.Colors.GREY_700
                        )
                    ], expand=True)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Container(height=10),
                # Top row with controls: Hide/Show buttons, Timer, Statistics
                ft.Row([
                    self.toggle_reviews_button,
                    self.toggle_citations_button,
                    ft.Container(expand=True),
                    self.timer.build_section(),
                    ft.Container(width=10),
                    statistics_button
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
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
        # Progress section (timer now in top row)
        progress_section = self.statement_display.build_progress_section()

        # Statement section
        statement_section = self.statement_display.build_statement_section()

        # Annotations section
        human_annotation_section = self.annotation_manager.build_section()
        self.annotations_row = self.statement_display.build_annotations_section(
            human_annotation_section,
            show_reviews=self.show_reviews
        )

        # Citations section with constant height
        self.citations_list = ft.Column(
            controls=[],
            spacing=10,
            scroll=ft.ScrollMode.AUTO
        )

        # Inner container for citations list with constant height
        self.citations_container = ft.Container(
            content=self.citations_list,
            height=300,  # Constant height
            bgcolor=ft.Colors.GREY_50,
            border_radius=8,
            padding=ft.padding.all(10)
        )

        citations_section = ft.Container(
            content=ft.Column([
                ft.Text(
                    "Supporting Citations",
                    size=14,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.GREY_900
                ),
                self.citations_container
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
        """Load fact-check results from database (PostgreSQL or SQLite)."""
        try:
            self.data_manager.load_from_database()

            # Initialize citation display with database instance now that it's loaded
            if self.citation_display is None:
                self.citation_display = CitationDisplay(self.data_manager.fact_checker_db)

            # Update UI with database info
            mode_indicator = " [INCREMENTAL MODE]" if self.incremental else ""
            db_source = self.data_manager.db_type.upper()

            # For SQLite, add package metadata
            extra_info = ""
            if self.data_manager.db_type == "sqlite" and self.data_manager.fact_checker_db:
                try:
                    db_info = self.data_manager.fact_checker_db.get_database_info()
                    metadata = db_info.get('metadata', {})
                    if metadata.get('export_date'):
                        export_date = metadata['export_date'][:10]  # Just the date part
                        extra_info = f" (exported {export_date})"
                except Exception:
                    pass

            self.status_text.value = f"✓ Loaded {len(self.data_manager.results)} statements from {db_source}{extra_info}{mode_indicator}"
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
            saved_review.get('human_explanation', ''),
            saved_review.get('confidence', '')
        )

        # Update citations
        self._display_citations(result.get('evidence_list', []))

        # Update navigation buttons
        self.prev_button.disabled = (self.current_index == 0)
        self.next_button.disabled = (self.current_index == len(self.data_manager.results) - 1)

        # Start timer with any previously accumulated time
        previous_time = saved_review.get('review_duration_seconds', 0) or 0
        self.timer.start(previous_seconds=previous_time)

        self.page.update()

    def _display_citations(self, evidence_list: list):
        """Display citations in the scrollable list."""
        self.citations_list.controls.clear()

        citations_column = self.citation_display.create_citations_list(evidence_list)
        self.citations_list.controls = citations_column.controls

    def _on_annotation_change(self, annotation: str, explanation: str, confidence: str):
        """Handle annotation change event."""
        # Only record time if an evaluation (yes/no/maybe) has been selected
        review_duration = None
        if annotation and annotation != "n/a":
            review_duration = self.timer.get_elapsed_seconds()

        self.data_manager.save_annotation(
            self.current_index,
            annotation,
            explanation,
            confidence,
            review_duration
        )

    def _on_previous(self, e):
        """Navigate to previous statement."""
        if self.current_index > 0:
            # Check if current statement has annotation - if not, reset timer (don't save time)
            current_review = self.data_manager.reviews[self.current_index]
            if not current_review.get('human_annotation'):
                self.timer.reset()

            self.current_index -= 1
            self._display_current_statement()

    def _on_next(self, e):
        """Navigate to next statement."""
        if self.current_index < len(self.data_manager.results) - 1:
            # Check if current statement has annotation - if not, reset timer (don't save time)
            current_review = self.data_manager.reviews[self.current_index]
            if not current_review.get('human_annotation'):
                self.timer.reset()

            self.current_index += 1
            self._display_current_statement()

    def _on_toggle_reviews(self, e):
        """Toggle visibility of review annotations (Original and AI)."""
        self.show_reviews = not self.show_reviews

        # Update button text and icon
        if self.show_reviews:
            self.toggle_reviews_button.text = "Hide Reviews"
            self.toggle_reviews_button.icon = ft.Icons.VISIBILITY_OFF
        else:
            self.toggle_reviews_button.text = "Show Reviews"
            self.toggle_reviews_button.icon = ft.Icons.VISIBILITY

        # Rebuild annotations section with new visibility
        human_annotation_section = self.annotation_manager.build_section()
        new_annotations_row = self.statement_display.build_annotations_section(
            human_annotation_section,
            show_reviews=self.show_reviews
        )

        # Replace the old annotations_row with new one
        self.annotations_row.visible = False
        self.annotations_row = new_annotations_row

        # Find parent container and update
        if hasattr(self, 'review_content') and self.review_content:
            # Rebuild the entire review content to update layout
            self._refresh_review_layout()

        self.page.update()

    def _on_toggle_citations(self, e):
        """Toggle visibility of citations section."""
        self.show_citations = not self.show_citations

        # Update button text and icon
        if self.show_citations:
            self.toggle_citations_button.text = "Hide Citations"
            self.toggle_citations_button.icon = ft.Icons.VISIBILITY_OFF
        else:
            self.toggle_citations_button.text = "Show Citations"
            self.toggle_citations_button.icon = ft.Icons.VISIBILITY

        # Toggle visibility of citations list (height stays constant)
        if self.citations_list:
            self.citations_list.visible = self.show_citations

        # Show placeholder when citations are hidden
        if self.citations_container and hasattr(self.citations_container, 'content'):
            if not self.show_citations:
                # Show placeholder message
                placeholder = ft.Container(
                    content=ft.Text(
                        "Citations hidden. Click 'Show Citations' to view supporting evidence.",
                        size=12,
                        color=ft.Colors.GREY_500,
                        italic=True,
                        text_align=ft.TextAlign.CENTER
                    ),
                    alignment=ft.alignment.center,
                    expand=True
                )
                # Store original content
                if not hasattr(self, '_original_citations_content'):
                    self._original_citations_content = self.citations_container.content
                self.citations_container.content = placeholder
            else:
                # Restore original content
                if hasattr(self, '_original_citations_content'):
                    self.citations_container.content = self._original_citations_content

        self.page.update()

    def _refresh_review_layout(self):
        """Refresh the review layout after visibility changes."""
        # Rebuild annotations section
        human_annotation_section = self.annotation_manager.build_section()
        new_annotations_row = self.statement_display.build_annotations_section(
            human_annotation_section,
            show_reviews=self.show_reviews
        )

        # Replace annotations_row in the review content
        # Find the Column in review_content and update the annotations_row
        if self.review_content and hasattr(self.review_content, 'content'):
            column = self.review_content.content
            if hasattr(column, 'controls'):
                # Find and replace the annotations_row (should be at index 4)
                for i, control in enumerate(column.controls):
                    if control == self.annotations_row:
                        column.controls[i] = new_annotations_row
                        self.annotations_row = new_annotations_row
                        break

    def _on_show_statistics(self, e):
        """Display statistics dialog."""
        try:
            stats = self.data_manager.calculate_statistics()
            show_statistics_dialog(self.page, stats)
        except Exception as ex:
            import traceback
            error_details = traceback.format_exc()
            print(f"ERROR in _on_show_statistics:")
            print(error_details)
            show_error_dialog(self.page, f"Error calculating statistics:\n\n{str(ex)}")

