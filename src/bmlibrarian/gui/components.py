"""
GUI Components for BMLibrarian Research Interface

Contains reusable UI components like StepCard for workflow progress tracking.
"""

import flet as ft
from typing import Optional, Callable
from ..cli.workflow_steps import WorkflowStep


class StepCard:
    """A collapsible card representing a workflow step."""
    
    def __init__(self, step: WorkflowStep, on_expand_change: Optional[Callable] = None):
        self.step = step
        self.expanded = False
        self.status = "pending"  # pending, running, completed, error, waiting
        self.content = ""
        self.error_message = ""
        self.on_expand_change = on_expand_change
        
        # UI components
        self.expansion_tile = None
        self.content_text = None
        self.status_icon = None
        self.progress_bar = None
        
        # Inline editing components
        self.editing_mode = False
        self.edit_field = None
        self.accept_button = None
        self.cancel_button = None
        self.edit_container = None
        self.edit_callback = None
        
    def build(self) -> ft.ExpansionTile:
        """Build the expansion tile UI component."""
        # Status icon based on current status
        self.status_icon = ft.Icon(
            name=self._get_status_icon(),
            color=self._get_status_color(),
            size=20
        )
        
        # Progress bar for running status
        self.progress_bar = ft.ProgressBar(
            visible=False,
            height=4,
            color=ft.Colors.BLUE_400
        )
        
        # Content text area
        self.content_text = ft.Text(
            value=self.content or "Waiting to start...",
            size=12,
            color=ft.Colors.GREY_700,
            selectable=True
        )
        
        # Content container
        content_container = ft.Container(
            content=ft.Column([
                self.progress_bar,
                ft.Container(
                    content=self.content_text,
                    padding=ft.padding.all(10),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=5
                )
            ], spacing=5),
            padding=ft.padding.only(left=10, right=10, bottom=10)
        )
        
        # Build expansion tile with minimal parameters
        self.expansion_tile = ft.ExpansionTile(
            title=ft.Row([
                self.status_icon,
                ft.Text(self.step.display_name, size=14, weight=ft.FontWeight.W_500),
            ], spacing=8),
            subtitle=ft.Text(self.step.description, size=12, color=ft.Colors.GREY_600),
            controls=[content_container]
        )
        
        return self.expansion_tile
    
    def update_status(self, status: str, content: str = None, error: str = None):
        """Update the step status and content."""
        self.status = status
        if content is not None:
            self.content = content
        if error is not None:
            self.error_message = error
            
        # Update UI components if they exist
        if self.status_icon:
            self.status_icon.name = self._get_status_icon()
            self.status_icon.color = self._get_status_color()
            
        if self.progress_bar:
            self.progress_bar.visible = (status == "running")
            
        if self.content_text:
            display_content = self.content
            if self.error_message:
                display_content += f"\n\nError: {self.error_message}"
            self.content_text.value = display_content or "Waiting to start..."
    
    def _get_status_icon(self) -> str:
        """Get the icon name for the current status."""
        icons = {
            "pending": ft.Icons.SCHEDULE,
            "running": ft.Icons.REFRESH,
            "completed": ft.Icons.CHECK_CIRCLE,
            "error": ft.Icons.ERROR,
            "waiting": ft.Icons.EDIT
        }
        return icons.get(self.status, ft.Icons.HELP)
    
    def _get_status_color(self) -> str:
        """Get the color for the current status."""
        colors = {
            "pending": ft.Colors.GREY_500,
            "running": ft.Colors.BLUE_500,
            "completed": ft.Colors.GREEN_500,
            "error": ft.Colors.RED_500,
            "waiting": ft.Colors.ORANGE_500
        }
        return colors.get(self.status, ft.Colors.GREY_500)
    
    def _on_expand_change(self, e):
        """Handle expansion tile change."""
        self.expanded = e.data == "true"
        if self.on_expand_change:
            self.on_expand_change(self, self.expanded)
    
    def enable_inline_editing(self, initial_text: str, callback: Callable[[bool, str], None]):
        """Enable inline editing mode with text field and accept/cancel buttons."""
        self.editing_mode = True
        self.edit_callback = callback
        
        # Create edit field
        self.edit_field = ft.TextField(
            value=initial_text,
            multiline=True,
            min_lines=3,
            max_lines=8,
            expand=True,
            hint_text="Edit the query as needed (no markdown formatting)"
        )
        
        # Create buttons
        self.accept_button = ft.ElevatedButton(
            "Accept",
            icon=ft.Icons.CHECK,
            on_click=self._on_accept_edit,
            bgcolor=ft.Colors.GREEN_600,
            color=ft.Colors.WHITE,
            height=36
        )
        
        self.cancel_button = ft.TextButton(
            "Cancel",
            icon=ft.Icons.CLOSE,
            on_click=self._on_cancel_edit,
            height=36
        )
        
        # Create edit container
        self.edit_container = ft.Container(
            content=ft.Column([
                ft.Text("Edit Query:", size=12, weight=ft.FontWeight.BOLD),
                ft.Text("Use & for AND, | for OR, () for grouping. No backticks or markdown.", 
                        size=10, color=ft.Colors.GREY_600),
                self.edit_field,
                ft.Row([
                    self.accept_button,
                    self.cancel_button
                ], spacing=10, alignment=ft.MainAxisAlignment.END)
            ], spacing=10),
            padding=ft.padding.all(10),
            bgcolor=ft.Colors.YELLOW_50,
            border=ft.border.all(2, ft.Colors.ORANGE_300),
            border_radius=5
        )
        
        # Replace content container with edit container
        if self.expansion_tile and len(self.expansion_tile.controls) > 0:
            # Get the content container and replace it
            content_container = self.expansion_tile.controls[0]
            if hasattr(content_container, 'content') and hasattr(content_container.content, 'controls'):
                # Add edit container after progress bar
                content_container.content.controls = [
                    self.progress_bar,
                    self.edit_container,
                    ft.Container(
                        content=self.content_text,
                        padding=ft.padding.all(10),
                        bgcolor=ft.Colors.GREY_50,
                        border_radius=5
                    )
                ]
        
        # Auto-expand the tile to show editing interface
        if self.expansion_tile:
            self.expansion_tile.initially_expanded = True
    
    def disable_inline_editing(self):
        """Disable inline editing mode and return to normal view."""
        self.editing_mode = False
        self.edit_callback = None
        
        # Remove edit container and restore normal content
        if self.expansion_tile and len(self.expansion_tile.controls) > 0:
            content_container = self.expansion_tile.controls[0]
            if hasattr(content_container, 'content') and hasattr(content_container.content, 'controls'):
                # Restore original content structure
                content_container.content.controls = [
                    self.progress_bar,
                    ft.Container(
                        content=self.content_text,
                        padding=ft.padding.all(10),
                        bgcolor=ft.Colors.GREY_50,
                        border_radius=5
                    )
                ]
    
    def _on_accept_edit(self, e):
        """Handle accept button click."""
        if self.edit_callback and self.edit_field:
            edited_text = self.edit_field.value or ""
            self.edit_callback(True, edited_text)
    
    def _on_cancel_edit(self, e):
        """Handle cancel button click."""
        if self.edit_callback:
            self.edit_callback(False, "")