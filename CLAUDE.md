# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BMLibrarian is a comprehensive Python library providing AI-powered access to biomedical literature databases. It features a multi-agent architecture with specialized agents for query processing, document scoring, citation extraction, report generation, and counterfactual analysis, all coordinated through an advanced task queue orchestration system.

The project includes a modern modular CLI (`bmlibrarian_cli.py`) that provides full multi-agent workflow capabilities with enhanced maintainability and extensibility.

## Dependencies and Environment

- **Python**: Requires Python >=3.12
- **Database**: PostgreSQL with pgvector extension for semantic search
- **AI/LLM**: Ollama for local language model inference
- **Main dependencies**:
  - psycopg >=3.2.9 for PostgreSQL connectivity (via DatabaseManager)
  - ollama - Python library for Ollama LLM communication (never use raw HTTP requests)
  - flet >=0.24.1 for GUI configuration interface
- **Package manager**: Uses `uv` for dependency management (uv.lock present)

## Configuration

- **Configuration file locations** (OS agnostic):
  - **Primary**: `~/.bmlibrarian/config.json` (recommended)
  - **Legacy fallback**: `bmlibrarian_config.json` in current directory
  - **GUI default**: Always saves to `~/.bmlibrarian/config.json`
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
- **OpenAthens proxy authentication** (optional):
  - Enable institutional access to paywalled PDFs via OpenAthens proxy
  - Supports 2FA authentication with persistent sessions (24 hours default)
  - Configure in `config.json` under `"openathens"` section
  - Requires Playwright: `uv add playwright && uv run python -m playwright install chromium`
  - See: `doc/OPENATHENS_QUICKSTART.md` and `doc/users/openathens_guide.md`

## Development Commands

Since this project uses `uv` for package management:
- `uv sync` - Install/sync dependencies
- `uv run python -m [module]` - Run Python modules in the virtual environment
- **Testing**: `uv run python -m pytest tests/` - Run comprehensive test suite
- **Database Setup & Battle Testing**:
  - `uv run python initial_setup_and_download.py test_database.env` - Complete database setup and import testing
  - `uv run python initial_setup_and_download.py test.env --skip-medrxiv --skip-pubmed` - Schema setup only
  - `uv run python initial_setup_and_download.py test.env --medrxiv-days 1 --pubmed-max-results 10` - Quick validation test
  - See [SETUP_GUIDE.md](SETUP_GUIDE.md) for comprehensive documentation
- **CLI Applications**:
  - `uv run python bmlibrarian_cli.py` - Interactive medical research CLI with full multi-agent workflow
  - `uv run python fact_checker_cli.py statements.json` - Batch fact-checker for biomedical statements (stores in PostgreSQL factcheck schema)
  - `uv run python fact_checker_cli.py statements.json --incremental` - Incremental mode (resume processing, skip already-evaluated statements)
  - `uv run python medrxiv_import_cli.py update --download-pdfs` - Import medRxiv preprints with PDFs
  - `uv run python medrxiv_import_cli.py fetch-pdfs --limit 100` - Download missing PDFs for existing records
  - `uv run python medrxiv_import_cli.py status` - Show medRxiv import statistics
  - `uv run python pubmed_import_cli.py search "COVID-19 vaccine" --max-results 100` - Import PubMed articles by search query (targeted import)
  - `uv run python pubmed_import_cli.py pmids 12345678 23456789` - Import PubMed articles by PMID list
  - `uv run python pubmed_import_cli.py status` - Show PubMed import statistics
  - `uv run python pubmed_bulk_cli.py download-baseline` - Download complete PubMed baseline (~38M articles, ~400GB, for offline mirroring)
  - `uv run python pubmed_bulk_cli.py download-updates` - Download PubMed daily update files (new articles + metadata updates)
  - `uv run python pubmed_bulk_cli.py import --type baseline` - Import downloaded baseline files into database (with Markdown abstract formatting)
  - `uv run python pubmed_bulk_cli.py sync --updates-only` - Download and import PubMed updates (incremental sync)
  - `uv run python pubmed_bulk_cli.py status` - Show PubMed bulk download/import status
  - **Note**: PubMed bulk importer now preserves abstract structure and formatting as Markdown (section labels, subscripts, superscripts, emphasis)
  - `uv run python embed_documents_cli.py embed --source medrxiv --limit 100` - Generate embeddings for medRxiv abstracts
  - `uv run python embed_documents_cli.py count --source medrxiv` - Count documents needing embeddings
  - `uv run python embed_documents_cli.py status` - Show embedding statistics
  - `uv run python pdf_import_cli.py file /path/to/paper.pdf` - Import single PDF with LLM-based metadata extraction and database matching
  - `uv run python pdf_import_cli.py directory /path/to/pdfs/` - Import directory of PDFs with intelligent matching
  - `uv run python pdf_import_cli.py directory /pdfs/ --recursive` - Import PDFs recursively from subdirectories
  - `uv run python pdf_import_cli.py file paper.pdf --dry-run` - Preview import without making changes
  - `uv run python pdf_import_cli.py status` - Show PDF import statistics and coverage
  - `uv run python fact_checker_cli.py statements.json -o results.json` - Export results to JSON file (PostgreSQL is always used)
  - `uv run python fact_checker_stats.py` - Generate comprehensive statistical analysis report (console output)
  - `uv run python fact_checker_stats.py --export-csv stats_output/` - Export statistics to CSV files
  - `uv run python fact_checker_stats.py --export-csv stats_output/ --plot` - Create visualization plots
- **GUI Applications**:
  - `uv run python setup_wizard.py` - PySide6 setup wizard for initial database configuration and data import
  - `uv run python bmlibrarian_research_gui.py` - Desktop research application with visual workflow progress and report preview
  - `uv run python bmlibrarian_config_gui.py` - Graphical configuration interface for agents and settings
  - `uv run python fact_checker_review_gui.py` - Human review and annotation interface for fact-checking results (PostgreSQL-based)
  - `uv run python fact_checker_review_gui.py --user alice` - Launch review GUI with username (skip login dialog)
  - `uv run python fact_checker_review_gui.py --user alice --incremental` - Incremental mode (only show unannotated statements)
  - `uv run python fact_checker_review_gui.py --user bob --blind` - Blind mode (hide AI/original annotations for unbiased review)
  - `uv run python fact_checker_review_gui.py --user alice --db-file review_package.db` - Review with SQLite package (no PostgreSQL needed)
