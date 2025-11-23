# PaperChecker Laboratory - Developer Documentation

This document provides technical details for developers working with or extending the PaperChecker Laboratory interface.

## Architecture Overview

The PaperChecker Laboratory is a PySide6/Qt-based GUI application that provides interactive testing and exploration of the PaperChecker fact-checking system. It follows a modular package architecture similar to `paper_weight_lab`.

### Component Structure

```
paper_checker_lab.py (root)              # Entry point script
├── argparse configuration               # CLI argument handling
├── logging setup                        # Debug mode configuration
└── Qt/Flet app launcher                 # --flet flag for legacy mode

src/bmlibrarian/lab/paper_checker_lab/   # Main package
├── __init__.py                          # Lazy imports, module exports
├── constants.py                         # UI constants (no magic numbers)
├── utils.py                             # Pure utility functions (no Qt)
├── worker.py                            # QThread workers
├── widgets.py                           # Custom Qt widgets
├── dialogs.py                           # Dialog classes
├── main_window.py                       # Main QMainWindow (~150 lines)
└── tabs/
    ├── __init__.py                      # Tab exports
    ├── input_tab.py                     # Text input and PMID lookup
    ├── pdf_upload_tab.py                # PDF upload and extraction
    ├── workflow_tab.py                  # Workflow progress visualization
    └── results_tab.py                   # Results display (5 sub-tabs)
```

### Key Design Patterns

1. **No Magic Numbers**: All dimensions, colors, and configuration values are defined in `constants.py`
2. **DPI-Aware Scaling**: All dimensions use `get_font_scale()` from the central styling system
3. **No Inline Stylesheets**: Uses `get_stylesheet_generator()` for consistent styling
4. **Pure Utility Functions**: `utils.py` contains framework-independent helpers
5. **Lazy Qt Imports**: Constants and utils can be imported without Qt/display
6. **Non-Blocking UI**: QThread workers with signal-based progress updates
7. **Type Hints**: All parameters and return values are typed
8. **Docstrings**: All classes, methods, and functions are documented
9. **Error Handling**: Comprehensive try-catch with user-friendly messages

## Module Reference

### constants.py

UI constants with no Qt dependencies:

```python
# Window dimensions
WINDOW_MIN_WIDTH = 1200
WINDOW_MIN_HEIGHT = 750

# Tab indices
TAB_INDEX_INPUT = 0
TAB_INDEX_PDF_UPLOAD = 1
TAB_INDEX_WORKFLOW = 2
TAB_INDEX_RESULTS = 3

# Workflow steps (11 total)
WORKFLOW_STEPS = [
    "Initializing",
    "Extracting statements",
    ...
]

# Colors (Qt-compatible hex strings)
VERDICT_COLORS = {
    "supports": "#43A047",
    "contradicts": "#E53935",
    "undecided": "#FB8C00"
}
```

### utils.py

Pure utility functions, easily testable without Qt:

```python
def validate_abstract(abstract: str) -> Tuple[bool, str]:
    """Validate abstract text for processing."""

def format_verdict_display(verdict: str) -> Tuple[str, str]:
    """Format verdict for display with color."""

def format_search_stats(search_results: Any) -> Dict[str, Any]:
    """Format search results statistics."""

def get_workflow_step_index(step_name: str) -> int:
    """Get the index of a workflow step by name."""
```

### worker.py

Background QThread workers:

```python
class PaperCheckWorker(QThread):
    """Background worker for paper checking."""
    progress_update = Signal(str, float)  # (step_name, progress)
    check_complete = Signal(object)       # PaperCheckResult
    check_error = Signal(str)             # error message

class PDFAnalysisWorker(QThread):
    """Background worker for PDF analysis."""
    progress_update = Signal(str)         # status message
    analysis_complete = Signal(dict)      # extracted data
    analysis_error = Signal(str)          # error message

class DocumentFetchWorker(QThread):
    """Background worker for PMID lookup."""
    fetch_complete = Signal(dict)         # document data
    fetch_error = Signal(str)             # error message
```

### widgets.py

Custom Qt widgets:

