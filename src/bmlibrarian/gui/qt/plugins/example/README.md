# Example Plugin - Template and Learning Resource

## Overview

This directory contains the **Example Plugin**, which serves as both a functional demonstration of the BMLibrarian Qt GUI plugin architecture and a template for creating new plugins.

## Purpose

The Example Plugin demonstrates:

1. **Complete Plugin Structure**: All required methods and patterns
2. **Best Practices**: Proper separation of concerns, error handling, resource management
3. **Interactive Features**: Buttons, signals, event bus communication
4. **Configuration**: Plugin-specific settings management
5. **Lifecycle Management**: Tab activation, deactivation, cleanup

## Directory Structure

```
example/
├── __init__.py          # Package marker (empty)
├── plugin.py            # Plugin implementation
└── README.md            # This file
```

## File Breakdown

### `plugin.py`

This file contains the complete plugin implementation with two main classes:

#### 1. `ExampleTabWidget` (Lines 24-156)

The UI component that creates the visual interface.

**Key Components**:
- **UI Building** (`_build_ui`, line 40): Creates the widget layout
- **Interactive Buttons**: Demonstrate signal/slot connections
- **Activity Log**: Shows plugin events in real-time
- **Event Handling**: Slot methods for button clicks

**Layout Structure**:
```
ExampleTabWidget
├── Header (QLabel)
├── Description (QLabel)
├── Features Group (QGroupBox)
│   └── Feature list
├── Interactive Group (QGroupBox)
│   ├── Status bar update button
│   ├── Event bus publish button
│   └── Navigation request button
└── Activity Log (QTextEdit)
```

**Important Methods**:
- `_log(message)`: Adds messages to activity log
- `_on_status_button_clicked()`: Updates main window status bar
- `_on_event_button_clicked()`: Publishes data to event bus
- `_on_nav_button_clicked()`: Requests navigation to another tab
- `on_activated()`: Called when tab becomes visible
- `on_deactivated()`: Called when tab is hidden

#### 2. `ExamplePlugin` (Lines 158-239)

The plugin class that implements the BaseTabPlugin interface.

**Required Methods** (You MUST implement these):

1. **`get_metadata()`** (Line 170):
   - Returns `TabPluginMetadata` with plugin information
   - **Fields**:
     - `plugin_id`: Unique identifier (snake_case)
     - `display_name`: Tab title shown to users
     - `description`: Brief description
     - `version`: Semantic version (e.g., "1.0.0")
     - `icon`: Optional path to icon
     - `requires`: Optional list of dependency plugin IDs

2. **`create_widget(parent)`** (Line 185):
   - Creates and returns the main QWidget for the tab
   - Called once during plugin loading
   - Store widget reference if you need to access it later

