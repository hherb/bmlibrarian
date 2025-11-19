# BMLibrarian Qt Plugin Development Guide

**Complete guide to creating plugins for the BMLibrarian Qt GUI**

## Table of Contents

1. [Introduction](#introduction)
2. [Plugin Architecture](#plugin-architecture)
3. [Quick Start - Your First Plugin](#quick-start---your-first-plugin)
4. [Core Concepts](#core-concepts)
5. [BaseTabPlugin API Reference](#basetabplugin-api-reference)
6. [Database Access](#database-access)
7. [AI/LLM Integration](#aillm-integration)
8. [Qt GUI Styling System](#qt-gui-styling-system)
9. [Inter-Plugin Communication](#inter-plugin-communication)
10. [Advanced Topics](#advanced-topics)
11. [Best Practices](#best-practices)
12. [Testing Plugins](#testing-plugins)
13. [Complete Examples](#complete-examples)

## Introduction

The BMLibrarian Qt GUI uses a **plugin-based architecture** where each major feature (research workflow, configuration, fact-checking, etc.) is implemented as an independent plugin. This provides:

- **Modularity**: Features developed and maintained independently
- **Extensibility**: Add new functionality without modifying core code
- **Configurability**: Users can enable/disable tabs based on needs
- **Maintainability**: Clear separation of concerns
- **Isolation**: Plugin crashes don't bring down the entire application

### What is a Plugin?

A plugin in BMLibrarian is a self-contained Qt widget that appears as a tab in the main application. Examples include:

- **Research Tab** - Multi-agent research workflow
- **Configuration Tab** - System settings and agent configuration
- **Fact Checker Tab** - Statement verification interface
- **Query Lab Tab** - Interactive query development
- **PICO Lab Tab** - PICO component extraction for systematic reviews
- **Document Interrogation Tab** - AI-powered document Q&A

## Plugin Architecture

### Directory Structure

All plugins live under `src/bmlibrarian/gui/qt/plugins/`:

```
src/bmlibrarian/gui/qt/plugins/
├── base_tab.py              # Abstract base class for all plugins
├── research/                # Research workflow plugin
│   ├── __init__.py
│   └── plugin.py           # Plugin entry point
├── configuration/           # Settings plugin
│   ├── __init__.py
│   └── plugin.py
├── your_plugin/            # Your new plugin!
│   ├── __init__.py
│   ├── plugin.py           # Plugin entry point (required)
│   ├── your_plugin_tab.py  # Main tab widget (recommended)
│   └── widgets/            # Custom widgets (optional)
│       └── ...
```

### Plugin Lifecycle

```
Discovery → Loading → Registration → Activation → Deactivation → Cleanup
```

1. **Discovery**: PluginManager scans `plugins/` directory for subdirectories
2. **Loading**: Checks each subdirectory for `plugin.py` and calls `create_plugin()`
3. **Registration**: Plugin registered in TabRegistry with metadata
4. **Widget Creation**: Calls `create_widget()` to get tab widget
5. **Activation**: User navigates to tab, `on_tab_activated()` called
6. **Deactivation**: User leaves tab, `on_tab_deactivated()` called
7. **Cleanup**: Application closes, `cleanup()` called

### Plugin Discovery

Plugins are discovered automatically by scanning the directory structure. Enabled plugins are configured in `~/.bmlibrarian/gui_config.json`:

```json
{
  "gui": {
    "tabs": {
      "enabled_plugins": [
        "research",
        "configuration",
        "your_plugin"
      ]
    }
  }
}
```

## Quick Start - Your First Plugin

### Step 1: Create Plugin Directory

```bash
cd src/bmlibrarian/gui/qt/plugins
mkdir -p my_plugin
touch my_plugin/__init__.py
```

### Step 2: Create Plugin Entry Point

Create `src/bmlibrarian/gui/qt/plugins/my_plugin/plugin.py`:

```python
"""My Plugin - A simple example plugin."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from ..base_tab import BaseTabPlugin, TabPluginMetadata


class MyPlugin(BaseTabPlugin):
    """My plugin implementation."""

    def get_metadata(self) -> TabPluginMetadata:
        """Return plugin metadata."""
        return TabPluginMetadata(
            plugin_id="my_plugin",           # Unique identifier (snake_case)
            display_name="My Plugin",        # Tab title
            description="A simple example plugin",
            version="1.0.0",
            icon=None,                       # Optional icon path
            requires=[]                      # Optional plugin dependencies
        )

    def create_widget(self, parent=None) -> QWidget:
        """Create and return the main widget for this tab."""
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)

        label = QLabel("Hello from My Plugin!")
        layout.addWidget(label)

        button = QPushButton("Click Me")
        button.clicked.connect(self._on_button_clicked)
        layout.addWidget(button)

        return widget

    def _on_button_clicked(self):
        """Handle button click."""
        self.status_changed.emit("Button was clicked!")

    def on_tab_activated(self):
        """Called when this tab becomes active."""
        self.status_changed.emit("My Plugin activated")

    def on_tab_deactivated(self):
        """Called when this tab is deactivated."""
        pass

    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        pass


def create_plugin() -> BaseTabPlugin:
    """Plugin entry point - called by plugin manager."""
    return MyPlugin()
```

### Step 3: Enable Your Plugin

Edit `~/.bmlibrarian/gui_config.json`:

```json
{
  "gui": {
    "tabs": {
      "enabled_plugins": [
        "research",
        "configuration",
        "my_plugin"
      ]
    }
  }
}
```

### Step 4: Launch and Test

```bash
uv run python bmlibrarian_qt.py
```

Your plugin should appear as a new tab! 🎉

## Core Concepts

### BaseTabPlugin Abstract Class

All plugins must inherit from `BaseTabPlugin`, which provides:

- Standardized interface for plugin manager
- Qt Signal support for communication
- Lifecycle management hooks
- Configuration management utilities

### TabPluginMetadata

Metadata describes your plugin:

```python
TabPluginMetadata(
    plugin_id="my_plugin",           # Unique identifier (required)
    display_name="My Plugin",        # Human-readable name (required)
    description="Brief description", # Plugin description (required)
    version="1.0.0",                # Semantic version (required)
    icon="path/to/icon.png",        # Optional icon
    requires=["other_plugin"]       # Optional dependencies
)
```

### Signals

Plugins can emit signals to communicate with the main window:

```python
# Update status bar
self.status_changed.emit("Processing complete")

# Navigate to another tab
self.request_navigation.emit("configuration")

# Share data with other plugins
self.data_updated.emit({
    "source": "my_plugin",
    "data": my_data
})
```

## BaseTabPlugin API Reference

### Required Methods

#### `get_metadata() -> TabPluginMetadata`

Returns plugin metadata. Called during plugin discovery.

```python
def get_metadata(self) -> TabPluginMetadata:
    return TabPluginMetadata(
        plugin_id="my_plugin",
        display_name="My Plugin",
        description="Plugin description",
        version="1.0.0"
    )
```

#### `create_widget(parent=None) -> QWidget`

Creates and returns the main widget for the plugin tab. Called once during plugin loading.

```python
def create_widget(self, parent=None) -> QWidget:
    widget = QWidget(parent)
    layout = QVBoxLayout(widget)
    # ... build your UI ...
    return widget
```

**Important**: Create all UI components here, connect signals/slots, and return a fully configured QWidget.

#### `on_tab_activated()`

Called when the tab becomes visible/active. Use this to:
- Refresh data
- Resume background tasks
- Emit status messages

```python
def on_tab_activated(self):
    self.status_changed.emit("Plugin activated")
    self.refresh_data()
```

#### `on_tab_deactivated()`

Called when the tab is hidden or another tab is activated. Use this to:
- Pause background tasks
- Save temporary state
- Free temporary resources

```python
def on_tab_deactivated(self):
    if self.worker and self.worker.isRunning():
        self.worker.pause()
```

### Optional Methods

#### `cleanup()`

Called when the plugin is being unloaded (application closing). Use this to:
- Close database connections
- Stop worker threads
- Save persistent state
- Release resources

```python
def cleanup(self):
    # Stop workers
    if self.worker and self.worker.isRunning():
        self.worker.quit()
        self.worker.wait()

    # Close connections
    if self.db_connection:
        self.db_connection.close()

    # Save state
    self.save_config()
```

#### `get_config() -> Dict[str, Any]`

Returns plugin-specific configuration.

```python
def get_config(self) -> Dict[str, Any]:
    from ..core.config_manager import GUIConfigManager
    config_manager = GUIConfigManager()
    return config_manager.get_plugin_config(self.get_metadata().plugin_id)
```

#### `set_config(config: Dict[str, Any])`

Updates plugin configuration.

```python
def set_config(self, config: Dict[str, Any]):
    from ..core.config_manager import GUIConfigManager
    config_manager = GUIConfigManager()
    config_manager.set_plugin_config(
        self.get_metadata().plugin_id,
        config
    )
```

### Signals

Plugins inherit these Qt signals from `BaseTabPlugin`:

#### `status_changed = Signal(str)`

Emit to update the main window status bar:

```python
self.status_changed.emit("Processing completed successfully")
```

#### `request_navigation = Signal(str)`

Emit to navigate to another tab:

```python
self.request_navigation.emit("configuration")  # Navigate to config tab
```

#### `data_updated = Signal(dict)`

Emit to share data with other plugins:

```python
self.data_updated.emit({
    "source": "my_plugin",
    "event": "search_completed",
    "documents": document_list
})
```

## Database Access

### CRITICAL RULE: Always Use DatabaseManager

**NEVER** create direct PostgreSQL connections in your plugin code. **ALWAYS** use the centralized `DatabaseManager` singleton.

### Why Use DatabaseManager?

- **Connection pooling**: Reuses connections efficiently (min 2, max 10)
- **Transaction safety**: Automatic commit/rollback with context managers
- **Source ID caching**: Fast filtering by data source (PubMed, medRxiv)
- **Lazy singleton**: Global access without re-initialization

### Getting Database Access

```python
from bmlibrarian.database import get_db_manager

# Get the singleton instance
db_manager = get_db_manager()

# Use context manager for automatic transaction management
with db_manager.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM document WHERE id = %s", (doc_id,))
        result = cur.fetchone()
        # Connection automatically commits on success
        # or rolls back on exception
```

### Key Database Functions

```python
from bmlibrarian.database import (
    find_abstracts,           # Full-text search with metadata
    find_abstract_ids,        # Fast ID-only search
    fetch_documents_by_ids,   # Bulk fetch by IDs
    search_by_embedding,      # Vector similarity search
    search_hybrid,            # Multi-strategy hybrid search
    get_db_manager            # Get DatabaseManager singleton
)

# Example: Search for documents
for doc in find_abstracts(
    ts_query_str="covid & vaccine",
    max_rows=100,
    use_pubmed=True,
    use_medrxiv=True,
    plain=False  # Use advanced tsquery syntax
):
    print(f"{doc['title']} - {doc['authors']}")
```

### Database Best Practices

1. **Always use context managers** for connections
2. **Use parameterized queries** to prevent SQL injection
3. **Batch operations** when processing many documents
4. **Let exceptions propagate** - rollback is automatic
5. **Don't hold connections** across UI interactions

### Example: Safe Database Query

```python
from bmlibrarian.database import get_db_manager
from psycopg.rows import dict_row
from typing import List, Dict, Any

def get_recent_documents(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch recent documents from the database.

    Args:
        limit: Maximum number of documents to retrieve

    Returns:
        List of document dictionaries
    """
    db_manager = get_db_manager()
    documents = []

    with db_manager.get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Use parameterized query for safety
            cur.execute("""
                SELECT id, title, abstract, publication_date
                FROM document
                ORDER BY publication_date DESC
                LIMIT %s
            """, (limit,))

            documents = cur.fetchall()

    return documents
```

## AI/LLM Integration

### CRITICAL RULE: Always Inherit from BaseAgent

**NEVER** create direct Ollama client instances. **ALWAYS** inherit from `BaseAgent` or use existing agent classes.

### Why Use BaseAgent?

- **Ollama client management**: Single client instance with host configuration
- **Retry logic**: Exponential backoff for transient failures (1s, 2s, 4s...)
- **Error classification**: Distinguishes retryable vs. non-retryable errors
- **JSON parsing**: Robust parsing with markdown code block removal
- **Callback system**: Progress tracking for long-running operations
- **Queue integration**: Task submission for batch processing
- **Structured logging**: Detailed request/response tracking

### Creating a Custom Agent

```python
"""Custom agent for specialized biomedical literature analysis."""

import logging
from typing import Dict, Optional, Callable
from bmlibrarian.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class CustomAnalysisAgent(BaseAgent):
    """Agent for custom biomedical document analysis."""

    def __init__(
        self,
        model: str = "gpt-oss:20b",
        host: str = "http://localhost:11434",
        temperature: float = 0.1,
        top_p: float = 0.9,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional["AgentOrchestrator"] = None,
        show_model_info: bool = True
    ):
        """Initialize the CustomAnalysisAgent."""
        super().__init__(
            model, host, temperature, top_p,
            callback, orchestrator, show_model_info
        )

        self.system_prompt = """You are an expert biomedical analyst..."""

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "custom_analysis_agent"

    def analyze_document(
        self,
        document: Dict,
        analysis_type: str = "comprehensive"
    ) -> Dict:
        """
        Analyze a document using the LLM.

        Args:
            document: Document dictionary with title, abstract, etc.
            analysis_type: Type of analysis to perform

        Returns:
            Analysis results as dictionary

        Raises:
            ConnectionError: If unable to connect to Ollama
            ValueError: If inputs are invalid
        """
        # Validate inputs
        if not document.get('title') or not document.get('abstract'):
            raise ValueError("Document must have title and abstract")

        # Build prompt
        prompt = f"""Analyze this biomedical document:

Title: {document['title']}
Abstract: {document['abstract']}

Analysis type: {analysis_type}

Provide your analysis in JSON format:
{{
    "key_findings": ["finding1", "finding2", ...],
    "methodology": "description",
    "significance": "assessment"
}}"""

        # Use BaseAgent method with automatic retry and JSON parsing
        response = self._generate_and_parse_json(
            prompt=prompt,
            max_retries=3,
            retry_context="document analysis"
        )

        return response
```

### Using Configuration for Models

**NEVER hardcode model names.** Always use the configuration system:

```python
from bmlibrarian.config import get_config, get_model, get_agent_config

# Get model for specific agent type
model = get_model('custom_agent', default='gpt-oss:20b')

# Get full agent configuration
agent_config = get_agent_config('custom')
temperature = agent_config.get('temperature', 0.1)
top_p = agent_config.get('top_p', 0.9)

# Create agent with config
agent = CustomAnalysisAgent(
    model=model,
    temperature=temperature,
    top_p=top_p
)
```

### Best Practices for AI Integration

1. **Always inherit from BaseAgent** - don't create raw Ollama clients
2. **Use retry methods** - `_generate_and_parse_json()`, `_make_ollama_request()`
3. **Validate inputs** before making LLM requests
4. **Use configuration** for all models and parameters
5. **Provide context in errors** - use `retry_context` parameter
6. **Handle empty responses** - BaseAgent does this automatically
7. **Log agent operations** - BaseAgent provides structured logging

## Qt GUI Styling System

### DPI-Aware Font Scaling

BMLibrarian uses a **font-relative scaling system** that ensures UI elements scale properly across all DPI settings (96 DPI, 144 DPI, 4K displays, etc.).

#### The FontScale Singleton

**NEVER use hardcoded pixel values.** Always use the `FontScale` singleton:

```python
from bmlibrarian.gui.qt.resources.styles.dpi_scale import FontScale, get_font_scale

# Get the singleton instance
scale = FontScale()

# Access scale values
font_size = scale['font_medium']      # 12pt (scaled from system font)
padding = scale['padding_large']      # 8px (scaled to DPI)
spacing = scale['spacing_medium']     # 6px (scaled to DPI)
icon_size = scale['icon_medium']      # 24px (scaled to DPI)
control_height = scale['control_height_medium']  # 30px (scaled to DPI)
```

#### Available Scale Keys

**Font Sizes** (in points, DPI-independent):
- `font_tiny`: 8-9pt
- `font_small`: 10pt
- `font_normal`: 11pt (system default)
- `font_medium`: 12pt
- `font_large`: 13pt
- `font_xlarge`: 15pt
- `font_icon`: 18pt

**Spacing/Padding** (in pixels, relative to line height):
- `spacing_tiny`: 2-3px
- `spacing_small`: 4-6px
- `spacing_medium`: 6-10px
- `spacing_large`: 8-12px
- `spacing_xlarge`: 12-18px

**Control Heights** (in pixels):
- `control_height_small`: 24px
- `control_height_medium`: 30px
- `control_height_large`: 40px

**Icon Sizes** (in pixels):
- `icon_tiny`: 12px
- `icon_small`: 16px
- `icon_medium`: 24px
- `icon_large`: 32px

### StylesheetGenerator for Consistent Theming

Use `StylesheetGenerator` for creating DPI-aware stylesheets:

```python
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import StylesheetGenerator

# Create generator
generator = StylesheetGenerator()

# Generate button stylesheet
button_style = generator.button_stylesheet(
    bg_color="#2196F3",
    text_color="white",
    hover_color="#1976D2",
    font_size_key='font_medium',
    padding_key='padding_small',
    radius_key='radius_small'
)
self.my_button.setStyleSheet(button_style)
```

### Example: Creating a Scaled Widget

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from bmlibrarian.gui.qt.resources.styles.dpi_scale import FontScale
from bmlibrarian.gui.qt.resources.styles.stylesheet_generator import StylesheetGenerator


class CustomPluginWidget(QWidget):
    """Custom plugin widget with proper DPI scaling."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Get scale values
        self.scale = FontScale()
        self.stylesheet_gen = StylesheetGenerator()

        self._setup_ui()

    def _setup_ui(self):
        """Initialize UI with scaled dimensions."""
        layout = QVBoxLayout(self)

        # Use scaled spacing
        layout.setSpacing(self.scale['spacing_medium'])
        layout.setContentsMargins(
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large'],
            self.scale['padding_large']
        )

        # Create header label with scaled font
        header = QLabel("Custom Plugin")
        header.setStyleSheet(self.stylesheet_gen.label_stylesheet(
            font_size_key='font_xlarge',
            color="#2C3E50",
            bold=True
        ))
        layout.addWidget(header)

        # Create button with scaled dimensions
        action_button = QPushButton("Analyze Documents")
        action_button.setFixedHeight(self.scale['control_height_medium'])
        action_button.setStyleSheet(self.stylesheet_gen.button_stylesheet(
            bg_color="#27AE60",
            text_color="white",
            hover_color="#229954"
        ))
        layout.addWidget(action_button)
```

## Inter-Plugin Communication

### Using the Event Bus

Plugins can communicate through the centralized EventBus:

```python
from bmlibrarian.gui.qt.core.event_bus import EventBus

class MyPlugin(BaseTabPlugin):
    def __init__(self):
        super().__init__()
        self.event_bus = EventBus()

        # Subscribe to events from other plugins
        self.event_bus.data_shared.connect(self._on_data_received)

    def _on_search_completed(self, documents):
        """Share results with other plugins."""
        self.event_bus.publish_data("my_plugin", {
            "event": "search_completed",
            "document_count": len(documents),
            "documents": documents
        })

    def _on_data_received(self, source_plugin_id: str, data: dict):
        """Handle data from other plugins."""
        if source_plugin_id == "search":
            if data.get("event") == "filter_applied":
                self._update_document_list(data["filtered_docs"])
```

## Advanced Topics

### Background Thread Execution

All long-running operations (agent calls, database queries) must run in background threads:

```python
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

class WorkerSignals(QObject):
    """Signals for worker threads."""
    finished = Signal()
    error = Signal(tuple)  # (exception_type, exception_value, traceback)
    result = Signal(object)
    progress = Signal(int)

class WorkflowWorker(QRunnable):
    """Worker for running workflow steps in background."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        """Execute the workflow step."""
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            import traceback
            self.signals.error.emit((type(e), e, traceback.format_exc()))
        finally:
            self.signals.finished.emit()
```

### Plugin Dependencies

Declare dependencies in metadata:

```python
def get_metadata(self) -> TabPluginMetadata:
    return TabPluginMetadata(
        plugin_id="advanced_search",
        display_name="Advanced Search",
        description="Enhanced search with filters",
        version="1.0.0",
        requires=["search"]  # Requires basic search plugin
    )
```

## Best Practices

### 1. Type Hints (MANDATORY)

Always use type hints for function signatures:

```python
from typing import Dict, List, Optional

def analyze_documents(
    documents: List[Dict[str, Any]],
    min_score: float = 0.7
) -> Tuple[List[Dict], Dict[str, float]]:
    """Analyze documents and return scored results."""
    # Implementation...
```

### 2. Docstrings (MANDATORY)

Use Google-style docstrings:

```python
def search_literature(
    query: str,
    max_results: int = 100
) -> List[Dict[str, Any]]:
    """
    Search biomedical literature databases.

    Args:
        query: Natural language search query
        max_results: Maximum number of results to return

    Returns:
        List of document dictionaries

    Raises:
        ValueError: If query is empty
        ConnectionError: If database is unavailable
    """
```

### 3. No Magic Numbers

Never use hardcoded numbers - use constants or configuration:

```python
# BAD
if score > 0.7:
    documents = documents[:50]

# GOOD
MIN_RELEVANCE_THRESHOLD = 0.7
DEFAULT_MAX_DOCUMENTS = 50

if score > MIN_RELEVANCE_THRESHOLD:
    documents = documents[:DEFAULT_MAX_DOCUMENTS]
```

### 4. Logging (MANDATORY)

Use Python's logging module, never `print()`:

```python
import logging

logger = logging.getLogger(__name__)

def process_documents(documents: List[Dict]) -> List[Dict]:
    """Process documents with comprehensive logging."""
    logger.info(f"Starting document processing: {len(documents)} documents")
    # ... processing ...
    logger.info(f"Processing complete: {len(processed)}/{len(documents)} successful")
```

## Testing Plugins

### Manual Testing Checklist

- [ ] Plugin loads without errors
- [ ] Tab appears in correct position
- [ ] Tab title and icon are correct
- [ ] Tab activates/deactivates correctly
- [ ] All controls are functional
- [ ] Long operations don't freeze UI
- [ ] Error messages are clear and helpful
- [ ] Configuration is saved/loaded correctly
- [ ] Plugin cleans up on close

### Automated Testing with pytest-qt

Create `tests/gui/qt/plugins/test_my_plugin.py`:

```python
import pytest
from pytestqt.qtbot import QtBot
from bmlibrarian.gui.qt.plugins.my_plugin.plugin import MyPlugin, create_plugin

def test_plugin_creation():
    """Test plugin can be created."""
    plugin = create_plugin()
    assert plugin is not None
    assert isinstance(plugin, MyPlugin)

def test_plugin_metadata():
    """Test plugin metadata."""
    plugin = create_plugin()
    metadata = plugin.get_metadata()

    assert metadata.plugin_id == "my_plugin"
    assert metadata.display_name == "My Plugin"
    assert metadata.version == "1.0.0"

def test_widget_creation(qtbot: QtBot):
    """Test widget can be created."""
    plugin = create_plugin()
    widget = plugin.create_widget()

    assert widget is not None
    qtbot.addWidget(widget)

    # Test widget is visible
    widget.show()
    assert widget.isVisible()
```

## Complete Examples

### Full-Featured Plugin with Database and AI

See the full examples in:
- `src/bmlibrarian/gui/qt/plugins/research/` - Research workflow plugin
- `src/bmlibrarian/gui/qt/plugins/query_lab/` - Query development plugin
- `src/bmlibrarian/gui/qt/plugins/pico_lab/` - PICO extraction plugin

## Troubleshooting

### Plugin Not Loading

1. Check `~/.bmlibrarian/gui_config.json` - is your plugin in `enabled_plugins`?
2. Check `plugin.py` exists with `create_plugin()` function
3. Check for syntax errors
4. Review logs at `~/.bmlibrarian/gui_qt.log`

### UI Freezing

1. Move long operations to worker threads
2. Use signals to update UI from worker threads
3. Don't block the main thread

## Next Steps

After reading this guide:

1. Review existing plugins in `src/bmlibrarian/gui/qt/plugins/`
2. Study `BaseAgent` implementation
3. Examine `DatabaseManager`
4. Create a simple plugin using the template
5. Test on multiple DPI displays
6. Add comprehensive unit tests

## Additional Resources

- [Architecture Overview](Architecture-Overview)
- [Qt Documentation](https://doc.qt.io/qtforpython/)
- [BaseAgent API](API-Reference#baseagent)
- [Database Schema](Database-Schema)
- [Contributing Guidelines](Contributing)

---

**Happy Plugin Development!** 🚀

Need help? Check the [GitHub Issues](https://github.com/hherb/bmlibrarian/issues) or ask in Discussions.
