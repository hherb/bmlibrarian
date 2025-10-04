"""
Document card creation utilities.

Provides functions for creating document cards for search results and scoring displays.
"""

import flet as ft
from typing import Dict, Optional, Callable
from .status_icons import get_score_color


def create_document_result_card(index: int, doc: Dict) -> ft.ExpansionTile:
    """Create an expandable card for displaying search result document.

    Args:
        index: Document index in the search results
        doc: Document dictionary with title, abstract, year, etc.

    Returns:
        ExpansionTile widget for the document
    """
    title = doc.get('title', 'Untitled Document')
    abstract = doc.get('abstract', 'No abstract available')
    year = doc.get('year', 'Unknown year')
    authors = doc.get('authors', 'Unknown authors')

    # Truncate title for display
    display_title = title[:80] + "..." if len(title) > 80 else title

    # Create expansion tile for document
    return ft.ExpansionTile(
        title=ft.Text(
            f"{index + 1}. {display_title}",
            size=12,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.BLUE_800
        ),
        subtitle=ft.Text(
            f"Year: {year}",
            size=11,
            color=ft.Colors.GREY_600
        ),
        controls=[
            ft.Container(
                content=ft.Column([
                    # Full title
                    ft.Container(
                        content=ft.Text(
                            f"Title: {title}",
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color=ft.Colors.BLUE_900
                        ),
                        padding=ft.padding.only(bottom=8)
                    ),
                    # Authors
                    ft.Container(
                        content=ft.Text(
                            f"Authors: {authors}",
                            size=10,
                            color=ft.Colors.GREY_700
                        ),
                        padding=ft.padding.only(bottom=8)
                    ),
                    # Abstract
                    ft.Container(
                        content=ft.Column([
                            ft.Text(
                                "Abstract:",
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.BLACK
                            ),
                            ft.Text(
                                abstract,
                                size=10,
                                color=ft.Colors.GREY_800,
                                selectable=True
                            )
                        ], spacing=4),
                        padding=ft.padding.all(8),
                        bgcolor=ft.Colors.GREY_100,
                        border_radius=5
                    )
                ], spacing=4),
                padding=ft.padding.all(10)
            )
        ]
    )


def create_document_scoring_card(
    index: int,
    doc: Dict,
    scoring_result: Dict,
    on_score_override: Optional[Callable[[int, str], None]] = None,
    on_score_approval: Optional[Callable[[int, bool], None]] = None
) -> ft.Container:
    """Create a card for displaying document with AI score and human override option.

    Args:
        index: Document index
        doc: Document dictionary
        scoring_result: Scoring result dictionary with 'score' and 'reasoning'
        on_score_override: Callback for score override changes
        on_score_approval: Callback for score approval changes

    Returns:
        Container widget with document scoring card
    """
    title = doc.get('title', 'Untitled Document')[:100]
    abstract = doc.get('abstract', 'No abstract available')[:300]

    ai_score = scoring_result.get('score', 0)
    reasoning = scoring_result.get('reasoning', 'No reasoning provided')

    # Create human score input field
    human_score_field = ft.TextField(
        label="Human Score (1-5)",
        hint_text="Override AI score",
        width=120,
        height=40,
        keyboard_type=ft.KeyboardType.NUMBER,
        on_change=lambda e: on_score_override(index, e.control.value) if on_score_override else None
    )

    # Create approval checkbox
    approve_checkbox = ft.Checkbox(
        label="Approve AI score",
        value=False,
        on_change=lambda e: on_score_approval(index, e.control.value) if on_score_approval else None
    )

    return ft.Container(
        content=ft.Column([
            # Document title
            ft.Text(
                f"Document {index + 1}: {title}",
                size=13,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.BLUE_800
            ),
            # Abstract
            ft.Container(
                content=ft.Text(
                    abstract + ("..." if len(doc.get('abstract', '')) > 300 else ""),
                    size=11,
                    color=ft.Colors.GREY_700
                ),
                padding=ft.padding.all(8),
                bgcolor=ft.Colors.GREY_100,
                border_radius=3
            ),
            # Scoring section
            ft.Row([
                # AI Score
                ft.Container(
                    content=ft.Column([
                        ft.Text("AI Score", size=11, weight=ft.FontWeight.BOLD),
                        ft.Text(f"{ai_score:.1f}/5.0", size=16, weight=ft.FontWeight.BOLD,
                               color=get_score_color(ai_score))
                    ], spacing=2),
                    padding=ft.padding.all(8),
                    bgcolor=ft.Colors.WHITE,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    border_radius=5,
                    width=80
                ),
                # Human interaction
                ft.Container(
                    content=ft.Column([
                        ft.Text("Human Review", size=11, weight=ft.FontWeight.BOLD),
                        human_score_field,
                        approve_checkbox
                    ], spacing=5),
                    padding=ft.padding.all(8),
                    width=160
                ),
                # Reasoning
                ft.Container(
                    content=ft.Column([
                        ft.Text("AI Reasoning", size=11, weight=ft.FontWeight.BOLD),
                        ft.Text(reasoning, size=10, color=ft.Colors.GREY_600)
                    ], spacing=2),
                    padding=ft.padding.all(8),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=3,
                    expand=True
                )
            ], spacing=10, alignment=ft.MainAxisAlignment.START)
        ], spacing=8),
        padding=ft.padding.all(10),
        margin=ft.margin.symmetric(vertical=5),
        bgcolor=ft.Colors.WHITE,
        border=ft.border.all(1, ft.Colors.GREY_300),
        border_radius=8
    )
