"""
Citation review components and utilities.

Provides functions for creating citation review cards with passage highlighting.
"""

import flet as ft
from typing import Any, Callable, Optional
from .text_highlighting import create_highlighted_abstract


def create_citation_review_card(index: int, citation: Any, on_toggle: Optional[Callable] = None) -> ft.Container:
    """Create a card for reviewing a citation with highlighted abstract.

    Args:
        index: Citation index
        citation: Citation object or dictionary
        on_toggle: Optional callback for status toggle (index, button)

    Returns:
        Container widget with citation review card
    """
    # Get citation details (handle both objects and dicts)
    passage = citation.passage if hasattr(citation, 'passage') else citation.get('passage', '')
    summary = citation.summary if hasattr(citation, 'summary') else citation.get('summary', '')
    title = citation.document_title if hasattr(citation, 'document_title') else citation.get('document_title', '')
    abstract = citation.abstract if hasattr(citation, 'abstract') else citation.get('abstract', '')

    # Create highlighted abstract widget
    abstract_widget = create_highlighted_abstract(abstract, passage)

    # Create status toggle button
    status_button = ft.IconButton(
        icon=ft.Icons.RADIO_BUTTON_UNCHECKED,
        icon_color=ft.Colors.GREY_400,
        tooltip="Unrated - Click to Accept",
        on_click=lambda e: on_toggle(index, status_button) if on_toggle else None,
        data={'index': index, 'status': None}  # Track status in button data
    )

    return ft.Container(
        content=ft.Column([
            # Citation header with status toggle
            ft.Row([
                ft.Text(f"Citation {index + 1}", size=13, weight=ft.FontWeight.BOLD,
                       color=ft.Colors.BLUE_800, expand=True),
                status_button
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),

            # Document title
            ft.Text(f"📄 {title}", size=12, weight=ft.FontWeight.W_500),

            # Summary
            ft.Container(
                content=ft.Column([
                    ft.Text("Summary:", size=11, weight=ft.FontWeight.BOLD),
                    ft.Text(summary, size=11, color=ft.Colors.GREY_700, selectable=True)
                ]),
                padding=ft.padding.all(8),
                bgcolor=ft.Colors.AMBER_50,
                border_radius=3
            ),

            # Abstract with highlighted passage
            ft.Container(
                content=ft.Column([
                    ft.Text("Abstract (highlighted passage):", size=11, weight=ft.FontWeight.BOLD),
                    abstract_widget
                ], spacing=5),
                padding=ft.padding.all(8),
                bgcolor=ft.Colors.GREY_100,
                border_radius=3,
                expand=True
            )
        ], spacing=8),
        padding=ft.padding.all(12),
        border=ft.border.all(1, ft.Colors.GREY_300),
        border_radius=5,
        bgcolor=ft.Colors.WHITE
    )


def toggle_citation_status(button: ft.IconButton) -> str:
    """Toggle citation status button through states: None → accepted → refused → None.

    Args:
        button: The IconButton to toggle

    Returns:
        New status string ('accepted', 'refused', or None)
    """
    current_status = button.data.get('status')

    # Cycle through states
    if current_status is None:
        # Unrated → Accepted
        new_status = 'accepted'
        button.icon = ft.Icons.CHECK_CIRCLE
        button.icon_color = ft.Colors.GREEN_700
        button.tooltip = "Accepted ✅ - Click to Refuse"
    elif current_status == 'accepted':
        # Accepted → Refused
        new_status = 'refused'
        button.icon = ft.Icons.CANCEL
        button.icon_color = ft.Colors.RED_700
        button.tooltip = "Refused ❌ - Click to Clear"
    else:  # refused
        # Refused → Unrated
        new_status = None
        button.icon = ft.Icons.RADIO_BUTTON_UNCHECKED
        button.icon_color = ft.Colors.GREY_400
        button.tooltip = "Unrated ⚪ - Click to Accept"

    # Update button data
    button.data['status'] = new_status

    return new_status
