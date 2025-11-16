# PySide6 Migration Plan for BMLibrarian GUI

## Executive Summary

This document outlines the comprehensive migration strategy for transitioning BMLibrarian's GUI applications from Flet to PySide6, implementing a modern plugin-based tab architecture that allows for dynamic configuration and extensibility.

## Migration Rationale

### Limitations of Flet
- Performance issues with large data sets
- Limited customization capabilities
- File picker bugs (especially on macOS)
- Immature ecosystem and limited third-party components
- Threading/async limitations with complex workflows
- Limited native platform integration

### Benefits of PySide6
- Mature, battle-tested Qt framework
- Native platform integration and performance
- Rich ecosystem of widgets and extensions
- Better threading/async support
- Comprehensive documentation and community
- Professional-grade UI capabilities
- Plugin architecture support

## Architecture Overview

### Directory Structure

```
src/bmlibrarian/
├── gui/                          # Legacy Flet GUI (maintenance mode)
│   ├── __init__.py
│   ├── research_app.py           # Legacy research GUI
│   ├── config_app.py             # Legacy config GUI
│   └── ...                       # All existing Flet components
│
├── gui/qt/                       # New PySide6 GUI (active development)
│   ├── __init__.py
│   ├── core/                     # Core framework components
│   │   ├── __init__.py
│   │   ├── application.py        # Main QApplication wrapper
│   │   ├── main_window.py        # Base tabbed main window
│   │   ├── plugin_manager.py    # Plugin loading and management
│   │   ├── tab_registry.py      # Tab plugin registration system
│   │   ├── config_manager.py    # GUI configuration (which tabs to show)
│   │   └── event_bus.py         # Inter-tab communication system
│   │
│   ├── plugins/                  # Tab plugins
│   │   ├── __init__.py
│   │   ├── base_tab.py          # Abstract base class for all tab plugins
│   │   ├── research/            # Research workflow tab plugin
│   │   │   ├── __init__.py
│   │   │   ├── plugin.py        # Plugin entry point
│   │   │   ├── research_tab.py  # Main research tab widget
│   │   │   ├── workflow_widget.py
│   │   │   ├── document_list.py
│   │   │   ├── citation_viewer.py
│   │   │   └── report_preview.py
│   │   │
│   │   ├── configuration/       # Settings/config tab plugin
│   │   │   ├── __init__.py
│   │   │   ├── plugin.py
│   │   │   ├── config_tab.py
│   │   │   ├── agent_config_widget.py
│   │   │   ├── ollama_settings.py
│   │   │   └── database_settings.py
│   │   │
│   │   ├── fact_checker/        # Fact-checker review tab plugin
│   │   │   ├── __init__.py
│   │   │   ├── plugin.py
│   │   │   ├── review_tab.py
│   │   │   ├── statement_widget.py
│   │   │   ├── annotation_widget.py
│   │   │   └── citation_cards.py
│   │   │
│   │   ├── query_lab/           # Query laboratory tab plugin
│   │   │   ├── __init__.py
│   │   │   ├── plugin.py
│   │   │   ├── query_lab_tab.py
│   │   │   └── sql_editor.py
│   │   │
│   │   └── search/              # Document search tab plugin
│   │       ├── __init__.py
│   │       ├── plugin.py
│   │       ├── search_tab.py
│   │       └── result_viewer.py
│   │
│   ├── widgets/                 # Reusable custom widgets
│   │   ├── __init__.py
│   │   ├── document_card.py     # Document display card
│   │   ├── citation_card.py     # Citation display card
│   │   ├── markdown_viewer.py   # Markdown rendering widget
│   │   ├── progress_widget.py   # Progress indicators
│   │   ├── step_indicator.py    # Workflow step indicator
│   │   └── pdf_viewer.py        # PDF preview widget
│   │
│   ├── dialogs/                 # Dialog windows
│   │   ├── __init__.py
│   │   ├── settings_dialog.py
│   │   ├── about_dialog.py
│   │   ├── export_dialog.py
│   │   └── login_dialog.py
│   │
│   ├── utils/                   # GUI utilities
│   │   ├── __init__.py
│   │   ├── threading.py         # Thread management for async operations
│   │   ├── formatting.py        # Text and data formatting
│   │   ├── icons.py             # Icon management
│   │   └── validators.py        # Input validation
│   │
│   └── resources/               # Resources (icons, stylesheets, etc.)
│       ├── icons/
│       ├── styles/
│       │   ├── default.qss      # Default Qt stylesheet
│       │   └── dark.qss         # Dark theme stylesheet
│       └── resources.qrc        # Qt resource file
│
└── factchecker/
    └── gui/                     # Legacy Flet fact-checker GUI (maintenance mode)
        └── ...
```

