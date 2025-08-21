"""
Refactored Workflow Orchestration Module

Modular workflow orchestrator using separated components for better maintainability.
"""

import time
import logging
from typing import Dict, Any
from .workflow_steps import (
    WorkflowStep, StepResult, WorkflowDefinition, WorkflowExecutor,
    create_default_research_workflow
)
from .workflow_agents import WorkflowAgentManager
from .workflow_state import WorkflowStateManager
from .workflow_execution import WorkflowExecutionManager
from .workflow_handlers import WorkflowStepHandlers

# Get logger for workflow operations
logger = logging.getLogger('bmlibrarian.workflow')


class RefactoredWorkflowOrchestrator:
    """Modular workflow orchestrator with separated responsibilities."""
    
    def __init__(self, config, ui, query_processor, formatter):
        self.config = config
        self.ui = ui
        self.query_processor = query_processor
        self.formatter = formatter
        
        # Initialize modular components
        self.agent_manager = WorkflowAgentManager(config, ui, query_processor)
        self.state_manager = WorkflowStateManager()
        self.execution_manager = WorkflowExecutionManager(
            config, ui, query_processor, self.agent_manager, self.state_manager
        )
        self.step_handlers = WorkflowStepHandlers(
            config, ui, self.agent_manager, self.state_manager, self.execution_manager
        )
        
        # Workflow execution system
        self.workflow_definition = None
        self.workflow_executor = None
    
    def setup_agents(self) -> bool:
        """Initialize and test all agents."""
        return self.agent_manager.setup_agents()
    
    def run_complete_workflow(self, auto_question: str = None) -> bool:
        """Execute the complete research workflow using the new step-based system."""
        workflow_start_time = time.time()
        workflow_id = f"workflow_{int(workflow_start_time)}"
        
        logger.info(f"Starting complete research workflow", extra={'structured_data': {
            'event_type': 'workflow_start',
            'workflow_id': workflow_id,
            'auto_mode': self.config.auto_mode,
            'auto_question': auto_question,
            'config': {
                'max_search_results': self.config.max_search_results,
                'timeout_minutes': self.config.timeout_minutes,
                'default_score_threshold': self.config.default_score_threshold,
                'default_min_relevance': self.config.default_min_relevance,
                'max_workers': self.config.max_workers
            },
            'timestamp': workflow_start_time
        }})
        
        try:
            # Setup agents and workflow
            setup_start = time.time()
            if not self.setup_agents():
                logger.error("Agent setup failed")
                self.ui.show_error_message("Cannot proceed without proper agent setup.")
                return False
            
            # Initialize workflow system
            self.workflow_definition = create_default_research_workflow()
            self.workflow_executor = WorkflowExecutor(self.workflow_definition)
            
            # Add auto question to context if provided
            if auto_question:
                self.workflow_executor.add_context('auto_question', auto_question)
                self.workflow_executor.add_context('auto_mode', self.config.auto_mode)
            
            logger.info(f"Agents and workflow setup completed in {(time.time() - setup_start)*1000:.2f}ms")
            
            # Start orchestrator
            self.agent_manager.start_orchestrator()
            
            # Execute workflow steps
            current_step = self.workflow_definition.steps[0]  # Start with first step
            
            while current_step:
                execution = self.workflow_executor.execute_step(
                    current_step, 
                    self.step_handlers.handle_workflow_step
                )
                self.workflow_executor.execution_history.append(execution)
                
                # Handle step result
                if execution.result == StepResult.FAILURE:
                    logger.error(f"Workflow failed at step: {current_step.display_name}")
                    self.ui.show_error_message(f"Workflow failed at: {current_step.display_name}")
                    return False
                
                elif execution.result == StepResult.USER_CANCELLED:
                    logger.info(f"Workflow cancelled by user at step: {current_step.display_name}")
                    return False
                
                elif execution.result == StepResult.REPEAT:
                    # Repeat the current step
                    continue
                
                elif execution.result == StepResult.BRANCH:
                    # Get branched step from context
                    branched_step = self.workflow_executor.get_context('branch_to_step')
                    if branched_step:
                        current_step = branched_step
                        # Clear the branch context so it doesn't repeat
                        self.workflow_executor.context.pop('branch_to_step', None)
                        continue
                
                # Move to next step
                current_step = self.workflow_definition.get_next_step(
                    current_step, 
                    self.workflow_executor.context
                )
            
            # Final summary and completion
            total_workflow_time = (time.time() - workflow_start_time) * 1000
            
            logger.info("Workflow completed successfully", extra={'structured_data': {
                'event_type': 'workflow_completion',
                'workflow_id': workflow_id,
                'success': True,
                'total_time_ms': total_workflow_time,
                'final_summary': {
                    'question': self.state_manager.current_question,
                    'documents_found': len(self.state_manager.search_results),
                    'documents_scored': len(self.state_manager.scored_documents),
                    'citations_extracted': len(self.state_manager.extracted_citations),
                    'evidence_strength': self.state_manager.final_report.evidence_strength if self.state_manager.final_report else None,
                    'counterfactual_questions': len(self.state_manager.counterfactual_analysis.counterfactual_questions) if self.state_manager.counterfactual_analysis else 0,
                    'steps_executed': len(self.workflow_executor.execution_history)
                },
                'timestamp': time.time()
            }})
            
            # Show workflow summary if we have completed the core workflow
            if self.state_manager.current_question and self.state_manager.final_report:
                self.ui.show_workflow_summary(
                    self.state_manager.current_question, 
                    len(self.state_manager.search_results), 
                    len(self.state_manager.scored_documents), 
                    len(self.state_manager.extracted_citations), 
                    self.state_manager.final_report.evidence_strength, 
                    self.state_manager.counterfactual_analysis
                )
            
            return True
            
        except KeyboardInterrupt:
            workflow_time = (time.time() - workflow_start_time) * 1000
            logger.warning(f"Workflow interrupted by user after {workflow_time:.2f}ms", extra={'structured_data': {
                'event_type': 'workflow_interruption',
                'workflow_id': workflow_id,
                'total_time_ms': workflow_time,
                'timestamp': time.time()
            }})
            self.ui.show_info_message("Workflow interrupted by user.")
            return False
        except Exception as e:
            workflow_time = (time.time() - workflow_start_time) * 1000
            logger.error(f"Workflow error after {workflow_time:.2f}ms: {e}", extra={'structured_data': {
                'event_type': 'workflow_error',
                'workflow_id': workflow_id,
                'error_type': type(e).__name__,
                'error_message': str(e),
                'total_time_ms': workflow_time,
                'timestamp': time.time()
            }})
            
            if self.config.verbose:
                import traceback
                logger.debug("Full traceback", extra={'structured_data': {
                    'event_type': 'workflow_traceback',
                    'workflow_id': workflow_id,
                    'traceback': traceback.format_exc()
                }})
                traceback.print_exc()
            
            self.ui.show_error_message(f"Workflow error: {e}")
            return False
        finally:
            self.agent_manager.stop_orchestrator()
    
    def get_workflow_state(self) -> Dict[str, Any]:
        """Get current workflow state for potential resumption."""
        base_state = self.state_manager.get_workflow_state()
        base_state['config'] = {
            'score_threshold': self.config.default_score_threshold,
            'min_relevance': self.config.default_min_relevance,
            'max_search_results': self.config.max_search_results
        }
        return base_state
    
    def clear_workflow_state(self) -> None:
        """Clear current workflow state for a fresh start."""
        self.state_manager.clear_workflow_state()