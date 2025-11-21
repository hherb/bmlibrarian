# PySide6 Migration - Directory Structure Reference

## Complete Directory Layout

```
bmlibrarian/
│
├── 📁 src/bmlibrarian/
│   │
│   ├── 📁 gui/                              # LEGACY: Flet GUI (maintenance mode)
│   │   ├── __init__.py
│   │   ├── research_app.py                  # ❌ No new features
│   │   ├── config_app.py                    # ❌ No new features
│   │   ├── components.py
│   │   ├── dialogs.py
│   │   ├── workflow.py
│   │   ├── tab_manager.py
│   │   └── tabs/
│   │       ├── general_tab.py
│   │       ├── agent_tab.py
│   │       └── query_generation_tab.py
│   │
│   ├── 📁 gui/qt/                           # NEW: PySide6 GUI (active development)
│   │   │
│   │   ├── __init__.py                      # Module exports (main function)
│   │   │
│   │   ├── 📁 core/                         # Core framework components
│   │   │   ├── __init__.py
│   │   │   ├── application.py               # 🔧 QApplication wrapper + entry point
│   │   │   ├── main_window.py               # 🪟 Main tabbed window (QMainWindow)
│   │   │   ├── plugin_manager.py            # 🔌 Plugin discovery & loading
│   │   │   ├── tab_registry.py              # 📋 Plugin registration system
│   │   │   ├── config_manager.py            # ⚙️ GUI configuration (JSON)
│   │   │   └── event_bus.py                 # 📡 Inter-plugin communication
│   │   │
│   │   ├── 📁 plugins/                      # Tab plugins (main features)
│   │   │   │
│   │   │   ├── base_tab.py                  # 🎯 Abstract base class for all plugins
│   │   │   │                                #    - TabPluginMetadata
│   │   │   │                                #    - BaseTabPlugin (ABC)
│   │   │   │
│   │   │   ├── 📁 research/                 # Research workflow plugin
│   │   │   │   ├── __init__.py
│   │   │   │   ├── plugin.py                # 🔌 Plugin entry point (create_plugin)
│   │   │   │   ├── research_tab.py          # Main tab widget
│   │   │   │   ├── workflow_widget.py       # Workflow step display
│   │   │   │   ├── question_input.py        # Question input widget
│   │   │   │   ├── document_list.py         # Document results list
│   │   │   │   ├── citation_viewer.py       # Citation display
│   │   │   │   └── report_preview.py        # Report preview with markdown
│   │   │   │
│   │   │   ├── 📁 configuration/            # Settings/config plugin
│   │   │   │   ├── __init__.py
│   │   │   │   ├── plugin.py                # 🔌 Plugin entry point
│   │   │   │   ├── config_tab.py            # Main config widget
│   │   │   │   ├── agent_config_widget.py   # Agent settings
│   │   │   │   ├── ollama_settings.py       # Ollama configuration
│   │   │   │   ├── database_settings.py     # Database config
│   │   │   │   └── query_gen_settings.py    # Multi-model query settings
│   │   │   │
│   │   │   ├── 📁 fact_checker/             # Fact-checker review plugin
│   │   │   │   ├── __init__.py
│   │   │   │   ├── plugin.py                # 🔌 Plugin entry point
│   │   │   │   ├── review_tab.py            # Main review widget
│   │   │   │   ├── statement_widget.py      # Statement display
│   │   │   │   ├── annotation_widget.py     # Annotation controls
│   │   │   │   ├── citation_cards.py        # Citation card display
│   │   │   │   └── timer_widget.py          # Confidence timer
│   │   │   │
│   │   │   ├── 📁 query_lab/                # Query laboratory plugin
│   │   │   │   ├── __init__.py
│   │   │   │   ├── plugin.py                # 🔌 Plugin entry point
│   │   │   │   ├── query_lab_tab.py         # Main lab widget
│   │   │   │   ├── sql_editor.py            # SQL editor with syntax highlighting
│   │   │   │   └── result_viewer.py         # Query results display
│   │   │   │
│   │   │   └── 📁 search/                   # Document search plugin
│   │   │       ├── __init__.py
│   │   │       ├── plugin.py                # 🔌 Plugin entry point
│   │   │       ├── search_tab.py            # Main search widget
│   │   │       ├── search_input.py          # Search controls
│   │   │       ├── filter_widget.py         # Search filters
│   │   │       └── result_viewer.py         # Results display
│   │   │
│   │   ├── 📁 widgets/                      # Reusable custom widgets
│   │   │   ├── __init__.py
│   │   │   ├── document_card.py             # 📄 Document display card
│   │   │   ├── citation_card.py             # 📝 Citation display card
│   │   │   ├── markdown_viewer.py           # 📖 Markdown rendering widget
│   │   │   ├── progress_widget.py           # ⏳ Progress indicators
│   │   │   ├── step_indicator.py            # 🪜 Workflow step indicator
│   │   │   ├── pdf_viewer.py                # 📑 PDF preview widget
│   │   │   ├── collapsible_section.py       # ⬇️ Collapsible panel widget
│   │   │   └── status_badge.py              # 🏷️ Status badge widget
│   │   │
│   │   ├── 📁 dialogs/                      # Dialog windows
│   │   │   ├── __init__.py
│   │   │   ├── settings_dialog.py           # ⚙️ Settings dialog
│   │   │   ├── about_dialog.py              # ℹ️ About dialog
│   │   │   ├── export_dialog.py             # 💾 Export dialog
│   │   │   ├── login_dialog.py              # 🔐 Login dialog
│   │   │   ├── progress_dialog.py           # ⏳ Progress dialog
│   │   │   └── error_dialog.py              # ❌ Error reporting dialog
│   │   │
│   │   ├── 📁 utils/                        # GUI utilities
│   │   │   ├── __init__.py
│   │   │   ├── threading.py                 # 🧵 Thread management (QRunnable, WorkerSignals)
│   │   │   ├── formatting.py                # 📝 Text and data formatting
│   │   │   ├── icons.py                     # 🎨 Icon management
│   │   │   ├── validators.py                # ✅ Input validation
│   │   │   ├── colors.py                    # 🎨 Color utilities
│   │   │   └── shortcuts.py                 # ⌨️ Keyboard shortcuts
│   │   │
│   │   └── 📁 resources/                    # Resources (icons, stylesheets, etc.)
│   │       ├── icons/                       # Icon files
│   │       │   ├── app.png
│   │       │   ├── research.png
│   │       │   ├── search.png
│   │       │   └── ...
│   │       ├── styles/                      # Qt stylesheets
│   │       │   ├── default.qss              # Default theme
│   │       │   └── dark.qss                 # Dark theme
│   │       └── resources.qrc                # Qt resource file
│   │
│   ├── 📁 factchecker/
│   │   └── gui/                             # LEGACY: Flet fact-checker GUI
│   │       ├── review_app.py                # ❌ No new features
│   │       └── ...
│   │
│   └── ... (other BMLibrarian modules)
│
├── 📁 tests/
│   ├── 📁 gui/
│   │   └── qt/                              # Qt GUI tests
│   │       ├── __init__.py
│   │       ├── test_plugin_manager.py       # Plugin loading tests
│   │       ├── test_event_bus.py            # Event bus tests
│   │       ├── test_config_manager.py       # Config manager tests
│   │       ├── 📁 plugins/                  # Plugin-specific tests
│   │       │   ├── test_research_plugin.py
│   │       │   ├── test_search_plugin.py
│   │       │   └── ...
│   │       └── 📁 widgets/                  # Widget tests
│   │           ├── test_document_card.py
│   │           └── ...
│   │
│   └── ... (other tests)
│
├── 📄 bmlibrarian_qt.py                     # NEW: Qt GUI entry point
├── 📄 bmlibrarian_research_gui.py           # LEGACY: Flet research GUI entry point
├── 📄 bmlibrarian_config_gui.py             # LEGACY: Flet config GUI entry point
├── 📄 fact_checker_review_gui.py            # LEGACY: Flet fact-checker GUI entry point
│
├── 📄 PYSIDE6_MIGRATION_README.md           # 📚 Main migration documentation index
├── 📄 PYSIDE6_MIGRATION_PLAN.md             # 📋 Comprehensive migration plan
├── 📄 PYSIDE6_PLUGIN_ARCHITECTURE.md        # 🏗️ Technical plugin architecture guide
├── 📄 PYSIDE6_QUICKSTART.md                 # 🚀 30-minute quick start guide
├── 📄 PYSIDE6_DIRECTORY_STRUCTURE.md        # 📂 This file
│
└── ... (other project files)
```

