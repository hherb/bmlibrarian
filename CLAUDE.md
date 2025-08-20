# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BMLibrarian is a comprehensive Python library providing AI-powered access to biomedical literature databases. It features a multi-agent architecture with specialized agents for query processing, document scoring, citation extraction, and report generation, all coordinated through an advanced task queue orchestration system.

## Dependencies and Environment

- **Python**: Requires Python >=3.12
- **Database**: PostgreSQL with pgvector extension for semantic search
- **AI/LLM**: Ollama for local language model inference
- **Main dependencies**: 
  - psycopg >=3.2.9 for PostgreSQL connectivity
  - requests >=2.31.0 for HTTP communication with Ollama
- **Package manager**: Uses `uv` for dependency management (uv.lock present)

## Configuration

- Environment variables are configured in `.env` file
- **Database connection parameters:**
  - `POSTGRES_DB`: Database name (default: "knowledgebase")  
  - `POSTGRES_USER`: Database user
  - `POSTGRES_PASSWORD`: Database password
  - `POSTGRES_HOST`: Database host (default: "localhost")
  - `POSTGRES_PORT`: Database port (default: "5432")
- **File system:**
  - `PDF_BASE_DIR`: Base directory for PDF files (default: "~/knowledgebase/pdf")
- **AI/LLM configuration:**
  - Ollama service typically runs on `http://localhost:11434`
  - Models used: `gpt-oss:20b` (default for complex tasks), `medgemma4B_it_q8:latest` (fast processing)

## Development Commands

Since this project uses `uv` for package management:
- `uv sync` - Install/sync dependencies
- `uv run python -m [module]` - Run Python modules in the virtual environment
- **Testing**: `uv run python -m pytest tests/` - Run comprehensive test suite
- **CLI Application**: `uv run python bmlibrarian_cli.py` - Interactive medical research CLI
- **Demonstrations**: 
  - `uv run python examples/agent_demo.py` - Multi-agent workflow demonstration
  - `uv run python examples/citation_demo.py` - Citation extraction examples
  - `uv run python examples/reporting_demo.py` - Report generation examples

## Architecture

BMLibrarian uses a sophisticated multi-agent architecture with the following key components:

### Core Components
- **Multi-Agent System**: Specialized AI agents for different literature analysis tasks
- **Task Queue Orchestration**: SQLite-based queue system for memory-efficient processing
- **Database Backend**: PostgreSQL with pgvector extension for semantic search
- **Local LLM Integration**: Ollama service for privacy-preserving AI inference

### Agent Types
1. **QueryAgent**: Natural language to PostgreSQL query conversion
2. **DocumentScoringAgent**: Relevance scoring for user questions (1-5 scale)
3. **CitationFinderAgent**: Extracts relevant passages from high-scoring documents
4. **ReportingAgent**: Synthesizes citations into medical publication-style reports

### Processing Pipeline
```
User Query → QueryAgent → Document Retrieval → DocumentScoringAgent → 
CitationFinderAgent → ReportingAgent → Final Evidence-Based Report
```

### Queue System
- **QueueManager**: SQLite-based persistent task queuing
- **AgentOrchestrator**: Coordinates multi-agent workflows
- **Task Priorities**: HIGH, NORMAL, LOW priority levels
- **Batch Processing**: Memory-efficient handling of large document sets

## Project Structure

```
bmlibrarian/
├── src/bmlibrarian/           # Main source code
│   └── agents/                # Multi-agent system
│       ├── __init__.py        # Agent module exports
│       ├── base.py            # BaseAgent foundation class
│       ├── query_agent.py     # Natural language query processing
│       ├── scoring_agent.py   # Document relevance scoring
│       ├── citation_agent.py  # Citation extraction from documents
│       ├── reporting_agent.py # Report synthesis and formatting
│       ├── queue_manager.py   # SQLite-based task queue system
│       └── orchestrator.py    # Multi-agent workflow coordination
├── tests/                     # Comprehensive test suite
│   ├── test_query_agent.py    # Query processing tests
│   ├── test_scoring_agent.py  # Document scoring tests
│   ├── test_citation_agent.py # Citation extraction tests
│   └── test_reporting_agent.py# Report generation tests
├── examples/                  # Demonstration scripts
│   ├── agent_demo.py          # Multi-agent workflow examples
│   ├── citation_demo.py       # Citation extraction demonstrations
│   └── reporting_demo.py      # Report generation examples
├── doc/                       # Comprehensive documentation
│   ├── users/                 # End-user guides
│   │   ├── query_agent_guide.md
│   │   ├── citation_guide.md
│   │   └── reporting_guide.md
│   └── developers/            # Technical documentation
│       ├── agent_module.md
│       ├── citation_system.md
│       └── reporting_system.md
├── bmlibrarian_cli.py         # Interactive CLI application
├── pyproject.toml             # Project configuration and dependencies
├── uv.lock                    # Locked dependency versions
├── .env                       # Environment configuration
└── README.md                  # Project description
```