### Plugin Configuration File

Location: `~/.bmlibrarian/gui_config.json`

```json
{
  "gui": {
    "theme": "default",
    "window": {
      "width": 1400,
      "height": 900,
      "remember_geometry": true
    },
    "tabs": {
      "enabled_plugins": [
        "research",
        "search",
        "fact_checker",
        "configuration",
        "query_lab"
      ],
      "tab_order": [
        "research",
        "search",
        "fact_checker",
        "query_lab",
        "configuration"
      ],
      "default_tab": "research"
    },
    "research_tab": {
      "show_workflow_steps": true,
      "auto_scroll_to_active": true,
      "max_documents_display": 100
    },
    "fact_checker_tab": {
      "auto_save": true,
      "show_confidence_timer": true
    }
  }
}
```

## Plugin Architecture Design

### Base Tab Plugin Interface

```python
# src/bmlibrarian/gui/qt/plugins/base_tab.py

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal, QObject

class TabPluginMetadata:
    """Metadata for a tab plugin."""
    def __init__(
        self,
        plugin_id: str,
        display_name: str,
        description: str,
        version: str,
        icon: Optional[str] = None,
        requires: Optional[list[str]] = None
    ):
        self.plugin_id = plugin_id
        self.display_name = display_name
        self.description = description
        self.version = version
        self.icon = icon
        self.requires = requires or []

class BaseTabPlugin(ABC):
    """Abstract base class for all tab plugins."""

    # Signals for inter-tab communication
    request_navigation = Signal(str)  # Navigate to another tab
    status_changed = Signal(str)      # Update status bar
    data_updated = Signal(dict)       # Share data with other tabs

    @abstractmethod
    def get_metadata(self) -> TabPluginMetadata:
        """Return plugin metadata."""
        pass

    @abstractmethod
    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """Create and return the main widget for this tab."""
        pass

    @abstractmethod
    def on_tab_activated(self):
        """Called when this tab becomes active."""
        pass

    @abstractmethod
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

### Plugin Manager

```python
# src/bmlibrarian/gui/qt/core/plugin_manager.py

from typing import Dict, List, Optional
from pathlib import Path
import importlib
import importlib.util
from .tab_registry import TabRegistry
from ..plugins.base_tab import BaseTabPlugin, TabPluginMetadata