## Key Files and Their Purposes

### Entry Points

| File | Purpose | Status | Command |
|------|---------|--------|---------|
| `bmlibrarian_qt.py` | PySide6 GUI entry point | ✨ New | `uv run python bmlibrarian_qt.py` |
| `bmlibrarian_research_gui.py` | Flet research GUI | ⚠️ Legacy | `uv run python bmlibrarian_research_gui.py` |
| `bmlibrarian_config_gui.py` | Flet config GUI | ⚠️ Legacy | `uv run python bmlibrarian_config_gui.py` |
| `fact_checker_review_gui.py` | Flet fact-checker GUI | ⚠️ Legacy | `uv run python fact_checker_review_gui.py` |

### Core Framework Files

| File | Lines | Complexity | Description |
|------|-------|------------|-------------|
| `core/application.py` | ~100 | Low | QApplication wrapper and main() function |
| `core/main_window.py` | ~250 | Medium | Main window with tab widget and menu bar |
| `core/plugin_manager.py` | ~200 | Medium | Plugin discovery, loading, lifecycle |
| `core/tab_registry.py` | ~100 | Low | Plugin registration and lookup |
| `core/config_manager.py` | ~150 | Low | JSON configuration management |
| `core/event_bus.py` | ~80 | Low | Signal-based inter-plugin communication |

