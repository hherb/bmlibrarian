"""
Dialog components for Fact Checker Review GUI.

Provides dialog windows for annotator information, file selection, and confirmations.
"""

from typing import Optional, Callable
import flet as ft


class AnnotatorDialog:
    """Dialog for collecting annotator information at startup."""

    def __init__(self, page: ft.Page, on_complete: Callable):
        """
        Initialize annotator dialog.

        Args:
            page: Flet page instance
            on_complete: Callback function to call when dialog is complete
        """
        self.page = page
        self.on_complete = on_complete
        self.annotator_info = None

        # Create input fields
        self.username_field = ft.TextField(
            label="Your Username/ID *",
            hint_text="e.g., jsmith",
            width=300,
            autofocus=True
        )

        self.full_name_field = ft.TextField(
            label="Full Name (optional)",
            hint_text="e.g., John Smith",
            width=300
        )

        self.email_field = ft.TextField(
            label="Email (optional)",
            hint_text="e.g., john@example.com",
            width=300
        )

        self.expertise_dropdown = ft.Dropdown(
            label="Expertise Level (optional)",
            options=[
                ft.dropdown.Option("expert", "Expert"),
                ft.dropdown.Option("intermediate", "Intermediate"),
                ft.dropdown.Option("novice", "Novice")
            ],
            width=300
        )

    def show(self):
        """Show the annotator information dialog."""
        def on_continue(e):
            if not self.username_field.value:
                self.username_field.error_text = "Username is required"
                self.page.update()
                return

            self.annotator_info = {
                'username': self.username_field.value,
                'full_name': self.full_name_field.value or None,
                'email': self.email_field.value or None,
                'expertise_level': self.expertise_dropdown.value or None
            }

            dialog.open = False
            self.page.update()

            # Call completion callback
            if self.on_complete:
                self.on_complete(self.annotator_info)

        dialog = ft.AlertDialog(
            title=ft.Text("Annotator Information", size=20, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(
                        "Please enter your information for annotation tracking:",
                        size=13,
                        color=ft.Colors.GREY_700
                    ),
                    ft.Container(height=15),
                    self.username_field,
                    self.full_name_field,
                    self.email_field,
                    self.expertise_dropdown
                ], tight=True),
                padding=ft.padding.all(10),
                width=400
            ),
            actions=[
                ft.ElevatedButton(
                    "Continue",
                    on_click=on_continue,
                    bgcolor=ft.Colors.BLUE_700,
                    color=ft.Colors.WHITE
                )
            ],
            modal=True
        )

        self.page.overlay.append(dialog)
        dialog.open = True
        self.page.update()


def show_error_dialog(page: ft.Page, message: str):
    """
    Show error dialog.

    Args:
        page: Flet page instance
        message: Error message to display
    """
    def close_dialog(e):
        dialog.open = False
        page.update()

    dialog = ft.AlertDialog(
        title=ft.Text("Error", color=ft.Colors.RED_700),
        content=ft.Text(message),
        actions=[
            ft.TextButton("OK", on_click=close_dialog)
        ]
    )
    page.overlay.append(dialog)
    dialog.open = True
    page.update()


def show_success_dialog(page: ft.Page, message: str):
    """
    Show success dialog.

    Args:
        page: Flet page instance
        message: Success message to display
    """
    def close_dialog(e):
        dialog.open = False
        page.update()

    dialog = ft.AlertDialog(
        title=ft.Text("Success", color=ft.Colors.GREEN_700),
        content=ft.Text(message),
        actions=[
            ft.TextButton("OK", on_click=close_dialog)
        ]
    )
    page.overlay.append(dialog)
    dialog.open = True
    page.update()


def show_save_dialog(page: ft.Page, default_path: str, on_save: Callable):
    """
    Show save file dialog.

    Args:
        page: Flet page instance
        default_path: Default file path
        on_save: Callback function with file path argument
    """
    save_path_field = ft.TextField(
        label="Output file path",
        value=default_path,
        width=500
    )

    def on_save_confirm(e):
        output_path = save_path_field.value
        if output_path:
            dialog.open = False
            page.update()
            on_save(output_path)

    def on_cancel(e):
        dialog.open = False
        page.update()

    dialog = ft.AlertDialog(
        title=ft.Text("Save Reviewed Annotations"),
        content=ft.Container(
            content=save_path_field,
            padding=ft.padding.all(10)
        ),
        actions=[
            ft.TextButton("Cancel", on_click=on_cancel),
            ft.ElevatedButton(
                "Save",
                on_click=on_save_confirm,
                bgcolor=ft.Colors.GREEN_700,
                color=ft.Colors.WHITE
            )
        ]
    )

    page.overlay.append(dialog)
    dialog.open = True
    page.update()
