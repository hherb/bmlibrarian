# PySide6 Migration - Quick Start Guide

## Getting Started in 30 Minutes

This guide will help you set up the PySide6 infrastructure and create your first plugin in under 30 minutes.

## Prerequisites

- BMLibrarian development environment setup
- Python >=3.12
- `uv` package manager
- PostgreSQL database configured

## Step 1: Install PySide6 (5 minutes)

### Update Dependencies

```bash
cd /home/user/bmlibrarian

# Edit pyproject.toml to add PySide6
```

Add these dependencies to `pyproject.toml`:

```toml
dependencies = [
    # ... existing dependencies ...
    "PySide6>=6.6.0",
    "PySide6-Addons>=6.6.0",
    "Markdown>=3.5.0",
    "Pygments>=2.17.0",
    "qtawesome>=1.3.0",
]
```

### Install Dependencies

```bash
uv sync
```

### Verify Installation

```bash
uv run python -c "from PySide6.QtWidgets import QApplication; print('PySide6 installed successfully')"
```

## Step 2: Create Directory Structure (5 minutes)

```bash
# Create main Qt GUI directory
mkdir -p src/bmlibrarian/gui/qt

# Create core framework directories
mkdir -p src/bmlibrarian/gui/qt/core
mkdir -p src/bmlibrarian/gui/qt/plugins
mkdir -p src/bmlibrarian/gui/qt/widgets
mkdir -p src/bmlibrarian/gui/qt/dialogs
mkdir -p src/bmlibrarian/gui/qt/utils
mkdir -p src/bmlibrarian/gui/qt/resources/icons
mkdir -p src/bmlibrarian/gui/qt/resources/styles

# Create plugin directories
mkdir -p src/bmlibrarian/gui/qt/plugins/research
mkdir -p src/bmlibrarian/gui/qt/plugins/configuration
mkdir -p src/bmlibrarian/gui/qt/plugins/fact_checker
mkdir -p src/bmlibrarian/gui/qt/plugins/query_lab
mkdir -p src/bmlibrarian/gui/qt/plugins/search

# Create __init__.py files
touch src/bmlibrarian/gui/qt/__init__.py
touch src/bmlibrarian/gui/qt/core/__init__.py
touch src/bmlibrarian/gui/qt/plugins/__init__.py
touch src/bmlibrarian/gui/qt/widgets/__init__.py
touch src/bmlibrarian/gui/qt/dialogs/__init__.py
touch src/bmlibrarian/gui/qt/utils/__init__.py

# Create plugin __init__.py files
touch src/bmlibrarian/gui/qt/plugins/research/__init__.py
touch src/bmlibrarian/gui/qt/plugins/configuration/__init__.py
touch src/bmlibrarian/gui/qt/plugins/fact_checker/__init__.py
touch src/bmlibrarian/gui/qt/plugins/query_lab/__init__.py
touch src/bmlibrarian/gui/qt/plugins/search/__init__.py
```

## Step 3: Implement Core Framework (10 minutes)

Create the minimal core framework files:

### 3.1 Base Tab Plugin

Create `src/bmlibrarian/gui/qt/plugins/base_tab.py`:

```python
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import QObject, Signal

class TabPluginMetadata:
    """Metadata for a tab plugin."""
    def __init__(
        self,
        plugin_id: str,
        display_name: str,
        description: str,
        version: str,
        icon: Optional[str] = None,
        requires: Optional[list] = None
    ):
        self.plugin_id = plugin_id
        self.display_name = display_name
        self.description = description
        self.version = version
        self.icon = icon
        self.requires = requires or []

class BaseTabPlugin(QObject, ABC):
    """Abstract base class for all tab plugins."""

    # Signals for inter-tab communication
    request_navigation = Signal(str)
    status_changed = Signal(str)
    data_updated = Signal(dict)

    @abstractmethod
    def get_metadata(self) -> TabPluginMetadata:
        """Return plugin metadata."""
        pass

    @abstractmethod
    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """Create and return the main widget for this tab."""
        pass

    def on_tab_activated(self):
        """Called when this tab becomes active."""
        pass

    def on_tab_deactivated(self):
        """Called when this tab is deactivated."""
        pass

    def get_config(self) -> Dict[str, Any]:
        """Get plugin-specific configuration."""
        return {}

    def set_config(self, config: Dict[str, Any]):
        """Update plugin configuration."""
        pass

    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        pass
```

### 3.2 Configuration Manager

Create `src/bmlibrarian/gui/qt/core/config_manager.py`:

