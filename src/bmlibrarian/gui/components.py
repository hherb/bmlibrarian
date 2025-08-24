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
        self.status = "pending"  # pending, running, completed, error
        self.content = ""
        self.error_message = ""
        self.on_expand_change = on_expand_change
        
        # UI components
        self.expansion_tile = None
        self.content_text = None
        self.status_icon = None
        self.progress_bar = None
        
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
            "error": ft.Icons.ERROR
        }
        return icons.get(self.status, ft.Icons.HELP)
    
    def _get_status_color(self) -> str:
        """Get the color for the current status."""
        colors = {
            "pending": ft.Colors.GREY_500,
            "running": ft.Colors.BLUE_500,
            "completed": ft.Colors.GREEN_500,
            "error": ft.Colors.RED_500
        }
        return colors.get(self.status, ft.Colors.GREY_500)
    
    def _on_expand_change(self, e):
        """Handle expansion tile change."""
        self.expanded = e.data == "true"
        if self.on_expand_change:
            self.on_expand_change(self, self.expanded)