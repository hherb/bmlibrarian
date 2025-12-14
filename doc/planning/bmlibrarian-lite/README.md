# BMLibrarian Lite - Implementation Plan

This directory contains the implementation plan for BMLibrarian Lite, a lightweight version of BMLibrarian that works without PostgreSQL or local Ollama.

## Overview

BMLibrarian Lite provides:
- **Online LLM inference** via Anthropic Claude API
- **Online PubMed search** via NCBI E-utilities API
- **Local embeddings** via FastEmbed (ONNX, CPU-optimized)
- **Embedded storage** via ChromaDB + SQLite
- **Two-tab GUI**: Systematic Review + Document Interrogation

## Documents

| Document | Description |
|----------|-------------|
| [00_ARCHITECTURE_OVERVIEW.md](00_ARCHITECTURE_OVERVIEW.md) | High-level architecture and design decisions |
| [01_STORAGE_LAYER.md](01_STORAGE_LAYER.md) | Phase 1: ChromaDB + SQLite storage implementation |
| [02_EMBEDDING_PROVIDER.md](02_EMBEDDING_PROVIDER.md) | Phase 2: FastEmbed integration |
| [03_LITE_AGENTS.md](03_LITE_AGENTS.md) | Phase 3: Simplified agent implementations |
| [04_SIMPLIFIED_GUI.md](04_SIMPLIFIED_GUI.md) | Phase 4: Two-tab PySide6 interface |

## Implementation Phases

### Phase 1: Storage Layer
- `src/bmlibrarian/lite/constants.py`
- `src/bmlibrarian/lite/config.py`
- `src/bmlibrarian/lite/data_models.py`
- `src/bmlibrarian/lite/storage.py`

### Phase 2: Embedding Provider
- `src/bmlibrarian/lite/embeddings.py`
- `src/bmlibrarian/lite/chroma_embeddings.py`
- `src/bmlibrarian/lite/chunking.py`

### Phase 3: Lite Agents
- `src/bmlibrarian/lite/agents/base.py`
- `src/bmlibrarian/lite/agents/search_agent.py`
- `src/bmlibrarian/lite/agents/scoring_agent.py`
- `src/bmlibrarian/lite/agents/citation_agent.py`
- `src/bmlibrarian/lite/agents/reporting_agent.py`
- `src/bmlibrarian/lite/agents/interrogation_agent.py`

### Phase 4: Simplified GUI
- `src/bmlibrarian/lite/gui/app.py`
- `src/bmlibrarian/lite/gui/systematic_review_tab.py`
- `src/bmlibrarian/lite/gui/document_interrogation_tab.py`
- `src/bmlibrarian/lite/gui/settings_dialog.py`
- `bmlibrarian_lite.py` (entry point)

## Dependencies

```toml
[project.optional-dependencies]
lite = [
    "chromadb>=0.4.0",
    "fastembed>=0.3.0",
    "PySide6>=6.6.0",
    "anthropic>=0.25.0",
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
]
```

## Quick Start

```bash
# Install lite dependencies
uv add chromadb fastembed

# Run the lite GUI
uv run python bmlibrarian_lite.py
```

## Golden Rules Compliance

All implementation follows the BMLibrarian golden rules:
1. No magic numbers - constants in `constants.py`
2. No hardcoded paths - configuration-based
3. LLM abstraction - uses `bmlibrarian.llm.LLMClient`
4. Type hints everywhere
5. Docstrings on all public APIs
6. Comprehensive error handling
7. Centralized styling
8. DPI-aware dimensions
