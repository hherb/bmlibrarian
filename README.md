# BMLibrarian

**The Biomedical Researcher's AI Workbench**

BMLibrarian is a comprehensive AI-powered platform designed to be a complete workbench for biomedical researchers, clinicians, and systematic reviewers. It provides evidence-based answers to clinical questions, peer-review quality automated assessment of research papers, and systematic fact-checking of biomedical statements—all powered by local AI models requiring no cloud APIs or external services.

## Why BMLibrarian?

### Evidence-Based Answers to Clinical Questions

Ask questions like *"What are the cardiovascular benefits of exercise?"* or *"Does metformin reduce mortality in diabetic patients?"* and receive comprehensive, citation-backed reports synthesizing evidence from the latest biomedical literature.

### Automated Research Quality Assessment

Evaluate research papers with the rigor of peer review:
- **Paper Weight Assessment**: Evaluate the evidential weight of studies based on study design, sample size, methodological quality, and risk of bias
- **PRISMA 2020 Compliance**: Assess systematic reviews against the 27-item PRISMA 2020 checklist
- **PICO Extraction**: Automatically extract Population, Intervention, Comparison, and Outcome components for systematic reviews

### Robust Fact-Checking

Validate biomedical statements with literature evidence:
- **Statement Fact-Checker**: Evaluate claims like *"Vaccine X causes Y"* against published literature
- **PaperChecker**: Validate research abstract claims by systematically searching for contradictory evidence
- **Counterfactual Analysis**: Actively search for evidence that contradicts initial findings for balanced conclusions

### Works Offline—Critical for Global Health

BMLibrarian is designed for clinicians and researchers working in areas with limited or unreliable internet connectivity:

- **Runs entirely with local AI models** via Ollama—no cloud APIs required
- **Local database** of PubMed and medRxiv publications with full-text PDFs where available
- **No API keys, subscriptions, or external services needed**
- **Periodic synchronization** with PubMed and medRxiv when connected
- **Complete functionality offline** after initial data import

This makes BMLibrarian uniquely valuable for healthcare workers in remote regions, field hospitals, developing nations, or any environment where reliable internet cannot be guaranteed.

### Multiple Search Strategies with AI Assistance

BMLibrarian employs sophisticated multi-strategy search capabilities:
- **Multi-model query generation**: Use multiple AI models to generate diverse database queries
- **Semantic search**: Vector-based similarity search using document embeddings
- **HyDE (Hypothetical Document Embeddings)**: Generate hypothetical answers to improve search relevance
- **Keyword extraction**: Traditional keyword-based search as fallback
- **Counterfactual search**: Actively search for contradictory evidence

### Privacy-Preserving AI

All AI processing happens locally on your hardware:
- **No data leaves your machine**—perfect for sensitive patient data or pre-publication research
- **No usage tracking or telemetry**
- **Complete control over model selection and parameters**

## What's New

**Latest Features (02/2026):**

### Paper Reviewer Lab

A comprehensive paper assessment tool that combines all of BMLibrarian's analysis agents into a single unified workflow. Accepts input via DOI, PMID, PDF file, or pasted text.

```bash
# Launch the Paper Reviewer Lab
uv run python scripts/paper_reviewer_lab.py
```

**11-Step Assessment Workflow:**
1. Resolve Input (fetch document metadata via DOI/PMID/PDF/text)
2. Generate Summary (2-3 sentence synopsis)
3. Extract Hypothesis (identify core claims)
4. Detect Study Type (classify research methodology)
5. PICO Analysis (Population/Intervention/Comparison/Outcome)
6. PRISMA 2020 Assessment (systematic review checklist, if applicable)
7. Paper Weight Assessment (evidential weight scoring)
8. Study Quality Assessment (trustworthiness evaluation)
9. Synthesize Strengths/Weaknesses
10. Search Contradictory Evidence (optional PubMed search)
11. Compile Comprehensive Report

**Key Features:**
- Multiple input methods: DOI, PMID, PDF file, pasted abstract text
- Real-time workflow progress visualization (PySide6/Qt)
- Model selection from available Ollama models
- Results display in Markdown and JSON
- Export to Markdown, PDF, or JSON

