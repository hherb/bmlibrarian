# PaperChecker Laboratory - Developer Documentation

This document provides technical details for developers working with or extending the PaperChecker Laboratory interface.

## Architecture Overview

The PaperChecker Laboratory is a Flet-based GUI application that provides interactive testing and exploration of the PaperChecker fact-checking system.

### Component Structure

```
paper_checker_lab.py (root)          # Entry point script
├── argparse configuration           # CLI argument handling
├── logging setup                    # Debug mode configuration
└── Flet app launcher               # Desktop/web mode selection

src/bmlibrarian/lab/paper_checker_lab.py  # Main implementation
├── PaperCheckerLab class            # Main application class
│   ├── UI Building                  # Layout construction methods
│   ├── Event Handlers               # User interaction handling
│   ├── Processing Logic             # Background task management
│   ├── Results Display              # Tab content generation
│   └── Export Methods               # JSON/Markdown export
└── Constants                        # All configuration values
```

### Key Design Patterns

1. **No Magic Numbers**: All dimensions, colors, and configuration values are defined as named constants
2. **Non-Blocking UI**: Background thread processing with progress callbacks
3. **Type Hints**: All parameters and return values are typed
4. **Docstrings**: All classes, methods, and functions are documented
5. **Error Handling**: Comprehensive try-catch with user-friendly messages

## Class Reference

### PaperCheckerLab

Main application class managing state, UI, and processing.

```python
class PaperCheckerLab:
    """Interactive laboratory for testing PaperChecker functionality."""

    def __init__(self) -> None:
        """Initialize with default state."""

    def main(self, page: ft.Page) -> None:
        """Entry point for Flet application."""
```

#### Key Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `page` | `Optional[ft.Page]` | Flet page instance |
| `config` | `Config` | BMLibrarian configuration |
| `agent` | `Optional[PaperCheckerAgent]` | PaperChecker agent instance |
| `current_result` | `Optional[PaperCheckResult]` | Most recent result |
| `controls` | `Dict[str, Any]` | UI control references |
| `workflow_steps` | `List[ft.Card]` | Workflow step cards |
| `executor` | `ThreadPoolExecutor` | Background task executor |
| `processing` | `bool` | Processing state flag |
| `_check_lock` | `threading.Lock` | Concurrency control |

#### UI Building Methods

| Method | Description |
|--------|-------------|
| `_build_ui()` | Construct main layout |
| `_build_header()` | Title and subtitle section |
| `_build_input_section()` | Input fields and buttons |
| `_build_progress_section()` | Progress bar and status |
| `_build_workflow_panel()` | Left panel with step cards |
| `_build_results_panel()` | Right panel with tabs |
| `_build_*_tab()` | Individual tab content builders |

#### Event Handlers

| Method | Event |
|--------|-------|
| `_on_check_clicked()` | Check button click |
| `_on_clear_clicked()` | Clear button click |
| `_on_model_change()` | Model selector change |
| `_refresh_models()` | Refresh button click |

#### Processing Methods

| Method | Description |
|--------|-------------|
| `_run_check()` | Start background check |
| `_on_progress_update()` | Handle progress callbacks |
| `_on_check_complete()` | Handle successful completion |
| `_on_check_error()` | Handle processing errors |

## Constants Reference

### Window Dimensions

```python
WINDOW_WIDTH_DEFAULT = 1400
WINDOW_HEIGHT_DEFAULT = 950
WINDOW_WIDTH_MIN = 1200
WINDOW_HEIGHT_MIN = 750
```

### Font Sizes

```python
FONT_SIZE_TINY = 11
FONT_SIZE_SMALL = 12
FONT_SIZE_NORMAL = 13
FONT_SIZE_MEDIUM = 14
FONT_SIZE_LARGE = 16
FONT_SIZE_XLARGE = 18
FONT_SIZE_TITLE = 24
FONT_SIZE_HEADER = 28
```

### Spacing

```python
SPACING_TINY = 3
SPACING_SMALL = 5
SPACING_MEDIUM = 10
SPACING_LARGE = 15
SPACING_XLARGE = 20
```

### Colors

```python
COLOR_PRIMARY = ft.Colors.BLUE_700
COLOR_SUCCESS = ft.Colors.GREEN_600
COLOR_WARNING = ft.Colors.ORANGE_600
COLOR_ERROR = ft.Colors.RED_600

VERDICT_COLORS = {
    "supports": ft.Colors.GREEN_600,
    "contradicts": ft.Colors.RED_600,
    "undecided": ft.Colors.ORANGE_600
}

CONFIDENCE_COLORS = {
    "high": ft.Colors.GREEN_600,
    "medium": ft.Colors.ORANGE_600,
    "low": ft.Colors.RED_600
}
```

## Threading Model

### Background Processing

The laboratory uses a `ThreadPoolExecutor` with a single worker for background processing:

```python
self.executor = ThreadPoolExecutor(max_workers=1)

def _run_check(self, abstract: str, metadata: Dict[str, Any]) -> None:
    def run_check_thread() -> None:
        result = self.agent.check_abstract(
            abstract=abstract,
            source_metadata=metadata,
            progress_callback=self._on_progress_update
        )
        # Schedule UI update on main thread
        self.page.run_task(lambda: self._on_check_complete(result))

    self.executor.submit(run_check_thread)
```

