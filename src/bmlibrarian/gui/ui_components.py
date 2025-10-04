"""
Comprehensive UI Component Factory Module for Flet GUIs

This module provides reusable component factory functions for consistent
UI styling across all BMLibrarian GUI applications. It consolidates common
patterns from ui_builder.py, tabs, and other GUI modules.

Usage:
    from bmlibrarian.gui.ui_components import (
        create_labeled_textfield, create_labeled_slider,
        create_section_header, create_action_button
    )
"""

import flet as ft
from typing import Optional, List, Callable, Any, Dict


# ============================================================================
# Section Headers and Titles
# ============================================================================

def create_section_header(
    text: str,
    size: int = 18,
    color: str = ft.Colors.BLUE_700
) -> ft.Text:
    """Create a standardized section header.

    Args:
        text: Header text
        size: Font size (default 18)
        color: Text color (default BLUE_700)

    Returns:
        Configured ft.Text widget
    """
    return ft.Text(
        text,
        size=size,
        weight=ft.FontWeight.BOLD,
        color=color
    )


def create_subsection_header(text: str) -> ft.Text:
    """Create a subsection header (smaller than section header).

    Args:
        text: Header text

    Returns:
        Configured ft.Text widget
    """
    return ft.Text(
        text,
        size=16,
        weight=ft.FontWeight.BOLD,
        color=ft.Colors.BLACK
    )


def create_helper_text(text: str, size: int = 12) -> ft.Text:
    """Create helper/hint text.

    Args:
        text: Helper text content
        size: Font size (default 12)

    Returns:
        Configured ft.Text widget
    """
    return ft.Text(
        text,
        size=size,
        color=ft.Colors.GREY_600
    )


# ============================================================================
# Input Fields
# ============================================================================

def create_labeled_textfield(
    label: str,
    value: str = "",
    width: int = 200,
    helper_text: Optional[str] = None,
    on_change: Optional[Callable] = None,
    on_blur: Optional[Callable] = None,
    multiline: bool = False,
    min_lines: Optional[int] = None,
    max_lines: Optional[int] = None,
    hint_text: Optional[str] = None,
    input_filter: Optional[Any] = None,
    expand: bool = False
) -> ft.TextField:
    """Create a labeled text field with common configuration.

    Args:
        label: Field label
        value: Initial value
        width: Field width (ignored if expand=True)
        helper_text: Helper text below field
        on_change: Change event handler
        on_blur: Blur event handler
        multiline: Enable multiline input
        min_lines: Minimum lines (multiline only)
        max_lines: Maximum lines (multiline only)
        hint_text: Placeholder text
        input_filter: Input filter (e.g., NumbersOnlyInputFilter)
        expand: Expand to fill available space

    Returns:
        Configured ft.TextField widget
    """
    return ft.TextField(
        label=label,
        value=value,
        width=None if expand else width,
        helper_text=helper_text,
        on_change=on_change,
        on_blur=on_blur,
        multiline=multiline,
        min_lines=min_lines,
        max_lines=max_lines,
        hint_text=hint_text,
        input_filter=input_filter,
        expand=expand
    )


def create_number_field(
    label: str,
    value: int = 0,
    width: int = 200,
    helper_text: Optional[str] = None,
    on_change: Optional[Callable] = None,
    on_blur: Optional[Callable] = None
) -> ft.TextField:
    """Create a number-only text field.

    Args:
        label: Field label
        value: Initial value
        width: Field width
        helper_text: Helper text below field
        on_change: Change event handler
        on_blur: Blur event handler

    Returns:
        Configured ft.TextField with number filter
    """
    return ft.TextField(
        label=label,
        value=str(value),
        width=width,
        helper_text=helper_text,
        on_change=on_change,
        on_blur=on_blur,
        input_filter=ft.NumbersOnlyInputFilter()
    )


def create_labeled_slider(
    min_val: float,
    max_val: float,
    value: float,
    divisions: int = 10,
    width: int = 300,
    tooltip: Optional[str] = None,
    on_change: Optional[Callable] = None
) -> ft.Slider:
    """Create a slider with value label.

    Args:
        min_val: Minimum value
        max_val: Maximum value
        value: Initial value
        divisions: Number of discrete steps
        width: Slider width
        tooltip: Tooltip text
        on_change: Change event handler

    Returns:
        Configured ft.Slider widget
    """
    return ft.Slider(
        min=min_val,
        max=max_val,
        value=value,
        divisions=divisions,
        label="{value}",
        width=width,
        tooltip=tooltip,
        on_change=on_change
    )


