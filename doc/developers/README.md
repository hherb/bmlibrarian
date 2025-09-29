# Developer Documentation

Welcome to BMLibrarian developer documentation! This section provides technical information for developers working with or contributing to BMLibrarian.

## Architecture and Design

🏗️ **[Architecture Overview](architecture.md)**
- System architecture and design principles
- Core components and their responsibilities
- Database schema and migration lifecycle
- Security model and error handling
- Performance considerations

🧠 **[Multi-Agent Architecture](agents_architecture.md)**
- AI agent system design and coordination
- Queue-based orchestration architecture
- Agent communication patterns
- Performance and scalability considerations

🔄 **[Workflow System](workflow_system.md)**
- Enum-based workflow orchestration
- Step definitions and execution models
- Repeatable and conditional workflows
- Context management and state preservation

🖥️ **[GUI Architecture](gui_architecture.md)**
- Modular GUI design with Flet framework
- Component-based architecture
- Dialog management and user interactions
- Real-time workflow visualization

## API Reference

📚 **[API Reference](api_reference.md)**
- Complete API documentation
- Class and method references
- Usage examples and patterns
- Error handling and exceptions
- Environment configuration

## Contributing

🤝 **[Contributing Guide](contributing.md)**
- Development environment setup
- Coding standards and guidelines
- Testing requirements and procedures
- Pull request process
- Release workflow

## Development Quick Start

### Setup Development Environment

```bash
# Clone repository
git clone <repository-url>
cd bmlibrarian

# Install dependencies
uv sync

# Run tests
uv run pytest tests/
```

### Project Structure

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
│   │   ├── counterfactual_agent.py # Counterfactual analysis
│   │   ├── editor_agent.py    # Comprehensive report editing
│   │   ├── queue_manager.py   # SQLite-based task queue system
│   │   └── orchestrator.py    # Multi-agent workflow coordination
│   ├── cli/                   # Modular CLI architecture
│   │   ├── __init__.py        # CLI module exports
│   │   ├── config.py          # Configuration management
│   │   ├── ui.py              # User interface components
│   │   ├── query_processing.py # Query editing and search
│   │   ├── formatting.py      # Report formatting and export
│   │   ├── workflow.py        # Workflow orchestration
│   │   └── workflow_steps.py  # Enum-based workflow step definitions
│   ├── gui/                   # Graphical user interfaces
│   │   ├── __init__.py        # GUI module exports
│   │   ├── config_app.py      # Configuration GUI application
│   │   ├── research_app.py    # Main research GUI application
│   │   ├── components.py      # Reusable UI components
│   │   ├── dialogs.py         # Dialog management and interactions
│   │   ├── workflow.py        # Real agent orchestration and execution
│   │   └── tabs/              # Configuration GUI tab components
│   └── lab/                   # Experimental tools and interfaces
├── tests/                     # Comprehensive test suite
├── doc/                       # Documentation
└── examples/                  # Demonstration scripts
```

### Testing

```bash
# Run all tests with coverage
uv run pytest tests/ --cov=src/bmlibrarian

# Run specific test categories
uv run pytest tests/test_query_agent.py    # Query processing tests
uv run pytest tests/test_scoring_agent.py  # Document scoring tests
uv run pytest tests/test_citation_agent.py # Citation extraction tests
uv run pytest tests/test_reporting_agent.py# Report generation tests
uv run pytest tests/test_counterfactual_agent.py # Counterfactual analysis tests

