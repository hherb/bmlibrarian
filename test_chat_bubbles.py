#!/usr/bin/env python3
"""Quick test for improved chat bubble layout."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from PySide6.QtWidgets import QApplication
from bmlibrarian.gui.qt.plugins.document_interrogation.document_interrogation_tab import (
    DocumentInterrogationTabWidget
)


def main():
    """Test the document interrogation tab with improved chat bubbles."""
    app = QApplication(sys.argv)

    # Create the widget
    widget = DocumentInterrogationTabWidget()

    # Add some test messages to see the bubble layout
    widget._add_chat_bubble("Hello! This is a short user message.", is_user=True)
    widget._add_chat_bubble(
        "This is a longer AI response that should demonstrate how the bubbles "
        "expand horizontally to make better use of available space. The bubble "
        "should have rounded corners, proper padding, and the icon should be "
        "positioned outside on the left side.",
        is_user=False
    )
    widget._add_chat_bubble(
        "Another user message to test the left alignment with asymmetric padding. "
        "The icon should always be on the left, and there should be minor padding "
        "on the left side with more padding on the right.",
        is_user=True
    )
    widget._add_chat_bubble(
        "And another AI response. Notice how the bubbles are right-aligned but "
        "the icons remain on the left side. This creates a nice visual flow "
        "where you can easily distinguish between user and AI messages.",
        is_user=False
    )

    # Show the widget
    widget.setWindowTitle("Chat Bubble Test")
    widget.resize(800, 600)
    widget.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
