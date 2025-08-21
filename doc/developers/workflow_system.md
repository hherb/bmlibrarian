# Workflow System Developer Guide

## Overview

BMLibrarian's workflow system provides flexible, enum-based orchestration for multi-agent research workflows. This system replaces brittle numbered steps with meaningful workflow orchestration that supports repeatable steps, branching logic, and iterative agent-driven refinement.

## Architecture

### Core Components

#### WorkflowStep Enum (`workflow_steps.py`)
Defines all available workflow steps with meaningful names:

```python
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

Each step provides:
- `display_name`: Human-readable name for UI display
- `description`: Detailed description of step functionality
- `is_repeatable`: Whether the step can be executed multiple times
- `is_optional`: Whether the step can be skipped

#### WorkflowDefinition
Defines workflow structure with dependencies, branching conditions, and repetition logic:

```python
class WorkflowDefinition:
    def __init__(self, name: str):
        self.steps: List[WorkflowStep] = []
        self.dependencies: Dict[WorkflowStep, Set[WorkflowStep]] = {}
        self.branch_conditions: Dict[WorkflowStep, Callable] = {}
        self.repeat_conditions: Dict[WorkflowStep, Callable] = {}
        self.skip_conditions: Dict[WorkflowStep, Callable] = {}
```

#### WorkflowExecutor
Manages step execution with context tracking and history:

```python
class WorkflowExecutor:
    def __init__(self, workflow: WorkflowDefinition):
        self.workflow = workflow
        self.execution_history: List[StepExecution] = []
        self.context: Dict[str, Any] = {}
        
    def execute_step(self, step: WorkflowStep, step_handler: Callable) -> StepExecution:
        # Executes step with timing, error handling, and logging
```

### Step Results

Steps return `StepResult` enum values:
- `SUCCESS`: Step completed successfully, proceed to next step
- `FAILURE`: Step failed, abort workflow
- `SKIP`: Step was skipped due to conditions
- `REPEAT`: Repeat the current step
- `BRANCH`: Branch to a different step (specified in context)
- `USER_CANCELLED`: User cancelled the step

## Creating New Workflow Steps

### 1. Define the Step
Add your step to the `WorkflowStep` enum:

```python
class WorkflowStep(Enum):
    # ... existing steps ...
    MY_NEW_STEP = auto()
    
    @property
    def display_name(self) -> str:
        display_names = {
            # ... existing mappings ...
            self.MY_NEW_STEP: "My New Step Name"
        }
        return display_names.get(self, self.name.replace('_', ' ').title())
    
    @property
    def description(self) -> str:
        descriptions = {
            # ... existing descriptions ...
            self.MY_NEW_STEP: "Detailed description of what this step does"
        }
        return descriptions.get(self, "No description available")
    
    @property
    def is_repeatable(self) -> bool:
        repeatable_steps = {
            # ... existing repeatable steps ...
            self.MY_NEW_STEP,  # If your step can be repeated
        }
        return self in repeatable_steps
```

### 2. Add to Workflow Definition
Include your step in the workflow sequence:

```python
def create_default_research_workflow() -> WorkflowDefinition:
    workflow = WorkflowDefinition("BMLibrarian Research Workflow")
    
    # ... existing steps ...
    
    workflow.add_step(
        WorkflowStep.MY_NEW_STEP,
        dependencies={WorkflowStep.PREVIOUS_STEP},
        repeat_condition=lambda ctx: ctx.get('repeat_my_step', False),
        skip_condition=lambda ctx: ctx.get('skip_my_step', False),
        branch_condition=lambda ctx: WorkflowStep.BRANCH_TARGET if ctx.get('should_branch') else None
    )
