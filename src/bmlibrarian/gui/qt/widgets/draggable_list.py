"""
Draggable list widget for reordering items via drag-and-drop.

This module provides a DraggableListWidget container that allows its child
widgets to be reordered through drag-and-drop operations.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QLabel, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QMimeData, QPoint, QRect
from PySide6.QtGui import (
    QDrag, QPixmap, QPainter, QColor, QCursor,
    QMouseEvent, QDragEnterEvent, QDragMoveEvent, QDragLeaveEvent, QDropEvent
)
from typing import List, Optional, Callable
import logging

from ..resources.styles import get_font_scale, scale_px, StylesheetGenerator


# MIME type for internal drag-drop operations
DRAG_MIME_TYPE = "application/x-bmlibrarian-drag-item"

# Constants for drag-drop behavior (in pixels, scaled via scale_px)
MIN_DRAG_DISTANCE_PX = 10  # Minimum distance before drag starts
DRAG_PIXMAP_ALPHA = 180  # Alpha value for dragged item ghost (0-255)
ITEM_SPACING_PX = 8  # Spacing between items in the list
HANDLE_SPACING_PX = 4  # Spacing between handle and content
DROP_INDICATOR_OFFSET_PX = 4  # Offset for drop indicator positioning
DROP_INDICATOR_MARGIN_PX = 8  # Horizontal margin for drop indicator


class DragHandle(QLabel):
    """A visual drag handle widget (grip icon)."""

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the drag handle.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        self.setText("⋮⋮")  # Unicode grip pattern
        gen = StylesheetGenerator()
        self.setStyleSheet(gen.drag_handle_stylesheet())
        self.setToolTip("Drag to reorder")


class DraggableItemWrapper(QFrame):
    """Wrapper that makes any widget draggable within a DraggableListWidget."""

    drag_started = Signal(object)  # Emits self when drag starts
    drag_finished = Signal()  # Emits when drag ends

    def __init__(
        self,
        item_widget: QWidget,
        item_id: str,
        show_handle: bool = True,
        parent: Optional[QWidget] = None
    ):
        """Initialize the draggable wrapper.

        Args:
            item_widget: The widget to make draggable
            item_id: Unique identifier for this item
            show_handle: Whether to show a drag handle
            parent: Parent widget
        """
        super().__init__(parent)
        self.scale = get_font_scale()
        self.item_widget = item_widget
        self.item_id = item_id
        self._drag_start_pos: Optional[QPoint] = None
        self._is_dragging = False

        self._build_ui(show_handle)

    def _build_ui(self, show_handle: bool) -> None:
        """Build the wrapper UI.

        Args:
            show_handle: Whether to show a drag handle
        """
        from PySide6.QtWidgets import QHBoxLayout

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scale_px(HANDLE_SPACING_PX))

        if show_handle:
            self.drag_handle = DragHandle(self)
            layout.addWidget(self.drag_handle)
        else:
            self.drag_handle = None

        layout.addWidget(self.item_widget, stretch=1)

        # Allow the entire widget to initiate drag
        self.setAcceptDrops(False)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press to initiate drag.

        Args:
            event: Mouse press event
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move to start drag operation.

        Args:
            event: Mouse move event
        """
        if not self._drag_start_pos:
            super().mouseMoveEvent(event)
            return

        # Check if we've moved enough to start a drag
        distance = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
        if distance < MIN_DRAG_DISTANCE_PX:
            super().mouseMoveEvent(event)
            return

        self._start_drag()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release.

        Args:
            event: Mouse release event
        """
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _start_drag(self) -> None:
        """Start the drag operation."""
        self._is_dragging = True
        self.drag_started.emit(self)

        # Create drag object
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setData(DRAG_MIME_TYPE, self.item_id.encode('utf-8'))
        drag.setMimeData(mime_data)

        # Create a semi-transparent pixmap of the widget
        pixmap = self.grab()
        # Make it semi-transparent
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.fillRect(pixmap.rect(), QColor(0, 0, 0, DRAG_PIXMAP_ALPHA))
        painter.end()

        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))

        # Execute drag
        drag.exec(Qt.DropAction.MoveAction)

        self._is_dragging = False
        self._drag_start_pos = None
        self.drag_finished.emit()


class DropIndicator(QFrame):
    """Visual indicator showing where an item will be dropped."""

    # Height in pixels before scaling (relative to ~16px baseline line height)
    INDICATOR_HEIGHT_PX = 4

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the drop indicator.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setFixedHeight(scale_px(self.INDICATOR_HEIGHT_PX))
        gen = StylesheetGenerator()
        self.setStyleSheet(gen.drop_indicator_stylesheet())
        self.hide()


class DraggableListWidget(QWidget):
    """A container widget that allows drag-and-drop reordering of items.

    Signals:
        order_changed: Emitted when items are reordered.
                      Provides the new order as List[str] of item IDs.

    Example:
        >>> list_widget = DraggableListWidget()
        >>> list_widget.add_item("plugin1", plugin_card1)
        >>> list_widget.add_item("plugin2", plugin_card2)
        >>> list_widget.order_changed.connect(lambda order: print(f"New order: {order}"))
    """

    order_changed = Signal(list)  # Emits List[str] of item IDs in new order

    def __init__(
        self,
        show_handles: bool = True,
        parent: Optional[QWidget] = None
    ):
        """Initialize the draggable list widget.

        Args:
            show_handles: Whether to show drag handles on items
            parent: Parent widget
        """
        super().__init__(parent)
        self.scale = get_font_scale()
        self.logger = logging.getLogger("bmlibrarian.gui.qt.widgets.DraggableListWidget")
        self._show_handles = show_handles
        self._items: List[DraggableItemWrapper] = []
        self._dragged_item: Optional[DraggableItemWrapper] = None

        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self) -> None:
        """Build the list widget UI."""
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(scale_px(ITEM_SPACING_PX))
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Drop indicator (hidden by default)
        self._drop_indicator = DropIndicator(self)

    def add_item(self, item_id: str, widget: QWidget) -> DraggableItemWrapper:
        """Add an item to the list.

        Args:
            item_id: Unique identifier for the item
            widget: The widget to add

        Returns:
            The DraggableItemWrapper containing the widget
        """
        wrapper = DraggableItemWrapper(
            item_widget=widget,
            item_id=item_id,
            show_handle=self._show_handles,
            parent=self
        )
        wrapper.drag_started.connect(self._on_drag_started)
        wrapper.drag_finished.connect(self._on_drag_finished)

        self._items.append(wrapper)
        self._layout.addWidget(wrapper)

        return wrapper

    def insert_item(self, index: int, item_id: str, widget: QWidget) -> DraggableItemWrapper:
        """Insert an item at a specific position.

        Args:
            index: Position to insert at
            item_id: Unique identifier for the item
            widget: The widget to add

        Returns:
            The DraggableItemWrapper containing the widget
        """
        wrapper = DraggableItemWrapper(
            item_widget=widget,
            item_id=item_id,
            show_handle=self._show_handles,
            parent=self
        )
        wrapper.drag_started.connect(self._on_drag_started)
        wrapper.drag_finished.connect(self._on_drag_finished)

        self._items.insert(index, wrapper)
        self._layout.insertWidget(index, wrapper)

        return wrapper

    def remove_item(self, item_id: str) -> bool:
        """Remove an item from the list.

        Args:
            item_id: ID of the item to remove

        Returns:
            True if item was removed, False if not found
        """
        for wrapper in self._items:
            if wrapper.item_id == item_id:
                self._items.remove(wrapper)
                self._layout.removeWidget(wrapper)
                wrapper.deleteLater()
                return True
        return False

    def clear(self) -> None:
        """Remove all items from the list."""
        for wrapper in self._items:
            self._layout.removeWidget(wrapper)
            wrapper.deleteLater()
        self._items.clear()

    def get_order(self) -> List[str]:
        """Get the current order of items.

        Returns:
            List of item IDs in current display order
        """
        return [wrapper.item_id for wrapper in self._items]

    def set_order(self, order: List[str]) -> None:
        """Reorder items to match the given order.

        Items not in the order list will be moved to the end.

        Args:
            order: List of item IDs in desired order
        """
        # Build a map of current items
        item_map = {wrapper.item_id: wrapper for wrapper in self._items}

        # Reorder according to the provided order
        new_items = []
        for item_id in order:
            if item_id in item_map:
                new_items.append(item_map.pop(item_id))

        # Add any remaining items not in the order list
        for wrapper in item_map.values():
            new_items.append(wrapper)

        # Update layout
        for wrapper in self._items:
            self._layout.removeWidget(wrapper)

        self._items = new_items
        for wrapper in self._items:
            self._layout.addWidget(wrapper)

    def get_item(self, item_id: str) -> Optional[QWidget]:
        """Get the widget for a specific item.

        Args:
            item_id: ID of the item

        Returns:
            The item widget, or None if not found
        """
        for wrapper in self._items:
            if wrapper.item_id == item_id:
                return wrapper.item_widget
        return None

    def _on_drag_started(self, wrapper: DraggableItemWrapper) -> None:
        """Handle drag start.

        Args:
            wrapper: The wrapper that started dragging
        """
        self._dragged_item = wrapper
        gen = StylesheetGenerator()
        wrapper.setStyleSheet(gen.draggable_item_stylesheet())

    def _on_drag_finished(self) -> None:
        """Handle drag end."""
        if self._dragged_item:
            self._dragged_item.setStyleSheet("")
        self._dragged_item = None
        self._drop_indicator.hide()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter event.

        Args:
            event: Drag enter event
        """
        if event.mimeData().hasFormat(DRAG_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Handle drag move event to show drop indicator.

        Args:
            event: Drag move event
        """
        if not event.mimeData().hasFormat(DRAG_MIME_TYPE):
            event.ignore()
            return

        event.acceptProposedAction()

        # Find the drop position
        drop_index = self._get_drop_index(event.position().toPoint())
        self._show_drop_indicator(drop_index)

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        """Handle drag leave event.

        Args:
            event: Drag leave event
        """
        self._drop_indicator.hide()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop event to reorder items.

        Args:
            event: Drop event
        """
        if not event.mimeData().hasFormat(DRAG_MIME_TYPE):
            event.ignore()
            return

        # Get the dropped item ID
        item_id = event.mimeData().data(DRAG_MIME_TYPE).data().decode('utf-8')

        # Find the wrapper
        wrapper = None
        old_index = -1
        for i, w in enumerate(self._items):
            if w.item_id == item_id:
                wrapper = w
                old_index = i
                break

        if wrapper is None:
            event.ignore()
            return

        # Get the drop index
        drop_index = self._get_drop_index(event.position().toPoint())

        # Adjust drop index if we're moving down
        if old_index < drop_index:
            drop_index -= 1

        # Move the item
        if old_index != drop_index:
            self._items.remove(wrapper)
            self._layout.removeWidget(wrapper)

            self._items.insert(drop_index, wrapper)
            self._layout.insertWidget(drop_index, wrapper)

            self.logger.info(f"Item '{item_id}' moved from {old_index} to {drop_index}")
            self.order_changed.emit(self.get_order())

        self._drop_indicator.hide()
        event.acceptProposedAction()

    def _get_drop_index(self, pos: QPoint) -> int:
        """Determine the drop index based on cursor position.

        Args:
            pos: Cursor position in widget coordinates

        Returns:
            Index where the item should be dropped
        """
        for i, wrapper in enumerate(self._items):
            rect = wrapper.geometry()
            mid_y = rect.top() + rect.height() // 2
            if pos.y() < mid_y:
                return i
        return len(self._items)

    def _show_drop_indicator(self, index: int) -> None:
        """Show the drop indicator at the specified index.

        Args:
            index: Index where the indicator should appear
        """
        if index >= len(self._items):
            # Show at the bottom
            if self._items:
                last_rect = self._items[-1].geometry()
                y = last_rect.bottom() + scale_px(DROP_INDICATOR_OFFSET_PX)
            else:
                y = 0
        else:
            # Show above the item at index
            y = self._items[index].geometry().top() - scale_px(DROP_INDICATOR_OFFSET_PX // 2)

        self._drop_indicator.setGeometry(
            scale_px(DROP_INDICATOR_MARGIN_PX),
            y,
            self.width() - scale_px(DROP_INDICATOR_MARGIN_PX * 2),
            scale_px(DropIndicator.INDICATOR_HEIGHT_PX)
        )
        self._drop_indicator.show()
        self._drop_indicator.raise_()