### Concurrency Control

A lock prevents concurrent processing:

```python
self._check_lock = threading.Lock()

def _run_check(self, abstract: str, metadata: Dict[str, Any]) -> None:
    with self._check_lock:
        if self.processing:
            return
        self.processing = True
    # ... processing logic ...
    finally:
        with self._check_lock:
            self.processing = False
```

### UI Updates from Background Thread

Use `page.run_task()` for UI updates from background threads:

```python
def _on_progress_update(self, step_name: str, progress: float) -> None:
    def update_ui() -> None:
        self.controls['progress_bar'].value = progress
        self.page.update()

    self.page.run_task(update_ui)
```

## Extension Points

### Adding New Tabs

1. Add tab index constant:
```python
TAB_INDEX_NEW_TAB = 5
```

2. Create placeholder builder:
```python
def _build_new_tab_placeholder(self) -> ft.Container:
    return ft.Container(
        content=ft.Text("Content placeholder"),
        padding=PADDING_MEDIUM
    )
```

3. Create content builder:
```python
def _build_new_tab(self, result: PaperCheckResult) -> ft.Container:
    # Build tab content from result
    pass
```

4. Add tab to `_build_results_panel()`:
```python
ft.Tab(text="New Tab", content=self._build_new_tab_placeholder())
```

5. Update `_display_results()`:
```python
self.controls['result_tabs'].tabs[TAB_INDEX_NEW_TAB].content = (
    self._build_new_tab(result)
)
```

### Adding New Export Formats

1. Add export method:
```python
def _export_csv(self, result: PaperCheckResult) -> None:
    try:
        output = self._generate_csv(result)
        # Display or save output
        self._show_success("CSV exported")
    except Exception as e:
        self._show_error(f"Export failed: {e}")
```

2. Add button to export tab in `_build_export_tab()`:
```python
ft.ElevatedButton(
    "Export as CSV",
    icon=ft.Icons.TABLE_CHART,
    on_click=lambda _: self._export_csv(result)
)
```

### Customizing Workflow Steps

Modify `WORKFLOW_STEPS` to add or rename steps:

```python
WORKFLOW_STEPS = [
    "Initializing",
    "Extracting statements",
    # ... add custom steps
    "Complete"
]
```

Note: Step names must match those used in `PaperCheckerAgent.check_abstract()` progress callbacks.

## Testing

### Manual Testing

1. Launch in debug mode:
```bash
uv run python paper_checker_lab.py --debug
```

2. Test each workflow:
   - Abstract text input
   - PMID fetching
   - Progress visualization
   - Results display
   - Export functions
   - Error handling

3. Verify UI responsiveness during processing

### Integration Testing

```python
# tests/test_paper_checker_lab.py
import pytest
from bmlibrarian.lab.paper_checker_lab import PaperCheckerLab

def test_lab_initialization():
    """Test laboratory initializes without errors."""
    lab = PaperCheckerLab()
    assert lab.agent is None  # Not initialized until main() is called
    assert lab.current_result is None
    assert lab.processing is False

def test_fetch_by_pmid_invalid():
    """Test PMID validation."""
    lab = PaperCheckerLab()
    result = lab._fetch_by_pmid("invalid")
    assert result is None

def test_available_models_fallback():
    """Test model list fallback."""
    lab = PaperCheckerLab()
    models = lab._get_available_models()
    assert len(models) > 0
    assert "gpt-oss:20b" in models
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `flet` | GUI framework |
| `asyncio` | Async operations |
| `threading` | Concurrency control |
| `json` | Export functionality |
| `concurrent.futures` | Background processing |

## Related Files

| File | Description |
|------|-------------|
| `src/bmlibrarian/paperchecker/agent.py` | PaperCheckerAgent implementation |
| `src/bmlibrarian/paperchecker/data_models.py` | Data model definitions |
| `src/bmlibrarian/paperchecker/database.py` | Database operations |
| `src/bmlibrarian/config.py` | Configuration management |
| `src/bmlibrarian/database.py` | Main database module |

## Golden Rules Compliance

This implementation follows all BMLibrarian golden rules:

1. **Input validation**: All user inputs are validated before processing
2. **No magic numbers**: All values defined as named constants
3. **No hardcoded paths**: Uses configuration system
4. **Ollama library**: Uses bmlibrarian agents (which use ollama library)
5. **Database manager**: Uses fetch_documents_by_ids and get_db_manager
6. **Type hints**: All parameters and returns are typed
7. **Docstrings**: All classes and methods documented
8. **Error handling**: Comprehensive error handling with user feedback
9. **No inline styles**: Uses Flet color constants (no stylesheet system in Flet)
10. **No hardcoded pixels**: Uses relative spacing constants
11. **User error reporting**: Snackbar messages for all errors
12. **Reusable functions**: Modular design with helper methods
13. **Documentation**: User and developer guides provided
