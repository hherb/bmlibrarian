#!/usr/bin/env python3
"""
Test script for Document Interrogation GUI.

Quick visual test to ensure the tab loads and displays correctly.
"""

import flet as ft
from src.bmlibrarian.gui.config_app import BMLibrarianConfigApp


def test_document_interrogation_tab():
    """Test the document interrogation tab in isolation."""

    def main(page: ft.Page):
        page.title = "Document Interrogation Test"
        page.window.width = 1200
        page.window.height = 800

        # Create app instance
        app = BMLibrarianConfigApp()
        app.page = page

        # Create just the document interrogation tab
        from src.bmlibrarian.gui.tabs import DocumentInterrogationTab
        doc_tab = DocumentInterrogationTab(app)

        # Build and display
        content = doc_tab.build()

        page.add(
            ft.Column([
                ft.Text("Document Interrogation Tab Test", size=20, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                content
            ],
            expand=True
            )
        )

        print("✅ Document Interrogation tab loaded successfully!")
        print("   - Top bar with file selector and model dropdown")
        print("   - Split pane layout (60% document / 40% chat)")
        print("   - Chat interface with message bubbles")
        print("")
        print("Test the following:")
        print("1. Click 'Load Document' button")
        print("2. Select a .md, .txt, or .pdf file")
        print("3. Select a model from dropdown")
        print("4. Type a message in the chat input")
        print("5. Click Send or press Enter")

    ft.app(target=main, view=ft.FLET_APP)


def test_full_config_gui():
    """Test the full config GUI with the new tab."""
    from src.bmlibrarian.gui.config_app import run_config_app

    print("✅ Testing full configuration GUI...")
    print("   Look for 'Document Interrogation' tab (chat icon)")
    print("")

    run_config_app()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        print("Running FULL CONFIG GUI test...")
        test_full_config_gui()
    else:
        print("Running ISOLATED TAB test...")
        print("(Use --full flag to test full config GUI)")
        print("")
        test_document_interrogation_tab()
