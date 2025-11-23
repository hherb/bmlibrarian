# PDF Upload Widget - Developer Specification

This document describes the architecture and implementation of the reusable PDF Upload Widget for BMLibrarian.

## Overview

The PDF Upload Widget provides a complete UI for PDF document import with:
- PDF viewing with PyMuPDF rendering
- Fast regex-based identifier extraction
- Quick database lookup
- LLM-based fallback extraction
- Document matching and selection

## Architecture

### Component Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                        PDFUploadWidget                         │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐│
│  │   PDFViewerWidget    │  │        Metadata Panel            ││
│  │                      │  │  ┌────────────────────────────┐  ││
│  │   - Page rendering   │  │  │ File Selection             │  ││
│  │   - Navigation       │  │  │ Status Display             │  ││
│  │   - Zoom controls    │  │  │ Quick Match Frame          │  ││
│  │                      │  │  │ Metadata Fields            │  ││
│  │                      │  │  │ Matches Tree               │  ││
│  │                      │  │  │ Options                    │  ││
│  │                      │  │  │ Action Buttons             │  ││
│  │                      │  │  └────────────────────────────┘  ││
│  └──────────────────────┘  └──────────────────────────────────┘│
└────────────────────────────────────────────────────────────────┘
              │                         │
              ▼                         ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│   QuickExtractWorker     │  │    LLMExtractWorker      │
│   (QThread)              │  │    (QThread)             │
│                          │  │                          │
│   - Text extraction      │  │   - LLM metadata extract │
│   - Regex DOI/PMID       │  │   - Database matching    │
│   - Quick DB lookup      │  │   - Alternative finding  │
└──────────────────────────┘  └──────────────────────────┘
              │                         │
              └────────────┬────────────┘
                           ▼
              ┌──────────────────────────┐
              │       PDFMatcher         │
              │                          │
              │   - extract_first_page   │
              │   - extract_identifiers  │
              │   - quick_database_lookup│
              │   - extract_metadata_llm │
              │   - find_matching_doc    │
              │   - find_alternatives    │
              └──────────────────────────┘
```

### File Structure

```
src/bmlibrarian/
├── importers/
│   └── pdf_matcher.py           # Core matching logic
└── gui/qt/widgets/
    ├── __init__.py              # Module exports
    ├── pdf_viewer.py            # Existing PDF viewer widget
    ├── pdf_upload_widget.py     # Main reusable widget
    └── pdf_upload_workers.py    # Background worker threads
```

## API Reference

### PDFUploadWidget

Main widget class providing the complete PDF upload interface.

#### Signals

| Signal | Parameters | Description |
|--------|------------|-------------|
| `document_selected` | `int` (doc_id) | Emitted when user selects an existing document |
| `document_created` | `int` (doc_id) | Emitted when a new document is created |
| `pdf_loaded` | `str` (path) | Emitted when a PDF is loaded into the viewer |
| `cancelled` | None | Emitted when user cancels the operation |

#### Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `load_pdf` | `pdf_path: str \| Path` | None | Load a PDF file for analysis |
| `should_ingest` | None | `bool` | Check if PDF ingestion is requested |
| `get_pdf_path` | None | `Optional[Path]` | Get the current PDF path |
| `get_selected_document` | None | `Optional[dict]` | Get the selected document |
| `get_extracted_metadata` | None | `Optional[dict]` | Get extracted metadata |

#### Usage Example

```python
from bmlibrarian.gui.qt.widgets import PDFUploadWidget

class MyApplication(QMainWindow):
    def __init__(self):
        super().__init__()

        # Create widget
        self.pdf_widget = PDFUploadWidget()

        # Connect signals
        self.pdf_widget.document_selected.connect(self.on_document_selected)
        self.pdf_widget.document_created.connect(self.on_document_created)
        self.pdf_widget.cancelled.connect(self.close)

        self.setCentralWidget(self.pdf_widget)

    def on_document_selected(self, doc_id: int):
        """Handle document selection."""
        document = self.pdf_widget.get_selected_document()
        print(f"Selected document {doc_id}: {document['title']}")

        if self.pdf_widget.should_ingest():
            self.ingest_pdf(self.pdf_widget.get_pdf_path(), doc_id)

    def on_document_created(self, doc_id: int):
        """Handle new document creation."""
        metadata = self.pdf_widget.get_extracted_metadata()
        print(f"Created document {doc_id} with title: {metadata['title']}")
