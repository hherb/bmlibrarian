"""
Workflow Execution Logic for BMLibrarian Research GUI

Coordinates the research workflow using modular components for interaction,
query processing, step execution, and report building.
"""

from typing import Dict, Any, Callable, Optional
from ..cli.workflow_steps import WorkflowStep
from ..agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent,
    ReportingAgent, CounterfactualAgent, EditorAgent, AgentOrchestrator
)
from ..config import get_config, get_model, get_agent_config
from .interactive_handler import InteractiveHandler
from .query_processor import QueryProcessor
from .workflow_steps_handler import WorkflowStepsHandler
from .report_builder import ReportBuilder


def filter_agent_config(agent_config: Dict[str, Any], allowed_params: set) -> Dict[str, Any]:
    """Filter agent configuration to only include allowed parameters."""
    return {k: v for k, v in agent_config.items() if k in allowed_params}


def initialize_agents_in_main_thread():
    """Initialize BMLibrarian agents in the main thread to avoid signal issues."""
    try:
        print("🔧 Initializing BMLibrarian agents with config.json settings...")
        
        # Get configuration
        config = get_config()
        ollama_config = config.get_ollama_config()
        
        # Create orchestrator
        orchestrator = AgentOrchestrator(max_workers=2)
        
        # Define allowed parameters for each agent type
        allowed_params = {
            'query': {'temperature', 'top_p', 'callback', 'show_model_info'},
            'scoring': {'temperature', 'top_p', 'callback', 'show_model_info'},
            'citation': {'temperature', 'top_p', 'callback', 'show_model_info'},
            'reporting': {'temperature', 'top_p', 'callback', 'show_model_info'},
            'counterfactual': {'temperature', 'top_p', 'callback', 'show_model_info'},
            'editor': {'temperature', 'top_p', 'callback', 'show_model_info'}
        }
        
        # Create agents with properly filtered configuration
        agents = {
            'query_agent': QueryAgent(
                model=get_model('query_agent'),
                host=ollama_config.get('host', 'http://localhost:11434'),
                orchestrator=orchestrator,
                **filter_agent_config(get_agent_config('query'), allowed_params['query'])
            ),
            'scoring_agent': DocumentScoringAgent(
                model=get_model('scoring_agent'),
                host=ollama_config.get('host', 'http://localhost:11434'),
                orchestrator=orchestrator,
                **filter_agent_config(get_agent_config('scoring'), allowed_params['scoring'])
            ),
            'citation_agent': CitationFinderAgent(
                model=get_model('citation_agent'),
                host=ollama_config.get('host', 'http://localhost:11434'),
                orchestrator=orchestrator,
                **filter_agent_config(get_agent_config('citation'), allowed_params['citation'])
            ),
            'reporting_agent': ReportingAgent(
                model=get_model('reporting_agent'),
                host=ollama_config.get('host', 'http://localhost:11434'),
                orchestrator=orchestrator,
                **filter_agent_config(get_agent_config('reporting'), allowed_params['reporting'])
            ),
            'counterfactual_agent': CounterfactualAgent(
                model=get_model('counterfactual_agent'),
                host=ollama_config.get('host', 'http://localhost:11434'),
                orchestrator=orchestrator,
                **filter_agent_config(get_agent_config('counterfactual'), allowed_params['counterfactual'])
            ),
            'editor_agent': EditorAgent(
                model=get_model('editor_agent'),
                host=ollama_config.get('host', 'http://localhost:11434'),
                orchestrator=orchestrator,
                **filter_agent_config(get_agent_config('editor'), allowed_params['editor'])
            ),
            'orchestrator': orchestrator
        }
        
        # Print which models are being used
        for agent_name, agent in agents.items():
            if hasattr(agent, 'model') and agent_name != 'orchestrator':
                print(f"🤖 {agent_name} using model: {agent.model}")
        
        print("✅ Agents initialized successfully in main thread")
        return agents
        
    except Exception as e:
        print(f"❌ Failed to initialize agents in main thread: {e}")
        return None


