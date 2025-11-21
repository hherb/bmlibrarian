# GUI Architecture Documentation

## Overview

BMLibrarian features a modern Qt-based desktop application built with PySide6 (Qt for Python). The GUI uses a **plugin-based architecture** where each major feature is implemented as a separate plugin tab, providing modularity, extensibility, and native performance across platforms.

## Architecture Status

### Current: Qt GUI (PySide6)
- **Entry Point**: `bmlibrarian_qt.py`
- **Framework**: PySide6 (Qt 6.x for Python)
- **Architecture**: Plugin-based tabbed interface
- **Status**: **Active development**, all new features

### Legacy: Flet GUI (Deprecated)
- **Entry Points**: `bmlibrarian_research_gui.py`, `bmlibrarian_config_gui.py`
- **Framework**: Flet (web-based framework)
- **Status**: **Deprecated**, maintenance mode only, will be removed in future versions
- **Migration**: See `doc/users/flet_to_qt_migration_guide.md`

## Architecture Principles

### 1. Plugin-Based Design
- **Modular plugins**: Each tab is a self-contained plugin
- **Hot-reloadable**: Plugins can be reloaded without restarting the app
- **Independent development**: Plugins developed and tested independently
- **Easy extension**: New tabs added by creating new plugin classes

### 2. Native Performance
- **Qt framework**: Battle-tested, mature GUI framework
- **Native widgets**: Platform-native look and feel
- **Efficient rendering**: No web overhead, direct GPU rendering
- **Thread management**: QThread for background operations

### 3. Theme System
- **Light and dark themes**: Professional color schemes
- **QSS stylesheets**: CSS-like styling with Qt extensions
- **Dynamic switching**: Theme changes applied at runtime
- **Consistent styling**: All plugins inherit theme automatically

### 4. Signal/Slot Architecture
- **Loose coupling**: Components communicate via signals
- **Type-safe**: Qt's signal/slot system with type checking
- **Thread-safe**: Cross-thread communication built-in
- **Event-driven**: Responsive UI with async operations

## Directory Structure

