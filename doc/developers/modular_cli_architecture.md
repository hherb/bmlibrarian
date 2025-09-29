# Modular CLI Architecture - Developer Documentation

## Overview

The BMLibrarian CLI (`bmlibrarian_cli.py`) implements a modular architecture that separates concerns across specialized modules. This design improves maintainability, testability, and extensibility while integrating seamlessly with the enum-based workflow system and multi-agent architecture.

## Architecture Principles

### 1. Separation of Concerns
Each module handles a specific aspect of the CLI functionality:
- **Configuration**: Command-line parsing, settings management, agent configuration
- **User Interface**: Display functions, user interaction, input validation
- **Query Processing**: Database search coordination, query editing
- **Formatting**: Report generation, markdown export, file operations
- **Workflow**: Enum-based workflow orchestration, multi-agent coordination
- **Workflow Steps**: Step definitions, execution context, and conditional logic

### 2. Dependency Injection
Components receive their dependencies through constructor injection, enabling:
- Easy testing with mocked dependencies
- Runtime configuration changes
- Clean module boundaries

### 3. Consistent Interfaces
All modules follow consistent patterns:
- Constructor accepts `config` and other required dependencies
- Methods return structured data types
- Error handling follows common patterns
- Progress reporting uses consistent callbacks

## Module Structure

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

## Core Modules

### CLIConfig (`config.py`)

**Purpose**: Centralized configuration management and command-line argument parsing.

```python
@dataclass
class CLIConfig:
    max_search_results: int = 100
    timeout_minutes: float = 5.0
    default_score_threshold: float = 2.5
    default_min_relevance: float = 0.7
    max_documents_display: int = 20
    max_workers: int = 2
    polling_interval: float = 0.1
    show_progress: bool = True
    verbose: bool = False
```

**Key Functions**:
- `parse_command_line_args()`: Handle command-line arguments
- `create_config_from_args(args)`: Convert arguments to config object
- `show_config_summary(config)`: Display current settings

**Benefits**:
- Single source of truth for configuration
- Type-safe configuration with dataclasses
- Easy testing with config overrides
- Consistent behavior across modules

### UserInterface (`ui.py`)

**Purpose**: All user interaction, display functions, and input validation.

**Key Methods**:
- `show_main_menu()`: Display main navigation menu
- `get_research_question()`: Collect research question with validation
- `display_document_scores()`: Show relevance scores with options
- `display_citations()`: Present extracted citations for review
- `display_report()`: Show generated report with formatting
- `get_counterfactual_analysis_choice()`: Ask about counterfactual analysis
- `display_counterfactual_analysis()`: Show counterfactual results
- `display_contradictory_evidence_results()`: Present contradictory evidence

**Design Patterns**:
- All user prompts include validation and retry logic
- Consistent formatting for different data types
- Progress indication for long-running operations
- Graceful error handling with user-friendly messages

### QueryProcessor (`query_processing.py`)

**Purpose**: Handle query editing, database search coordination, and document processing.

**Key Classes**:
- `QueryProcessor`: Main query editing and search interface
- `DocumentProcessor`: Document review and filtering operations

**Key Methods**:
- `search_documents_with_review()`: Complete search workflow with user review
- `set_query_agent()`: Dependency injection for agent
- `test_database_connection()`: Connection verification
- `process_search_results()`: Document filtering and review

**Features**:
- Interactive query editing with AI assistance
- Real-time document count feedback
- User control over search refinement
- Integrated error handling and recovery

### ReportFormatter (`formatting.py`)

**Purpose**: Report formatting, markdown generation, and file export operations.

**Key Methods**:
- `format_report_as_markdown(report, counterfactual_analysis)`: Generate markdown content
- `save_report_to_file(report, question, counterfactual_analysis)`: Export to file
- `_get_counterfactual_analysis_section()`: Format counterfactual results for markdown

**Enhanced Features**:
- **Counterfactual Integration**: Includes counterfactual analysis in reports
- **Priority-Grouped Questions**: Organizes research questions by importance
- **Professional Formatting**: Medical publication-style output
- **Comprehensive Metadata**: Technical details and quality controls

