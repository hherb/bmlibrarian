"""
Document Card Factory Demo

Demonstrates how to use the document card factory pattern to create
consistent PySide6/Qt document cards with three-state PDF buttons.

Usage:
    uv run python examples/document_card_factory_demo.py
"""

import sys
from pathlib import Path

# Add src to path for imports when run from a source checkout
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# Example: Using the Qt Factory
def qt_example():
    """Example of creating document cards with Qt."""
    from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel
    from bmlibrarian.gui.qt.qt_document_card_factory import QtDocumentCardFactory
    from bmlibrarian.gui.document_card_factory_base import (
        DocumentCardData, CardContext
    )

    app = QApplication(sys.argv)

    # Create factory
    factory = QtDocumentCardFactory(
        pdf_manager=None,
        base_pdf_dir=Path.home() / "knowledgebase" / "pdf"
    )

    # Example document cards
    card_data_1 = DocumentCardData(
        doc_id=12345,
        title="Cardiovascular Benefits of Regular Exercise: A Meta-Analysis",
        abstract="This comprehensive meta-analysis examines the cardiovascular benefits...",
        authors=["Smith J", "Johnson A", "Williams B"],
        year=2023,
        journal="Journal of Cardiology",
        pmid="12345678",
        doi="10.1234/jcard.2023.001",
        relevance_score=4.5,
        context=CardContext.LITERATURE,
        show_pdf_button=True
    )

    card_data_2 = DocumentCardData(
        doc_id=23456,
        title="Novel Biomarkers for Early Detection of Alzheimer's Disease",
        abstract="Recent advances in proteomics have identified several novel biomarkers...",
        authors=["Chen X", "Rodriguez M", "Kim S"],
        year=2024,
        journal="Nature Neuroscience",
        doi="10.1038/nn.2024.456",
        relevance_score=3.8,
        pdf_url="https://example.com/paper.pdf",
        context=CardContext.SCORING,
        show_pdf_button=True
    )

    # Create main window
    window = QMainWindow()
    window.setWindowTitle("Qt Document Card Factory Demo")
    window.setGeometry(100, 100, 800, 600)

    # Create central widget with layout
    central_widget = QWidget()
    layout = QVBoxLayout(central_widget)

    # Add title
    title = QLabel("Document Card Factory Demo")
    title.setStyleSheet("font-size: 18pt; font-weight: bold; margin: 10px;")
    layout.addWidget(title)

    # Create and add cards
    layout.addWidget(QLabel("Card 1: Literature Context"))
    card1 = factory.create_card(card_data_1)
    layout.addWidget(card1)

    layout.addWidget(QLabel("\nCard 2: Scoring Context with PDF Fetch"))
    card2 = factory.create_card(card_data_2)
    layout.addWidget(card2)

    layout.addStretch()

    window.setCentralWidget(central_widget)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    qt_example()
