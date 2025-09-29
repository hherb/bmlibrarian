# GUI Architecture Documentation

## Overview

BMLibrarian features a modern, modular GUI architecture built with the [Flet](https://flet.dev/) framework. The GUI system provides both configuration management and research workflow capabilities through two main applications with a shared component architecture.

## Architecture Principles

### Modular Design
- **Component-based architecture** with reusable UI elements
- **Separation of concerns** between UI, business logic, and data management
- **Clean interfaces** between GUI and core BMLibrarian functionality
- **Cross-platform compatibility** (desktop and web deployment modes)

### Real-time Integration
- **Live agent orchestration** with real-time progress updates
- **Configuration synchronization** with BMLibrarian's config system
- **Dynamic model refresh** from Ollama server
- **Responsive UI updates** during long-running operations

## GUI Applications

### Configuration GUI (`config_app.py`)

The Configuration GUI provides a comprehensive tabbed interface for managing BMLibrarian settings.

#### Key Features
- **Tabbed Interface**: Separate configuration tabs for each agent type
- **Model Management**: Live model selection from Ollama server
- **Parameter Tuning**: Interactive controls for agent parameters
- **Connection Testing**: Verify Ollama connectivity and model availability
- **File Operations**: Save/load configuration files with validation

#### Architecture Components
```python
class BMLibrarianConfigApp:
    """Main configuration application using Flet."""
    
    def __init__(self):
        self.config = get_config()           # Configuration management
        self.tabs: Dict[str, Any] = {}       # Tab registry
        self.tab_objects: Dict[str, Any] = {} # Tab object references
```

#### Tab System
- **GeneralSettingsTab**: Ollama server, database, and CLI defaults
- **AgentConfigTab**: Individual agent configuration (one per agent type)
- **Dynamic Tab Creation**: Tabs created programmatically based on agent types
- **Shared State Management**: Configuration changes propagated across tabs

### Research GUI (`research_app.py`) - Modular Architecture

The Research GUI provides a visual interface for executing BMLibrarian's multi-agent research workflows. **Recently refactored from a 2,325-line monolithic file into a modular architecture with 6 specialized modules.**

#### Key Features
- **Interactive Workflow**: Visual progress through 11 research steps
- **Real-time Execution**: Live agent orchestration with progress updates
- **Report Preview**: Full markdown rendering with scrollable display
- **File Management**: Direct file save with cross-platform compatibility
- **Configuration Integration**: Uses models and settings from config system
- **Modular Architecture**: 90% size reduction with specialized modules

#### Modular Architecture Components

**Main Application Class (227 lines):**
```python
class ResearchGUI:
    """Refactored research GUI with modular architecture."""
    
    def __init__(self, agents=None):
        # Managers and handlers (initialized in main())
        self.tab_manager = None           # TabManager - handles tabs
        self.event_handlers = None        # EventHandlers - handles events
        self.data_updaters = None         # DataUpdaters - updates tab content
        self.dialog_manager = None        # DialogManager - dialogs
        self.workflow_executor = None     # WorkflowExecutor - execution
        
    def _build_ui(self):
        """Build UI using modular components."""
        header = create_header()
        self.question_field = create_question_field(self.event_handlers.on_question_change)
        controls_section = create_controls_section(...)
        tabs_container = self.tab_manager.create_tabbed_interface(...)
```

**Supporting Modules:**

1. **`ui_builder.py` (354 lines)** - Reusable UI component builders
2. **`tab_manager.py` (140 lines)** - Tabbed interface management  
3. **`event_handlers.py` (330 lines)** - Event handling functions
4. **`data_updaters.py` (290 lines)** - Tab content update logic
5. **`display_utils.py` (570 lines)** - Display helper classes

## Modular GUI Architecture

### Architecture Overview

The Research GUI has been refactored from a single 2,325-line monolithic file into a **modular architecture** with 6 specialized modules, achieving a **90% size reduction** in the main application class while improving maintainability and reusability.

#### Design Principles

- **Single Responsibility**: Each module handles one specific concern
- **Short Functions**: Most functions are 10-30 lines (vs 200+ lines before)
- **Reusable Components**: UI builders can be used across different interfaces  
- **Clean Separation**: UI, logic, data, and events are properly separated
- **Dependency Injection**: Modules receive dependencies rather than creating them

#### Module Organization

```
gui/
├── research_app.py              # Main class (227 lines) - 90% reduction!
├── ui_builder.py               # Reusable UI component builders (354 lines)
├── tab_manager.py              # Tabbed interface management (140 lines)  
├── event_handlers.py           # Event handling functions (330 lines)
├── data_updaters.py            # Tab content update logic (290 lines)
├── display_utils.py            # Display helper classes (570 lines)
├── research_app_original_backup.py  # Backup of original
├── components.py               # Existing step cards (unchanged)
├── dialogs.py                  # Existing dialogs (unchanged)  
└── workflow.py                 # Existing workflow (unchanged)
```

### Module Details

#### 1. UI Builder Module (`ui_builder.py`)

**Purpose**: Reusable UI component construction functions with consistent styling.

**Key Functions**:
```python
# Core UI components
create_header() -> ft.Container
create_question_field(on_change_handler) -> ft.TextField
create_toggle_switch(label, value, on_change_handler) -> ft.Switch
create_start_button(on_click_handler) -> ft.ElevatedButton
create_controls_section(...) -> ft.Container

# Standardized elements
create_tab_header(title, count=None, subtitle="") -> List[ft.Control]
create_empty_state(message) -> ft.Container
create_expandable_card(title, subtitle, content, badges=None) -> ft.ExpansionTile

# Badges and indicators
create_score_badge(score, max_score=5.0) -> ft.Container
create_relevance_badge(relevance) -> ft.Container  
create_priority_badge(priority) -> ft.Container

# Content sections
create_metadata_section(items, bg_color) -> ft.Container
create_text_content_section(title, content, bg_color, selectable, italic) -> ft.Container
create_action_button_row(buttons) -> ft.Row

# Utilities
truncate_text(text, max_length=80) -> str
extract_year_from_date(date_str) -> str
format_authors_list(authors, max_count=3) -> str
```

#### 2. Tab Manager Module (`tab_manager.py`)

**Purpose**: Manages the tabbed interface creation and content updates.

**Key Class**:
```python
class TabManager:
    def __init__(self):
        self.tabs_container: Optional[ft.Tabs] = None
        self.tab_contents: Dict[str, ft.Container] = {}
        
    def create_tabbed_interface(self, step_cards) -> ft.Tabs:
        """Create complete tabbed interface with 6 tabs."""
        
    def get_tab_content(self, tab_name: str) -> Optional[ft.Container]:
        """Get specific tab's content container."""
        
    def update_tab_content(self, tab_name: str, new_content: ft.Column):
        """Update a tab's content dynamically."""
```

**Managed Tabs**: Workflow, Literature, Scoring, Citations, Counterfactual, Report

#### 3. Event Handlers Module (`event_handlers.py`)

**Purpose**: Handles all UI events with focused, single-purpose functions.

**Key Class**:
```python
class EventHandlers:
    def __init__(self, app: 'ResearchGUI'):
        self.app = app
        
    # Core event handlers
    def on_question_change(self, e): """Handle research question input."""
    def on_human_loop_toggle_change(self, e): """Handle interactive mode toggle."""  
    def on_start_research(self, e): """Start the research workflow."""
    def on_save_report(self, e): """Save final report to file."""
    def on_copy_report(self, e): """Copy report to clipboard."""
    def on_preview_report(self, e): """Show report preview overlay."""
    
    # Private helpers
    def _run_workflow_thread(self): """Execute workflow in background."""
    def _update_step_status(self, step, status, content): """Update step progress."""  
    def _show_save_path_dialog(self): """Custom save dialog."""
    def _show_preview_overlay(self): """Report preview overlay."""
```

#### 4. Data Updaters Module (`data_updaters.py`)

**Purpose**: Handles tab content updates with workflow data.

**Key Class**:
```python
class DataUpdaters:
    def __init__(self, app: 'ResearchGUI'):
        self.app = app
        
    # Public update methods
    def update_documents(self, documents: List[dict]): """Update literature tab."""
    def update_scored_documents(self, scored_documents: List[tuple]): """Update scoring tab."""
    def update_citations(self, citations: List[Any]): """Update citations tab."""
    def update_counterfactual_analysis(self, analysis: Any): """Update counterfactual tab."""  
    def update_report(self, report_content: str): """Update report tab."""
    
    # Conditional update methods
    def update_documents_if_available(self): """Update if data exists in workflow executor."""
    def update_all_tabs_if_data_available(self): """Update all tabs after workflow."""
    
    # Private update methods
    def _update_literature_tab(self): """Internal literature tab update."""
    def _update_scoring_tab(self): """Internal scoring tab update."""
    def _create_report_components(self) -> List[ft.Control]: """Create report display."""
```

#### 5. Display Utils Module (`display_utils.py`)

**Purpose**: Helper classes for creating complex display components.

**Key Classes**:
```python
class DocumentCardCreator:
    """Creates document display cards."""
    def create_document_cards_list(self, documents, show_score=False) -> List[ft.Control]
    def create_scored_document_cards_list(self, scored_documents) -> List[ft.Control] 
    def create_document_card(self, index, doc, show_score=False, scoring_result=None) -> ft.ExpansionTile

class CitationCardCreator:
    """Creates citation display cards."""
    def create_citation_cards_list(self, citations) -> List[ft.Control]
    def create_citation_card(self, index, citation) -> ft.ExpansionTile
    
class CounterfactualDisplayCreator:
    """Creates counterfactual analysis displays."""  
    def create_counterfactual_display(self, analysis) -> List[ft.Control]
    def _create_comprehensive_analysis_components(self, analysis_dict) -> List[ft.Control]
    def _create_basic_analysis_components(self, analysis) -> List[ft.Control]
```

### Benefits Achieved

#### Maintainability
- **Easy Navigation**: Specific functionality is easy to locate
- **Focused Changes**: Modifications affect only relevant modules
- **Clear Dependencies**: Module relationships are explicit
- **Reduced Complexity**: Each module handles a single concern

#### Reusability  
- **Component Library**: UI builders can be used in other applications
- **Shared Logic**: Display utilities work across different contexts
- **Modular Updates**: Tab managers can handle different content types
- **Event Patterns**: Event handlers demonstrate reusable patterns

#### Testability
- **Unit Testing**: Each module can be tested independently
- **Mock Dependencies**: Easy to mock dependencies for testing
- **Isolated Logic**: Business logic separated from UI concerns
- **Clear Interfaces**: Well-defined APIs between modules

#### Extensibility
- **New Components**: Easy to add new UI builders
- **Additional Events**: Simple to add new event handlers  
- **More Tabs**: Tab manager easily handles new tab types
- **Display Types**: Display utils support new data formats

## Component Architecture

### Legacy Components (Unchanged)

#### Reusable Components (`components.py`)

#### StepCard Component
Provides visual representation of workflow steps with real-time status updates.

```python
class StepCard:
    """Visual representation of a workflow step with status tracking."""
    
    def __init__(self, step: WorkflowStep, page: ft.Page):
        self.step = step
        self.status = StepStatus.PENDING
        self.card = ft.Card(...)  # Flet UI component
        
    def update_status(self, status: StepStatus, message: str = ""):
        """Update step status with visual feedback."""
```

**Features:**
- **Status Visualization**: Pending, running, completed, error states
- **Progress Indicators**: Visual feedback during execution
- **Collapsible Design**: Space-efficient layout with expand/collapse
- **Message Display**: Show step-specific status messages

### Dialog Management (`dialogs.py`)

Centralized dialog handling for consistent user experience.

```python
class DialogManager:
    """Manages all dialog interactions for the GUI."""
    
    def __init__(self, page: ft.Page):
        self.page = page
        self.dialogs: Dict[str, ft.AlertDialog] = {}
        
    def show_error_dialog(self, title: str, message: str):
        """Display error dialog with consistent styling."""
        
    def show_save_dialog(self, callback: Callable):
        """File save dialog with cross-platform compatibility."""
```

**Key Dialogs:**
- **Error Dialogs**: Consistent error reporting with actionable messages
- **File Save Dialog**: Cross-platform file selection (macOS-compatible)
- **Confirmation Dialogs**: User confirmation for destructive operations
- **Progress Dialogs**: Long-running operation feedback

### Tab Components (`tabs/`)

Modular tab system for the configuration GUI.

#### GeneralSettingsTab (`general_tab.py`)
- **Ollama Configuration**: Server URL, connection testing
- **Database Settings**: PostgreSQL connection parameters
- **CLI Defaults**: Default values for command-line options

#### AgentConfigTab (`agent_tab.py`)
- **Model Selection**: Dropdown with live model refresh
- **Parameter Controls**: Sliders and inputs for agent-specific settings
- **Validation**: Real-time parameter validation
- **Reset Functionality**: Restore default agent settings

## Workflow Integration (`gui/workflow.py`)

### WorkflowExecutor Class
Bridges GUI components with BMLibrarian's agent orchestration system.

```python
class WorkflowExecutor:
    """Executes research workflows with GUI integration."""
    
    def __init__(self, research_gui: 'ResearchGUI'):
        self.gui = research_gui
        self.agents = None
        self.orchestrator = None
        
    async def execute_workflow_step(self, step: WorkflowStep, context: dict):
        """Execute workflow step with GUI updates."""
```

**Key Features:**
- **Agent Initialization**: Configure agents from GUI settings
- **Step Execution**: Execute workflow steps with visual feedback
- **Context Management**: Maintain workflow state across steps
- **Error Handling**: Graceful error recovery with user feedback

## Cross-Platform Deployment

### Desktop Mode (Default)
```bash
uv run python bmlibrarian_config_gui.py        # Native desktop app
uv run python bmlibrarian_research_gui.py      # Desktop research interface
```

### Web Mode
```bash
uv run python bmlibrarian_config_gui.py --view web --port 8080
```

**Features:**
- **Native Desktop**: Platform-specific window management and file dialogs
- **Web Interface**: Browser-based access with responsive design
- **Port Configuration**: Customizable web server port
- **Debug Mode**: Enhanced logging and error reporting

## State Management

### Configuration Synchronization
- **Automatic Loading**: Load configuration from `~/.bmlibrarian/config.json`
- **Live Updates**: Real-time configuration changes without restart
- **Validation**: Input validation with user feedback
- **Persistence**: Automatic saving of configuration changes

### Workflow State
- **Context Preservation**: Maintain workflow state across steps
- **Progress Tracking**: Track completion status of each step
- **Error Recovery**: Handle and recover from step execution errors
- **Results Storage**: Store intermediate and final results

## Performance Considerations

### Async Operations
- **Non-blocking UI**: Agent execution doesn't freeze the interface
- **Progress Updates**: Real-time feedback during long operations
- **Cancellation Support**: Ability to cancel running workflows
- **Resource Management**: Proper cleanup of background tasks

### Memory Management
- **Component Lifecycle**: Proper initialization and cleanup
- **Resource Disposal**: Release UI resources when no longer needed
- **Agent Lifecycle**: Manage agent initialization and termination
- **Queue Management**: Efficient handling of background tasks

## Development Guidelines

### Working with the Modular Architecture

#### Adding New UI Components
1. **Use UI Builder Functions**: Add new builders to `ui_builder.py`
2. **Follow Naming Conventions**: `create_*` for builders, short descriptive names
3. **Keep Functions Short**: Aim for 10-30 lines per function
4. **Use Consistent Styling**: Follow established color and spacing patterns
5. **Add Type Hints**: Include proper type annotations for all parameters
6. **Document Parameters**: Clear docstrings with parameter descriptions

**Example**:
```python
def create_status_indicator(status: str, size: int = 12) -> ft.Container:
    """Create a colored status indicator.
    
    Args:
        status: Status string (pending, running, completed, error)
        size: Icon size in pixels
        
    Returns:
        Container with status icon and styling
    """
    # Implementation here...
```

#### Adding New Event Handlers
1. **Add to EventHandlers Class**: Keep all handlers in `event_handlers.py`
2. **Use Descriptive Names**: `on_*` prefix for event handlers
3. **Handle Errors Gracefully**: Include try-catch blocks and user feedback
4. **Keep Handlers Focused**: One handler per specific user action
5. **Use Private Helpers**: Break complex logic into private methods

**Example**:
```python
def on_export_data(self, e):
    """Handle data export button click."""
    try:
        self._validate_export_settings()
        self._show_export_dialog()
    except Exception as ex:
        self.app.dialog_manager.show_error_dialog(f"Export failed: {str(ex)}")
```

#### Adding New Tabs
1. **Use TabManager**: Add tab creation to `tab_manager.py`
2. **Create Update Logic**: Add corresponding update methods to `data_updaters.py`
3. **Use Display Utils**: Create card creators in `display_utils.py` if needed
4. **Follow Tab Pattern**: Use `create_tab_header()` and `create_empty_state()`
5. **Register Tab Content**: Store tab references in `tab_contents` dictionary

**Example**:
```python
def _create_analysis_tab(self) -> ft.Container:
    """Create the analysis results tab content."""
    header_components = create_tab_header(
        "Analysis Results",
        subtitle="Statistical analysis and insights."
    )
    empty_state = create_empty_state("No analysis results yet.")
    
    self.tab_contents['analysis'] = ft.Container(
        content=ft.Column([*header_components, empty_state], spacing=10, scroll=ft.ScrollMode.AUTO),
        padding=ft.padding.all(15),
        expand=True
    )
    return self.tab_contents['analysis']
```

#### Adding New Display Components
1. **Create Helper Classes**: Add to `display_utils.py` for complex displays
2. **Use Card Pattern**: Leverage `create_expandable_card()` for consistency
3. **Implement Data Extraction**: Handle both objects and dictionaries
4. **Include Error Handling**: Graceful fallbacks for missing data
5. **Add Utility Methods**: Use existing utility functions for common operations

**Example**:
```python
class AnalysisCardCreator:
    """Creates analysis result display cards."""
    
    def create_analysis_card(self, index: int, analysis: Any) -> ft.ExpansionTile:
        """Create expandable card for analysis result."""
        title_text = f"{index + 1}. {truncate_text(analysis.title, 80)}"
        subtitle_text = f"Confidence: {analysis.confidence:.2f}"
        
        content_sections = [
            create_text_content_section("Analysis:", analysis.description),
            create_metadata_section([
                ("Type", analysis.type),
                ("Date", extract_year_from_date(analysis.date))
            ])
        ]
        
        badges = [create_score_badge(analysis.confidence)]
        
        return create_expandable_card(title_text, subtitle_text, content_sections, badges)
```

### Extending Workflow Integration
1. **Update EventHandlers**: Add step completion handling in `_handle_step_completion()`
2. **Update DataUpdaters**: Add methods to update tabs with new data types
3. **Maintain Patterns**: Follow existing patterns for step status updates
4. **Add Progress Tracking**: Include visual progress indicators
5. **Handle Context**: Proper state management across workflow steps

### Configuration Integration
1. **Follow Config Schema**: Use established configuration patterns
2. **Add Validation**: Input validation and error feedback
3. **Include Defaults**: Sensible default values
4. **Document Settings**: Clear documentation for new settings
5. **Test Persistence**: Verify configuration save/load functionality

### Testing Modular Components

#### Unit Testing Strategy
1. **Test Each Module**: Independent tests for each module
2. **Mock Dependencies**: Use mocks for external dependencies
3. **Test Public APIs**: Focus on public methods and interfaces
4. **Include Edge Cases**: Test error conditions and boundary cases
5. **UI Testing**: Test UI components with Flet testing framework

**Example Test Structure**:
```python
# test_ui_builder.py
def test_create_header():
    """Test header creation with proper styling."""
    header = create_header()
    assert isinstance(header, ft.Container)
    assert header.content.controls[0].value == "BMLibrarian Research Assistant"

# test_event_handlers.py  
def test_on_question_change():
    """Test question change event handling."""
    mock_app = Mock()
    handlers = EventHandlers(mock_app)
    mock_event = Mock()
    mock_event.control.value = "test question"
    
    handlers.on_question_change(mock_event)
    
    assert mock_app.research_question == "test question"
```

#### Integration Testing
1. **Test Module Interactions**: Verify modules work together correctly
2. **Test Workflow**: End-to-end testing of research workflow
3. **Test UI Updates**: Verify tab updates work with real data
4. **Test Error Handling**: Ensure graceful error recovery
5. **Performance Testing**: Check responsiveness with large datasets

## Best Practices

### UI Design
- **Consistent Styling**: Follow established visual patterns
- **Responsive Layout**: Adapt to different screen sizes and resolutions
- **Accessibility**: Include proper ARIA labels and keyboard navigation
- **User Feedback**: Provide clear feedback for all user actions
- **Error Prevention**: Validate inputs and prevent invalid states

### Code Organization
- **Separation of Concerns**: Keep UI logic separate from business logic
- **Modular Architecture**: Create reusable components and modules
- **Clean Interfaces**: Well-defined APIs between components
- **Documentation**: Comprehensive code documentation
- **Testing**: Unit tests for critical GUI functionality

### Performance
- **Lazy Loading**: Load components and data only when needed
- **Efficient Updates**: Minimize unnecessary UI updates
- **Background Processing**: Keep long operations off the main thread
- **Resource Cleanup**: Proper disposal of UI resources
- **Memory Monitoring**: Track and optimize memory usage

## Future Enhancements

### Planned Features
- **Plugin Architecture**: Support for custom GUI extensions using modular system
- **Theme System**: Multiple UI themes leveraging UI builder functions
- **Advanced Visualizations**: Enhanced charts and graphs using display utilities
- **Collaborative Features**: Multi-user workflow coordination through event handlers
- **Mobile Support**: Responsive design using existing modular components

### Architecture Evolution

#### Leveraging Modular Architecture
- **Component Library**: Export UI builders as standalone library for other applications
- **Extended Display Utils**: Add more card creators for different data types
- **Event Handler Registry**: Plugin system for custom event handlers
- **Tab Plugin System**: Allow third-party tabs using TabManager interface
- **Theming System**: UI builder functions with theme parameter support

#### Enhanced Modularity
- **Service Layer**: Extract business logic into service modules
- **State Management**: Centralized state management using existing data updaters pattern
- **Configuration Framework**: Extend modular config system to support plugins
- **Testing Infrastructure**: Comprehensive testing using module-based structure
- **API Gateway**: Clean APIs between GUI modules and core functionality

#### Backward Compatibility
- **Migration Path**: Gradual migration from legacy components to modular system
- **Adapter Pattern**: Adapt existing components to work with new modular architecture
- **Version Support**: Support both old and new component patterns during transition
- **Documentation Updates**: Maintain docs for both legacy and modular approaches

---

This GUI architecture provides a solid foundation for BMLibrarian's visual interfaces while maintaining the flexibility to evolve and expand as the system grows.