```
src/bmlibrarian/gui/qt/
├── __init__.py                      # Main entry point and app initialization
├── core/                            # Core application framework
│   ├── __init__.py
│   ├── main_window.py               # Main application window
│   ├── plugin_manager.py            # Plugin discovery and loading
│   ├── config_manager.py            # Configuration management
│   ├── theme_manager.py             # Theme switching and stylesheet management
│   └── status_bar.py                # Status bar with messages
├── plugins/                         # Plugin-based tab system
│   ├── __init__.py
│   ├── base_tab.py                  # Abstract base class for all plugins
│   ├── research/                    # Research workflow plugin (modular architecture)
│   │   ├── __init__.py              # Module exports
│   │   ├── plugin.py                # Plugin entry point and registration
│   │   ├── research_tab.py          # Main tab widget and UI orchestration
│   │   ├── constants.py             # UI constants, colors, and stylesheet generators
│   │   ├── tab_builders.py          # Tab construction and UI building functions
│   │   ├── tab_updaters.py          # Tab state update handlers
│   │   ├── workflow_executor.py     # Qt workflow executor (agents, scoring, reports)
│   │   ├── workflow_handlers.py     # Workflow event handlers and signal connections
│   │   ├── workflow_thread.py       # QThread-based background workflow execution
│   │   └── export_utils.py          # Report export functionality
│   ├── search/                      # Document search plugin
│   │   ├── __init__.py
│   │   ├── plugin.py
│   │   ├── search_tab.py            # Main search interface
│   │   ├── filter_widget.py         # Search filters
│   │   └── results_widget.py        # Search results display
│   ├── fact_checker/                # Fact-checking review plugin
│   │   ├── __init__.py
│   │   ├── plugin.py
│   │   ├── fact_checker_tab.py      # Main review interface
│   │   ├── statement_widget.py      # Statement display
│   │   └── annotation_widget.py     # Annotation controls
│   ├── query_lab/                   # Query testing lab plugin
│   │   ├── __init__.py
│   │   ├── plugin.py
│   │   └── query_lab_tab.py         # Query testing interface
│   ├── configuration/               # Settings plugin
│   │   ├── __init__.py
│   │   ├── plugin.py
│   │   ├── configuration_tab.py     # Main settings interface
│   │   ├── agent_config_widget.py   # Agent configuration
│   │   └── general_settings_widget.py # General settings
│   ├── pico_lab/                    # PICO extraction lab
│   ├── prisma2020_lab/              # PRISMA 2020 assessment lab
│   ├── study_assessment/            # Study quality assessment
│   ├── document_interrogation/      # Document Q&A interface
│   ├── settings/                    # Advanced settings
│   ├── plugins_manager/             # Plugin management UI
│   └── example/                     # Example plugin for developers
├── widgets/                         # Reusable Qt widgets
│   ├── __init__.py
│   ├── document_card.py             # Document display card
│   ├── citation_card.py             # Citation display card
│   ├── score_badge.py               # Relevance score badge
│   ├── progress_bar.py              # Custom progress bars
│   ├── collapsible_section.py       # Expandable/collapsible sections
│   ├── markdown_viewer.py           # Markdown rendering widget
│   └── text_highlighter.py          # Syntax highlighting
├── dialogs/                         # Dialog windows
│   ├── __init__.py
│   ├── about_dialog.py              # About BMLibrarian dialog
│   ├── settings_dialog.py           # Quick settings dialog
│   ├── export_dialog.py             # Export options dialog
│   └── error_dialog.py              # Error message display
├── resources/                       # Resources (styles, icons, themes)
│   ├── styles/                      # QSS stylesheets
│   │   ├── default.qss              # Light theme stylesheet
│   │   └── dark.qss                 # Dark theme stylesheet
│   ├── icons/                       # Application icons
│   │   ├── app_icon.png
│   │   ├── tab_icons/               # Tab-specific icons
│   │   └── action_icons/            # Action button icons
│   └── themes/                      # Theme configuration files
│       ├── light_theme.json
│       └── dark_theme.json
├── utils/                           # Utility modules
│   ├── __init__.py
│   ├── qt_helpers.py                # Qt convenience functions
│   ├── async_worker.py              # QThread worker base class
│   ├── signal_bus.py                # Application-wide signal bus
│   └── resource_loader.py           # Resource file loading
├── qt_document_card_factory.py      # Document card factory for Qt
└── tabs/                            # Legacy tab components (deprecated)
```

## Core Components

### Main Window (`core/main_window.py`)

The main application window coordinates all GUI components.

**Key Features**:
- Menu bar with File, View, Tools, Help menus
- Tab bar for plugin tabs
- Central widget area for active tab
- Status bar for messages and notifications
- Keyboard shortcut management
- Window geometry persistence

**Architecture**:
```python
class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.plugin_manager = PluginManager()
        self.theme_manager = ThemeManager()
        self.config_manager = ConfigManager()

    def setup_ui(self):
        """Initialize UI components."""
        self._create_menu_bar()
        self._create_tab_widget()
        self._create_status_bar()
        self._setup_shortcuts()

    def load_plugins(self):
        """Discover and load all enabled plugins."""
        plugins = self.plugin_manager.discover_plugins()
        for plugin in plugins:
            if plugin.is_enabled():
                tab_widget = plugin.create_tab()
                self.tab_widget.addTab(tab_widget, plugin.tab_icon(), plugin.tab_name())
```

### Plugin Manager (`core/plugin_manager.py`)

Discovers, loads, and manages plugins dynamically.

**Key Features**:
- Plugin discovery from `plugins/` directory
- Dependency checking and validation
- Plugin enable/disable management
- Hot-reloading support
- Error handling and recovery

**Plugin Lifecycle**:
```python
class PluginManager:
    """Manages plugin discovery and lifecycle."""

    def discover_plugins(self) -> List[BaseTab]:
        """Scan plugins directory and load enabled plugins."""

    def load_plugin(self, plugin_id: str) -> Optional[BaseTab]:
        """Load a specific plugin by ID."""

    def reload_plugin(self, plugin_id: str):
        """Reload a plugin (for development)."""

    def enable_plugin(self, plugin_id: str):
        """Enable a disabled plugin."""

    def disable_plugin(self, plugin_id: str):
        """Disable an active plugin."""
```