### Systematic Literature Review Agent

A complete systematic review automation system with human oversight and audit trails. Conducts AI-assisted literature reviews following PRISMA 2020 guidelines with configurable search strategies, quality assessment, and composite scoring.

```bash
# Run a systematic review
uv run python systematic_review_cli.py --question "Effect of statins on CVD prevention" \
    --include "RCTs" "Human studies" --exclude "Animal studies"

# GUI with checkpoint-based resume capability
uv run python systematic_review_gui.py
```

**Key Capabilities:**
- **Multi-strategy search**: Semantic, keyword, hybrid, and HyDE queries with PICO analysis
- **9-phase workflow**: Search planning, execution, filtering, scoring, quality assessment, composite scoring, classification, evidence synthesis, reporting
- **Cochrane/GRADE assessment**: Integrated quality assessment with GRADE formatting
- **Checkpoint-based resume**: Save and resume reviews across sessions
- **Human checkpoints**: Interactive mode pauses at key decision points for human review
- **Quality assessment**: Integrates StudyAssessmentAgent, PaperWeightAssessmentAgent, PICOAgent, and PRISMA2020Agent
- **Complete audit trail**: Full reproducibility with JSON, Markdown, CSV, and PRISMA flow diagram outputs
- **Configurable weights**: Customize relevance, quality, recency, and source reliability weights

### Europe PMC Full-Text and PDF Import

Download and import full-text articles and PDFs from Europe PMC's Open Access repository.

```bash
# List available Europe PMC packages (~1000+ files, ~100 articles each)
uv run python europe_pmc_bulk_cli.py list

# Download and import full-text XML with Markdown conversion
uv run python europe_pmc_bulk_cli.py sync --output-dir ~/europepmc

# Download Open Access PDFs
uv run python europe_pmc_pdf_cli.py download --output-dir ~/europepmc_pdf
```

**Key Features:**
- JATS XML to Markdown conversion (headers, figures, tables, emphasis)
- Resumable downloads with progress tracking
- Configurable rate limiting (polite mode)
- Year-based PDF organization
- PMCID range filtering

### PubMed Search Lab

Interactive PubMed search directly via the PubMed API, without requiring a local database.

```bash
uv run python scripts/pubmed_search_lab.py
```

**Key Features:**
- Natural language to PubMed query conversion
- MeSH term lookup and expansion
- Search results display with abstracts
- No local database required

### Audit Trail Validation GUI

A human review interface for validating automated evaluations in the systematic review audit trail.

```bash
uv run python audit_validation_gui.py --user alice
uv run python audit_validation_gui.py --user alice --incremental
```

**Key Features:**
- Tab-per-step organization for Queries, Scores, Citations, Reports, and Counterfactuals
- Validation statuses: Validated, Incorrect, Uncertain, or Needs Review
- Error categorization with 25+ predefined categories
- Statistics dashboard with reviewer performance tracking
- Multi-reviewer support for inter-rater reliability studies

### Citation-Aware Writing Editor

A markdown editor with integrated citation management for academic writing.

**Key Features:**
- Citation markers with `[@id:12345:Smith2023]` format
- Semantic search for finding references
- Multiple citation styles: Vancouver, APA, Harvard, Chicago
- Autosave with version history
- Export with formatted reference lists
- PostgreSQL-backed document persistence

### Other Recent Features

- **Paper Weight Assessment**: Evaluate research papers across five quality dimensions (study design, sample size, methodology, bias risk, replication)
- **PICO Extraction**: Automatically extract Population, Intervention, Comparison, and Outcome for systematic reviews
- **PRISMA 2020 Compliance**: Assess systematic reviews against the full 27-item PRISMA 2020 checklist
- **Document Interrogation**: Interactive Q&A interface for asking questions about loaded PDF, Markdown, or text documents
- **Full-Text PDF Discovery**: Automated discovery and download from PMC, Unpaywall, DOI resolution, and OpenAthens
- **PaperChecker System**: Fact-check medical abstracts by searching for contradictory literature evidence
- **Fact Checker System**: LLM training data auditing with literature validation (CLI, desktop GUI, blind mode, incremental mode, SQLite integration)
- **Multi-Model Query Generation**: Use up to 3 AI models simultaneously for 20-40% more relevant documents
- **Semantic Chunking**: Multiple chunking strategies (adaptive, sentence-based, SpaCy NLP) with vector embeddings for improved retrieval
- **LLM Provider Abstraction**: Unified interface across multiple LLM providers with token tracking
- **Thesaurus/MeSH Expansion**: Term expansion and synonym lookup for improved search coverage
- **User Authentication**: Login system with per-user database-backed settings
- **PubMed Download Repair**: CLI for detecting and fixing corrupted gzip files in bulk downloads
- **PostgreSQL Audit Trail**: Complete persistent tracking of research workflow sessions
- **Automatic Database Migrations**: Zero-configuration schema updates on startup

