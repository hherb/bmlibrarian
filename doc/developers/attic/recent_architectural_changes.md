# Recent Architectural Changes - Developer Guide

## Overview

This document outlines the substantial design and code changes made to BMLibrarian, focusing on the evolution from a monolithic system to a sophisticated, modular multi-agent architecture with comprehensive GUI support.

## Major Architectural Transformations

### 1. Multi-Agent System Implementation

**Previous State**: Single-threaded, procedural processing
**New State**: Sophisticated multi-agent architecture with specialized AI agents

#### Agent Specialization
- **QueryAgent** (`agents/query_agent.py`): Natural language to PostgreSQL query conversion
- **DocumentScoringAgent** (`agents/scoring_agent.py`): Document relevance scoring (1-5 scale)
- **CitationFinderAgent** (`agents/citation_agent.py`): Passage extraction from high-scoring documents
- **ReportingAgent** (`agents/reporting_agent.py`): Medical publication-style report synthesis
- **CounterfactualAgent** (`agents/counterfactual_agent.py`): Contradictory evidence analysis
- **EditorAgent** (`agents/editor_agent.py`): Comprehensive report editing and integration

#### Agent Orchestration
- **AgentOrchestrator** (`agents/orchestrator.py`): Coordinates multi-agent workflows
- **QueueManager** (`agents/queue_manager.py`): SQLite-based persistent task queuing
- **BaseAgent** (`agents/base.py`): Standardized agent interface and patterns

### 2. Enum-Based Workflow System

**Previous State**: Brittle numbered step system
**New State**: Flexible enum-based workflow orchestration

#### Core Workflow Components
```python
# workflow_steps.py - New enum-based step definitions
class WorkflowStep(Enum):
    COLLECT_RESEARCH_QUESTION = auto()
    GENERATE_AND_EDIT_QUERY = auto()
    SEARCH_DOCUMENTS = auto()
    REVIEW_SEARCH_RESULTS = auto()
    SCORE_DOCUMENTS = auto()
    EXTRACT_CITATIONS = auto()
    GENERATE_REPORT = auto()
    PERFORM_COUNTERFACTUAL_ANALYSIS = auto()
    SEARCH_CONTRADICTORY_EVIDENCE = auto()
    EDIT_COMPREHENSIVE_REPORT = auto()
    EXPORT_REPORT = auto()
    
    # Repeatable/conditional steps
    REFINE_QUERY = auto()
    ADJUST_SCORING_THRESHOLDS = auto()
    REQUEST_MORE_CITATIONS = auto()
    REVIEW_AND_REVISE_REPORT = auto()
```

#### Workflow Features
- **Meaningful Step Names**: Replace brittle numbering with descriptive enums
- **Repeatable Steps**: Support iterative workflows and agent-driven refinement
- **Conditional Branching**: Dynamic step execution based on context
- **Context Management**: Preserve state across step executions
- **Auto Mode Support**: Graceful non-interactive execution

### 3. Modular CLI Architecture

**Previous State**: Monolithic CLI file
**New State**: Modular, testable CLI architecture

#### CLI Module Structure
```
src/bmlibrarian/cli/
├── __init__.py              # Public API exports
├── config.py                # Configuration management and CLI parsing
├── ui.py                    # User interface components
├── query_processing.py      # Query editing and database search
├── formatting.py            # Report formatting and export
├── workflow.py              # Multi-agent workflow orchestration
└── workflow_steps.py        # Enum-based workflow step definitions
```

#### Module Responsibilities
- **CLIConfig**: Centralized configuration with agent parameter management
- **UserInterface**: Consistent UI patterns with progress reporting
- **QueryProcessor**: Database search with interactive query editing
- **ReportFormatter**: Enhanced markdown generation with counterfactual analysis
- **WorkflowOrchestrator**: Enum-based step execution with error recovery

### 4. Comprehensive GUI System

**Previous State**: No graphical interface
**New State**: Full-featured desktop applications with Flet framework

#### GUI Applications
1. **Configuration GUI** (`gui/config_app.py`):
   - Tabbed interface for agent configuration
   - Live model refresh from Ollama server
   - Parameter tuning with interactive controls
   - Connection testing and validation

2. **Research GUI** (`gui/research_app.py`):
   - Visual workflow progress with real-time updates
   - Interactive research question input
   - Report preview with markdown rendering
   - File save functionality with cross-platform support

#### GUI Architecture Components
```
src/bmlibrarian/gui/
├── __init__.py            # GUI module exports
├── config_app.py          # Configuration GUI application
├── research_app.py        # Main research GUI application
├── components.py          # Reusable UI components (StepCard, etc.)
├── dialogs.py             # Dialog management and interactions
├── workflow.py            # Real agent orchestration and execution
└── tabs/                  # Configuration GUI tab components
    ├── __init__.py
    ├── general_tab.py     # General settings tab
    └── agent_tab.py       # Agent-specific configuration tabs
```

#### Key GUI Features
- **Component-Based Design**: Reusable UI elements with consistent styling
- **Real-time Updates**: Live progress tracking during workflow execution
- **Cross-Platform Support**: Desktop and web deployment modes
- **Configuration Integration**: Seamless integration with BMLibrarian's config system
- **Thread Safety**: Proper handling of background operations

### 5. Advanced Configuration System

**Previous State**: Basic configuration files
**New State**: Sophisticated agent configuration with GUI management

#### Configuration Features
- **Agent-Specific Settings**: Individual configuration for each agent type
- **Model Management**: Dynamic model selection from Ollama server
- **Parameter Validation**: Real-time validation with user feedback
- **OS-Agnostic Paths**: `~/.bmlibrarian/config.json` as primary location
- **GUI Integration**: Visual configuration management

