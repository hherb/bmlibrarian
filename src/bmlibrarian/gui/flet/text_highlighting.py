"""
Text highlighting utilities for GUI components.

Provides functions for creating highlighted text displays, particularly for
showing citation passages within abstracts.
"""

import re
import flet as ft
from typing import Optional


def create_highlighted_abstract(abstract: str, passage: str) -> ft.Control:
    """Create abstract widget with yellow-highlighted passage (like text marker).

    Args:
        abstract: Full abstract text
        passage: Passage to highlight within the abstract

    Returns:
        Flet widget displaying the abstract with highlighted passage
    """
    if not abstract or not passage:
        return ft.Text(abstract or "No abstract available", size=11, selectable=True)

    # Clean up passage for matching (remove extra whitespace)
    clean_passage = ' '.join(passage.split())

    # Try to find exact match (case-insensitive)
    pattern = re.compile(re.escape(clean_passage), re.IGNORECASE)
    match = pattern.search(abstract)

    if match:
        return _create_exact_match_widget(abstract, match)
    else:
        return _create_fuzzy_match_widget(abstract, passage, clean_passage)


def _create_exact_match_widget(abstract: str, match: re.Match) -> ft.Text:
    """Create widget for exact passage match with highlighting.

    Args:
        abstract: Full abstract text
        match: Regex match object for the passage

    Returns:
        Text widget with highlighted passage
    """
    start, end = match.span()
    spans = []

    # Text before highlight
    if start > 0:
        spans.append(
            ft.TextSpan(
                abstract[:start],
                style=ft.TextStyle(size=11, color=ft.Colors.BLACK87)
            )
        )

    # Highlighted passage (yellow background like highlighter marker)
    spans.append(
        ft.TextSpan(
            "📌 " + abstract[start:end] + " 📌",
            style=ft.TextStyle(
                size=11,
                color=ft.Colors.BLACK,
                weight=ft.FontWeight.W_600,
                bgcolor=ft.Colors.YELLOW_300  # Yellow highlighter effect
            )
        )
    )

    # Text after highlight
    if end < len(abstract):
        spans.append(
            ft.TextSpan(
                abstract[end:],
                style=ft.TextStyle(size=11, color=ft.Colors.BLACK87)
            )
        )

    return ft.Text(spans=spans, selectable=True)


def _create_fuzzy_match_widget(abstract: str, passage: str, clean_passage: str) -> ft.Control:
    """Create widget for fuzzy/partial passage match.

    Args:
        abstract: Full abstract text
        passage: Original passage text
        clean_passage: Cleaned passage text

    Returns:
        Widget displaying fuzzy match or separate passage/abstract
    """
    # Try fuzzy matching with first 10 words
    passage_start = ' '.join(passage.split()[:10])
    fuzzy_pattern = re.compile(re.escape(passage_start), re.IGNORECASE)
    fuzzy_match = fuzzy_pattern.search(abstract)

    if fuzzy_match:
        # Show partial match with warning
        start = fuzzy_match.span()[0]
        end = min(start + len(clean_passage), len(abstract))

        spans = []
        if start > 0:
            spans.append(ft.TextSpan(abstract[:start], style=ft.TextStyle(size=11, color=ft.Colors.BLACK87)))

        spans.append(
            ft.TextSpan(
                "⚠️ " + abstract[start:end] + " ⚠️",
                style=ft.TextStyle(
                    size=11,
                    color=ft.Colors.BLACK,
                    weight=ft.FontWeight.W_600,
                    bgcolor=ft.Colors.ORANGE_200  # Orange for partial match
                )
            )
        )

        if end < len(abstract):
            spans.append(ft.TextSpan(abstract[end:], style=ft.TextStyle(size=11, color=ft.Colors.BLACK87)))

        return ft.Column([
            ft.Text("⚠️ Approximate match only", size=10, color=ft.Colors.ORANGE_700, italic=True),
            ft.Text(spans=spans, selectable=True)
        ])
    else:
        # No match - show separately
        return _create_no_match_widget(abstract, passage)


def _create_no_match_widget(abstract: str, passage: str) -> ft.Column:
    """Create widget when passage cannot be found in abstract.

    Args:
        abstract: Full abstract text
        passage: Passage text that couldn't be matched

    Returns:
        Column widget showing passage and abstract separately
    """
    return ft.Column([
        ft.Container(
            content=ft.Text(f"📌 Cited Passage:\n{passage}",
                          size=11, weight=ft.FontWeight.W_600, selectable=True),
            padding=ft.padding.all(8),
            bgcolor=ft.Colors.YELLOW_300,
            border_radius=3
        ),
        ft.Text("Full Abstract:", size=10, weight=ft.FontWeight.BOLD),
        ft.Text(abstract, size=11, color=ft.Colors.BLACK87, selectable=True)
    ], spacing=5)
