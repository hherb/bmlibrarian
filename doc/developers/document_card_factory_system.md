# Document Card Factory System

## Overview

The Document Card Factory system provides a unified, framework-agnostic interface for creating document cards across different UI frameworks (Flet and Qt). This architecture ensures consistency in appearance and functionality while allowing for framework-specific implementations.

## Architecture

### Key Components

1. **DocumentCardFactoryBase** (`document_card_factory_base.py`)
   - Abstract base class defining the factory interface
   - Common utility methods for formatting metadata, authors, scores
   - PDF state determination logic
   - Framework-agnostic data structures

2. **FletDocumentCardFactory** (`flet_document_card_factory.py`)
   - Flet-specific implementation
   - Wraps existing `UnifiedDocumentCard` class
   - Provides Flet-style PDF buttons with three states

3. **QtDocumentCardFactory** (`qt/qt_document_card_factory.py`)
   - Qt-specific implementation
   - Integrates with existing Qt card widgets
   - Adds PDF button functionality to Qt cards (previously missing)

### Data Structures

#### DocumentCardData
```python
@dataclass
class DocumentCardData:
    """Data for rendering a document card."""
    # Core document data
    doc_id: int
    title: str
    abstract: Optional[str] = None
    authors: Optional[List[str]] = None
    year: Optional[int] = None
    journal: Optional[str] = None
    pmid: Optional[str] = None
    doi: Optional[str] = None
    source: Optional[str] = None

    # Scoring data
    relevance_score: Optional[float] = None
    human_score: Optional[float] = None
    confidence: Optional[str] = None

    # Citation data
    citations: Optional[List[Dict[str, Any]]] = None

    # PDF data
    pdf_path: Optional[Path] = None
    pdf_url: Optional[str] = None

    # Display options
    context: CardContext = CardContext.LITERATURE
    show_abstract: bool = True
    show_metadata: bool = True
    show_pdf_button: bool = True
    expanded_by_default: bool = False

    # Callbacks
    on_score_change: Optional[Callable] = None
    on_citation_select: Optional[Callable] = None
    on_pdf_action: Optional[Callable] = None
```

#### PDFButtonConfig
```python
@dataclass
class PDFButtonConfig:
    """Configuration for PDF button behavior."""
    state: PDFButtonState
    pdf_path: Optional[Path] = None
    pdf_url: Optional[str] = None
    on_view: Optional[Callable] = None
    on_fetch: Optional[Callable] = None
    on_upload: Optional[Callable] = None
    show_notifications: bool = True
```

#### CardContext
```python
class CardContext(Enum):
    """Context in which a document card is being displayed."""
    LITERATURE = "literature"
    SCORING = "scoring"
    CITATIONS = "citations"
    COUNTERFACTUAL = "counterfactual"
    REPORT = "report"
    SEARCH = "search"
    REVIEW = "review"
```

#### PDFButtonState
```python
class PDFButtonState(Enum):
    """State of the PDF button for a document."""
    VIEW = "view"      # Local PDF exists, can view
    FETCH = "fetch"    # PDF URL available, can download
    UPLOAD = "upload"  # No PDF, allow manual upload
    HIDDEN = "hidden"  # No PDF button shown
```

## PDF Button Three-State System

The PDF button has three distinct states based on PDF availability:

### 1. VIEW State (Blue)
- **Condition**: Local PDF file exists
- **Button Text**: "📄 View Full Text"
- **Action**: Opens PDF in viewer (system default or embedded viewer)
- **Color**: Blue (#1976D2)

### 2. FETCH State (Orange)
- **Condition**: PDF URL available but no local file
- **Button Text**: "⬇️ Fetch Full Text"
- **Action**: Downloads PDF from URL, then transitions to VIEW state
- **Color**: Orange (#F57C00)

### 3. UPLOAD State (Green)
- **Condition**: No local PDF and no URL
- **Button Text**: "📤 Upload Full Text"
- **Action**: Opens file picker for manual upload, then transitions to VIEW state
- **Color**: Green (#388E3C)

### State Transitions

```
┌─────────┐  Download   ┌──────┐
│  FETCH  │ ───────────>│ VIEW │
└─────────┘             └──────┘
                           ^
┌─────────┐  Upload        │
│ UPLOAD  │ ───────────────┘
└─────────┘
```

After successful fetch or upload, the button automatically transitions to VIEW state.

## Usage Examples

### Basic Flet Example

```python
import flet as ft
from bmlibrarian.gui.flet_document_card_factory import FletDocumentCardFactory
from bmlibrarian.gui.document_card_factory_base import DocumentCardData, CardContext

def main(page: ft.Page):
    # Create factory
    factory = FletDocumentCardFactory(page=page)

    # Create card data
    card_data = DocumentCardData(
        doc_id=12345,
        title="Example Study on Cardiovascular Health",
        abstract="This study examines...",
        authors=["Smith J", "Johnson A"],
        year=2023,
        journal="Journal of Cardiology",
        pmid="12345678",
        relevance_score=4.5,
        pdf_url="https://example.com/paper.pdf",
        context=CardContext.LITERATURE,
        show_pdf_button=True
    )

    # Create card
    card = factory.create_card(card_data)

    # Add to page
    page.add(card)

ft.app(target=main)
```

### Basic Qt Example

```python
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from bmlibrarian.gui.qt.qt_document_card_factory import QtDocumentCardFactory
from bmlibrarian.gui.document_card_factory_base import DocumentCardData, CardContext

app = QApplication([])

# Create factory
factory = QtDocumentCardFactory()

# Create card data
card_data = DocumentCardData(
    doc_id=12345,
    title="Example Study on Cardiovascular Health",
    abstract="This study examines...",
    authors=["Smith J", "Johnson A"],
    year=2023,
    journal="Journal of Cardiology",
    pmid="12345678",
    relevance_score=4.5,
    context=CardContext.LITERATURE,
    show_pdf_button=True
)

# Create card
card = factory.create_card(card_data)

# Add to layout
widget = QWidget()
layout = QVBoxLayout(widget)
layout.addWidget(card)
widget.show()

app.exec()
```

### Custom PDF Handlers

```python
from pathlib import Path
from bmlibrarian.gui.flet_document_card_factory import FletDocumentCardFactory
from bmlibrarian.gui.document_card_factory_base import DocumentCardData

def custom_pdf_action_handler(action: str, doc_id: int, *args):
    """Custom handler for PDF actions."""
    if action == 'view':
        print(f"Viewing PDF for document {doc_id}")
        # Custom view logic
    elif action == 'fetch':
        pdf_url = args[0]
        print(f"Fetching PDF from {pdf_url}")
        # Custom fetch logic
        return Path("/path/to/downloaded.pdf")
    elif action == 'upload':
        print(f"Uploading PDF for document {doc_id}")
        # Custom upload logic
        return Path("/path/to/uploaded.pdf")

# Use with card data
card_data = DocumentCardData(
    doc_id=12345,
    title="Example Study",
    on_pdf_action=custom_pdf_action_handler,
    show_pdf_button=True
)
```

## Implementation Details

### PDF State Determination Logic

The factory automatically determines the appropriate PDF button state:

```python
def determine_pdf_state(
    self,
    doc_id: int,
    pdf_path: Optional[Path] = None,
    pdf_url: Optional[str] = None
) -> PDFButtonState:
    # 1. Check explicit path
    if pdf_path and pdf_path.exists():
        return PDFButtonState.VIEW

    # 2. Check standard location
    standard_path = self.base_pdf_dir / f"{doc_id}.pdf"
    if standard_path.exists():
        return PDFButtonState.VIEW

    # 3. Check if URL available
    if pdf_url:
        return PDFButtonState.FETCH

    # 4. Default to upload
    return PDFButtonState.UPLOAD
```

### Framework-Specific Implementations

#### Flet Implementation

The Flet factory wraps the existing `UnifiedDocumentCard` class and maps the factory's data structures to Flet's expected format:

```python
class FletDocumentCardFactory(DocumentCardFactoryBase):
    def create_card(self, card_data: DocumentCardData) -> ft.ExpansionTile:
        # Convert CardContext to DocumentCardContext
        # Prepare document dictionary
        # Delegate to UnifiedDocumentCard
        return self._card_creator.create_card(...)
```

#### Qt Implementation

The Qt factory integrates with existing Qt card widgets and adds PDF button functionality:

```python
class QtDocumentCardFactory(DocumentCardFactoryBase):
    def create_card(self, card_data: DocumentCardData) -> QFrame:
        # Create CollapsibleDocumentCard
        card = CollapsibleDocumentCard(doc)

        # Add PDF button to details layout
        if card_data.show_pdf_button:
            pdf_button = self._create_pdf_button_for_card(card_data)
            card.details_layout.addWidget(pdf_button)

        return card
```

### Qt PDF Button Widget

The `PDFButtonWidget` is a custom Qt widget that manages the three PDF button states:

```python
class PDFButtonWidget(QPushButton):
    """Qt PDF button with three states."""

    pdf_viewed = Signal()
    pdf_fetched = Signal(Path)
    pdf_uploaded = Signal(Path)

    def _handle_click(self):
        if self.config.state == PDFButtonState.VIEW:
            self._handle_view()
        elif self.config.state == PDFButtonState.FETCH:
            self._handle_fetch()
        elif self.config.state == PDFButtonState.UPLOAD:
            self._handle_upload()

    def _transition_to_view(self, pdf_path: Path):
        """Transition to VIEW state after fetch/upload."""
        self.config.pdf_path = pdf_path
        self.config.state = PDFButtonState.VIEW
        self._update_button_appearance()
```

## Extending the Factory System

### Creating a New Card Context

1. Add new context to `CardContext` enum:
```python
class CardContext(Enum):
    LITERATURE = "literature"
    SCORING = "scoring"
    # ... existing contexts
    NEW_CONTEXT = "new_context"  # Add new context
```

2. Update framework-specific factories to handle new context:
```python
def create_card(self, card_data: DocumentCardData):
    if card_data.context == CardContext.NEW_CONTEXT:
        # Handle new context-specific rendering
        pass
```

### Adding Custom Card Variations

To create a new card variation:

1. Subclass the appropriate factory
2. Override `create_card()` method
3. Add custom rendering logic

Example:
```python
class CustomFletCardFactory(FletDocumentCardFactory):
    def create_card(self, card_data: DocumentCardData):
        # Custom pre-processing
        card_data = self._customize_card_data(card_data)

        # Call parent implementation
        card = super().create_card(card_data)

        # Custom post-processing
        return self._add_custom_features(card)
```

## Testing

### Unit Tests

Run the complete test suite:
```bash
uv run python -m pytest tests/test_document_card_factory.py -v
```

### Test Coverage

The test suite covers:
- PDF state determination logic
- Author formatting
- Metadata formatting
- Score color mapping
- Abstract truncation
- Card creation for both frameworks
- PDF button widget functionality
- Custom callback handling

### Example Test

```python
def test_determine_pdf_state_view(tmp_path):
    """Test PDF state when local file exists."""
    pdf_file = tmp_path / "12345.pdf"
    pdf_file.write_text("test")

    factory = TestFactory(base_pdf_dir=tmp_path)
    state = factory.determine_pdf_state(12345)

    assert state == PDFButtonState.VIEW
```

## Best Practices

### 1. Use Factory Pattern for All New Cards

Always use the factory pattern when creating new document cards:

❌ **Don't**:
```python
# Directly instantiating card classes
card = UnifiedDocumentCard(page, pdf_manager)
card.create_card(index, doc, ...)
```

✅ **Do**:
```python
# Using factory pattern
factory = FletDocumentCardFactory(page, pdf_manager)
card_data = DocumentCardData(doc_id=123, title="Example")
card = factory.create_card(card_data)
```

### 2. Leverage CardContext

Use appropriate context for different scenarios:

```python
# Literature browsing
card_data = DocumentCardData(..., context=CardContext.LITERATURE)

# Document scoring
card_data = DocumentCardData(..., context=CardContext.SCORING)

# Citation extraction
card_data = DocumentCardData(..., context=CardContext.CITATIONS)
```

### 3. Handle PDF Actions Consistently

Implement PDF action handlers that return appropriate values:

```python
def on_pdf_fetch(url: str) -> Optional[Path]:
    """Fetch handler should return downloaded path."""
    try:
        path = download_pdf(url)
        return path
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return None
```

### 4. Maintain Consistent Styling

Use the factory's built-in utilities for consistent formatting:

```python
# Use factory methods
authors_text = factory.format_authors(authors, max_authors=3)
score_color = factory.get_score_color(relevance_score)
metadata = factory.format_metadata(year, journal, pmid, doi)

# Don't reinvent formatting logic
```

### 5. Test Both Frameworks

When making changes to the factory system, test both Flet and Qt implementations:

```bash
# Test Flet
uv run python examples/document_card_factory_demo.py --framework flet

# Test Qt
uv run python examples/document_card_factory_demo.py --framework qt
```

## Migration Guide

### Migrating Existing Code to Factory Pattern

#### Before (Direct Card Creation)

```python
# Old Flet code
card_creator = UnifiedDocumentCard(page, pdf_manager)
card = card_creator.create_card(
    index=0,
    doc=doc_dict,
    context="literature",
    ai_score=4.5,
    show_scoring_controls=False
)
```

#### After (Factory Pattern)

```python
# New factory-based code
from bmlibrarian.gui.flet_document_card_factory import FletDocumentCardFactory
from bmlibrarian.gui.document_card_factory_base import DocumentCardData, CardContext

factory = FletDocumentCardFactory(page, pdf_manager)
card_data = DocumentCardData(
    doc_id=doc_dict['id'],
    title=doc_dict['title'],
    abstract=doc_dict.get('abstract'),
    authors=doc_dict.get('authors'),
    year=doc_dict.get('year'),
    journal=doc_dict.get('publication'),
    pmid=doc_dict.get('pmid'),
    doi=doc_dict.get('doi'),
    relevance_score=4.5,
    context=CardContext.LITERATURE
)
card = factory.create_card(card_data)
```

## Performance Considerations

### Card Creation Overhead

The factory pattern adds minimal overhead:
- Factory instantiation: O(1)
- Card data creation: O(1)
- Card creation: Same as direct instantiation

### Memory Usage

- Factory instances are lightweight (shared utilities)
- Card data structures use dataclasses (efficient)
- Recommended: Create one factory instance per page/window

### Optimization Tips

1. **Reuse Factory Instances**:
```python
# Create once
factory = FletDocumentCardFactory(page)

# Reuse for multiple cards
for doc in documents:
    card_data = DocumentCardData(...)
    card = factory.create_card(card_data)
```

2. **Lazy PDF State Determination**:
```python
# PDF state is only determined when card is created
# No upfront filesystem checks
```

3. **Batch Card Creation**:
```python
# Create cards in batch
cards = [factory.create_card(DocumentCardData(...))
         for doc in documents]
```

## Troubleshooting

### PDF Button Not Showing

**Problem**: PDF button not appearing in card

**Solutions**:
1. Check `show_pdf_button=True` in `DocumentCardData`
2. Verify PDF state is not `HIDDEN`
3. For Qt: Ensure `details_layout` is accessible

### PDF State Incorrect

**Problem**: Button shows wrong state (e.g., FETCH instead of VIEW)

**Solutions**:
1. Check `base_pdf_dir` configuration
2. Verify PDF file exists at expected location
3. Check file permissions
4. Use `factory.get_pdf_path(doc_id)` to debug

### Qt Card Not Showing PDF Button

**Problem**: Qt cards don't have PDF buttons after migration

**Solution**:
```python
# Ensure using QtDocumentCardFactory
from bmlibrarian.gui.qt.qt_document_card_factory import QtDocumentCardFactory

factory = QtDocumentCardFactory()
card = factory.create_card(card_data)  # PDF button included
```

## Related Documentation

- [User Guide: Multi-Model Query Generation](../users/multi_model_query_guide.md)
- [Developer Guide: Agent Module](agent_module.md)
- [Developer Guide: Citation System](citation_system.md)
- [Examples: Document Card Factory Demo](../../examples/document_card_factory_demo.py)

## API Reference

See inline documentation in:
- `src/bmlibrarian/gui/document_card_factory_base.py`
- `src/bmlibrarian/gui/flet_document_card_factory.py`
- `src/bmlibrarian/gui/qt/qt_document_card_factory.py`