### Theme Manager (`core/theme_manager.py`)

Manages application-wide theming and stylesheets.

**Key Features**:
- Light and dark theme support
- QSS stylesheet loading and parsing
- Runtime theme switching
- Color scheme management
- Per-widget style overrides

**Theme Architecture**:
```python
class ThemeManager:
    """Manages application themes and stylesheets."""

    def __init__(self):
        self.current_theme = "light"
        self.themes = self._load_themes()

    def apply_theme(self, theme_name: str):
        """Apply a theme to the application."""
        stylesheet = self._load_stylesheet(theme_name)
        QApplication.instance().setStyleSheet(stylesheet)

    def get_color(self, role: str) -> QColor:
        """Get a color from current theme."""
        return self.themes[self.current_theme].colors[role]
```

## Plugin Architecture

### Base Plugin Class (`plugins/base_tab.py`)

All plugins inherit from `BaseTab` abstract class.

**Required Methods**:
```python
from abc import ABC, abstractmethod
from PySide6.QtWidgets import QWidget

class BaseTab(ABC, QWidget):
    """Abstract base class for all tab plugins."""

    @abstractmethod
    def plugin_id(self) -> str:
        """Unique plugin identifier (e.g., 'research', 'search')."""

    @abstractmethod
    def tab_name(self) -> str:
        """Display name for the tab."""

    @abstractmethod
    def tab_icon(self) -> QIcon:
        """Icon for the tab."""

    @abstractmethod
    def setup_ui(self):
        """Initialize the plugin's UI components."""

    @abstractmethod
    def cleanup(self):
        """Clean up resources when tab is closed."""

    # Optional overrides
    def on_tab_activated(self):
        """Called when tab becomes active."""
        pass

    def on_tab_deactivated(self):
        """Called when tab loses focus."""
        pass

    def save_state(self) -> dict:
        """Save plugin state for persistence."""
        return {}

    def restore_state(self, state: dict):
        """Restore plugin state from saved data."""
        pass
```

### Example Plugin: Research Tab

**Plugin Entry Point** (`plugins/research/plugin.py`):
```python
from ..base_tab import BaseTab
from .research_tab import ResearchTabWidget

class ResearchPlugin(BaseTab):
    """Research workflow plugin."""

    def plugin_id(self) -> str:
        return "research"

    def tab_name(self) -> str:
        return "Research"

    def tab_icon(self) -> QIcon:
        return QIcon(":/icons/research.png")

    def setup_ui(self):
        self.research_widget = ResearchTabWidget(self)
        layout = QVBoxLayout()
        layout.addWidget(self.research_widget)
        self.setLayout(layout)

    def cleanup(self):
        self.research_widget.cancel_workflow()
        self.research_widget.deleteLater()
```

**Tab Widget** (`plugins/research/research_tab.py`):
```python
class ResearchTabWidget(QWidget):
    """Main research workflow interface."""

    # Signals
    workflow_started = Signal()
    workflow_completed = Signal(str)  # report
    workflow_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.setup_agents()

    def setup_ui(self):
        """Build the research interface."""
        # Question input
        self.question_input = QTextEdit()

        # Controls
        self.start_button = QPushButton("Start Research")
        self.start_button.clicked.connect(self.start_workflow)

        # Workflow progress
        self.workflow_widget = WorkflowProgressWidget()

        # Results tabs
        self.results_tabs = QTabWidget()

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.question_input)
        layout.addWidget(self.start_button)
        layout.addWidget(self.workflow_widget)
        layout.addWidget(self.results_tabs)
        self.setLayout(layout)

    def start_workflow(self):
        """Start the research workflow in background thread."""
        self.worker = ResearchWorker(self.question_input.toPlainText())
        self.worker.progress_update.connect(self.update_progress)
        self.worker.finished.connect(self.on_workflow_complete)
        self.worker.start()
```

### Research Plugin Modular Architecture

The Research plugin demonstrates best practices for complex plugin organization, separating concerns into focused modules:

**Module Responsibilities**:

| Module | Responsibility |
|--------|----------------|
| `plugin.py` | Plugin registration, metadata, lifecycle management |
| `research_tab.py` | Main widget orchestration, UI layout, component coordination |
| `constants.py` | UI constants, color schemes, stylesheet generators |
| `tab_builders.py` | Tab construction functions, widget creation |
| `tab_updaters.py` | State update handlers, UI refresh logic |
| `workflow_executor.py` | Agent coordination, workflow state, business logic |
| `workflow_handlers.py` | Signal connections, event response handlers |
| `workflow_thread.py` | Background thread execution, cancellation support |
| `export_utils.py` | Report export, file operations |

**Architecture Diagram**:
```
┌─────────────────────────────────────────────────────────────┐
│                      ResearchPlugin                          │
│                       (plugin.py)                            │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   ResearchTabWidget                          │
│                   (research_tab.py)                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ tab_builders │ │ tab_updaters │ │  workflow_handlers   │ │
│  │   (.py)      │ │    (.py)     │ │       (.py)          │ │
│  └──────────────┘ └──────────────┘ └──────────────────────┘ │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   WorkflowThread                             │
│                 (workflow_thread.py)                         │
│         Background execution with cancellation               │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│               QtWorkflowExecutor                             │
│              (workflow_executor.py)                          │
│  ┌────────────┐ ┌───────────────┐ ┌───────────────────────┐ │
│  │ QueryAgent │ │ ScoringAgent  │ │ CitationFinderAgent   │ │
│  └────────────┘ └───────────────┘ └───────────────────────┘ │
│  ┌────────────┐ ┌───────────────┐ ┌───────────────────────┐ │
│  │ReportAgent │ │Counterfactual │ │    EditorAgent        │ │
│  └────────────┘ └───────────────┘ └───────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Key Design Patterns**:

1. **Separation of Concerns**: UI construction, state management, and business logic in separate files
2. **Mixin-Style Handlers**: `workflow_handlers.py` adds methods to `ResearchTabWidget` via composition
3. **Threaded Execution**: `WorkflowThread` runs agents in background, emits signals for UI updates
4. **Centralized Constants**: All UI constants in `constants.py` for consistent theming
5. **Cancellation Support**: `WorkflowCancelledException` and `_should_cancel` flag for graceful termination

**Workflow Executor Methods**:

```python
class QtWorkflowExecutor(QObject):
    """Coordinates agent-based workflow with Qt signals."""

    # Workflow steps
    def generate_query(self, question: str) -> str
    def search_documents(self, query: str) -> List[dict]
    def score_documents(self, documents: List[dict]) -> List[Tuple[dict, dict]]
    def extract_citations(self, scored_docs: List) -> List[dict]
    def generate_preliminary_report(self, citations: List) -> str
    def perform_counterfactual_analysis(self, report: str) -> Optional[dict]
    def generate_final_report(self, preliminary: str, counterfactual: dict) -> str

    # Lifecycle
    def cleanup(self) -> None
    def cancel_workflow(self) -> None
```

## Signal/Slot Communication

### Application-Wide Signal Bus

Central signal bus for cross-plugin communication:

```python
class SignalBus(QObject):
    """Application-wide signal bus for loosely-coupled communication."""

    # Document signals
    document_selected = Signal(int)  # document_id
    document_updated = Signal(int)   # document_id

    # Configuration signals
    config_changed = Signal(str)     # config_key
    theme_changed = Signal(str)      # theme_name

    # Status signals
    status_message = Signal(str, int)  # message, timeout_ms
    error_occurred = Signal(str)       # error_message

# Global instance
signal_bus = SignalBus()
```

**Usage in Plugins**:
```python
# Emit signal
signal_bus.document_selected.emit(doc_id)

# Connect to signal
signal_bus.document_selected.connect(self.on_document_selected)