#### Configuration Structure
```json
{
  "general": {
    "ollama_base_url": "http://localhost:11434",
    "database_params": {...},
    "cli_defaults": {...}
  },
  "agents": {
    "query_agent": {
      "model": "gpt-oss:20b",
      "temperature": 0.1,
      "top_p": 0.9
    },
    "scoring_agent": {...},
    "citation_agent": {...},
    "reporting_agent": {...},
    "counterfactual_agent": {...},
    "editor_agent": {...}
  }
}
```

### 6. Enhanced Error Handling and Recovery

**Previous State**: Basic error handling
**New State**: Comprehensive error recovery with user feedback

#### Error Handling Features
- **Step-Level Recovery**: Handle errors within individual workflow steps
- **Graceful Degradation**: Continue workflow when possible despite errors
- **User Choice**: Present recovery options to users
- **Detailed Logging**: Comprehensive error tracking and debugging
- **GUI Error Dialogs**: Consistent error reporting in graphical interfaces

## Migration Impact

### Breaking Changes
1. **CLI Interface**: New modular structure requires import path updates
2. **Configuration Format**: Enhanced config structure with agent-specific settings
3. **Step Definitions**: Workflow steps now use enums instead of numbers
4. **Agent Initialization**: Agents now require orchestrator and configuration parameters

### Backward Compatibility
- **Configuration Migration**: Automatic migration from old config formats
- **Database Schema**: No changes to PostgreSQL database structure
- **Report Formats**: Enhanced but backward-compatible markdown output

### New Dependencies
- **Flet**: GUI framework for cross-platform desktop applications
- **Enhanced Queue System**: SQLite-based persistent task queuing
- **Agent Configuration**: Structured configuration management

## Development Impact

### Code Organization Benefits
1. **Improved Testability**: Modular architecture enables comprehensive unit testing
2. **Enhanced Maintainability**: Clear separation of concerns across modules
3. **Better Extensibility**: Easy addition of new agents, workflow steps, and GUI components
4. **Consistent Patterns**: Standardized interfaces and error handling across components

### Developer Experience Improvements
1. **Type Safety**: Enhanced type hints throughout the codebase
2. **Documentation**: Comprehensive developer and user documentation
3. **Testing Infrastructure**: Unit tests for all major components
4. **Debugging Tools**: Enhanced logging and error reporting

### Performance Enhancements
1. **Queue-Based Processing**: Efficient handling of large document sets
2. **Async GUI Operations**: Non-blocking user interface operations
3. **Resource Management**: Proper cleanup of agent and UI resources
4. **Connection Pooling**: Efficient database and API connection management

## Usage Examples

### CLI Usage (Enhanced)
```bash
# Interactive CLI with full workflow
uv run python bmlibrarian_cli.py

# Auto mode with specific question
uv run python bmlibrarian_cli.py --auto "research question"

# Quick testing mode
uv run python bmlibrarian_cli.py --quick --max-results 50
```

### GUI Applications
```bash
# Configuration GUI
uv run python bmlibrarian_config_gui.py

# Research GUI with visual workflow
uv run python bmlibrarian_research_gui.py

# Web-based interface
uv run python bmlibrarian_config_gui.py --view web --port 8080
```

### Programmatic API
```python
from bmlibrarian.cli.workflow_steps import WorkflowStep, create_default_research_workflow
from bmlibrarian.cli import WorkflowOrchestrator, CLIConfig, UserInterface

# Create workflow with enum-based steps
workflow_definition = create_default_research_workflow()
config = CLIConfig()
ui = UserInterface(config)
orchestrator = WorkflowOrchestrator(config, ui, query_processor, formatter)

# Execute complete workflow
success = orchestrator.run_complete_workflow("research question")
```

## Future Architectural Directions

### Planned Enhancements
1. **Plugin Architecture**: Support for custom agents and workflow steps
2. **Distributed Processing**: Multi-node agent orchestration
3. **Advanced Visualizations**: Enhanced charts and graphs for research data
4. **Collaborative Features**: Multi-user workflow coordination
5. **API Gateway**: REST API for external system integration

### Technical Debt Reduction
1. **Test Coverage**: Achieve >98% test coverage across all modules
2. **Performance Optimization**: Continued optimization of agent processing
3. **Memory Management**: Enhanced resource cleanup and memory monitoring
4. **Security Hardening**: Additional security measures for multi-agent communication

## Migration Guide for Developers

### Updating Existing Code
1. **Import Path Changes**: Update imports to use new modular structure
2. **Configuration Updates**: Migrate to new agent-specific configuration format
3. **Workflow Integration**: Replace numbered steps with enum-based workflow
4. **Agent Initialization**: Update agent creation to use new orchestrator pattern

### Testing Updates
1. **Module Testing**: Write tests for new modular components
2. **GUI Testing**: Implement GUI component testing
3. **Integration Testing**: Test complete workflows with new architecture
4. **Performance Testing**: Validate performance improvements

### Documentation Requirements
1. **API Documentation**: Update all API references for new architecture
2. **User Guides**: Update user documentation for new interfaces
3. **Developer Guides**: Comprehensive documentation for new components
4. **Migration Guides**: Detailed migration instructions for existing deployments

---

This architectural transformation represents a significant evolution of BMLibrarian from a simple CLI tool to a comprehensive, modular, multi-agent research platform with sophisticated GUI capabilities and flexible workflow orchestration.