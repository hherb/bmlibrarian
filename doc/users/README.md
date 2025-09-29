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

### GUI Applications

🖥️ **[Research GUI Guide](research_gui_guide.md)**
- Desktop research application with visual workflow
- Interactive research question input
- Real-time progress tracking
- Report preview and export

🔧 **[Configuration GUI Guide](config_gui_guide.md)**
- Visual agent configuration interface
- Model selection and parameter tuning
- Connection testing and validation

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
# Interactive CLI research
uv run python bmlibrarian_cli.py

# Research GUI (desktop)
uv run python bmlibrarian_research_gui.py

# Configuration GUI
uv run python bmlibrarian_config_gui.py

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