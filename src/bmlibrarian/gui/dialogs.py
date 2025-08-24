"""
Dialog Handlers for BMLibrarian Research GUI

Contains all dialog-related functionality including success, error, preview, and save dialogs.
"""

import os
import flet as ft
from datetime import datetime
from typing import Optional


class DialogManager:
    """Manages all dialog interactions for the research GUI."""
    
    def __init__(self, page: ft.Page):
        self.page = page
    
    def show_success_dialog(self, message: str):
        """Show success dialog."""
        def close_success(e):
            self.page.dialog.open = False
            self.page.dialog = None
            self.page.update()
            
        self.page.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Success", color=ft.Colors.GREEN_700),
            content=ft.Text(message),
            actions=[ft.TextButton("OK", on_click=close_success)]
        )
        self.page.dialog.open = True
        self.page.update()
    
    def show_error_dialog(self, message: str):
        """Show error dialog."""
        def close_error(e):
            self.page.dialog.open = False
            self.page.dialog = None
            self.page.update()
            
        self.page.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Error", color=ft.Colors.RED_700),
            content=ft.Text(message),
            actions=[ft.TextButton("OK", on_click=close_error)]
        )
        self.page.dialog.open = True
        self.page.update()
    
    def show_confirm_dialog(self, title: str, message: str, callback):
        """Show confirmation dialog."""
        def handle_cancel(e):
            self.page.dialog.open = False
            self.page.dialog = None
            self.page.update()
            callback(False)
            
        def handle_confirm(e):
            self.page.dialog.open = False
            self.page.dialog = None
            self.page.update()
            callback(True)
        
        self.page.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title, color=ft.Colors.ORANGE_700),
            content=ft.Text(message),
            actions=[
                ft.TextButton("Cancel", on_click=handle_cancel),
                ft.TextButton("Confirm", on_click=handle_confirm)
            ]
        )
        self.page.dialog.open = True
        self.page.update()
    
    def show_preview_dialog(self, report_content: str):
        """Show report preview dialog."""
        if not report_content:
            self.show_error_dialog("No report available to preview")
            return
        
        def close_preview(e):
            self.page.dialog.open = False
            self.page.dialog = None
            self.page.update()
        
        # Debug: Check if we have a report
        print(f"Preview dialog: Report length = {len(report_content) if report_content else 0}")
        
        # Create a simple text display - limit size for stability
        try:
            preview_text = ft.TextField(
                value=report_content[:5000] + ("..." if len(report_content) > 5000 else ""),
                multiline=True,
                read_only=True,
                min_lines=20,
                max_lines=20,
                width=600,
                expand=False
            )
            
            self.page.dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Report Preview"),
                content=ft.Container(
                    content=preview_text,
                    width=600,
                    height=400
                ),
                actions=[ft.TextButton("Close", on_click=close_preview)],
                actions_alignment=ft.MainAxisAlignment.END
            )
            
            self.page.dialog.open = True
            self.page.update()
            print("Preview dialog created and opened - dialog should be visible now")
            
        except Exception as ex:
            print(f"Error creating preview dialog: {ex}")
            self.show_error_dialog(f"Failed to open preview: {str(ex)}")
    
    def show_save_dialog(self, report_content: str, success_callback=None):
        """Show save report dialog with path input (macOS-compatible)."""
        print(f"show_save_dialog called with report length: {len(report_content) if report_content else 0}")
        if not report_content:
            self.show_error_dialog("No report available to save")
            return
        
        # Use a simple text input dialog instead of FilePicker (which has bugs on macOS)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_path = f"~/Desktop/research_report_{timestamp}.md"
        
        def save_with_path(file_path):
            try:
                # Expand user path
                expanded_path = os.path.expanduser(file_path)
                
                # Add .md extension if not present
                if not expanded_path.endswith('.md'):
                    expanded_path += '.md'
                
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(expanded_path), exist_ok=True)
                
                # Save the file
                with open(expanded_path, 'w', encoding='utf-8') as f:
                    f.write(report_content)
                
                self.show_success_dialog(f"Report saved successfully to:\n{expanded_path}")
                
                if success_callback:
                    success_callback(expanded_path)
                
            except Exception as ex:
                self.show_error_dialog(f"Failed to save report: {str(ex)}")
        
        def handle_save(e):
            file_path = path_field.value.strip()
            if file_path:
                self.page.dialog.open = False
                self.page.dialog = None
                self.page.update()
                save_with_path(file_path)
            else:
                self.show_error_dialog("Please enter a file path")
        
        def handle_cancel(e):
            self.page.dialog.open = False
            self.page.dialog = None
            self.page.update()
        
        # Create path input field
        path_field = ft.TextField(
            label="Save report to:",
            value=default_path,
            width=500,
            hint_text="Enter full file path (e.g., ~/Desktop/my_report.md)"
        )
        
        self.page.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Save Research Report"),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("Enter the path where you want to save the report:"),
                    path_field
                ], spacing=10),
                width=500,
                height=120
            ),
            actions=[
                ft.TextButton("Cancel", on_click=handle_cancel),
                ft.ElevatedButton("Save", on_click=handle_save)
            ]
        )
        
        self.page.dialog.open = True
        self.page.update()
        print("Save dialog opened and page updated")
    
    def copy_to_clipboard(self, content: str):
        """Copy content to clipboard."""
        try:
            self.page.set_clipboard(content)
            self.show_success_dialog("Content copied to clipboard!")
        except Exception as ex:
            self.show_error_dialog(f"Failed to copy to clipboard: {str(ex)}")