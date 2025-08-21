"""
Workflow Step Definitions and Orchestration Enums

Provides a flexible, enum-based workflow system that supports:
- Meaningful step names instead of brittle numbering
- Repeatable steps for iterative workflows
- Easy reordering and insertion of new steps
- Conditional step execution and branching
"""

from enum import Enum, auto
from typing import Dict, List, Optional, Set, Callable, Any
from dataclasses import dataclass
import time
import logging

logger = logging.getLogger('bmlibrarian.workflow_steps')


class WorkflowStep(Enum):
    """Enumeration of all workflow steps with meaningful names."""
    
    # Core workflow steps
    COLLECT_RESEARCH_QUESTION = auto()
    GENERATE_AND_EDIT_QUERY = auto()  
    SEARCH_DOCUMENTS = auto()
    REVIEW_SEARCH_RESULTS = auto()
    SCORE_DOCUMENTS = auto()
    EXTRACT_CITATIONS = auto()
    GENERATE_REPORT = auto()
    
    # Analysis and enhancement steps
    PERFORM_COUNTERFACTUAL_ANALYSIS = auto()
    SEARCH_CONTRADICTORY_EVIDENCE = auto()
    EDIT_COMPREHENSIVE_REPORT = auto()
    
    # Export and finalization steps
    EXPORT_REPORT = auto()
    
    # Repeatable/conditional steps
    REFINE_QUERY = auto()              # Can repeat if search results insufficient
    ADJUST_SCORING_THRESHOLDS = auto()  # Can repeat to get better citations
    REQUEST_MORE_CITATIONS = auto()     # Can repeat if report needs more evidence
    REVIEW_AND_REVISE_REPORT = auto()   # Can repeat for iterative editing

    @property
    def display_name(self) -> str:
        """Human-readable display name for the step."""
        display_names = {
            self.COLLECT_RESEARCH_QUESTION: "Research Question Collection",
            self.GENERATE_AND_EDIT_QUERY: "Query Generation & Editing", 
            self.SEARCH_DOCUMENTS: "Document Search",
            self.REVIEW_SEARCH_RESULTS: "Search Results Review",
            self.SCORE_DOCUMENTS: "Document Relevance Scoring",
            self.EXTRACT_CITATIONS: "Citation Extraction",
            self.GENERATE_REPORT: "Report Generation",
            self.PERFORM_COUNTERFACTUAL_ANALYSIS: "Counterfactual Analysis",
            self.SEARCH_CONTRADICTORY_EVIDENCE: "Contradictory Evidence Search",
            self.EDIT_COMPREHENSIVE_REPORT: "Comprehensive Report Editing",
            self.EXPORT_REPORT: "Report Export",
            self.REFINE_QUERY: "Query Refinement",
            self.ADJUST_SCORING_THRESHOLDS: "Scoring Threshold Adjustment",
            self.REQUEST_MORE_CITATIONS: "Additional Citation Request",
            self.REVIEW_AND_REVISE_REPORT: "Report Review & Revision"
        }
        return display_names.get(self, self.name.replace('_', ' ').title())

    @property
    def description(self) -> str:
        """Detailed description of what this step accomplishes."""
        descriptions = {
            self.COLLECT_RESEARCH_QUESTION: "Collect the research question from user or auto-mode",
            self.GENERATE_AND_EDIT_QUERY: "Generate PostgreSQL query and allow human editing",
            self.SEARCH_DOCUMENTS: "Execute database search using the refined query",
            self.REVIEW_SEARCH_RESULTS: "Review and approve search results with user",
            self.SCORE_DOCUMENTS: "Score documents (1-5) for relevance to research question",
            self.EXTRACT_CITATIONS: "Extract relevant passages from high-scoring documents",
            self.GENERATE_REPORT: "Generate medical publication-style report from citations",
            self.PERFORM_COUNTERFACTUAL_ANALYSIS: "Analyze report for potential contradictory evidence",
            self.SEARCH_CONTRADICTORY_EVIDENCE: "Search database for studies that contradict findings",
            self.EDIT_COMPREHENSIVE_REPORT: "Create balanced report integrating all evidence",
            self.EXPORT_REPORT: "Save final report to file with user's choice",
            self.REFINE_QUERY: "Refine search query based on insufficient results",
            self.ADJUST_SCORING_THRESHOLDS: "Adjust relevance thresholds to get more citations", 
            self.REQUEST_MORE_CITATIONS: "Request additional citations for comprehensive reporting",
            self.REVIEW_AND_REVISE_REPORT: "Review and iteratively improve the generated report"
        }
        return descriptions.get(self, "No description available")

    @property
    def is_repeatable(self) -> bool:
        """Whether this step can be repeated in the workflow."""
        repeatable_steps = {
            self.REFINE_QUERY,
            self.ADJUST_SCORING_THRESHOLDS,
            self.REQUEST_MORE_CITATIONS, 
            self.REVIEW_AND_REVISE_REPORT,
            self.GENERATE_AND_EDIT_QUERY,  # User might want to edit query multiple times
            self.REVIEW_SEARCH_RESULTS,    # User might want to review again after changes
        }
        return self in repeatable_steps

    @property
    def is_optional(self) -> bool:
        """Whether this step can be skipped."""
        optional_steps = {
            self.PERFORM_COUNTERFACTUAL_ANALYSIS,
            self.SEARCH_CONTRADICTORY_EVIDENCE,
            self.EDIT_COMPREHENSIVE_REPORT,
            self.EXPORT_REPORT
        }
        return self in optional_steps