```

### 3. Implement Step Handler
Add a handler method in `WorkflowOrchestrator`:

```python
def _handle_my_new_step(self, context: Dict[str, Any]) -> StepResult:
    """Handle my new workflow step."""
    try:
        # Get data from context
        input_data = context.get('input_data')
        if not input_data:
            return StepResult.FAILURE
        
        # Perform step logic
        result = self._execute_my_step_logic(input_data)
        
        # Store result in context
        context['my_step_result'] = result
        
        # Check for branching conditions
        if should_branch_somewhere(result):
            context['branch_to_step'] = WorkflowStep.TARGET_STEP
            return StepResult.BRANCH
        
        # Check for repetition
        if should_repeat(result):
            return StepResult.REPEAT
        
        return StepResult.SUCCESS
        
    except Exception as e:
        logger.error(f"Error in my new step: {e}")
        return StepResult.FAILURE
```

### 4. Register Handler
Add your handler to the step dispatcher:

```python
def _handle_workflow_step(self, step: WorkflowStep, context: Dict[str, Any]) -> StepResult:
    """Handle execution of a workflow step."""
    try:
        if step == WorkflowStep.MY_NEW_STEP:
            return self._handle_my_new_step(context)
        # ... existing handlers ...
    except Exception as e:
        logger.error(f"Error executing step {step}: {e}")
        return StepResult.FAILURE
```

## Context Management

The workflow context (`Dict[str, Any]`) is shared across all steps and maintains state throughout execution.

### Best Practices

1. **Use descriptive keys**: `context['research_question']` not `context['q']`
2. **Check for required data**: Always validate context data before use
3. **Store results appropriately**: Use clear naming for step outputs
4. **Clean up branching context**: Remove `branch_to_step` after use

### Common Context Keys

- `research_question`: The user's research question
- `documents`: Search results from document search
- `scored_documents`: Documents with relevance scores
- `citations`: Extracted citations
- `report`: Generated report
- `counterfactual_analysis`: Counterfactual analysis results
- `comprehensive_report`: Final edited report

### Branching Context Keys

- `branch_to_step`: Target step for branching
- `no_documents_found`: Trigger query refinement
- `insufficient_citations`: Trigger threshold adjustment
- `user_wants_different_search`: User requested search refinement

## Implementing Repeatable Steps

Repeatable steps can be executed multiple times within a workflow:

```python
def _handle_repeatable_step(self, context: Dict[str, Any]) -> StepResult:
    """Handle a step that can be repeated."""
    
    # Get execution count
    execution_count = self.workflow_executor.get_step_execution_count(WorkflowStep.MY_REPEATABLE_STEP)
    
    # Implement max repetition limit
    if execution_count > 3:
        logger.warning("Maximum repetitions reached for step")
        return StepResult.SUCCESS
    
    # Perform step logic
    result = self._do_repeatable_work()
    
    # Check if repetition is needed
    if self.workflow_definition.should_repeat(WorkflowStep.MY_REPEATABLE_STEP, context):
        return StepResult.REPEAT
    
    return StepResult.SUCCESS
```

## Auto Mode Considerations

When implementing steps, consider auto mode execution:

```python
def _handle_interactive_step(self, context: Dict[str, Any]) -> StepResult:
    """Handle a step that may require user interaction."""
    
    if self.config.auto_mode:
        # Provide automatic behavior or graceful failure
        if can_handle_automatically(context):
            return self._handle_automatically(context)
        else:
            logger.error("Auto mode: Cannot handle step without user interaction")
            self.ui.show_error_message("Step requires interactive mode")
            return StepResult.FAILURE
    else:
        # Interactive handling
        return self._handle_interactively(context)
```

## Error Handling

### Step-Level Error Handling

```python
def _handle_step_with_recovery(self, context: Dict[str, Any]) -> StepResult:
    """Handle step with error recovery."""
    try:
        return self._do_step_work(context)
    except RecoverableError as e:
        logger.warning(f"Recoverable error in step: {e}")
        # Attempt recovery
        if self._can_recover(e):
            return self._recover_from_error(e, context)
        else:
            return StepResult.FAILURE
    except Exception as e:
        logger.error(f"Unrecoverable error in step: {e}")
        return StepResult.FAILURE