## Overview

BMLibrarian transforms how researchers interact with biomedical literature by combining AI-powered natural language processing with robust database infrastructure. The system employs multiple specialized AI agents that work together to convert research questions into comprehensive, evidence-based medical reports with proper citations and balanced analysis of contradictory evidence.

## ARCHITECTURAL SCALE

### Codebase Statistics

- **728 Python files** organized in hierarchical module structure
- **1,390 classes** implementing specialized functionality
- **9,671 functions** providing granular capabilities
- **~211,000 lines of code** (excluding comments, docstrings, and blank lines; ~298,000 total)
- **~8,800 docstrings** for comprehensive documentation
- **145 test files** with comprehensive test coverage
- **272 documentation files** (Markdown)
- **100% type hints** for all public APIs and data structures
- **26 top-level CLI/GUI applications**
- **17 GUI plugins** in the Qt plugin system

### Comparison to Established Systems

| System | Lines of Code | Domain | Status |
|--------|---------------|--------|--------|
| Redis | ~30,000 | Database | Production |
| nginx | ~100,000 | Web server | Production |
| Django | ~300,000 | Web framework | Production |
| **BMLibrarian** | **~211,000** | **Biomedical AI** | **Production-ready** |

**BMLibrarian exceeds the scale of many mature, widely-deployed infrastructure software projects.**

---

## WHAT THIS SCALE REPRESENTS

### Not a PhD Side Project — Infrastructure Software

**Multi-layer architecture:**
- **Core database layer:** PostgreSQL integration with custom query optimization
- **Vector search layer:** pgvector integration with HNSW indexing at 40M+ document scale
- **Agent orchestration layer:** 15+ specialized AI agents with sophisticated coordination
- **Workflow management layer:** Persistent task queuing, state management, error recovery
- **Multiple user interfaces:** CLI, desktop GUI (PySide6/Qt), laboratory tools
- **Full-text discovery system:** Multi-source PDF retrieval with browser automation
- **Semantic chunking system:** Multiple chunking strategies with vector embeddings
- **LLM provider abstraction:** Unified interface with token tracking across providers
- **Research quality assessment:** PRISMA 2020, PICO extraction, study design evaluation, paper weight scoring
- **Fact-checking infrastructure:** Statement validation, training data auditing, abstract fact-checking
- **Systematic review automation:** Checkpoint-based reviews with Cochrane/GRADE assessment
- **Configuration management:** Hierarchical config system with database-backed user settings
- **User authentication:** Login system with per-user settings and session management
- **Database migrations:** Automatic schema updates with version tracking
- **Comprehensive documentation:** 272 markdown files covering user guides + developer docs

### Development Methodology

**Professional software engineering practices:**
- Type hints throughout (Python 3.12+)
- Comprehensive unit testing (134 test files)
- Modular architecture with clear separation of concerns
- Configuration-driven design (no hardcoded parameters)
- Extensive error handling and logging
- Database transaction management and connection pooling
- Async/parallel processing where appropriate
- GUI/CLI separation for testability
- Plugin architecture for extensibility (17 GUI plugins)
---

## Fact Checker System

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
- **Native desktop application** (PySide6/Qt)

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

## Paper Weight Assessment

The **Paper Weight Assessment** system evaluates the evidential strength of biomedical research papers based on multiple dimensions, providing a comprehensive quality score that helps researchers and clinicians assess how much weight to give to study findings.

