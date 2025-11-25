# BMLibrarian

A Python library and app providing AI-powered access to biomedical literature databases. BMLibrarian features a multi-agent multi-model architecture with specialized agents for query processing, document scoring, citation extraction, report generation, and counterfactual analysis, all coordinated through an advanced task queue orchestration system. 

A specialised submodule can be used as a fact checker on biomdeical statements. It will systematically search available literature (via BMLibrarian) that supports or contradicts the statement. Prime use case will be automated validation of machine generated training data sets.

BMLibrarian is able to run entirely with local models, and does not need any network connection other than for periodic synchronisation with data from PubMed and MedXiv. 

BMLibrarian does not require any API keys nor any proprietary libraries or services.

## What's New 🎉

**Latest Features (11/2025):**
- 🔍 **Fact Checker System**: LLM training data auditing with literature validation
      - **CLI & Desktop GUI**: Batch processing and interactive human review interfaces
      - **Blind Mode**: Review statements without AI bias for unbiased human annotation
      - **Incremental Mode**: Smart filtering to show only unannotated statements
      - **SQLite Integration**: Persistent database storage with intelligent JSON import/merge

- **Citation Hallucination Prevention**: Validation system ensures all citations reference real documents
- 🚀 **Multi-Model Query Generation**: Use up to 3 AI models simultaneously for 20-40% more relevant documents
- 📊 **Query Performance Tracking**: Real-time analysis showing which models find the best documents
- 🗄️ **PostgreSQL Audit Trail**: Complete persistent tracking of research workflow sessions
- ⚡ **Automatic Database Migrations**: Zero-configuration schema updates on startup
- 📈 **Smart Result Pagination**: Efficient handling of large document sets across multiple queries
- 🎯 **Performance Statistics**: See which models and parameters work best for your research
- 🔧 **Enhanced Configuration GUI**: Dedicated tab for multi-model query generation setup

## Overview

BMLibrarian transforms how researchers interact with biomedical literature by combining AI-powered natural language processing with robust database infrastructure. The system employs multiple specialized AI agents that work together to convert research questions into comprehensive, evidence-based medical reports with proper citations and balanced analysis of contradictory evidence.

## ARCHITECTURAL SCALE

### Codebase Statistics

- **347 Python files** organized in hierarchical module structure
- **437 classes** implementing specialized functionality
- **3,654 functions** providing granular capabilities
- **104,000 lines of code** (excluding comments, docstrings, and blank lines)
- **> 8,000 lines of docstrings** for comprehensive documentation
- **100% type hints** for all public APIs and data structures
- **100% docstrings** for all public APIs, classes, methods, and functions
- **Comprehensive test coverage:** >95% across critical modules

### Comparison to Established Systems

| System | Lines of Code | Domain | Status |
|--------|---------------|--------|--------|
| Redis | ~30,000 | Database | Production |
| nginx | ~100,000 | Web server | Production |
| **BMLibrarian** | **~104,000** | **Biomedical AI** | **functional prototype** |
| Django | ~300,000 | Web framework | Production |

**BMLibrarian is comparable in scale to mature, widely-deployed infrastructure software.**

---

## WHAT THIS SCALE REPRESENTS

### Not a PhD Side Project — Infrastructure Software

**Multi-layer architecture:**
- **Core database layer:** PostgreSQL integration with custom query optimization
- **Vector search layer:** pgvector integration with HNSW indexing at 40M document scale
- **Agent orchestration layer:** 13+ specialized AI agents with sophisticated coordination
- **Workflow management layer:** Persistent task queuing, state management, error recovery
- **Multiple user interfaces:** CLI, desktop GUI (Flet + Qt), web mode, laboratory tools
- **Full-text discovery system:** Multi-source PDF retrieval with browser automation
- **Research quality assessment:** PRISMA 2020, PICO extraction, study design evaluation
- **Fact-checking infrastructure:** Statement validation, training data auditing
- **Configuration management:** Hierarchical config system with GUI editors
- **Database migrations:** Automatic schema updates with version tracking
- **Comprehensive documentation:** User guides + developer docs for every major component

### Development Methodology

**Professional software engineering practices:**
- ✅ Type hints throughout (Python 3.12+)
- ✅ Comprehensive unit testing (>95% coverage)
- ✅ Modular architecture with clear separation of concerns
- ✅ Configuration-driven design (no hardcoded parameters)
- ✅ Extensive error handling and logging
- ✅ Database transaction management and connection pooling
- ✅ Async/parallel processing where appropriate
- ✅ GUI/CLI separation for testability
- ✅ Plugin architecture for extensibility
---

## Fact Checker System 🔍

The **BMLibrarian Fact Checker** is a specialized tool for auditing biomedical statements in LLM training datasets, medical knowledge bases, and research claims. It evaluates statement veracity by searching literature databases and comparing claims against published evidence.

### Core Capabilities

