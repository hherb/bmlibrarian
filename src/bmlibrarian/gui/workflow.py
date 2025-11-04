"""
Workflow Execution Logic for BMLibrarian Research GUI

Coordinates the research workflow using modular components for interaction,
query processing, step execution, and report building.
"""

from typing import Dict, Any, Callable, Optional, List
from ..cli.workflow_steps import WorkflowStep
from ..agents import AgentFactory
from .interactive_handler import InteractiveHandler
from .query_processor import QueryProcessor
from .workflow_steps_handler import WorkflowStepsHandler
from .report_builder import ReportBuilder


def initialize_agents_in_main_thread():
    """Initialize BMLibrarian agents in the main thread to avoid signal issues."""
    try:
        print("🔧 Initializing BMLibrarian agents with config.json settings...")

        # Use AgentFactory to create all agents with proper configuration
        agents = AgentFactory.create_all_agents(auto_register=True)

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
    
    def __init__(self, agents: Dict[str, Any], config_overrides: Optional[Dict[str, Any]] = None, tab_manager: Optional[Any] = None):
        self.agents = agents
        self.config_overrides: Dict[str, Any] = config_overrides or {}
        self.tab_manager = tab_manager  # Store tab_manager reference

        # Store workflow results for tab access
        self.documents = []
        self.scored_documents = []
        self.citations = []
        self.counterfactual_analysis = None
        self.preliminary_report = ""
        self.final_report = ""
        self.last_query_text = None  # Store last query for "Add More Documents" feature

        # Store model information for report footnotes
        self.agent_model_info = {}

        # Initialize modular components
        self.interactive_handler = None
        self.query_processor = QueryProcessor()
        self.steps_handler = WorkflowStepsHandler(agents, self.config_overrides, tab_manager)
        
        # Collect agent model information for footnotes
        self._collect_agent_model_info()
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
                    dialog_manager=None, step_cards=None, tab_manager=None) -> str:
        """
        Run the complete research workflow.

        Args:
            research_question: The research question to investigate
            human_in_loop: Whether to run in interactive mode
            update_callback: Callback function for step updates (step, status, content)
            dialog_manager: Dialog manager for interactive prompts
            step_cards: Dictionary of step cards for inline editing
            tab_manager: Tab manager for accessing scoring interface

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
        self.tab_manager = tab_manager
        
        # Initialize interactive handler with step cards and tab manager
        self.interactive_handler = InteractiveHandler(step_cards, tab_manager=tab_manager)
        
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
            
            # Store the final query for export
            self.last_query_text = query_text
            
            # Always show the full query (not truncated)
            update_callback(WorkflowStep.GENERATE_AND_EDIT_QUERY, "completed",
                          f"Final query: {query_text}")
            
            # Step 3: Search Documents
            documents = self.steps_handler.execute_document_search(
                research_question, query_text, update_callback, self.interactive_mode
            )
            
            # Store documents for tab access IMMEDIATELY after getting them
            self.documents = documents
            print(f"🗂️ Workflow stored {len(documents)} documents for tab access")
            
            # Force a manual update callback to trigger tab updates since documents are now stored
            print(f"🔄 Triggering manual tab update for SEARCH_DOCUMENTS")
            update_callback(WorkflowStep.SEARCH_DOCUMENTS, "tab_update", 
                          f"Tab update: {len(documents)} documents available")
            
            # Step 4: Review Results
            if self.interactive_mode:
                # Interactive mode: Show full expandable search results interface
                if not self.interactive_handler.get_user_approval_for_search_results(documents, update_callback):
                    raise Exception("User cancelled workflow at search results review")
            else:
                # Auto mode: Show summary of search results with document list
                doc_summary = self._create_document_summary(documents)
                update_callback(WorkflowStep.REVIEW_SEARCH_RESULTS, "completed",
                              f"Found {len(documents)} documents:\n\n{doc_summary}")
            
            if self.interactive_mode:
                update_callback(WorkflowStep.REVIEW_SEARCH_RESULTS, "completed",
                              "Search results approved")
            
            # Step 5: Score Documents
            # Create progress callback for scoring (scoring agent format: current, total)
            def scoring_progress_callback(current: int, total: int):
                # Update StepCard progress
                if WorkflowStep.SCORE_DOCUMENTS in self.step_cards:
                    card = self.step_cards[WorkflowStep.SCORE_DOCUMENTS]
                    card.update_progress(current, total, f"Scoring document {current}/{total}")

                # Update Scoring tab progress bar
                if self.tab_manager:
                    from .data_updaters import DataUpdaters
                    updaters = DataUpdaters(type('obj', (), {
                        'tab_manager': self.tab_manager,
                        'page': self.dialog_manager.page if self.dialog_manager else None
                    })())
                    updaters.show_scoring_progress(visible=True, current=current, total=total)

                if self.dialog_manager and hasattr(self.dialog_manager, 'page'):
                    self.dialog_manager.page.update()
            
            scored_documents = self.steps_handler.execute_document_scoring(
                research_question, documents, update_callback, 
                progress_callback=scoring_progress_callback
            )
            
            # Store scored documents for tab access IMMEDIATELY after getting them
            self.scored_documents = scored_documents
            print(f"📊 Workflow stored {len(scored_documents)} scored documents for tab access")
            
            # Force a manual update callback to trigger tab updates since scored documents are now stored
            print(f"🔄 Triggering manual tab update for SCORE_DOCUMENTS")
            update_callback(WorkflowStep.SCORE_DOCUMENTS, "tab_update",
                          f"Tab update: {len(scored_documents)} scored documents available")
            
            # Interactive review of scored documents with potential human overrides/approvals
            score_data = {}
            if self.interactive_mode:
                score_threshold = self.config_overrides.get('score_threshold', 2.5)
                score_data = self.interactive_handler.get_user_approval_for_scores(
                    documents, scored_documents, score_threshold, update_callback
                )

                # Extract overrides and approvals
                score_overrides = score_data.get('overrides', {}) if isinstance(score_data, dict) else score_data
                score_approvals = score_data.get('approvals', {}) if isinstance(score_data, dict) else {}

                # Apply human feedback and log - no re-scoring needed
                if score_overrides or score_approvals:
                    from bmlibrarian.agents import get_human_edit_logger
                    logger = get_human_edit_logger()

                    # Apply overrides to scored_documents for further processing
                    updated_scored_documents = []
                    for doc_index, (doc, scoring_result) in enumerate(scored_documents):
                        # Make a copy of the scoring result
                        updated_result = dict(scoring_result)

                        # Apply override if present
                        if doc_index in score_overrides:
                            human_score = score_overrides[doc_index]
                            # Replace the score with human override
                            updated_result['score'] = human_score
                            updated_result['human_override'] = True
                            updated_result['original_ai_score'] = scoring_result.get('score')

                            # Log the override
                            try:
                                logger.log_document_score_edit(
                                    user_question=research_question,
                                    document=doc,
                                    ai_score=int(scoring_result.get('score', 0)),
                                    ai_reasoning=scoring_result.get('reasoning', ''),
                                    human_score=int(human_score),
                                    explicitly_approved=False
                                )
                            except Exception as e:
                                print(f"Warning: Failed to log override for document {doc_index}: {e}")

                        # Log approval if present
                        if doc_index in score_approvals:
                            updated_result['human_approved'] = True
                            try:
                                logger.log_document_score_edit(
                                    user_question=research_question,
                                    document=doc,
                                    ai_score=int(scoring_result.get('score', 0)),
                                    ai_reasoning=scoring_result.get('reasoning', ''),
                                    human_score=None,
                                    explicitly_approved=True
                                )
                            except Exception as e:
                                print(f"Warning: Failed to log approval for document {doc_index}: {e}")

                        updated_scored_documents.append((doc, updated_result))

                    # Update scored documents with human feedback applied
                    scored_documents = updated_scored_documents
                    self.scored_documents = scored_documents

                    print(f"📊 Applied {len(score_overrides)} override(s) and logged {len(score_approvals)} approval(s)")
            
            # Step 6: Extract Citations
            # Track time and document info for enhanced progress feedback
            import time
            citation_start_time = time.time()
            current_doc_info = {'title': None}  # Mutable dict to share between closures

            # Create progress callback for citation extraction (citation agent format: current, total, doc_title)
            def citation_progress_callback(current: int, total: int, doc_title: str = None):
                # Store current document title
                if doc_title:
                    current_doc_info['title'] = doc_title

                # Calculate elapsed time
                elapsed_time = time.time() - citation_start_time

                # Update StepCard progress
                if WorkflowStep.EXTRACT_CITATIONS in self.step_cards:
                    card = self.step_cards[WorkflowStep.EXTRACT_CITATIONS]
                    card.update_progress(current, total, f"Extracting citation {current}/{total}")

                # Update Citations tab progress bar with enhanced feedback
                if self.tab_manager:
                    from .data_updaters import DataUpdaters
                    updaters = DataUpdaters(type('obj', (), {
                        'tab_manager': self.tab_manager,
                        'page': self.dialog_manager.page if self.dialog_manager else None
                    })())
                    updaters.show_citations_progress(
                        visible=True,
                        current=current,
                        total=total,
                        current_doc_title=current_doc_info['title'],
                        elapsed_time=elapsed_time
                    )

                if self.dialog_manager and hasattr(self.dialog_manager, 'page'):
                    self.dialog_manager.page.update()
            
            citations = self.steps_handler.execute_citation_extraction(
                research_question, scored_documents, update_callback,
                progress_callback=citation_progress_callback
            )
            
            # Store citations for tab access IMMEDIATELY after getting them
            self.citations = citations
            print(f"📝 Workflow stored {len(citations)} citations for tab access")
            
            # Force a manual update callback to trigger tab updates since citations are now stored
            print(f"🔄 Triggering manual tab update for EXTRACT_CITATIONS")
            update_callback(WorkflowStep.EXTRACT_CITATIONS, "tab_update",
                          f"Tab update: {len(citations)} citations available")
            
            # Interactive review of citations
            if self.interactive_mode:
                citation_reviews = self.interactive_handler.get_user_approval_for_citations(citations, update_callback)
                # citation_reviews is a dict mapping citation indices to review status
                # Empty dict means "proceed with all citations" - this is valid, not a cancellation
            
            # Step 7: Generate Report
            report = self.steps_handler.execute_report_generation(
                research_question, citations, update_callback
            )
            
            # Step 8: Store preliminary report (before counterfactual analysis)
            # Get report content as string
            if hasattr(report, 'content'):
                report_content = report.content
            elif isinstance(report, str):
                report_content = report
            else:
                report_content = str(report)
            
            # Store as preliminary report for tab display
            self.preliminary_report = report_content
            print(f"📄 Stored preliminary report ({len(self.preliminary_report)} characters)")
            
            # Trigger preliminary report tab update
            update_callback(WorkflowStep.GENERATE_REPORT, "tab_update",
                          f"Preliminary report generated ({len(self.preliminary_report)} characters)")

            # Mark report generation as completed
            update_callback(WorkflowStep.GENERATE_REPORT, "completed",
                          f"Preliminary report generated ({len(self.preliminary_report)} characters)")

            # Step 9: Counterfactual Analysis

            # Check if comprehensive counterfactual analysis is enabled
            comprehensive_cf = self.config_overrides.get('comprehensive_counterfactual', False)
            print(f"🔧 Config overrides: {self.config_overrides}")
            print(f"🎛️ Comprehensive counterfactual enabled: {comprehensive_cf}")
            
            if comprehensive_cf:
                print("🧠 Performing comprehensive counterfactual analysis with literature search...")
                update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "running",
                              "Performing comprehensive counterfactual analysis with literature search...")
                counterfactual_analysis = self.steps_handler.execute_comprehensive_counterfactual_analysis(
                    report_content, citations, update_callback
                )
                print(f"🔬 Comprehensive analysis completed. Type: {type(counterfactual_analysis)}")
            else:
                print("🧠 Performing basic counterfactual analysis...")
                update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "running",
                              "Performing basic counterfactual analysis...")
                counterfactual_analysis = self.steps_handler.execute_counterfactual_analysis(
                    report_content, citations, update_callback
                )
                print(f"🔬 Basic analysis completed. Type: {type(counterfactual_analysis)}")
            
            # Store counterfactual analysis for tab access IMMEDIATELY after getting it
            self.counterfactual_analysis = counterfactual_analysis
            print(f"🧠 Workflow stored counterfactual analysis for tab access: {bool(counterfactual_analysis)}")
            
            # Force a manual update callback to trigger tab updates
            if counterfactual_analysis:
                print(f"🔄 Triggering manual tab update for PERFORM_COUNTERFACTUAL_ANALYSIS")
                update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "tab_update",
                              f"Tab update: Counterfactual analysis completed")
            
            # Steps 9-11: Complete remaining steps
            self.steps_handler.complete_remaining_steps(update_callback)
            
            # Build comprehensive final report
            print("Building final report...")
            print(f"Input report content length: {len(report_content) if report_content else 0}")
            
            final_report = self.report_builder.build_final_report(
                research_question, report_content, counterfactual_analysis,
                documents, scored_documents, citations, self.interactive_mode,
                self.agent_model_info
            )
            
            # Store final report for tab access
            self.final_report = final_report if final_report else ""
            print(f"Final report built, length: {len(final_report) if final_report else 0}")
            
            # Debug report content to see if it's being truncated
            if final_report:
                print(f"📝 Final report preview: ...{final_report[-200:]}")
                if len(report_content) > 0 and len(final_report) < len(report_content):
                    print(f"⚠️ WARNING: Final report is shorter than input report content!")
                    print(f"Input: {len(report_content)} chars, Output: {len(final_report)} chars")
            
            # Trigger report tab update
            if final_report:
                print(f"🔄 Triggering manual tab update for EXPORT_REPORT")
                update_callback(WorkflowStep.EXPORT_REPORT, "tab_update",
                              f"Tab update: Final report ready ({len(final_report)} characters)")
            
            print(f"Workflow summary: {self.get_workflow_summary()}")
            return final_report
            
        except Exception as e:
            raise Exception(f"Workflow execution failed: {str(e)}")
    
    def _create_document_summary(self, documents: List[Dict]) -> str:
        """Create a summary of documents for display in auto mode.
        
        Args:
            documents: List of document dictionaries
            
        Returns:
            Formatted string summary of documents
        """
        if not documents:
            return "No documents found."
        
        summary_lines = []
        for i, doc in enumerate(documents[:10], 1):  # Show first 10 documents
            title = doc.get('title', 'Untitled Document')[:80]
            year = doc.get('year', 'Unknown')
            summary_lines.append(f"{i}. {title} ({year})")
        
        if len(documents) > 10:
            summary_lines.append(f"... and {len(documents) - 10} more documents")
        
        return "\n".join(summary_lines)
    
    def _collect_agent_model_info(self):
        """Collect model information from all agents for report footnotes."""
        try:
            for agent_name, agent in self.agents.items():
                if agent_name == 'orchestrator':
                    continue
                    
                agent_info = {
                    'model': getattr(agent, 'model', 'Unknown'),
                    'host': getattr(agent, 'host', 'Unknown'),
                    'temperature': getattr(agent, 'temperature', 'Unknown'),
                    'top_p': getattr(agent, 'top_p', 'Unknown')
                }
                
                # Map agent names to workflow steps
                workflow_step_map = {
                    'query_agent': 'Query Generation',
                    'scoring_agent': 'Document Scoring',
                    'citation_agent': 'Citation Extraction',
                    'reporting_agent': 'Report Generation',
                    'counterfactual_agent': 'Counterfactual Analysis',
                    'editor_agent': 'Report Editing'
                }
                
                step_name = workflow_step_map.get(agent_name, agent_name)
                self.agent_model_info[step_name] = agent_info
                
            print(f"Collected model info for {len(self.agent_model_info)} agents")
            
        except Exception as e:
            print(f"Error collecting agent model info: {e}")
            self.agent_model_info = {}
    
    def get_workflow_summary(self) -> Dict[str, Any]:
        """Get a summary of workflow execution results.
        
        Returns:
            Dictionary with workflow statistics and results
        """
        return {
            'documents_found': len(self.documents),
            'documents_scored': len(self.scored_documents),
            'citations_extracted': len(self.citations),
            'report_length': len(self.final_report),
            'counterfactual_analysis_performed': bool(self.counterfactual_analysis),
            'interactive_mode': getattr(self, 'interactive_mode', False),
            'agent_models': self.agent_model_info
        }
    
    def export_comprehensive_data(self, research_question: str, query_text: str = None) -> Dict[str, Any]:
        """Export comprehensive workflow data for full reconstruction.
        
        Args:
            research_question: The original research question
            query_text: The generated PostgreSQL query (if available)
            
        Returns:
            Complete workflow data dictionary suitable for JSON serialization
        """
        from datetime import datetime
        import json
        
        def serialize_object(obj):
            """Convert objects to JSON-serializable format."""
            if hasattr(obj, '__dict__'):
                # Object with attributes - convert to dict
                result = {}
                for key, value in vars(obj).items():
                    try:
                        # Test if value is JSON serializable
                        json.dumps(value)
                        result[key] = value
                    except (TypeError, ValueError):
                        # Convert non-serializable values to string
                        result[key] = str(value)
                return result
            else:
                return str(obj)
        
        # Extract scored documents with proper structure
        scored_documents_data = []
        for doc, score_result in self.scored_documents:
            scored_documents_data.append({
                'document': doc,
                'score_result': score_result
            })
        
        # Handle counterfactual analysis with nested structure extraction
        counterfactual_data = None
        if self.counterfactual_analysis:
            try:
                if isinstance(self.counterfactual_analysis, dict):
                    # Complex nested structure - clean it up
                    counterfactual_data = {}
                    
                    # Copy basic fields
                    for key, value in self.counterfactual_analysis.items():
                        if key not in ['contradictory_evidence', 'contradictory_citations']:
                            try:
                                json.dumps(value)
                                counterfactual_data[key] = value
                            except (TypeError, ValueError):
                                counterfactual_data[key] = str(value)
                    
                    # Handle contradictory evidence with proper extraction
                    contradictory_evidence = self.counterfactual_analysis.get('contradictory_evidence', [])
                    if contradictory_evidence:
                        evidence_data = []
                        for evidence_item in contradictory_evidence:
                            if isinstance(evidence_item, dict) and 'document' in evidence_item:
                                # Extract document and metadata
                                evidence_data.append({
                                    'document': evidence_item['document'],
                                    'score': evidence_item.get('score'),
                                    'reasoning': evidence_item.get('reasoning'),
                                    'query_info': evidence_item.get('query_info')
                                })
                            else:
                                evidence_data.append(serialize_object(evidence_item))
                        counterfactual_data['contradictory_evidence'] = evidence_data
                    
                    # Handle contradictory citations with proper extraction
                    contradictory_citations = self.counterfactual_analysis.get('contradictory_citations', [])
                    if contradictory_citations:
                        citations_data = []
                        for citation_item in contradictory_citations:
                            if isinstance(citation_item, dict) and 'citation' in citation_item:
                                # Extract citation and metadata
                                citation_data = {
                                    'citation': serialize_object(citation_item['citation']),
                                    'original_claim': citation_item.get('original_claim'),
                                    'counterfactual_question': citation_item.get('counterfactual_question'),
                                    'document_score': citation_item.get('document_score'),
                                    'score_reasoning': citation_item.get('score_reasoning')
                                }
                                citations_data.append(citation_data)
                            else:
                                citations_data.append(serialize_object(citation_item))
                        counterfactual_data['contradictory_citations'] = citations_data
                else:
                    counterfactual_data = serialize_object(self.counterfactual_analysis)
            except Exception as e:
                print(f"Error serializing counterfactual analysis: {e}")
                counterfactual_data = {"error": f"Serialization failed: {str(e)}"}
        
        # Serialize citations properly
        citations_data = []
        for citation in self.citations:
            citations_data.append(serialize_object(citation))
        
        # Build comprehensive export data
        export_data = {
            'metadata': {
                'export_timestamp': datetime.now().isoformat(),
                'bmlibrarian_version': 'GUI-2024',
                'workflow_type': 'multi_agent_research',
                'export_format_version': '1.0'
            },
            'workflow_input': {
                'research_question': research_question,
                'generated_query': query_text,
                'config_overrides': self.config_overrides,
                'interactive_mode': getattr(self, 'interactive_mode', False)
            },
            'workflow_execution': {
                'steps_completed': len(self.workflow_steps),
                'workflow_steps': [step.value for step in self.workflow_steps],
                'agent_model_info': self.agent_model_info
            },
            'search_results': {
                'total_documents_found': len(self.documents),
                'documents': self.documents,
                'search_metadata': {
                    'search_timestamp': datetime.now().isoformat(),
                    'database_queried': 'bmlibrarian_knowledgebase'
                }
            },
            'scoring_results': {
                'total_documents_scored': len(self.scored_documents),
                'scored_documents': scored_documents_data,
                'scoring_threshold': self.config_overrides.get('score_threshold', 2.5),
                'scoring_metadata': {
                    'scoring_agent_model': self.agent_model_info.get('Document Scoring', {}).get('model', 'Unknown')
                }
            },
            'citation_extraction': {
                'total_citations_extracted': len(self.citations),
                'citations': citations_data,
                'extraction_metadata': {
                    'citation_agent_model': self.agent_model_info.get('Citation Extraction', {}).get('model', 'Unknown')
                }
            },
            'report_generation': {
                'final_report_content': self.final_report,
                'report_length': len(self.final_report) if self.final_report else 0,
                'generation_metadata': {
                    'reporting_agent_model': self.agent_model_info.get('Report Generation', {}).get('model', 'Unknown')
                }
            },
            'counterfactual_analysis': {
                'analysis_performed': bool(self.counterfactual_analysis),
                'analysis_type': 'comprehensive' if isinstance(self.counterfactual_analysis, dict) and 
                                self.counterfactual_analysis.get('contradictory_evidence') else 'basic',
                'analysis_data': counterfactual_data,
                'analysis_metadata': {
                    'counterfactual_agent_model': self.agent_model_info.get('Counterfactual Analysis', {}).get('model', 'Unknown')
                }
            },
            'workflow_summary': self.get_workflow_summary()
        }
        
        return export_data
