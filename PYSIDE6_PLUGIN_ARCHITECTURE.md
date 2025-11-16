# PySide6 Plugin Architecture - Technical Implementation Guide

## Table of Contents
1. [Plugin System Architecture](#plugin-system-architecture)
2. [Core Components Reference](#core-components-reference)
3. [Inter-Tab Communication](#inter-tab-communication)
4. [Thread Safety and Async Operations](#thread-safety-and-async-operations)
5. [Resource Management](#resource-management)
6. [Advanced Plugin Features](#advanced-plugin-features)
7. [Complete Plugin Example](#complete-plugin-example)

## Plugin System Architecture

### Overview

The BMLibrarian Qt GUI uses a plugin-based architecture where each major feature (research workflow, configuration, fact-checking, etc.) is implemented as an independent, loadable plugin. This provides:

- **Modularity**: Features can be developed, tested, and maintained independently
- **Configurability**: Users can enable/disable tabs based on their needs
- **Extensibility**: New features can be added without modifying core code
- **Maintainability**: Clear separation of concerns and responsibilities

### Plugin Lifecycle

```
Discovery → Loading → Registration → Activation → Deactivation → Cleanup
```

1. **Discovery**: PluginManager scans `gui/qt/plugins/` directory
2. **Loading**: Dynamic import of plugin module and instantiation
3. **Registration**: Plugin registered in TabRegistry with metadata
4. **Activation**: User navigates to tab, `on_tab_activated()` called
5. **Deactivation**: User leaves tab, `on_tab_deactivated()` called
6. **Cleanup**: Application closes, `cleanup()` called for resource release

## Core Components Reference

### TabRegistry

```python
# src/bmlibrarian/gui/qt/core/tab_registry.py

from typing import Dict, Optional, List
from ..plugins.base_tab import BaseTabPlugin, TabPluginMetadata

class TabRegistry:
    """Central registry for all tab plugins."""

    def __init__(self):
        self._plugins: Dict[str, BaseTabPlugin] = {}
        self._metadata: Dict[str, TabPluginMetadata] = {}

    def register(self, plugin: BaseTabPlugin):
        """Register a plugin."""
        metadata = plugin.get_metadata()
        plugin_id = metadata.plugin_id

        if plugin_id in self._plugins:
            raise ValueError(f"Plugin '{plugin_id}' already registered")

        self._plugins[plugin_id] = plugin
        self._metadata[plugin_id] = metadata

    def unregister(self, plugin_id: str):
        """Unregister a plugin."""
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]
            del self._metadata[plugin_id]

    def get_plugin(self, plugin_id: str) -> Optional[BaseTabPlugin]:
        """Get a plugin by ID."""
        return self._plugins.get(plugin_id)

    def get_metadata(self, plugin_id: str) -> Optional[TabPluginMetadata]:
        """Get plugin metadata."""
        return self._metadata.get(plugin_id)

    def list_plugins(self) -> List[str]:
        """List all registered plugin IDs."""
        return list(self._plugins.keys())

    def validate_dependencies(self, plugin_id: str) -> bool:
        """Check if plugin dependencies are satisfied."""
        metadata = self._metadata.get(plugin_id)
        if not metadata:
            return False

        for required_id in metadata.requires:
            if required_id not in self._plugins:
                return False

        return True
```

### ConfigManager

```python
# src/bmlibrarian/gui/qt/core/config_manager.py

from pathlib import Path
import json
from typing import Dict, Any, Optional

class GUIConfigManager:
    """Manages GUI-specific configuration."""

    DEFAULT_CONFIG = {
        "gui": {
            "theme": "default",
            "window": {
                "width": 1400,
                "height": 900,
                "remember_geometry": True
            },
            "tabs": {
                "enabled_plugins": [
                    "research",
                    "search",
                    "configuration"
                ],
                "tab_order": [
                    "research",
                    "search",
                    "configuration"
                ],
                "default_tab": "research"
            }
        }
    }

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path.home() / ".bmlibrarian" / "gui_config.json"

        self.config_path = config_path
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if not self.config_path.exists():
            # Create default config
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG.copy()

        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                # Merge with defaults (for new keys)
                return self._merge_configs(self.DEFAULT_CONFIG, config)
        except Exception as e:
            print(f"Error loading GUI config: {e}")
            return self.DEFAULT_CONFIG.copy()

    def _merge_configs(self, default: Dict, user: Dict) -> Dict:
        """Recursively merge user config with defaults."""
        result = default.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self._config

    def save_config(self, config: Dict[str, Any]):
        """Save configuration to file."""
        self._config = config
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)

    def get_plugin_config(self, plugin_id: str) -> Dict[str, Any]:
        """Get configuration for a specific plugin."""
        return self._config.get("gui", {}).get(f"{plugin_id}_tab", {})

    def set_plugin_config(self, plugin_id: str, config: Dict[str, Any]):
        """Set configuration for a specific plugin."""
        if "gui" not in self._config:
            self._config["gui"] = {}
        self._config["gui"][f"{plugin_id}_tab"] = config
        self.save_config(self._config)
```

### EventBus

```python
# src/bmlibrarian/gui/qt/core/event_bus.py

from PySide6.QtCore import QObject, Signal
from typing import Any, Dict

class EventBus(QObject):
    """Central event bus for inter-plugin communication."""

    # Global signals
    data_shared = Signal(str, dict)  # (source_plugin_id, data)
    navigation_requested = Signal(str)  # target_plugin_id
    status_updated = Signal(str)  # message
    workflow_state_changed = Signal(str, dict)  # (state, context)

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            super().__init__()
            self._initialized = True

    def publish_data(self, source_plugin_id: str, data: Dict[str, Any]):
        """Publish data from a plugin to all listeners."""
        self.data_shared.emit(source_plugin_id, data)

    def request_navigation(self, target_plugin_id: str):
        """Request navigation to a specific tab."""
        self.navigation_requested.emit(target_plugin_id)

    def update_status(self, message: str):
        """Update application status bar."""
        self.status_updated.emit(message)

    def notify_workflow_state(self, state: str, context: Dict[str, Any]):
        """Notify all plugins of workflow state change."""
        self.workflow_state_changed.emit(state, context)
```

## Inter-Tab Communication

### Using the Event Bus

Plugins can communicate through the centralized EventBus:

```python
from bmlibrarian.gui.qt.core.event_bus import EventBus

class ResearchTabPlugin(BaseTabPlugin):
    def __init__(self):
        super().__init__()
        self.event_bus = EventBus()

        # Subscribe to events from other plugins
        self.event_bus.data_shared.connect(self._on_data_received)
        self.event_bus.workflow_state_changed.connect(self._on_workflow_state)

    def _on_search_completed(self, documents):
        """Called when document search completes."""
        # Share results with other plugins
        self.event_bus.publish_data("research", {
            "event": "search_completed",
            "document_count": len(documents),
            "documents": documents
        })

    def _on_data_received(self, source_plugin_id: str, data: dict):
        """Handle data from other plugins."""
        if source_plugin_id == "search":
            # Process search results from search plugin
            if data.get("event") == "filter_applied":
                self._update_document_list(data["filtered_docs"])

    def _navigate_to_config(self):
        """Navigate user to configuration tab."""
        self.event_bus.request_navigation("configuration")
```

### Direct Plugin Communication

For tightly coupled interactions, plugins can communicate directly through the registry:

```python
from bmlibrarian.gui.qt.core.tab_registry import TabRegistry

class FactCheckerPlugin(BaseTabPlugin):
    def __init__(self, registry: TabRegistry):
        super().__init__()
        self.registry = registry

    def _request_document_details(self, doc_id: str):
        """Request detailed info from search plugin."""
        search_plugin = self.registry.get_plugin("search")
        if search_plugin and hasattr(search_plugin, "get_document_details"):
            return search_plugin.get_document_details(doc_id)
        return None
```

## Thread Safety and Async Operations

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

class ResearchTabWidget(QWidget):
    """Research tab with async workflow execution."""

    def __init__(self):
        super().__init__()
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(4)

    def execute_workflow_step(self, step_fn, *args, **kwargs):
        """Execute a workflow step asynchronously."""
        worker = WorkflowWorker(step_fn, *args, **kwargs)

        # Connect signals
        worker.signals.result.connect(self._on_step_completed)
        worker.signals.error.connect(self._on_step_error)
        worker.signals.finished.connect(self._on_step_finished)

        # Update UI to show progress
        self._set_status("Processing...")

        # Start execution
        self.threadpool.start(worker)

    @Slot(object)
    def _on_step_completed(self, result):
        """Handle step completion (runs in main thread)."""
        # Update UI with results
        self.result_viewer.display_results(result)

    @Slot(tuple)
    def _on_step_error(self, error_info):
        """Handle step error (runs in main thread)."""
        exc_type, exc_value, exc_traceback = error_info
        # Show error dialog
        QMessageBox.critical(self, "Error", str(exc_value))

    @Slot()
    def _on_step_finished(self):
        """Step finished (success or error)."""
        self._set_status("Ready")
```

### Progress Reporting

For long-running operations with progress updates:

```python
class ProgressWorker(QRunnable):
    """Worker with progress reporting."""

    def __init__(self, agent, documents):
        super().__init__()
        self.agent = agent
        self.documents = documents
        self.signals = WorkerSignals()

    def progress_callback(self, current, total):
        """Called by agent to report progress."""
        percentage = int((current / total) * 100)
        self.signals.progress.emit(percentage)

    @Slot()
    def run(self):
        """Execute with progress reporting."""
        try:
            result = self.agent.process_documents(
                self.documents,
                progress_callback=self.progress_callback
            )
            self.signals.result.emit(result)
        except Exception as e:
            self.signals.error.emit((type(e), e, traceback.format_exc()))
        finally:
            self.signals.finished.emit()

# In the widget
def start_scoring(self):
    worker = ProgressWorker(self.scoring_agent, self.documents)
    worker.signals.progress.connect(self.progress_bar.setValue)
    worker.signals.result.connect(self._on_scoring_complete)
    self.threadpool.start(worker)
```

## Resource Management

### Plugin Cleanup

Plugins must properly cleanup resources when deactivated or unloaded:

```python
class ResearchTabPlugin(BaseTabPlugin):
    def __init__(self):
        super().__init__()
        self.threadpool = QThreadPool()
        self.database_connections = []
        self.temp_files = []

    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        # Stop all running threads
        self.threadpool.clear()
        self.threadpool.waitForDone(5000)  # Wait up to 5 seconds

        # Close database connections
        for conn in self.database_connections:
            try:
                conn.close()
            except:
                pass

        # Delete temporary files
        for temp_file in self.temp_files:
            try:
                temp_file.unlink()
            except:
                pass

        # Disconnect event bus signals
        self.event_bus.data_shared.disconnect(self._on_data_received)

        print(f"Plugin '{self.get_metadata().plugin_id}' cleaned up")
```

### Memory Management

Use weak references for large data structures shared between plugins:

```python
import weakref
from typing import Optional

class DocumentCache:
    """Shared document cache using weak references."""

    def __init__(self):
        self._cache = weakref.WeakValueDictionary()

    def set(self, doc_id: str, document: dict):
        """Store document (will be garbage collected when no longer used)."""
        # Wrap in a container object (WeakValueDictionary needs objects, not dicts)
        self._cache[doc_id] = DocumentWrapper(document)

    def get(self, doc_id: str) -> Optional[dict]:
        """Retrieve document if still in memory."""
        wrapper = self._cache.get(doc_id)
        return wrapper.data if wrapper else None

class DocumentWrapper:
    """Wrapper for documents in weak reference cache."""
    def __init__(self, data: dict):
        self.data = data
```

## Advanced Plugin Features

### Plugin Dependencies

Declare dependencies in metadata:

```python
class AdvancedSearchPlugin(BaseTabPlugin):
    def get_metadata(self) -> TabPluginMetadata:
        return TabPluginMetadata(
            plugin_id="advanced_search",
            display_name="Advanced Search",
            description="Enhanced search with filters",
            version="1.0.0",
            requires=["search"]  # Requires basic search plugin
        )

# PluginManager validates dependencies before loading
def load_plugin(self, plugin_id: str) -> Optional[BaseTabPlugin]:
    # ... load plugin ...

    # Validate dependencies
    if not self.registry.validate_dependencies(plugin_id):
        metadata = plugin.get_metadata()
        missing = [r for r in metadata.requires
                   if r not in self.registry.list_plugins()]
        raise ValueError(f"Missing dependencies: {missing}")

    return plugin
```

### Plugin Configuration UI

Plugins can provide their own configuration widgets:

```python
class ResearchTabPlugin(BaseTabPlugin):
    def create_config_widget(self, parent=None) -> Optional[QWidget]:
        """Create configuration widget for this plugin."""
        widget = QWidget(parent)
        layout = QFormLayout(widget)

        # Add configuration options
        self.show_steps_checkbox = QCheckBox()
        self.show_steps_checkbox.setChecked(
            self.config.get("show_workflow_steps", True)
        )
        layout.addRow("Show Workflow Steps:", self.show_steps_checkbox)

        self.auto_scroll_checkbox = QCheckBox()
        self.auto_scroll_checkbox.setChecked(
            self.config.get("auto_scroll_to_active", True)
        )
        layout.addRow("Auto-scroll to Active Step:", self.auto_scroll_checkbox)

        return widget

    def get_config_from_widget(self, widget: QWidget) -> Dict[str, Any]:
        """Extract configuration from the widget."""
        return {
            "show_workflow_steps": self.show_steps_checkbox.isChecked(),
            "auto_scroll_to_active": self.auto_scroll_checkbox.isChecked()
        }
```

### Hot Reload (Development)

For development, support hot reloading of plugins:

```python
class PluginManager:
    def reload_plugin(self, plugin_id: str):
        """Reload a plugin (for development)."""
        # Unload existing
        if plugin_id in self.loaded_plugins:
            self.unload_plugin(plugin_id)

        # Clear module cache
        import sys
        module_name = f"bmlibrarian.gui.qt.plugins.{plugin_id}"
        if module_name in sys.modules:
            del sys.modules[module_name]

        # Reload
        return self.load_plugin(plugin_id)
```

## Complete Plugin Example

### Full-Featured Search Plugin

```python
# src/bmlibrarian/gui/qt/plugins/search/plugin.py

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QLabel,
    QProgressBar, QMessageBox
)
from PySide6.QtCore import Qt, Slot, QRunnable, QThreadPool
from typing import Dict, Any, List
import psycopg

from ..base_tab import BaseTabPlugin, TabPluginMetadata
from ...core.event_bus import EventBus
from ...widgets.document_card import DocumentCard
from ...utils.threading import WorkerSignals

class SearchWorker(QRunnable):
    """Worker for executing database searches."""

    def __init__(self, query: str, db_config: Dict[str, str]):
        super().__init__()
        self.query = query
        self.db_config = db_config
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        """Execute search query."""
        try:
            # Connect to database
            conn = psycopg.connect(**self.db_config)
            cursor = conn.cursor()

            # Execute search
            cursor.execute("""
                SELECT id, title, abstract, source, date_added
                FROM documents
                WHERE title ILIKE %s OR abstract ILIKE %s
                ORDER BY date_added DESC
                LIMIT 100
            """, (f"%{self.query}%", f"%{self.query}%"))

            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row[0],
                    "title": row[1],
                    "abstract": row[2],
                    "source": row[3],
                    "date_added": row[4]
                })

            cursor.close()
            conn.close()

            self.signals.result.emit(results)

        except Exception as e:
            import traceback
            self.signals.error.emit((type(e), e, traceback.format_exc()))
        finally:
            self.signals.finished.emit()


class SearchTabWidget(QWidget):
    """Search tab widget."""

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.db_config = plugin.get_db_config()
        self.threadpool = QThreadPool()
        self.current_results = []

        self._build_ui()

    def _build_ui(self):
        """Build the user interface."""
        layout = QVBoxLayout(self)

        # Search input
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search terms...")
        self.search_input.returnPressed.connect(self._on_search_clicked)
        search_layout.addWidget(self.search_input)

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._on_search_clicked)
        search_layout.addWidget(self.search_button)

        layout.addLayout(search_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Results status
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(
            ["ID", "Title", "Source", "Date"]
        )
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.itemDoubleClicked.connect(self._on_result_double_clicked)
        layout.addWidget(self.results_table)

        # Action buttons
        button_layout = QHBoxLayout()
        self.export_button = QPushButton("Export Results")
        self.export_button.clicked.connect(self._on_export_clicked)
        self.export_button.setEnabled(False)
        button_layout.addWidget(self.export_button)

        self.share_button = QPushButton("Share with Research Tab")
        self.share_button.clicked.connect(self._on_share_clicked)
        self.share_button.setEnabled(False)
        button_layout.addWidget(self.share_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

    @Slot()
    def _on_search_clicked(self):
        """Execute search."""
        query = self.search_input.text().strip()
        if not query:
            return

        # Update UI
        self.search_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.status_label.setText(f"Searching for: {query}")

        # Create and start worker
        worker = SearchWorker(query, self.db_config)
        worker.signals.result.connect(self._on_search_complete)
        worker.signals.error.connect(self._on_search_error)
        worker.signals.finished.connect(self._on_search_finished)

        self.threadpool.start(worker)

    @Slot(object)
    def _on_search_complete(self, results: List[Dict[str, Any]]):
        """Handle search results."""
        self.current_results = results

        # Update table
        self.results_table.setRowCount(len(results))
        for i, doc in enumerate(results):
            self.results_table.setItem(i, 0, QTableWidgetItem(str(doc["id"])))
            self.results_table.setItem(i, 1, QTableWidgetItem(doc["title"]))
            self.results_table.setItem(i, 2, QTableWidgetItem(doc["source"]))
            self.results_table.setItem(i, 3,
                QTableWidgetItem(doc["date_added"].strftime("%Y-%m-%d")))

        # Update status
        self.status_label.setText(f"Found {len(results)} documents")

        # Enable action buttons
        self.export_button.setEnabled(len(results) > 0)
        self.share_button.setEnabled(len(results) > 0)

    @Slot(tuple)
    def _on_search_error(self, error_info):
        """Handle search error."""
        exc_type, exc_value, exc_traceback = error_info
        QMessageBox.critical(self, "Search Error", str(exc_value))
        self.status_label.setText("Error occurred")

    @Slot()
    def _on_search_finished(self):
        """Search finished (success or error)."""
        self.search_button.setEnabled(True)
        self.progress_bar.setVisible(False)

    @Slot()
    def _on_result_double_clicked(self):
        """Handle double-click on result."""
        current_row = self.results_table.currentRow()
        if 0 <= current_row < len(self.current_results):
            doc = self.current_results[current_row]
            # Show document details dialog
            self._show_document_details(doc)

    @Slot()
    def _on_export_clicked(self):
        """Export results to file."""
        # TODO: Implement export functionality
        pass

    @Slot()
    def _on_share_clicked(self):
        """Share results with other tabs via event bus."""
        self.plugin.event_bus.publish_data("search", {
            "event": "search_results",
            "query": self.search_input.text(),
            "documents": self.current_results
        })
        self.status_label.setText(
            f"Shared {len(self.current_results)} documents with other tabs"
        )

    def _show_document_details(self, doc: Dict[str, Any]):
        """Show detailed view of a document."""
        # TODO: Implement document details dialog
        pass


class SearchPlugin(BaseTabPlugin):
    """Search tab plugin."""

    def __init__(self):
        super().__init__()
        self.event_bus = EventBus()
        self.widget = None
        self.config = {}

    def get_metadata(self) -> TabPluginMetadata:
        return TabPluginMetadata(
            plugin_id="search",
            display_name="Document Search",
            description="Search biomedical literature database",
            version="1.0.0",
            icon="search.png"
        )

    def create_widget(self, parent=None) -> QWidget:
        """Create the search tab widget."""
        self.widget = SearchTabWidget(self, parent)
        return self.widget

    def on_tab_activated(self):
        """Called when tab is activated."""
        self.event_bus.update_status("Search tab active")

    def on_tab_deactivated(self):
        """Called when tab is deactivated."""
        pass

    def get_config(self) -> Dict[str, Any]:
        """Get plugin configuration."""
        return self.config

    def set_config(self, config: Dict[str, Any]):
        """Set plugin configuration."""
        self.config = config

    def get_db_config(self) -> Dict[str, str]:
        """Get database configuration."""
        # TODO: Load from BMLibrarian config
        return {
            "dbname": "knowledgebase",
            "user": "postgres",
            "password": "",
            "host": "localhost",
            "port": "5432"
        }

    def get_document_details(self, doc_id: str) -> Dict[str, Any]:
        """Get detailed information about a document (for other plugins)."""
        # Find in current results
        if self.widget and self.widget.current_results:
            for doc in self.widget.current_results:
                if str(doc["id"]) == str(doc_id):
                    return doc
        return None

    def cleanup(self):
        """Cleanup resources."""
        if self.widget:
            self.widget.threadpool.clear()
            self.widget.threadpool.waitForDone(5000)


def create_plugin() -> BaseTabPlugin:
    """Plugin entry point."""
    return SearchPlugin()
```

## Best Practices Summary

1. **Plugin Independence**: Plugins should not directly import from each other
2. **Use Event Bus**: Prefer event bus for inter-plugin communication
3. **Thread Safety**: All long operations in background threads
4. **Resource Cleanup**: Always implement proper cleanup
5. **Configuration**: Store plugin-specific settings in GUI config
6. **Error Handling**: Graceful error handling with user feedback
7. **Progress Reporting**: Show progress for long operations
8. **Memory Management**: Use weak references for shared large data
9. **Documentation**: Document plugin interface and signals
10. **Testing**: Write unit tests for each plugin

## Troubleshooting

### Common Issues

**Issue**: Plugin not loading
- Check plugin directory structure
- Verify `plugin.py` exists with `create_plugin()` function
- Check for syntax errors in plugin code
- Verify plugin ID is in enabled_plugins list

**Issue**: UI freezing during operations
- Ensure long operations are in background threads
- Check for blocking operations in main thread
- Use QThreadPool for concurrent operations

**Issue**: Memory leaks
- Check for circular references
- Verify cleanup() properly releases resources
- Use weak references for shared data
- Monitor with memory profiler

**Issue**: Signals not working
- Verify signal connections
- Check for disconnected signals on cleanup
- Ensure signals emitted from correct thread (use Qt.QueuedConnection if needed)

## Next Steps

After reading this guide:
1. Review the base plugin example
2. Study existing plugin implementations
3. Create a simple plugin using the template
4. Test plugin loading and lifecycle
5. Implement inter-tab communication
6. Add async operations with threading
7. Write unit tests for your plugin

For questions or issues, refer to the main migration plan or consult Qt documentation.