### Plugin Files (Each Plugin)

| File | Lines | Complexity | Description |
|------|-------|------------|-------------|
| `plugins/{name}/plugin.py` | ~50-100 | Low | Plugin entry point with `create_plugin()` |
| `plugins/{name}/{name}_tab.py` | ~300-600 | Medium-High | Main tab widget implementation |
| `plugins/{name}/*_widget.py` | ~100-300 | Medium | Sub-widgets and components |

### Base Classes

| File | Lines | Complexity | Description |
|------|-------|------------|-------------|
| `plugins/base_tab.py` | ~80 | Low | Abstract base class for all plugins |

## Plugin Structure Pattern

Every plugin follows this standard structure:

```
plugins/{plugin_name}/
├── __init__.py                  # Empty or exports
├── plugin.py                    # Entry point - REQUIRED
│   └── create_plugin() → BaseTabPlugin
│
├── {plugin_name}_tab.py         # Main tab widget
│   └── {PluginName}TabWidget(QWidget)
│
├── *_widget.py                  # Sub-widgets (optional)
│   └── {Feature}Widget(QWidget)
│
└── README.md                    # Plugin documentation (optional)
```

### Required Elements

1. **`plugin.py`** must exist
2. **`create_plugin()`** function must exist and return a `BaseTabPlugin` instance
3. **Plugin class** must inherit from `BaseTabPlugin`
4. **Metadata** must be returned by `get_metadata()`
5. **Widget factory** must be implemented in `create_widget()`

## File Size Estimates

### Current (Flet)

```
src/bmlibrarian/gui/                    ~8,000 lines
├── research_app.py                       ~2,500 lines
├── config_app.py                         ~1,200 lines
└── Other components                      ~4,300 lines

factchecker/gui/                        ~1,800 lines
└── review_app.py + components            ~1,800 lines

TOTAL                                   ~9,800 lines
```

### Target (PySide6)

```
src/bmlibrarian/gui/qt/                ~10,000 lines
├── core/                                 ~1,000 lines
├── plugins/research/                     ~2,500 lines
├── plugins/configuration/                ~1,500 lines
├── plugins/fact_checker/                 ~2,000 lines
├── plugins/query_lab/                    ~1,000 lines
├── plugins/search/                       ~1,200 lines
├── widgets/                              ~1,500 lines
├── dialogs/                                ~800 lines
└── utils/                                  ~500 lines

TOTAL                                  ~10,000 lines (similar to Flet)
```

