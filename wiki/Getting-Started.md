# Getting Started with BMLibrarian

This guide will help you install and configure BMLibrarian for the first time.

## Prerequisites

Before installing BMLibrarian, ensure you have the following:

### Required Software

1. **Python 3.12 or higher**
   ```bash
   python --version  # Should show 3.12.0 or higher
   ```

2. **PostgreSQL 14 or higher** with **pgvector extension**
   ```bash
   psql --version  # Should show PostgreSQL 14.0 or higher
   ```

3. **Ollama** for local LLM inference
   ```bash
   ollama --version  # Install from https://ollama.ai
   ```

4. **uv** package manager (recommended)
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

### System Requirements

- **RAM**: 16GB minimum, 32GB recommended (for local LLM models)
- **Storage**: 500GB+ recommended for full PubMed database
- **OS**: Linux, macOS, or Windows (WSL recommended for Windows)

## Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/hherb/bmlibrarian.git
cd bmlibrarian
```

### Step 2: Install Dependencies

Using `uv` (recommended):
```bash
uv sync
```

Using `pip`:
```bash
pip install -e .
```

### Step 3: Set Up PostgreSQL Database

Create a PostgreSQL database with the pgvector extension:

```bash
# Create database
createdb knowledgebase

# Enable pgvector extension
psql knowledgebase -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Step 4: Configure Environment

Copy the example environment file and edit it:

```bash
cp test_database.env.example .env
```

Edit `.env` with your database credentials:

```env
POSTGRES_DB=knowledgebase
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

PDF_BASE_DIR=~/knowledgebase/pdf
```

### Step 5: Configure BMLibrarian

Create the configuration file:

```bash
mkdir -p ~/.bmlibrarian
```

Create `~/.bmlibrarian/config.json`:

```json
{
  "database": {
    "name": "knowledgebase",
    "user": "your_username",
    "password": "your_password",
    "host": "localhost",
    "port": "5432"
  },
  "ollama": {
    "host": "http://localhost:11434"
  },
  "agents": {
    "query": {
      "model": "medgemma4B_it_q8:latest",
      "temperature": 0.1,
      "top_p": 0.9
    },
    "scoring": {
      "model": "gpt-oss:20b",
      "temperature": 0.1,
      "top_p": 0.9
    },
    "citation": {
      "model": "gpt-oss:20b",
      "temperature": 0.1,
      "top_p": 0.9
    },
    "reporting": {
      "model": "gpt-oss:20b",
      "temperature": 0.2,
      "top_p": 0.9
    }
  }
}
```

### Step 6: Install Ollama Models

Download the recommended models:

```bash
# Fast model for query generation
ollama pull medgemma4B_it_q8:latest

# Powerful model for analysis and reporting
ollama pull gpt-oss:20b
```

### Step 7: Initialize Database and Import Data

Run the setup script to create the database schema and import initial data:

```bash
# Full setup with medRxiv and PubMed sample data
uv run python initial_setup_and_download.py .env

# Quick setup (schema only, no data import)
uv run python initial_setup_and_download.py .env --skip-medrxiv --skip-pubmed

# Limited import for testing
uv run python initial_setup_and_download.py .env --medrxiv-days 7 --pubmed-max-results 1000
```

This will:
- Create the database schema
- Import medRxiv preprints (optional)
- Import PubMed articles (optional)
- Generate embeddings for semantic search (optional)

**Note**: Full PubMed import requires ~400GB of storage and several days. Start with the quick setup for testing.

## Verification

### Test Database Connection

```bash
uv run python -c "
from bmlibrarian.database import get_db_manager
db = get_db_manager()
with db.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute('SELECT COUNT(*) FROM document;')
        print(f'Documents in database: {cur.fetchone()[0]}')
"
```

### Test Ollama Connection

```bash
curl http://localhost:11434/api/tags
```

Should return a list of installed models.

### Test Configuration

```bash
uv run python -c "
from bmlibrarian.config import get_config
config = get_config()
print('Configuration loaded successfully!')
print(f'Database: {config[\"database\"][\"name\"]}')
print(f'Ollama: {config[\"ollama\"][\"host\"]}')
"
```

## First Run

### Option 1: Qt GUI (Recommended for New Users)

Launch the desktop application:

```bash
uv run python bmlibrarian_qt.py
```

The GUI provides:
- Research tab for automated literature research
- Configuration tab for settings
- Query Lab for interactive query development
- PICO Lab for systematic review components
- Document Interrogation for AI-powered document Q&A

### Option 2: Interactive CLI

Launch the command-line interface:

```bash
uv run python bmlibrarian_cli.py
```

Follow the prompts to:
1. Enter your research question
2. Review and edit the generated database query
3. Score documents for relevance
4. Extract citations
5. Generate a comprehensive report

### Option 3: Fact Checker

Validate biomedical statements:

```bash
# Create a sample statements file
cat > statements.json << 'EOF'
[
  {
    "id": 1,
    "statement": "Aspirin reduces the risk of cardiovascular events.",
    "expected_answer": "yes"
  },
  {
    "id": 2,
    "statement": "Vitamin C prevents the common cold.",
    "expected_answer": "no"
  }
]
EOF

# Run fact checker
uv run python fact_checker_cli.py statements.json -o results.json

# Review results in GUI
uv run python fact_checker_review_gui.py --input-file results.db
```

## Common Issues and Solutions

### Issue: "Connection to Ollama failed"

**Solution**: Ensure Ollama is running:
```bash
ollama serve
```

### Issue: "Database connection failed"

**Solution**: Check PostgreSQL is running and credentials are correct:
```bash
psql -h localhost -U your_username -d knowledgebase
```

### Issue: "pgvector extension not found"

**Solution**: Install pgvector extension:
```bash
# Ubuntu/Debian
sudo apt install postgresql-15-pgvector

# macOS (using Homebrew)
brew install pgvector

# Then enable in your database
psql knowledgebase -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Issue: "Model not found in Ollama"

**Solution**: Pull the model:
```bash
ollama pull medgemma4B_it_q8:latest
ollama pull gpt-oss:20b
```

### Issue: "Out of memory during import"

**Solution**: Import data in smaller batches:
```bash
# Import only recent medRxiv preprints
uv run python medrxiv_import_cli.py update --days 30

# Import PubMed by specific queries instead of bulk download
uv run python pubmed_import_cli.py search "COVID-19" --max-results 10000
```

## Data Import Options

### Quick Start (Minimal Data)

For testing and development:

```bash
# Import last 7 days of medRxiv
uv run python medrxiv_import_cli.py update --days 7

# Import specific PubMed articles
uv run python pubmed_import_cli.py search "machine learning medical imaging" --max-results 1000
```

### Moderate Setup (Recommended)

For typical research use:

```bash
# Import last 90 days of medRxiv
uv run python medrxiv_import_cli.py update --days 90 --download-pdfs

# Import PubMed articles by topic
uv run python pubmed_import_cli.py search "cardiovascular disease" --max-results 50000
uv run python pubmed_import_cli.py search "diabetes treatment" --max-results 50000
```

### Full Mirror (Advanced)

For complete PubMed mirror (~400GB):

```bash
# Download complete PubMed baseline
uv run python pubmed_bulk_cli.py download-baseline

# Import baseline into database (takes several days)
uv run python pubmed_bulk_cli.py import --type baseline

# Set up daily updates
uv run python pubmed_bulk_cli.py sync --updates-only
```

## Next Steps

Now that BMLibrarian is installed and configured:

1. **Learn the Basics**
   - Read the [User Guide](User-Guide) for a comprehensive tutorial
   - Explore the [Qt GUI Guide](Qt-GUI-Guide) for desktop application features
   - Check the [CLI Reference](CLI-Reference) for command-line tools

2. **Try Advanced Features**
   - [Multi-Model Query Generation](Multi-Model-Queries) - Use multiple AI models for better results
   - [Fact Checker Guide](Fact-Checker-Guide) - Validate biomedical statements
   - [Query Optimization](Query-Optimization) - Improve search quality

3. **Customize BMLibrarian**
   - [Configuration Guide](Configuration-Guide) - Tune parameters for your needs
   - [Plugin Development](Plugin-Development-Guide) - Extend the Qt GUI
   - [Agent Development](Agent-Development) - Create custom AI agents

4. **Join the Community**
   - Report bugs on [GitHub Issues](https://github.com/hherb/bmlibrarian/issues)
   - Share your research workflows
   - Contribute to the project - see [Contributing Guidelines](Contributing)

## Quick Reference

### Common Commands

```bash
# Launch Qt GUI
uv run python bmlibrarian_qt.py

# Launch CLI
uv run python bmlibrarian_cli.py

# Run fact checker
uv run python fact_checker_cli.py statements.json -o results.json

# Import medRxiv preprints
uv run python medrxiv_import_cli.py update --days 30 --download-pdfs

# Import PubMed articles
uv run python pubmed_import_cli.py search "your query" --max-results 10000

# Generate embeddings
uv run python embed_documents_cli.py embed --source medrxiv --limit 1000

# Check import status
uv run python medrxiv_import_cli.py status
uv run python pubmed_import_cli.py status
```

### Important File Locations

- **Configuration**: `~/.bmlibrarian/config.json`
- **GUI Settings**: `~/.bmlibrarian/gui_config.json`
- **Database Environment**: `.env` (in project root)
- **PDF Storage**: `~/knowledgebase/pdf/` (configurable)
- **Log Files**: `~/.bmlibrarian/logs/`

## Getting Help

If you encounter issues:

1. Check the [Troubleshooting Guide](Troubleshooting)
2. Search [GitHub Issues](https://github.com/hherb/bmlibrarian/issues)
3. Review relevant documentation pages
4. Ask in GitHub Discussions
5. Report bugs with detailed error messages

---

**Congratulations!** 🎉 BMLibrarian is now ready to use. Happy researching!