def create_labeled_dropdown(
    label: str,
    options: List[str],
    value: Optional[str] = None,
    width: int = 400,
    helper_text: Optional[str] = None,
    on_change: Optional[Callable] = None
) -> ft.Dropdown:
    """Create a labeled dropdown with options.

    Args:
        label: Dropdown label
        options: List of option strings
        value: Initially selected value
        width: Dropdown width
        helper_text: Helper text below dropdown
        on_change: Change event handler

    Returns:
        Configured ft.Dropdown widget
    """
    return ft.Dropdown(
        label=label,
        value=value,
        options=[ft.dropdown.Option(opt) for opt in options],
        width=width,
        helper_text=helper_text,
        on_change=on_change
    )


def create_labeled_checkbox(
    label: str,
    value: bool = False,
    tooltip: Optional[str] = None,
    on_change: Optional[Callable] = None
) -> ft.Checkbox:
    """Create a labeled checkbox.

    Args:
        label: Checkbox label
        value: Initial checked state
        tooltip: Tooltip text
        on_change: Change event handler

    Returns:
        Configured ft.Checkbox widget
    """
    return ft.Checkbox(
        label=label,
        value=value,
        tooltip=tooltip,
        on_change=on_change
    )


def create_labeled_switch(
    label: str,
    value: bool = False,
    on_change: Optional[Callable] = None
) -> ft.Switch:
    """Create a labeled switch toggle.

    Args:
        label: Switch label
        value: Initial state
        on_change: Change event handler

    Returns:
        Configured ft.Switch widget
    """
    return ft.Switch(
        label=label,
        value=value,
        on_change=on_change
    )


# ============================================================================
# Buttons
# ============================================================================

def create_action_button(
    text: str,
    icon: Optional[str] = None,
    on_click: Optional[Callable] = None,
    bgcolor: Optional[str] = None,
    color: Optional[str] = None,
    width: Optional[int] = None,
    height: int = 40,
    disabled: bool = False,
    tooltip: Optional[str] = None
) -> ft.ElevatedButton:
    """Create an action button with consistent styling.

    Args:
        text: Button text
        icon: Optional icon name
        on_click: Click event handler
        bgcolor: Background color
        color: Text/icon color
        width: Button width (None for auto)
        height: Button height
        disabled: Disabled state
        tooltip: Tooltip text

    Returns:
        Configured ft.ElevatedButton widget
    """
    button = ft.ElevatedButton(
        text,
        icon=icon,
        on_click=on_click,
        width=width,
        height=height,
        disabled=disabled,
        tooltip=tooltip
    )

    if bgcolor or color:
        button.style = ft.ButtonStyle(
            bgcolor=bgcolor,
            color=color
        )

    return button


def create_primary_button(
    text: str,
    icon: Optional[str] = None,
    on_click: Optional[Callable] = None,
    width: Optional[int] = None,
    disabled: bool = False
) -> ft.ElevatedButton:
    """Create a primary action button (blue).

    Args:
        text: Button text
        icon: Optional icon name
        on_click: Click event handler
        width: Button width
        disabled: Disabled state

    Returns:
        Primary styled button
    """
    return create_action_button(
        text=text,
        icon=icon,
        on_click=on_click,
        bgcolor=ft.Colors.BLUE_600,
        color=ft.Colors.WHITE,
        width=width,
        disabled=disabled
    )


def create_success_button(
    text: str,
    icon: Optional[str] = None,
    on_click: Optional[Callable] = None,
    width: Optional[int] = None
) -> ft.ElevatedButton:
    """Create a success action button (green).

    Args:
        text: Button text
        icon: Optional icon name
        on_click: Click event handler
        width: Button width

    Returns:
        Success styled button
    """
    return create_action_button(
        text=text,
        icon=icon,
        on_click=on_click,
        bgcolor=ft.Colors.GREEN_600,
        color=ft.Colors.WHITE,
        width=width
    )


def create_warning_button(
    text: str,
    icon: Optional[str] = None,
    on_click: Optional[Callable] = None,
    width: Optional[int] = None
) -> ft.ElevatedButton:
    """Create a warning action button (orange).

    Args:
        text: Button text
        icon: Optional icon name
        on_click: Click event handler
        width: Button width

    Returns:
        Warning styled button
    """
    return create_action_button(
        text=text,
        icon=icon,
        on_click=on_click,
        bgcolor=ft.Colors.ORANGE_600,
        color=ft.Colors.WHITE,
        width=width
    )


def create_icon_button(
    icon: str,
    on_click: Optional[Callable] = None,
    tooltip: Optional[str] = None,
    icon_color: Optional[str] = None
) -> ft.IconButton:
    """Create an icon button.

    Args:
        icon: Icon name
        on_click: Click event handler
        tooltip: Tooltip text
        icon_color: Icon color

    Returns:
        Configured ft.IconButton widget
    """
    return ft.IconButton(
        icon=icon,
        on_click=on_click,
        tooltip=tooltip,
        icon_color=icon_color
    )


