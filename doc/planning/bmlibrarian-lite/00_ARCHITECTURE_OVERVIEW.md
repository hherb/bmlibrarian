# BMLibrarian Lite - Architecture Overview

## Purpose

BMLibrarian Lite is a lightweight, portable version of BMLibrarian designed for users without powerful hardware or complex infrastructure requirements. It provides core research capabilities using:

- **Online LLM inference** via Anthropic Claude API (no local Ollama required)
- **Online PubMed search** via NCBI E-utilities API (no local database mirror)
- **Local embeddings** via FastEmbed (ONNX-based, CPU-optimized)
- **Embedded storage** via ChromaDB + SQLite (no PostgreSQL required)

## Target Users

- Researchers without access to powerful GPUs
- Users who cannot install PostgreSQL
- Mobile/laptop users wanting portable installations
- Quick-start users wanting minimal setup time

## Core Design Philosophy

1. **Minimal Dependencies**: Single `pip install` with no external services
2. **Portable**: All data in `~/.bmlibrarian_lite/` directory
3. **Offline-Capable**: Embeddings and vector search work offline
4. **Online-When-Needed**: Only LLM inference and PubMed queries need internet
5. **Golden Rules Compliant**: Follow all BMLibrarian coding standards

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     BMLibrarian Lite GUI                         │
│  ┌─────────────────────────┐  ┌─────────────────────────────┐   │
│  │   Systematic Review     │  │   Document Interrogation    │   │
│  │         Tab             │  │           Tab               │   │
│  └───────────┬─────────────┘  └──────────────┬──────────────┘   │
│              │                               │                   │
├──────────────┴───────────────────────────────┴──────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    LLMClient                             │    │
│  │            (Anthropic Claude Provider)                   │    │
│  │         Uses existing bmlibrarian.llm module             │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│  ┌──────────────────────────┴──────────────────────────────┐    │
│  │                                                          │    │
│  │  ┌─────────────────┐  ┌─────────────────┐               │    │
│  │  │  PubMed Search  │  │   FastEmbed     │               │    │
│  │  │  (E-utilities)  │  │ (ONNX/CPU)      │               │    │
│  │  │  Uses existing  │  │ bge-small-en    │               │    │
│  │  │  pubmed_search  │  │ 384 dimensions  │               │    │
│  │  └────────┬────────┘  └────────┬────────┘               │    │
│  │           │                    │                         │    │
│  └───────────┴────────────────────┴─────────────────────────┘    │
│                              │                                   │
│  ┌───────────────────────────┴──────────────────────────────┐   │
│  │                     LiteStorage                           │   │
│  │  ┌─────────────────────┐  ┌─────────────────────────┐    │   │
│  │  │      ChromaDB       │  │        SQLite           │    │   │
│  │  │  (Vector Storage)   │  │   (Metadata/Config)     │    │   │
│  │  │  - documents        │  │   - search_sessions     │    │   │
│  │  │  - chunks           │  │   - review_checkpoints  │    │   │
│  │  │  - embeddings       │  │   - user_settings       │    │   │
│  │  └─────────────────────┘  └─────────────────────────┘    │   │
│  │              ~/.bmlibrarian_lite/                         │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Component Overview

### 1. Storage Layer (`src/bmlibrarian/lite/storage.py`)

**LiteStorage** - Unified embedded storage abstraction

| Component | Technology | Purpose |
|-----------|------------|---------|
| Vector Store | ChromaDB | Document embeddings, semantic search |
| Metadata Store | SQLite | Search sessions, checkpoints, config |
| File Storage | Local filesystem | PDF cache, exports |

**Key Design Decisions:**
- ChromaDB handles embedding storage and similarity search
- SQLite stores structured metadata (no pgvector dependency)
- All data persisted to `~/.bmlibrarian_lite/`

### 2. Embedding Provider (`src/bmlibrarian/lite/embeddings.py`)

**LiteEmbedder** - FastEmbed wrapper for CPU-optimized embeddings

| Model | Dimensions | Size | Use Case |
|-------|------------|------|----------|
| `BAAI/bge-small-en-v1.5` | 384 | ~50MB | Default (fast) |
| `BAAI/bge-base-en-v1.5` | 768 | ~130MB | Better quality |

**Key Design Decisions:**
- FastEmbed uses ONNX runtime (no PyTorch dependency)
- CPU-optimized, works on any hardware
- ChromaDB integration via `FastEmbedEmbeddingFunction`

### 3. Lite Agents (`src/bmlibrarian/lite/agents/`)

Simplified agents that work without PostgreSQL:

| Agent | Purpose | Database Dependency |
|-------|---------|---------------------|
| `LiteSearchAgent` | PubMed API search + result caching | ChromaDB |
| `LiteScoringAgent` | Document relevance scoring | None (stateless) |
| `LiteCitationAgent` | Citation extraction | None (stateless) |
| `LiteReportingAgent` | Report generation | None (stateless) |
| `LiteInterrogationAgent` | Document Q&A | ChromaDB (chunks) |

