"""
Query Card Components for Research GUI

Displays generated queries as cards with statistics (documents found, high-scoring, unique).
"""

import flet as ft
from typing import Optional, Dict


class QueryCard:
    """A card displaying a single query with its statistics."""

    def __init__(
        self,
        query_index: int,
        model_name: str,
        attempt_number: int,
        query_text: str,
        has_error: bool = False,
        error_message: str = None
    ):
        """Initialize a query card.

        Args:
            query_index: Index of the query (1-based)
            model_name: Name of the model that generated this query
            attempt_number: Attempt number for this model
            query_text: The PostgreSQL tsquery string
            has_error: Whether query generation failed
            error_message: Error message if generation failed
        """
        self.query_index = query_index
        self.model_name = model_name
        self.attempt_number = attempt_number
        self.query_text = query_text
        self.has_error = has_error
        self.error_message = error_message

        # Statistics (updated later)
        self.total_documents = None
        self.high_scoring_documents = None
        self.unique_high_scoring = None
        self.execution_time = None

        # UI components
        self.card_container = None
        self.stats_row = None
        self._build()

    def _build(self):
        """Build the query card UI."""
        # Shorten model name for display
        display_model = self.model_name.split(':')[0] if ':' in self.model_name else self.model_name

        # Header row with model and attempt info
        header = ft.Row(
            [
                ft.Container(
                    content=ft.Text(
                        f"Query #{self.query_index}",
                        size=13,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_900
                    ),
                    bgcolor=ft.Colors.BLUE_50,
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    border_radius=4
                ),
                ft.Text(
                    f"{display_model} • Attempt {self.attempt_number}",
                    size=11,
                    color=ft.Colors.GREY_600,
                    italic=True
                )
            ],
            spacing=10,
            alignment=ft.MainAxisAlignment.START
        )

        # Query text display
        if self.has_error:
            query_display = ft.Container(
                content=ft.Text(
                    f"❌ Generation failed: {self.error_message or 'Unknown error'}",
                    size=11,
                    color=ft.Colors.RED_700,
                    italic=True
                ),
                padding=ft.padding.all(8),
                bgcolor=ft.Colors.RED_50,
                border_radius=4
            )
        else:
            query_display = ft.Container(
                content=ft.Text(
                    self.query_text,
                    size=11,
                    color=ft.Colors.GREY_800,
                    selectable=True,
                    font_family="Courier New"
                ),
                padding=ft.padding.all(8),
                bgcolor=ft.Colors.GREY_50,
                border_radius=4,
                expand=True
            )

        # Statistics row (initially empty or showing "Pending...")
        self.stats_row = self._build_stats_row()

        # Assemble card
        content = ft.Column(
            [
                header,
                ft.Container(height=5),
                query_display,
                ft.Container(height=5),
                self.stats_row
            ],
            spacing=0,
            tight=True
        )

        self.card_container = ft.Container(
            content=content,
            border=ft.border.all(
                1,
                ft.Colors.RED_300 if self.has_error else ft.Colors.BLUE_200
            ),
            border_radius=8,
            padding=ft.padding.all(12),
            bgcolor=ft.Colors.WHITE,
            margin=ft.margin.only(bottom=8)
        )

    def _build_stats_row(self) -> ft.Row:
        """Build the statistics display row."""
        if self.has_error:
            return ft.Row(
                [
                    ft.Text(
                        "No statistics (generation failed)",
                        size=10,
                        color=ft.Colors.GREY_500,
                        italic=True
                    )
                ],
                spacing=10
            )

        if self.total_documents is None:
            # Pending state
            return ft.Row(
                [
                    ft.ProgressRing(width=12, height=12, stroke_width=2),
                    ft.Text(
                        "Executing query...",
                        size=10,
                        color=ft.Colors.GREY_600,
                        italic=True
                    )
                ],
                spacing=8
            )

        # Stats available
        stat_items = []

        # Total documents
        stat_items.append(
            self._create_stat_chip(
                "📄",
                f"{self.total_documents} docs",
                ft.Colors.BLUE_100,
                ft.Colors.BLUE_900
            )
        )

        # High-scoring documents (only if scoring is complete)
        if self.high_scoring_documents is not None:
            stat_items.append(
                self._create_stat_chip(
                    "⭐",
                    f"{self.high_scoring_documents} high-scoring",
                    ft.Colors.AMBER_100,
                    ft.Colors.AMBER_900
                )
            )

        # Unique high-scoring (only if available)
        if self.unique_high_scoring is not None:
            stat_items.append(
                self._create_stat_chip(
                    "✨",
                    f"{self.unique_high_scoring} unique",
                    ft.Colors.GREEN_100,
                    ft.Colors.GREEN_900
                )
            )

        # Execution time
        if self.execution_time is not None:
            stat_items.append(
                self._create_stat_chip(
                    "⏱️",
                    f"{self.execution_time:.2f}s",
                    ft.Colors.GREY_100,
                    ft.Colors.GREY_700
                )
            )

        return ft.Row(
            stat_items,
            spacing=8,
            wrap=True
        )

    def _create_stat_chip(
        self,
        icon: str,
        text: str,
        bgcolor: str,
        textcolor: str
    ) -> ft.Container:
        """Create a small statistics chip."""
        return ft.Container(
            content=ft.Text(
                f"{icon} {text}",
                size=10,
                weight=ft.FontWeight.W_500,
                color=textcolor
            ),
            bgcolor=bgcolor,
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            border_radius=12
        )

    def update_stats(
        self,
        total_documents: int = None,
        high_scoring_documents: int = None,
        unique_high_scoring: int = None,
        execution_time: float = None
    ):
        """Update the statistics for this query.

        Args:
            total_documents: Total number of documents found by this query
            high_scoring_documents: Number of high-scoring documents
            unique_high_scoring: Number of unique high-scoring documents
            execution_time: Query execution time in seconds
        """
        if total_documents is not None:
            self.total_documents = total_documents
        if high_scoring_documents is not None:
            self.high_scoring_documents = high_scoring_documents
        if unique_high_scoring is not None:
            self.unique_high_scoring = unique_high_scoring
        if execution_time is not None:
            self.execution_time = execution_time

        # Rebuild the entire card to reflect new stats
        self._build()

    def get_control(self) -> ft.Container:
        """Get the Flet control for this card."""
        return self.card_container