# ============================================================================
# Layout Containers
# ============================================================================

def create_form_row(
    label: str,
    control: ft.Control,
    label_width: int = 120,
    spacing: int = 10
) -> ft.Row:
    """Create a form row with label and control.

    Args:
        label: Label text
        control: Form control widget
        label_width: Width of label column
        spacing: Spacing between label and control

    Returns:
        ft.Row with label and control
    """
    return ft.Row(
        [
            ft.Text(label, width=label_width),
            control
        ],
        spacing=spacing,
        vertical_alignment=ft.CrossAxisAlignment.CENTER
    )


def create_card_container(
    content: ft.Control,
    bgcolor: str = ft.Colors.GREY_50,
    padding: int = 10,
    border_radius: int = 5,
    border_color: Optional[str] = None,
    border_width: int = 1
) -> ft.Container:
    """Create a card-style container.

    Args:
        content: Content widget
        bgcolor: Background color
        padding: Padding (all sides)
        border_radius: Border radius
        border_color: Optional border color
        border_width: Border width (if border_color specified)

    Returns:
        Configured ft.Container widget
    """
    border = None
    if border_color:
        border = ft.border.all(border_width, border_color)

    return ft.Container(
        content=content,
        bgcolor=bgcolor,
        padding=ft.padding.all(padding),
        border_radius=border_radius,
        border=border
    )


def create_section_container(
    controls: List[ft.Control],
    title: Optional[str] = None,
    spacing: int = 10,
    margin_bottom: int = 20
) -> ft.Container:
    """Create a container for a configuration section.

    Args:
        controls: List of controls to include
        title: Optional section title
        spacing: Spacing between controls
        margin_bottom: Bottom margin

    Returns:
        Configured ft.Container with section content
    """
    column_controls = []

    if title:
        column_controls.append(create_section_header(title))

    column_controls.extend(controls)

    return ft.Container(
        ft.Column(column_controls, spacing=spacing),
        margin=ft.margin.only(bottom=margin_bottom)
    )


# ============================================================================
# Badges and Status Indicators
# ============================================================================

def create_badge(
    text: str,
    bgcolor: str,
    text_color: str = ft.Colors.WHITE,
    size: int = 12
) -> ft.Container:
    """Create a colored badge.

    Args:
        text: Badge text
        bgcolor: Background color
        text_color: Text color
        size: Font size

    Returns:
        Badge container
    """
    return ft.Container(
        content=ft.Text(
            text,
            size=size,
            weight=ft.FontWeight.BOLD,
            color=text_color
        ),
        bgcolor=bgcolor,
        padding=ft.padding.symmetric(horizontal=8, vertical=4),
        border_radius=12
    )


def create_score_badge(score: float, max_score: float = 5.0) -> ft.Container:
    """Create a colored score badge.

    Args:
        score: Score value
        max_score: Maximum possible score

    Returns:
        Score badge with appropriate color
    """
    def get_color(score_val: float) -> str:
        if score_val >= 4.5:
            return ft.Colors.GREEN_700
        elif score_val >= 3.5:
            return ft.Colors.BLUE_700
        elif score_val >= 2.5:
            return ft.Colors.ORANGE_700
        else:
            return ft.Colors.RED_700

    return create_badge(
        text=f"{score:.1f}",
        bgcolor=get_color(score)
    )


def create_priority_badge(priority: str) -> ft.Container:
    """Create a priority badge.

    Args:
        priority: Priority level (HIGH, MEDIUM, LOW)

    Returns:
        Priority badge with appropriate color
    """
    color_map = {
        "HIGH": ft.Colors.RED_700,
        "MEDIUM": ft.Colors.ORANGE_700,
        "LOW": ft.Colors.GREEN_700
    }

    return create_badge(
        text=priority,
        bgcolor=color_map.get(priority, ft.Colors.GREY_700),
        size=10
    )


def create_status_badge(status: str) -> ft.Container:
    """Create a status badge.

    Args:
        status: Status text (completed, running, pending, error, etc.)

    Returns:
        Status badge with appropriate color
    """
    color_map = {
        "completed": ft.Colors.GREEN_700,
        "running": ft.Colors.BLUE_700,
        "pending": ft.Colors.GREY_500,
        "error": ft.Colors.RED_700,
        "waiting": ft.Colors.ORANGE_700
    }

    return create_badge(
        text=status.upper(),
        bgcolor=color_map.get(status.lower(), ft.Colors.GREY_700),
        size=10
    )


# ============================================================================
# Dividers and Separators
# ============================================================================