## Development Notes

### Project Maturity
- **Current State**: Full multi-agent architecture implemented with comprehensive testing and documentation
- **Core Features**: Query processing, document scoring, citation extraction, and report generation are fully functional
- **Production Ready**: Complete system with queue orchestration, error handling, and quality control

### Development Principles
- **Modern Python Standards**: Uses pyproject.toml, type hints, and Python >=3.12
- **Comprehensive Testing**: Unit tests for all agents with >95% coverage
- **Documentation First**: Both developer and user documentation for all features
- **AI-Powered**: Local LLM integration via Ollama for privacy-preserving processing
- **Scalable Architecture**: Queue-based processing for memory-efficient large-scale operations

### Database Safety
- **CRITICAL**: Never modify or drop the production database "knowledgebase"
- **Development**: Use "bmlibrarian_dev" database for testing/migration experiments
- **Production Access**: Read-only access unless explicitly instructed otherwise
- **Data Integrity**: All document IDs are programmatically verified to prevent hallucination

### Code Quality Standards
- **Testing**: Write comprehensive unit tests for every new module
- **Documentation**: Create both user guides (`doc/users/`) and developer docs (`doc/developers/`)
- **Type Safety**: Use type hints throughout the codebase
- **Error Handling**: Robust error recovery and logging
- **Model Standards**: Only use approved models (`gpt-oss:20b`, `medgemma4B_it_q8:latest`)

### Agent Development Guidelines
- **BaseAgent Pattern**: All agents inherit from BaseAgent with standardized interfaces
- **Queue Integration**: New agents should support queue-based processing
- **Connection Testing**: All agents must implement connection testing methods
- **Progress Tracking**: Support progress callbacks for long-running operations
- **Document ID Integrity**: Always use real database IDs, never mock/fabricated references

## Usage Examples

### Interactive CLI Application

The easiest way to use BMLibrarian is through the interactive CLI:

```bash
# Start the interactive medical research CLI
uv run python bmlibrarian_cli.py

# The CLI guides you through:
# 1. Research question entry
# 2. Query generation and editing
# 3. Database search and review
# 4. Document relevance scoring
# 5. Citation extraction
# 6. Report generation
# 7. Markdown export
```

The CLI provides human-in-the-loop interaction at every step, allowing you to:
- Review and edit generated database queries
- Examine search results and scoring
- Adjust relevance thresholds
- Review extracted citations
- Export professional markdown reports

### Basic Multi-Agent Workflow
```python
from bmlibrarian.agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent, 
    ReportingAgent, AgentOrchestrator
)

# Initialize orchestrator and agents
orchestrator = AgentOrchestrator(max_workers=4)
query_agent = QueryAgent(orchestrator=orchestrator)
scoring_agent = DocumentScoringAgent(orchestrator=orchestrator)
citation_agent = CitationFinderAgent(orchestrator=orchestrator)
reporting_agent = ReportingAgent(orchestrator=orchestrator)

# Complete research workflow
user_question = "What are the cardiovascular benefits of exercise?"

# 1. Query processing and document retrieval
documents = query_agent.search_documents(user_question)

# 2. Score documents for relevance
scored_docs = []
for doc in documents:
    score = scoring_agent.evaluate_document(user_question, doc)
    if score:
        scored_docs.append((doc, score))

# 3. Extract citations from high-scoring documents
citations = citation_agent.process_scored_documents_for_citations(
    user_question=user_question,
    scored_documents=scored_docs,
    score_threshold=2.5
)

# 4. Generate medical publication-style report
report = reporting_agent.generate_citation_based_report(
    user_question=user_question,
    citations=citations,
    format_output=True
)

print(report)
```

### Key Features Demonstrated
- **Natural Language Processing**: Convert questions to database queries
- **Relevance Assessment**: AI-powered document scoring (1-5 scale)
- **Citation Extraction**: Extract specific passages that answer questions
- **Evidence Synthesis**: Generate professional medical reports with proper references
- **Quality Control**: Document verification and evidence strength assessment
- **Scalable Processing**: Queue-based batch processing for large datasets

## Important Instructions and Reminders
### When developing new agents or features:
1. **Always inherit from BaseAgent** for consistent interfaces
2. **Implement comprehensive testing** with realistic test data
3. **Create both user and developer documentation** for all new features
4. **Use only approved LLM models** specified in configuration
5. **Never create or modify production database** without explicit permission
6. **Ensure document ID verification** to prevent citation hallucination
7. **Support queue-based processing** for scalability
8. **Include progress tracking** for long-running operations

### Testing and Quality Assurance:
- Run full test suite: `uv run python -m pytest tests/`
- Test agent demos: `uv run python examples/agent_demo.py`
- Verify Ollama connection before LLM operations
- Validate all citations reference real database documents
- Check evidence strength assessments are appropriate