"""
Unit tests for document card factory classes.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from bmlibrarian.gui.document_card_factory_base import (
    DocumentCardFactoryBase,
    DocumentCardData,
    PDFButtonConfig,
    PDFButtonState,
    CardContext
)


class TestDocumentCardFactoryBase:
    """Tests for DocumentCardFactoryBase abstract class."""

    def test_determine_pdf_state_view(self, tmp_path):
        """Test PDF state determination when local file exists."""
        # Create a test PDF file
        pdf_file = tmp_path / "12345.pdf"
        pdf_file.write_text("test")

        # Create a concrete subclass for testing
        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory(base_pdf_dir=tmp_path)
        state = factory.determine_pdf_state(12345)

        assert state == PDFButtonState.VIEW

    def test_determine_pdf_state_fetch(self, tmp_path):
        """Test PDF state determination when URL available but no local file."""
        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory(base_pdf_dir=tmp_path)
        state = factory.determine_pdf_state(
            12345,
            pdf_url="https://example.com/paper.pdf"
        )

        assert state == PDFButtonState.FETCH

    def test_determine_pdf_state_upload(self, tmp_path):
        """Test PDF state determination when no local file or URL."""
        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory(base_pdf_dir=tmp_path)
        state = factory.determine_pdf_state(12345)

        assert state == PDFButtonState.UPLOAD

    def test_get_pdf_path_exists(self, tmp_path):
        """Test getting PDF path when file exists."""
        pdf_file = tmp_path / "12345.pdf"
        pdf_file.write_text("test")

        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory(base_pdf_dir=tmp_path)
        path = factory.get_pdf_path(12345)

        assert path == pdf_file
        assert path.exists()

    def test_get_pdf_path_not_exists(self, tmp_path):
        """Test getting PDF path when file doesn't exist."""
        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory(base_pdf_dir=tmp_path)
        path = factory.get_pdf_path(12345)

        assert path is None

    def test_format_authors_short_list(self):
        """Test author formatting with short list."""
        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory()
        authors = ["Smith J", "Johnson A"]
        formatted = factory.format_authors(authors)

        assert formatted == "Smith J, Johnson A"

    def test_format_authors_long_list(self):
        """Test author formatting with long list (et al)."""
        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory()
        authors = ["Smith J", "Johnson A", "Williams B", "Chen X", "Kim S"]
        formatted = factory.format_authors(authors, max_authors=3)

        assert formatted == "Smith J, Johnson A, Williams B, et al."

    def test_format_authors_none(self):
        """Test author formatting with None."""
        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory()
        formatted = factory.format_authors(None)

        assert formatted == "Unknown authors"

    def test_format_metadata(self):
        """Test metadata formatting."""
        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory()
        metadata = factory.format_metadata(
            year=2023,
            journal="Nature",
            pmid="12345678",
            doi="10.1234/test"
        )

        assert metadata["Year"] == "2023"
        assert metadata["Journal"] == "Nature"
        assert metadata["PMID"] == "12345678"
        assert metadata["DOI"] == "10.1234/test"

    def test_get_score_color_high(self):
        """Test score color for high relevance."""
        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory()
        color = factory.get_score_color(4.8)

        assert color == "#2E7D32"  # Dark green

    def test_get_score_color_medium(self):
        """Test score color for medium relevance."""
        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory()
        color = factory.get_score_color(3.5)

        assert color == "#1976D2"  # Blue

    def test_get_score_color_low(self):
        """Test score color for low relevance."""
        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory()
        color = factory.get_score_color(2.0)

        assert color == "#C62828"  # Red

    def test_truncate_abstract_short(self):
        """Test abstract truncation with short text."""
        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory()
        abstract = "This is a short abstract."
        truncated = factory.truncate_abstract(abstract, max_length=500)

        assert truncated == abstract

    def test_truncate_abstract_long(self):
        """Test abstract truncation with long text."""
        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory()
        abstract = "This is a very long abstract. " * 50  # Create long text
        truncated = factory.truncate_abstract(abstract, max_length=100)

        assert len(truncated) <= 103  # 100 + "..."
        assert truncated.endswith("...") or truncated.endswith(".")

    def test_truncate_abstract_none(self):
        """Test abstract truncation with None."""
        class TestFactory(DocumentCardFactoryBase):
            def create_card(self, card_data):
                pass

            def create_pdf_button(self, config):
                pass

        factory = TestFactory()
        truncated = factory.truncate_abstract(None)

        assert truncated == "No abstract available."


class TestDocumentCardData:
    """Tests for DocumentCardData dataclass."""

    def test_create_minimal_card_data(self):
        """Test creating card data with minimal required fields."""
        data = DocumentCardData(
            doc_id=12345,
            title="Test Document"
        )

        assert data.doc_id == 12345
        assert data.title == "Test Document"
        assert data.abstract is None
        assert data.context == CardContext.LITERATURE
        assert data.show_pdf_button is True

    def test_create_full_card_data(self):
        """Test creating card data with all fields."""
        data = DocumentCardData(
            doc_id=12345,
            title="Test Document",
            abstract="Test abstract",
            authors=["Smith J", "Johnson A"],
            year=2023,
            journal="Nature",
            pmid="12345678",
            doi="10.1234/test",
            source="pubmed",
            relevance_score=4.5,
            human_score=5.0,
            confidence="high",
            context=CardContext.SCORING,
            show_abstract=True,
            show_metadata=True,
            show_pdf_button=True,
            pdf_path=Path("/path/to/pdf"),
            pdf_url="https://example.com/pdf"
        )

        assert data.doc_id == 12345
        assert data.title == "Test Document"
        assert data.abstract == "Test abstract"
        assert data.authors == ["Smith J", "Johnson A"]
        assert data.year == 2023
        assert data.journal == "Nature"
        assert data.pmid == "12345678"
        assert data.doi == "10.1234/test"
        assert data.source == "pubmed"
        assert data.relevance_score == 4.5
        assert data.human_score == 5.0
        assert data.confidence == "high"
        assert data.context == CardContext.SCORING
        assert data.pdf_path == Path("/path/to/pdf")
        assert data.pdf_url == "https://example.com/pdf"