- **Fact-Checker Distribution Tools** (for inter-rater reliability analysis):
  - `uv run python export_review_package.py --output review_package.db --exported-by username` - Export self-contained SQLite review package
  - `uv run python export_human_evaluations.py --db-file review.db --annotator alice -o alice.json` - Export human annotations to JSON
  - `uv run python import_human_evaluations.py alice.json bob.json charlie.json` - Re-import human evaluations to PostgreSQL
- **Laboratory Tools**:
  - `uv run python query_lab.py` - Interactive QueryAgent laboratory for experimenting with natural language to PostgreSQL query conversion
  - `uv run python pico_lab.py` - Interactive PICO laboratory for extracting Population, Intervention, Comparison, and Outcome components from documents
  - `uv run python study_assessment_lab.py` - Interactive Study Assessment laboratory for evaluating research quality and trustworthiness
  - `uv run python prisma2020_lab.py` - Interactive PRISMA 2020 laboratory for assessing systematic review compliance with PRISMA reporting guidelines
  - `uv run python paper_weight_lab.py` - Interactive Paper Weight Assessment laboratory (PySide6/Qt) for evaluating evidential weight of research papers
- **PDF Processing Tools**:
  - `uv run python pdf_processor_demo.py` - PySide6 demo application for PDF section segmentation (biomedical publications)
  - `uv run python test_pdf_processor.py paper.pdf` - Command-line test script for PDF processor library
- **Demonstrations**:
  - `uv run python examples/agent_demo.py` - Multi-agent workflow demonstration
  - `uv run python examples/citation_demo.py` - Citation extraction examples
  - `uv run python examples/reporting_demo.py` - Report generation examples
  - `uv run python examples/counterfactual_demo.py` - Counterfactual analysis demonstration

## OpenAthens Authentication

BMLibrarian includes secure OpenAthens authentication for accessing institutional journal subscriptions:

### Key Features
- **Secure Session Management**: JSON-based storage with 600 file permissions (no pickle vulnerability)
- **Browser Automation**: Interactive login via Playwright
- **Cookie-Based Authentication**: Automatic cookie injection for authenticated downloads
- **Session Validation Caching**: Performance optimization with configurable TTL
- **HTTPS Enforcement**: All institutional URLs must use HTTPS
- **Network Connectivity Checks**: Pre-authentication validation

### Security Improvements Implemented
1. **JSON Serialization**: Replaced pickle to eliminate code execution vulnerability
2. **File Permissions**: Session files stored with 600 permissions (owner read/write only)
3. **Cookie Pattern Matching**: Specific regex patterns for OpenAthens/SAML/Shibboleth cookies
4. **Configurable Parameters**: No magic numbers, all timeouts/intervals configurable
5. **URL Validation**: HTTPS requirement and format validation
6. **Browser Crash Handling**: Graceful cleanup on browser failures
7. **Session Cache TTL**: Reduces validation overhead during batch downloads

### Usage
```python
from bmlibrarian.utils.openathens_auth import OpenAthensConfig, OpenAthensAuth
from bmlibrarian.utils.pdf_manager import PDFManager

# Configure OpenAthens
config = OpenAthensConfig(
    institution_url='https://institution.openathens.net/login',
    session_max_age_hours=24,
    session_cache_ttl=60
)

# Authenticate (interactive browser login)
auth = OpenAthensAuth(config)
import asyncio
asyncio.run(auth.login_interactive())

# Use with PDFManager for authenticated downloads
pdf_manager = PDFManager(openathens_auth=auth)
pdf_path = pdf_manager.download_pdf(document)
```

### Documentation
- **User Guide**: `doc/users/openathens_guide.md` - Complete usage guide with examples
- **Security Documentation**: `doc/developers/openathens_security.md` - Security architecture and best practices
- **Unit Tests**: `tests/test_openathens_auth.py` - Comprehensive test suite

## Architecture

BMLibrarian uses a sophisticated multi-agent architecture with enum-based workflow orchestration:

### Core Components
- **Multi-Agent System**: Specialized AI agents for different literature analysis tasks
- **Enum-Based Workflow**: Flexible step orchestration with meaningful names and repeatable steps
- **Task Queue Orchestration**: SQLite-based queue system for memory-efficient processing
- **Database Backend**: PostgreSQL with pgvector extension for semantic search
- **Local LLM Integration**: Ollama service for privacy-preserving AI inference

### Agent Types
1. **QueryAgent**: Natural language to PostgreSQL query conversion
2. **DocumentScoringAgent**: Relevance scoring for user questions (1-5 scale)
3. **CitationFinderAgent**: Extracts relevant passages from high-scoring documents
4. **ReportingAgent**: Synthesizes citations into medical publication-style reports
5. **CounterfactualAgent**: Analyzes documents to generate research questions for finding contradictory evidence
6. **EditorAgent**: Creates balanced comprehensive reports integrating all evidence
7. **FactCheckerAgent**: Evaluates biomedical statements (yes/no/maybe) with literature evidence for training data auditing
8. **PICOAgent**: Extracts Population, Intervention, Comparison, and Outcome components from research papers for systematic reviews
9. **StudyAssessmentAgent**: Evaluates research quality, study design, methodological rigor, bias risk, and trustworthiness of biomedical evidence
10. **PRISMA2020Agent**: Assesses systematic reviews and meta-analyses against PRISMA 2020 reporting guidelines (27-item checklist with suitability pre-screening)

### Document Card Factory System

BMLibrarian uses a factory pattern for creating document cards with consistent functionality across different UI frameworks (Flet and Qt).