- **Automated Verification**: Evaluates biomedical statements as yes/no/maybe based on literature evidence
- **Evidence Extraction**: Provides specific citations with stance indicators (supports/contradicts/neutral)
- **Batch Processing**: Process hundreds of statements from JSON input files
- **Confidence Assessment**: Rates confidence (high/medium/low) based on evidence strength and consistency
- **Citation Validation**: Prevents hallucination by validating all citations reference real database documents
- **Human Review Interface**: Desktop GUI for annotation, comparison, and quality control

### Key Features

#### CLI Tool (`fact_checker_cli.py`)
- **Batch fact-checking** from JSON input files
- **Incremental processing** - smart detection of previously evaluated statements
- **SQLite database storage** for persistent results and annotations
- **Flexible thresholds** for relevance scoring and citation extraction
- **Quick mode** for faster testing with reduced document sets
- **Detailed output** with evidence metadata and validation statistics

#### Review GUI (`fact_checker_review_gui.py`)
- **Interactive human review** with statement-by-statement navigation
- **Blind mode** - hide AI evaluations to prevent bias during human annotation
- **Incremental mode** - filter to show only unannotated statements for efficient review
- **Database integration** - automatic SQLite database creation from JSON files
- **Intelligent merging** - import new statements without overwriting existing annotations
- **Citation inspection** - expandable cards with full abstracts and highlighted passages
- **Multi-user support** - track annotations by different reviewers
- **Export functionality** - save human-annotated results for analysis

### Use Cases

1. **LLM Training Data Auditing**: Verify factual accuracy of biomedical statements in training datasets
2. **Medical Knowledge Validation**: Check medical claims against current literature
3. **Dataset Quality Control**: Identify potentially incorrect statements in medical corpora
4. **Evidence-Based Verification**: Validate medical facts with specific literature references
5. **Research Claim Verification**: Evaluate research statements before publication

### Database Workflow

The fact checker uses SQLite databases for persistent storage:

1. **First run with JSON**: Creates `.db` file alongside input JSON (e.g., `results.json` → `results.db`)
2. **Subsequent runs**: Intelligently merges new statements from JSON without overwriting existing evaluations/annotations
3. **Real-time persistence**: All AI evaluations and human annotations saved immediately to database
4. **Incremental processing**: Skip already-evaluated statements with `--incremental` flag
5. **Cross-tool compatibility**: CLI and GUI share the same database format

### Example Workflow

```bash
# Step 1: Generate fact-check results from statements
uv run python fact_checker_cli.py statements.json -o results.json
# Creates: results.json (JSON output) and results.db (SQLite database)

# Step 2: Review with GUI in blind mode (no AI bias)
uv run python fact_checker_review_gui.py --input-file results.db --blind --user alice
# Human reviewer annotates statements without seeing AI evaluations

# Step 3: Review remaining statements in normal mode
uv run python fact_checker_review_gui.py --input-file results.db --incremental --user alice
# Shows only statements not yet annotated by alice

# Step 4: Export annotated results
# Use GUI "Save Reviews" button → results_annotated.json

# Step 5: Analyze results
uv run python analyze_factcheck_progress.py results_annotated.json
```

## PaperChecker System

The **BMLibrarian PaperChecker** is a sophisticated fact-checking system for medical abstracts that validates research claims by systematically searching for and analyzing contradictory evidence.

### Core Capabilities

- **Statement Extraction**: Identifies core research claims (hypothesis, finding, conclusion) from abstracts
- **Counter-Evidence Search**: Multi-strategy search (semantic + HyDE + keyword) for contradictory literature
- **Evidence-Based Verdicts**: Three-class classification (supports/contradicts/undecided) with confidence levels
- **Complete Audit Trail**: Full provenance tracking from search to final verdict
- **Batch Processing**: CLI for processing multiple abstracts with database persistence

### Key Features

#### CLI Tool (`paper_checker_cli.py`)
- **Batch fact-checking** of medical abstracts from JSON or by PMID
- **Multi-strategy search** combining semantic, HyDE, and keyword approaches
- **Counter-report generation** synthesizing contradictory evidence
- **Markdown export** for detailed reports per abstract
- **Database persistence** in PostgreSQL `papercheck` schema

#### Laboratory GUI (`paper_checker_lab.py`)
- **Interactive testing** with step-by-step workflow visualization
- **Real-time progress** showing each processing stage
- **Results inspection** for all intermediate outputs
- **Desktop and web modes** for flexible deployment

### Workflow Overview

```
Abstract → Statement Extraction → Counter-Statement Generation →
Multi-Strategy Search → Document Scoring → Citation Extraction →
Counter-Report Generation → Verdict Analysis → JSON/Markdown Output
```

### Example Usage

```bash
# Check abstracts from JSON file
uv run python paper_checker_cli.py abstracts.json -o results.json

# Export detailed markdown reports
uv run python paper_checker_cli.py abstracts.json --export-markdown reports/

# Check abstracts by PMID from database
uv run python paper_checker_cli.py --pmid 12345678 23456789

# Quick mode for testing
uv run python paper_checker_cli.py abstracts.json --quick

# Interactive laboratory
uv run python paper_checker_lab.py
```

### Documentation

