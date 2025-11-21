# PySide6 GUI Migration - Documentation Index

## Overview

This directory contains comprehensive documentation for migrating BMLibrarian's GUI from Flet to PySide6 with a modern plugin-based tab architecture.

## Why PySide6?

BMLibrarian has outgrown the capabilities of the Flet GUI library. Key limitations include:

- **Performance Issues**: Slow rendering with large datasets (100+ documents)
- **File Picker Bugs**: Especially problematic on macOS
- **Limited Customization**: Difficult to implement advanced UI features
- **Immature Ecosystem**: Limited third-party components and plugins
- **Threading Limitations**: Challenges with complex async workflows

PySide6 (Qt for Python) provides:

- **Battle-tested Framework**: Mature, professional-grade Qt framework
- **Native Performance**: Direct platform integration and optimization
- **Rich Widget Ecosystem**: Comprehensive built-in and third-party components
- **Advanced Threading**: Robust support for async operations
- **Plugin Architecture**: Built-in support for extensible applications
- **Cross-platform**: Consistent experience on Linux, macOS, and Windows

## Migration Strategy

### Dual-Track Approach

1. **Legacy Flet GUI** (`src/bmlibrarian/gui/`):
   - Maintenance mode (critical bug fixes only)
   - No new features
   - Gradual deprecation over 6 months

2. **New PySide6 GUI** (`src/bmlibrarian/gui/qt/`):
   - Active development
   - All new features
   - Plugin-based architecture
   - Feature parity first, then enhancements

### Plugin-Based Architecture

The new GUI implements a plugin-based tab system where:

- Each major feature is a **plugin** (research, search, fact-checker, etc.)
- Plugins are **configurable** - users can enable/disable tabs
- Plugins are **independent** - can be developed and tested separately
- Plugins **communicate** via event bus for data sharing
- New features can be added as **new plugins** without modifying core code

## Documentation Structure

### 📋 [Migration Plan](PYSIDE6_MIGRATION_PLAN.md) - READ FIRST
**Comprehensive migration strategy and timeline**

- Executive summary and rationale
- Complete directory structure
- Plugin configuration system
- 6-phase migration timeline (12 weeks)
- Risk mitigation strategies
- Success metrics
- Legacy support plan

**Who should read**: Project managers, architects, all developers

**Time investment**: 30-45 minutes

### 🏗️ [Plugin Architecture Guide](PYSIDE6_PLUGIN_ARCHITECTURE.md)
**Deep technical implementation details**

- Plugin system architecture
- Core component reference code
- Inter-tab communication patterns
- Thread safety and async operations
- Resource management best practices
- Complete working plugin examples

**Who should read**: Developers implementing plugins

**Time investment**: 1-2 hours (reference material)

### 🚀 [Quick Start Guide](PYSIDE6_QUICKSTART.md)
**Get up and running in 30 minutes**

- Step-by-step setup instructions
- Install PySide6 dependencies
- Create directory structure
- Implement minimal framework
- Build your first "Hello World" plugin
- Launch the Qt GUI
- Troubleshooting common issues

**Who should read**: Developers starting implementation

**Time investment**: 30 minutes hands-on

## Quick Navigation

### For Different Roles

#### **Project Manager / Architect**
1. Read [Migration Plan](PYSIDE6_MIGRATION_PLAN.md) - Executive Summary
2. Review timeline and phases
3. Assess resource requirements
4. Review risk mitigation strategies

#### **Developer - First Time Setup**
1. Skim [Migration Plan](PYSIDE6_MIGRATION_PLAN.md) - Architecture Overview
2. Follow [Quick Start Guide](PYSIDE6_QUICKSTART.md) step-by-step
3. Reference [Plugin Architecture Guide](PYSIDE6_PLUGIN_ARCHITECTURE.md) as needed

#### **Developer - Implementing New Plugin**
1. Review "Plugin Architecture" section in [Migration Plan](PYSIDE6_MIGRATION_PLAN.md)
2. Study plugin examples in [Plugin Architecture Guide](PYSIDE6_PLUGIN_ARCHITECTURE.md)
3. Copy template from "Complete Plugin Example" section
4. Implement your plugin following best practices

#### **Developer - Debugging Issues**
1. Check "Troubleshooting" in [Quick Start Guide](PYSIDE6_QUICKSTART.md)
2. Review "Common Issues" in [Plugin Architecture Guide](PYSIDE6_PLUGIN_ARCHITECTURE.md)
3. Consult Qt documentation for widget-specific problems

## Migration Timeline

### Phase 1: Foundation (Weeks 1-2) ⚙️
**Status**: Not started
**Deliverable**: Core framework and plugin system

- Add PySide6 dependencies
- Create directory structure
- Implement plugin manager
- Create configuration system
- Setup resource system

**Start here**: [Quick Start Guide](PYSIDE6_QUICKSTART.md)

### Phase 2: Research Tab Plugin (Weeks 3-4) 🔬
**Status**: Not started
**Deliverable**: Full-featured research workflow interface

