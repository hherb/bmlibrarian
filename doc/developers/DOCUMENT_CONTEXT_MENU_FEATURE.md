# Document Context Menu "Send to" Feature

## Overview

This document describes the implementation of a right-click context menu system for document cards in the BMLibrarian Qt GUI. This feature allows users to send documents from the Search tab to any active "lab" tab (PICO Lab, PRISMA 2020 Lab, Study Assessment Lab, etc.) via a context menu.

## Architecture

### Components

1. **IDocumentReceiver Interface** (`src/bmlibrarian/gui/qt/core/document_receiver.py`)
   - Abstract interface for plugins that can receive documents
   - Methods:
     - `get_receiver_id()` - Unique identifier
     - `get_receiver_name()` - Display name for menu
     - `can_receive_document(document_data)` - Filter capability
     - `receive_document(document_data)` - Handle incoming document
     - `get_receiver_icon()` - Optional icon (future enhancement)
     - `get_receiver_description()` - Optional tooltip text

2. **DocumentReceiverRegistry** (`src/bmlibrarian/gui/qt/core/document_receiver_registry.py`)
   - Singleton registry managing all document receivers
   - Methods:
     - `register_receiver(receiver)` - Register a receiver
     - `unregister_receiver(receiver_id)` - Unregister a receiver
     - `get_available_receivers(document_data)` - Get receivers that can accept a document
     - `send_document(receiver_id, document_data)` - Send document to specific receiver

3. **DocumentCard Updates** (`src/bmlibrarian/gui/qt/widgets/document_card.py`)
   - Added context menu support:
     - Right-click on any document card shows "Send to" submenu
     - Dynamically builds submenu from registered receivers
     - Sends document via registry and navigates to target tab

4. **Lab Tab Implementations**
   - Updated plugins to implement IDocumentReceiver:
     - **PICO Lab** (`pico_lab/`)
     - **PRISMA 2020 Lab** (`prisma2020_lab/`)
     - **Study Assessment Lab** (`study_assessment/`)
   - Each registers itself on widget creation
   - Each unregisters itself on cleanup

## Usage

### For End Users

1. **Search for documents** in the Document Search tab
2. **Right-click** on any document card
3. **Select "Send to"** from the context menu
4. **Choose a lab** from the submenu (e.g., "PICO Lab", "PRISMA 2020 Lab")
5. The **selected tab is activated** and the **document is automatically loaded**

### For Developers - Adding New Receivers

To make a new tab receive documents:

```python
# 1. Import the interface
from ...core.document_receiver import IDocumentReceiver

# 2. Implement the interface in your tab widget
class MyLabTabWidget(QWidget, IDocumentReceiver):

    def get_receiver_id(self) -> str:
        return "my_lab"  # Must match plugin_id

    def get_receiver_name(self) -> str:
        return "My Lab"  # Display name in menu

    def get_receiver_description(self) -> Optional[str]:
        return "Description shown in tooltip"

    def can_receive_document(self, document_data: Dict[str, Any]) -> bool:
        # Return True if you can process this document
        doc_id = document_data.get('id') or document_data.get('document_id')
        return doc_id is not None

    def receive_document(self, document_data: Dict[str, Any]) -> None:
        # Load the document
        doc_id = document_data.get('id') or document_data.get('document_id')
        if doc_id:
            self.doc_id_input.setText(str(doc_id))
            self._load_document()

# 3. Register in your plugin's create_widget()
from ...core.document_receiver_registry import DocumentReceiverRegistry

def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
    self.tab_widget = MyLabTabWidget(parent)

    # Register as document receiver
    registry = DocumentReceiverRegistry()
    registry.register_receiver(self.tab_widget)

    return self.tab_widget

# 4. Unregister in your plugin's cleanup()
def cleanup(self):
    if self.tab_widget:
        registry = DocumentReceiverRegistry()
        registry.unregister_receiver(self.tab_widget.get_receiver_id())
        self.tab_widget.cleanup()
```

## Design Decisions

### Why Singleton Registry?
- Single source of truth for all receivers
- Avoids passing registry instances through constructors
- Simple access pattern from any component

### Why Interface-Based?
- Loose coupling between components
- Easy to add new receivers without modifying existing code
- Type safety and IDE autocomplete support

### Why EventBus for Navigation?
- Existing infrastructure for tab navigation
- Consistent with other plugin communication patterns
- Decouples context menu from MainWindow

### Why can_receive_document()?
- Allows receivers to filter documents (e.g., PRISMA 2020 only accepts systematic reviews)
- Future enhancement: Only show applicable receivers
- Currently, all lab tabs accept all documents

## Benefits

