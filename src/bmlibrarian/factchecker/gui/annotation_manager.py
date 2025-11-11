"""
Annotation manager for Fact Checker Review GUI.

Handles user input for annotations and explanations.
"""

from typing import Callable, Optional
import flet as ft


class AnnotationManager:
    """Manages annotation input components and callbacks."""

    def __init__(self, on_annotation_change: Optional[Callable] = None):
        """
        Initialize annotation manager.

        Args:
            on_annotation_change: Callback when annotation changes (annotation, explanation)
        """
        self.on_annotation_change = on_annotation_change

        # Create input components
        self.annotation_dropdown = ft.Dropdown(
            label="Your Annotation",
            options=[
                ft.dropdown.Option("yes", "Yes"),
                ft.dropdown.Option("no", "No"),
                ft.dropdown.Option("maybe", "Maybe"),
                ft.dropdown.Option("", "-- Select --")
            ],
            value="",
            width=200,
            on_change=self._handle_annotation_change
        )

        self.explanation_field = ft.TextField(
            label="Explanation for your annotation (optional)",
            multiline=True,
            min_lines=2,
            max_lines=4,
            on_change=self._handle_explanation_change
        )

    def _handle_annotation_change(self, e):
        """Handle annotation dropdown change."""
        if self.on_annotation_change:
            self.on_annotation_change(
                self.annotation_dropdown.value,
                self.explanation_field.value
            )

    def _handle_explanation_change(self, e):
        """Handle explanation text change."""
        if self.on_annotation_change:
            self.on_annotation_change(
                self.annotation_dropdown.value,
                self.explanation_field.value
            )

    def set_annotation(self, annotation: str, explanation: str = ""):
        """
        Set annotation values programmatically.

        Args:
            annotation: Annotation value (yes/no/maybe)
            explanation: Explanation text
        """
        self.annotation_dropdown.value = annotation
        self.explanation_field.value = explanation

    def get_annotation(self) -> str:
        """Get current annotation value."""
        return self.annotation_dropdown.value

    def get_explanation(self) -> str:
        """Get current explanation text."""
        return self.explanation_field.value

    def clear(self):
        """Clear annotation inputs."""
        self.annotation_dropdown.value = ""
        self.explanation_field.value = ""

    def build_section(self) -> ft.Container:
        """Build annotation input section UI."""
        return ft.Container(
            content=ft.Column([
                ft.Text("Human Review", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700),
                self.annotation_dropdown,
                self.explanation_field
            ], spacing=10),
            padding=ft.padding.all(15),
            bgcolor=ft.Colors.GREEN_50,
            border_radius=8,
            border=ft.border.all(2, ft.Colors.GREEN_300)
        )
