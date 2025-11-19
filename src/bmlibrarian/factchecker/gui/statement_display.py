"""
Statement display components for Fact Checker Review GUI.

Handles UI components for displaying statements, annotations, and progress.
"""

from typing import Optional
import flet as ft

from .styles import (
    Colors, ContainerStyles, TextStyles, LayoutConfig,
    AnnotationBadgeStyles, DPIScale
)


class StatementDisplay:
    """Manages statement display UI components."""

    def __init__(self, blind_mode: bool = False):
        """
        Initialize statement display components.

        Args:
            blind_mode: If True, hide original and AI annotations from display
        """
        self.blind_mode = blind_mode

        # Progress components
        counter_style = TextStyles.progress_counter()
        self.statement_counter = ft.Text(
            "Statement 0 of 0",
            **counter_style
        )

        self.progress_bar = ft.ProgressBar(
            value=0,
            width=LayoutConfig.PROGRESS_BAR_WIDTH,
            color=LayoutConfig.PROGRESS_BAR_COLOR,
            bgcolor=LayoutConfig.PROGRESS_BAR_BG
        )

        # Statement text
        self.statement_text = ft.Text(
            "",
            size=DPIScale.font_size(DPIScale.FONT_SIZE_LARGE),
            weight=ft.FontWeight.W_500,
            selectable=True
        )

        # Annotation badges
        self.original_annotation = self._create_annotation_display(
            "Original Annotation",
            Colors.ANNOTATION_PURPLE_BG,
            Colors.ANNOTATION_PURPLE
        )

        self.ai_annotation = self._create_annotation_display(
            "AI Fact-Checker",
            Colors.ANNOTATION_BLUE_BG,
            Colors.ANNOTATION_BLUE
        )

        rationale_style = TextStyles.body_small()
        self.ai_rationale = ft.Text(
            "",
            size=rationale_style['size'],
            color=Colors.GREY_DARK,
            selectable=True
        )

    def _create_annotation_display(self, title: str, bg_color: str, text_color: str) -> ft.Column:
        """Create a standardized annotation display component."""
        annotation_badge = ft.Container(
            content=ft.Text(
                "--",
                size=AnnotationBadgeStyles.badge_font_size(),
                weight=ft.FontWeight.BOLD,
                color=Colors.WHITE
            ),
            padding=AnnotationBadgeStyles.badge_padding(),
            bgcolor=text_color,
            border_radius=AnnotationBadgeStyles.badge_border_radius(),
            alignment=ft.alignment.center
        )

        label_style = TextStyles.label_small()
        return ft.Column([
            ft.Text(title, size=label_style['size'], weight=ft.FontWeight.BOLD, color=text_color),
            annotation_badge
        ], spacing=LayoutConfig.SPACING_SMALL, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

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
        value_lower = str(value).lower() if value else ''

        if value_lower == 'yes':
            badge_text.value = "YES ✓"
            badge_container.bgcolor = Colors.EVAL_YES
        elif value_lower == 'no':
            badge_text.value = "NO ✗"
            badge_container.bgcolor = Colors.EVAL_NO
        elif value_lower == 'maybe':
            badge_text.value = "MAYBE ?"
            badge_container.bgcolor = Colors.EVAL_MAYBE
        else:
            badge_text.value = str(value).upper() if value else "N/A"
            badge_container.bgcolor = Colors.EVAL_NA

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
        ], spacing=LayoutConfig.SPACING_LARGE, alignment=ft.MainAxisAlignment.START)

    def build_statement_section(self) -> ft.Container:
        """Build statement display section."""
        label_style = TextStyles.label_bold()
        statement_style = ContainerStyles.statement_container()
        return ft.Container(
            content=ft.Column([
                ft.Text("Statement:", **label_style),
                self.statement_text
            ], spacing=LayoutConfig.SPACING_SMALL),
            **statement_style
        )

    def build_annotations_section(self, human_annotation_section: ft.Container, show_reviews: bool = True) -> ft.Row:
        """
        Build annotations display section.

        Args:
            human_annotation_section: Human annotation input section
            show_reviews: Whether to show Original and AI annotations (default: True)

        Returns:
            Row containing annotation sections based on visibility settings
        """
        if self.blind_mode or not show_reviews:
            # In blind mode or when reviews are hidden, only show the human annotation section
            return ft.Row([
                ft.Container(
                    content=human_annotation_section,
                    expand=1
                )
            ], spacing=LayoutConfig.SPACING_MEDIUM, vertical_alignment=ft.CrossAxisAlignment.START)
        else:
            # Normal mode: show all annotations
            label_style = TextStyles.label_small()
            return ft.Row([
                ft.Container(
                    content=self.original_annotation,
                    expand=1
                ),
                ft.Container(
                    content=ft.Column([
                        self.ai_annotation,
                        ft.Container(height=LayoutConfig.SPACING_SMALL),
                        ft.Container(
                            content=ft.Column([
                                ft.Text("AI Rationale:", **label_style, color=Colors.GREY_MEDIUM),
                                self.ai_rationale
                            ], spacing=LayoutConfig.SPACING_TINY),
                            padding=ft.padding.all(DPIScale.to_pt(DPIScale.CONTAINER_PADDING_SMALL)),
                            bgcolor=Colors.GREY_BG,
                            border_radius=DPIScale.to_pt(DPIScale.CONTAINER_PADDING_SMALL * 0.5)
                        )
                    ], spacing=LayoutConfig.SPACING_NONE),
                    expand=1
                ),
                ft.Container(
                    content=human_annotation_section,
                    expand=1
                )
            ], spacing=LayoutConfig.SPACING_MEDIUM, vertical_alignment=ft.CrossAxisAlignment.START)