1. **Improved Workflow**: Direct document transfer from search results to analysis tools
2. **Extensible**: Easy to add new receivers without modifying existing code
3. **Discoverable**: Context menu makes feature obvious to users
4. **Type-Safe**: Interface ensures all receivers implement required methods
5. **Clean Architecture**: Follows plugin system patterns

## Future Enhancements

1. **Document Type Filtering**: PRISMA 2020 Lab could filter to only systematic reviews
2. **Batch Send**: Send multiple documents to a receiver
3. **Recent Receivers**: Quick access to recently used receivers
4. **Keyboard Shortcuts**: Quick send via keyboard
5. **Icon Support**: Visual icons in context menu for each receiver
6. **Cross-Tab History**: Track document flow across tabs for reproducibility

## Files Modified

### New Files
- `src/bmlibrarian/gui/qt/core/document_receiver.py`
- `src/bmlibrarian/gui/qt/core/document_receiver_registry.py`

### Modified Files
- `src/bmlibrarian/gui/qt/core/__init__.py`
- `src/bmlibrarian/gui/qt/widgets/document_card.py`
- `src/bmlibrarian/gui/qt/plugins/pico_lab/pico_lab_tab.py`
- `src/bmlibrarian/gui/qt/plugins/pico_lab/plugin.py`
- `src/bmlibrarian/gui/qt/plugins/prisma2020_lab/prisma2020_lab_tab.py`
- `src/bmlibrarian/gui/qt/plugins/prisma2020_lab/plugin.py`
- `src/bmlibrarian/gui/qt/plugins/study_assessment/study_assessment_tab.py`
- `src/bmlibrarian/gui/qt/plugins/study_assessment/plugin.py`

## Testing

### Manual Testing Steps

1. **Basic Functionality**:
   - Launch Qt GUI: `uv run python bmlibrarian_qt.py`
   - Go to Document Search tab
   - Search for documents
   - Right-click on a document card
   - Verify "Send to" submenu appears with 3 options:
     - PICO Lab
     - PRISMA 2020 Lab
     - Study Assessment Lab
   - Select each option and verify:
     - Tab switches to selected lab
     - Document ID is populated
     - Document loads automatically

2. **Multiple Documents**:
   - Send different documents to different labs
   - Verify each lab maintains its own document state

3. **Error Handling**:
   - Try sending a document with invalid ID
   - Verify graceful error handling

4. **Registration/Unregistration**:
   - Check registry statistics: `registry.get_statistics()`
   - Verify receivers are properly registered on startup
   - Close tabs and verify unregistration (if plugins support hot-reload)

### Unit Test Ideas (Future Work)

```python
# tests/test_document_receiver_registry.py
def test_register_receiver():
    """Test receiver registration."""
    registry = DocumentReceiverRegistry()
    receiver = MockReceiver()
    registry.register_receiver(receiver)
    assert receiver.get_receiver_id() in registry.get_statistics()['receiver_ids']

def test_get_available_receivers():
    """Test filtering receivers by document type."""
    registry = DocumentReceiverRegistry()
    receiver1 = MockReceiver(accepts_all=True)
    receiver2 = MockReceiver(accepts_all=False)
    registry.register_receiver(receiver1)
    registry.register_receiver(receiver2)

    doc_data = {'id': 123}
    available = registry.get_available_receivers(doc_data)
    assert len(available) == 1
    assert available[0].get_receiver_id() == receiver1.get_receiver_id()

def test_send_document():
    """Test sending document to receiver."""
    registry = DocumentReceiverRegistry()
    receiver = MockReceiver()
    registry.register_receiver(receiver)

    doc_data = {'id': 123, 'title': 'Test'}
    success = registry.send_document(receiver.get_receiver_id(), doc_data)
    assert success
    assert receiver.last_received_document == doc_data
```

## Troubleshooting

### Context Menu Doesn't Appear
- Check that document card has `setContextMenuPolicy(Qt.CustomContextMenu)`
- Check that `customContextMenuRequested` signal is connected
- Verify at least one receiver is registered: `DocumentReceiverRegistry().get_statistics()`

### Receiver Not in Menu
- Verify receiver is registered in plugin's `create_widget()`
- Check `can_receive_document()` returns True
- Check receiver ID matches plugin ID for navigation

### Document Not Loading
- Verify `receive_document()` implementation
- Check document ID extraction: `doc_data.get('id') or doc_data.get('document_id')`
- Verify `_load_document()` method exists and works

### Tab Not Switching
- Check EventBus navigation signal is emitted
- Verify receiver_id matches plugin_id in metadata
- Check MainWindow handles `navigation_requested` signal

## Conclusion

This feature provides a flexible, extensible mechanism for transferring documents between tabs in the BMLibrarian Qt GUI. The interface-based design makes it easy to add new receivers, and the registry pattern ensures clean management of available receivers.