```python
from pathlib import Path
import json
from typing import Dict, Any

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
                "enabled_plugins": ["research"],
                "tab_order": ["research"],
                "default_tab": "research"
            }
        }
    }

    def __init__(self, config_path: Path = None):
        if config_path is None:
            config_path = Path.home() / ".bmlibrarian" / "gui_config.json"

        self.config_path = config_path
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if not self.config_path.exists():
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG.copy()

        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading GUI config: {e}")
            return self.DEFAULT_CONFIG.copy()

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self._config

    def save_config(self, config: Dict[str, Any]):
        """Save configuration to file."""
        self._config = config
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
```

### 3.3 Simple Main Window

Create `src/bmlibrarian/gui/qt/core/main_window.py`:

```python
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QStatusBar, QLabel
)
from PySide6.QtCore import Qt

class BMLibrarianMainWindow(QMainWindow):
    """Main application window with plugin-based tabs."""

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        """Setup the main window UI."""
        self.setWindowTitle("BMLibrarian - Biomedical Literature Research (Qt)")

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # Set initial size
        self.resize(1400, 900)

    def add_tab(self, widget: QWidget, title: str):
        """Add a tab to the window."""
        self.tab_widget.addTab(widget, title)
```

### 3.4 Application Entry Point

Create `src/bmlibrarian/gui/qt/core/application.py`:

```python
import sys
from PySide6.QtWidgets import QApplication
from .main_window import BMLibrarianMainWindow

class BMLibrarianApplication:
    """Main application class."""

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("BMLibrarian")
        self.app.setOrganizationName("BMLibrarian")
        self.main_window = BMLibrarianMainWindow()

    def run(self):
        """Run the application."""
        self.main_window.show()
        return self.app.exec()

def main():
    """Application entry point."""
    app = BMLibrarianApplication()
    sys.exit(app.run())
```

### 3.5 Main Module Init

Update `src/bmlibrarian/gui/qt/__init__.py`:

```python
from .core.application import main

__all__ = ['main']
```

## Step 4: Create First Plugin - Hello World (5 minutes)

Create `src/bmlibrarian/gui/qt/plugins/research/plugin.py`:

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Slot
from ..base_tab import BaseTabPlugin, TabPluginMetadata

class ResearchTabWidget(QWidget):
    """Simple research tab widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # Add a label
        label = QLabel("Welcome to BMLibrarian Research Tab (PySide6)")
        label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(label)

        # Add a button
        button = QPushButton("Click Me!")
        button.clicked.connect(self._on_button_clicked)
        layout.addWidget(button)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        layout.addStretch()

    @Slot()
    def _on_button_clicked(self):
        """Handle button click."""
        self.status_label.setText("Button clicked!")

class ResearchPlugin(BaseTabPlugin):
    """Research tab plugin."""

    def get_metadata(self) -> TabPluginMetadata:
        return TabPluginMetadata(
            plugin_id="research",
            display_name="Research",
            description="Medical research workflow",
            version="1.0.0"
        )

    def create_widget(self, parent=None) -> QWidget:
        """Create the research tab widget."""
        return ResearchTabWidget(parent)

def create_plugin() -> BaseTabPlugin:
    """Plugin entry point."""
    return ResearchPlugin()
```

## Step 5: Create Entry Point Script (2 minutes)

Create `bmlibrarian_qt.py` in the root directory:

```python
#!/usr/bin/env python3
"""
BMLibrarian Qt GUI Entry Point

Launch the PySide6-based GUI for BMLibrarian.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.gui.qt.core.application import BMLibrarianApplication
from bmlibrarian.gui.qt.core.config_manager import GUIConfigManager

# Import the research plugin
from bmlibrarian.gui.qt.plugins.research.plugin import create_plugin

def main():
    """Main entry point."""
    # Create application
    app_instance = BMLibrarianApplication()

    # Load configuration
    config_manager = GUIConfigManager()

    # Create and add research plugin
    research_plugin = create_plugin()
    research_widget = research_plugin.create_widget()

    app_instance.main_window.add_tab(
        research_widget,
        research_plugin.get_metadata().display_name
    )

    # Run application
    sys.exit(app_instance.run())

if __name__ == "__main__":
    main()