```python
class StatusSpinnerWidget(QWidget):
    """Animated spinner with status text."""

class WorkflowStepCard(QFrame):
    """Card showing workflow step progress."""

class VerdictBadge(QFrame):
    """Colored verdict badge."""

class CitationCardWidget(QFrame):
    """Expandable citation display card."""

class StatisticsSection(QGroupBox):
    """Statistics display with chips."""
```

### dialogs.py

Dialog classes:

```python
class FullTextDialog(QDialog):
    """Display full untruncated text."""

class ExportPreviewDialog(QDialog):
    """Preview and save export content."""

class PMIDLookupDialog(QDialog):
    """Search database for documents by PMID."""
```

### tabs/

Tab implementations following the pattern:

```python
class InputTab(QWidget):
    """Abstract text input and PMID lookup."""
    check_requested = Signal(str, dict)  # (abstract, metadata)
    clear_requested = Signal()

class PDFUploadTab(QWidget):
    """PDF upload and abstract extraction."""
    abstract_extracted = Signal(str, dict)  # (abstract, metadata)
    check_requested = Signal(str, dict)

class WorkflowTab(QWidget):
    """Workflow progress visualization."""
    abort_requested = Signal()

class ResultsTab(QWidget):
    """Results display with 5 sub-tabs."""
```

### main_window.py

Lean coordinator (~150 lines):

```python
class PaperCheckerLab(QMainWindow):
    """Main application window."""

    def __init__(self):
        # Initialize agent
        # Create tabs
        # Connect signals

    def _start_check(self, abstract: str, metadata: Dict):
        """Start paper check in background."""

    def _on_check_complete(self, result: PaperCheckResult):
        """Handle check completion."""
```

## Signal Flow

```
User Input (Text or PDF)
    ↓
InputTab.check_requested / PDFUploadTab.check_requested
    ↓
PaperCheckerLab._start_check()
    ↓
Creates PaperCheckWorker
    ↓
Worker.progress_update → WorkflowTab.update_step()
    ↓
Worker.check_complete → PaperCheckerLab._on_check_complete()
    ↓
ResultsTab.load_result()
    ↓
Tab switch to Results
```

## Threading Model

All long-running operations use QThread:

1. **PaperCheckWorker**: Main check processing (2-10 minutes)
2. **PDFAnalysisWorker**: PDF text extraction and LLM analysis
3. **DocumentFetchWorker**: Database PMID lookup

Workers emit signals for thread-safe UI updates.

## Extension Points

### Adding New Workflow Steps

1. Add step name to `WORKFLOW_STEPS` in `constants.py`
2. Update `WORKFLOW_STEP_COUNT`
3. Map agent progress to step in `utils.py:map_agent_progress_to_step()`

### Adding New Result Sub-Tabs

1. Add tab index constant in `constants.py`
2. Create `_create_<name>_tab()` method in `results_tab.py`
3. Add to tab widget in `_setup_ui()`
4. Create `_populate_<name>()` method

### Adding New Export Formats

1. Add export method in `results_tab.py`
2. Create button in `_create_export_tab()`
3. Use `ExportPreviewDialog` for preview/save

## Testing

### Unit Tests

```python
# Test pure utilities (no Qt needed)
from bmlibrarian.lab.paper_checker_lab.utils import validate_abstract

def test_validate_abstract():
    is_valid, error = validate_abstract("")
    assert not is_valid
    assert "required" in error.lower()
```

### Integration Tests

```python
# Test with Qt (requires display or QApplication)
from PySide6.QtWidgets import QApplication
from bmlibrarian.lab.paper_checker_lab import PaperCheckerLab

def test_main_window():
    app = QApplication([])
    window = PaperCheckerLab()
    assert window.windowTitle() == "PaperChecker Laboratory"
```

## Migration from Flet

The old Flet-based implementation is preserved at:
`src/bmlibrarian/lab/paper_checker_lab_flet.py`

Key differences:
- PySide6 uses signals/slots instead of callbacks
- QThread instead of ThreadPoolExecutor
- DPI-aware styling instead of fixed pixel values
- Modular package structure instead of single file

## See Also

- [Paper Weight Lab Architecture](paper_weight_lab_system.md) - Similar Qt pattern
- [PaperChecker Architecture](paper_checker_architecture.md) - Agent system
- [Qt Styling Guide](qt_styling_guide.md) - DPI scaling and stylesheets