class PluginManager:
    """Manages loading, registration, and lifecycle of tab plugins."""

    def __init__(self, registry: TabRegistry):
        self.registry = registry
        self.loaded_plugins: Dict[str, BaseTabPlugin] = {}
        self.plugin_path = Path(__file__).parent.parent / "plugins"

    def discover_plugins(self) -> List[str]:
        """Discover available plugins in the plugins directory."""
        discovered = []
        for plugin_dir in self.plugin_path.iterdir():
            if plugin_dir.is_dir() and (plugin_dir / "plugin.py").exists():
                discovered.append(plugin_dir.name)
        return discovered

    def load_plugin(self, plugin_id: str) -> Optional[BaseTabPlugin]:
        """Load a plugin by ID."""
        if plugin_id in self.loaded_plugins:
            return self.loaded_plugins[plugin_id]

        plugin_file = self.plugin_path / plugin_id / "plugin.py"
        if not plugin_file.exists():
            raise ValueError(f"Plugin '{plugin_id}' not found")

        # Dynamic import
        spec = importlib.util.spec_from_file_location(
            f"bmlibrarian.gui.qt.plugins.{plugin_id}.plugin",
            plugin_file
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Instantiate plugin
        if not hasattr(module, "create_plugin"):
            raise ValueError(f"Plugin '{plugin_id}' missing create_plugin() function")

        plugin = module.create_plugin()
        if not isinstance(plugin, BaseTabPlugin):
            raise ValueError(f"Plugin '{plugin_id}' does not implement BaseTabPlugin")

        self.loaded_plugins[plugin_id] = plugin
        self.registry.register(plugin)

        return plugin

    def load_enabled_plugins(self, enabled_list: List[str]) -> Dict[str, BaseTabPlugin]:
        """Load all enabled plugins from configuration."""
        loaded = {}
        for plugin_id in enabled_list:
            try:
                plugin = self.load_plugin(plugin_id)
                loaded[plugin_id] = plugin
            except Exception as e:
                print(f"Failed to load plugin '{plugin_id}': {e}")
        return loaded

    def unload_plugin(self, plugin_id: str):
        """Unload a plugin and cleanup resources."""
        if plugin_id in self.loaded_plugins:
            plugin = self.loaded_plugins[plugin_id]
            plugin.cleanup()
            self.registry.unregister(plugin_id)
            del self.loaded_plugins[plugin_id]
```

### Main Application Window

```python
# src/bmlibrarian/gui/qt/core/main_window.py

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QStatusBar, QMenuBar, QMenu
)
from PySide6.QtCore import Qt, Slot
from typing import Dict
from .plugin_manager import PluginManager
from .tab_registry import TabRegistry
from .config_manager import GUIConfigManager
from ..plugins.base_tab import BaseTabPlugin