def create_divider(height: int = 20, thickness: int = 1) -> ft.Divider:
    """Create a horizontal divider.

    Args:
        height: Vertical space occupied by divider
        thickness: Line thickness

    Returns:
        Configured ft.Divider widget
    """
    return ft.Divider(height=height, thickness=thickness)


def create_spacer(height: int = 20) -> ft.Container:
    """Create vertical spacer.

    Args:
        height: Spacer height

    Returns:
        Empty container with specified height
    """
    return ft.Container(height=height)


# ============================================================================
# Configuration-Specific Components
# ============================================================================

def create_parameter_slider_row(
    label: str,
    min_val: float,
    max_val: float,
    value: float,
    tooltip: str,
    divisions: int = 20,
    on_change: Optional[Callable] = None
) -> ft.Row:
    """Create a labeled parameter slider row (common in config GUIs).

    Args:
        label: Parameter label
        min_val: Minimum value
        max_val: Maximum value
        value: Initial value
        tooltip: Parameter description
        divisions: Number of discrete steps
        on_change: Change event handler

    Returns:
        ft.Row with label and slider
    """
    slider = create_labeled_slider(
        min_val=min_val,
        max_val=max_val,
        value=value,
        divisions=divisions,
        tooltip=tooltip,
        on_change=on_change
    )

    return ft.Row(
        [
            ft.Text(label, width=120),
            slider
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER
    )


def create_model_selector(
    available_models: List[str],
    current_model: Optional[str] = None,
    on_change: Optional[Callable] = None,
    on_refresh: Optional[Callable] = None
) -> ft.Row:
    """Create a model selector with refresh button.

    Args:
        available_models: List of available model names
        current_model: Currently selected model
        on_change: Change event handler
        on_refresh: Refresh button click handler

    Returns:
        ft.Row with dropdown and refresh button
    """
    dropdown = create_labeled_dropdown(
        label="Model",
        options=available_models,
        value=current_model,
        helper_text="Select the LLM model for this agent",
        on_change=on_change
    )

    refresh_btn = create_icon_button(
        icon=ft.Icons.REFRESH,
        tooltip="Refresh available models from Ollama",
        on_click=on_refresh
    )

    return ft.Row(
        [dropdown, refresh_btn],
        vertical_alignment=ft.CrossAxisAlignment.CENTER
    )


# ============================================================================
# Dialog Components
# ============================================================================

def create_alert_dialog(
    title: str,
    content: str,
    on_close: Optional[Callable] = None,
    close_text: str = "OK"
) -> ft.AlertDialog:
    """Create a simple alert dialog.

    Args:
        title: Dialog title
        content: Dialog content text
        on_close: Close button handler
        close_text: Close button text

    Returns:
        Configured ft.AlertDialog
    """
    return ft.AlertDialog(
        title=ft.Text(title),
        content=ft.Text(content),
        actions=[
            ft.TextButton(close_text, on_click=on_close)
        ],
        actions_alignment=ft.MainAxisAlignment.END
    )


def create_confirmation_dialog(
    title: str,
    content: str,
    on_confirm: Optional[Callable] = None,
    on_cancel: Optional[Callable] = None,
    confirm_text: str = "Confirm",
    cancel_text: str = "Cancel"
) -> ft.AlertDialog:
    """Create a confirmation dialog with confirm/cancel buttons.

    Args:
        title: Dialog title
        content: Dialog content text
        on_confirm: Confirm button handler
        on_cancel: Cancel button handler
        confirm_text: Confirm button text
        cancel_text: Cancel button text

    Returns:
        Configured ft.AlertDialog
    """
    return ft.AlertDialog(
        title=ft.Text(title),
        content=ft.Text(content),
        actions=[
            ft.TextButton(cancel_text, on_click=on_cancel),
            ft.ElevatedButton(
                confirm_text,
                on_click=on_confirm,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE_600,
                    color=ft.Colors.WHITE
                )
            )
        ],
        actions_alignment=ft.MainAxisAlignment.END
    )


# ============================================================================
# Utility Functions
# ============================================================================

def truncate_text(text: str, max_length: int = 80, suffix: str = "...") -> str:
    """Truncate text to specified length with suffix.

    Args:
        text: Text to truncate
        max_length: Maximum length before truncation
        suffix: Suffix to append (default "...")

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def format_list(items: List[str], max_count: int = 3, separator: str = ", ") -> str:
    """Format a list with truncation.

    Args:
        items: List of items to format
        max_count: Maximum items before truncation
        separator: Item separator

    Returns:
        Formatted string
    """
    if not items:
        return ""

    if len(items) <= max_count:
        return separator.join(items)

    return separator.join(items[:max_count]) + "..."