### Assessment Dimensions

| Dimension | Weight | What It Evaluates |
|-----------|--------|-------------------|
| **Study Design** | 25% | Research methodology (RCT, cohort, case-control, etc.) |
| **Sample Size** | 15% | Statistical power, confidence intervals, power calculations |
| **Methodological Quality** | 30% | Randomization, blinding, protocol registration, ITT analysis |
| **Risk of Bias** | 20% | Selection, performance, detection, and reporting biases |
| **Replication Status** | 10% | Whether findings have been replicated by other studies |

### Example Usage

```bash
# Launch the Paper Weight Laboratory (GUI)
uv run python paper_weight_lab.py

# Features:
# - Search documents by PMID, DOI, or title
# - Real-time assessment progress tracking
# - Detailed audit trail for each dimension
# - Configurable dimension weights
# - Export to Markdown or JSON
```

### Documentation

- [User Guide](doc/users/paper_weight_lab_guide.md) - Complete laboratory guide

## PICO Extraction System

The **PICO Agent** extracts structured components from biomedical research papers using the PICO framework—essential for systematic reviews and evidence-based medicine.

### What is PICO?

- **P**opulation: Who was studied? (demographics, condition, setting)
- **I**ntervention: What was done? (treatment, test, exposure)
- **C**omparison: What was the control? (placebo, alternative treatment)
- **O**utcome: What was measured? (effects, results, endpoints)

### Example Usage

```python
from bmlibrarian.agents import PICOAgent

agent = PICOAgent(model="gpt-oss:20b")
extraction = agent.extract_pico_from_document(document)

print(f"Population: {extraction.population}")
print(f"Intervention: {extraction.intervention}")
print(f"Comparison: {extraction.comparison}")
print(f"Outcome: {extraction.outcome}")
print(f"Confidence: {extraction.extraction_confidence:.1%}")
```

```bash
# Interactive PICO Laboratory
uv run python pico_lab.py

# Batch process documents
# Export to CSV for systematic review tools (Covidence, DistillerSR)
```

### Use Cases

- **Systematic Reviews**: Rapidly extract PICO from hundreds of papers
- **Meta-Analysis**: Standardize study data for quantitative synthesis
- **Research Gap Analysis**: Identify understudied populations or outcomes
- **Grant Writing**: Structure research questions using evidence-based frameworks

### Documentation

- [User Guide](doc/users/pico_agent_guide.md) - Complete PICO extraction guide
- [Developer Documentation](doc/developers/pico_agent.md) - API reference

## PRISMA 2020 Compliance Assessment

The **PRISMA 2020 Agent** assesses systematic reviews and meta-analyses against the PRISMA 2020 (Preferred Reporting Items for Systematic reviews and Meta-Analyses) 27-item checklist.

### Assessment Process

1. **Suitability Check**: Automatically determines if the document is a systematic review or meta-analysis
2. **27-Item Assessment**: Evaluates all PRISMA checklist items with detailed explanations
3. **Compliance Scoring**: Provides overall compliance percentage and category

### Scoring System

| Score | Category | Interpretation |
|-------|----------|----------------|
| 90-100% | Excellent | Outstanding adherence to PRISMA 2020 |
| 75-89% | Good | Strong reporting with minor gaps |
| 60-74% | Adequate | Acceptable with room for improvement |
| 40-59% | Poor | Significant reporting deficiencies |
| 0-39% | Very Poor | Major reporting failures |

### Example Usage

```bash
# Launch the PRISMA 2020 Laboratory (GUI)
uv run python prisma2020_lab.py

# Features:
# - Automatic suitability screening
# - Color-coded compliance cards for each item
# - Export assessments to JSON or CSV
# - Batch processing multiple reviews
```

### Use Cases

- **Self-assessment** before submitting systematic reviews to journals
- **Peer review** of systematic review manuscripts
- **Editorial screening** for journal submissions
- **Training** on PRISMA 2020 standards

### Documentation

- [User Guide](doc/users/prisma2020_guide.md) - Complete assessment guide
- [Developer Documentation](doc/developers/prisma2020_system.md) - System architecture

## Document Interrogation