**Note**: Line count similar, but code is:
- More modular
- Better organized
- More testable
- More maintainable

## Configuration Files

### GUI Configuration

**Location**: `~/.bmlibrarian/gui_config.json`

```json
{
  "gui": {
    "theme": "default",
    "window": {
      "width": 1400,
      "height": 900,
      "remember_geometry": true,
      "position_x": 100,
      "position_y": 100
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

### BMLibrarian Main Configuration

**Location**: `~/.bmlibrarian/config.json`

- Agent settings
- Database configuration
- Ollama settings
- Multi-model query generation

**Note**: GUI config is separate from main BMLibrarian config.

## Resource Organization

### Icons

```
resources/icons/
├── app.png              # Application icon
├── research.png         # Research tab icon
├── search.png           # Search tab icon
├── fact_checker.png     # Fact-checker tab icon
├── query_lab.png        # Query lab icon
├── configuration.png    # Settings icon
├── document.png         # Document icon
├── citation.png         # Citation icon
└── ...
```

### Stylesheets

```
resources/styles/
├── default.qss          # Default light theme
└── dark.qss             # Dark theme (future)
```

Example QSS (Qt Style Sheet):

```css
/* default.qss */
QMainWindow {
    background-color: #f5f5f5;
}

QPushButton {
    background-color: #2196F3;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
}

QPushButton:hover {
    background-color: #1976D2;
}

