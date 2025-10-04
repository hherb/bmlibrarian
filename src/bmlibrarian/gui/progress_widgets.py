"""
Progress bar and progress tracking widgets.

Provides reusable progress display components for showing task progress.
"""

import flet as ft
from typing import Optional


def create_simple_progress_bar(visible: bool = False) -> ft.ProgressBar:
    """Create a simple indeterminate progress bar.

    Args:
        visible: Whether the progress bar should be visible initially

    Returns:
        ProgressBar widget
    """
    return ft.ProgressBar(
        visible=visible,
        height=4,
        color=ft.Colors.BLUE_400
    )


def create_detailed_progress_container(visible: bool = False) -> ft.Container:
    """Create a detailed progress container with tqdm-style display.

    Returns:
        Container with progress bar, text, and item description components
    """
    return ft.Container(
        visible=visible,
        content=ft.Column([
            ft.Row([
                ft.Text("Progress:", size=11, weight=ft.FontWeight.BOLD),
                ft.Text("", size=11, color=ft.Colors.GREY_600)  # Progress text (e.g., "25/100")
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.ProgressBar(
                value=0.0,
                height=6,
                color=ft.Colors.GREEN_400,
                bgcolor=ft.Colors.GREY_300
            ),
            ft.Text("", size=10, color=ft.Colors.GREY_600, italic=True)  # Current item text
        ], spacing=4),
        padding=ft.padding.symmetric(horizontal=10, vertical=8),
        bgcolor=ft.Colors.GREEN_50,
        border_radius=5,
        border=ft.border.all(1, ft.Colors.GREEN_200)
    )


def update_progress(
    progress_container: ft.Container,
    current: int,
    total: int,
    item_name: str = "",
    visible: bool = True
) -> None:
    """Update a detailed progress container with new values.

    Args:
        progress_container: The progress container to update (from create_detailed_progress_container)
        current: Current progress count
        total: Total items to process
        item_name: Name/description of current item being processed
        visible: Whether to show the progress container
    """
    if total <= 0:
        return

    # Calculate progress percentage
    progress_value = current / total

    # Update progress components (accessing nested controls)
    try:
        # Progress text (e.g., "25/100 (25.0%)")
        progress_container.content.controls[0].controls[1].value = f"{current}/{total} ({progress_value*100:.1f}%)"

        # Progress bar value
        progress_container.content.controls[1].value = progress_value

        # Current item text
        if item_name:
            progress_container.content.controls[2].value = item_name

        # Show/hide based on parameters
        progress_container.visible = visible and (total > 1)
    except (AttributeError, IndexError) as e:
        # Gracefully handle if structure doesn't match
        pass


def get_progress_components(progress_container: ft.Container) -> tuple:
    """Get references to progress components from a detailed progress container.

    Args:
        progress_container: Container created by create_detailed_progress_container

    Returns:
        Tuple of (progress_text, progress_bar, item_text) controls
    """
    try:
        progress_text = progress_container.content.controls[0].controls[1]
        progress_bar = progress_container.content.controls[1]
        item_text = progress_container.content.controls[2]
        return progress_text, progress_bar, item_text
    except (AttributeError, IndexError):
        return None, None, None
