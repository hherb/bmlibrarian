"""
Status icon and color utilities for GUI components.

Provides reusable functions for mapping status strings to appropriate icons and colors.
"""

import flet as ft


def get_status_icon(status: str) -> str:
    """Get the icon name for a given status.

    Args:
        status: Status string (pending, running, completed, error, waiting)

    Returns:
        Flet icon name
    """
    icons = {
        "pending": ft.Icons.SCHEDULE,
        "running": ft.Icons.REFRESH,
        "completed": ft.Icons.CHECK_CIRCLE,
        "error": ft.Icons.ERROR,
        "waiting": ft.Icons.EDIT
    }
    return icons.get(status, ft.Icons.HELP)


def get_status_color(status: str) -> str:
    """Get the color for a given status.

    Args:
        status: Status string (pending, running, completed, error, waiting)

    Returns:
        Flet color constant
    """
    colors = {
        "pending": ft.Colors.GREY_500,
        "running": ft.Colors.BLUE_500,
        "completed": ft.Colors.GREEN_500,
        "error": ft.Colors.RED_500,
        "waiting": ft.Colors.ORANGE_500
    }
    return colors.get(status, ft.Colors.GREY_500)


def get_score_color(score: float) -> str:
    """Get color based on score value (1-5 scale).

    Args:
        score: Numeric score value

    Returns:
        Flet color constant
    """
    if score >= 4.5:
        return ft.Colors.GREEN_700
    elif score >= 3.5:
        return ft.Colors.BLUE_700
    elif score >= 2.5:
        return ft.Colors.ORANGE_700
    else:
        return ft.Colors.RED_700