class BMLibrarianMainWindow(QMainWindow):
    """Main application window with plugin-based tabs."""

    def __init__(self):
        super().__init__()
        self.config_manager = GUIConfigManager()
        self.tab_registry = TabRegistry()
        self.plugin_manager = PluginManager(self.tab_registry)

        self.tabs: Dict[str, QWidget] = {}

        self._setup_ui()
        self._load_plugins()
        self._create_menu_bar()
        self._restore_geometry()

    def _setup_ui(self):
        """Setup the main window UI."""
        self.setWindowTitle("BMLibrarian - Biomedical Literature Research")

        # Create central widget with tab container
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(False)
        self.tab_widget.setMovable(True)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self.tab_widget)

        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _load_plugins(self):
        """Load enabled plugins and create tabs."""
        config = self.config_manager.get_config()
        enabled_plugins = config.get("tabs", {}).get("enabled_plugins", [])
        tab_order = config.get("tabs", {}).get("tab_order", enabled_plugins)

        # Load all enabled plugins
        loaded_plugins = self.plugin_manager.load_enabled_plugins(enabled_plugins)

        # Create tabs in specified order
        for plugin_id in tab_order:
            if plugin_id in loaded_plugins:
                self._add_plugin_tab(loaded_plugins[plugin_id])

        # Set default tab
        default_tab = config.get("tabs", {}).get("default_tab", None)
        if default_tab and default_tab in self.tabs:
            index = list(self.tabs.keys()).index(default_tab)
            self.tab_widget.setCurrentIndex(index)

    def _add_plugin_tab(self, plugin: BaseTabPlugin):
        """Add a tab from a plugin."""
        metadata = plugin.get_metadata()
        widget = plugin.create_widget(self)

        # Connect plugin signals
        plugin.status_changed.connect(self._on_plugin_status_changed)
        plugin.request_navigation.connect(self._navigate_to_tab)

        # Add tab
        index = self.tab_widget.addTab(widget, metadata.display_name)
        if metadata.icon:
            # TODO: Set tab icon
            pass

        self.tabs[metadata.plugin_id] = widget

    @Slot(int)
    def _on_tab_changed(self, index: int):
        """Handle tab change events."""
        if index < 0:
            return

        # Notify plugins
        plugin_id = list(self.tabs.keys())[index]
        plugin = self.plugin_manager.loaded_plugins.get(plugin_id)
        if plugin:
            # Deactivate previous tab
            for pid, p in self.plugin_manager.loaded_plugins.items():
                if pid != plugin_id:
                    p.on_tab_deactivated()

            # Activate current tab
            plugin.on_tab_activated()

    @Slot(str)
    def _navigate_to_tab(self, plugin_id: str):
        """Navigate to a specific tab by plugin ID."""
        if plugin_id in self.tabs:
            index = list(self.tabs.keys()).index(plugin_id)
            self.tab_widget.setCurrentIndex(index)

    @Slot(str)
    def _on_plugin_status_changed(self, message: str):
        """Update status bar with plugin messages."""
        self.status_bar.showMessage(message, 5000)

    def _create_menu_bar(self):
        """Create the application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction("&Exit", self.close)

        # View menu
        view_menu = menubar.addMenu("&View")
        view_menu.addAction("&Configure Tabs...", self._show_tab_configuration)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction("&About", self._show_about)

    def _restore_geometry(self):
        """Restore window geometry from config."""
        config = self.config_manager.get_config()
        window_config = config.get("window", {})

        width = window_config.get("width", 1400)
        height = window_config.get("height", 900)
        self.resize(width, height)

        # TODO: Restore position if remember_geometry is True

    def _show_tab_configuration(self):
        """Show tab configuration dialog."""
        # TODO: Implement tab configuration dialog
        pass

    def _show_about(self):
        """Show about dialog."""
        # TODO: Implement about dialog
        pass

    def closeEvent(self, event):
        """Handle window close event."""
        # Save geometry
        config = self.config_manager.get_config()
        if config.get("window", {}).get("remember_geometry", True):
            config.setdefault("window", {})["width"] = self.width()
            config.setdefault("window", {})["height"] = self.height()
            self.config_manager.save_config(config)

        # Cleanup plugins
        for plugin in self.plugin_manager.loaded_plugins.values():
            plugin.cleanup()

        event.accept()
```

## Migration Phases

### Phase 1: Foundation (Weeks 1-2)
**Goal**: Establish PySide6 infrastructure and plugin architecture

**Tasks**:
1. Add PySide6 to dependencies in `pyproject.toml`
2. Create `gui/qt/` directory structure
3. Implement core framework:
   - `application.py` - QApplication wrapper
   - `main_window.py` - Main tabbed window
   - `plugin_manager.py` - Plugin loading system
   - `tab_registry.py` - Tab registration
   - `config_manager.py` - GUI configuration
   - `event_bus.py` - Inter-tab communication
4. Implement `BaseTabPlugin` abstract class
5. Create basic GUI configuration file structure
6. Setup resource system (icons, stylesheets)
7. Create entry point script: `bmlibrarian_qt.py`

**Deliverables**:
- Working PySide6 application skeleton
- Plugin system functional
- Configuration loading/saving
- Basic styling with default theme

**Testing**:
- Launch empty application with no tabs
- Load/save GUI configuration
- Verify plugin discovery mechanism

### Phase 2: Research Tab Plugin (Weeks 3-4)
**Goal**: Migrate primary research workflow interface

**Tasks**:
1. Create `plugins/research/` structure
2. Implement research plugin entry point
3. Migrate core research UI components:
   - Question input field
   - Workflow step indicators (collapsible)
   - Progress tracking widgets
   - Document list view
   - Citation viewer
   - Report preview with markdown rendering
4. Implement async workflow execution with threading
5. Connect to existing agent orchestrator
6. Implement export functionality

**Deliverables**:
- Fully functional research tab plugin
- Feature parity with Flet research GUI
- Better performance with large document sets

**Testing**:
- Complete research workflow end-to-end
- Test with 100+ documents
- Verify all agent integrations
- Test report export functionality

### Phase 3: Configuration Tab Plugin (Weeks 5-6)
**Goal**: Migrate settings and configuration interface

**Tasks**:
1. Create `plugins/configuration/` structure
2. Implement configuration plugin
3. Migrate configuration UI components:
   - Agent settings (model selection, parameters)
   - Ollama server configuration
   - Database settings
   - CLI defaults
   - Multi-model query generation settings
4. Implement model refresh from Ollama
5. Implement save/load configuration
6. Add connection testing functionality

**Deliverables**:
- Fully functional configuration tab plugin
- Feature parity with Flet config GUI
- Enhanced UI with better validation

**Testing**:
- Test all configuration options
- Verify Ollama connection testing
- Test save/load to various file locations
- Verify agent configuration updates

### Phase 4: Fact-Checker Review Tab Plugin (Weeks 7-8)
**Goal**: Migrate fact-checker review interface

**Tasks**:
1. Create `plugins/fact_checker/` structure
2. Implement fact-checker plugin
3. Migrate review UI components:
   - Statement display
   - Annotation widgets (yes/no/maybe)
   - Citation cards with expandable abstracts
   - Confidence timer component
   - Navigation controls
4. Implement database integration (PostgreSQL and SQLite)
5. Add export functionality for annotations

**Deliverables**:
- Fully functional fact-checker review tab plugin
- Support for both PostgreSQL and SQLite backends
- Feature parity with Flet review GUI
- Better performance with large datasets

**Testing**:
- Test with PostgreSQL backend
- Test with SQLite review packages
- Verify annotation persistence
- Test multi-user scenarios
- Test export functionality

### Phase 5: Additional Tab Plugins (Weeks 9-10)
**Goal**: Implement remaining specialized interfaces

**Tasks**:
1. **Query Lab Plugin**:
   - SQL editor with syntax highlighting
   - Query execution and results display
   - Query history
2. **Search Plugin**:
   - Advanced document search interface
   - Filter options
   - Results visualization
3. **Reusable Widgets**:
   - Document card widget (used across multiple tabs)
   - Citation card widget
   - Markdown viewer with GitHub-flavored markdown
   - PDF viewer integration
   - Progress indicators

**Deliverables**:
- Query lab tab plugin
- Search tab plugin
- Reusable widget library
- Enhanced functionality over Flet versions

**Testing**:
- Test query lab with various SQL queries
- Test search functionality
- Verify widget reusability across tabs

### Phase 6: Polish and Documentation (Weeks 11-12)
**Goal**: Finalize migration with documentation and quality improvements

**Tasks**:
1. Implement dark theme stylesheet
2. Add keyboard shortcuts
3. Improve accessibility
4. Performance optimization
5. Memory leak testing
6. Create comprehensive documentation:
   - Plugin development guide
   - User guide for Qt GUI
   - Migration notes for users
   - API documentation
7. Create example plugin template
8. Setup automated testing for GUI components

**Deliverables**:
- Production-ready PySide6 GUI
- Complete documentation
- Plugin development guide
- Test coverage >80%

**Testing**:
- Full regression testing
- Performance benchmarking vs Flet
- Memory profiling
- Cross-platform testing (Linux, macOS, Windows)

## Legacy Flet Support Strategy

### Maintenance Mode
- Keep all existing Flet code in `src/bmlibrarian/gui/`
- No new features, only critical bug fixes
- Mark as deprecated in documentation
- Provide migration notice to users

### Deprecation Timeline
- **Months 1-3**: Both GUIs available, PySide6 is "beta"
- **Months 4-6**: PySide6 is default, Flet is "legacy"
- **Month 7+**: Consider removing Flet entirely (based on user feedback)

### Entry Points
```python
# bmlibrarian_qt.py (new)
from bmlibrarian.gui.qt import main
if __name__ == "__main__":
    main()

# bmlibrarian_research_gui.py (legacy - add deprecation warning)
import warnings
warnings.warn(
    "The Flet-based GUI is deprecated. Please use bmlibrarian_qt.py instead.",
    DeprecationWarning
)
from bmlibrarian.gui import ResearchGUI
# ... existing code
```

## Dependencies Update

Add to `pyproject.toml`:
```toml
dependencies = [
    # ... existing dependencies
    "PySide6>=6.6.0",          # Qt for Python bindings
    "PySide6-Addons>=6.6.0",   # Additional Qt modules
    "Markdown>=3.5.0",         # Markdown rendering
    "Pygments>=2.17.0",        # Syntax highlighting
    "qtawesome>=1.3.0",        # Icon fonts for Qt
]
```

## Development Guidelines

### Plugin Development Best Practices
1. **Separation of Concerns**: Keep UI logic separate from business logic
2. **Signal-Based Communication**: Use Qt signals for inter-tab communication
3. **Thread Safety**: All agent operations must run in background threads
4. **Resource Management**: Properly cleanup resources in `cleanup()`
5. **Configuration**: Store plugin-specific config under plugin_id key
6. **Testing**: Each plugin should have unit tests

### Code Organization
- One plugin per directory
- Main widget in `{plugin_name}_tab.py`
- Reusable widgets in `gui/qt/widgets/`
- Shared utilities in `gui/qt/utils/`
- Keep plugins independent (no cross-plugin imports except base classes)

### UI/UX Standards
- Follow Qt design guidelines
- Use Qt layouts (QVBoxLayout, QHBoxLayout, QGridLayout) - never fixed positioning
- Implement responsive design
- Support keyboard navigation
- Provide tooltips for all interactive elements
- Use icons consistently

## Testing Strategy

### Unit Tests
- Test each plugin's business logic independently
- Mock Qt widgets for faster testing
- Test plugin loading/unloading
- Test configuration management

### Integration Tests
- Test inter-tab communication
- Test workflow execution
- Test database integration
- Test agent orchestration

### UI Tests
- Manual testing checklist for each tab
- Automated GUI testing with `pytest-qt`
- Performance testing with large datasets
- Memory leak detection

### Cross-Platform Testing
- Linux (primary development platform)
- macOS
- Windows

## Documentation Requirements

### User Documentation
1. **Installation Guide**: Installing PySide6 version
2. **User Guide**: Using the new Qt GUI
3. **Migration Guide**: Transitioning from Flet to Qt
4. **Plugin Configuration**: Enabling/disabling tabs

### Developer Documentation
1. **Plugin Development Guide**: Creating new tab plugins
2. **Architecture Overview**: System design and patterns
3. **API Reference**: Plugin interfaces and utilities
4. **Contributing Guide**: How to contribute new plugins

### Example Plugin
Create a template plugin in `plugins/example/` with:
- Complete plugin structure
- Commented code explaining each component
- README with step-by-step guide

## Risk Mitigation

### Technical Risks
1. **Risk**: PySide6 learning curve
   - **Mitigation**: Start with simple plugins, extensive documentation

2. **Risk**: Threading complexity with Qt
   - **Mitigation**: Use QThreadPool, QRunnable patterns, comprehensive examples

3. **Risk**: Plugin compatibility issues
   - **Mitigation**: Strong plugin interface contract, version checking

### Project Risks
1. **Risk**: Migration takes longer than planned
   - **Mitigation**: Phased approach, maintain Flet GUI during transition

2. **Risk**: User resistance to new GUI
   - **Mitigation**: Feature parity first, then enhancements; clear migration path

3. **Risk**: Performance issues
   - **Mitigation**: Performance testing at each phase, profiling tools

## Success Metrics

1. **Performance**: 50% faster workflow execution vs Flet
2. **Memory**: 30% lower memory usage with 100+ documents
3. **Stability**: Zero crashes in standard workflows
4. **Test Coverage**: >80% for all Qt GUI code
5. **Documentation**: Complete plugin development guide
6. **User Satisfaction**: Positive feedback from beta testers

## Future Enhancements (Post-Migration)

Once migration is complete, PySide6 enables:

1. **Advanced Visualizations**:
   - Citation network graphs
   - Document clustering visualizations
   - Timeline views of research

2. **Enhanced PDF Integration**:
   - Built-in PDF viewer with annotation
   - Highlight citations in original PDFs

3. **Database Browser**:
   - Visual database exploration
   - Schema viewer
   - Query builder

4. **Multi-Window Support**:
   - Detachable tabs
   - Multiple research sessions

5. **Advanced Export**:
   - Rich PDF reports
   - PowerPoint presentations
   - Excel spreadsheets

6. **Collaboration Features**:
   - Share research sessions
   - Collaborative annotations

## Conclusion

This migration to PySide6 with a plugin-based architecture will:
- Overcome Flet limitations
- Provide a more robust, performant GUI
- Enable extensibility through plugins
- Support future enhancements
- Maintain professional-grade user experience

The phased approach ensures minimal disruption while delivering incremental value. The plugin architecture future-proofs the application by making it easy to add new functionality without modifying core code.

## Appendix A: Plugin Example Template

```python
# src/bmlibrarian/gui/qt/plugins/example/plugin.py

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from ..base_tab import BaseTabPlugin, TabPluginMetadata

class ExamplePlugin(BaseTabPlugin):
    """Example tab plugin demonstrating the plugin interface."""

    def get_metadata(self) -> TabPluginMetadata:
        return TabPluginMetadata(
            plugin_id="example",
            display_name="Example Tab",
            description="Demonstrates plugin architecture",
            version="1.0.0",
            icon="example.png"
        )

    def create_widget(self, parent=None) -> QWidget:
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)

        label = QLabel("Example Plugin Content")
        layout.addWidget(label)

        return widget

    def on_tab_activated(self):
        self.status_changed.emit("Example tab activated")

    def on_tab_deactivated(self):
        pass

def create_plugin() -> BaseTabPlugin:
    """Plugin entry point."""
    return ExamplePlugin()
```

## Appendix B: Configuration Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "gui": {
      "type": "object",
      "properties": {
        "theme": {
          "type": "string",
          "enum": ["default", "dark"],
          "default": "default"
        },
        "window": {
          "type": "object",
          "properties": {
            "width": {"type": "integer", "minimum": 800},
            "height": {"type": "integer", "minimum": 600},
            "remember_geometry": {"type": "boolean", "default": true}
          }
        },
        "tabs": {
          "type": "object",
          "properties": {
            "enabled_plugins": {
              "type": "array",
              "items": {"type": "string"}
            },
            "tab_order": {
              "type": "array",
              "items": {"type": "string"}
            },
            "default_tab": {"type": "string"}
          }
        }
      }
    }
  }
}
```

## Appendix C: Implementation Checklist

- [ ] Phase 1: Foundation
  - [ ] Add PySide6 dependencies
  - [ ] Create directory structure
  - [ ] Implement core framework
  - [ ] Setup resource system
  - [ ] Create entry point
  - [ ] Basic testing

- [ ] Phase 2: Research Tab
  - [ ] Plugin structure
  - [ ] UI components
  - [ ] Workflow integration
  - [ ] Testing

- [ ] Phase 3: Configuration Tab
  - [ ] Plugin structure
  - [ ] Settings UI
  - [ ] Configuration I/O
  - [ ] Testing

- [ ] Phase 4: Fact-Checker Tab
  - [ ] Plugin structure
  - [ ] Review UI
  - [ ] Database integration
  - [ ] Testing

- [ ] Phase 5: Additional Plugins
  - [ ] Query Lab plugin
  - [ ] Search plugin
  - [ ] Reusable widgets
  - [ ] Testing

- [ ] Phase 6: Polish
  - [ ] Theming
  - [ ] Documentation
  - [ ] Performance optimization
  - [ ] Release preparation