class TestPDFButtonConfig:
    """Tests for PDFButtonConfig dataclass."""

    def test_create_view_config(self):
        """Test creating VIEW button configuration."""
        config = PDFButtonConfig(
            state=PDFButtonState.VIEW,
            pdf_path=Path("/path/to/pdf")
        )

        assert config.state == PDFButtonState.VIEW
        assert config.pdf_path == Path("/path/to/pdf")
        assert config.show_notifications is True

    def test_create_fetch_config(self):
        """Test creating FETCH button configuration."""
        config = PDFButtonConfig(
            state=PDFButtonState.FETCH,
            pdf_url="https://example.com/pdf"
        )

        assert config.state == PDFButtonState.FETCH
        assert config.pdf_url == "https://example.com/pdf"

    def test_create_upload_config(self):
        """Test creating UPLOAD button configuration."""
        config = PDFButtonConfig(
            state=PDFButtonState.UPLOAD
        )

        assert config.state == PDFButtonState.UPLOAD

    def test_config_with_callbacks(self):
        """Test configuration with callback functions."""
        view_callback = Mock()
        fetch_callback = Mock()
        upload_callback = Mock()

        config = PDFButtonConfig(
            state=PDFButtonState.VIEW,
            on_view=view_callback,
            on_fetch=fetch_callback,
            on_upload=upload_callback
        )

        assert config.on_view == view_callback
        assert config.on_fetch == fetch_callback
        assert config.on_upload == upload_callback


# Flet Factory Tests (requires mocking Flet components)
@pytest.mark.skipif(
    not pytest.importorskip("flet", minversion="0.24.0"),
    reason="Flet not installed"
)
class TestFletDocumentCardFactory:
    """Tests for FletDocumentCardFactory."""

    @patch('bmlibrarian.gui.flet_document_card_factory.UnifiedDocumentCard')
    def test_create_card(self, mock_unified_card, tmp_path):
        """Test creating Flet card."""
        from bmlibrarian.gui.flet_document_card_factory import FletDocumentCardFactory
        import flet as ft

        # Mock page
        page = Mock(spec=ft.Page)

        # Create factory
        factory = FletDocumentCardFactory(
            page=page,
            base_pdf_dir=tmp_path
        )

        # Create card data
        card_data = DocumentCardData(
            doc_id=12345,
            title="Test Document",
            abstract="Test abstract",
            authors=["Smith J"],
            year=2023,
            context=CardContext.LITERATURE
        )

        # Create card
        card = factory.create_card(card_data)

        # Verify UnifiedDocumentCard was called
        assert mock_unified_card.return_value.create_card.called


# Qt Factory Tests (requires Qt components)
@pytest.mark.skipif(
    not pytest.importorskip("PySide6"),
    reason="PySide6 not installed"
)
class TestQtDocumentCardFactory:
    """Tests for QtDocumentCardFactory."""

    def test_create_card(self, tmp_path, qapp):
        """Test creating Qt card."""
        from bmlibrarian.gui.qt.qt_document_card_factory import QtDocumentCardFactory

        # Create factory
        factory = QtDocumentCardFactory(base_pdf_dir=tmp_path)

        # Create card data
        card_data = DocumentCardData(
            doc_id=12345,
            title="Test Document",
            abstract="Test abstract",
            authors=["Smith J"],
            year=2023,
            context=CardContext.LITERATURE
        )

        # Create card
        card = factory.create_card(card_data)

        # Verify card was created
        assert card is not None

    def test_pdf_button_widget_view(self, qapp):
        """Test PDF button widget in VIEW state."""
        from bmlibrarian.gui.qt.qt_document_card_factory import PDFButtonWidget

        config = PDFButtonConfig(
            state=PDFButtonState.VIEW,
            pdf_path=Path("/path/to/pdf")
        )

        button = PDFButtonWidget(config)

        assert "View Full Text" in button.text()

    def test_pdf_button_widget_fetch(self, qapp):
        """Test PDF button widget in FETCH state."""
        from bmlibrarian.gui.qt.qt_document_card_factory import PDFButtonWidget

        config = PDFButtonConfig(
            state=PDFButtonState.FETCH,
            pdf_url="https://example.com/pdf"
        )

        button = PDFButtonWidget(config)

        assert "Fetch Full Text" in button.text()

    def test_pdf_button_widget_upload(self, qapp):
        """Test PDF button widget in UPLOAD state."""
        from bmlibrarian.gui.qt.qt_document_card_factory import PDFButtonWidget

        config = PDFButtonConfig(
            state=PDFButtonState.UPLOAD
        )

        button = PDFButtonWidget(config)

        assert "Upload Full Text" in button.text()


# Fixtures
@pytest.fixture
def qapp():
    """Create QApplication instance for Qt tests."""
    try:
        from PySide6.QtWidgets import QApplication
        import sys

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        yield app
    except ImportError:
        pytest.skip("PySide6 not available")