**Key Features**:
- **Framework-Agnostic Interface**: Single API for creating cards in Flet or Qt
- **Three-State PDF Buttons**: VIEW (local PDF), FETCH (download from URL), UPLOAD (manual upload)
- **Consistent Styling**: Unified appearance across frameworks
- **Context-Aware Rendering**: Different card styles for literature, scoring, citations, etc.
- **Extensible Design**: Easy to add new card variations or contexts

**Factory Classes**:
- `DocumentCardFactoryBase`: Abstract base class with common utilities
- `FletDocumentCardFactory`: Flet-specific implementation with `ft.ExpansionTile` cards
- `QtDocumentCardFactory`: Qt-specific implementation with `QFrame` cards and integrated PDF buttons

**Usage Example**:
```python
from bmlibrarian.gui.flet_document_card_factory import FletDocumentCardFactory
from bmlibrarian.gui.document_card_factory_base import DocumentCardData, CardContext

factory = FletDocumentCardFactory(page=page)
card_data = DocumentCardData(
    doc_id=12345,
    title="Example Study",
    authors=["Smith J", "Johnson A"],
    year=2023,
    relevance_score=4.5,
    pdf_url="https://example.com/paper.pdf",
    context=CardContext.LITERATURE,
    show_pdf_button=True
)
card = factory.create_card(card_data)
```

**PDF Button States**:
- **VIEW** (Blue): Local PDF exists → Opens in viewer
- **FETCH** (Orange): URL available → Downloads then transitions to VIEW
- **UPLOAD** (Green): No PDF → File picker then transitions to VIEW

**See Documentation**:
- Developer guide: `doc/developers/document_card_factory_system.md`
- Demo: `examples/document_card_factory_demo.py`

### Multi-Model Query Generation

BMLibrarian supports using multiple AI models to generate diverse database queries for improved document retrieval. This feature leverages the strengths of different models to create query variations that often find more relevant literature than single-model approaches.

**Key Features**:
- **Query Diversity**: Generate 1-3 queries per model using up to 3 different models
- **Improved Coverage**: Typically finds 20-40% more relevant documents
- **Serial Execution**: Simple serial processing optimized for local Ollama + PostgreSQL instances
- **Automatic De-duplication**: Query and document ID de-duplication handled automatically
- **Backward Compatible**: Feature flag system (disabled by default)

**Configuration** (`~/.bmlibrarian/config.json`):
```json
{
  "query_generation": {
    "multi_model_enabled": true,
    "models": [
      "medgemma-27b-text-it-Q8_0:latest",
      "gpt-oss:20b",
      "medgemma4B_it_q8:latest"
    ],
    "queries_per_model": 1,
    "execution_mode": "serial",
    "deduplicate_results": true,
    "show_all_queries_to_user": true,
    "allow_query_selection": true
  }
}
```

**Architecture Highlights**:
- **Serial Execution**: Simple for-loops (not parallel) prevent resource bottlenecks with local instances
- **ID-Only Queries**: Fast document ID retrieval (~10x faster) followed by single bulk document fetch
- **Type-Safe Results**: Dataclasses (`QueryGenerationResult`, `MultiModelQueryResult`) for all query results
- **Error Resilience**: Model failures handled gracefully, system continues with available models

**Performance**:
- Overhead: ~2-3x slower than single-model (typically 5-15 seconds vs 2-5 seconds)
- Benefit: 20-40% more relevant documents with 2-3 models
- Recommended: Start with 2 models, 1 query each for best balance

**See Documentation**:
- User guide: `doc/users/multi_model_query_guide.md`
- Technical docs: `doc/developers/multi_model_architecture.md`

### Workflow Orchestration System
The new enum-based workflow system (`workflow_steps.py`) provides:
- **WorkflowStep Enum**: Meaningful step names instead of brittle numbering
- **Repeatable Steps**: Query refinement, threshold adjustment, citation requests
- **Branching Logic**: Conditional step execution and error recovery
- **Context Management**: State preservation across step executions
- **Auto Mode Support**: Graceful handling of non-interactive execution

### Workflow Steps
```
COLLECT_RESEARCH_QUESTION → GENERATE_AND_EDIT_QUERY → SEARCH_DOCUMENTS → 
REVIEW_SEARCH_RESULTS → SCORE_DOCUMENTS → EXTRACT_CITATIONS → 
GENERATE_REPORT → PERFORM_COUNTERFACTUAL_ANALYSIS → 
SEARCH_CONTRADICTORY_EVIDENCE → EDIT_COMPREHENSIVE_REPORT → 
REVIEW_AND_REVISE_REPORT → EXPORT_REPORT
```

### Iterative Capabilities
- **Query Refinement**: When search results are insufficient
- **Threshold Adjustment**: For better citation extraction
- **Citation Requests**: Agents can request more evidence during report generation
- **Report Revision**: Iterative improvement of generated reports
- **Evidence Enhancement**: Counterfactual analysis for finding contradictory studies

### Queue System
- **QueueManager**: SQLite-based persistent task queuing
- **AgentOrchestrator**: Coordinates multi-agent workflows
- **WorkflowExecutor**: Manages step execution with context tracking
- **Task Priorities**: HIGH, NORMAL, LOW priority levels
- **Batch Processing**: Memory-efficient handling of large document sets

## Project Structure