# Run GUI applications for testing
uv run python bmlibrarian_cli.py --quick                     # Interactive CLI testing
uv run python bmlibrarian_research_gui.py --quick            # Research GUI testing
uv run python bmlibrarian_config_gui.py                      # Configuration GUI testing
```

Current test coverage: **>95%** across all agent modules

## Key Development Areas

### Multi-Agent System Core
- **Directory**: `src/bmlibrarian/agents/`
- **Purpose**: AI-powered literature analysis and processing
- **Key Classes**: `BaseAgent`, `QueryAgent`, `DocumentScoringAgent`, `CitationFinderAgent`, `ReportingAgent`, `CounterfactualAgent`, `EditorAgent`
- **Orchestration**: `AgentOrchestrator` with SQLite-based queue system

### Modular CLI Architecture
- **Directory**: `src/bmlibrarian/cli/`
- **Purpose**: Interactive command-line interface with workflow orchestration
- **Key Classes**: `CLIConfig`, `UserInterface`, `QueryProcessor`, `ReportFormatter`, `WorkflowOrchestrator`
- **Workflow System**: Enum-based step definitions with repeatable and conditional execution

### GUI Applications
- **Directory**: `src/bmlibrarian/gui/`
- **Purpose**: Desktop applications for configuration and research
- **Key Applications**: 
  - `ConfigApp` - Tabbed configuration interface for agents and settings
  - `ResearchGUI` - Visual research workflow with real-time progress
- **Components**: Modular design with reusable UI components and dialog management

### Workflow Orchestration System
- **File**: `src/bmlibrarian/cli/workflow_steps.py`
- **Purpose**: Flexible, enum-based workflow execution
- **Key Features**: Meaningful step names, repeatable steps, conditional branching, context management

## Development Guidelines

### Code Quality
- **Follow Modern Python Standards**: Use PEP 8 style guidelines, type hints, and Python >=3.12 features
- **BaseAgent Pattern**: All agents inherit from `BaseAgent` with standardized interfaces
- **Configuration Integration**: Use `get_model()` and `get_agent_config()` from config system
- **Comprehensive Testing**: Unit tests for all agents with >95% coverage
- **Documentation First**: Create both user guides and developer documentation

### Agent Development Standards
- **Parameter Filtering**: Filter agent config to only include supported parameters (temperature, top_p, etc.)
- **Queue Integration**: New agents should support queue-based processing via `AgentOrchestrator`
- **Workflow Integration**: Implement workflow step handlers for enum-based orchestration
- **Connection Testing**: All agents must implement connection testing methods for LLM services
- **Progress Tracking**: Support progress callbacks for long-running operations
- **Document ID Integrity**: Always use real database IDs, never mock/fabricated references
- **No Artificial Limits**: Process ALL documents unless explicitly configured otherwise

### GUI Development Standards
- **Modular Design**: Use component-based architecture with reusable UI elements
- **Flet Framework**: Follow Flet best practices for cross-platform desktop applications
- **Real-time Updates**: Support live progress updates during workflow execution
- **Dialog Management**: Centralized dialog handling for consistent user experience
- **Configuration Integration**: Respect agent models and parameters from `~/.bmlibrarian/config.json`

### Workflow Development Guidelines
- **WorkflowStep Enum**: Use meaningful names for new workflow steps
- **Repeatable Steps**: Mark steps as repeatable when they support iteration
- **Branching Logic**: Implement conditional execution and error recovery
- **Context Management**: Preserve state across step executions
- **Auto Mode Support**: Ensure steps work in non-interactive mode

## Advanced Topics

### Extension Points
- Custom migration directories
- Environment-specific configurations
- Database connection customization
- CLI command extensions

### Performance Optimization
- Connection management patterns
- Migration performance considerations
- Memory usage optimization
- Concurrent operation handling

### Security Considerations
- Credential management best practices
- SQL injection prevention
- Database permission models
- Network security patterns

## Debugging and Maintenance

### Debugging Tools
```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Inspect migration state
manager._get_applied_migrations()
manager._database_exists("database_name")
```

### Common Development Tasks
- Adding new CLI commands
- Extending MigrationManager functionality
- Writing integration tests
- Updating documentation

## Getting Help

- **Architecture Questions**: Review the [Architecture Guide](architecture.md)
- **API Usage**: Check the [API Reference](api_reference.md)
- **Contribution Process**: See the [Contributing Guide](contributing.md)
- **Testing Issues**: Refer to test documentation in contributing guide

---

Start with the [Architecture Overview](architecture.md) to understand the system design, then check the [API Reference](api_reference.md) for detailed technical information.