- [User Guide](doc/users/paper_checker_guide.md) - Overview and quick start
- [CLI Guide](doc/users/paper_checker_cli_guide.md) - Command-line reference
- [Laboratory Guide](doc/users/paper_checker_lab_guide.md) - Interactive testing
- [Architecture](doc/developers/paper_checker_architecture.md) - System design

## Key Features

### 🤖 Multi-Agent AI System
- **QueryAgent**: Natural language to PostgreSQL query conversion
- **DocumentScoringAgent**: Relevance scoring for research questions (1-5 scale)
- **CitationFinderAgent**: Extracts relevant passages from high-scoring documents
- **ReportingAgent**: Synthesizes citations into medical publication-style reports
- **CounterfactualAgent**: Analyzes documents to generate research questions for finding contradictory evidence
- **EditorAgent**: Creates balanced comprehensive reports integrating all evidence
- **FactCheckerAgent**: Evaluates biomedical statements (yes/no/maybe) with literature evidence for training data auditing
- **PaperCheckerAgent**: Validates medical abstract claims against contradictory literature evidence

### 🔄 Advanced Workflow Orchestration
- **Enum-Based Workflow**: Flexible step orchestration with meaningful names
- **Iterative Processing**: Query refinement, threshold adjustment, citation requests
- **Task Queue System**: SQLite-based persistent task queuing for memory-efficient processing
- **Human-in-the-Loop**: Interactive decision points with auto-mode support
- **Branching Logic**: Conditional step execution and error recovery

### 🏗️ Production-Ready Infrastructure
- **Database Migration System**: Automated schema initialization and incremental updates with startup integration
- **PostgreSQL + pgvector**: Semantic search with vector embeddings
- **PostgreSQL Audit Trail**: Comprehensive tracking of research workflow sessions, queries, documents, and evaluations
- **Local LLM Integration**: Ollama service for privacy-preserving AI inference
- **Comprehensive Testing**: Unit tests for all agents with >95% coverage
- **GUI Applications**: Desktop interfaces for research and configuration
- **Browser-Based Downloader**: Playwright automation for Cloudflare-protected PDFs (optional)

### 📊 Advanced Analytics
- **Multi-Model Query Generation**: Use multiple AI models (up to 3) to generate diverse database queries for 20-40% improved document retrieval
- **Query Performance Tracking**: Real-time analysis of which models and parameters find the most relevant documents
- **Counterfactual Analysis**: Systematic search for contradictory evidence with progressive audit trail
- **Evidence Strength Assessment**: Quality evaluation with citation validation and rejection reasoning
- **Temporal Precision**: Specific year references instead of vague temporal terms
- **Document Verification**: Real database ID validation to prevent hallucination
- **Citation Validation**: AI-powered verification that citations actually support counterfactual claims
- **User Override Capability**: Expert users can override AI rejection decisions with custom reasoning
- **Research Workflow Audit Trail**: PostgreSQL-based persistent tracking of complete research sessions

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd bmlibrarian

# Install dependencies using uv (recommended)
uv sync
```

### Prerequisites

- **Python**: 3.12+ (required for modern type hints and performance)
- **Database**: PostgreSQL 12+ with pgvector extension
- **AI/LLM**: Ollama server for local language model inference
- **Extensions**: `pgvector`, `pg_trgm` for semantic search capabilities

### Environment Setup

1. **Configure database and AI settings:**
```bash
# Create .env file in project directory
cat > .env << EOF
# Database Configuration
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=knowledgebase

# File System
PDF_BASE_DIR=~/knowledgebase/pdf

# AI/LLM Configuration (Ollama typically runs on localhost:11434)
OLLAMA_BASE_URL=http://localhost:11434
EOF
```

2. **Start required services:**
```bash
# Start Ollama service (for AI inference)
ollama serve

# Ensure PostgreSQL is running with pgvector extension
psql -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Usage Examples

#### Interactive Research CLI
```bash
# Start the comprehensive medical research CLI
uv run python bmlibrarian_cli.py

# Quick testing mode
uv run python bmlibrarian_cli.py --quick

# Automated mode with research question
uv run python bmlibrarian_cli.py --auto "What are the cardiovascular benefits of exercise?"
```

#### Desktop Research Application
```bash
# Launch the GUI research application
uv run python bmlibrarian_research_gui.py

# Features:
# - Visual workflow progress with collapsible step cards
# - Real-time agent execution with model configuration
# - Multi-model query generation with smart pagination and result tracking
# - Query performance statistics showing model effectiveness
# - Progressive counterfactual audit trail showing claims, queries, searches, and results
# - Formatted markdown report preview with scrolling
# - Direct file save functionality
# - Complete transparency into citation validation and rejection reasoning
# - Automatic audit trail persistence to PostgreSQL database
```

#### Configuration GUI
```bash
# Launch the configuration interface
uv run python bmlibrarian_config_gui.py

# Configure agents, models, and parameters through GUI:
# - Model selection with live refresh from Ollama
# - Parameter tuning with interactive sliders
# - Multi-model query generation configuration tab
# - Connection testing and validation
# - Visual value displays for all configuration parameters
```

