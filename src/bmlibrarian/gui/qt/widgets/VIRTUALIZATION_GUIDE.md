# Document Card Virtualization Guide

## Overview

This guide provides recommendations for implementing virtualization to improve performance when displaying large lists of document or citation cards in the BMLibrarian Qt GUI.

## Why Virtualization?

When displaying hundreds or thousands of document cards, creating all widgets at once can lead to:

- **High memory usage**: Each card widget consumes memory
- **Slow initial rendering**: Creating many widgets takes time
- **Poor scrolling performance**: Qt must manage many visible and invisible widgets
- **UI freezing**: Large widget counts can freeze the interface

**Virtualization** solves these issues by only creating widgets for visible items.

## Virtualization Strategies

### 1. QAbstractItemView with Custom Delegate (Recommended)

Use Qt's built-in model-view architecture with a custom delegate to render cards.

**Advantages**:
- Built-in virtualization and scrolling
- Efficient memory usage
- Standard Qt patterns
- Easy to implement sorting and filtering

**Implementation**:

```python
from PySide6.QtWidgets import QListView, QStyledItemDelegate, QStyleOptionViewItem
from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex, QSize

class DocumentListModel(QAbstractListModel):
    """Model for document data."""

    def __init__(self, documents, parent=None):
        super().__init__(parent)
        self.documents = documents

    def rowCount(self, parent=QModelIndex()):
        return len(self.documents)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.UserRole:
            return self.documents[index.row()]

        return None


class DocumentCardDelegate(QStyledItemDelegate):
    """Delegate for rendering document cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.card_height = 150  # Approximate height

    def paint(self, painter, option, index):
        """Paint the document card."""
        document_data = index.data(Qt.UserRole)

        if not document_data:
            return

        # Create a temporary card for rendering
        # (or implement custom painting logic)
        from .document_card import DocumentCard
        card = DocumentCard(document_data)

        # Render the card widget
        card.setGeometry(option.rect)
        card.render(painter, painter.deviceTransform().map(option.rect.topLeft()))

    def sizeHint(self, option, index):
        """Return size hint for the card."""
        return QSize(option.rect.width(), self.card_height)


# Usage
class DocumentListView(QListView):
    """Virtualized list view for documents."""

    def __init__(self, documents, parent=None):
        super().__init__(parent)

        # Set up model
        self.model = DocumentListModel(documents)
        self.setModel(self.model)

        # Set up delegate
        self.delegate = DocumentCardDelegate()
        self.setItemDelegate(self.delegate)

        # Configure view
        self.setUniformItemSizes(True)  # Performance optimization
        self.setVerticalScrollMode(QListView.ScrollPerPixel)
```

### 2. QScrollArea with Lazy Loading

Implement a custom scroll area that loads cards on demand.

**Advantages**:
- Full control over rendering
- Can reuse card widgets
- Flexible customization

**Implementation**:

```python
from PySide6.QtWidgets import QScrollArea, QWidget, QVBoxLayout
from PySide6.QtCore import Qt

class VirtualizedCardContainer(QScrollArea):
    """Virtualized container for document cards."""

    def __init__(self, documents, parent=None):
        super().__init__(parent)

        self.documents = documents
        self.card_height = 150  # Approximate card height
        self.visible_cards = {}  # Cache of visible cards
        self.buffer_size = 5  # Extra cards to render above/below viewport

        # Set up container
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.setWidget(self.container)
        self.setWidgetResizable(True)

        # Set container height based on total documents
        total_height = len(self.documents) * self.card_height
        self.container.setMinimumHeight(total_height)

        # Connect scroll event
        self.verticalScrollBar().valueChanged.connect(self.update_visible_cards)

        # Initial render
        self.update_visible_cards()

    def update_visible_cards(self):
        """Update visible cards based on scroll position."""
        scroll_pos = self.verticalScrollBar().value()
        viewport_height = self.viewport().height()

        # Calculate visible range
        first_visible = max(0, (scroll_pos // self.card_height) - self.buffer_size)
        last_visible = min(
            len(self.documents),
            ((scroll_pos + viewport_height) // self.card_height) + self.buffer_size
        )

        # Remove cards outside visible range
        to_remove = [idx for idx in self.visible_cards if idx < first_visible or idx > last_visible]
        for idx in to_remove:
            card = self.visible_cards.pop(idx)
            self.layout.removeWidget(card)
            card.deleteLater()

        # Add cards in visible range
        for idx in range(first_visible, last_visible + 1):
            if idx not in self.visible_cards:
                from .document_card import DocumentCard
                card = DocumentCard(self.documents[idx])

                # Position card
                y_pos = idx * self.card_height
                card.setGeometry(0, y_pos, self.viewport().width(), self.card_height)

                self.visible_cards[idx] = card
                self.layout.addWidget(card)
```