```

### QuickExtractWorker

Background worker for fast regex extraction and database lookup.

#### Signals

| Signal | Parameters | Description |
|--------|------------|-------------|
| `quick_match_found` | `QuickMatchResult` | Exact database match found |
| `no_quick_match` | `QuickMatchResult` | No quick match, text available for LLM |
| `error_occurred` | `str` | Error message |
| `status_update` | `str` | Status update message |

### LLMExtractWorker

Background worker for LLM-based metadata extraction.

#### Signals

| Signal | Parameters | Description |
|--------|------------|-------------|
| `extraction_complete` | `LLMExtractResult` | Extraction finished with results |
| `error_occurred` | `str` | Error message |
| `status_update` | `str` | Status update message |

### PDFMatcher Enhanced API

New methods added to support fast extraction:

```python
# Fast regex extraction
def extract_identifiers_regex(self, text: str) -> ExtractedIdentifiers:
    """Extract DOI/PMID using regex patterns (~100ms)."""

# Quick database lookup
def quick_database_lookup(
    self,
    doi: Optional[str] = None,
    pmid: Optional[str] = None
) -> Optional[dict]:
    """Fast exact-match lookup by DOI or PMID (~100ms)."""

# Find alternative matches
def find_alternative_matches(
    self,
    title: str,
    exclude_id: Optional[int] = None
) -> list[dict]:
    """Find similar documents by title with relaxed threshold."""
```

## Data Types

### ExtractedIdentifiers

```python
@dataclass
class ExtractedIdentifiers:
    doi: Optional[str]
    pmid: Optional[str]
    extraction_method: str = "regex"

    def has_identifiers(self) -> bool:
        """Check if any identifiers were extracted."""
```

### QuickMatchResult

```python
@dataclass
class QuickMatchResult:
    success: bool
    identifiers: Optional[ExtractedIdentifiers] = None
    document: Optional[dict] = None
    extracted_text: Optional[str] = None
    error: Optional[str] = None

    def has_quick_match(self) -> bool:
        """Check if a quick database match was found."""
```

### LLMExtractResult

```python
@dataclass
class LLMExtractResult:
    success: bool
    metadata: Optional[dict] = None
    document: Optional[dict] = None
    alternatives: Optional[list[dict]] = None
    error: Optional[str] = None
```

## Extraction Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                         PDF Selected                             │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│          Extract text from first page (PyMuPDF)                  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│          Regex extraction for DOI/PMID (~100ms)                  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
              ┌─────────────────┴─────────────────┐
              │ Identifiers found?                │
              └─────────────────┬─────────────────┘
                    Yes │               │ No
                        ▼               ▼
┌───────────────────────────┐  ┌────────────────────────────────┐
│ Quick database lookup     │  │  Start LLM extraction          │
│ by DOI/PMID (~100ms)      │  │  (5-30 seconds)                │
└───────────────┬───────────┘  └────────────────┬───────────────┘
                │                               │
      ┌─────────┴─────────┐                     │
      │ Match found?      │                     │
      └─────────┬─────────┘                     │
          Yes │       │ No                      │
              ▼       ▼                         ▼
┌─────────────────┐  ┌─────────────────────────────────────────┐
│ Show quick      │  │ LLM extracts metadata:                  │
│ match panel     │  │ - DOI, PMID, Title, Authors             │
│                 │  │ - Database matching                     │
│ User can:       │  │ - Alternative matches                   │
│ - Accept match  │  └─────────────────────────────────────────┘
│ - Try LLM       │              │
└─────────────────┘              ▼
                    ┌────────────────────────────────────────┐
                    │ Display matches in tree widget         │
                    │ User selects or creates new document   │
                    └────────────────────────────────────────┘
```

## Regex Patterns

### DOI Pattern

