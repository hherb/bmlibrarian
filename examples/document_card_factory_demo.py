"""
Document Card Factory Demo

Demonstrates how to use the document card factory pattern to create
consistent document cards across different UI frameworks (Flet and Qt).
"""

import sys
from pathlib import Path

# Example 1: Using Flet Factory
def flet_example():
    """Example of creating document cards with Flet."""
    import flet as ft
    from bmlibrarian.gui.flet_document_card_factory import FletDocumentCardFactory
    from bmlibrarian.gui.document_card_factory_base import (
        DocumentCardData, CardContext, PDFButtonConfig, PDFButtonState
    )

    def main(page: ft.Page):
        page.title = "Flet Document Card Factory Demo"
        page.padding = 20

        # Create factory
        factory = FletDocumentCardFactory(
            page=page,
            pdf_manager=None,  # Optional PDF manager
            base_pdf_dir=Path.home() / "knowledgebase" / "pdf"
        )

        # Example 1: Card with VIEW PDF button (local PDF exists)
        card_data_view = DocumentCardData(
            doc_id=12345,
            title="Cardiovascular Benefits of Regular Exercise: A Meta-Analysis",
            abstract="This comprehensive meta-analysis examines the cardiovascular benefits...",
            authors=["Smith J", "Johnson A", "Williams B"],
            year=2023,
            journal="Journal of Cardiology",
            pmid="12345678",
            doi="10.1234/jcard.2023.001",
            relevance_score=4.5,
            pdf_path=Path("/path/to/existing.pdf"),  # If file exists, shows VIEW button
            context=CardContext.LITERATURE,
            show_pdf_button=True
        )

        # Example 2: Card with FETCH PDF button (URL available)
        card_data_fetch = DocumentCardData(
            doc_id=23456,
            title="Novel Biomarkers for Early Detection of Alzheimer's Disease",
            abstract="Recent advances in proteomics have identified several novel biomarkers...",
            authors=["Chen X", "Rodriguez M", "Kim S", "et al."],
            year=2024,
            journal="Nature Neuroscience",
            doi="10.1038/nn.2024.456",
            relevance_score=3.8,
            pdf_url="https://example.com/paper.pdf",  # URL available, shows FETCH button
            context=CardContext.SCORING,
            show_pdf_button=True
        )

        # Example 3: Card with UPLOAD PDF button (no PDF available)
        card_data_upload = DocumentCardData(
            doc_id=34567,
            title="Machine Learning in Medical Diagnosis: Current State and Future Directions",
            abstract="This review explores the application of machine learning algorithms...",
            authors=["Anderson T", "Brown K"],
            year=2023,
            journal="AI in Medicine",
            pmid="34567890",
            relevance_score=2.9,
            # No pdf_path or pdf_url, shows UPLOAD button
            context=CardContext.CITATIONS,
            show_pdf_button=True
        )

        # Create cards using factory
        card1 = factory.create_card(card_data_view)
        card2 = factory.create_card(card_data_fetch)
        card3 = factory.create_card(card_data_upload)

        # Add to page
        page.add(
            ft.Text("Document Card Factory Demo", size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text("Card 1: With local PDF (VIEW button)", size=16, weight=ft.FontWeight.BOLD),
            card1,
            ft.Divider(),
            ft.Text("Card 2: With PDF URL (FETCH button)", size=16, weight=ft.FontWeight.BOLD),
            card2,
            ft.Divider(),
            ft.Text("Card 3: No PDF (UPLOAD button)", size=16, weight=ft.FontWeight.BOLD),
            card3,
        )

    ft.app(target=main)


# Example 2: Using Qt Factory
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


# Example 3: Custom PDF Button Configuration
def custom_pdf_button_example():
    """Example of creating custom PDF buttons with custom handlers."""
    import flet as ft
    from bmlibrarian.gui.flet_document_card_factory import FletDocumentCardFactory
    from bmlibrarian.gui.document_card_factory_base import PDFButtonConfig, PDFButtonState
    from pathlib import Path

    def main(page: ft.Page):
        page.title = "Custom PDF Button Demo"
        page.padding = 20

        factory = FletDocumentCardFactory(page=page)

        # Custom handlers
        def custom_view_handler():
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Custom view handler called!"),
                bgcolor=ft.Colors.GREEN
            )
            page.snack_bar.open = True
            page.update()

        def custom_fetch_handler():
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Custom fetch handler called!"),
                bgcolor=ft.Colors.ORANGE
            )
            page.snack_bar.open = True
            page.update()
            return Path("/tmp/downloaded.pdf")  # Return path after download

        def custom_upload_handler():
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Custom upload handler called!"),
                bgcolor=ft.Colors.BLUE
            )
            page.snack_bar.open = True
            page.update()
            return Path("/tmp/uploaded.pdf")  # Return path after upload

        # Create custom PDF button configurations
        view_config = PDFButtonConfig(
            state=PDFButtonState.VIEW,
            pdf_path=Path("/path/to/existing.pdf"),
            on_view=custom_view_handler,
            show_notifications=True
        )

        fetch_config = PDFButtonConfig(
            state=PDFButtonState.FETCH,
            pdf_url="https://example.com/paper.pdf",
            on_fetch=custom_fetch_handler,
            show_notifications=True
        )

        upload_config = PDFButtonConfig(
            state=PDFButtonState.UPLOAD,
            on_upload=custom_upload_handler,
            show_notifications=True
        )

        # Create buttons
        view_button = factory.create_pdf_button(view_config)
        fetch_button = factory.create_pdf_button(fetch_config)
        upload_button = factory.create_pdf_button(upload_config)

        # Add to page
        page.add(
            ft.Text("Custom PDF Button Handlers", size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Text("VIEW button with custom handler:"),
            view_button,
            ft.Divider(),
            ft.Text("FETCH button with custom handler:"),
            fetch_button,
            ft.Divider(),
            ft.Text("UPLOAD button with custom handler:"),
            upload_button,
        )

    ft.app(target=main)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Document Card Factory Demo")
    parser.add_argument(
        "--framework",
        choices=["flet", "qt", "custom"],
        default="flet",
        help="Which example to run"
    )

    args = parser.parse_args()

    if args.framework == "flet":
        print("Running Flet example...")
        flet_example()
    elif args.framework == "qt":
        print("Running Qt example...")
        qt_example()
    elif args.framework == "custom":
        print("Running custom PDF button example...")
        custom_pdf_button_example()
