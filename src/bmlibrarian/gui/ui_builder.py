"""
UI Component Builder Module for Research GUI

Contains reusable functions for building UI components with consistent styling
and short, focused functions.
"""

import flet as ft
from typing import Optional, List, Any
from ..cli.workflow_steps import WorkflowStep


def create_header() -> ft.Container:
    """Create the main header section."""
    return ft.Container(
        content=ft.Column([
            ft.Text(
                "BMLibrarian Research Assistant",
                size=28,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.BLUE_700
            ),
            ft.Text(
                "AI-Powered Evidence-Based Medical Literature Research",
                size=14,
                color=ft.Colors.GREY_600
            )
        ], spacing=5),
        margin=ft.margin.only(bottom=20)
    )


def create_question_field(on_change_handler) -> ft.TextField:
    """Create the research question input field."""
    return ft.TextField(
        label="Enter your medical research question",
        hint_text="e.g., What are the cardiovascular benefits of regular exercise in adults?",
        multiline=True,
        min_lines=3,
        max_lines=6,
        expand=True,
        on_change=on_change_handler
    )


def create_toggle_switch(label: str, value: bool, on_change_handler) -> ft.Switch:
    """Create a toggle switch with consistent styling."""
    return ft.Switch(
        label=label,
        value=value,
        on_change=on_change_handler
    )


def create_start_button(on_click_handler) -> ft.ElevatedButton:
    """Create the main start research button."""
    return ft.ElevatedButton(
        "Start Research",
        icon=ft.Icons.SEARCH,
        on_click=on_click_handler,
        style=ft.ButtonStyle(
            bgcolor=ft.Colors.BLUE_600,
            color=ft.Colors.WHITE
        ),
        height=45,
        width=160,
        disabled=True
    )


def create_max_results_field(value: int, on_change_handler) -> ft.TextField:
    """Create the max search results input field."""
    return ft.TextField(
        label="Max Results",
        hint_text="100",
        value=str(value),
        width=120,
        height=45,
        text_align=ft.TextAlign.CENTER,
        on_blur=on_change_handler,  # Use on_blur instead of on_change to avoid constant updates
        input_filter=ft.NumbersOnlyInputFilter()
    )


def create_min_relevant_field(value: int, on_change_handler) -> ft.TextField:
    """Create the min relevant docs input field."""
    return ft.TextField(
        label="Min Relevant",
        hint_text="10",
        value=str(value),
        width=120,
        height=45,
        text_align=ft.TextAlign.CENTER,
        on_blur=on_change_handler,  # Use on_blur instead of on_change to avoid constant updates
        input_filter=ft.NumbersOnlyInputFilter(),
        tooltip="Minimum high-scoring documents to find (triggers iterative search)"
    )


def create_controls_section(
    question_field: ft.TextField,
    max_results_field: ft.TextField,
    min_relevant_field: ft.TextField,
    human_loop_toggle: ft.Switch,
    counterfactual_toggle: ft.Switch,
    start_button: ft.ElevatedButton
) -> ft.Container:
    """Create the controls section with reorganized layout."""
    # First row: Question field and Start button
    first_row = ft.Row([
        question_field,
        ft.Container(width=20),  # Spacer
        start_button
    ], alignment=ft.MainAxisAlignment.START,
       vertical_alignment=ft.CrossAxisAlignment.END)

    # Second row: Max results, Min relevant, Interactive toggle, and Counterfactual toggle
    second_row = ft.Row([
        max_results_field,
        ft.Container(width=10),  # Smaller spacer
        min_relevant_field,
        ft.Container(width=20),  # Spacer
        human_loop_toggle,
        ft.Container(width=20),  # Spacer
        counterfactual_toggle
    ], alignment=ft.MainAxisAlignment.START,
       vertical_alignment=ft.CrossAxisAlignment.CENTER)

    return ft.Container(
        content=ft.Column([
            first_row,
            second_row
        ], spacing=15),
        padding=ft.padding.all(15),
        bgcolor=ft.Colors.GREY_50,
        border_radius=10,
        margin=ft.margin.only(bottom=15)
    )


def create_tab_header(title: str, count: Optional[int] = None, subtitle: str = "") -> List[ft.Control]:
    """Create standardized tab header with title, optional count, and subtitle."""
    main_title = f"{title} ({count})" if count is not None else title
    
    components: List[ft.Control] = [
        ft.Text(
            main_title,
            size=18,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_700
        )
    ]
    
    if subtitle:
        components.append(
            ft.Text(
                subtitle,
                size=14,
                color=ft.Colors.GREY_600
            )
        )
    
    return components


def create_empty_state(message: str) -> ft.Container:
    """Create a standardized empty state container."""
    return ft.Container(
        content=ft.Text(message),
        padding=ft.padding.all(20),
        bgcolor=ft.Colors.GREY_50,
        border_radius=5
    )


def create_score_badge(score: float, max_score: float = 5.0) -> ft.Container:
    """Create a colored score badge based on score value."""
    def get_score_color(score_val: float) -> str:
        if score_val >= 4.5:
            return ft.Colors.GREEN_700
        elif score_val >= 3.5:
            return ft.Colors.BLUE_700
        elif score_val >= 2.5:
            return ft.Colors.ORANGE_700
        else:
            return ft.Colors.RED_700
    
    return ft.Container(
        content=ft.Text(
            f"{score:.1f}",
            size=12,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.WHITE
        ),
        bgcolor=get_score_color(score),
        padding=ft.padding.symmetric(horizontal=8, vertical=4),
        border_radius=12,
        margin=ft.margin.only(left=10)
    )


