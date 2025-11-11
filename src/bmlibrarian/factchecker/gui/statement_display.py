"""
Statement display components for Fact Checker Review GUI.

Handles UI components for displaying statements, annotations, and progress.
"""

from typing import Optional
import flet as ft


class StatementDisplay:
    """Manages statement display UI components."""

    def __init__(self):
        """Initialize statement display components."""
        # Progress components
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

        # Statement text
        self.statement_text = ft.Text(
            "",
            size=16,
            weight=ft.FontWeight.W_500,
            selectable=True
        )

        # Annotation badges
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

    def update_progress(self, current_index: int, total: int):
        """
        Update progress indicator.

        Args:
            current_index: Current statement index (0-based)
            total: Total number of statements
        """
        self.statement_counter.value = f"Statement {current_index + 1} of {total}"
        self.progress_bar.value = (current_index + 1) / total if total > 0 else 0

    def update_statement(self, statement_text: str):
        """
        Update displayed statement text.

        Args:
            statement_text: Statement to display
        """
        self.statement_text.value = statement_text

    def update_annotation_badge(self, annotation_column: ft.Column, value: str):
        """
        Update an annotation badge with the given value.

        Args:
            annotation_column: Column containing the badge
            value: Annotation value (yes/no/maybe)
        """
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

    def update_annotations(self, original: str, ai_eval: str, ai_reason: str):
        """
        Update all annotation displays.

        Args:
            original: Original expected answer
            ai_eval: AI evaluation
            ai_reason: AI rationale
        """
        self.update_annotation_badge(self.original_annotation, original)
        self.update_annotation_badge(self.ai_annotation, ai_eval)
        self.ai_rationale.value = ai_reason or "No rationale provided"

    def build_progress_section(self) -> ft.Row:
        """Build progress section UI."""
        return ft.Row([
            self.statement_counter,
            self.progress_bar
        ], spacing=20, alignment=ft.MainAxisAlignment.START)

    def build_statement_section(self) -> ft.Container:
        """Build statement display section."""
        return ft.Container(
            content=ft.Column([
                ft.Text("Statement:", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_700),
                self.statement_text
            ], spacing=8),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.GREY_50,
            border_radius=8,
            border=ft.border.all(1, ft.Colors.GREY_300)
        )

    def build_annotations_section(self, human_annotation_section: ft.Container) -> ft.Row:
        """
        Build annotations display section.

        Args:
            human_annotation_section: Human annotation input section

        Returns:
            Row containing all annotation sections
        """
        return ft.Row([
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