class StepResult(Enum):
    """Result of executing a workflow step."""
    SUCCESS = "success"
    FAILURE = "failure"
    SKIP = "skip"
    REPEAT = "repeat"
    BRANCH = "branch"
    USER_CANCELLED = "user_cancelled"


@dataclass
class StepExecution:
    """Record of a step execution."""
    step: WorkflowStep
    start_time: float
    end_time: Optional[float] = None
    result: Optional[StepResult] = None
    data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    execution_count: int = 1

    @property
    def duration_ms(self) -> float:
        """Duration of step execution in milliseconds."""
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0

    @property
    def is_completed(self) -> bool:
        """Whether the step completed successfully."""
        return self.result == StepResult.SUCCESS


class WorkflowDefinition:
    """Defines a workflow as a sequence of steps with branching and repetition logic."""
    
    def __init__(self, name: str):
        self.name = name
        self.steps: List[WorkflowStep] = []
        self.dependencies: Dict[WorkflowStep, Set[WorkflowStep]] = {}
        self.branch_conditions: Dict[WorkflowStep, Callable[[Dict[str, Any]], Optional[WorkflowStep]]] = {}
        self.repeat_conditions: Dict[WorkflowStep, Callable[[Dict[str, Any]], bool]] = {}
        self.skip_conditions: Dict[WorkflowStep, Callable[[Dict[str, Any]], bool]] = {}

    def add_step(self, step: WorkflowStep, 
                 dependencies: Optional[Set[WorkflowStep]] = None,
                 branch_condition: Optional[Callable[[Dict[str, Any]], Optional[WorkflowStep]]] = None,
                 repeat_condition: Optional[Callable[[Dict[str, Any]], bool]] = None,
                 skip_condition: Optional[Callable[[Dict[str, Any]], bool]] = None) -> 'WorkflowDefinition':
        """Add a step to the workflow with optional conditions."""
        if step not in self.steps:
            self.steps.append(step)
        
        if dependencies:
            self.dependencies[step] = dependencies
            
        if branch_condition:
            self.branch_conditions[step] = branch_condition
            
        if repeat_condition:
            self.repeat_conditions[step] = repeat_condition
            
        if skip_condition:
            self.skip_conditions[step] = skip_condition
            
        return self

    def should_repeat(self, step: WorkflowStep, context: Dict[str, Any]) -> bool:
        """Check if a step should be repeated."""
        if not step.is_repeatable:
            return False
        
        repeat_condition = self.repeat_conditions.get(step)
        if repeat_condition:
            return repeat_condition(context)
        
        return False

    def should_skip(self, step: WorkflowStep, context: Dict[str, Any]) -> bool:
        """Check if a step should be skipped."""
        skip_condition = self.skip_conditions.get(step)
        if skip_condition:
            return skip_condition(context)
            
        return False

    def get_next_step(self, current_step: WorkflowStep, context: Dict[str, Any]) -> Optional[WorkflowStep]:
        """Get the next step based on current step and context."""
        # Check for branching conditions
        branch_condition = self.branch_conditions.get(current_step)
        if branch_condition:
            branch_step = branch_condition(context)
            if branch_step:
                return branch_step

        # Get the next step in sequence
        try:
            current_index = self.steps.index(current_step)
            if current_index + 1 < len(self.steps):
                return self.steps[current_index + 1]
        except ValueError:
            logger.warning(f"Current step {current_step} not found in workflow steps")
        
        return None