# Disconnect
signal_bus.document_selected.disconnect(self.on_document_selected)
```

## Background Operations

### Async Worker Pattern

Long-running operations use QThread workers:

```python
class AsyncWorker(QThread):
    """Base class for background worker threads."""

    # Signals
    progress_update = Signal(int, str)  # percent, message
    result_ready = Signal(object)       # result
    error_occurred = Signal(str)        # error_message

    def __init__(self, task_func, *args, **kwargs):
        super().__init__()
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs
        self._cancelled = False

    def run(self):
        """Execute task in background thread."""
        try:
            result = self.task_func(*self.args, **self.kwargs)
            if not self._cancelled:
                self.result_ready.emit(result)
        except Exception as e:
            self.error_occurred.emit(str(e))

    def cancel(self):
        """Request cancellation."""
        self._cancelled = True
```

**Usage**:
```python
# Create worker
worker = AsyncWorker(query_agent.search_documents, user_question)

# Connect signals
worker.progress_update.connect(self.update_progress_bar)
worker.result_ready.connect(self.display_results)
worker.error_occurred.connect(self.show_error)

# Start
worker.start()

# Cancel (if needed)
worker.cancel()
worker.wait()  # Wait for thread to finish
```

## Theme System

### QSS Stylesheets

Themes are defined using Qt Style Sheets (QSS), similar to CSS:

**Light Theme** (`resources/styles/default.qss`):
```css
/* Main window */
QMainWindow {
    background-color: #ffffff;
}

/* Tab widget */
QTabWidget::pane {
    border: 1px solid #cccccc;
    background-color: #ffffff;
}

QTabBar::tab {
    background-color: #f0f0f0;
    color: #333333;
    padding: 8px 16px;
    border: 1px solid #cccccc;
}

QTabBar::tab:selected {
    background-color: #ffffff;
    border-bottom-color: #ffffff;
}

/* Buttons */
QPushButton {
    background-color: #0066cc;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
}

QPushButton:hover {
    background-color: #0052a3;
}

QPushButton:pressed {
    background-color: #003d7a;
}

/* Document cards */
QFrame.document-card {
    background-color: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    padding: 12px;
}
```

**Dark Theme** (`resources/styles/dark.qss`):
```css
QMainWindow {
    background-color: #1e1e1e;
    color: #cccccc;
}

QTabWidget::pane {
    border: 1px solid #3c3c3c;
    background-color: #252526;
}

QPushButton {
    background-color: #0e639c;
    color: #ffffff;
}

QFrame.document-card {
    background-color: #2d2d30;
    border: 1px solid #3e3e42;
}
```

### Applying Themes

```python
# In ThemeManager
def apply_theme(self, theme_name: str):
    """Apply theme to application."""
    stylesheet_path = f":/styles/{theme_name}.qss"
    with open(stylesheet_path, 'r') as f:
        stylesheet = f.read()
    QApplication.instance().setStyleSheet(stylesheet)

    # Update color palette
    palette = self._create_palette(theme_name)
    QApplication.instance().setPalette(palette)

    # Notify plugins
    signal_bus.theme_changed.emit(theme_name)
```

## Configuration Management

### GUI Configuration

GUI-specific configuration stored in `~/.bmlibrarian/gui_config.json`:

```json
{
  "gui": {
    "theme": "dark",
    "window": {
      "width": 1400,
      "height": 900,
      "maximized": false,
      "remember_geometry": true
    },
    "tabs": {
      "enabled_plugins": [
        "research",
        "search",
        "fact_checker",
        "query_lab",
        "configuration"
      ],
      "tab_order": [
        "research",
        "search",
        "fact_checker",
        "query_lab",
        "configuration"
      ],
      "default_tab": "research"
    }
  }
}
```

### Agent Configuration

Agent configuration shared with CLI (in `~/.bmlibrarian/config.json`):

```json
{
  "ollama": {
    "host": "http://localhost:11434"
  },
  "agents": {
    "query_agent": {
      "model": "medgemma4B_it_q8:latest",
      "temperature": 0.1
    },
    "scoring_agent": {
      "model": "gpt-oss:20b",
      "temperature": 0.2
    }
  }
}
```

## Development Guidelines

### Creating a New Plugin

1. **Create plugin directory**: `src/bmlibrarian/gui/qt/plugins/myplugin/`

2. **Implement `plugin.py`**:
```python
from ..base_tab import BaseTab