```
bmlibrarian/
├── src/bmlibrarian/           # Main source code
│   ├── agents/                # Multi-agent system
│   │   ├── __init__.py        # Agent module exports
│   │   ├── base.py            # BaseAgent foundation class
│   │   ├── query_agent.py     # Natural language query processing
│   │   ├── scoring_agent.py   # Document relevance scoring
│   │   ├── citation_agent.py  # Citation extraction from documents
│   │   ├── reporting_agent.py # Report synthesis and formatting
│   │   ├── counterfactual_agent.py # Counterfactual analysis for contradictory evidence
│   │   ├── editor_agent.py    # Comprehensive report editing and integration
│   │   ├── queue_manager.py   # SQLite-based task queue system
│   │   ├── orchestrator.py    # Multi-agent workflow coordination
│   │   └── query_generation/  # Multi-model query generation system
│   │       ├── __init__.py    # Query generation module exports
│   │       ├── data_types.py  # Type-safe dataclasses for query results
│   │       └── generator.py   # Multi-model query generator
│   ├── importers/             # External data source importers
│   │   ├── __init__.py        # Importer module exports
│   │   ├── medrxiv_importer.py # MedRxiv preprint importer
│   │   ├── pubmed_importer.py # PubMed E-utilities importer (targeted imports)
│   │   ├── pubmed_bulk_importer.py # PubMed FTP bulk importer (complete mirror)
│   │   ├── pdf_matcher.py     # LLM-based PDF matching and import (DOI/PMID/title matching)
│   │   └── README.md          # Importer documentation
│   ├── embeddings/            # Document embedding generation
│   │   ├── __init__.py        # Embeddings module exports
│   │   └── document_embedder.py # Document embedder (uses Ollama)
│   ├── pdf_processor/         # PDF processing and segmentation for biomedical publications
│   │   ├── __init__.py        # PDF processor module exports
│   │   ├── models.py          # Data models (TextBlock, Section, Document, SectionType)
│   │   ├── extractor.py       # PDF text extraction with layout analysis (PyMuPDF)
│   │   ├── segmenter.py       # Section segmentation using NLP and heuristics
│   │   └── README.md          # PDF processor documentation
│   └── cli/                   # Modular CLI architecture
│       ├── __init__.py        # CLI module exports
│       ├── config.py          # Configuration management
│       ├── ui.py              # User interface components
│       ├── query_processing.py # Query editing and search
│       ├── formatting.py      # Report formatting and export
│       ├── workflow.py        # Workflow orchestration
│       └── workflow_steps.py  # Enum-based workflow step definitions
│   └── gui/                   # Graphical user interfaces (Flet and Qt)
│       ├── __init__.py        # GUI module exports (re-exports from flet/ for backwards compatibility)
│       ├── flet/              # Flet-based GUI components
│       │   ├── __init__.py    # Flet module exports
│       │   ├── config_app.py  # Configuration GUI application
│       │   ├── research_app.py # Main research GUI application
│       │   ├── components.py  # Reusable UI components (StepCard, etc.)
│       │   ├── dialogs.py     # Dialog management and interactions
│       │   ├── workflow.py    # Real agent orchestration and execution
│       │   ├── document_card_factory_base.py  # Base classes for document cards
│       │   ├── flet_document_card_factory.py  # Flet document card factory
│       │   ├── unified_document_card.py       # Unified document card interface
│       │   └── tabs/          # Configuration GUI tab components
│       │       ├── __init__.py
│       │       ├── general_tab.py # General settings tab
│       │       ├── agent_tab.py   # Agent-specific configuration tabs
│       │       ├── query_generation_tab.py  # Multi-model query generation tab
│       │       ├── search_tab.py  # Search settings tab
│       │       └── document_interrogation_tab.py  # Document interrogation interface
│       └── qt/                # Qt/PySide6-based GUI components
│           ├── __init__.py    # Qt module entry point
│           ├── core/          # Core application infrastructure
│           ├── plugins/       # Plugin system (research, fact_checker, etc.)
│           ├── widgets/       # Reusable Qt widgets
│           ├── resources/     # Resources and styling (dpi_scale, stylesheets)
│           └── qt_document_card_factory.py  # Qt document card factory
│   └── lab/                   # Experimental tools and interfaces
│       ├── __init__.py        # Lab module exports
│       ├── query_lab.py       # QueryAgent experimental GUI
│       ├── pico_lab.py        # PICOAgent experimental GUI for PICO component extraction
│       ├── study_assessment_lab.py # StudyAssessmentAgent experimental GUI for study quality evaluation
│       └── prisma2020_lab.py  # PRISMA2020Agent experimental GUI for PRISMA 2020 compliance assessment
│   └── factchecker/           # Fact-checker module (PostgreSQL-based)
│       ├── __init__.py        # Fact-checker module exports
│       ├── agent/             # Fact-checker agent
│       │   ├── __init__.py
│       │   └── fact_checker_agent.py  # FactCheckerAgent (orchestrates multi-agent workflow)
│       ├── db/                # Database operations
│       │   ├── __init__.py
│       │   └── database.py    # FactCheckerDB (PostgreSQL factcheck schema)
│       ├── cli/               # CLI application
│       │   ├── __init__.py
│       │   ├── app.py         # Main CLI entry point
│       │   ├── commands.py    # Command handlers
│       │   └── formatters.py  # Output formatting
│       └── gui/               # Review GUI application
│           ├── __init__.py
│           ├── review_app.py  # Main review application
│           ├── data_manager.py    # Database queries
│           ├── annotation_manager.py  # Annotation logic
│           ├── statement_display.py   # Statement UI
│           ├── citation_display.py    # Citation cards
│           └── dialogs.py     # Login/export dialogs
├── tests/                     # Comprehensive test suite
│   ├── test_query_agent.py    # Query processing tests
│   ├── test_scoring_agent.py  # Document scoring tests
│   ├── test_citation_agent.py # Citation extraction tests
│   ├── test_reporting_agent.py# Report generation tests
│   └── test_counterfactual_agent.py # Counterfactual analysis tests
├── examples/                  # Demonstration scripts
│   ├── agent_demo.py          # Multi-agent workflow examples
│   ├── citation_demo.py       # Citation extraction demonstrations
│   ├── reporting_demo.py      # Report generation examples
│   └── counterfactual_demo.py # Counterfactual analysis demonstrations
├── doc/                       # Comprehensive documentation
│   ├── users/                 # End-user guides
│   │   ├── query_agent_guide.md
│   │   ├── citation_guide.md
│   │   ├── reporting_guide.md
│   │   ├── counterfactual_guide.md
│   │   ├── fact_checker_guide.md
│   │   ├── fact_checker_review_guide.md  # Fact-checker review GUI guide
│   │   ├── medrxiv_import_guide.md  # MedRxiv import guide
│   │   ├── document_embedding_guide.md  # Document embedding guide
│   │   ├── document_interrogation_guide.md  # Document interrogation tab guide
│   │   ├── pdf_import_guide.md  # PDF import and matching guide
│   │   ├── study_assessment_guide.md  # Study quality assessment guide
│   │   ├── prisma2020_guide.md  # PRISMA 2020 compliance assessment guide
│   │   └── multi_model_query_guide.md  # Multi-model query generation guide
│   └── developers/            # Technical documentation
│       ├── agent_module.md
│       ├── citation_system.md
│       ├── reporting_system.md
│       ├── counterfactual_system.md
│       ├── fact_checker_system.md
│       ├── study_assessment_system.md  # Study quality assessment system
│       ├── prisma2020_system.md  # PRISMA 2020 compliance assessment system
│       ├── document_interrogation_ui_spec.md  # Document interrogation UI specification
│       └── multi_model_architecture.md  # Multi-model architecture docs
├── bmlibrarian_cli.py         # Interactive CLI application with full multi-agent workflow
├── bmlibrarian_research_gui.py # Desktop research GUI application (98-line modular entry point)
├── bmlibrarian_config_gui.py  # Graphical configuration interface
├── fact_checker_cli.py        # Fact-checker CLI for training data auditing
├── fact_checker_review_gui.py # Human review and annotation GUI for fact-checking results
├── fact_checker_stats.py      # Comprehensive statistical analysis for fact-checker evaluations
├── export_review_package.py   # Export SQLite review packages for distribution
├── export_human_evaluations.py # Export human annotations to JSON
├── import_human_evaluations.py # Re-import human evaluations to PostgreSQL
├── medrxiv_import_cli.py      # MedRxiv preprint import CLI
├── pubmed_import_cli.py       # PubMed E-utilities import CLI (targeted imports)
├── pubmed_bulk_cli.py         # PubMed FTP bulk download/import CLI (complete mirror)
├── embed_documents_cli.py     # Document embedding generation CLI
├── pdf_import_cli.py          # PDF import CLI with LLM-based metadata extraction and matching
├── query_lab.py               # QueryAgent experimental laboratory GUI
├── pico_lab.py                # PICOAgent experimental laboratory GUI for PICO component extraction
├── study_assessment_lab.py    # StudyAssessmentAgent experimental laboratory GUI for study quality evaluation
├── prisma2020_lab.py          # PRISMA2020Agent experimental laboratory GUI for PRISMA 2020 compliance assessment
├── paper_weight_lab.py        # PaperWeightAssessmentAgent laboratory GUI (PySide6/Qt) for evaluating evidential weight
├── pdf_processor_demo.py      # PySide6 demo application for biomedical publication section segmentation
├── test_pdf_processor.py      # Command-line test script for PDF processor library
├── initial_setup_and_download.py  # Database setup and battle-testing script
├── baseline_schema.sql        # Base PostgreSQL schema definition
├── migrations/                # Database migration scripts
├── test_database.env.example  # Example environment file for testing
├── SETUP_GUIDE.md            # Comprehensive setup and testing guide
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
- **Enum-Based Architecture**: Flexible workflow orchestration with meaningful step names
- **Comprehensive Testing**: Unit tests for all agents with >95% coverage
- **Documentation First**: Both developer and user documentation for all features
- **AI-Powered**: Local LLM integration via Ollama for privacy-preserving processing
- **Scalable Architecture**: Queue-based processing for memory-efficient large-scale operations
- **Iterative Workflows**: Support for repeatable steps and agent-driven refinement

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
- **Temporal Precision**: Use specific years instead of vague temporal references (e.g., "In a 2023 study" NOT "In a recent study")

### Agent Development Guidelines
- **BaseAgent Pattern**: All agents inherit from BaseAgent with standardized interfaces
- **Configuration Integration**: Agents must use `get_model()` and `get_agent_config()` from config system
- **Parameter Filtering**: Filter agent config to only include supported parameters (temperature, top_p, etc.)
- **Queue Integration**: New agents should support queue-based processing
- **Workflow Integration**: Agents should work with enum-based workflow system
- **Connection Testing**: All agents must implement connection testing methods
- **Progress Tracking**: Support progress callbacks for long-running operations
- **Document ID Integrity**: Always use real database IDs, never mock/fabricated references
- **Step Handler Methods**: Implement appropriate workflow step handlers for agent actions
- **No Artificial Limits**: Process ALL documents unless explicitly configured otherwise

### Workflow Development Guidelines
- **WorkflowStep Enum**: Use meaningful names for new workflow steps
- **Repeatable Steps**: Mark steps as repeatable when they support iteration
- **Branching Logic**: Implement conditional execution and error recovery
- **Context Management**: Preserve state across step executions
- **Auto Mode Support**: Ensure steps work in non-interactive mode

## Usage Examples

### Research GUI Application

BMLibrarian includes a comprehensive desktop research application built with Flet:

```bash
# Start the research GUI application (default desktop mode)
uv run python bmlibrarian_research_gui.py

