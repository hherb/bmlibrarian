# User Documentation

Welcome to BMLibrarian user documentation! BMLibrarian is a comprehensive AI-powered biomedical literature analysis platform featuring multi-agent research workflows, desktop GUI applications, and advanced literature review capabilities.

## Getting Started

Start here if you're new to BMLibrarian:

📖 **[Getting Started Guide](getting_started.md)**
- Installation and setup
- Prerequisites (PostgreSQL, Ollama)
- Initial configuration
- First research workflow

## User Interfaces

### Qt GUI Application (Current)

🖥️ **[Qt GUI User Guide](qt_gui_user_guide.md)**
- Modern PySide6-based desktop application
- Plugin-based tabbed interface for multiple workflows
- Research, Search, Fact-Checking, Query Lab, and Configuration tabs
- Light and dark theme support
- Comprehensive keyboard shortcuts
- Native performance and stability

**Launch**: `uv run python bmlibrarian_qt.py`

### Legacy GUIs (Deprecated)

⚠️ **Note**: The Flet-based GUI applications are deprecated and will be removed in future versions. Please migrate to the Qt GUI.

📖 **[Flet to Qt Migration Guide](flet_to_qt_migration_guide.md)**
- How to transition from Flet to Qt GUI
- Feature comparison and workflow changes
- Configuration migration steps

### Command Line Interface

⚡ **[CLI Guide](cli_guide.md)**
- Interactive research workflow
- Command-line options and modes
- Automated execution patterns

📋 **[CLI Reference](cli_reference.md)**
- Complete command reference
- Usage examples and patterns
- Configuration options

## Research Workflows

🔄 **[Workflow Guide](workflow_guide.md)**
- Understanding the multi-agent research process
- Workflow steps and execution flow
- Interactive vs. automated modes
- Customizing research parameters

🧠 **[Agents Guide](agents_guide.md)**
- Multi-agent system overview
- Individual agent capabilities
- Agent configuration and tuning

## Advanced Features

### Literature Analysis

📝 **[Citation Guide](citation_guide.md)**
- Citation extraction from documents
- Relevance scoring and filtering
- Quality assessment techniques

📊 **[Reporting Guide](reporting_guide.md)**
- Report generation and formatting
- Citation integration
- Export options and formats

🔍 **[Counterfactual Guide](counterfactual_guide.md)**
- Contradictory evidence analysis
- Research question generation
- Evidence strength assessment

### Fact-Checking System

✅ **[Fact Checker Guide](fact_checker_guide.md)**
- Automated verification of biomedical statements
- Evidence extraction from literature database
- Multi-user annotation and review system
- Batch processing for LLM training data auditing
- PostgreSQL-based storage with inter-rater reliability support
- CLI and GUI interfaces

🔍 **[Fact Checker Review Guide](fact_checker_review_guide.md)**
- Human annotation and review interface
- Comparing AI evaluations with human judgments
- Citation evidence examination
- Inter-rater reliability analysis
- Export annotations for statistical analysis

### Configuration Management

⚙️ **[Configuration Guide](configuration_guide.md)**
- Agent configuration and tuning
- Model selection and parameters
- Database and API setup

## Support

### Troubleshooting

🔧 **[Troubleshooting Guide](troubleshooting.md)**
- Common issues and solutions
- Error message explanations
- Debug and recovery procedures
- Performance optimization

## Quick Reference

### Installation
```bash
# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your database credentials
```

### Running Applications
```bash
# Qt GUI (desktop application with all features)
uv run python bmlibrarian_qt.py

# Interactive CLI research
uv run python bmlibrarian_cli.py

# Fact-checker CLI (batch processing)
uv run python fact_checker_cli.py statements.json

# Quick testing mode
uv run python bmlibrarian_cli.py --quick
```

### Configuration Files
```bash
# Primary configuration location
~/.bmlibrarian/config.json

# Legacy fallback (current directory)
bmlibrarian_config.json
```

## Need More Help?

- **Technical Issues**: Check the [Troubleshooting Guide](troubleshooting.md)
- **Feature Requests**: See the developer documentation
- **API Usage**: Refer to the [API Reference](../developers/api_reference.md)

---

Choose a topic above to get started, or begin with the [Getting Started Guide](getting_started.md) if you're new to BMLibrarian.