#### Fact Checker CLI for LLM Training Data Auditing
```bash
# Check biomedical statements against literature evidence
uv run python fact_checker_cli.py input.json -o results.json

# Input format (input.json):
# [
#   {"statement": "All cases of childhood UC require colectomy", "answer": "no"},
#   {"statement": "Vitamin D deficiency is common in IBD", "answer": "yes"}
# ]

# This creates TWO outputs:
#   - results.json: JSON file with fact-check results
#   - results.db: SQLite database for persistent storage

# Incremental mode - skip already-evaluated statements
uv run python fact_checker_cli.py input.json -o results.json --incremental
# Only processes new statements, preserves existing evaluations

# Quick mode for faster testing
uv run python fact_checker_cli.py input.json -o results.json --quick

# Custom thresholds for precision control
uv run python fact_checker_cli.py input.json -o results.json \
  --score-threshold 3.0 --max-search-results 100 --max-citations 15

# Verbose mode with detailed output
uv run python fact_checker_cli.py input.json -o results.json -v --detailed

# Custom model selection
uv run python fact_checker_cli.py input.json -o results.json \
  --model medgemma-27b-text-it-Q8_0:latest --temperature 0.15

# Run demonstration
uv run python examples/fact_checker_demo.py
```

#### Fact-Checker Review GUI
```bash
# Human review and annotation of fact-checking results
uv run python fact_checker_review_gui.py

# Load JSON file (auto-creates SQLite database for annotations)
uv run python fact_checker_review_gui.py --input-file results.json

# Load existing database directly
uv run python fact_checker_review_gui.py --input-file results.db

# BLIND MODE - hide AI evaluations to prevent annotation bias
uv run python fact_checker_review_gui.py --input-file results.db --blind --user alice
# Perfect for unbiased human annotation without AI influence

# INCREMENTAL MODE - show only unannotated statements
uv run python fact_checker_review_gui.py --input-file results.db --incremental --user alice
# Efficiently review only statements you haven't annotated yet

# Multi-user workflow with user tracking
uv run python fact_checker_review_gui.py --input-file results.db --user bob
# Track annotations by different reviewers

# Features:
# - Automatic SQLite database creation from JSON files
# - Intelligent merging: import new statements without overwriting existing annotations
# - Real-time persistence: all annotations saved immediately to database
# - Statement-by-statement review with progress tracking
# - Compare original, AI, and human annotations side-by-side
# - Expandable citation cards with full abstracts and highlighted passages
# - Color-coded stance indicators (supports/contradicts/neutral)
# - Blind mode for unbiased annotation (hide AI evaluations)
# - Incremental mode for efficient review (filter unannotated statements)
# - Multi-user support with annotator metadata
# - Export reviewed annotations to JSON file
# - Perfect for quality control and training data validation
```

#### Browser-Based PDF Download (Optional)

For PDFs protected by Cloudflare or anti-bot measures:

```bash
# Install browser automation support (optional)
uv add --optional browser
uv run python -m playwright install chromium

# Download PDFs using browser automation
uv run python download_pdfs_with_browser.py --batch-size 20

# Run with visible browser (for debugging)
uv run python download_pdfs_with_browser.py --visible

# Test the browser downloader
uv run python test_browser_download.py
```

See [BROWSER_DOWNLOADER.md](BROWSER_DOWNLOADER.md) for detailed documentation on:
- Cloudflare bypass techniques
- CAPTCHA handling
- Stealth mode configuration
- Performance optimization

#### Multi-Agent Workflow (Programmatic)
```python
from bmlibrarian.agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent, 
    ReportingAgent, CounterfactualAgent, EditorAgent, 
    AgentOrchestrator
)
from bmlibrarian.cli.workflow_steps import (
    create_default_research_workflow, WorkflowExecutor
)

# Initialize orchestration system
orchestrator = AgentOrchestrator(max_workers=4)
workflow = create_default_research_workflow()
executor = WorkflowExecutor(workflow)

# Initialize specialized agents
query_agent = QueryAgent(orchestrator=orchestrator)
scoring_agent = DocumentScoringAgent(orchestrator=orchestrator)
citation_agent = CitationFinderAgent(orchestrator=orchestrator)
reporting_agent = ReportingAgent(orchestrator=orchestrator)
counterfactual_agent = CounterfactualAgent(orchestrator=orchestrator)
editor_agent = EditorAgent(orchestrator=orchestrator)

# Execute research workflow
research_question = "What are the cardiovascular benefits of exercise?"
executor.add_context('research_question', research_question)

# The workflow handles: query generation, document search, scoring,
# citation extraction, report generation, and counterfactual analysis
final_report = executor.get_context('comprehensive_report')
```

## Architecture Overview

### Multi-Agent System Architecture

BMLibrarian employs a sophisticated multi-agent architecture where specialized AI agents collaborate to process biomedical literature:

```mermaid
graph TD
    A[Research Question] --> B[QueryAgent]
    B --> C[Database Search]
    C --> D[DocumentScoringAgent]
    D --> E[CitationFinderAgent]
    E --> F[ReportingAgent]
    F --> G{Counterfactual Analysis?}
    G -->|Yes| H[CounterfactualAgent]
    G -->|No| I[EditorAgent]
    H --> J[Contradictory Evidence Search]
    J --> I
    I --> K[Comprehensive Report]
```

### Workflow Orchestration System

The enum-based workflow system provides flexible step orchestration:

- **WorkflowStep Enum**: Meaningful step names instead of brittle numbering
- **Repeatable Steps**: Query refinement, threshold adjustment, citation requests
- **Branching Logic**: Conditional step execution and error recovery
- **Context Management**: State preservation across step executions
- **Auto Mode Support**: Graceful handling of non-interactive execution

### Task Queue System

- **QueueManager**: SQLite-based persistent task queuing
- **AgentOrchestrator**: Coordinates multi-agent workflows
- **Task Priorities**: HIGH, NORMAL, LOW priority levels
- **Batch Processing**: Memory-efficient handling of large document sets

## Application Suite

### Command Line Interface (CLI)
The interactive medical research CLI (`bmlibrarian_cli.py`) provides:
- Full 12-step research workflow with enum-based orchestration
- Human-in-the-loop decision points with auto-mode support
- Query refinement and threshold adjustment capabilities
- Counterfactual analysis for comprehensive evidence evaluation
- Enhanced markdown export with proper citation formatting

### Fact-Checker CLI
The fact-checking command-line tool (`fact_checker_cli.py`) provides:
- **Batch processing** of biomedical statements from JSON files
- **Literature validation** with AI-powered yes/no/maybe evaluations
- **SQLite database storage** for persistent results and incremental processing
- **Evidence extraction** with citation stance indicators and confidence assessment
- **Incremental mode** - skip already-evaluated statements for efficient processing
- **Flexible thresholds** - control relevance scoring and citation extraction
- **Validation support** - compare AI evaluations against expected answers
- **Detailed output** - comprehensive metadata, statistics, and evidence lists

### Fact-Checker Review GUI
The human review desktop application (`fact_checker_review_gui.py`) provides:
- **Interactive review interface** with statement-by-statement navigation
- **Blind mode** - hide AI evaluations to prevent annotation bias for unbiased human judgments
- **Incremental mode** - filter to show only unannotated statements for efficient review
- **Database integration** - automatic SQLite database creation and intelligent JSON import/merge
- **Citation inspection** - expandable cards with full abstracts and highlighted passages
- **Multi-user support** - track annotations by different reviewers with metadata
- **Comparison view** - see original annotations, AI evaluations, and human annotations side-by-side
- **Real-time persistence** - all annotations saved immediately to database
- **Export functionality** - save human-annotated results to JSON for analysis
- **Quality control** - perfect for training data validation and model evaluation

### Desktop Research Application
The GUI research application (`bmlibrarian_research_gui.py`) offers:
- Native cross-platform desktop interface built with Flet
- Visual workflow progress with collapsible step cards
- **Multi-model query generation** with smart pagination and result tracking:
  - 🔍 Multiple AI models generate diverse database queries
  - 📊 Per-query result counts showing documents found by each model
  - 📈 Real-time performance statistics identifying best-performing models
  - 🎯 Unique document tracking showing which models find documents others miss
- **Progressive counterfactual audit trail** with real-time updates showing:
  - 📋 Identified claims with confidence levels
  - ❓ Counterfactual research questions with priority badges
  - 🔍 Database searches with PostgreSQL queries
  - 📊 Search results with color-coded relevance scores
  - 📝 Citation extraction showing validated, rejected, and no-extraction cases
  - 📈 Summary statistics and confidence assessment
- **PostgreSQL audit trail** for persistent session tracking and historical analysis
- Real-time agent execution with configured AI models
- Formatted markdown report preview with scrollable display
- Direct file save functionality (macOS-compatible)
- Complete transparency into citation validation and rejection reasoning

### Configuration Interface
The configuration GUI (`bmlibrarian_config_gui.py`) provides:
- Tabbed interface for agent-specific configuration
- Model selection with live refresh from Ollama server
- Parameter adjustment with interactive sliders and visual value displays
- **Multi-model query generation configuration tab** for setting up multiple models
- Connection testing and validation tools
- Support for configuring query diversity, pagination, and performance tracking

### Laboratory Tools
- **QueryAgent Lab** (`query_lab.py`): Experimental interface for natural language to SQL conversion
- **Agent Demonstrations**: Examples showcasing multi-agent capabilities
- **Citation System**: Advanced citation extraction and formatting

## Configuration System

### Configuration File Locations
BMLibrarian uses a hierarchical configuration system:

- **Primary**: `~/.bmlibrarian/config.json` (recommended, OS agnostic)
- **Legacy fallback**: `bmlibrarian_config.json` in current directory
- **GUI default**: Always saves to `~/.bmlibrarian/config.json`

