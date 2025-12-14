# BMLibrarian Lite User Guide

A lightweight, portable version of BMLibrarian for biomedical literature research without requiring PostgreSQL or local Ollama infrastructure.

## Overview

BMLibrarian Lite is designed for users who want to:
- Conduct systematic literature reviews using AI assistance
- Ask questions about loaded documents (Q&A)
- Work without installing PostgreSQL or running local LLM servers
- Have a portable, self-contained research environment

### Key Features

| Feature | Description |
|---------|-------------|
| **Systematic Review** | Search PubMed, score relevance, extract citations, generate reports |
| **Document Interrogation** | Load documents and ask questions with AI-powered answers |
| **Portable Storage** | All data stored locally in `~/.bmlibrarian_lite/` |
| **Online LLM** | Uses Anthropic Claude API (no local GPU required) |
| **Local Embeddings** | CPU-optimized embeddings via FastEmbed (works offline) |
| **No PostgreSQL** | Uses ChromaDB + SQLite for all storage needs |

## Quick Start

### Prerequisites

- Python 3.12 or later
- Anthropic API key ([get one here](https://console.anthropic.com/))
- Internet connection (for PubMed search and Claude API)

### Installation

```bash
# Clone the repository (if not already done)
git clone https://github.com/hherb/bmlibrarian.git
cd bmlibrarian

# Install dependencies
uv sync

# Run BMLibrarian Lite
uv run python bmlibrarian_lite.py
```

### First-Time Setup

1. Launch the application: `uv run python bmlibrarian_lite.py`
2. Click the **Settings** button in the status bar
3. Enter your **Anthropic API key**
4. Optionally enter your **email** for PubMed access (recommended by NCBI)
5. Click **Save**

## Systematic Review Tab

The Systematic Review tab provides a complete literature review workflow:

### Workflow Steps

```
1. Enter Question → 2. Search PubMed → 3. Score Documents → 4. Extract Citations → 5. Generate Report
```

### Step-by-Step Guide

1. **Enter Your Research Question**
   - Type a clear, specific research question in the text area
   - Example: "What are the cardiovascular benefits of regular aerobic exercise in adults over 50?"

2. **Configure Search Settings**
   - Adjust the **minimum score** threshold (1-5, default: 3)
   - Higher threshold = fewer but more relevant documents

3. **Click "Search"**
   - The system will:
     - Convert your question to an optimized PubMed query
     - Search PubMed and retrieve article metadata
     - Cache results locally with embeddings

4. **Review Progress**
   - Watch the progress bar for each step
   - Status messages show what's happening

5. **View Results**
   - **Documents found**: Total articles retrieved from PubMed
   - **Relevant documents**: Articles scoring >= minimum score
   - **Citations extracted**: Key passages supporting your question

6. **Export Report**
   - Click **Export** to save the generated report
   - Reports are saved to `~/.bmlibrarian_lite/exports/`

### Understanding Relevance Scores

| Score | Meaning |
|-------|---------|
| 5 | Directly answers the question with strong evidence |
| 4 | Highly relevant with substantial supporting data |
| 3 | Moderately relevant, provides useful context |
| 2 | Marginally relevant, tangential information |
| 1 | Not relevant to the research question |

## Document Interrogation Tab

Load documents and have AI-powered conversations about their content.

### Supported Document Types

- **PDF files** (`.pdf`) - Research papers, reports
- **Text files** (`.txt`) - Plain text documents
- **Markdown files** (`.md`) - Formatted documents

### How to Use

1. **Load a Document**
   - Click **Load Document** button
   - Select a PDF or text file
   - Wait for processing (chunking and embedding)

2. **Ask Questions**
   - Type your question in the input field
   - Press Enter or click Send
   - The AI will answer based on the document content

3. **Review Conversation**
   - Questions and answers are displayed in chat format
   - Each answer is grounded in the actual document content

### Example Questions

For a research paper about diabetes treatment:
- "What were the main findings of this study?"
- "What medications were compared in this trial?"
- "What were the inclusion criteria for participants?"
- "What limitations did the authors acknowledge?"

## Settings

Access settings via the **Settings** button in the status bar.

### LLM Settings

| Setting | Description | Default |
|---------|-------------|---------|
| Provider | LLM provider | `anthropic` |
| Model | Claude model to use | `claude-sonnet-4-20250514` |
| Temperature | Response creativity (0.0-1.0) | `0.3` |
| Max Tokens | Maximum response length | `4096` |

### Embedding Settings

| Setting | Description | Default |
|---------|-------------|---------|
| Model | Embedding model | `BAAI/bge-small-en-v1.5` |
| Cache Directory | Where to cache models | Auto |

Available embedding models:
- `BAAI/bge-small-en-v1.5` - Fast, good quality (recommended)
- `BAAI/bge-base-en-v1.5` - Better quality, slower
- `intfloat/multilingual-e5-small` - Multi-language support

### PubMed Settings

| Setting | Description | Default |
|---------|-------------|---------|
| Email | Your email (for NCBI) | (empty) |
| API Key | NCBI API key (optional) | (empty) |

**Note**: NCBI requests that you provide an email for polite API access. An API key increases your rate limit from 3 to 10 requests per second.

### Search Settings

| Setting | Description | Default |
|---------|-------------|---------|
| Chunk Size | Characters per document chunk | `8000` |
| Chunk Overlap | Overlap between chunks | `200` |
| Similarity Threshold | Minimum similarity for search | `0.5` |
| Max Results | Maximum search results | `20` |

## Data Storage

All data is stored in `~/.bmlibrarian_lite/`:

```
~/.bmlibrarian_lite/
├── config.json         # User configuration
├── .env                # API keys (optional)
├── metadata.db         # SQLite database
├── chroma_db/          # ChromaDB vector storage
│   ├── documents/      # PubMed articles
│   └── chunks/         # Document chunks
├── reviews/            # Review checkpoints
├── exports/            # Exported reports
└── cache/              # Temporary cache
```

### Backup Your Data

To backup your BMLibrarian Lite data:

```bash
# Create a backup
cp -r ~/.bmlibrarian_lite ~/bmlibrarian_lite_backup_$(date +%Y%m%d)

# Restore from backup
cp -r ~/bmlibrarian_lite_backup_20241214 ~/.bmlibrarian_lite
```

### Clear All Data

To start fresh:

```bash
# Remove all data
rm -rf ~/.bmlibrarian_lite

# Or from Python
from bmlibrarian.lite import LiteConfig, LiteStorage
storage = LiteStorage(LiteConfig.load())
storage.clear_all(confirm=True)  # WARNING: Permanent!
```

## Environment Variables

You can set API keys via environment variables instead of the config file:

```bash
# In ~/.bmlibrarian_lite/.env
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
NCBI_API_KEY=xxxxx
```

Or export them in your shell:

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
```

## Command Line Options

### Basic Usage

```bash
# Launch the GUI
uv run python bmlibrarian_lite.py

# With verbose logging
uv run python bmlibrarian_lite.py --verbose

# Show version
uv run python bmlibrarian_lite.py --version

# Show help
uv run python bmlibrarian_lite.py --help
```

### Quick Search (Non-Interactive)

```bash
# Run a search without GUI (coming soon)
uv run python bmlibrarian_lite.py search "cardiovascular benefits of exercise"

# Show storage statistics
uv run python bmlibrarian_lite.py stats
```

## Troubleshooting

### "API key not configured"

1. Go to Settings
2. Enter your Anthropic API key
3. Click Save

### "No results found"

- Try a broader search query
- Check if the query is too specific
- Verify your internet connection

### "Embedding model download failed"

- Check internet connection
- The first run downloads the embedding model (~50MB)
- Subsequent runs use the cached model

### "ChromaDB error"

- Try clearing the ChromaDB directory:
  ```bash
  rm -rf ~/.bmlibrarian_lite/chroma_db
  ```
- Restart the application

### Slow Performance

- Reduce `max_results` in settings for faster searches
- Use the smaller embedding model (`bge-small-en-v1.5`)
- Close other applications to free memory

## Comparison: Lite vs Full Version

| Feature | BMLibrarian Lite | BMLibrarian Full |
|---------|-----------------|------------------|
| Database | ChromaDB + SQLite | PostgreSQL + pgvector |
| LLM | Anthropic Claude (online) | Ollama (local) |
| Embeddings | FastEmbed (CPU) | Ollama (GPU optional) |
| Setup | Minimal | PostgreSQL required |
| Offline Use | Partial (embeddings only) | Full support |
| Storage | Local files | PostgreSQL database |
| Multi-user | No | Yes |
| Scale | Personal use | Enterprise |

## Tips for Best Results

### Writing Good Research Questions

**Good questions:**
- "What is the efficacy of metformin versus sulfonylureas for type 2 diabetes glycemic control?"
- "What are the risk factors for postoperative cognitive dysfunction in elderly patients?"

**Less effective questions:**
- "diabetes treatment" (too broad)
- "What is the best medicine?" (too vague)

### Improving Search Results

1. **Be specific** about the population, intervention, and outcomes
2. **Use medical terminology** when appropriate
3. **Include timeframes** if relevant (e.g., "in the past 5 years")
4. **Adjust the minimum score** to balance quality vs quantity

### Document Interrogation Best Practices

1. **Load focused documents** - The AI works better with specific papers than entire textbooks
2. **Ask specific questions** - "What was the sample size?" is better than "Tell me about the study"
3. **Reference the document** - "According to this paper, what..." helps ground the response

## Getting Help

- **GitHub Issues**: [github.com/hherb/bmlibrarian/issues](https://github.com/hherb/bmlibrarian/issues)
- **Documentation**: See other guides in `doc/users/`
- **Full Version**: Consider BMLibrarian Full for advanced features

## Version History

### Phase 4 (Current)
- Simplified PySide6 GUI with two-tab interface
- Settings dialog for configuration
- Export functionality for reports

### Phase 3
- Simplified agents (Search, Scoring, Citation, Reporting, Interrogation)
- Stateless agent design for simplicity

### Phase 2
- FastEmbed integration for local embeddings
- ChromaDB embedding function wrapper

### Phase 1
- Storage layer with ChromaDB + SQLite
- Configuration system with JSON persistence
- Data models and constants