# Research GUI Features:
# - Multi-line text input for medical research questions
# - Interactive/automated workflow toggle
# - Visual workflow progress with collapsible step cards
# - Real-time agent execution with proper model configuration
# - Formatted markdown report preview with scrolling
# - Direct file save functionality (avoids macOS FilePicker bugs)
# - Space-efficient layout with optimized screen usage
# - Full integration with BMLibrarian's multi-agent system

# Command line options:
uv run python bmlibrarian_research_gui.py --auto "research question"  # Automated execution
uv run python bmlibrarian_research_gui.py --quick                    # Quick mode with limits
uv run python bmlibrarian_research_gui.py --max-results 100          # Custom search limits
uv run python bmlibrarian_research_gui.py --score-threshold 3.0      # Custom relevance threshold
```

The Research GUI provides:
- **Desktop Application**: Native cross-platform desktop interface
- **Visual Workflow**: Collapsible cards showing real-time progress through 11 workflow steps
- **Agent Integration**: Uses configured models from `~/.bmlibrarian/config.json` 
- **Document Processing**: Scores ALL found documents by default (no artificial limits)
- **Citation Extraction**: Processes ALL documents above relevance threshold
- **Report Generation**: Full markdown rendering with GitHub-style formatting
- **Save Functionality**: Direct file path input dialog (macOS-compatible)
- **Preview System**: Full-screen overlay with scrollable markdown display
- **Space Optimization**: Controls positioned efficiently, collapsible workflow section
- **Configuration Support**: Respects agent models, parameters, and thresholds from config
- **Performance Modes**: Normal (all documents) vs Quick (limited for speed)

### Configuration GUI Application

BMLibrarian includes a modern graphical configuration interface built with Flet:

```bash
# Start the desktop configuration GUI (default)
uv run python bmlibrarian_config_gui.py

