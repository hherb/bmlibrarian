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
  - psycopg >=3.2.9 for PostgreSQL connectivity
  - requests >=2.31.0 for HTTP communication with Ollama
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

## Development Commands

Since this project uses `uv` for package management:
- `uv sync` - Install/sync dependencies
- `uv run python -m [module]` - Run Python modules in the virtual environment
- **Testing**: `uv run python -m pytest tests/` - Run comprehensive test suite
- **CLI Applications**: 
  - `uv run python bmlibrarian_cli.py` - Interactive medical research CLI with full multi-agent workflow
- **Configuration GUI**: 
  - `uv run python bmlibrarian_config_gui.py` - Graphical configuration interface for agents and settings
- **Laboratory Tools**:
  - `uv run python query_lab.py` - Interactive QueryAgent laboratory for experimenting with natural language to PostgreSQL query conversion
- **Demonstrations**: 
  - `uv run python examples/agent_demo.py` - Multi-agent workflow demonstration
  - `uv run python examples/citation_demo.py` - Citation extraction examples
  - `uv run python examples/reporting_demo.py` - Report generation examples
  - `uv run python examples/counterfactual_demo.py` - Counterfactual analysis demonstration

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
│   │   └── orchestrator.py    # Multi-agent workflow coordination
│   └── cli/                   # Modular CLI architecture
│       ├── __init__.py        # CLI module exports
│       ├── config.py          # Configuration management
│       ├── ui.py              # User interface components
│       ├── query_processing.py # Query editing and search
│       ├── formatting.py      # Report formatting and export
│       ├── workflow.py        # Workflow orchestration
│       └── workflow_steps.py  # Enum-based workflow step definitions
│   └── gui/                   # Graphical user interface for configuration
│       ├── __init__.py        # GUI module exports
│       ├── config_app.py      # Main GUI application using Flet
│       └── tabs/              # Individual configuration tab components
│           ├── __init__.py
│           ├── general_tab.py # General settings tab
│           └── agent_tab.py   # Agent-specific configuration tabs
│   └── lab/                   # Experimental tools and interfaces
│       ├── __init__.py        # Lab module exports
│       └── query_lab.py       # QueryAgent experimental GUI
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
│   │   └── counterfactual_guide.md
│   └── developers/            # Technical documentation
│       ├── agent_module.md
│       ├── citation_system.md
│       ├── reporting_system.md
│       └── counterfactual_system.md
├── bmlibrarian_cli.py         # Interactive CLI application with full multi-agent workflow
├── bmlibrarian_config_gui.py  # Graphical configuration interface
├── query_lab.py               # QueryAgent experimental laboratory GUI
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

### Agent Development Guidelines
- **BaseAgent Pattern**: All agents inherit from BaseAgent with standardized interfaces
- **Queue Integration**: New agents should support queue-based processing
- **Workflow Integration**: Agents should work with enum-based workflow system
- **Connection Testing**: All agents must implement connection testing methods
- **Progress Tracking**: Support progress callbacks for long-running operations
- **Document ID Integrity**: Always use real database IDs, never mock/fabricated references
- **Step Handler Methods**: Implement appropriate workflow step handlers for agent actions

### Workflow Development Guidelines
- **WorkflowStep Enum**: Use meaningful names for new workflow steps
- **Repeatable Steps**: Mark steps as repeatable when they support iteration
- **Branching Logic**: Implement conditional execution and error recovery
- **Context Management**: Preserve state across step executions
- **Auto Mode Support**: Ensure steps work in non-interactive mode

## Usage Examples

### Interactive CLI Application

The main way to use BMLibrarian is through the interactive CLI:

```bash
# Start the interactive medical research CLI
uv run python bmlibrarian_cli.py

# Enhanced workflow with comprehensive steps:
# 1. Research question entry
# 2. Query generation and editing
# 3. Database search and review
# 4. Document relevance scoring
# 5. Citation extraction
# 6. Report generation
# 7. Counterfactual analysis (optional)
# 8. Enhanced markdown export

# Command line options:
uv run python bmlibrarian_cli.py --quick  # Quick testing mode
uv run python bmlibrarian_cli.py --max-results 50 --timeout 10
uv run python bmlibrarian_cli.py --auto "research question"  # Automated mode
```

The CLI provides enhanced human-in-the-loop interaction:
- **Enum-Based Workflow**: Flexible step orchestration with meaningful names
- **Iterative Capabilities**: Repeatable steps for query refinement and threshold adjustment
- **Modular Architecture**: Cleaner separation of concerns for maintainability
- **Enhanced Workflow**: Optional counterfactual analysis for finding contradictory evidence
- **Agent-Driven Refinement**: Agents can request more citations or evidence during processing
- **Improved UI**: Better user experience with clearer navigation
- **Comprehensive Export**: Reports include counterfactual analysis when performed
- **Auto Mode Support**: Graceful handling of non-interactive execution

### Configuration GUI Application

BMLibrarian includes a modern graphical configuration interface built with Flet:

```bash
# Start the desktop configuration GUI (default)
uv run python bmlibrarian_config_gui.py

# GUI Features:
# - Native desktop application with tabbed interface
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
- **Agent Configuration**: Individual tabs for Query, Scoring, Citation, Reporting, Counterfactual, and Editor agents
- **Model Management**: Dropdown selection with live model refresh from Ollama
- **Parameter Tuning**: Interactive sliders for temperature, top-p, and agent-specific settings
- **General Settings**: Ollama server configuration, database settings, and CLI defaults
- **File Operations**: Save/load configuration files with JSON format
- **Connection Testing**: Verify Ollama server connectivity and list available models
- **Dual Mode**: Can run as desktop app or web interface

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
2. **Implement comprehensive testing** with realistic test data
3. **Create both user and developer documentation** for all new features
4. **Use only approved LLM models** specified in configuration
5. **Never create or modify production database** without explicit permission
6. **Ensure document ID verification** to prevent citation hallucination
7. **Support queue-based processing** for scalability
8. **Include progress tracking** for long-running operations
9. **Use enum-based workflow system** for new workflow steps (workflow_steps.py)
10. **Use modular CLI architecture** for new CLI features (bmlibrarian_cli_refactored.py)
11. **Include counterfactual analysis** capabilities where appropriate for evidence validation
12. **Implement workflow step handlers** for agent integration with orchestration system
13. **Support auto mode execution** with graceful fallbacks for interactive features

### Testing and Quality Assurance:
- Run full test suite: `uv run python -m pytest tests/`
- Test preferred CLI: `uv run python bmlibrarian_cli_refactored.py --quick`
- Test agent demos: `uv run python examples/agent_demo.py`
- Test counterfactual analysis: `uv run python examples/counterfactual_demo.py`
- Verify Ollama connection before LLM operations
- Validate all citations reference real database documents
- Check evidence strength assessments are appropriate
- Verify counterfactual analysis generates meaningful research questions