QTabBar::tab {
    padding: 8px 16px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #2196F3;
    color: white;
}
```

## Development Phases and File Creation Order

### Phase 1: Foundation

**Create these files first:**

1. ✅ `pyproject.toml` - Add PySide6 dependencies
2. ✅ Directory structure - Create all folders
3. ✅ `plugins/base_tab.py` - Base plugin interface
4. ✅ `core/config_manager.py` - Configuration system
5. ✅ `core/main_window.py` - Main window (basic)
6. ✅ `core/application.py` - Application wrapper
7. ✅ `bmlibrarian_qt.py` - Entry point
8. ✅ Test launch - Verify empty window opens

### Phase 2: Research Tab

**Create these files:**

1. ✅ `plugins/research/plugin.py` - Plugin entry point
2. ✅ `plugins/research/research_tab.py` - Main widget
3. ✅ `plugins/research/question_input.py` - Question input
4. ✅ `plugins/research/workflow_widget.py` - Workflow display
5. ✅ `widgets/document_card.py` - Document display (reusable)
6. ✅ `widgets/citation_card.py` - Citation display (reusable)
7. ✅ `widgets/markdown_viewer.py` - Markdown rendering
8. ✅ `utils/threading.py` - Async operations
9. ✅ Update `core/plugin_manager.py` - Add discovery
10. ✅ Update `core/main_window.py` - Add plugin loading

### Phase 3-6: Continue with other plugins

Follow similar pattern for each plugin.

## Migration Checklist by File

### Core Framework Files

- [ ] `core/application.py`
- [ ] `core/main_window.py`
- [ ] `core/plugin_manager.py`
- [ ] `core/tab_registry.py`
- [ ] `core/config_manager.py`
- [ ] `core/event_bus.py`

### Base Classes

- [ ] `plugins/base_tab.py`

### Research Plugin

- [ ] `plugins/research/plugin.py`
- [ ] `plugins/research/research_tab.py`
- [ ] `plugins/research/workflow_widget.py`
- [ ] `plugins/research/question_input.py`
- [ ] `plugins/research/document_list.py`
- [ ] `plugins/research/citation_viewer.py`
- [ ] `plugins/research/report_preview.py`

### Configuration Plugin

- [ ] `plugins/configuration/plugin.py`
- [ ] `plugins/configuration/config_tab.py`
- [ ] `plugins/configuration/agent_config_widget.py`
- [ ] `plugins/configuration/ollama_settings.py`
- [ ] `plugins/configuration/database_settings.py`
- [ ] `plugins/configuration/query_gen_settings.py`

### Fact-Checker Plugin

- [ ] `plugins/fact_checker/plugin.py`
- [ ] `plugins/fact_checker/review_tab.py`
- [ ] `plugins/fact_checker/statement_widget.py`
- [ ] `plugins/fact_checker/annotation_widget.py`
- [ ] `plugins/fact_checker/citation_cards.py`
- [ ] `plugins/fact_checker/timer_widget.py`

### Search Plugin

- [ ] `plugins/search/plugin.py`
- [ ] `plugins/search/search_tab.py`
- [ ] `plugins/search/search_input.py`
- [ ] `plugins/search/filter_widget.py`
- [ ] `plugins/search/result_viewer.py`

### Query Lab Plugin

- [ ] `plugins/query_lab/plugin.py`
- [ ] `plugins/query_lab/query_lab_tab.py`
- [ ] `plugins/query_lab/sql_editor.py`
- [ ] `plugins/query_lab/result_viewer.py`

### Reusable Widgets

- [ ] `widgets/document_card.py`
- [ ] `widgets/citation_card.py`
- [ ] `widgets/markdown_viewer.py`
- [ ] `widgets/progress_widget.py`
- [ ] `widgets/step_indicator.py`
- [ ] `widgets/pdf_viewer.py`
- [ ] `widgets/collapsible_section.py`
- [ ] `widgets/status_badge.py`

### Dialogs

- [ ] `dialogs/settings_dialog.py`
- [ ] `dialogs/about_dialog.py`
- [ ] `dialogs/export_dialog.py`
- [ ] `dialogs/login_dialog.py`
- [ ] `dialogs/progress_dialog.py`
- [ ] `dialogs/error_dialog.py`

### Utilities

- [ ] `utils/threading.py`
- [ ] `utils/formatting.py`
- [ ] `utils/icons.py`
- [ ] `utils/validators.py`
- [ ] `utils/colors.py`
- [ ] `utils/shortcuts.py`

### Resources

- [ ] `resources/styles/default.qss`
- [ ] `resources/styles/dark.qss`
- [ ] `resources/icons/` - Collect/create icons

### Tests

- [ ] `tests/gui/qt/test_plugin_manager.py`
- [ ] `tests/gui/qt/test_event_bus.py`
- [ ] `tests/gui/qt/test_config_manager.py`
- [ ] `tests/gui/qt/plugins/test_research_plugin.py`
- [ ] `tests/gui/qt/plugins/test_search_plugin.py`
- [ ] `tests/gui/qt/widgets/test_document_card.py`

## Quick Reference - Common Patterns

### Import a Plugin

```python
from bmlibrarian.gui.qt.plugins.research.plugin import create_plugin

plugin = create_plugin()
widget = plugin.create_widget()
```

### Use Event Bus

```python
from bmlibrarian.gui.qt.core.event_bus import EventBus

event_bus = EventBus()
event_bus.publish_data("research", {"documents": docs})
```

### Load Configuration

```python
from bmlibrarian.gui.qt.core.config_manager import GUIConfigManager

config_mgr = GUIConfigManager()
config = config_mgr.get_config()
enabled_plugins = config["gui"]["tabs"]["enabled_plugins"]
```

### Create Worker Thread

```python
from bmlibrarian.gui.qt.utils.threading import WorkerSignals, create_worker

worker = create_worker(long_running_function, arg1, arg2)
worker.signals.result.connect(self._on_complete)
threadpool.start(worker)
```

## Next Steps

1. **Phase 1**: Create directory structure (use `mkdir -p` commands above)
2. **Phase 1**: Implement core framework files
3. **Phase 1**: Test with empty/minimal plugins
4. **Phase 2+**: Implement plugins one by one
5. **Throughout**: Write tests alongside code
6. **Phase 6**: Polish and documentation

**Start here**: [Quick Start Guide](PYSIDE6_QUICKSTART.md) for step-by-step instructions.

---

*Last updated: 2025-11-16*