### Agent Configuration
Each agent can be individually configured with:
- **Model Selection**: Choose from available Ollama models
- **Temperature**: Control creativity/randomness (0.0-1.0)
- **Top-P**: Control nucleus sampling (0.0-1.0)
- **Agent-Specific Settings**: Citation count limits, scoring thresholds, etc.

### Multi-Model Query Generation Configuration
Configure query diversity for improved document retrieval:
- **Multi-Model Enabled**: Toggle feature on/off (default: disabled)
- **Models**: Select up to 3 different AI models for query generation
- **Queries Per Model**: Generate 1-3 diverse queries per model
- **Execution Mode**: Serial execution optimized for local instances
- **De-duplication**: Automatic query and document de-duplication
- **User Control**: Option to review and select generated queries before execution

Example configuration:
```json
{
  "query_generation": {
    "multi_model_enabled": true,
    "models": ["medgemma-27b-text-it-Q8_0:latest", "gpt-oss:20b", "medgemma4B_it_q8:latest"],
    "queries_per_model": 1,
    "execution_mode": "serial",
    "deduplicate_results": true,
    "show_all_queries_to_user": true,
    "allow_query_selection": true
  }
}
```

### Environment Variables

```bash
# Database Configuration
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password  
POSTGRES_HOST=localhost          # Default: localhost
POSTGRES_PORT=5432              # Default: 5432
POSTGRES_DB=knowledgebase       # Default: knowledgebase

# File System
PDF_BASE_DIR=~/knowledgebase/pdf # Base directory for PDF files

# AI/LLM Configuration  
OLLAMA_BASE_URL=http://localhost:11434  # Ollama server URL
```

### Using .env Files

Create a `.env` file in your project directory:
```env
# Database settings
POSTGRES_USER=bmlib_user
POSTGRES_PASSWORD=secure_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=knowledgebase

# AI settings
OLLAMA_BASE_URL=http://localhost:11434
PDF_BASE_DIR=~/knowledgebase/pdf
```

### Default AI Models
- **Complex Tasks**: `gpt-oss:20b` (comprehensive analysis, report generation)
- **Fast Processing**: `medgemma4B_it_q8:latest` (quick scoring, classification)
- **Multi-Model Query Generation**: Combine multiple models for query diversity:
  - `medgemma-27b-text-it-Q8_0:latest` (medical domain specialist)
  - `gpt-oss:20b` (general purpose with strong reasoning)
  - `medgemma4B_it_q8:latest` (fast queries with medical focus)

## Documentation

Comprehensive documentation is available in the `doc/` directory:

### User Guides
- **[Getting Started](doc/users/getting_started.md)** - Quick start guide and installation
- **[Configuration Guide](doc/users/configuration_guide.md)** - System configuration and settings
- **[CLI Guide](doc/users/cli_guide.md)** - Command-line interface usage
- **[Research GUI Guide](doc/users/research_gui_guide.md)** - Desktop research application
- **[Config GUI Guide](doc/users/config_gui_guide.md)** - Configuration interface
- **[Fact Checker Guide](doc/users/fact_checker_guide.md)** - LLM training data auditing and statement verification
- **[Fact Checker Review Guide](doc/users/fact_checker_review_guide.md)** - Human annotation and review GUI
- **[Query Agent Guide](doc/users/query_agent_guide.md)** - Natural language query processing
- **[Multi-Model Query Guide](doc/users/multi_model_query_guide.md)** - Multi-model query generation
- **[Query Performance Tracking](doc/users/query_performance_tracking.md)** - Performance analysis
- **[Citation Guide](doc/users/citation_guide.md)** - Citation extraction and formatting
- **[Reporting Guide](doc/users/reporting_guide.md)** - Report generation and export
- **[Counterfactual Guide](doc/users/counterfactual_guide.md)** - Contradictory evidence analysis
- **[Workflow Guide](doc/users/workflow_guide.md)** - Workflow orchestration system
- **[Migration System](doc/users/migration_system.md)** - Database migration system
- **[Troubleshooting](doc/users/troubleshooting.md)** - Common issues and solutions

### Developer Documentation
- **[Agent Module](doc/developers/agent_module.md)** - Multi-agent system architecture
- **[Citation System](doc/developers/citation_system.md)** - Citation processing internals
- **[Reporting System](doc/developers/reporting_system.md)** - Report generation system
- **[Counterfactual System](doc/developers/counterfactual_system.md)** - Evidence analysis framework
- **[Fact Checker System](doc/developers/fact_checker_system.md)** - Fact-checking architecture and internals

## Development

### Development Environment Setup

1. **Clone the repository:**
```bash
git clone <repository-url>
cd bmlibrarian
```

2. **Install dependencies using uv (recommended):**
```bash
uv sync
```

3. **Set up environment:**
```bash
# Copy example environment file
cp .env.example .env
# Edit .env with your database and Ollama settings
```

