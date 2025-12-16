# BMLibrarian Lite

A lightweight biomedical literature research tool - no PostgreSQL required.

BMLibrarian Lite is a simplified version of BMLibrarian that provides AI-powered literature search and analysis capabilities without requiring a PostgreSQL database. It uses ChromaDB for vector storage and SQLite for metadata, making it easy to install and use on any machine.

## Features

- **Systematic Literature Review**: Search PubMed, score documents, extract citations, and generate reports
- **Document Interrogation**: Interactive Q&A with loaded documents
- **Quality Assessment**: Automated study quality evaluation with evidence grading
- **Multiple LLM Providers**: Support for both Anthropic Claude (online) and Ollama (local)
- **Embedded Storage**: ChromaDB + SQLite - no external database needed
- **Cross-Platform GUI**: PySide6-based desktop application

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/hherb/bmlibrarian-lite.git
cd bmlibrarian-lite

# Create virtual environment and install
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

### Configuration

1. **Set your Anthropic API key** (for Claude):
   ```bash
   export ANTHROPIC_API_KEY="your-api-key-here"
   ```

2. **Or configure Ollama** (for local models):
   ```bash
   # Install Ollama: https://ollama.ai
   ollama pull llama3.2
   export OLLAMA_HOST="http://localhost:11434"
   ```

3. **Optional: Set your email for PubMed** (recommended):
   ```bash
   export NCBI_EMAIL="your@email.com"
   ```

### Running the Application

```bash
# Launch the GUI
python bmlibrarian_lite.py

# Or using the package entry point
python -m bmlibrarian_lite
```

### CLI Commands

```bash
# Show storage statistics
python bmlibrarian_lite.py stats

# Validate configuration
python bmlibrarian_lite.py validate --verbose

# Show current configuration
python bmlibrarian_lite.py config

# Clear all data
python bmlibrarian_lite.py clear
```

## Usage

### Systematic Review Workflow

1. **Enter your research question** in the main text area
2. **Click "Search"** to query PubMed
3. **Review found articles** and adjust filters as needed
4. **Score documents** for relevance (1-5 scale)
5. **Extract citations** from high-scoring documents
6. **Generate a report** synthesizing the evidence

### Document Interrogation

1. **Switch to the "Document Interrogation" tab**
2. **Load a document** (PDF, TXT, or MD file)
3. **Ask questions** about the document content
4. **Get AI-powered answers** with source references

## Configuration

Configuration is stored in `~/.bmlibrarian_lite/config.json`:

```json
{
  "llm": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "temperature": 0.7,
    "max_tokens": 4096
  },
  "embeddings": {
    "model": "BAAI/bge-small-en-v1.5"
  },
  "pubmed": {
    "email": "your@email.com"
  },
  "search": {
    "chunk_size": 512,
    "chunk_overlap": 50,
    "similarity_threshold": 0.7,
    "max_results": 100
  }
}
```

### LLM Providers

**Anthropic Claude** (default):
```json
{
  "llm": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514"
  }
}
```

**Ollama** (local):
```json
{
  "llm": {
    "provider": "ollama",
    "model": "llama3.2"
  }
}
```

You can also use the model string format: `anthropic:claude-sonnet-4-20250514` or `ollama:llama3.2`

## Requirements

- Python 3.12+
- Internet connection (for PubMed search and Claude API)
- ~500MB disk space for embeddings cache

### Dependencies

- **chromadb**: Vector storage
- **fastembed**: CPU-optimized embeddings
- **anthropic**: Claude API client
- **ollama**: Ollama API client
- **PySide6**: GUI framework
- **PyMuPDF**: PDF processing

## Differences from Full BMLibrarian

BMLibrarian Lite is designed for ease of use and portability:

| Feature | BMLibrarian | BMLibrarian Lite |
|---------|-------------|------------------|
| Database | PostgreSQL + pgvector | ChromaDB + SQLite |
| Embeddings | Ollama (local) | FastEmbed (CPU) |
| PDF Discovery | Full (Unpaywall, PMC, OpenAthens) | Not included |
| Multi-Agent Workflow | Full orchestration | Simplified workflow |
| Installation | Complex | Simple `pip install` |

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check .

# Run type checking
mypy src/
```

## License

MIT License - see LICENSE file for details.

## Acknowledgments

BMLibrarian Lite is derived from [BMLibrarian](https://github.com/hherb/bmlibrarian), a comprehensive biomedical literature research platform.

## Support

- **Issues**: [GitHub Issues](https://github.com/hherb/bmlibrarian-lite/issues)
- **Documentation**: See the `doc/` directory for detailed guides