```

Make it executable:

```bash
chmod +x bmlibrarian_qt.py
```

## Step 6: Test Your First PySide6 GUI (3 minutes)

```bash
# Launch the Qt GUI
uv run python bmlibrarian_qt.py
```

You should see:
- A window titled "BMLibrarian - Biomedical Literature Research (Qt)"
- A single "Research" tab
- A welcome message, a button, and a status label
- Clicking the button updates the status

**Congratulations!** You now have a working PySide6 GUI with a plugin architecture.

## Next Steps

Now that you have the foundation working, you can:

### 1. Implement Plugin Manager (30 minutes)

Add automatic plugin discovery and loading:

- Create `src/bmlibrarian/gui/qt/core/plugin_manager.py` (see full migration plan)
- Create `src/bmlibrarian/gui/qt/core/tab_registry.py`
- Update main window to use PluginManager

### 2. Add Event Bus (20 minutes)

Enable inter-tab communication:

- Create `src/bmlibrarian/gui/qt/core/event_bus.py`
- Connect plugins to event bus
- Test communication between plugins

### 3. Migrate Real Functionality (2-4 hours per plugin)

Start migrating actual features:

#### Research Tab:
- Question input field
- Workflow step indicators
- Agent integration
- Report preview

#### Configuration Tab:
- Agent settings
- Database configuration
- Model selection

#### Search Tab:
- Search interface
- Results display
- Export functionality

### 4. Add Threading Support (1 hour)

Enable async operations:

- Create `src/bmlibrarian/gui/qt/utils/threading.py`
- Implement WorkerSignals and QRunnable patterns
- Test with long-running agent operations

## Common Commands

```bash
# Launch Qt GUI
uv run python bmlibrarian_qt.py

# Launch legacy Flet GUI
uv run python bmlibrarian_research_gui.py

# Run tests (when you add them)
uv run python -m pytest tests/gui/qt/

# Check for memory leaks (install memory_profiler)
uv run python -m memory_profiler bmlibrarian_qt.py
```

## Troubleshooting

### Qt Platform Plugin Error

**Error**: `qt.qpa.plugin: Could not find the Qt platform plugin`

**Solution**: Install Qt platform dependencies:
```bash
# Ubuntu/Debian
sudo apt-get install libxcb-xinerama0 libxcb-cursor0

# macOS - usually works out of the box

# Windows - usually works out of the box
```

### Import Errors

**Error**: `ModuleNotFoundError: No module named 'PySide6'`

**Solution**: Ensure dependencies are installed:
```bash
uv sync
```

### Window Not Showing

**Error**: Window opens and immediately closes

**Solution**: Check for exceptions in console. Ensure you're using `sys.exit(app.exec())` not just `app.exec()`.

### Plugin Not Loading

**Error**: Plugin not appearing in tabs

**Solution**:
1. Verify `create_plugin()` function exists in `plugin.py`
2. Check plugin is in `enabled_plugins` list
3. Look for errors in console during plugin loading

## Development Workflow

1. **Create Feature Branch**:
   ```bash
   git checkout -b pyside6-migration-phase1
   ```

2. **Implement Changes**: Follow the migration plan phases

3. **Test Frequently**: Run the GUI after each change

4. **Commit Incrementally**: Small, focused commits

5. **Document**: Update documentation as you go

## Resources

- **PySide6 Documentation**: https://doc.qt.io/qtforpython-6/
- **Qt Widgets**: https://doc.qt.io/qt-6/qtwidgets-index.html
- **Qt Designer**: Use for rapid UI prototyping
- **Full Migration Plan**: `PYSIDE6_MIGRATION_PLAN.md`
- **Plugin Architecture Guide**: `PYSIDE6_PLUGIN_ARCHITECTURE.md`

## Getting Help

- Check the migration plan for detailed architecture
- Review plugin architecture guide for advanced patterns
- Consult Qt documentation for widget-specific questions
- Test with minimal examples when debugging

## Success Criteria for Phase 1

By the end of your first day, you should have:

- ✅ PySide6 installed and working
- ✅ Directory structure created
- ✅ Core framework implemented (minimal)
- ✅ At least one working plugin (Hello World level)
- ✅ Application launches without errors
- ✅ Tab switching works
- ✅ Status bar updates

You're now ready to start migrating real functionality!

## Daily Development Checklist

Each day, before starting work:

- [ ] Pull latest changes from main branch
- [ ] Run `uv sync` to update dependencies
- [ ] Test that GUI still launches
- [ ] Review TODO list in migration plan

Each day, before committing:

- [ ] Test all modified plugins
- [ ] Check for console errors/warnings
- [ ] Verify no memory leaks (basic check)
- [ ] Update documentation if needed
- [ ] Run any existing tests

Happy coding! 🚀
