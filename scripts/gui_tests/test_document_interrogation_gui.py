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
        page.window.width = 1400
        page.window.height = 900

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
        print("1. Load Document (PDF, Markdown, or Text)")
        print("   - Click 'Load Document' button")
        print("   - Select a .md, .txt, or .pdf file")
        print("")
        print("2. PDF Features (if PDF loaded)")
        print("   - Navigate pages with arrow buttons")
        print("   - Zoom in/out with zoom controls")
        print("   - Search for text in PDF")
        print("   - Navigate between search results")
        print("")
        print("3. Chat Interface")
        print("   - Select a model from dropdown")
        print("   - Type a message in the chat input")
        print("   - Click Send or press Enter")
        print("")
        print("4. Programmatic API (via Python console)")
        print("   - doc_tab.search_pdf('keyword')")
        print("   - doc_tab.highlight_pdf_region(0, (100, 100, 300, 120))")
        print("   - doc_tab.jump_to_pdf_page(5)")
        print("   - doc_tab.clear_pdf_highlights()")

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
