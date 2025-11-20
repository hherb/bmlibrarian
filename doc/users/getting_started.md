# Getting Started with BMLibrarian

BMLibrarian is a comprehensive AI-powered biomedical literature analysis platform featuring multi-agent research workflows, desktop GUI applications, and advanced literature review capabilities. This guide will help you get started with installation, configuration, and running your first research workflow.

## Overview

BMLibrarian provides:
- **Multi-Agent System**: AI agents for query processing, document scoring, citation extraction, and report generation
- **Qt Desktop GUI**: Modern desktop application with plugin-based tabbed interface
- **Command-Line Interface**: Interactive CLI for research workflows
- **Fact-Checking System**: Automated verification of biomedical statements
- **Local Processing**: All AI processing runs locally via Ollama (no cloud dependencies)
- **PostgreSQL Backend**: Robust database for literature storage and semantic search

## Prerequisites

Before installing BMLibrarian, ensure you have:

### 1. Python
- **Version**: Python 3.12 or higher
- **Check version**: `python --version`

### 2. PostgreSQL Database
- **Version**: PostgreSQL 12 or later
- **Required Extensions**:
  - `pgvector` - For vector similarity search
  - `pg_trgm` - For full-text search
  - `uuid-ossp` - For UUID generation

**Installation**:
```bash
# Ubuntu/Debian
sudo apt install postgresql postgresql-contrib postgresql-14-pgvector

# macOS (via Homebrew)
brew install postgresql@14
brew install pgvector

# Then enable extensions in your database:
psql -d your_database -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql -d your_database -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
psql -d your_database -c "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"
```

