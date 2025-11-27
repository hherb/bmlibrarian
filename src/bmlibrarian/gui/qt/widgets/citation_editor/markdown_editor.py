"""
Markdown editor widget with citation support.

Provides a QPlainTextEdit-based editor with:
- Markdown + citation syntax highlighting
- Right-click context menu for citation search
- Citation insertion at cursor
- Text selection for semantic search
- Line numbers (optional)
- Undo/redo support
"""

import logging
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QPlainTextEdit, QWidget, QVBoxLayout, QMenu, QTextEdit
)
from PySide6.QtCore import Signal, Qt, QRect, QMimeData
from PySide6.QtGui import (
    QFont, QTextCursor, QPainter, QColor, QTextFormat,
    QAction, QKeySequence, QFontMetrics, QDragEnterEvent, QDropEvent
)

from ...resources.styles import get_font_scale, StylesheetGenerator
from .syntax_highlighter import MarkdownCitationHighlighter

logger = logging.getLogger(__name__)


class LineNumberArea(QWidget):
    """Widget for displaying line numbers alongside the editor."""

    def __init__(self, editor: "MarkdownEditorWidget") -> None:
        """
        Initialize line number area.

        Args:
            editor: Parent editor widget
        """
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        """Return preferred size."""
        return self._editor.line_number_area_width(), 0

    def paintEvent(self, event):
        """Paint line numbers."""
        self._editor.line_number_area_paint_event(event)