# GUI Features:
# - Native desktop application with tabbed interface
# - Document Interrogation tab: Interactive document viewer with AI chatbot for Q&A
# - Separate configuration tabs for each agent
# - Model selection with live refresh from Ollama server
# - Parameter adjustment with sliders and input fields
# - Configuration save/load functionality
# - Connection testing to verify Ollama availability
# - Reset to defaults option
# - Cross-platform compatibility (desktop or web modes)

# Command line options:
uv run python bmlibrarian_config_gui.py --view web          # Launch in web browser
uv run python bmlibrarian_config_gui.py --view web --port 8080  # Web with custom port
uv run python bmlibrarian_config_gui.py --debug            # Enable debug mode
```

The GUI provides:
- **Native Desktop App**: Cross-platform desktop application (default mode)
- **Document Interrogation**: Interactive split-pane interface for document Q&A
  - Left pane: Document viewer (PDF, Markdown, text files) with 60% width
  - Right pane: Chat interface with dialogue bubbles (40% width)
  - File selector and model dropdown in top bar
  - Support for programmatic document loading from other plugins
  - Message history with user/AI distinction
  - Real-time chat with selected Ollama model
- **Agent Configuration**: Individual tabs for Query, Scoring, Citation, Reporting, Counterfactual, and Editor agents
- **Model Management**: Dropdown selection with live model refresh from Ollama
- **Parameter Tuning**: Interactive sliders for temperature, top-p, and agent-specific settings
- **General Settings**: Ollama server configuration, database settings, and CLI defaults
- **File Operations**: Save/load configuration files with JSON format
- **Connection Testing**: Verify Ollama server connectivity and list available models
- **Dual Mode**: Can run as desktop app or web interface

### Fact-Checker Review GUI Application

BMLibrarian includes a human review and annotation interface for fact-checking results:

```bash
# Start the Fact-Checker Review GUI
uv run python fact_checker_review_gui.py

# Load JSON file (auto-creates SQLite database for annotations)
uv run python fact_checker_review_gui.py --input-file results.json

# Load existing database directly
uv run python fact_checker_review_gui.py --input-file results.db

# Incremental mode: only show statements without AI evaluations
uv run python fact_checker_review_gui.py --input-file results.json --incremental
```

The Fact-Checker Review GUI provides:
- **Database Auto-Creation**: Automatically creates SQLite database from JSON files (e.g., `results.json` → `results.db`)
- **Intelligent Merging**: If database exists, imports new statements from JSON without overwriting existing annotations
- **CLI-Consistent Behavior**: Same database workflow as the fact-checker CLI for seamless integration
- **Real-Time Persistence**: All annotations saved directly to database as you review
- **Incremental Mode**: Filter to show only unevaluated statements (consistent with CLI)
- **Multi-User Support**: Track annotations by different reviewers with annotator metadata
- **Evidence Review**: Examine supporting citations with expandable cards showing full abstracts
- **Annotation Comparison**: View original, AI, and human annotations side-by-side

**Database Workflow** (matches CLI):
1. Load `results.json`: Checks if `results.db` exists
2. If DB exists: Merges new statements from JSON (skips existing with evaluations/annotations)
3. If DB doesn't exist: Creates new database and imports all JSON data
4. All annotations are saved to the database in real-time

This ensures that the GUI and CLI provide identical database management behavior, making it easy to switch between interfaces or use both for different tasks.

### Fact-Checker Distribution System for Inter-Rater Reliability

BMLibrarian includes a complete distribution system for sending fact-check results to external reviewers without requiring PostgreSQL installation. This enables inter-rater reliability analysis with multiple independent human annotators.

**Complete Workflow**:

1. **Export Review Package** (PostgreSQL → SQLite):
   ```bash
   uv run python export_review_package.py --output review_package.db --exported-by username
   ```
   - Creates self-contained SQLite database with:
     - All statements and AI evaluations
     - Evidence citations with full document abstracts
     - Document metadata (titles, PMIDs, DOIs)
     - NO human annotations from other reviewers
   - Typical size: 100-500 MB for 1000 statements
   - Ready for distribution via file sharing

2. **Distribute to External Reviewers**:
   - Send `.db` file + `fact_checker_review_gui.py` to reviewers
   - No PostgreSQL installation required
   - Works offline with full functionality

3. **Reviewer Annotation** (SQLite):
   ```bash
   uv run python fact_checker_review_gui.py --user alice --db-file review_package.db
   ```
   - Read-write mode: Annotations saved to SQLite in real-time
   - Full abstract display for all citations
   - Same interface as PostgreSQL version
   - Supports blind mode and incremental mode

4. **Export Human Evaluations** (SQLite → JSON):
   ```bash
   uv run python export_human_evaluations.py --db-file review_package.db --annotator alice -o alice.json
   ```
   - Lightweight JSON export (1-10 KB per statement)
   - Contains: statement_id, statement_text, annotation, explanation
   - Reviewer sends back only the small JSON file

5. **Re-import to PostgreSQL** (JSON → PostgreSQL):
   ```bash
   uv run python import_human_evaluations.py alice.json bob.json charlie.json
   ```
   - Creates/updates annotator records with username tagging
   - Validates statements match by ID and text
   - Inserts/updates annotations (one per annotator per statement)
   - Reports statistics (inserted, updated, errors)
   - Update/overwrite behavior for duplicate annotations

6. **Analyze Inter-Rater Agreement**:
   ```sql
   -- PostgreSQL query
   SELECT * FROM factcheck.calculate_inter_annotator_agreement();
   SELECT * FROM factcheck.v_inter_annotator_agreement;
   ```

**Key Features**:
- **Database Abstraction**: Unified interface supporting both PostgreSQL and SQLite backends
- **Self-Contained Packages**: All data needed for review in single `.db` file
- **No Dependencies**: Reviewers don't need PostgreSQL, just Python + Flet
- **Validation**: Statement text matching prevents mismatches during import
- **Multi-Reviewer Support**: Track annotations by username for inter-rater analysis
- **Security**: Audit trail via export_history, encrypted distribution recommended

**Documentation**:
- Quick Start Guide: `doc/users/FACT_CHECKER_DISTRIBUTION_QUICKSTART.md`
- Implementation Plan: `doc/developers/FACT_CHECKER_DISTRIBUTION_PLAN.md`
- User Guide: `doc/users/fact_checker_distribution_guide.md` (if exists)

**Architecture**:
- `src/bmlibrarian/factchecker/db/abstract_db.py`: Abstract database interface
- `src/bmlibrarian/factchecker/db/sqlite_db.py`: SQLite implementation
- `src/bmlibrarian/factchecker/db/postgresql_db.py`: PostgreSQL wrapper
- `src/bmlibrarian/factchecker/db/sqlite_schema.sql`: Complete SQLite schema
- `export_review_package.py`: Review package export script
- `export_human_evaluations.py`: Human annotations export script
- `import_human_evaluations.py`: PostgreSQL import script

### Fact-Checker Statistical Analysis

BMLibrarian includes a comprehensive statistical analysis tool (`fact_checker_stats.py`) for evaluating fact-checker performance and inter-rater reliability. The tool calculates multiple metrics with proper statistical rigor.

**Statistical Metrics Calculated**:
- **Concordance rates**: Agreement between AI evaluations and expected answers or human annotations with 95% confidence intervals using Wilson score interval (binomial proportions)
- **Cohen's kappa**: Inter-rater reliability coefficient with standard errors and 95% confidence intervals
- **Confusion matrices**: Cross-tabulation of evaluations with accuracy, precision, recall, and F1-scores
- **Confidence calibration**: Relationship between AI confidence levels (low/medium/high) and actual accuracy
- **Chi-square tests**: Statistical significance testing for categorical data (p < 0.05)
- **Category-specific transitions**: Analysis of evaluation changes:
  - Yes → No transitions: Percentage of statements where evaluations changed from "yes" to "no"
  - No → Yes transitions: Percentage of statements where evaluations changed from "no" to "yes"
  - Certainty changes: Percentage moving to "maybe" (increased uncertainty)
  - Stability: Percentage with unchanged evaluations

**Usage**:
```bash
# Console output only
uv run python fact_checker_stats.py