### 3. Ollama (Local AI Server)
- **Purpose**: Runs local language models for AI processing
- **Installation**: Download from [ollama.ai](https://ollama.ai) or:

```bash
# Linux
curl -fsSL https://ollama.ai/install.sh | sh

# macOS
brew install ollama

# Windows
# Download installer from ollama.ai
```

**Start Ollama**:
```bash
ollama serve
```

**Download Required Models**:
```bash
# Primary model for complex tasks (recommended)
ollama pull gpt-oss:20b

# Fast model for quick processing
ollama pull medgemma4B_it_q8:latest

# Optional: Medical domain model
ollama pull medgemma-27b-text-it-Q8_0:latest
```

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd bmlibrarian
```

### 2. Install Dependencies

BMLibrarian uses `uv` for dependency management:

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies
uv sync
```

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# Database connection settings
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
POSTGRES_DB=knowledgebase

# Optional: PDF storage directory
PDF_BASE_DIR=~/knowledgebase/pdf

# Ollama server URL (usually default)
OLLAMA_HOST=http://localhost:11434
```

### 4. Initialize Database

Run the database setup script:

```bash
# Complete setup with test data import
uv run python initial_setup_and_download.py test_database.env

# Or schema-only setup (faster, no data import)
uv run python initial_setup_and_download.py test.env --skip-medrxiv --skip-pubmed
```

This will:
- Create the database schema
- Set up required extensions
- Import initial test data (optional)
- Create configuration directory at `~/.bmlibrarian/`

## Configuration

### 1. Create Configuration File

BMLibrarian stores configuration at `~/.bmlibrarian/config.json`. On first run, a default configuration is created automatically.

**Manual Configuration** (optional):

Create `~/.bmlibrarian/config.json`:

```json
{
  "ollama": {
    "host": "http://localhost:11434",
    "default_model": "gpt-oss:20b"
  },
  "database": {
    "host": "localhost",
    "port": 5432,
    "database": "knowledgebase"
  },
  "agents": {
    "query_agent": {
      "model": "medgemma4B_it_q8:latest",
      "temperature": 0.1,
      "top_p": 0.9
    },
    "scoring_agent": {
      "model": "gpt-oss:20b",
      "temperature": 0.2
    },
    "citation_agent": {
      "model": "gpt-oss:20b",
      "temperature": 0.1,
      "max_citations": 10
    },
    "reporting_agent": {
      "model": "gpt-oss:20b",
      "temperature": 0.3
    }
  }
}
```

### 2. Verify Installation

Test Ollama connection:
```bash
curl http://localhost:11434/api/tags
```

Test database connection:
```bash
psql -h localhost -U your_username -d knowledgebase -c "SELECT COUNT(*) FROM schema_migrations;"
```

## First Research Workflow

### Using the Qt GUI (Recommended)

Launch the Qt desktop application:

```bash
uv run python bmlibrarian_qt.py
```

**Workflow**:
1. Click the **Research** tab
2. Enter your research question:
   ```
   What are the cardiovascular benefits of exercise?
   ```
3. Click **Start Research**
4. Follow the interactive workflow:
   - Query generation (AI converts question to database query)
   - Document search (searches literature database)
   - Document scoring (AI scores relevance)
   - Citation extraction (AI extracts relevant passages)
   - Report generation (AI synthesizes findings)
5. Review and export the generated report

**Other Tabs**:
- **Search**: Advanced document search with filters
- **Fact Checker**: Review and annotate fact-checking results
- **Query Lab**: Experiment with query generation
- **Configuration**: Adjust agent settings and models

### Using the Command-Line Interface

Launch the interactive CLI:

```bash
uv run python bmlibrarian_cli.py
```

Follow the prompts to:
1. Enter your research question
2. Review and edit the generated database query
3. Review search results
4. Adjust scoring parameters if needed
5. Extract citations from relevant documents
6. Generate and review the research report
7. Export to markdown file

**Quick Mode** (for testing):
```bash
uv run python bmlibrarian_cli.py --quick
```

### Automated Mode

Run without interaction:

```bash
uv run python bmlibrarian_cli.py --auto "What are the effects of vitamin D supplementation?"
```

## Importing Literature Data

### PubMed Articles (Targeted Import)

Import specific articles by search query:

```bash
# Search and import by query
uv run python pubmed_import_cli.py search "COVID-19 vaccine" --max-results 100

# Import by PMID list
uv run python pubmed_import_cli.py pmids 12345678 23456789 34567890
```

### medRxiv Preprints

Import recent preprints:

```bash
# Update with recent articles
uv run python medrxiv_import_cli.py update --download-pdfs

# Check status
uv run python medrxiv_import_cli.py status
```

### Generate Embeddings (for Semantic Search)

After importing documents, generate embeddings:

```bash
# Generate embeddings for PubMed articles
uv run python embed_documents_cli.py embed --source pubmed --limit 1000

# Generate embeddings for medRxiv articles
uv run python embed_documents_cli.py embed --source medrxiv --limit 1000

# Check status
uv run python embed_documents_cli.py status
```

## Using the Fact-Checker

The fact-checker verifies biomedical statements against literature evidence.

### 1. Create Input File

Create `statements.json`:

```json
[
  {
    "statement": "Vitamin D deficiency is associated with increased COVID-19 severity",
    "answer": "yes"
  },
  {
    "statement": "All antibiotics are effective against viral infections",
    "answer": "no"
  }
]
```

### 2. Run Fact-Checker

```bash
uv run python fact_checker_cli.py statements.json
```

Results are stored in PostgreSQL (factcheck schema). Optional JSON export:

```bash
uv run python fact_checker_cli.py statements.json -o results.json
```

### 3. Review Results in Qt GUI

The Fact-Checker tab in the Qt GUI provides a review interface:

```bash
uv run python bmlibrarian_qt.py
# Click "Fact Checker" tab
```

## Configuration Management

### Using Qt GUI Configuration Tab

1. Launch Qt GUI: `uv run python bmlibrarian_qt.py`
2. Click **Configuration** tab
3. Adjust settings:
   - Select models for each agent
   - Tune temperature and top-p parameters
   - Set default thresholds
4. Click **Save** to persist changes

### Manual Configuration

Edit `~/.bmlibrarian/config.json` directly, then restart the application.

## Common Commands Quick Reference

```bash
# Launch applications
uv run python bmlibrarian_qt.py              # Qt GUI (all features)
uv run python bmlibrarian_cli.py             # Interactive CLI
uv run python fact_checker_cli.py input.json # Fact-checker CLI

# Import literature
uv run python pubmed_import_cli.py search "query" --max-results 100
uv run python medrxiv_import_cli.py update --download-pdfs

# Generate embeddings
uv run python embed_documents_cli.py embed --source pubmed --limit 1000

# Testing
uv run python bmlibrarian_cli.py --quick     # Quick test mode
uv run pytest tests/                          # Run test suite
```

## Next Steps

Now that you have BMLibrarian installed and configured:

- **[Qt GUI User Guide](qt_gui_user_guide.md)**: Learn about the desktop application
- **[CLI Guide](cli_guide.md)**: Master the command-line interface
- **[Workflow Guide](workflow_guide.md)**: Understand the multi-agent research process
- **[Agents Guide](agents_guide.md)**: Learn about individual AI agents
- **[Fact Checker Guide](fact_checker_guide.md)**: Use the fact-checking system
- **[Configuration Guide](configuration_guide.md)**: Advanced configuration options

## Troubleshooting

### Ollama Not Responding

```bash
# Check Ollama status
curl http://localhost:11434/api/tags

# Restart Ollama
ollama serve
```

### Database Connection Issues

```bash
# Test connection
psql -h localhost -U your_username -d knowledgebase

# Check PostgreSQL status
sudo systemctl status postgresql  # Linux
brew services list                # macOS
```

### Qt GUI Won't Start

```bash
# Check Python version
python --version  # Must be 3.12+

# Reinstall dependencies
uv sync

# Check logs
tail -f ~/.bmlibrarian/gui_qt.log
```

### Models Not Found

```bash
# List installed models
ollama list

# Pull required models
ollama pull gpt-oss:20b
ollama pull medgemma4B_it_q8:latest
```

## Getting Help

- **[Troubleshooting Guide](troubleshooting.md)**: Comprehensive troubleshooting
- **[FAQ](qt_gui_user_guide.md#faq)**: Frequently asked questions
- **Logs**: Check `~/.bmlibrarian/gui_qt.log` for errors
- **Documentation**: Browse the complete documentation in `doc/`

---

**Welcome to BMLibrarian!**

You're now ready to start conducting AI-powered biomedical literature research. We recommend starting with the Qt GUI to familiarize yourself with the workflow, then exploring the CLI and fact-checker as needed.

Happy researching!