- Migrate research UI components
- Implement async workflow execution
- Connect to agent orchestrator
- Report preview and export

**Reference**: [Plugin Architecture Guide](PYSIDE6_PLUGIN_ARCHITECTURE.md) - Thread Safety section

### Phase 3: Configuration Tab Plugin (Weeks 5-6) ⚙️
**Status**: Not started
**Deliverable**: Settings and configuration interface

- Agent settings (models, parameters)
- Ollama server configuration
- Database settings
- Multi-model query settings

### Phase 4: Fact-Checker Review Tab Plugin (Weeks 7-8) ✅
**Status**: Not started
**Deliverable**: Review and annotation interface

- Statement display and annotation
- Citation cards with expandable abstracts
- Database integration (PostgreSQL & SQLite)
- Export functionality

### Phase 5: Additional Plugins (Weeks 9-10) 🔍
**Status**: Not started
**Deliverable**: Query lab, search, and reusable widgets

- Query lab with SQL editor
- Advanced search interface
- Reusable widget library

### Phase 6: Polish & Documentation (Weeks 11-12) ✨
**Status**: Not started
**Deliverable**: Production-ready application

- Dark theme
- Keyboard shortcuts
- Performance optimization
- Comprehensive documentation
- Automated testing

## Current Applications to Migrate

### 1. Research GUI (`bmlibrarian_research_gui.py`)
**Lines of Code**: ~2500 across 30+ files
**Complexity**: High
**Priority**: High

Main features:
- Multi-line research question input
- Visual workflow progress with collapsible steps
- Real-time agent execution
- Document and citation display
- Markdown report preview
- Export functionality

### 2. Configuration GUI (`bmlibrarian_config_gui.py`)
**Lines of Code**: ~1200 across 10+ files
**Complexity**: Medium
**Priority**: Medium

Main features:
- Tabbed agent configuration
- Model selection with live refresh
- Parameter adjustment sliders
- Connection testing
- Save/load configuration

### 3. Fact-Checker Review GUI (`fact_checker_review_gui.py`)
**Lines of Code**: ~1800 across 8 files
**Complexity**: Medium
**Priority**: Medium

Main features:
- Statement review and annotation
- Citation display with full abstracts
- Database integration (PostgreSQL/SQLite)
- Timer component for confidence tracking
- Multi-user support

### 4. Query Lab GUI (`query_lab.py`)
**Lines of Code**: ~800
**Complexity**: Low
**Priority**: Low

Main features:
- Interactive SQL query testing
- Query history
- Result display

## Getting Started

### Prerequisites

```bash
# Verify Python version
python --version  # Should be >=3.12

# Verify uv is installed
uv --version

# Verify PostgreSQL is running
psql --version
```

### Installation (5 minutes)

```bash
# 1. Navigate to project directory
cd /home/user/bmlibrarian

# 2. Follow Quick Start Guide
# See: PYSIDE6_QUICKSTART.md

# 3. Install PySide6
# (Instructions in Quick Start)

# 4. Create directory structure
# (Instructions in Quick Start)

# 5. Launch your first Qt GUI
uv run python bmlibrarian_qt.py
```

### First Plugin (30 minutes)

Follow the complete walkthrough in [Quick Start Guide](PYSIDE6_QUICKSTART.md).

## Development Workflow

```bash
# 1. Create feature branch
git checkout -b pyside6-research-tab

# 2. Implement plugin following architecture guide

# 3. Test frequently
uv run python bmlibrarian_qt.py

# 4. Commit incrementally
git add src/bmlibrarian/gui/qt/plugins/research/
git commit -m "feat(qt): Implement research tab plugin"

# 5. Push and create PR
git push -u origin pyside6-research-tab
```

## Testing Strategy

### Unit Tests

```bash
# Test plugin loading
uv run python -m pytest tests/gui/qt/test_plugin_manager.py

# Test specific plugin
uv run python -m pytest tests/gui/qt/plugins/test_research_plugin.py
```

### Integration Tests

```bash
# Test inter-tab communication
uv run python -m pytest tests/gui/qt/test_event_bus.py

# Test workflow execution
uv run python -m pytest tests/gui/qt/test_workflow_integration.py
```

### Manual Testing

```bash
# Launch GUI for manual testing
uv run python bmlibrarian_qt.py

# Test with sample data
uv run python bmlibrarian_qt.py --test-mode

# Performance profiling
uv run python -m cProfile -o profile.stats bmlibrarian_qt.py
```

## Configuration

### GUI Configuration File

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
        "configuration"
      ],
      "tab_order": ["research", "search", "fact_checker", "configuration"],
      "default_tab": "research"
    }
  }
}
```

Users can customize which tabs appear by editing `enabled_plugins`.

## Plugin Development

### Creating a New Plugin

```bash
# 1. Create plugin directory
mkdir -p src/bmlibrarian/gui/qt/plugins/myplugin

# 2. Create __init__.py
touch src/bmlibrarian/gui/qt/plugins/myplugin/__init__.py

