"""
Paper Weight Laboratory - Dialog Classes

Reusable dialog classes for the Paper Weight Assessment Laboratory.
"""

from typing import Optional, Dict, List

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSlider, QFormLayout,
    QTreeWidget, QTreeWidgetItem, QMessageBox, QTextEdit,
)
from PySide6.QtCore import Qt

from bmlibrarian.gui.qt.resources.styles.dpi_scale import get_font_scale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import get_stylesheet_generator
from bmlibrarian.agents.paper_weight_db import search_documents

from .constants import (
    WEIGHT_SLIDER_MIN,
    WEIGHT_SLIDER_MAX,
    WEIGHT_SLIDER_PRECISION,
)
from .utils import (
    format_dimension_name,
    validate_weights_sum,
    slider_value_to_weight,
    weight_to_slider_value,
)


class DimensionWeightDialog(QDialog):
    """
    Dialog for configuring dimension weights.

    Provides sliders for each dimension weight with real-time validation
    that weights sum to 1.0.
    """

    def __init__(
        self,
        current_weights: Dict[str, float],
        parent: Optional[object] = None
    ):
        """
        Initialize weight configuration dialog.

        Args:
            current_weights: Current dimension weights dictionary
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Configure Dimension Weights")

        # Get scaling values
        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()

        self.setMinimumWidth(self.scale['control_width_xlarge'])

        self.weights = current_weights.copy()
        self.sliders: Dict[str, QSlider] = {}
        self.value_labels: Dict[str, QLabel] = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup dialog user interface."""
        layout = QFormLayout()
        layout.setSpacing(self.scale['spacing_medium'])

        # Create slider for each dimension
        for dim_name, weight in self.weights.items():
            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(WEIGHT_SLIDER_MIN)
            slider.setMaximum(WEIGHT_SLIDER_MAX)
            slider.setValue(weight_to_slider_value(weight))
            slider.valueChanged.connect(self._on_weight_changed)

            value_label = QLabel(f"{weight:.2f}")
            value_label.setMinimumWidth(self.scale['control_width_tiny'])

            h_layout = QHBoxLayout()
            h_layout.addWidget(slider, stretch=1)
            h_layout.addWidget(value_label)

            display_name = format_dimension_name(dim_name)
            layout.addRow(f"{display_name}:", h_layout)

            self.sliders[dim_name] = slider
            self.value_labels[dim_name] = value_label

        # Warning/status label
        self.status_label = QLabel()
        self.status_label.setStyleSheet(self.styles.label_stylesheet(
            font_size_key='font_small',
            color='#666'
        ))
        layout.addRow(self.status_label)

        # Update status initially
        self._update_status()

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def _on_weight_changed(self) -> None:
        """Handle slider value changes."""
        # Update value labels
        for dim_name, slider in self.sliders.items():
            value = slider_value_to_weight(slider.value())
            self.value_labels[dim_name].setText(f"{value:.2f}")

        self._update_status()

    def _update_status(self) -> None:
        """Update status label with weight sum validation."""
        current_weights = self.get_weights()
        is_valid, total = validate_weights_sum(current_weights)

        if is_valid:
            self.status_label.setText("✓ Weights sum to 1.0")
            self.status_label.setStyleSheet(self.styles.label_stylesheet(
                font_size_key='font_small',
                color='green'
            ))
        else:
            self.status_label.setText(
                f"⚠ Weights sum to {total:.2f} (must be 1.0)"
            )
            self.status_label.setStyleSheet(self.styles.label_stylesheet(
                font_size_key='font_small',
                color='orange'
            ))

    def _validate_and_accept(self) -> None:
        """Validate weights sum to 1.0 before accepting."""
        current_weights = self.get_weights()
        is_valid, total = validate_weights_sum(current_weights)

        if not is_valid:
            QMessageBox.warning(
                self,
                "Invalid Weights",
                f"Weights must sum to 1.0 (currently {total:.2f}).\n"
                "Please adjust the sliders."
            )
            return

        self.accept()

    def get_weights(self) -> Dict[str, float]:
        """
        Get configured weights.

        Returns:
            Dictionary mapping dimension names to their weights
        """
        return {
            dim: slider_value_to_weight(slider.value())
            for dim, slider in self.sliders.items()
        }