```python
DOI_PATTERN = re.compile(
    r'(?:doi[:\s]*)?'  # Optional "doi:" prefix
    r'(10\.\d{4,}/[^\s\"\'\<\>\]\)]+)',  # Standard DOI format
    re.IGNORECASE
)
```

Matches:
- `10.1234/example.123`
- `doi: 10.1234/example.123`
- `DOI:10.1234/example.123`
- `https://doi.org/10.1234/example.123`

### PMID Patterns

```python
PMID_PATTERNS = [
    re.compile(r'PMID[:\s]*(\d{7,8})', re.IGNORECASE),
    re.compile(r'PubMed\s*ID[:\s]*(\d{7,8})', re.IGNORECASE),
    re.compile(r'(?:^|\s)PMID(\d{7,8})(?:\s|$)', re.IGNORECASE),
]
```

Matches:
- `PMID: 12345678`
- `PMID12345678`
- `PubMed ID: 12345678`

## Constants

```python
# UI layout
SPLITTER_RATIO_PDF = 60          # PDF viewer width %
SPLITTER_RATIO_METADATA = 40     # Metadata panel width %

# Database matching
TITLE_SIMILARITY_THRESHOLD_STRICT = 0.6   # For primary matching
TITLE_SIMILARITY_THRESHOLD_RELAXED = 0.3  # For alternatives
MAX_ALTERNATIVE_MATCHES = 5

# LLM extraction
LLM_TEXT_TRUNCATION_LENGTH = 3000
LLM_TEMPERATURE = 0.1
LLM_TOP_P = 0.9

# Text extraction
MIN_EXTRACTED_TEXT_LENGTH = 50
```

## Integration Examples

### Replacing Existing PDF Upload Tab

```python
# In paper_weight_lab/tabs/__init__.py

# Before:
from .pdf_upload_tab import PDFUploadTab

# After:
from bmlibrarian.gui.qt.widgets import PDFUploadWidget

class PDFUploadTab(QWidget):
    """Wrapper to integrate PDFUploadWidget into tab interface."""

    document_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.upload_widget = PDFUploadWidget()
        self.upload_widget.document_selected.connect(self.document_selected)
        layout.addWidget(self.upload_widget)
```

### Embedding in Dialog

```python
from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox
from bmlibrarian.gui.qt.widgets import PDFUploadWidget

class PDFSelectDialog(QDialog):
    """Dialog for PDF selection and matching."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select PDF Document")
        self.resize(1200, 800)

        layout = QVBoxLayout(self)

        self.upload_widget = PDFUploadWidget()
        self.upload_widget.document_selected.connect(self._on_selected)
        self.upload_widget.cancelled.connect(self.reject)
        layout.addWidget(self.upload_widget)

        self._selected_doc_id = None

    def _on_selected(self, doc_id: int):
        self._selected_doc_id = doc_id
        self.accept()

    def get_selected_document_id(self) -> Optional[int]:
        return self._selected_doc_id
```

## Testing

Run the standalone demo for interactive testing:

```bash
uv run python pdf_upload_widget_demo.py
```

The demo application provides:
- Event logging for all signal emissions
- Full widget functionality
- Command-line PDF loading

## Golden Rule Compliance

The implementation follows all BMLibrarian golden rules:

1. **Input Validation**: PDF paths validated before processing
2. **No Magic Numbers**: All constants defined at module level
3. **No Hardcoded Paths**: Uses configuration for PDF storage
4. **Ollama Library**: Uses `ollama` Python library (not HTTP requests)
5. **Database Manager**: All queries via DatabaseManager
6. **Type Hints**: Full type annotations on all functions
7. **Docstrings**: Comprehensive documentation
8. **Error Handling**: Try/except with logging throughout
9. **Centralized Styling**: Uses StylesheetGenerator and get_font_scale()
10. **DPI Scaling**: All dimensions via dpi_scale system

## See Also

- [PDF Matcher Library](../developers/pdf_matcher_system.md)
- [Qt Widget Architecture](../developers/qt_widget_architecture.md)
- [Document Card Factory System](../developers/document_card_factory_system.md)