# Export to CSV files
uv run python fact_checker_stats.py --export-csv stats_output/

# Create visualization plots (confusion matrices, calibration curves, transition charts)
uv run python fact_checker_stats.py --export-csv stats_output/ --plot
```

**Output Files**:
- `ai_vs_expected.csv`: Raw data for AI evaluations vs expected answers
- `ai_vs_human.csv`: Raw data for AI evaluations vs human annotations
- `human_pairs.csv`: Paired human annotations for inter-rater analysis
- `summary_statistics.json`: Complete statistical results in JSON format
- `confusion_matrix_ai_vs_expected.png`: Heatmap visualization
- `confidence_calibration.png`: Calibration curve with error bars
- `transition_analysis.png`: Bar charts showing category transitions

**Key Features**:
- **Rigorous Statistics**: Uses Wilson score intervals for binomial proportions, Fleiss standard errors for kappa
- **Three Comparisons**: AI vs Expected, AI vs Human, Human vs Human inter-rater agreement
- **Significance Testing**: Chi-square tests for independence with p-value interpretation
- **Confidence Assessment**: Evaluates whether AI confidence levels correlate with actual accuracy
- **Transition Analysis**: Identifies patterns in evaluation changes for temporal validity studies
- **Publication-Ready**: Generates formatted reports and high-resolution plots (300 DPI)

**Statistical Methods**:
- Wilson score interval for concordance rate confidence intervals (better coverage than normal approximation)
- Fleiss et al. (1969) formula for Cohen's kappa standard errors
- Pearson chi-square test for categorical independence
- Landis & Koch (1977) interpretation scale for kappa values

**Documentation**:
- Complete guide: `doc/users/FACT_CHECKER_STATS_GUIDE.md`
- Statistical methods and interpretation guidelines included
- Example output with real-world interpretation

### Enum-Based Workflow System
```python
from bmlibrarian.agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent, 
    ReportingAgent, CounterfactualAgent, EditorAgent, AgentOrchestrator
)
from bmlibrarian.cli.workflow_steps import (
    WorkflowStep, WorkflowDefinition, WorkflowExecutor, 
    create_default_research_workflow, StepResult
)

# Initialize workflow system
workflow_definition = create_default_research_workflow()
workflow_executor = WorkflowExecutor(workflow_definition)

# Initialize orchestrator and agents
orchestrator = AgentOrchestrator(max_workers=4)
query_agent = QueryAgent(orchestrator=orchestrator)
scoring_agent = DocumentScoringAgent(orchestrator=orchestrator)
citation_agent = CitationFinderAgent(orchestrator=orchestrator)
reporting_agent = ReportingAgent(orchestrator=orchestrator)
counterfactual_agent = CounterfactualAgent(orchestrator=orchestrator)
editor_agent = EditorAgent(orchestrator=orchestrator)

# Set up workflow context
user_question = "What are the cardiovascular benefits of exercise?"
workflow_executor.add_context('research_question', user_question)