def create_relevance_badge(relevance: float) -> ft.Container:
    """Create a colored relevance badge (0-1 range)."""
    def get_relevance_color(rel_val: float) -> str:
        if rel_val >= 0.8:
            return ft.Colors.GREEN_700
        elif rel_val >= 0.6:
            return ft.Colors.BLUE_700
        elif rel_val >= 0.4:
            return ft.Colors.ORANGE_700
        else:
            return ft.Colors.RED_700
    
    return ft.Container(
        content=ft.Text(
            f"{relevance:.2f}",
            size=12,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.WHITE
        ),
        bgcolor=get_relevance_color(relevance),
        padding=ft.padding.symmetric(horizontal=8, vertical=4),
        border_radius=12,
        margin=ft.margin.only(left=10)
    )


def create_priority_badge(priority: str) -> ft.Container:
    """Create a colored priority badge."""
    def get_priority_color(priority_val: str) -> str:
        if priority_val == "HIGH":
            return ft.Colors.RED_700
        elif priority_val == "MEDIUM":
            return ft.Colors.ORANGE_700
        else:
            return ft.Colors.GREEN_700
    
    return ft.Container(
        content=ft.Text(
            priority,
            size=10,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.WHITE
        ),
        bgcolor=get_priority_color(priority),
        padding=ft.padding.symmetric(horizontal=8, vertical=4),
        border_radius=12
    )


def create_metadata_section(items: List[tuple], bg_color: str = ft.Colors.GREY_50) -> ft.Container:
    """Create a metadata section with key-value pairs."""
    metadata_items = []
    for key, value in items:
        if value and str(value).strip():
            metadata_items.append(
                ft.Text(
                    f"{key}: {value}",
                    size=10,
                    color=ft.Colors.GREY_600
                )
            )
    
    return ft.Container(
        content=ft.Column(metadata_items, spacing=4),
        padding=ft.padding.only(bottom=8),
        bgcolor=bg_color,
        border_radius=5
    ) if metadata_items else ft.Container()


def create_text_content_section(title: str, content: str, 
                               bg_color: str = ft.Colors.GREY_100,
                               selectable: bool = True,
                               italic: bool = False) -> ft.Container:
    """Create a text content section with title and body."""
    return ft.Container(
        content=ft.Column([
            ft.Text(
                title,
                size=11,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.BLACK
            ),
            ft.Text(
                content,
                size=10,
                color=ft.Colors.GREY_800,
                selectable=selectable,
                italic=italic
            )
        ], spacing=4),
        padding=ft.padding.all(8),
        bgcolor=bg_color,
        border_radius=5
    )


def create_action_button_row(buttons: List[dict]) -> ft.Row:
    """Create a row of action buttons.
    
    Args:
        buttons: List of button configs with keys: text, icon, on_click, style (optional)
    """
    button_widgets = []
    
    for btn_config in buttons:
        style = btn_config.get('style', {})
        button = ft.ElevatedButton(
            btn_config['text'],
            icon=btn_config.get('icon'),
            on_click=btn_config['on_click'],
            height=40
        )
        
        # Apply custom style if provided
        if 'bgcolor' in style or 'color' in style:
            button.style = ft.ButtonStyle(
                bgcolor=style.get('bgcolor'),
                color=style.get('color')
            )
        
        button_widgets.append(button)
    
    return ft.Row(
        button_widgets,
        spacing=10,
        alignment=ft.MainAxisAlignment.END
    )


def truncate_text(text: str, max_length: int = 80) -> str:
    """Truncate text to specified length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def extract_year_from_date(date_str: str) -> str:
    """Extract year from publication date string."""
    if not date_str or str(date_str).strip() in ['', 'Unknown', 'None']:
        return 'Unknown'
    
    date_clean = str(date_str).strip()
    if '-' in date_clean:
        return date_clean.split('-')[0]
    return date_clean


def format_authors_list(authors: List[str], max_count: int = 3) -> str:
    """Format authors list with truncation."""
    if not authors:
        return 'Unknown authors'
    
    if len(authors) <= max_count:
        return ', '.join(authors)
    
    return ', '.join(authors[:max_count]) + '...'


def create_expandable_card(
    title_text: str,
    subtitle_text: str,
    content_sections: List[ft.Control],
    badges: Optional[List[ft.Control]] = None
) -> ft.ExpansionTile:
    """Create a standardized expandable card."""
    title_row: List[ft.Control] = [ft.Text(
        title_text,
        size=12,
        weight=ft.FontWeight.W_500,
        color=ft.Colors.BLUE_800
    )]
    
    if badges:
        title_row.extend(badges)
    
    return ft.ExpansionTile(
        title=ft.Row(title_row, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        subtitle=ft.Text(
            subtitle_text,
            size=11,
            color=ft.Colors.GREY_600
        ),
        controls=[
            ft.Container(
                content=ft.Column(content_sections, spacing=4),
                padding=ft.padding.all(10)
            )
        ]
    )