```

### Workflow-Level Error Handling

The `WorkflowOrchestrator` handles step failures:

```python
if execution.result == StepResult.FAILURE:
    logger.error(f"Workflow failed at step: {current_step.display_name}")
    self.ui.show_error_message(f"Workflow failed at: {current_step.display_name}")
    return False
```

## Testing Workflow Steps

### Unit Testing Steps

```python
def test_my_workflow_step():
    """Test custom workflow step."""
    from bmlibrarian.cli.workflow_steps import WorkflowStep, WorkflowExecutor, WorkflowDefinition
    
    # Create test workflow
    workflow = WorkflowDefinition("Test Workflow")
    workflow.add_step(WorkflowStep.MY_NEW_STEP)
    
    # Create executor with test context
    executor = WorkflowExecutor(workflow)
    executor.add_context('test_data', 'test_value')
    
    # Create mock step handler
    def mock_handler(step, context):
        assert step == WorkflowStep.MY_NEW_STEP
        assert context['test_data'] == 'test_value'
        return StepResult.SUCCESS
    
    # Execute step
    execution = executor.execute_step(WorkflowStep.MY_NEW_STEP, mock_handler)
    
    assert execution.result == StepResult.SUCCESS
    assert execution.step == WorkflowStep.MY_NEW_STEP
```

### Integration Testing

```python
def test_workflow_integration():
    """Test complete workflow execution."""
    config = create_test_config()
    ui = create_test_ui()
    
    orchestrator = WorkflowOrchestrator(config, ui, query_processor, formatter)
    
    # Test with known good question
    result = orchestrator.run_complete_workflow("test question")
    
    assert result is True
    assert orchestrator.final_report is not None
```

## Performance Considerations

### Step Timing

The `WorkflowExecutor` automatically tracks step execution time:

```python
@property
def duration_ms(self) -> float:
    """Duration of step execution in milliseconds."""
    if self.end_time:
        return (self.end_time - self.start_time) * 1000
    return 0.0
```

### Context Size Management

- Store only necessary data in context
- Clean up large objects after use
- Use references to shared objects when possible

### Long-Running Steps

For steps that take significant time:

```python
def _handle_long_running_step(self, context: Dict[str, Any]) -> StepResult:
    """Handle step that takes significant time."""
    
    # Show progress to user
    self.ui.show_progress_message("Starting long operation...")
    
    # Implement progress callbacks
    def progress_callback(current, total):
        if self.config.show_progress:
            percentage = (current / total) * 100
            print(f"   Progress: {current}/{total} ({percentage:.1f}%)")
    
    # Execute with progress tracking
    result = self._long_operation(progress_callback=progress_callback)
    
    return StepResult.SUCCESS if result else StepResult.FAILURE
```

## Migration from Numbered Steps

When migrating from numbered step systems:

1. **Identify step boundaries**: Map numbered steps to enum values
2. **Extract step logic**: Move step code into handler methods
3. **Preserve state**: Ensure context maintains necessary data
4. **Test thoroughly**: Verify workflow behavior matches original
5. **Update documentation**: Reflect new step names in user guides

## Best Practices

1. **Meaningful Names**: Use descriptive enum names that clearly indicate purpose
2. **Single Responsibility**: Each step should have one clear purpose
3. **Context Validation**: Always validate required context data
4. **Error Recovery**: Implement graceful error handling and recovery
5. **Progress Feedback**: Provide user feedback for long-running operations
6. **Auto Mode Support**: Consider non-interactive execution paths
7. **Testing**: Write comprehensive tests for step logic
8. **Documentation**: Document step behavior and context requirements
9. **Logging**: Include structured logging for debugging and monitoring
10. **Flexibility**: Design steps to support future extensions and modifications