def create_default_research_workflow() -> WorkflowDefinition:
    """Create the default BMLibrarian research workflow."""
    workflow = WorkflowDefinition("BMLibrarian Research Workflow")
    
    # Define the main workflow sequence
    workflow.add_step(WorkflowStep.COLLECT_RESEARCH_QUESTION)
    
    workflow.add_step(
        WorkflowStep.GENERATE_AND_EDIT_QUERY,
        dependencies={WorkflowStep.COLLECT_RESEARCH_QUESTION},
        repeat_condition=lambda ctx: ctx.get('user_wants_to_edit_query', False)
    )
    
    workflow.add_step(
        WorkflowStep.SEARCH_DOCUMENTS,
        dependencies={WorkflowStep.GENERATE_AND_EDIT_QUERY}
    )
    
    workflow.add_step(
        WorkflowStep.REVIEW_SEARCH_RESULTS,
        dependencies={WorkflowStep.SEARCH_DOCUMENTS}
    )
    
    workflow.add_step(
        WorkflowStep.SCORE_DOCUMENTS,
        dependencies={WorkflowStep.REVIEW_SEARCH_RESULTS}
    )
    
    workflow.add_step(
        WorkflowStep.EXTRACT_CITATIONS,
        dependencies={WorkflowStep.SCORE_DOCUMENTS}
    )
    
    workflow.add_step(
        WorkflowStep.GENERATE_REPORT,
        dependencies={WorkflowStep.EXTRACT_CITATIONS}
    )
    
    workflow.add_step(
        WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS,
        dependencies={WorkflowStep.GENERATE_REPORT},
        skip_condition=lambda ctx: not ctx.get('user_wants_counterfactual', True)
    )
    
    workflow.add_step(
        WorkflowStep.SEARCH_CONTRADICTORY_EVIDENCE,
        dependencies={WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS},
        skip_condition=lambda ctx: not ctx.get('user_wants_contradictory_search', True)
    )
    
    workflow.add_step(
        WorkflowStep.EDIT_COMPREHENSIVE_REPORT,
        dependencies={WorkflowStep.GENERATE_REPORT}
    )
    
    workflow.add_step(
        WorkflowStep.REVIEW_AND_REVISE_REPORT,
        repeat_condition=lambda ctx: ctx.get('user_wants_report_revision', False)
    )
    
    workflow.add_step(
        WorkflowStep.EXPORT_REPORT,
        dependencies={WorkflowStep.EDIT_COMPREHENSIVE_REPORT},
        skip_condition=lambda ctx: not ctx.get('user_wants_to_save', True)
    )
    
    return workflow


class WorkflowExecutor:
    """Executes workflows with step tracking and context management."""
    
    def __init__(self, workflow: WorkflowDefinition):
        self.workflow = workflow
        self.execution_history: List[StepExecution] = []
        self.context: Dict[str, Any] = {}
        self.current_step: Optional[WorkflowStep] = None
        
    def execute_step(self, step: WorkflowStep, step_handler: Callable[[WorkflowStep, Dict[str, Any]], StepResult]) -> StepExecution:
        """Execute a single workflow step."""
        execution = StepExecution(step=step, start_time=time.time())
        
        # Check if step should be skipped
        if self.workflow.should_skip(step, self.context):
            execution.result = StepResult.SKIP
            execution.end_time = time.time()
            logger.info(f"Skipping step: {step.display_name}")
            return execution
        
        # Log step start
        logger.info(f"Starting step: {step.display_name}", extra={'structured_data': {
            'event_type': 'workflow_step_start',
            'step': step.name,
            'step_display_name': step.display_name,
            'execution_count': execution.execution_count,
            'timestamp': execution.start_time
        }})
        
        try:
            # Execute the step
            result = step_handler(step, self.context)
            execution.result = result
            execution.end_time = time.time()
            
            # Log completion
            logger.info(f"Completed step: {step.display_name} ({result.value}) in {execution.duration_ms:.2f}ms", extra={'structured_data': {
                'event_type': 'workflow_step_complete',
                'step': step.name, 
                'result': result.value,
                'duration_ms': execution.duration_ms,
                'timestamp': execution.end_time
            }})
            
        except Exception as e:
            execution.result = StepResult.FAILURE
            execution.error_message = str(e)
            execution.end_time = time.time()
            logger.error(f"Step failed: {step.display_name} - {e}", extra={'structured_data': {
                'event_type': 'workflow_step_error',
                'step': step.name,
                'error': str(e),
                'timestamp': execution.end_time
            }})
        
        return execution
    
    def get_step_execution_count(self, step: WorkflowStep) -> int:
        """Get how many times a step has been executed."""
        return len([ex for ex in self.execution_history if ex.step == step])
    
    def get_last_execution(self, step: WorkflowStep) -> Optional[StepExecution]:
        """Get the last execution of a specific step."""
        executions = [ex for ex in self.execution_history if ex.step == step]
        return executions[-1] if executions else None
    
    def add_context(self, key: str, value: Any) -> None:
        """Add data to the workflow context."""
        self.context[key] = value
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """Get data from the workflow context."""
        return self.context.get(key, default)