The **Document Interrogation** interface provides an interactive chat experience for asking questions about loaded documents (PDFs, Markdown, or text files).

### Features

- **Split-pane interface**: Document viewer (60%) and chat interface (40%)
- **Multiple document formats**: PDF, Markdown (.md), text (.txt)
- **Dialogue-style chat**: User and AI messages in distinct bubbles
- **Full conversation history**: Scrollable message history
- **Model selection**: Choose any available Ollama model

### Example Usage

```bash
# Launch the Configuration GUI (includes Document Interrogation tab)
uv run python bmlibrarian_config_gui.py

# Workflow:
# 1. Navigate to "Document Interrogation" tab
# 2. Load a document (PDF, MD, or TXT)
# 3. Select an Ollama model
# 4. Ask questions about the document
```

### Example Questions

- *"What are the main findings of this study?"*
- *"What methods did the authors use?"*
- *"Are there any limitations mentioned?"*
- *"Summarize the introduction section"*

### Documentation

- [User Guide](doc/users/document_interrogation_guide.md) - Complete usage guide

## Full-Text PDF Discovery

The **Full-Text Discovery** system automatically finds and downloads PDF versions of academic papers through legal open access channels.

### Discovery Sources (in priority order)

1. **PubMed Central (PMC)** - Verified open access repository
2. **Unpaywall** - Open access aggregator (millions of papers)
3. **DOI Resolution** - CrossRef and doi.org content negotiation
4. **Direct URL** - Existing PDF URLs from database
5. **OpenAthens** - Institutional proxy (if configured)

### Example Usage

```python
from bmlibrarian.discovery import FullTextFinder, DocumentIdentifiers

# Create finder with Unpaywall email
finder = FullTextFinder(unpaywall_email="your@email.com")

# Discover PDF sources
identifiers = DocumentIdentifiers(doi="10.1038/nature12373")
result = finder.discover(identifiers)

if result.best_source:
    print(f"Found: {result.best_source.url}")
    print(f"Access: {result.best_source.access_type.value}")
```

```bash
# Download PDFs for documents in database
uv run python -c "from bmlibrarian.discovery import download_pdf_for_document; ..."
```

### Key Features

- **Multi-source discovery**: Searches PMC, Unpaywall, CrossRef, DOI.org
- **Priority-based selection**: Automatically selects best source (open access preferred)
- **Browser fallback**: Handles Cloudflare and anti-bot protections via Playwright
- **Year-based organization**: PDFs stored in `YYYY/filename.pdf` structure
- **Database integration**: Automatically updates document records with PDF paths

### Documentation

- [User Guide](doc/users/full_text_discovery_guide.md) - Complete discovery guide
- [Developer Documentation](doc/developers/full_text_discovery_system.md) - System architecture

## Key Features

### Multi-Agent AI System
- **QueryAgent**: Natural language to PostgreSQL query conversion
- **SemanticQueryAgent**: Vector-based semantic search with embeddings
- **DocumentScoringAgent**: Relevance scoring for research questions (1-5 scale)
- **CitationFinderAgent**: Extracts relevant passages from high-scoring documents
- **ReportingAgent**: Synthesizes citations into medical publication-style reports
- **CounterfactualAgent**: Analyzes documents to generate research questions for finding contradictory evidence
- **EditorAgent**: Creates balanced comprehensive reports integrating all evidence
- **FactCheckerAgent**: Evaluates biomedical statements (yes/no/maybe) with literature evidence
- **PaperCheckerAgent**: Validates medical abstract claims against contradictory literature evidence
- **PaperReviewerAgent**: Comprehensive paper assessment combining all analysis agents in an 11-step workflow
- **PICOAgent**: Extracts Population, Intervention, Comparison, and Outcome components
- **PRISMA2020Agent**: Assesses systematic reviews against the 27-item PRISMA 2020 checklist
- **StudyAssessmentAgent**: Evaluates research quality, study design, and bias risk
- **PaperWeightAgent**: Evidential weight scoring across five quality dimensions
- **DocumentInterrogationAgent**: Interactive Q&A with loaded documents (PDF, Markdown, text)
- **SystematicReviewAgent**: Automated systematic literature review with Cochrane/GRADE assessment