# Execute workflow steps
current_step = workflow_definition.steps[0]
while current_step:
    execution = workflow_executor.execute_step(current_step, step_handler)
    workflow_executor.execution_history.append(execution)
    
    if execution.result == StepResult.SUCCESS:
        current_step = workflow_definition.get_next_step(current_step, workflow_executor.context)
    elif execution.result == StepResult.BRANCH:
        current_step = workflow_executor.get_context('branch_to_step')
    else:
        break

# Get final results from context
final_report = workflow_executor.get_context('comprehensive_report')
counterfactual_analysis = workflow_executor.get_context('counterfactual_analysis')
```

### Basic Multi-Agent Workflow (Legacy)
```python
# For direct agent usage without workflow orchestration
from bmlibrarian.agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent, 
    ReportingAgent, CounterfactualAgent, AgentOrchestrator
)

# Initialize orchestrator and agents
orchestrator = AgentOrchestrator(max_workers=4)
query_agent = QueryAgent(orchestrator=orchestrator)
scoring_agent = DocumentScoringAgent(orchestrator=orchestrator)
citation_agent = CitationFinderAgent(orchestrator=orchestrator)
reporting_agent = ReportingAgent(orchestrator=orchestrator)
counterfactual_agent = CounterfactualAgent(orchestrator=orchestrator)

# Manual workflow execution
user_question = "What are the cardiovascular benefits of exercise?"
documents = query_agent.search_documents(user_question)
scored_docs = [(doc, scoring_agent.evaluate_document(user_question, doc)) 
               for doc in documents if scoring_agent.evaluate_document(user_question, doc)]
citations = citation_agent.process_scored_documents_for_citations(
    user_question=user_question, scored_documents=scored_docs, score_threshold=2.5)
report = reporting_agent.generate_citation_based_report(
    user_question=user_question, citations=citations, format_output=True)
```

### Key Features Demonstrated
- **Enum-Based Workflow**: Flexible step orchestration with meaningful names
- **Iterative Processing**: Repeatable steps for query refinement and evidence enhancement
- **Natural Language Processing**: Convert questions to database queries
- **Relevance Assessment**: AI-powered document scoring (1-5 scale)
- **Citation Extraction**: Extract specific passages that answer questions
- **Evidence Synthesis**: Generate professional medical reports with proper references
- **Counterfactual Analysis**: Generate research questions to find contradictory evidence
- **Comprehensive Editing**: Balanced report integration with all evidence types
- **Quality Control**: Document verification and evidence strength assessment
- **Confidence Assessment**: Evaluate evidence reliability with contradictory evidence search
- **Agent-Driven Refinement**: Agents can request more citations during report generation
- **Auto Mode Support**: Non-interactive execution with graceful error handling
- **Scalable Processing**: Queue-based batch processing for large datasets

## Important Instructions and Reminders
### When developing new agents or features:
1. **Always inherit from BaseAgent** for consistent interfaces
2. **Use configuration system**: Load models via `get_model()` and settings via `get_agent_config()`
3. **Filter configuration parameters**: Only pass supported parameters to agent constructors
4. **Process ALL documents by default**: No artificial limits unless explicitly configured
5. **Implement comprehensive testing** with realistic test data
6. **Create both user and developer documentation** for all new features
7. **Never create or modify production database** without explicit permission
8. **Ensure document ID verification** to prevent citation hallucination
9. **Support queue-based processing** for scalability
10. **Include progress tracking** for long-running operations
11. **Use enum-based workflow system** for new workflow steps (workflow_steps.py)
12. **Use modular GUI architecture** for new GUI features (see src/bmlibrarian/gui/)
13. **Include counterfactual analysis** capabilities where appropriate for evidence validation
14. **Implement workflow step handlers** for agent integration with orchestration system
15. **Support auto mode execution** with graceful fallbacks for interactive features

### Testing and Quality Assurance:
- Run full test suite: `uv run python -m pytest tests/`
- Test CLI: `uv run python bmlibrarian_cli.py --quick`
- Test Research GUI: `uv run python bmlibrarian_research_gui.py --auto "test question" --quick`
- Test Configuration GUI: `uv run python bmlibrarian_config_gui.py`
- Test agent demos: `uv run python examples/agent_demo.py`
- Test counterfactual analysis: `uv run python examples/counterfactual_demo.py`
- Verify Ollama connection before LLM operations
- Validate all citations reference real database documents
- Check evidence strength assessments are appropriate
- Verify counterfactual analysis generates meaningful research questions
- Ensure agents use configured models from config.json
- Test document processing without artificial limits

## The "golden rules" of programming for BMLibrarian
1. **Never trust input from users, external data, network or file data**: Always validate and sanitize input. Never trust that it will be in the expected format or contain the expected data.
2. **No magic numbers**: Always use constants or configuration for numbers. Never hardcode numbers. Always use named constants for numbers that are used in multiple places.
3. **No hardcoded paths**: Always use constants or configuration for paths. Never hardcode paths. Always use named constants for paths that are used in multiple places. and the migration system:
4. **All model communication happnes through thepython ollama library**: Never use raw HTTP requests to communicate with Ollama. Always use the `ollama` library.
5. **ALl postgres database communication happens through the database manager** Never use psycopg connection directly or modify the database structure/schema without prper migration
6. **All parameters must have type hints**: No exceptions.
7. **All functions, methods, and classes must have docstrings**: No exceptions.
8. **All errors must be handled, logged, and reported to the user**: No exceptions.
9. **No inline style sheets**: All stylesheets must be generated by the stylesheet generator / centralised styling system (stylesheet_generator.py).
10. **No hardcoded pixel values**: All dimensions must be calculated from font metrics or relative to other elements, generally using our dpi font scaling system (dpi_scale.py).
10. **All errors must be reported to the user**: No exceptions.
11. **we prefer reusable pure functions over more comlex larger structures.** Where possible, such pure functions shoudl be factored out into generally useful libraries
12. **All modules need to be documented in markdown format** in doc/users for the end user, and doc/debvelopers for developers. Importantinformation for the AI assistantgo into doc/llm.