**Markdown Structure**:
```markdown
# Medical Literature Research Report

## Research Question
## Evidence Assessment  
## Findings
## References
## Counterfactual Analysis  # NEW
### Main Claims Analyzed
### Research Questions for Contradictory Evidence
#### High Priority Questions
#### Medium Priority Questions  
#### Low Priority Questions
### Overall Assessment
## Methodology
## Technical Details
```

### WorkflowSteps (`workflow_steps.py`)

**Purpose**: Defines the enum-based workflow system with flexible step orchestration.

**Key Components**:
- **WorkflowStep Enum**: Meaningful step names instead of brittle numbering
- **WorkflowDefinition**: Step dependencies, branching conditions, and repetition logic  
- **WorkflowExecutor**: Context management and step execution tracking
- **StepResult Enum**: SUCCESS, FAILURE, REPEAT, BRANCH, SKIP, USER_CANCELLED

**Features**:
- **Repeatable Steps**: Support for iterative workflows and agent-driven refinement
- **Conditional Branching**: Dynamic step selection based on execution context
- **Context Preservation**: Maintain workflow state across step executions
- **Auto Mode Support**: Graceful handling of non-interactive execution

### WorkflowOrchestrator (`workflow.py`)

**Purpose**: Coordinate the complete multi-agent research workflow using enum-based step definitions.

**Key Components**:
- **Enum-Based Execution**: Uses `WorkflowStep` definitions from `workflow_steps.py`
- **Agent Management**: Initialize and coordinate all agents with configuration integration
- **Context Management**: Preserve workflow state for session resumption and step repetition
- **Step Handlers**: Individual handlers for each workflow step with error recovery
- **Progress Reporting**: Real-time progress updates with step-specific messaging

**Enum-Based Workflow Integration**:
The `WorkflowOrchestrator` uses the enum-based workflow system from `workflow_steps.py`:

```python
# Default workflow steps (from workflow_steps.py)
COLLECT_RESEARCH_QUESTION → GENERATE_AND_EDIT_QUERY → SEARCH_DOCUMENTS → 
REVIEW_SEARCH_RESULTS → SCORE_DOCUMENTS → EXTRACT_CITATIONS → 
GENERATE_REPORT → PERFORM_COUNTERFACTUAL_ANALYSIS → 
SEARCH_CONTRADICTORY_EVIDENCE → EDIT_COMPREHENSIVE_REPORT → 
REVIEW_AND_REVISE_REPORT → EXPORT_REPORT

# Repeatable/conditional steps for iterative workflows:
- REFINE_QUERY: When search results are insufficient
- ADJUST_SCORING_THRESHOLDS: For better citation extraction
- REQUEST_MORE_CITATIONS: When agents need more evidence
- REVIEW_AND_REVISE_REPORT: For iterative editing
```

**Counterfactual Integration**:
```python
def _execute_counterfactual_analysis(self, report: Report) -> Optional[CounterfactualAnalysis]:
    # Ask user if they want counterfactual analysis
    if not self.ui.get_counterfactual_analysis_choice():
        return None
    
    # Perform analysis
    formatted_report = self.reporting_agent.format_report_output(report)
    analysis = self.counterfactual_agent.analyze_document(
        document_content=formatted_report,
        document_title=f"Research Report: {self.current_question[:50]}..."
    )
    
    # Display results and optionally search for contradictory evidence
    self.ui.display_counterfactual_analysis(analysis)
    if self.ui.get_contradictory_evidence_search_choice():
        self._search_contradictory_evidence(analysis, formatted_report)
    
    return analysis
```

## Integration with Agents

The modular CLI integrates with all BMLibrarian agents:

### Agent Initialization
```python
# In WorkflowOrchestrator.setup_agents()
self.orchestrator = AgentOrchestrator(max_workers=self.config.max_workers)
self.query_agent = QueryAgent(orchestrator=self.orchestrator)
self.scoring_agent = DocumentScoringAgent(orchestrator=self.orchestrator)
self.citation_agent = CitationFinderAgent(orchestrator=self.orchestrator)
self.reporting_agent = ReportingAgent(orchestrator=self.orchestrator)
self.counterfactual_agent = CounterfactualAgent(orchestrator=self.orchestrator)  # NEW
```

### Agent Coordination
The workflow orchestrator coordinates agents through a standardized pattern:
1. **Connection Testing**: Verify all agents can connect to required services
2. **Sequential Processing**: Each agent processes the output of the previous agent
3. **User Interaction**: Users can review and adjust results at each step
4. **State Management**: Track progress for potential session resumption
5. **Error Recovery**: Handle agent failures with graceful degradation

## Benefits of Modular Architecture

### Maintainability
- **Single Responsibility**: Each module has a clear, focused purpose
- **Loose Coupling**: Modules interact through well-defined interfaces
- **Easy Testing**: Components can be tested in isolation
- **Code Reuse**: Common patterns are shared across modules

### Extensibility
- **New Features**: Easy to add new capabilities without affecting existing code
- **Agent Integration**: Simple to add new agents to the workflow
- **UI Enhancements**: Interface improvements don't require workflow changes
- **Export Formats**: Additional output formats can be added to formatter

### Testability
- **Mocked Dependencies**: Each module can be tested with mocked dependencies
- **Isolated Testing**: Unit tests focus on individual module functionality
- **Integration Testing**: End-to-end testing verifies module interactions
- **Configuration Testing**: Different scenarios can be tested with config variations

## Development Guidelines

### Adding New Features

1. **Identify the Appropriate Module**: Determine which module should handle the new functionality
2. **Update Interfaces**: Add new methods with proper type hints and documentation
3. **Implement Functionality**: Follow existing patterns and error handling practices
4. **Add Tests**: Write comprehensive unit tests for new functionality
5. **Update Documentation**: Update both user and developer documentation

### Adding New Agents

1. **Agent Implementation**: Create agent following BaseAgent pattern
2. **Workflow Integration**: Add agent initialization in `WorkflowOrchestrator`
3. **UI Integration**: Add user interface methods in `UserInterface`
4. **Formatting Integration**: Add formatting support in `ReportFormatter`
5. **Testing**: Add comprehensive tests for agent integration

### Module Communication

Modules communicate through:
- **Constructor Injection**: Dependencies passed during initialization
- **Method Parameters**: Data passed as structured parameters
- **Return Values**: Structured data types returned from methods
- **Configuration**: Shared configuration object for settings

## Migration from Monolithic CLI

For users migrating from the original CLI:

### Backward Compatibility
- All original features are preserved
- Command-line behavior remains consistent
- Export formats are enhanced but compatible
- Database interactions are unchanged

### New Features
- **Modular Architecture**: Better maintainability and extensibility
- **Enhanced Configuration**: More command-line options and settings
- **Counterfactual Analysis**: Optional contradictory evidence analysis
- **Improved Error Handling**: Better recovery from failures
- **Session State**: Foundation for session resumption features

### Usage Changes
```bash
# Original CLI
uv run python bmlibrarian_cli.py

# Refactored CLI (recommended)
uv run python bmlibrarian_cli_refactored.py

# With new options
uv run python bmlibrarian_cli_refactored.py --quick
uv run python bmlibrarian_cli_refactored.py --max-results 50 --timeout 10
```

## Future Enhancements

The modular architecture enables future enhancements:

### Session Resumption
- State serialization and restoration
- Workflow checkpoint saving
- Recovery from interrupted sessions

### Configuration Management
- User profile management
- Preset configurations for common use cases
- Dynamic configuration updates

### Advanced Features
- Parallel document processing
- Custom export templates
- API integration for external tools
- Advanced counterfactual analysis options

## Conclusion

The modular CLI architecture provides a solid foundation for BMLibrarian's continued development. By separating concerns across specialized modules, the system becomes more maintainable, testable, and extensible while preserving all existing functionality and adding powerful new features like counterfactual analysis.