### Advanced Workflow Orchestration
- **Enum-Based Workflow**: Flexible step orchestration with meaningful names
- **Iterative Processing**: Query refinement, threshold adjustment, citation requests
- **Task Queue System**: SQLite-based persistent task queuing for memory-efficient processing
- **Human-in-the-Loop**: Interactive decision points with auto-mode support
- **Branching Logic**: Conditional step execution and error recovery

### Production-Ready Infrastructure
- **Database Migration System**: Automated schema initialization and incremental updates with startup integration
- **PostgreSQL + pgvector**: Semantic search with vector embeddings at 40M+ document scale
- **Semantic Chunking**: Multiple strategies (adaptive, sentence-based, SpaCy NLP) with vector embeddings
- **PostgreSQL Audit Trail**: Comprehensive tracking of research workflow sessions
- **User Authentication**: Login system with per-user database-backed settings
- **LLM Provider Abstraction**: Unified interface with token tracking across providers
- **Local LLM Integration**: Ollama service for privacy-preserving AI inference
- **134 Test Files**: Comprehensive test coverage across all modules
- **16 GUI Plugins**: Modular PySide6/Qt plugin architecture
- **Browser-Based Downloader**: Playwright automation for Cloudflare-protected PDFs (optional)

### Advanced Analytics
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
git clone https://github.com/hherb/bmlibrarian.git
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
- Native cross-platform desktop interface built with PySide6/Qt
- Visual workflow progress with collapsible step cards
- Multi-model query generation with smart pagination and result tracking
- Progressive counterfactual audit trail with real-time updates
- PostgreSQL audit trail for persistent session tracking
- Real-time agent execution with configured AI models
- Formatted markdown report preview with scrollable display
- Direct file save functionality
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
- **Paper Reviewer Lab** (`paper_reviewer_lab.py`): Comprehensive paper assessment with 11-step unified workflow (PySide6/Qt)
- **Paper Checker Lab** (`paper_checker_lab.py`): Interactive medical abstract fact-checking with step-by-step visualization
- **Paper Weight Lab** (`paper_weight_lab.py`): Evidential weight assessment across five quality dimensions (PySide6/Qt)
- **PubMed Search Lab** (`pubmed_search_lab.py`): Search PubMed API directly without local database (PySide6/Qt)
- **QueryAgent Lab** (`query_lab.py`): Experimental interface for natural language to SQL conversion
- **PICO Lab** (`pico_lab.py`): Interactive PICO component extraction from research papers
- **PRISMA 2020 Lab** (`prisma2020_lab.py`): Systematic review compliance assessment against 27-item checklist
- **Study Assessment Lab** (`study_assessment_lab.py`): Research quality and trustworthiness evaluation
- **Citation Lab** (`citation_lab.py`): Citation extraction experimentation
- **Agent Demonstrations**: Examples showcasing multi-agent capabilities in `examples/` directory

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
- **[Paper Reviewer Lab Guide](doc/users/paper_reviewer_lab_guide.md)** - Comprehensive paper assessment
- **[Fact Checker Guide](doc/users/fact_checker_guide.md)** - LLM training data auditing and statement verification
- **[Fact Checker Review Guide](doc/users/fact_checker_review_guide.md)** - Human annotation and review GUI
- **[Paper Checker Guide](doc/users/paper_checker_guide.md)** - Medical abstract fact-checking
- **[Paper Weight Lab Guide](doc/users/paper_weight_lab_guide.md)** - Evidential weight assessment
- **[PICO Agent Guide](doc/users/pico_agent_guide.md)** - PICO component extraction for systematic reviews
- **[PRISMA 2020 Guide](doc/users/prisma2020_guide.md)** - Systematic review compliance assessment
- **[Study Assessment Guide](doc/users/study_assessment_guide.md)** - Research quality evaluation
- **[Document Interrogation Guide](doc/users/document_interrogation_guide.md)** - Interactive document Q&A
- **[Full-Text Discovery Guide](doc/users/full_text_discovery_guide.md)** - PDF discovery and download
- **[PDF Export Guide](doc/users/pdf_export_guide.md)** - Markdown to PDF export
- **[Query Agent Guide](doc/users/query_agent_guide.md)** - Natural language query processing
- **[Multi-Model Query Guide](doc/users/multi_model_query_guide.md)** - Multi-model query generation
- **[Citation Guide](doc/users/citation_guide.md)** - Citation extraction and formatting
- **[Reporting Guide](doc/users/reporting_guide.md)** - Report generation and export
- **[Counterfactual Guide](doc/users/counterfactual_guide.md)** - Contradictory evidence analysis
- **[Systematic Review Guide](doc/users/systematic_review_guide.md)** - Systematic literature review workflow
- **[Audit Validation Guide](doc/users/audit_validation_guide.md)** - Human validation of audit trail items
- **[Writing Plugin Guide](doc/users/writing_plugin_guide.md)** - Citation-aware markdown editor
- **[Settings Migration Guide](doc/users/settings_migration_guide.md)** - Database-backed settings migration
- **[OpenAthens Guide](doc/users/openathens_guide.md)** - Institutional proxy authentication
- **[MedRxiv Import Guide](doc/users/medrxiv_import_guide.md)** - MedRxiv preprint import
- **[Document Embedding Guide](doc/users/document_embedding_guide.md)** - Document embedding generation
- **[Workflow Guide](doc/users/workflow_guide.md)** - Workflow orchestration system
- **[Troubleshooting](doc/users/troubleshooting.md)** - Common issues and solutions