class MyPlugin(BaseTab):
    def plugin_id(self) -> str:
        return "myplugin"

    def tab_name(self) -> str:
        return "My Plugin"

    def tab_icon(self) -> QIcon:
        return QIcon(":/icons/myplugin.png")

    def setup_ui(self):
        # Build your UI here
        pass

    def cleanup(self):
        # Clean up resources
        pass
```

3. **Register plugin**: Plugin auto-discovered by `PluginManager`

4. **Enable in config**: Add to `enabled_plugins` in `gui_config.json`

### Best Practices

**Thread Safety**:
- Use QThread for background operations
- Update UI only from main thread
- Use signal/slot for cross-thread communication

**Memory Management**:
- Call `deleteLater()` on widgets when done
- Disconnect signals when objects are destroyed
- Use weak references where appropriate

**Error Handling**:
- Catch exceptions in worker threads
- Emit error signals instead of raising
- Display user-friendly error messages

**Performance**:
- Use virtual scrolling for large lists
- Lazy-load tab content (only when activated)
- Cache expensive computations
- Profile with Qt performance tools

**Testing**:
- Unit test plugin logic separately from UI
- Use Qt Test framework for UI tests
- Test with both light and dark themes
- Test keyboard shortcuts

## Migration from Flet

For developers maintaining legacy Flet code or migrating features:

### Key Differences

| Aspect | Flet | Qt |
|--------|------|-----|
| **Framework** | Web-based (Flutter) | Native desktop |
| **Language** | Python only | Python + QSS |
| **Threading** | Async/await | QThread |
| **Styling** | Inline properties | QSS stylesheets |
| **Events** | Callbacks | Signal/slot |
| **Performance** | Web overhead | Native performance |

### Migration Strategy

1. **Identify functionality**: Understand what the Flet component does
2. **Find Qt equivalent**: Map to equivalent Qt widget
3. **Reimplement UI**: Build UI using Qt widgets
4. **Port business logic**: Keep logic, change UI code
5. **Test thoroughly**: Ensure feature parity

### Example Migration

**Flet Code**:
```python
def build_document_card(doc):
    return ft.ExpansionTile(
        title=ft.Text(doc["title"]),
        subtitle=ft.Text(doc["authors"]),
        controls=[
            ft.Text(doc["abstract"])
        ]
    )
```

**Qt Code**:
```python
def build_document_card(doc):
    card = QFrame()
    card.setObjectName("document-card")

    layout = QVBoxLayout(card)

    title = QLabel(doc["title"])
    title.setStyleSheet("font-weight: bold;")
    layout.addWidget(title)

    authors = QLabel(doc["authors"])
    authors.setStyleSheet("color: #666;")
    layout.addWidget(authors)

    # Collapsible abstract
    abstract_button = QToolButton()
    abstract_button.setText("Show Abstract")
    abstract_button.setCheckable(True)

    abstract_text = QLabel(doc["abstract"])
    abstract_text.setWordWrap(True)
    abstract_text.setVisible(False)

    abstract_button.toggled.connect(abstract_text.setVisible)

    layout.addWidget(abstract_button)
    layout.addWidget(abstract_text)

    return card
```

## Resources

### Qt Documentation
- [Qt for Python Documentation](https://doc.qt.io/qtforpython/)
- [Qt Widgets Module](https://doc.qt.io/qt-6/qtwidgets-module.html)
- [Qt Style Sheets Reference](https://doc.qt.io/qt-6/stylesheet-reference.html)

### BMLibrarian Documentation
- [Qt GUI User Guide](../users/qt_gui_user_guide.md)
- [Qt Plugin Development Guide](qt_plugin_development_guide.md)
- [Flet to Qt Migration Guide](../users/flet_to_qt_migration_guide.md)

### Example Code
- Example plugin: `src/bmlibrarian/gui/qt/plugins/example/`
- Research tab: `src/bmlibrarian/gui/qt/plugins/research/`
- Reusable widgets: `src/bmlibrarian/gui/qt/widgets/`

---

**This architecture provides a solid foundation for building feature-rich, performant desktop applications with BMLibrarian's Qt GUI system.**