4. **Start required services:**
```bash
# Start Ollama service for AI inference
ollama serve

# Ensure PostgreSQL is running with pgvector
psql -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

5. **Database migrations run automatically:**
```bash
# No manual migration required! The system automatically:
# - Detects your database schema version
# - Applies any pending migrations on first startup
# - Creates audit trail tables for research tracking
# - Tracks migration history for safe upgrades
```

### Testing

BMLibrarian includes comprehensive testing for all agents and workflow components:

```bash
# Run all tests with coverage
uv run python -m pytest tests/ --cov=src/bmlibrarian

# Test specific components
uv run python -m pytest tests/test_query_agent.py
uv run python -m pytest tests/test_scoring_agent.py
uv run python -m pytest tests/test_citation_agent.py
uv run python -m pytest tests/test_reporting_agent.py
uv run python -m pytest tests/test_counterfactual_agent.py

# Run integration tests (requires database)
uv run python -m pytest tests/ -m integration

# Test CLI and GUI applications
uv run python bmlibrarian_cli.py --quick
uv run python bmlibrarian_research_gui.py --auto "test question" --quick
uv run python bmlibrarian_config_gui.py --debug
```

Current test coverage: **>95%** across all agent modules

### Development Commands

```bash
# Run agent demonstrations
uv run python examples/agent_demo.py
uv run python examples/citation_demo.py  
uv run python examples/reporting_demo.py
uv run python examples/counterfactual_demo.py

# Launch laboratory tools
uv run python query_lab.py  # QueryAgent experimental interface

