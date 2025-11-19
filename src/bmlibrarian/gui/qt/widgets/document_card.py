"""
Document card widget for BMLibrarian Qt GUI.

Displays document information in a card format using centralized
styles and utility functions for consistent formatting.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QMenu
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from typing import Optional, Dict, Any
import logging

from .card_utils import (
    DocumentData,
    validate_document_data,
    format_authors,
    extract_year,
    format_journal_year,
    format_document_ids,
    format_relevance_score,
    html_escape
)
from ..core.document_receiver_registry import DocumentReceiverRegistry
from ..core.event_bus import EventBus


class DocumentCard(QFrame):
    """
    Card widget for displaying document information.

    Shows title, authors, journal, year, and relevance score using
    centralized stylesheet and utility functions.

    Signals:
        clicked: Emitted when card is clicked, passes document data

    Example:
        >>> doc_data = {
        ...     "title": "Example Study",
        ...     "authors": ["Smith J", "Jones A"],
        ...     "journal": "Nature",
        ...     "year": 2023,
        ...     "pmid": 12345678,
        ...     "relevance_score": 4.5
        ... }
        >>> card = DocumentCard(doc_data)
    """

    # Signal emitted when card is clicked
    clicked = Signal(dict)  # Emits document data

    def __init__(self, document_data: Dict[str, Any], parent: Optional[QWidget] = None):
        """
        Initialize document card.

        Args:
            document_data: Dictionary containing document information
            parent: Optional parent widget

        Raises:
            TypeError: If document_data is not a dictionary
            ValueError: If required fields are missing
        """
        super().__init__(parent)

        # Validate and store document data
        self.document_data = validate_document_data(document_data)

        # Setup context menu support
        self.logger = logging.getLogger("bmlibrarian.gui.qt.widgets.DocumentCard")
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Configure frame (styling from QSS)
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("documentCard")

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        # Title
        title = self.document_data.get("title", "Untitled")
        title_label = QLabel(f"<b>{html_escape(title)}</b>")
        title_label.setObjectName("title")
        title_label.setWordWrap(True)
        title_label.setTextFormat(Qt.RichText)
        layout.addWidget(title_label)

        # Authors
        authors = format_authors(
            self.document_data.get("authors"),
            max_authors=3,
            et_al=True
        )
        authors_label = QLabel(f"<i>{html_escape(authors)}</i>")
        authors_label.setObjectName("authors")
        authors_label.setWordWrap(True)
        layout.addWidget(authors_label)

        # Journal and year
        journal_year = format_journal_year(
            self.document_data.get("journal"),
            self.document_data.get("year")
        )
        if journal_year:
            journal_label = QLabel(html_escape(journal_year))
            journal_label.setObjectName("journal")
            layout.addWidget(journal_label)

        # Relevance score (if available)
        score_text = format_relevance_score(self.document_data.get("relevance_score"))
        if score_text:
            score_label = QLabel(score_text)
            score_label.setObjectName("score")
            layout.addWidget(score_label)

        # PMID/DOI
        ids_text = format_document_ids(
            pmid=self.document_data.get("pmid"),
            doi=self.document_data.get("doi"),
            doc_id=self.document_data.get("document_id")
        )
        if ids_text:
            ids_label = QLabel(ids_text)
            ids_label.setObjectName("metadata")
            layout.addWidget(ids_label)

    def mousePressEvent(self, event):
        """
        Handle mouse press event.

        Emits clicked signal with document data on left button click.

        Args:
            event: Mouse event
        """
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.document_data)
        super().mousePressEvent(event)

    def get_document_id(self) -> Optional[int]:
        """
        Get the document ID.

        Returns:
            Document ID if available, None otherwise
        """
        return self.document_data.get("document_id")

    def get_title(self) -> str:
        """
        Get the document title.

        Returns:
            Document title
        """
        return self.document_data.get("title", "Untitled")

    def update_relevance_score(self, score: float) -> None:
        """
        Update the relevance score display.

        Args:
            score: New relevance score value
        """
        self.document_data["relevance_score"] = score

        # Find and update the score label
        for i in range(self.layout().count()):
            widget = self.layout().itemAt(i).widget()
            if isinstance(widget, QLabel) and widget.objectName() == "score":
                score_text = format_relevance_score(score)
                widget.setText(score_text)
                break

    def _show_context_menu(self, position):
        """
        Show context menu with "Send to" submenu for registered receivers.

        Args:
            position: Position where context menu was requested
        """
        # Get available document receivers
        registry = DocumentReceiverRegistry()
        receivers = registry.get_available_receivers(self.document_data)

        if not receivers:
            self.logger.debug("No document receivers available for context menu")
            return

        # Create context menu
        context_menu = QMenu(self)

        # Create "Send to" submenu
        send_to_menu = context_menu.addMenu("Send to")

        # Add action for each receiver
        for receiver in receivers:
            receiver_id = receiver.get_receiver_id()
            receiver_name = receiver.get_receiver_name()
            receiver_desc = receiver.get_receiver_description()

            action = QAction(receiver_name, send_to_menu)

            # Set tooltip if description available
            if receiver_desc:
                action.setToolTip(receiver_desc)

            # Connect to handler with receiver_id
            action.triggered.connect(
                lambda checked=False, rid=receiver_id: self._send_to_receiver(rid)
            )

            send_to_menu.addAction(action)

        # Show context menu at cursor position
        context_menu.exec(self.mapToGlobal(position))

    def _send_to_receiver(self, receiver_id: str):
        """
        Send this document to a specific receiver.

        Args:
            receiver_id: ID of the receiver to send document to
        """
        registry = DocumentReceiverRegistry()
        event_bus = EventBus()

        # Send document via registry
        success = registry.send_document(receiver_id, self.document_data)

        if success:
            # Request navigation to the receiver's tab
            event_bus.request_navigation(receiver_id)
            self.logger.info(
                f"Sent document {self.get_document_id()} to receiver '{receiver_id}'"
            )
        else:
            self.logger.error(
                f"Failed to send document {self.get_document_id()} "
                f"to receiver '{receiver_id}'"
            )