class MarkdownEditorWidget(QPlainTextEdit):
    """
    Markdown editor with citation support.

    Signals:
        text_changed: Emitted when text content changes
        selection_changed: Emitted when selection changes, with selected text
        citation_search_requested: Emitted when user requests citation search
        insert_citation_shortcut: Emitted when Ctrl+Shift+K is pressed
    """

    text_changed = Signal(str)
    selection_changed = Signal(str)
    citation_search_requested = Signal(str)  # Selected text for search
    insert_citation_shortcut = Signal()  # Ctrl+Shift+K pressed

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        show_line_numbers: bool = True
    ) -> None:
        """
        Initialize markdown editor.

        Args:
            parent: Parent widget
            show_line_numbers: Whether to show line numbers
        """
        super().__init__(parent)

        self.scale = get_font_scale()
        self.style_gen = StylesheetGenerator()

        self._show_line_numbers = show_line_numbers
        self._line_number_area: Optional[LineNumberArea] = None

        self._setup_ui()
        self._setup_highlighter()
        self._setup_connections()
        self._setup_context_menu()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        s = self.scale

        # Set monospace font
        font = QFont("Consolas, Monaco, Courier New, monospace")
        font.setPointSize(s['font_normal'])
        self.setFont(font)

        # Tab width (4 spaces)
        metrics = QFontMetrics(font)
        self.setTabStopDistance(4 * metrics.horizontalAdvance(' '))

        # Styling
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #FAFAFA;
                color: #212121;
                border: 1px solid #E0E0E0;
                border-radius: {s['radius_small']}px;
                padding: {s['padding_small']}px;
            }}
            QPlainTextEdit:focus {{
                border: 1px solid #2196F3;
            }}
        """)

        # Line wrapping
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        # Placeholder text
        self.setPlaceholderText("Start writing your document here...\n\n"
                                "Use [@id:12345:Label] format for citations.")

        # Set up line numbers if enabled
        if self._show_line_numbers:
            self._line_number_area = LineNumberArea(self)
            self.blockCountChanged.connect(self._update_line_number_area_width)
            self.updateRequest.connect(self._update_line_number_area)
            self._update_line_number_area_width(0)

        # Enable drag and drop
        self.setAcceptDrops(True)

    def _setup_highlighter(self) -> None:
        """Set up syntax highlighter."""
        self._highlighter = MarkdownCitationHighlighter(self.document())

    def _setup_connections(self) -> None:
        """Set up signal connections."""
        self.textChanged.connect(self._on_text_changed)
        self.selectionChanged.connect(self._on_selection_changed)

    def _setup_context_menu(self) -> None:
        """Set up custom context menu."""
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _on_text_changed(self) -> None:
        """Handle text change."""
        self.text_changed.emit(self.toPlainText())

    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        cursor = self.textCursor()
        selected_text = cursor.selectedText()
        if selected_text:
            self.selection_changed.emit(selected_text)

    def _show_context_menu(self, position) -> None:
        """
        Show custom context menu.

        Args:
            position: Click position
        """
        menu = self.createStandardContextMenu()

        # Add separator before our custom actions
        menu.addSeparator()

        # Get selected text
        cursor = self.textCursor()
        selected_text = cursor.selectedText()

        if selected_text:
            # Add "Find Citations" action
            find_citations_action = QAction("Find Citations", menu)
            find_citations_action.setToolTip(
                "Search for citations related to the selected text"
            )
            find_citations_action.triggered.connect(
                lambda: self.citation_search_requested.emit(selected_text)
            )
            menu.addAction(find_citations_action)

        # Add insert citation shortcut hint
        insert_action = QAction("Insert Citation (Ctrl+Shift+K)", menu)
        insert_action.setEnabled(False)  # Just a hint
        menu.addAction(insert_action)

        menu.exec(self.mapToGlobal(position))

    def keyPressEvent(self, event) -> None:
        """
        Handle key press events.

        Args:
            event: Key event
        """
        # Ctrl+Shift+K - insert citation shortcut
        if (event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
                and event.key() == Qt.Key.Key_K):
            self.insert_citation_shortcut.emit()
            event.accept()
            return

        # Handle tab for indentation
        if event.key() == Qt.Key.Key_Tab:
            cursor = self.textCursor()
            if cursor.hasSelection():
                # Indent selected lines
                self._indent_selection(cursor, increase=True)
            else:
                # Insert 4 spaces
                cursor.insertText("    ")
            event.accept()
            return

        # Handle Shift+Tab for unindent
        if event.key() == Qt.Key.Key_Backtab:
            cursor = self.textCursor()
            self._indent_selection(cursor, increase=False)
            event.accept()
            return

        super().keyPressEvent(event)

    def _indent_selection(self, cursor: QTextCursor, increase: bool) -> None:
        """
        Indent or unindent selected lines.

        Args:
            cursor: Text cursor with selection
            increase: True to indent, False to unindent
        """
        cursor.beginEditBlock()

        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        start_block = cursor.blockNumber()

        cursor.setPosition(end)
        end_block = cursor.blockNumber()

        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)

        for _ in range(end_block - start_block + 1):
            if increase:
                cursor.insertText("    ")
            else:
                # Remove up to 4 spaces from start
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                text = cursor.block().text()
                spaces_to_remove = 0
                for char in text[:4]:
                    if char == ' ':
                        spaces_to_remove += 1
                    else:
                        break
                if spaces_to_remove:
                    cursor.movePosition(
                        QTextCursor.MoveOperation.Right,
                        QTextCursor.MoveMode.KeepAnchor,
                        spaces_to_remove
                    )
                    cursor.removeSelectedText()

            cursor.movePosition(QTextCursor.MoveOperation.NextBlock)

        cursor.endEditBlock()

    def insert_citation(self, document_id: int, label: str) -> None:
        """
        Insert a citation marker at the cursor position.

        Args:
            document_id: Database document ID
            label: Human-readable label (e.g., "Smith2023")
        """
        citation = f"[@id:{document_id}:{label}]"
        cursor = self.textCursor()
        cursor.insertText(citation)
        self.setTextCursor(cursor)

    def get_selected_text(self) -> str:
        """
        Get currently selected text.

        Returns:
            Selected text or empty string
        """
        return self.textCursor().selectedText()

    def get_word_at_cursor(self) -> str:
        """
        Get the word at the current cursor position.

        Returns:
            Word under cursor
        """
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        return cursor.selectedText()

    def get_citation_at_cursor(self) -> Optional[str]:
        """
        Get citation marker at cursor position if any.

        Returns:
            Citation marker text or None
        """
        cursor = self.textCursor()
        position = cursor.position()
        text = self.toPlainText()

        # Look for citation pattern around cursor
        import re
        pattern = re.compile(r'\[@id:\d+:[^\]]+\]')

        for match in pattern.finditer(text):
            if match.start() <= position <= match.end():
                return match.group(0)

        return None

    # Line number area methods
    def line_number_area_width(self) -> int:
        """Calculate width needed for line numbers."""
        if not self._show_line_numbers:
            return 0

        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num //= 10
            digits += 1

        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits + 3
        return space

    def _update_line_number_area_width(self, _) -> None:
        """Update viewport margins for line numbers."""
        if self._show_line_numbers:
            self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy) -> None:
        """Update line number area on scroll."""
        if not self._line_number_area:
            return

        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0, rect.y(),
                self._line_number_area.width(), rect.height()
            )

        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def resizeEvent(self, event) -> None:
        """Handle resize event."""
        super().resizeEvent(event)

        if self._line_number_area:
            cr = self.contentsRect()
            self._line_number_area.setGeometry(
                QRect(cr.left(), cr.top(),
                      self.line_number_area_width(), cr.height())
            )

    def line_number_area_paint_event(self, event) -> None:
        """Paint line numbers."""
        if not self._line_number_area:
            return

        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor("#F5F5F5"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(
            self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor("#9E9E9E"))
                painter.drawText(
                    0, top,
                    self._line_number_area.width() - 3,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number
                )

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def set_show_line_numbers(self, show: bool) -> None:
        """
        Toggle line numbers visibility.

        Args:
            show: Whether to show line numbers
        """
        self._show_line_numbers = show

        if show and not self._line_number_area:
            self._line_number_area = LineNumberArea(self)
            self.blockCountChanged.connect(self._update_line_number_area_width)
            self.updateRequest.connect(self._update_line_number_area)

        self._update_line_number_area_width(0)

        if self._line_number_area:
            self._line_number_area.setVisible(show)

    def get_cursor_position(self) -> tuple:
        """
        Get current cursor position as (line, column).

        Returns:
            Tuple of (line_number, column_number) (1-based)
        """
        cursor = self.textCursor()
        return (cursor.blockNumber() + 1, cursor.columnNumber() + 1)

    def set_cursor_position(self, line: int, column: int) -> None:
        """
        Set cursor position.

        Args:
            line: Line number (1-based)
            column: Column number (1-based)
        """
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(
            QTextCursor.MoveOperation.NextBlock,
            QTextCursor.MoveMode.MoveAnchor,
            line - 1
        )
        cursor.movePosition(
            QTextCursor.MoveOperation.Right,
            QTextCursor.MoveMode.MoveAnchor,
            column - 1
        )
        self.setTextCursor(cursor)
        self.centerCursor()

    # Drag and drop support

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """
        Handle drag enter event.

        Accepts drags with citation data or plain text.

        Args:
            event: Drag enter event
        """
        mime_data = event.mimeData()

        # Accept citation data (from document cards)
        if mime_data.hasFormat('application/x-citation-data'):
            event.acceptProposedAction()
            return

        # Accept plain text
        if mime_data.hasText():
            event.acceptProposedAction()
            return

        event.ignore()

    def dragMoveEvent(self, event) -> None:
        """
        Handle drag move event.

        Args:
            event: Drag move event
        """
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        """
        Handle drop event.

        Inserts citation if citation data is dropped.

        Args:
            event: Drop event
        """
        import json

        mime_data = event.mimeData()

        # Handle citation data
        if mime_data.hasFormat('application/x-citation-data'):
            try:
                data = bytes(mime_data.data('application/x-citation-data')).decode('utf-8')
                citation_data = json.loads(data)

                doc_id = citation_data.get('document_id')
                label = citation_data.get('label', f'Doc{doc_id}')

                if doc_id:
                    # Move cursor to drop position
                    cursor = self.cursorForPosition(event.position().toPoint())
                    self.setTextCursor(cursor)

                    # Insert citation
                    self.insert_citation(doc_id, label)
                    event.acceptProposedAction()
                    return

            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to parse citation drop data: {e}")

        # Handle plain text (default behavior)
        if mime_data.hasText():
            cursor = self.cursorForPosition(event.position().toPoint())
            self.setTextCursor(cursor)
            cursor.insertText(mime_data.text())
            event.acceptProposedAction()
            return

        event.ignore()