# 3. Create plugin.py using template from architecture guide
# See: PYSIDE6_PLUGIN_ARCHITECTURE.md - Complete Plugin Example

# 4. Implement your plugin

# 5. Add to enabled_plugins in config
```

### Plugin Template

See [Plugin Architecture Guide](PYSIDE6_PLUGIN_ARCHITECTURE.md) - Appendix A: Plugin Example Template

## Resources

### Documentation
- **PySide6 Official**: https://doc.qt.io/qtforpython-6/
- **Qt Widgets**: https://doc.qt.io/qt-6/qtwidgets-index.html
- **Qt Designer**: UI design tool (optional)
- **Qt Examples**: https://doc.qt.io/qt-6/qtexamples.html

### Tools
- **Qt Designer**: Visual UI designer
- **Qt Linguist**: Internationalization tool
- **QML Designer**: For advanced UI (if needed)

### Community
- **Qt Forum**: https://forum.qt.io/
- **Stack Overflow**: Tag `pyside6` or `pyqt`
- **GitHub Issues**: Report BMLibrarian-specific issues

## FAQ

### Why not keep Flet?

Flet is excellent for simple applications, but BMLibrarian has grown beyond its capabilities:
- Performance issues with 100+ documents
- File picker bugs on macOS
- Limited customization options
- Difficult to implement advanced features (drag-drop, custom widgets, etc.)

### Why not PyQt6?

PySide6 and PyQt6 are very similar (both are Qt bindings). We chose PySide6 because:
- Official Qt for Python implementation
- LGPL license (more permissive than PyQt6's GPL)
- Better documentation and examples
- Active development by Qt Company

### Can I use both GUIs?

Yes! During the transition period (months 1-6), both GUIs will be available:
- **Flet GUI**: `uv run python bmlibrarian_research_gui.py` (legacy)
- **Qt GUI**: `uv run python bmlibrarian_qt.py` (new)

After 6 months, the Flet GUI may be deprecated based on user feedback.

### Do I need to learn Qt?

Basic Qt knowledge is helpful but not required:
- Follow the [Quick Start Guide](PYSIDE6_QUICKSTART.md) for step-by-step setup
- Use plugin templates from [Plugin Architecture Guide](PYSIDE6_PLUGIN_ARCHITECTURE.md)
- Copy patterns from example plugins
- Consult Qt documentation for specific widgets

### How long will migration take?

Estimated timeline: **12 weeks** (3 months) for full migration

- Weeks 1-2: Foundation
- Weeks 3-4: Research tab
- Weeks 5-6: Configuration tab
- Weeks 7-8: Fact-checker tab
- Weeks 9-10: Additional plugins
- Weeks 11-12: Polish and documentation

Actual time depends on team size and availability.

### What happens to existing Flet code?

- Flet code stays in `src/bmlibrarian/gui/` (unchanged)
- Maintenance mode: critical bug fixes only
- No new features in Flet version
- Deprecation warnings added to entry points
- May be removed after 6 months based on usage

## Success Metrics

Track progress using these metrics:

- **Feature Parity**: All Flet features available in Qt ✅
- **Performance**: 50% faster than Flet with 100+ documents 📈
- **Memory**: 30% lower memory usage 🧠
- **Stability**: Zero crashes in standard workflows 💪
- **Test Coverage**: >80% for Qt GUI code 🧪
- **Documentation**: Complete plugin development guide 📚
- **User Satisfaction**: Positive feedback from beta testers 😊

## Support

### Getting Help

1. **Read the docs** (you are here!)
2. **Check troubleshooting sections** in Quick Start and Architecture guides
3. **Consult Qt documentation** for widget-specific questions
4. **Ask in team chat** for BMLibrarian-specific issues
5. **Create GitHub issue** for bugs or feature requests

### Contributing

Contributions welcome! Please:

1. Read the migration plan
2. Follow plugin architecture guidelines
3. Write tests for new code
4. Update documentation
5. Create PR with clear description

## Roadmap

### Short-term (Months 1-3)
- ✅ Complete Phase 1-6 migration
- ✅ Achieve feature parity with Flet
- ✅ Beta testing with users

### Medium-term (Months 4-6)
- Enhanced visualizations (citation networks, timeline views)
- Built-in PDF viewer with annotations
- Database browser tab
- Multi-window support

### Long-term (Months 7+)
- Advanced export (PDF reports, PowerPoint, Excel)
- Collaboration features
- Mobile companion app (Qt for Mobile)
- Plugin marketplace

## License

Same as BMLibrarian main project.

## Authors

BMLibrarian development team.

---

**Ready to get started?** → [Quick Start Guide](PYSIDE6_QUICKSTART.md)

**Need architectural details?** → [Plugin Architecture Guide](PYSIDE6_PLUGIN_ARCHITECTURE.md)

**Planning the project?** → [Migration Plan](PYSIDE6_MIGRATION_PLAN.md)

---

*Last updated: 2025-11-16*
