# BMLibrarian Qt Plugin Development Guide

## Table of Contents

1. [Introduction](#introduction)
2. [Plugin Architecture Overview](#plugin-architecture-overview)
3. [Creating Your First Plugin](#creating-your-first-plugin)
4. [BaseTabPlugin API Reference](#basetabplugin-api-reference)
5. [Advanced Topics](#advanced-topics)
6. [Best Practices](#best-practices)
7. [Testing Plugins](#testing-plugins)
8. [Example Plugins](#example-plugins)

## Introduction

The BMLibrarian Qt GUI uses a plugin-based architecture where each tab is implemented as a separate plugin. This design provides:

- **Modularity**: Each feature is self-contained
- **Extensibility**: Easy to add new functionality
- **Maintainability**: Changes to one plugin don't affect others
- **Configuration**: Plugins can be enabled/disabled dynamically
- **Isolation**: Plugin crashes don't bring down the entire application

This guide will teach you how to create your own plugins for the BMLibrarian Qt GUI.

## Plugin Architecture Overview

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
│   └── ...                 # Additional modules as needed
```

### Plugin Discovery

Plugins are discovered automatically by the `PluginManager`:

1. Scans `plugins/` directory for subdirectories
2. Checks each subdirectory for `plugin.py`
3. Loads plugins listed in `~/.bmlibrarian/gui_config.json`:

```json
{
  "gui": {
    "tabs": {
      "enabled_plugins": [
        "research",
        "search",
        "your_plugin"
      ]
    }
  }
}
```

### Plugin Lifecycle

1. **Discovery**: Plugin manager finds `plugin.py`
2. **Loading**: Calls `create_plugin()` function
3. **Registration**: Registers plugin with tab registry
4. **Widget Creation**: Calls `create_widget()` to get tab widget
5. **Activation**: Calls `on_tab_activated()` when tab is shown
6. **Deactivation**: Calls `on_tab_deactivated()` when tab is hidden
7. **Cleanup**: Calls `cleanup()` when application closes

## Creating Your First Plugin

### Step 1: Create Plugin Directory

```bash
mkdir -p src/bmlibrarian/gui/qt/plugins/my_plugin
touch src/bmlibrarian/gui/qt/plugins/my_plugin/__init__.py
```

### Step 2: Create Plugin Entry Point

Create `src/bmlibrarian/gui/qt/plugins/my_plugin/plugin.py`:

```python
"""My Plugin - A simple example plugin."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from ..base_tab import BaseTabPlugin, TabPluginMetadata


class MyPlugin(BaseTabPlugin):
    """My plugin implementation.

    This plugin demonstrates the basic structure required for
    all BMLibrarian Qt GUI plugins.
    """

    def get_metadata(self) -> TabPluginMetadata:
        """Return plugin metadata.

        Returns:
            TabPluginMetadata: Plugin information
        """
        return TabPluginMetadata(
            plugin_id="my_plugin",           # Unique identifier
            display_name="My Plugin",        # Tab title
            description="A simple example plugin",
            version="1.0.0",
            icon=None,                       # Optional icon path
            requires=[]                      # Optional plugin dependencies
        )

    def create_widget(self, parent=None) -> QWidget:
        """Create and return the main widget for this tab.

        Args:
            parent: Parent widget (typically the main window)

        Returns:
            QWidget: The plugin's main widget
        """
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)

        label = QLabel("Hello from My Plugin!")
        layout.addWidget(label)

        return widget

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
    """Plugin entry point.

    This function is called by the plugin manager to instantiate the plugin.

    Returns:
        BaseTabPlugin: Plugin instance
    """
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
        "search",
        "my_plugin"
      ]
    }
  }
}
```

### Step 4: Launch and Test

```bash
python bmlibrarian_qt.py
```

Your plugin should appear as a new tab!

## BaseTabPlugin API Reference

### Required Methods

#### `get_metadata() -> TabPluginMetadata`

Returns plugin metadata including:
- `plugin_id` (str): Unique identifier (use snake_case)
- `display_name` (str): Human-readable name for tab
- `description` (str): Brief description
- `version` (str): Plugin version (semantic versioning)
- `icon` (Optional[str]): Path to icon file
- `requires` (Optional[List[str]]): List of required plugin IDs

#### `create_widget(parent=None) -> QWidget`

Creates and returns the main widget for the plugin tab.

**Important**:
- Create all UI components here
- Connect signals/slots
- Return a fully configured QWidget
- This is called only once during plugin loading

#### `on_tab_activated()`

Called when the tab becomes visible/active.

**Use this to**:
- Refresh data
- Resume background tasks
- Emit status messages

#### `on_tab_deactivated()`

Called when the tab is hidden or another tab is activated.

**Use this to**:
- Pause background tasks
- Save temporary state
- Free temporary resources

### Optional Methods

#### `cleanup()`

Called when the plugin is being unloaded (application closing).

**Use this to**:
- Close database connections
- Stop worker threads
- Save persistent state
- Release resources

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

Emit this to update the main window status bar:

```python
self.status_changed.emit("Processing completed successfully")
```

#### `request_navigation = Signal(str)`

Emit this to navigate to another tab:

```python
self.request_navigation.emit("configuration")  # Navigate to config tab
```

#### `data_updated = Signal(dict)`

Emit this to share data with other plugins:

```python
self.data_updated.emit({
    "source": "my_plugin",
    "documents": document_list
})
```

## Advanced Topics

### Using Worker Threads

Long-running operations should run in background threads to keep the UI responsive.

```python
from PySide6.QtCore import QThread, Signal

class WorkerThread(QThread):
    """Worker thread for long-running operations."""

    result_ready = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, task_data):
        super().__init__()
        self.task_data = task_data

    def run(self):
        """Execute long-running operation."""
        try:
            # Perform time-consuming task
            result = self.process_data(self.task_data)
            self.result_ready.emit(result)
        except Exception as e:
            self.error_occurred.emit(str(e))

    def process_data(self, data):
        # Your processing logic here
        return {"status": "success"}


class MyPlugin(BaseTabPlugin):
    def __init__(self):
        super().__init__()
        self.worker = None

    def start_background_task(self, data):
        """Start a background task."""
        if self.worker and self.worker.isRunning():
            return  # Already running

        self.worker = WorkerThread(data)
        self.worker.result_ready.connect(self._on_result)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.start()

    def _on_result(self, result):
        """Handle worker thread result."""
        self.status_changed.emit(f"Task completed: {result}")

    def _on_error(self, error_msg):
        """Handle worker thread error."""
        self.status_changed.emit(f"Error: {error_msg}")

    def cleanup(self):
        """Stop worker thread on cleanup."""
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
```

### Accessing BMLibrarian Agents

Plugins can use BMLibrarian's multi-agent system:

```python
from bmlibrarian.agents import QueryAgent, DocumentScoringAgent

class MyPlugin(BaseTabPlugin):
    def __init__(self):
        super().__init__()
        self.query_agent = None

    def create_widget(self, parent=None):
        # Initialize agent
        try:
            self.query_agent = QueryAgent()
        except Exception as e:
            # Handle agent initialization error
            pass

        # Create widget...
        return widget

    def search_documents(self, question: str):
        """Use QueryAgent to search documents."""
        if not self.query_agent:
            return []

        try:
            documents = self.query_agent.search_documents(question)
            return documents
        except Exception as e:
            self.status_changed.emit(f"Search error: {e}")
            return []
```

### Using Reusable Widgets

BMLibrarian provides reusable widgets in `gui/qt/widgets/`:

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout
from ..widgets import (
    DocumentCard,
    MarkdownViewer,
    ProgressWidget,
    CollapsibleSection
)

class MyPluginWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        # Use progress widget
        self.progress = ProgressWidget()
        layout.addWidget(self.progress)

        # Use collapsible section
        section = CollapsibleSection("Documents")
        layout.addWidget(section)

        # Use markdown viewer
        self.viewer = MarkdownViewer()
        section.setContentLayout(QVBoxLayout())
        section.contentWidget().layout().addWidget(self.viewer)

    def show_document(self, doc):
        """Display a document using DocumentCard."""
        card = DocumentCard(doc)
        card.clicked.connect(self.on_document_clicked)
        # Add to layout...
```

### Database Access

Plugins can access the PostgreSQL database:

```python
import psycopg
from bmlibrarian.cli.config import get_config

class MyPlugin(BaseTabPlugin):
    def __init__(self):
        super().__init__()
        self.conn = None

    def create_widget(self, parent=None):
        # Connect to database
        try:
            config = get_config()
            db_config = config["database"]
            self.conn = psycopg.connect(
                dbname=db_config["name"],
                user=db_config["user"],
                password=db_config["password"],
                host=db_config["host"],
                port=db_config["port"]
            )
        except Exception as e:
            # Handle connection error
            pass

        # Create widget...
        return widget

    def query_database(self, sql: str, params=None):
        """Execute a database query."""
        if not self.conn:
            return []

        try:
            with self.conn.cursor() as cur:
                cur.execute(sql, params or ())
                return cur.fetchall()
        except Exception as e:
            self.status_changed.emit(f"Database error: {e}")
            return []

    def cleanup(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
```

### Plugin Configuration

Store plugin-specific settings in the configuration:

```python
class MyPlugin(BaseTabPlugin):
    def __init__(self):
        super().__init__()
        self.config = self.load_config()

    def load_config(self) -> dict:
        """Load plugin configuration."""
        from ..core.config_manager import GUIConfigManager
        config_manager = GUIConfigManager()

        # Get plugin-specific config with defaults
        config = config_manager.get_plugin_config("my_plugin")

        # Set defaults if not present
        if not config:
            config = {
                "max_results": 100,
                "auto_refresh": True,
                "theme_color": "#0078d4"
            }
            config_manager.set_plugin_config("my_plugin", config)

        return config

    def save_config(self):
        """Save plugin configuration."""
        from ..core.config_manager import GUIConfigManager
        config_manager = GUIConfigManager()
        config_manager.set_plugin_config("my_plugin", self.config)
```

### Inter-Plugin Communication

Plugins can communicate through signals:

```python
# Plugin A (sender)
class PluginA(BaseTabPlugin):
    def send_data_to_other_plugin(self, data):
        self.data_updated.emit({
            "source": "plugin_a",
            "type": "documents",
            "data": data
        })

# Plugin B (receiver)
class PluginB(BaseTabPlugin):
    def __init__(self):
        super().__init__()
        # Connect to event bus in main window
        # (This is typically done by the main window)

    def on_data_received(self, data_dict):
        """Handle data from other plugins."""
        if data_dict.get("source") == "plugin_a":
            documents = data_dict.get("data", [])
            # Process documents...
```

## Best Practices

### 1. Separation of Concerns

**DO**: Keep business logic separate from UI code

```python
# Good: Separate widget and logic
class MyPluginLogic:
    """Business logic for my plugin."""
    def process_data(self, data):
        # Logic here
        return result

class MyPluginWidget(QWidget):
    """UI for my plugin."""
    def __init__(self):
        super().__init__()
        self.logic = MyPluginLogic()
```

**DON'T**: Mix everything together

```python
# Bad: Logic mixed with UI
class MyPluginWidget(QWidget):
    def on_button_click(self):
        # Database query directly in UI code
        conn = psycopg.connect(...)
        # Complex business logic
        result = complicated_calculation()
        # More UI code
```

### 2. Thread Safety

**DO**: Use worker threads for long operations

```python
# Good: Background processing
def on_search_button_clicked(self):
    self.worker = SearchWorker(self.query)
    self.worker.result_ready.connect(self.display_results)
    self.worker.start()
```

**DON'T**: Block the UI thread

```python
# Bad: UI freezes during operation
def on_search_button_clicked(self):
    results = expensive_search_operation()  # UI frozen!
    self.display_results(results)
```

### 3. Resource Management

**DO**: Clean up resources properly

```python
def cleanup(self):
    # Stop workers
    if self.worker and self.worker.isRunning():
        self.worker.quit()
        self.worker.wait()

    # Close connections
    if self.conn:
        self.conn.close()

    # Save state
    self.save_config()
```

**DON'T**: Leave resources hanging

```python
def cleanup(self):
    pass  # Memory leaks, connection leaks, etc.
```

### 4. Error Handling

**DO**: Handle errors gracefully

```python
def load_data(self):
    try:
        data = self.fetch_from_database()
        return data
    except DatabaseError as e:
        self.status_changed.emit(f"Database error: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        QMessageBox.warning(
            self,
            "Error",
            "An unexpected error occurred. See logs for details."
        )
        return []
```

**DON'T**: Let exceptions crash the plugin

```python
def load_data(self):
    data = self.fetch_from_database()  # Uncaught exception!
    return data
```

### 5. User Feedback

**DO**: Provide clear feedback

```python
def start_processing(self):
    self.progress.set_progress(0, "Starting processing...")
    self.status_changed.emit("Processing started")
    # ... processing ...
    self.progress.set_progress(100, "Complete!")
    self.status_changed.emit("Processing completed successfully")
```

**DON'T**: Leave users wondering

```python
def start_processing(self):
    # ... long operation with no feedback ...
    # User doesn't know what's happening
```

### 6. Consistent UI

**DO**: Follow Qt design patterns

```python
# Use layouts, not fixed positioning
layout = QVBoxLayout()
layout.addWidget(self.title_label)
layout.addWidget(self.content)
self.setLayout(layout)
```

**DON'T**: Use fixed sizes and positions

```python
# Bad: Fixed positioning breaks on different screens
self.label.setGeometry(10, 10, 200, 30)
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

def test_tab_activation():
    """Test tab activation/deactivation."""
    plugin = create_plugin()

    # Should not raise exceptions
    plugin.on_tab_activated()
    plugin.on_tab_deactivated()

def test_cleanup():
    """Test plugin cleanup."""
    plugin = create_plugin()
    widget = plugin.create_widget()

    # Should not raise exceptions
    plugin.cleanup()
```

Run tests:

```bash
pytest tests/gui/qt/plugins/test_my_plugin.py -v
```

## Example Plugins

### Simple Display Plugin

A plugin that displays static content:

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from ..base_tab import BaseTabPlugin, TabPluginMetadata

class SimpleDisplayPlugin(BaseTabPlugin):
    def get_metadata(self) -> TabPluginMetadata:
        return TabPluginMetadata(
            plugin_id="simple_display",
            display_name="Simple Display",
            description="Displays simple content",
            version="1.0.0"
        )

    def create_widget(self, parent=None) -> QWidget:
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)

        label = QLabel("This is a simple display plugin")
        button = QPushButton("Click Me")
        button.clicked.connect(self.on_button_clicked)

        layout.addWidget(label)
        layout.addWidget(button)

        return widget

    def on_button_clicked(self):
        self.status_changed.emit("Button was clicked!")

    def on_tab_activated(self):
        self.status_changed.emit("Simple Display activated")

    def on_tab_deactivated(self):
        pass

def create_plugin():
    return SimpleDisplayPlugin()
```

### Data Processing Plugin

A plugin that processes data in background:

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QPushButton, QTextEdit
)
from PySide6.QtCore import QThread, Signal
from ..base_tab import BaseTabPlugin, TabPluginMetadata

class DataWorker(QThread):
    result_ready = Signal(str)

    def run(self):
        # Simulate processing
        import time
        time.sleep(2)
        self.result_ready.emit("Processing completed!")

class DataProcessingPlugin(BaseTabPlugin):
    def __init__(self):
        super().__init__()
        self.worker = None

    def get_metadata(self) -> TabPluginMetadata:
        return TabPluginMetadata(
            plugin_id="data_processing",
            display_name="Data Processing",
            description="Processes data in background",
            version="1.0.0"
        )

    def create_widget(self, parent=None) -> QWidget:
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)

        self.status_label = QLabel("Ready")
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        process_btn = QPushButton("Start Processing")
        process_btn.clicked.connect(self.start_processing)

        layout.addWidget(self.status_label)
        layout.addWidget(self.output)
        layout.addWidget(process_btn)

        return widget

    def start_processing(self):
        if self.worker and self.worker.isRunning():
            return

        self.status_label.setText("Processing...")
        self.status_changed.emit("Processing started")

        self.worker = DataWorker()
        self.worker.result_ready.connect(self.on_result)
        self.worker.start()

    def on_result(self, result):
        self.status_label.setText("Completed")
        self.output.append(result)
        self.status_changed.emit("Processing completed")

    def on_tab_activated(self):
        pass

    def on_tab_deactivated(self):
        pass

    def cleanup(self):
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()

def create_plugin():
    return DataProcessingPlugin()
```

## Troubleshooting

### Plugin Not Appearing

1. Check `~/.bmlibrarian/gui_config.json` - is your plugin listed in `enabled_plugins`?
2. Check `plugin.py` exists in your plugin directory
3. Check `create_plugin()` function exists and returns a BaseTabPlugin instance
4. Check logs at `~/.bmlibrarian/gui_qt.log` for error messages

### Plugin Crashes on Load

1. Check `get_metadata()` returns valid TabPluginMetadata
2. Check `create_widget()` returns a valid QWidget
3. Check for exceptions in `__init__` method
4. Review logs for stack traces

### UI Freezing

1. Move long operations to worker threads
2. Use signals to update UI from worker threads
3. Don't block the main thread

### Signal Not Working

1. Ensure signal is defined as class variable: `signal_name = Signal(type)`
2. Connect signal after object creation
3. Emit with correct type: `self.signal_name.emit(value)`

## Additional Resources

- **Qt Documentation**: https://doc.qt.io/qtforpython/
- **BMLibrarian Agents**: See `doc/developers/agent_module.md`
- **Example Plugins**: See `src/bmlibrarian/gui/qt/plugins/example/`
- **Widget Library**: See `src/bmlibrarian/gui/qt/widgets/`

## Getting Help

- Check existing plugins for examples
- Review logs at `~/.bmlibrarian/gui_qt.log`
- Ask in project discussions/issues

---

**Happy Plugin Development!**

This guide covers the essentials of creating plugins for BMLibrarian Qt GUI. For more advanced topics, refer to the source code of existing plugins.