### Developer Documentation
- **[Agent Module](doc/developers/agent_module.md)** - Multi-agent system architecture
- **[Citation System](doc/developers/citation_system.md)** - Citation processing internals
- **[Reporting System](doc/developers/reporting_system.md)** - Report generation system
- **[Counterfactual System](doc/developers/counterfactual_system.md)** - Evidence analysis framework
- **[Fact Checker System](doc/developers/fact_checker_system.md)** - Fact-checking architecture and internals
- **[Paper Checker Architecture](doc/developers/paper_checker_architecture.md)** - PaperChecker system design
- **[PICO Agent](doc/developers/pico_agent.md)** - PICO extraction system internals
- **[PRISMA 2020 System](doc/developers/prisma2020_system.md)** - PRISMA compliance assessment system
- **[Study Assessment System](doc/developers/study_assessment_system.md)** - Research quality evaluation system
- **[Full-Text Discovery System](doc/developers/full_text_discovery_system.md)** - PDF discovery architecture
- **[Document Card Factory](doc/developers/document_card_factory_system.md)** - GUI document card system
- **[Multi-Model Architecture](doc/developers/multi_model_architecture.md)** - Multi-model query generation
- **[Audit Validation System](doc/developers/audit_validation_system.md)** - Human validation architecture
- **[Writing System](doc/developers/writing_system.md)** - Citation-aware editor internals

## Development

### Development Environment Setup

1. **Clone the repository:**
```bash
git clone https://github.com/hherb/bmlibrarian.git
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

Test suite: **145 test files** across all modules

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

- **15+ Specialized AI Agents**: Full multi-agent architecture with sophisticated coordination
- **Systematic Review Automation**: Checkpoint-based reviews with Cochrane/GRADE assessment
- **Comprehensive Workflow System**: 12-step research process with iterative capabilities
- **Robust Infrastructure**: Queue orchestration, error handling, semantic chunking, and progress tracking
- **26 CLI/GUI Applications**: Research, configuration, fact-checking, systematic review, import tools
- **16 GUI Plugins**: Modular PySide6/Qt plugin architecture
- **134 Test Files**: Comprehensive test coverage across all modules
- **272 Documentation Files**: User guides and developer documentation for every component
- **Privacy-First**: All AI processing runs locally via Ollama

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
- **PySide6/Qt**: Cross-platform native desktop GUI framework
- **ReportLab**: Professional PDF generation (BSD license)
- **Playwright**: Browser automation for PDF discovery and OpenAthens authentication
- **Python Ecosystem**: Modern Python >=3.12 with comprehensive typing support

---

*BMLibrarian: The Biomedical Researcher's AI Workbench—evidence-based answers, peer-review quality assessment, and systematic fact-checking, all running locally on your hardware.*