### 4. Simplified GUI (`src/bmlibrarian/lite/gui/`)

Two-tab PySide6 interface:

| Tab | Features |
|-----|----------|
| **Systematic Review** | Research question → PubMed search → scoring → report |
| **Document Interrogation** | Load PDF/text → chunk → embed → Q&A chat |

## Dependency Comparison

| Dependency | Full BMLibrarian | Lite Version |
|------------|------------------|--------------|
| PostgreSQL | Required | Not needed |
| pgvector | Required | Not needed |
| Ollama | Required (embeddings) | Not needed |
| PySide6 | Required | Required |
| psycopg | Required | Not needed |
| chromadb | Not used | Required |
| fastembed | Not used | Required |
| anthropic | Required | Required |

## Installation

```bash
# Lite version install
pip install bmlibrarian-lite

# Or from source
uv add chromadb fastembed anthropic PySide6 httpx python-dotenv
```

## Configuration

```json
// ~/.bmlibrarian_lite/config.json
{
    "llm": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "temperature": 0.3
    },
    "embeddings": {
        "model": "BAAI/bge-small-en-v1.5"
    },
    "pubmed": {
        "email": "user@example.com",
        "api_key": null
    },
    "storage": {
        "data_dir": "~/.bmlibrarian_lite"
    }
}
```

## Data Directory Structure

```
~/.bmlibrarian_lite/
├── config.json              # User configuration
├── chroma_db/               # ChromaDB vector store
│   ├── documents/           # PubMed abstracts
│   └── chunks/              # Document chunks for interrogation
├── metadata.db              # SQLite metadata database
├── reviews/                 # Systematic review checkpoints
│   └── {review_id}/
│       ├── checkpoint.json
│       └── report.md
├── cache/                   # Temporary cache
│   └── pubmed/              # PubMed API response cache
└── exports/                 # Exported reports
    └── {timestamp}_report.pdf
```

## Golden Rules Compliance

| Rule | Lite Implementation |
|------|---------------------|
| 1. Input validation | All user input validated before processing |
| 2. No magic numbers | Constants in `constants.py` module |
| 3. No hardcoded paths | All paths from config or `DEFAULT_DATA_DIR` |
| 4. LLM abstraction | Uses existing `bmlibrarian.llm.LLMClient` |
| 5. Database abstraction | `LiteStorage` class, no direct SQLite access |
| 6. Type hints | All parameters typed |
| 7. Docstrings | All functions documented |
| 8. Error handling | Comprehensive logging and user feedback |
| 9. Centralized styling | Uses existing stylesheet system |
| 10. DPI scaling | Uses existing `dpi_scale.py` |
| 11. Pure functions | Stateless agent operations where possible |
| 12. Documentation | User and developer docs |
| 13. Tests | Unit tests for all components |
| 14. No truncation | Full data processing |

## Implementation Phases

### Phase 1: Storage Layer (Steps 01-02)
- LiteStorage with ChromaDB + SQLite
- Data models and constants
- Configuration management

### Phase 2: Embedding Provider (Step 03)
- FastEmbed integration
- ChromaDB embedding function
- Model management

### Phase 3: Lite Agents (Steps 04-06)
- LiteSearchAgent (PubMed + ChromaDB caching)
- LiteScoringAgent, LiteCitationAgent, LiteReportingAgent
- LiteInterrogationAgent

### Phase 4: Simplified GUI (Steps 07-08)
- Two-tab interface
- Systematic Review tab
- Document Interrogation tab

### Phase 5: Integration (Steps 09-10)
- Entry point script
- Testing and documentation

## Reuse Strategy

Maximize reuse of existing BMLibrarian code:

| Component | Strategy |
|-----------|----------|
| `bmlibrarian.llm.LLMClient` | Use directly (supports Anthropic) |
| `bmlibrarian.pubmed_search` | Use directly (API-based) |
| `bmlibrarian.gui.qt.resources` | Reuse styling system |
| `bmlibrarian.gui.qt.widgets` | Reuse where possible |
| `DocumentScoringAgent` | Adapt for stateless operation |
| `CitationFinderAgent` | Adapt for stateless operation |
| `ReportingAgent` | Adapt for stateless operation |

## Success Criteria

1. **Installation**: Single `pip install` with no manual setup
2. **Startup Time**: < 5 seconds to launch GUI
3. **Search Performance**: < 30 seconds for PubMed search + scoring
4. **Embedding Speed**: < 1 second per abstract (CPU)
5. **Storage Footprint**: < 500MB for typical usage
6. **Portability**: Works on Windows, macOS, Linux without modifications