class DocumentSearchDialog(QDialog):
    """
    Dialog for searching and selecting documents.

    Provides a search interface with results list.
    """

    def __init__(self, parent: Optional[object] = None):
        """
        Initialize document search dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle("Search Documents")

        self.scale = get_font_scale()
        self.styles = get_stylesheet_generator()

        self.setMinimumWidth(self.scale['control_width_xlarge'] * 2)
        self.setMinimumHeight(self.scale['control_height_xlarge'] * 10)

        self.selected_document_id: Optional[int] = None
        self.search_results: List[Dict] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup dialog user interface."""
        layout = QVBoxLayout()
        layout.setSpacing(self.scale['spacing_medium'])

        # Search input
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Enter PMID, DOI, or title keywords..."
        )
        self.search_input.returnPressed.connect(self._do_search)
        search_layout.addWidget(self.search_input, stretch=1)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._do_search)
        search_btn.setStyleSheet(self.styles.button_stylesheet(
            bg_color="#2196F3"
        ))
        search_layout.addWidget(search_btn)

        layout.addLayout(search_layout)

        # Results list
        self.results_list = QTreeWidget()
        self.results_list.setHeaderLabels(["ID", "Title", "PMID", "Year"])
        self.results_list.setColumnWidth(0, self.scale['char_width'] * 8)
        self.results_list.setColumnWidth(1, self.scale['char_width'] * 60)
        self.results_list.setColumnWidth(2, self.scale['char_width'] * 12)
        self.results_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.results_list)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._select_document)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def _do_search(self) -> None:
        """Perform document search."""
        query = self.search_input.text().strip()
        if not query:
            return

        self.results_list.clear()
        self.search_results = search_documents(query)

        for doc in self.search_results:
            item = QTreeWidgetItem([
                str(doc['id']),
                doc['title'] or 'No title',
                str(doc['pmid'] or ''),
                str(doc['year'] or '')
            ])
            # Set full title as tooltip for truncated display
            item.setToolTip(1, doc['title'] or 'No title')
            self.results_list.addTopLevelItem(item)

        if not self.search_results:
            QMessageBox.information(
                self,
                "No Results",
                f"No documents found matching: {query}"
            )

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double-click on result item."""
        self._select_document()

    def _select_document(self) -> None:
        """Select current document and close dialog."""
        current = self.results_list.currentItem()
        if current:
            self.selected_document_id = int(current.text(0))
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select a document from the list."
            )

    def get_selected_document_id(self) -> Optional[int]:
        """
        Get the selected document ID.

        Returns:
            Selected document ID or None if nothing selected
        """
        return self.selected_document_id


class FullTextDialog(QDialog):
    """
    Dialog for displaying full untruncated text.

    Used when evidence or reasoning text is too long for the tree widget.
    """

    def __init__(
        self,
        title: str,
        text: str,
        parent: Optional[object] = None
    ):
        """
        Initialize full text dialog.

        Args:
            title: Dialog window title
            text: Full text to display
            parent: Parent widget
        """
        super().__init__(parent)
        self.setWindowTitle(title)

        self.scale = get_font_scale()

        self.setMinimumWidth(self.scale['control_width_xlarge'])
        self.setMinimumHeight(self.scale['control_height_xlarge'] * 6)

        self._setup_ui(text)

    def _setup_ui(self, text: str) -> None:
        """Setup dialog user interface."""
        layout = QVBoxLayout()
        layout.setSpacing(self.scale['spacing_medium'])

        # Text display (read-only)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(text)
        text_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        layout.addWidget(text_edit)

        # Close button
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

        self.setLayout(layout)


__all__ = [
    'DimensionWeightDialog',
    'DocumentSearchDialog',
    'FullTextDialog',
]