3. **`on_tab_activated()`** (Line 197):
   - Called when tab becomes active (user clicks tab)
   - Use for: Refreshing data, starting timers, emitting status
   - Keep lightweight (don't block UI)

4. **`on_tab_deactivated()`** (Line 203):
   - Called when user switches to another tab
   - Use for: Pausing tasks, saving temporary state

**Optional Methods** (Implement if needed):

5. **`get_config()`** (Line 208):
   - Returns plugin-specific configuration
   - Configuration stored in `~/.bmlibrarian/gui_config.json`

6. **`set_config(config)`** (Line 219):
   - Updates plugin configuration
   - Apply configuration changes to plugin behavior

7. **`cleanup()`** (Line 228):
   - Called when application is closing
   - **Critical**: Release resources (connections, threads, files)
   - Always call `super().cleanup()` at the end

#### 3. `create_plugin()` Function (Line 241)

**Plugin Entry Point** - The PluginManager calls this to instantiate your plugin.

```python
def create_plugin() -> BaseTabPlugin:
    """Plugin entry point."""
    return ExamplePlugin()
```

**Important**: This function MUST exist and MUST be named `create_plugin`.

## How to Use as a Template

### Step 1: Copy the Example

```bash
# From repository root
cp -r src/bmlibrarian/gui/qt/plugins/example src/bmlibrarian/gui/qt/plugins/my_plugin
```

### Step 2: Rename and Customize

Edit `my_plugin/plugin.py`:

1. **Update Plugin Metadata** (line 176):
   ```python
   return TabPluginMetadata(
       plugin_id="my_plugin",           # Change this
       display_name="My Plugin",        # Change this
       description="My awesome plugin", # Change this
       version="1.0.0",
       icon=None,
       requires=[]
   )
   ```

2. **Rename Classes**:
   - `ExamplePlugin` → `MyPlugin`
   - `ExampleTabWidget` → `MyPluginWidget`

3. **Update `create_plugin()`**:
   ```python
   def create_plugin() -> BaseTabPlugin:
       return MyPlugin()  # Change this
   ```

4. **Customize UI** in `_build_ui()`:
   - Replace header text
   - Add your own widgets
   - Create your plugin's functionality

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

### Step 4: Test

```bash
python bmlibrarian_qt.py
```

Your plugin should appear as a new tab!

## Key Patterns Demonstrated

### Pattern 1: Separation of UI and Logic

```python
class MyPluginWidget(QWidget):
    """UI component"""
    def __init__(self, plugin, parent=None):
        self.plugin = plugin  # Reference to plugin for signals

class MyPlugin(BaseTabPlugin):
    """Plugin logic"""
    def create_widget(self, parent=None):
        return MyPluginWidget(self, parent)
```

**Why**: Keeps business logic separate from UI code for better maintainability.

### Pattern 2: Signal/Slot Communication

```python
# In widget
def _on_button_clicked(self):
    self.plugin.status_changed.emit("Button clicked!")

# In plugin class
self.status_changed.emit("Status message")  # Updates main window status bar
self.request_navigation.emit("configuration")  # Navigate to another tab
self.data_updated.emit({"key": "value"})  # Share data with other plugins
```

**Why**: Decouples components, makes code more maintainable.

### Pattern 3: Event Bus for Inter-Plugin Communication

```python
# Publish data
self.event_bus.publish_data("my_plugin", {
    "event": "something_happened",
    "data": my_data
})

# Subscribe to data (in another plugin)
self.event_bus.data_published.connect(self.on_data_received)
```

**Why**: Allows plugins to communicate without direct dependencies.

### Pattern 4: Resource Cleanup

```python
def cleanup(self):
    # 1. Stop background tasks
    if self.worker:
        self.worker.quit()
        self.worker.wait()

    # 2. Close connections
    if self.db_connection:
        self.db_connection.close()

    # 3. Clear references
    self.widget = None

    # 4. Call parent cleanup
    super().cleanup()
```

**Why**: Prevents memory leaks and ensures graceful shutdown.

### Pattern 5: Logging

```python
# In plugin class
self.logger.info("Important event")
self.logger.debug("Detailed information")
self.logger.error("Something went wrong", exc_info=True)

# In widget class
self._log("User-visible event")  # Shows in UI log area
```

**Why**: Debugging and troubleshooting.

## Interactive Features

The Example Plugin includes interactive buttons that demonstrate:

### 1. Status Bar Update

**Button**: "Update Status Bar"

**What it does**:
- Emits `status_changed` signal
- Main window displays message in status bar
- Message shows for 5 seconds

**Code**:
```python
self.plugin.status_changed.emit("Status updated from example plugin!")
```

**Use this pattern**: When you want to show brief status updates to the user.

### 2. Event Bus Message

**Button**: "Publish Event Bus Message"

**What it does**:
- Publishes data to the event bus
- Other plugins can subscribe to receive this data
- Demonstrates inter-plugin communication

**Code**:
```python
self.event_bus.publish_data("example", {
    "event": "example_event",
    "message": "Hello from example plugin!",
    "timestamp": "now"
})
```

**Use this pattern**: When you need to share data between plugins.

### 3. Tab Navigation

**Button**: "Request Navigation to Configuration"

**What it does**:
- Emits `request_navigation` signal
- Main window switches to specified tab
- Demonstrates programmatic navigation

**Code**:
```python
self.plugin.request_navigation.emit("configuration")
```

**Use this pattern**: When your plugin needs to direct users to another tab.

## Configuration Example

The plugin includes configuration methods:

```python
def get_config(self) -> Dict[str, Any]:
    """Get current configuration."""
    return {
        "example_setting": True,
        "example_value": 42
    }

def set_config(self, config: Dict[str, Any]):
    """Update configuration."""
    self.logger.info(f"Configuration updated: {config}")
```

**How to use**:

1. **Load config from file**:
   ```python
   from ...core.config_manager import GUIConfigManager
   config_manager = GUIConfigManager()
   config = config_manager.get_plugin_config("my_plugin")
   ```

2. **Save config to file**:
   ```python
   config_manager.set_plugin_config("my_plugin", {
       "setting1": value1,
       "setting2": value2
   })
   ```

3. **Access in widget**:
   ```python
   config = self.plugin.get_config()
   if config.get("example_setting", True):
       # Do something
   ```

## Common Customizations

### Add a Worker Thread

For long-running operations:

```python
from PySide6.QtCore import QThread, Signal

class WorkerThread(QThread):
    finished = Signal(dict)

    def run(self):
        # Long operation here
        result = self.do_work()
        self.finished.emit(result)

class MyPlugin(BaseTabPlugin):
    def start_work(self):
        self.worker = WorkerThread()
        self.worker.finished.connect(self.on_work_finished)
        self.worker.start()

    def on_work_finished(self, result):
        self.status_changed.emit("Work completed!")

    def cleanup(self):
        if self.worker:
            self.worker.quit()
            self.worker.wait()
        super().cleanup()
```

### Add Database Access

```python
import psycopg
from bmlibrarian.cli.config import get_config

class MyPlugin(BaseTabPlugin):
    def __init__(self):
        super().__init__()
        self.conn = None

    def create_widget(self, parent=None):
        # Connect to database
        config = get_config()
        self.conn = psycopg.connect(
            dbname=config["database"]["name"],
            user=config["database"]["user"],
            password=config["database"]["password"]
        )
        return MyPluginWidget(self, parent)

    def query_database(self, sql, params=None):
        with self.conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()

    def cleanup(self):
        if self.conn:
            self.conn.close()
        super().cleanup()
```

### Add Reusable Widgets

```python
from ...widgets import (
    DocumentCard,
    MarkdownViewer,
    ProgressWidget,
    CollapsibleSection
)

class MyPluginWidget(QWidget):
    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # Use progress widget
        self.progress = ProgressWidget()
        layout.addWidget(self.progress)

        # Use markdown viewer
        self.viewer = MarkdownViewer()
        layout.addWidget(self.viewer)

        # Use collapsible section
        section = CollapsibleSection("Details")
        layout.addWidget(section)
```

## Testing Your Plugin

### Manual Testing Checklist

- [ ] Plugin loads without errors
- [ ] Tab appears with correct title
- [ ] UI renders correctly
- [ ] Buttons/controls are functional
- [ ] Status bar updates work
- [ ] Tab activation/deactivation work
- [ ] Navigation works (if applicable)
- [ ] Cleanup doesn't cause errors
- [ ] Configuration saves/loads correctly

### Automated Testing

Create `tests/gui/qt/plugins/test_my_plugin.py`:

```python
import pytest
from pytestqt.qtbot import QtBot
from bmlibrarian.gui.qt.plugins.my_plugin.plugin import (
    MyPlugin, create_plugin
)

def test_plugin_creation():
    plugin = create_plugin()
    assert plugin is not None
    assert isinstance(plugin, MyPlugin)

def test_metadata():
    plugin = create_plugin()
    metadata = plugin.get_metadata()
    assert metadata.plugin_id == "my_plugin"
    assert metadata.display_name == "My Plugin"

def test_widget_creation(qtbot):
    plugin = create_plugin()
    widget = plugin.create_widget()
    qtbot.addWidget(widget)
    assert widget is not None
    assert widget.isVisible()
```

Run tests:
```bash
pytest tests/gui/qt/plugins/test_my_plugin.py -v
```

## Troubleshooting

### Plugin Not Appearing

**Problem**: Plugin doesn't show up in tabs

**Checklist**:
1. ✅ `plugin.py` exists in plugin directory?
2. ✅ `create_plugin()` function exists?
3. ✅ Plugin ID added to `gui_config.json` `enabled_plugins`?
4. ✅ No syntax errors? Check logs at `~/.bmlibrarian/gui_qt.log`

### Import Errors

**Problem**: `ImportError` or `ModuleNotFoundError`

**Solutions**:
- Use relative imports: `from ..base_tab import BaseTabPlugin`
- For core: `from ...core.config_manager import GUIConfigManager`
- For widgets: `from ...widgets import DocumentCard`

### Widget Not Showing

**Problem**: Tab is empty or widget doesn't appear

**Checklist**:
1. ✅ `create_widget()` returns a QWidget?
2. ✅ Widget has a layout?
3. ✅ Widgets are added to layout?
4. ✅ No exceptions during widget creation?

### Signals Not Working

**Problem**: Buttons click but nothing happens

**Checklist**:
1. ✅ Signal is connected: `button.clicked.connect(self.handler)`?
2. ✅ Handler is a slot: `@Slot()` decorator?
3. ✅ Handler is a method: `self.handler` not `self.handler()`?
4. ✅ No exceptions in handler? Check logs.

## Additional Resources

- **Plugin Development Guide**: `doc/developers/qt_plugin_development_guide.md`
- **BaseTabPlugin API**: `src/bmlibrarian/gui/qt/plugins/base_tab.py`
- **Existing Plugins**: See `research/`, `search/`, `configuration/` directories
- **Widget Library**: `src/bmlibrarian/gui/qt/widgets/`
- **Qt Documentation**: https://doc.qt.io/qtforpython/

## Next Steps

After understanding the Example Plugin:

1. **Read**: Plugin Development Guide for comprehensive documentation
2. **Study**: Existing plugins (Research, Search, Configuration)
3. **Create**: Your own plugin using this as a template
4. **Test**: Write tests for your plugin
5. **Share**: Contribute your plugin to the project!

---

**Happy Plugin Development!** 🚀

The Example Plugin is here to help you learn and succeed. Refer back to it whenever you need a refresher on plugin patterns and best practices.