# Run applications in development mode
uv run python bmlibrarian_cli.py --debug
uv run python bmlibrarian_research_gui.py --debug
uv run python bmlibrarian_config_gui.py --debug
```

### Development Principles

- **Modern Python Standards**: Uses Python ≥3.12 with type hints and pyproject.toml
- **Enum-Based Architecture**: Flexible workflow orchestration with meaningful step names
- **Comprehensive Testing**: Unit tests for all agents with realistic test data
- **Documentation First**: Both user guides and developer documentation for all features
- **AI-Powered**: Local LLM integration via Ollama for privacy-preserving processing
- **Scalable Architecture**: Queue-based processing for memory-efficient large-scale operations
- **Database-First Design**: PostgreSQL audit trail for complete research workflow tracking
- **Performance Monitoring**: Built-in query performance tracking and optimization insights
- **Zero-Configuration Migrations**: Automatic database schema updates on startup

### Code Quality Standards

- **BaseAgent Pattern**: All agents inherit from BaseAgent with standardized interfaces
- **Configuration Integration**: Agents use `get_model()` and `get_agent_config()` from config system
- **Document ID Integrity**: Always use real database IDs, never mock/fabricated references
- **Workflow Integration**: Agents support enum-based workflow system execution
- **No Artificial Limits**: Process ALL documents unless explicitly configured otherwise

## Security & Best Practices

- **Credentials**: Never hardcode passwords; use environment variables and .env files
- **Local AI Processing**: Uses local Ollama service to keep research data private
- **Database Safety**: Never modify production database "knowledgebase" without permission
- **Data Integrity**: All document IDs are programmatically verified to prevent hallucination
- **Input Validation**: All user inputs and LLM outputs are validated and sanitized
- **Error Handling**: Robust error recovery and logging throughout the system

## Contributing

We welcome contributions to BMLibrarian! Areas for contribution include:

### Agent Development
- New specialized agents for literature analysis tasks
- Enhanced natural language processing capabilities
- Improved evidence synthesis and reporting algorithms

### Workflow Enhancement  
- Additional workflow steps for specialized research domains
- Enhanced iterative capabilities and human-in-the-loop features
- Integration with external biomedical databases and APIs

### User Experience
- GUI improvements and new interface features
- Enhanced visualization of research workflow progress
- Mobile and web-based interface development

### Documentation & Testing
- Expanded user guides and tutorials
- Additional agent demonstrations and examples
- Performance testing and optimization

## Project Status & Maturity

BMLibrarian is a **production-ready** system with:

- ✅ **Full Multi-Agent Architecture**: Complete implementation with 6 specialized AI agents
- ✅ **Comprehensive Workflow System**: 12-step research process with iterative capabilities  
- ✅ **Robust Infrastructure**: Queue orchestration, error handling, and progress tracking
- ✅ **Multiple Interfaces**: CLI, desktop GUI, and configuration applications
- ✅ **Extensive Testing**: >95% test coverage across all agent modules
- ✅ **Complete Documentation**: Both user guides and developer documentation
- ✅ **Privacy-First**: Local LLM processing via Ollama for sensitive research data

### Recent Major Updates

#### Fact Checker System for LLM Training Data Auditing (Latest)
- **Complete fact-checking infrastructure**: CLI tool and desktop GUI for biomedical statement verification
- **Blind mode review**: Hide AI evaluations during human annotation to prevent bias
- **Incremental processing**: Smart filtering to show only unannotated statements for efficient review
- **SQLite database integration**: Persistent storage with intelligent JSON import/merge workflow
- **Citation hallucination prevention**: Validation system ensures all citations reference real database documents
- **Multi-user support**: Track annotations by different reviewers with user metadata
- **Expandable citation cards**: Full abstract display with highlighted passages for context verification
- **Database workflow**: Automatic `.db` creation from JSON files with seamless merging on subsequent imports
- **Confidence assessment**: High/medium/low confidence ratings based on evidence strength and consistency
- **Validation support**: Compare AI evaluations against expected answers for accuracy testing

#### Database Migration System & Automatic Startup
- **Automatic schema initialization**: Database migrations run automatically on application startup
- **Incremental updates**: Smart migration system tracks completed migrations and only applies new ones
- **Zero-downtime upgrades**: Seamless schema updates without manual intervention
- **Migration tracking**: Comprehensive tracking of applied migrations with timestamps

#### PostgreSQL Audit Trail System
- **Comprehensive research tracking**: Persistent storage of complete research workflow sessions
- **Session management**: Track research questions, queries, documents, scores, and citations
- **Performance analysis**: Historical query performance data for optimization insights
- **Document provenance**: Full traceability from query to final report citations
- **Integration**: Seamlessly integrated into all CLI and GUI workflows

#### Query Performance Tracking System
- **Real-time model analysis**: Track which AI models find the most relevant documents
- **Parameter optimization**: Identify best temperature, top_p, and other parameter combinations
- **Unique document tracking**: See which models find documents others miss
- **Statistical summaries**: Per-query and per-model performance metrics
- **GUI integration**: Visual display of performance statistics in research GUI

#### Multi-Model Query Generation
- **Query diversity**: Use 1-3 queries per model across up to 3 different AI models
- **Improved retrieval**: Typically finds 20-40% more relevant documents than single-model
- **Smart pagination**: Efficient handling of large result sets across multiple queries
- **Per-query result counts**: Visual display of documents found by each query/model
- **Configuration GUI**: Dedicated tab for multi-model query generation settings
- **Backward compatible**: Feature flag system (disabled by default, opt-in)

#### Progressive Counterfactual Audit Trail
- **Real-time workflow visualization**: Complete transparency into counterfactual analysis
- **Stage-by-stage display**: Claims → Questions → Searches → Results → Citations → Summary
- **Citation validation transparency**: See exactly why citations were rejected or accepted
- **Persistent audit trail**: All stages remain visible after completion for detailed study
- **User override capability**: Expert users can accept rejected citations with custom reasoning
- **Enhanced token limits**: Reduced JSON truncation errors (6K→10K tokens)
- **Consistent search parameters**: Counterfactual search uses same max_results as main search

#### Multi-Agent System Implementation
- Complete 6-agent architecture with specialized roles
- Enum-based workflow orchestration system
- SQLite-based task queue for memory-efficient processing
- Human-in-the-loop interaction with auto-mode support

#### Advanced Research Capabilities
- Counterfactual analysis for finding contradictory evidence
- Citation validation with AI-powered verification and rejection reasoning
- Comprehensive report editing with evidence integration
- Agent-driven refinement (agents can request more citations)
- Document verification to prevent citation hallucination
- Full abstract display for user judgment on rejected citations

#### Modern GUI Applications
- Desktop research application with progressive workflow visualization
- Multi-model query generation with smart pagination and performance tracking
- Query performance statistics showing model effectiveness in real-time
- Progressive counterfactual audit trail with real-time updates
- Configuration GUI with model selection and parameter tuning
- Dedicated multi-model query generation configuration tab
- Cross-platform compatibility with native desktop and web modes
- Real-time agent execution monitoring
- Color-coded relevance scores and priority badges
- Visual value displays for all configuration sliders

#### Workflow Enhancement
- Iterative query refinement and threshold adjustment
- Branching logic for conditional step execution
- Context management and state preservation
- Enhanced markdown export with proper citation formatting
- Progressive display that persists after workflow completion

#### Quality Improvements & Bug Fixes
- **Serialization fixes**: Resolved datetime and scoring result JSON export bugs
- **Performance tracking**: Restored progress callbacks for document scoring and citation extraction
- **Multi-model pagination**: Smart handling of large result sets across multiple queries
- **GUI slider improvements**: All configuration sliders now show current values visually
- **Markdown handling**: Proper parsing of code blocks in LLM query responses
- **Database connectivity**: Consistent use of DatabaseManager for all audit connections
- **Citation extraction**: Full abstract display for rejected citations to aid user judgment
- **Result deduplication**: Comprehensive statistics showing before/after deduplication comparison

## License

[License information to be added]

## Support & Community

- **Documentation**: Comprehensive guides available in the [doc/](doc/) directory
- **Issues**: Report bugs and feature requests via GitHub issues  
- **Discussions**: Join our community discussions for questions and collaboration
- **Examples**: Review demonstration scripts in the [examples/](examples/) directory

## Acknowledgments

BMLibrarian builds upon the power of:
- **PostgreSQL + pgvector**: High-performance semantic search capabilities
- **Ollama**: Local, privacy-preserving language model inference
- **Flet**: Cross-platform GUI development framework
- **Python Ecosystem**: Modern Python ≥3.12 with comprehensive typing support

---

*BMLibrarian: Transforming biomedical literature research through AI-powered multi-agent workflows* 🔬📚🤖