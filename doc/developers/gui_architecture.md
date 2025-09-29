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

### Research GUI (`research_app.py`)

The Research GUI provides a visual interface for executing BMLibrarian's multi-agent research workflows.

#### Key Features
- **Interactive Workflow**: Visual progress through 11 research steps
- **Real-time Execution**: Live agent orchestration with progress updates
- **Report Preview**: Full markdown rendering with scrollable display
- **File Management**: Direct file save with cross-platform compatibility
- **Configuration Integration**: Uses models and settings from config system

#### Architecture Components
```python
class ResearchGUI:
    """Main research GUI application."""
    
    def __init__(self, agents=None):
        self.step_cards: Dict[WorkflowStep, StepCard] = {}  # Visual workflow
        self.workflow_orchestrator = None                   # Agent coordination
        self.dialog_manager = None                          # UI dialogs
        self.agents_initialized = agents is not None       # Pre-initialized agents
```

## Component Architecture

### Reusable Components (`components.py`)

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

### Adding New GUI Components
1. **Inherit from Base Patterns**: Follow existing component architecture
2. **Implement State Management**: Proper state synchronization
3. **Add Error Handling**: Graceful error recovery and user feedback
4. **Include Documentation**: Component-level documentation and examples
5. **Test Cross-Platform**: Verify functionality on all target platforms

### Extending Workflow Integration
1. **Implement Step Handlers**: Add handlers for new workflow steps
2. **Update Visual Components**: Create appropriate UI elements
3. **Add Progress Tracking**: Include progress indicators for new operations
4. **Handle Edge Cases**: Error recovery and validation
5. **Maintain Context**: Proper state management across steps

### Configuration Integration
1. **Follow Config Schema**: Use established configuration patterns
2. **Add Validation**: Input validation and error feedback
3. **Include Defaults**: Sensible default values
4. **Document Settings**: Clear documentation for new settings
5. **Test Persistence**: Verify configuration save/load functionality

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
- **Plugin Architecture**: Support for custom GUI extensions
- **Theme System**: Multiple UI themes and customization options
- **Advanced Visualizations**: Enhanced charts and graphs for research data
- **Collaborative Features**: Multi-user workflow coordination
- **Mobile Support**: Responsive design for mobile devices

### Architecture Evolution
- **Component Library**: Shared component library across applications
- **State Management Framework**: Centralized state management system
- **API Abstraction**: Clean separation between GUI and core functionality
- **Testing Framework**: Comprehensive GUI testing infrastructure
- **Internationalization**: Multi-language support infrastructure

---

This GUI architecture provides a solid foundation for BMLibrarian's visual interfaces while maintaining the flexibility to evolve and expand as the system grows.