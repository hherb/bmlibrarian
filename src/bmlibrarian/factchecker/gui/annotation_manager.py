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
        # IMPORTANT: Using "n/a" as key instead of "" because Flet has issues with empty string keys
        self.annotation_dropdown = ft.Dropdown(
            label="Your Annotation",
            options=[
                ft.dropdown.Option(key="n/a", text="N/A"),
                ft.dropdown.Option(key="yes", text="Yes"),
                ft.dropdown.Option(key="no", text="No"),
                ft.dropdown.Option(key="maybe", text="Maybe")
            ],
            value="n/a",  # Default to n/a
            width=200,
            on_change=self._handle_annotation_change,
            filled=True
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
            annotation: Annotation value (yes/no/maybe or None/empty for N/A)
            explanation: Explanation text
        """
        # Handle None or empty string as no annotation
        # Using "n/a" instead of empty string because Flet has issues with empty string keys
        if annotation is None or annotation == "":
            self.annotation_dropdown.value = "n/a"
        else:
            self.annotation_dropdown.value = str(annotation).lower()

        self.explanation_field.value = explanation if explanation else ""

        # Trigger explicit update to force Flet to re-render
        if hasattr(self.annotation_dropdown, 'update'):
            try:
                self.annotation_dropdown.update()
                self.explanation_field.update()
            except:
                pass  # Not yet added to page, update will happen on page.update()

    def get_annotation(self) -> str:
        """Get current annotation value, converting 'n/a' to empty string."""
        value = self.annotation_dropdown.value
        # Convert "n/a" back to empty string for database storage
        return "" if value == "n/a" else value

    def get_explanation(self) -> str:
        """Get current explanation text."""
        return self.explanation_field.value

    def clear(self):
        """Clear annotation inputs."""
        self.annotation_dropdown.value = "n/a"  # Use "n/a" instead of empty string
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