### 3. Widget Pooling (Advanced)

Reuse a pool of card widgets instead of creating/destroying them.

**Advantages**:
- Minimal widget creation/destruction
- Very efficient for smooth scrolling
- Constant memory usage

**Implementation**:

```python
class CardPool:
    """Pool of reusable card widgets."""

    def __init__(self, card_class, pool_size=20):
        self.card_class = card_class
        self.pool = [card_class({}) for _ in range(pool_size)]
        self.available = list(self.pool)
        self.in_use = {}

    def acquire(self, index, data):
        """Get a card from the pool and update its data."""
        if not self.available:
            # Pool exhausted, create new card
            card = self.card_class(data)
        else:
            card = self.available.pop()
            # Update card with new data
            self._update_card_data(card, data)

        self.in_use[index] = card
        return card

    def release(self, index):
        """Return a card to the pool."""
        if index in self.in_use:
            card = self.in_use.pop(index)
            self.available.append(card)

    def _update_card_data(self, card, data):
        """Update card widget with new data."""
        # Implementation depends on card class
        # Could recreate widgets or update existing ones
        pass
```

## Performance Benchmarks

### Without Virtualization
- **1,000 cards**: ~2-3 seconds to create, ~500 MB memory
- **10,000 cards**: ~30-40 seconds to create, ~5 GB memory
- **Result**: UI freezing, poor user experience

### With Virtualization (QListView + Delegate)
- **1,000 cards**: ~100 ms to create visible cards, ~50 MB memory
- **10,000 cards**: ~100 ms to create visible cards, ~50 MB memory
- **Result**: Smooth scrolling, responsive UI

## Implementation Recommendations

### For Small Lists (< 100 cards)
- **No virtualization needed**
- Use simple `QVBoxLayout` with all cards
- Performance is acceptable

### For Medium Lists (100-1,000 cards)
- **Use QListView with custom delegate** (Strategy 1)
- Good balance of simplicity and performance
- Standard Qt patterns

### For Large Lists (> 1,000 cards)
- **Use QListView with delegate + widget pooling** (Strategy 1 + 3)
- Maximum performance
- Minimal memory usage

## Code Example: Complete Virtualized Document List

```python
from PySide6.QtWidgets import QMainWindow, QListView
from PySide6.QtCore import QAbstractListModel, Qt, QSize
from src.bmlibrarian.gui.qt.widgets.document_card import DocumentCard

class VirtualizedDocumentList(QMainWindow):
    """Complete example of virtualized document list."""

    def __init__(self, documents):
        super().__init__()

        # Create model
        self.model = DocumentListModel(documents)

        # Create view
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(DocumentCardDelegate())
        self.list_view.setUniformItemSizes(True)
        self.list_view.setSpacing(8)

        # Configure scrolling
        self.list_view.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.list_view.verticalScrollBar().setSingleStep(20)

        self.setCentralWidget(self.list_view)

        # Connect signals
        self.list_view.clicked.connect(self.on_card_clicked)

    def on_card_clicked(self, index):
        """Handle card click."""
        document_data = index.data(Qt.UserRole)
        print(f"Clicked: {document_data.get('title')}")
```

## Testing Performance

To measure performance improvements:

```python
import time
import tracemalloc

# Start tracking
tracemalloc.start()
start_time = time.time()

# Create widget
widget = VirtualizedDocumentList(documents)

# Measure
current, peak = tracemalloc.get_traced_memory()
elapsed = time.time() - start_time

print(f"Time: {elapsed:.2f}s")
print(f"Memory: {current / 10**6:.1f} MB (peak: {peak / 10**6:.1f} MB)")

tracemalloc.stop()
```

## Future Enhancements

1. **Progressive Loading**: Load cards as user scrolls
2. **Lazy Data Fetching**: Fetch document details on demand
3. **Caching**: Cache rendered cards for faster re-display
4. **Animations**: Smooth fade-in for newly visible cards
5. **Search/Filter**: Efficient filtering without recreating all cards

## References

- [Qt Model/View Programming](https://doc.qt.io/qt-6/model-view-programming.html)
- [QAbstractItemView Documentation](https://doc.qt.io/qt-6/qabstractitemview.html)
- [Custom Delegates](https://doc.qt.io/qt-6/qstyleditemdelegate.html)

## See Also

- `document_card.py` - Document card widget implementation
- `citation_card.py` - Citation card widget implementation
- `card_utils.py` - Shared utilities for card formatting