class WorkflowExecutor:
    """Executes the research workflow using real BMLibrarian agents.
    
    Coordinates the workflow through modular components:
    - InteractiveHandler: Manages user interactions and inline editing
    - QueryProcessor: Handles query cleaning and validation
    - WorkflowStepsHandler: Executes individual workflow steps
    - ReportBuilder: Constructs comprehensive final reports
    
    In interactive mode, users can review and edit queries, results, and parameters
    at key workflow steps before proceeding.
    """
    
    def __init__(self, agents: Dict[str, Any], config_overrides: Optional[Dict[str, Any]] = None):
        self.agents = agents
        self.config_overrides: Dict[str, Any] = config_overrides or {}
        
        # Initialize modular components
        self.interactive_handler = None
        self.query_processor = QueryProcessor()
        self.steps_handler = WorkflowStepsHandler(agents, config_overrides)
        self.workflow_steps = [
            WorkflowStep.COLLECT_RESEARCH_QUESTION,
            WorkflowStep.GENERATE_AND_EDIT_QUERY,
            WorkflowStep.SEARCH_DOCUMENTS,
            WorkflowStep.REVIEW_SEARCH_RESULTS,
            WorkflowStep.SCORE_DOCUMENTS,
            WorkflowStep.EXTRACT_CITATIONS,
            WorkflowStep.GENERATE_REPORT,
            WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS,
            WorkflowStep.SEARCH_CONTRADICTORY_EVIDENCE,
            WorkflowStep.EDIT_COMPREHENSIVE_REPORT,
            WorkflowStep.EXPORT_REPORT
        ]
        self.report_builder = ReportBuilder(self.workflow_steps)
        
        # Legacy compatibility
        self.dialog_manager = None
        self.step_cards = None
    
    def run_workflow(self, research_question: str, human_in_loop: bool, 
                    update_callback: Callable[[WorkflowStep, str, str], None],
                    dialog_manager=None, step_cards=None) -> str:
        """
        Run the complete research workflow.
        
        Args:
            research_question: The research question to investigate
            human_in_loop: Whether to run in interactive mode
            update_callback: Callback function for step updates (step, status, content)
            dialog_manager: Dialog manager for interactive prompts
            step_cards: Dictionary of step cards for inline editing
            
        Returns:
            Final report content as string
        """
        if not self.agents:
            raise Exception("Agents not initialized")
        
        # Store interactive mode setting and callback
        self.interactive_mode = human_in_loop
        self.update_callback = update_callback
        self.dialog_manager = dialog_manager
        self.step_cards = step_cards
        
        # Initialize interactive handler with step cards
        self.interactive_handler = InteractiveHandler(step_cards)
        
        try:
            # Step 1: Research Question Collection
            update_callback(WorkflowStep.COLLECT_RESEARCH_QUESTION, "completed", 
                          f"Research Question: {research_question}")
            
            # Step 2: Generate Query
            query_text = self.steps_handler.execute_query_generation(research_question, update_callback)
            
            # In interactive mode, allow user to review and edit the query
            if self.interactive_mode:
                final_query = self.interactive_handler.get_user_approval_for_query(
                    query_text, research_question, update_callback, self.query_processor.clean_user_query
                )
                if final_query is None:
                    raise Exception("User cancelled workflow at query review")
                query_text = final_query
            
            # Always show the full query (not truncated)
            update_callback(WorkflowStep.GENERATE_AND_EDIT_QUERY, "completed",
                          f"Final query: {query_text}")
            
            # Step 3: Search Documents
            documents = self.steps_handler.execute_document_search(
                research_question, query_text, update_callback, self.interactive_mode
            )
            
            # Step 4: Review Results
            if self.interactive_mode:
                if not self.interactive_handler.get_user_approval_for_search_results(documents, update_callback):
                    raise Exception("User cancelled workflow at search results review")
            
            update_callback(WorkflowStep.REVIEW_SEARCH_RESULTS, "completed",
                          "Search results approved")
            
            # Step 5: Score Documents
            scored_documents = self.steps_handler.execute_document_scoring(
                research_question, documents, update_callback
            )
            
            # Interactive review of scored documents with potential human overrides
            score_overrides = {}
            if self.interactive_mode:
                score_threshold = self.config_overrides.get('score_threshold', 2.5)
                score_overrides = self.interactive_handler.get_user_approval_for_scores(
                    documents, scored_documents, score_threshold, update_callback
                )
                
                # If we have overrides, re-run scoring with human scores
                if score_overrides:
                    print(f"Re-scoring documents with {len(score_overrides)} human overrides...")
                    scored_documents = self.steps_handler.execute_document_scoring(
                        research_question, documents, update_callback, score_overrides
                    )
            
            # Step 6: Extract Citations
            citations = self.steps_handler.execute_citation_extraction(
                research_question, scored_documents, update_callback
            )
            
            # Interactive review of citations
            if self.interactive_mode:
                if not self.interactive_handler.get_user_approval_for_citations(citations, update_callback):
                    raise Exception("User cancelled workflow at citation review")
            
            # Step 7: Generate Report
            report = self.steps_handler.execute_report_generation(
                research_question, citations, update_callback
            )
            
            # Step 8: Counterfactual Analysis
            # Get report content as string
            if hasattr(report, 'content'):
                report_content = report.content
            elif isinstance(report, str):
                report_content = report
            else:
                report_content = str(report)
                
            counterfactual_analysis = self.steps_handler.execute_counterfactual_analysis(
                report_content, citations, update_callback
            )
            
            # Steps 9-11: Complete remaining steps
            self.steps_handler.complete_remaining_steps(update_callback)
            
            # Build comprehensive final report
            print("Building final report...")
            final_report = self.report_builder.build_final_report(
                research_question, report_content, counterfactual_analysis,
                documents, scored_documents, citations, self.interactive_mode
            )
            
            print(f"Final report built, length: {len(final_report) if final_report else 0}")
            return final_report
            
        except Exception as e:
            raise Exception(f"Workflow execution failed: {str(e)}")
    
    
    
    
    
    
    
    
    
    
