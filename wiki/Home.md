# BMLibrarian Wiki

Welcome to the BMLibrarian documentation! BMLibrarian is a comprehensive Python library and application providing AI-powered access to biomedical literature databases, featuring a sophisticated multi-agent architecture for research automation.

## 🚀 Quick Links

### For New Users
- **[Getting Started](Getting-Started)** - Installation and first steps
- **[User Guide](User-Guide)** - Complete guide to using BMLibrarian
- **[CLI Reference](CLI-Reference)** - Command-line interface documentation
- **[Qt GUI Guide](Qt-GUI-Guide)** - Desktop application user guide

### For Developers
- **[Architecture Overview](Architecture-Overview)** - System design and components
- **[Plugin Development Guide](Plugin-Development-Guide)** - Create custom plugins for the Qt GUI
- **[API Reference](API-Reference)** - Python API documentation
- **[Contributing Guidelines](Contributing)** - How to contribute to the project
- **[Development Setup](Development-Setup)** - Set up your development environment

### For Researchers
- **[Research Workflow](Research-Workflow)** - Multi-agent research automation
- **[Fact Checker Guide](Fact-Checker-Guide)** - Validate biomedical statements
- **[Query Optimization](Query-Optimization)** - Get better search results

## What is BMLibrarian?

BMLibrarian is a comprehensive Python library that provides AI-powered access to biomedical literature databases. It features a multi-agent architecture with specialized agents for:

- **Query Processing** - Convert natural language questions to database queries
- **Document Scoring** - Assess relevance of documents to research questions
- **Citation Extraction** - Extract specific passages that answer questions
- **Report Generation** - Synthesize evidence into publication-quality reports
- **Counterfactual Analysis** - Find contradictory evidence for balanced analysis
- **Fact Checking** - Validate biomedical statements against literature

## Key Features

### 🤖 Multi-Agent Architecture
- Specialized AI agents for different research tasks
- Coordinated workflow orchestration
- Queue-based batch processing
- Support for multiple LLM models (via Ollama)

### 🗄️ Robust Database Infrastructure
- PostgreSQL with pgvector for semantic search
- Support for PubMed (38M+ articles) and medRxiv preprints
- Full-text search and vector similarity search
- Automatic schema migrations

### 🖥️ Multiple Interfaces
- **CLI** - Interactive command-line interface
- **Qt GUI** - Modern desktop application with plugin architecture
- **Python API** - Full programmatic access

### 🔍 Advanced Features
- Multi-model query generation (20-40% more relevant documents)
- Citation hallucination prevention
- Query performance tracking
- OpenAthens institutional access support
- PDF management and viewing

### 🛡️ Privacy-First Design
- Runs entirely with local models (Ollama)
- No API keys required
- No proprietary services needed
- Complete offline operation (after initial data sync)

## System Requirements

- **Python**: 3.12 or higher
- **Database**: PostgreSQL 14+ with pgvector extension
- **AI/LLM**: Ollama for local model inference
- **Package Manager**: `uv` (recommended) or `pip`

## Quick Start

```bash
# Install dependencies
uv sync

# Set up database and import data
uv run python initial_setup_and_download.py test_database.env

# Run the Qt GUI
uv run python bmlibrarian_qt.py

# Or run the CLI
uv run python bmlibrarian_cli.py
```

See the [Getting Started](Getting-Started) guide for detailed installation instructions.

## Project Structure

```
bmlibrarian/
├── src/bmlibrarian/          # Main source code
│   ├── agents/               # Multi-agent system
│   ├── importers/            # Data importers (PubMed, medRxiv)
│   ├── embeddings/           # Document embeddings
│   ├── factchecker/          # Fact-checking system
│   ├── gui/qt/               # Qt GUI application
│   │   ├── plugins/          # Plugin-based architecture
│   │   ├── widgets/          # Reusable UI components
│   │   └── resources/        # Styles and assets
│   ├── database.py           # Database access layer
│   └── config.py             # Configuration management
├── doc/                      # Comprehensive documentation
│   ├── users/                # End-user guides
│   └── developers/           # Technical documentation
├── tests/                    # Test suite
└── examples/                 # Example scripts
```

## Documentation Overview

### User Documentation
- [Getting Started](Getting-Started) - Installation and setup
- [User Guide](User-Guide) - Using BMLibrarian for research
- [CLI Reference](CLI-Reference) - Command-line tools
- [Qt GUI Guide](Qt-GUI-Guide) - Desktop application
- [Fact Checker Guide](Fact-Checker-Guide) - Statement validation
- [Configuration Guide](Configuration-Guide) - Customize BMLibrarian

### Developer Documentation
- [Architecture Overview](Architecture-Overview) - System design
- [Plugin Development Guide](Plugin-Development-Guide) - Create Qt plugins
- [Agent Development](Agent-Development) - Create custom agents
- [Database Schema](Database-Schema) - PostgreSQL schema reference
- [API Reference](API-Reference) - Python API documentation
- [Testing Guide](Testing-Guide) - Writing and running tests

### Research Guides
- [Research Workflow](Research-Workflow) - Automated research process
- [Query Optimization](Query-Optimization) - Improve search results
- [Citation Best Practices](Citation-Best-Practices) - Extract quality evidence
- [Multi-Model Queries](Multi-Model-Queries) - Use multiple AI models

## Community and Support

- **GitHub Repository**: [hherb/bmlibrarian](https://github.com/hherb/bmlibrarian)
- **Issue Tracker**: Report bugs and request features
- **Discussions**: Ask questions and share ideas
- **Contributing**: See [Contributing Guidelines](Contributing)

## Recent Updates

**November 2025:**
- ✅ Qt GUI with plugin architecture
- ✅ Fact Checker system with CLI and GUI
- ✅ Multi-model query generation
- ✅ Query performance tracking
- ✅ Citation hallucination prevention
- ✅ PostgreSQL audit trail
- ✅ Automatic database migrations

## License

BMLibrarian is open-source software. See the repository for license details.

---

**Next Steps:**
1. [Install BMLibrarian](Getting-Started) and set up your environment
2. [Follow the User Guide](User-Guide) to learn the basics
3. [Try the Qt GUI](Qt-GUI-Guide) for a visual research workflow
4. [Develop a Plugin](Plugin-Development-Guide) to extend functionality

Welcome to BMLibrarian! 🎉
