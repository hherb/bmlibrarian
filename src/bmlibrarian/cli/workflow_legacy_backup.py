"""
Workflow Orchestration Module

Handles the main research workflow coordination, agent setup, and state management.
This module now provides backwards compatibility while using the refactored modular components.
"""

import time
import logging
from typing import List, Dict, Any, Tuple, Optional
from bmlibrarian.agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent, 
    ReportingAgent, CounterfactualAgent, EditorAgent, AgentOrchestrator, 
    Citation, Report, CounterfactualAnalysis, EditedReport
)
from .workflow_steps import (
    WorkflowStep, StepResult, WorkflowDefinition, WorkflowExecutor,
    create_default_research_workflow
)
from .workflow_refactored import RefactoredWorkflowOrchestrator

# Get logger for workflow operations
logger = logging.getLogger('bmlibrarian.workflow')


class WorkflowOrchestrator:
    """Orchestrates the complete research workflow with agent coordination.
    
    This class now delegates to the refactored modular implementation for better maintainability
    while preserving the original interface for backwards compatibility.
    """
    
    def __init__(self, config, ui, query_processor, formatter):
        # Initialize the refactored orchestrator
        self._refactored_orchestrator = RefactoredWorkflowOrchestrator(
            config, ui, query_processor, formatter
        )
        
        # Expose compatibility properties
        self.config = config
        self.ui = ui
        self.query_processor = query_processor
        self.formatter = formatter
    
    def setup_agents(self) -> bool:
        """Initialize and test all agents."""
        return self._refactored_orchestrator.setup_agents()
    
    def run_complete_workflow(self, auto_question: str = None) -> bool:
        """Execute the complete research workflow."""
        return self._refactored_orchestrator.run_complete_workflow(auto_question)
    
    def get_workflow_state(self) -> Dict[str, Any]:
        """Get current workflow state for potential resumption."""
        return self._refactored_orchestrator.get_workflow_state()
    
    def clear_workflow_state(self) -> None:
        """Clear current workflow state for a fresh start."""
        self._refactored_orchestrator.clear_workflow_state()
    
    # Legacy properties for backwards compatibility
    @property
    def current_question(self) -> Optional[str]:
        return self._refactored_orchestrator.state_manager.current_question
    
    @property
    def search_results(self) -> List[Dict[str, Any]]:
        return self._refactored_orchestrator.state_manager.search_results
    
    @property
    def scored_documents(self) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        return self._refactored_orchestrator.state_manager.scored_documents
    
    @property
    def extracted_citations(self) -> List[Citation]:
        return self._refactored_orchestrator.state_manager.extracted_citations
    
    @property
    def final_report(self) -> Optional[Report]:
        return self._refactored_orchestrator.state_manager.final_report
    
    @property
    def counterfactual_analysis(self) -> Optional[CounterfactualAnalysis]:
        return self._refactored_orchestrator.state_manager.counterfactual_analysis
    
    @property
    def contradictory_evidence(self) -> Optional[Dict[str, Any]]:
        return self._refactored_orchestrator.state_manager.contradictory_evidence
    
    @property
    def comprehensive_report(self) -> Optional[EditedReport]:
        return self._refactored_orchestrator.state_manager.comprehensive_report
    
    # Agent properties for backwards compatibility
    @property
    def orchestrator(self) -> Optional[AgentOrchestrator]:
        return self._refactored_orchestrator.agent_manager.orchestrator
    
    @property
    def query_agent(self) -> Optional[QueryAgent]:
        return self._refactored_orchestrator.agent_manager.query_agent
    
    @property
    def scoring_agent(self) -> Optional[DocumentScoringAgent]:
        return self._refactored_orchestrator.agent_manager.scoring_agent
    
    @property
    def citation_agent(self) -> Optional[CitationFinderAgent]:
        return self._refactored_orchestrator.agent_manager.citation_agent
    
    @property
    def reporting_agent(self) -> Optional[ReportingAgent]:
        return self._refactored_orchestrator.agent_manager.reporting_agent
    
    @property
    def counterfactual_agent(self) -> Optional[CounterfactualAgent]:
        return self._refactored_orchestrator.agent_manager.counterfactual_agent
    
    @property
    def editor_agent(self) -> Optional[EditorAgent]:
        return self._refactored_orchestrator.agent_manager.editor_agent


# All legacy method implementations have been moved to the modular components
# The refactored architecture provides better separation of concerns and maintainability
        """Test all service connections."""
        self.ui.show_progress_message("Testing service connections...")
        
        # Test database connection
        db_connected = self.query_processor.test_database_connection()
        status_db = "✅ Connected" if db_connected else "❌ Failed"
        print(f"   Database: {status_db}")
        
        # Test Ollama connections
        scoring_connected = self.scoring_agent.test_connection()
        status_scoring = "✅ Connected" if scoring_connected else "❌ Failed"
        print(f"   Scoring Agent (Ollama): {status_scoring}")
        
        citation_connected = self.citation_agent.test_connection()
        status_citation = "✅ Connected" if citation_connected else "❌ Failed"
        print(f"   Citation Agent (Ollama): {status_citation}")
        
        reporting_connected = self.reporting_agent.test_connection()
        status_reporting = "✅ Connected" if reporting_connected else "❌ Failed"
        print(f"   Reporting Agent (Ollama): {status_reporting}")
        
        counterfactual_connected = self.counterfactual_agent.test_connection()
        status_counterfactual = "✅ Connected" if counterfactual_connected else "❌ Failed"
        print(f"   Counterfactual Agent (Ollama): {status_counterfactual}")
        
        editor_connected = self.editor_agent.test_connection()
        status_editor = "✅ Connected" if editor_connected else "❌ Failed"
        print(f"   Editor Agent (Ollama): {status_editor}")
        
        # Check if all critical services are available
        if not (db_connected and scoring_connected and citation_connected and reporting_connected and counterfactual_connected and editor_connected):
            self.ui.show_warning_message("Some AI services are unavailable. Please ensure:")
            print("   - Ollama is running: ollama serve")
            print("   - Required models are installed:")
            print("     ollama pull gpt-oss:20b")
            print("     ollama pull medgemma4B_it_q8:latest")
            return False
        
        self.ui.show_success_message("All services connected and ready!")
        return True
    
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
            self.orchestrator.start_processing()
            
            # Execute workflow steps
            current_step = self.workflow_definition.steps[0]  # Start with first step
            
            while current_step:
                execution = self.workflow_executor.execute_step(
                    current_step, 
                    self._handle_workflow_step
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
                    'question': self.current_question,
                    'documents_found': len(self.search_results),
                    'documents_scored': len(self.scored_documents),
                    'citations_extracted': len(self.extracted_citations),
                    'evidence_strength': self.final_report.evidence_strength if self.final_report else None,
                    'counterfactual_questions': len(self.counterfactual_analysis.counterfactual_questions) if self.counterfactual_analysis else 0,
                    'steps_executed': len(self.workflow_executor.execution_history)
                },
                'timestamp': time.time()
            }})
            
            # Show workflow summary if we have completed the core workflow
            if self.current_question and self.final_report:
                self.ui.show_workflow_summary(
                    self.current_question, len(self.search_results), len(self.scored_documents), 
                    len(self.extracted_citations), self.final_report.evidence_strength, self.counterfactual_analysis
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
            if self.orchestrator:
                logger.debug(f"Stopping orchestrator for workflow {workflow_id}")
                self.orchestrator.stop_processing()
    
    def _handle_workflow_step(self, step: WorkflowStep, context: Dict[str, Any]) -> StepResult:
        """Handle execution of a workflow step."""
        try:
            if step == WorkflowStep.COLLECT_RESEARCH_QUESTION:
                return self._handle_collect_research_question(context)
            
            elif step == WorkflowStep.GENERATE_AND_EDIT_QUERY:
                return self._handle_generate_and_edit_query(context)
            
            elif step == WorkflowStep.SEARCH_DOCUMENTS:
                return self._handle_search_documents(context)
            
            elif step == WorkflowStep.REVIEW_SEARCH_RESULTS:
                return self._handle_review_search_results(context)
            
            elif step == WorkflowStep.SCORE_DOCUMENTS:
                return self._handle_score_documents(context)
            
            elif step == WorkflowStep.EXTRACT_CITATIONS:
                return self._handle_extract_citations(context)
            
            elif step == WorkflowStep.GENERATE_REPORT:
                return self._handle_generate_report(context)
            
            elif step == WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS:
                return self._handle_counterfactual_analysis(context)
            
            elif step == WorkflowStep.SEARCH_CONTRADICTORY_EVIDENCE:
                return self._handle_search_contradictory_evidence(context)
            
            elif step == WorkflowStep.EDIT_COMPREHENSIVE_REPORT:
                return self._handle_edit_comprehensive_report(context)
            
            elif step == WorkflowStep.EXPORT_REPORT:
                return self._handle_export_report(context)
            
            elif step == WorkflowStep.REFINE_QUERY:
                return self._handle_refine_query(context)
            
            elif step == WorkflowStep.ADJUST_SCORING_THRESHOLDS:
                return self._handle_adjust_scoring_thresholds(context)
            
            elif step == WorkflowStep.REQUEST_MORE_CITATIONS:
                return self._handle_request_more_citations(context)
            
            elif step == WorkflowStep.REVIEW_AND_REVISE_REPORT:
                return self._handle_review_and_revise_report(context)
            
            else:
                logger.error(f"Unknown workflow step: {step}")
                return StepResult.FAILURE
                
        except Exception as e:
            logger.error(f"Error executing step {step}: {e}")
            return StepResult.FAILURE
    
    def _handle_collect_research_question(self, context: Dict[str, Any]) -> StepResult:
        """Handle collecting the research question."""
        auto_question = context.get('auto_question')
        auto_mode = context.get('auto_mode', False)
        
        if auto_mode and auto_question:
            question = auto_question
            print(f"\n🔬 Auto-mode research question: {question}")
            logger.info(f"Using auto-mode question: {question}")
        else:
            question = self.ui.get_research_question()
            if not question:
                if auto_mode:
                    logger.error("Auto mode requires a research question")
                    self.ui.show_error_message("Auto mode requires a research question to be provided.")
                else:
                    logger.info("User cancelled question input")
                return StepResult.USER_CANCELLED
            logger.info(f"User provided question: {question}")
        
        self.current_question = question
        context['research_question'] = question
        return StepResult.SUCCESS
    
    def _handle_generate_and_edit_query(self, context: Dict[str, Any]) -> StepResult:
        """Handle query generation and editing."""
        question = context.get('research_question')
        if not question:
            return StepResult.FAILURE
        
        # For now, the query generation is handled within the search process
        # This step serves as a placeholder for future query editing UI
        logger.info(f"Query generation step for question: {question}")
        return StepResult.SUCCESS
    
    def _handle_search_documents(self, context: Dict[str, Any]) -> StepResult:
        """Handle document search."""
        question = context.get('research_question')
        if not question:
            return StepResult.FAILURE
        
        documents = self._execute_document_search(question)
        if not documents:
            logger.error("No documents found in search")
            self.ui.show_error_message("Cannot proceed without documents.")
            context['no_documents_found'] = True
            
            # In auto mode, we can't refine the query, so we fail the workflow
            if self.config.auto_mode:
                logger.error("Auto mode: No documents found and cannot refine query")
                self.ui.show_error_message("Auto mode failed: No documents found for the research question.")
                self.ui.show_info_message("Suggestions for better results:")
                self.ui.show_info_message("• Try more general terms in your research question")
                self.ui.show_info_message("• Use different medical terminology or synonyms")
                self.ui.show_info_message("• Check for spelling errors in medical terms")
                self.ui.show_info_message("• Run in interactive mode to refine the query")
                return StepResult.FAILURE
            else:
                # In interactive mode, branch to query refinement
                context['branch_to_step'] = WorkflowStep.REFINE_QUERY
                return StepResult.BRANCH
        
        self.search_results = documents
        context['documents'] = documents
        return StepResult.SUCCESS
    
    def _handle_review_search_results(self, context: Dict[str, Any]) -> StepResult:
        """Handle search results review."""
        documents = context.get('documents', self.search_results)
        
        reviewed_documents = self._process_search_results(documents)
        if not reviewed_documents:
            logger.error("Document review cancelled or failed")
            context['user_wants_different_search'] = True
            
            # In auto mode, we can't refine the query, so we fail the workflow
            if self.config.auto_mode:
                logger.error("Auto mode: Document review failed and cannot refine query")
                self.ui.show_error_message("Auto mode failed: Document review was unsuccessful.")
                self.ui.show_info_message("Run in interactive mode to review and refine search results.")
                return StepResult.FAILURE
            else:
                # In interactive mode, branch to query refinement
                context['branch_to_step'] = WorkflowStep.REFINE_QUERY
                return StepResult.BRANCH
        
        self.search_results = reviewed_documents
        context['documents'] = reviewed_documents
        return StepResult.SUCCESS
    
    def _handle_score_documents(self, context: Dict[str, Any]) -> StepResult:
        """Handle document scoring."""
        question = context.get('research_question')
        documents = context.get('documents', self.search_results)
        
        scored_docs = self._execute_document_scoring(question, documents)
        if not scored_docs:
            logger.error("Document scoring failed")
            self.ui.show_error_message("Cannot proceed without scored documents.")
            return StepResult.FAILURE
        
        self.scored_documents = scored_docs
        context['scored_documents'] = scored_docs
        return StepResult.SUCCESS
    
    def _handle_extract_citations(self, context: Dict[str, Any]) -> StepResult:
        """Handle citation extraction."""
        question = context.get('research_question')
        scored_docs = context.get('scored_documents', self.scored_documents)
        
        citations = self._execute_citation_extraction(question, scored_docs)
        if not citations:
            logger.error("Citation extraction failed")
            self.ui.show_error_message("Cannot proceed without citations.")
            context['insufficient_citations'] = True
            return StepResult.BRANCH  # This will trigger threshold adjustment
        
        self.extracted_citations = citations
        context['citations'] = citations
        return StepResult.SUCCESS
    
    def _handle_generate_report(self, context: Dict[str, Any]) -> StepResult:
        """Handle report generation."""
        question = context.get('research_question')
        citations = context.get('citations', self.extracted_citations)
        
        report = self._execute_report_generation(question, citations)
        if not report:
            logger.error("Report generation failed")
            self.ui.show_error_message("Report generation failed.")
            context['insufficient_evidence_for_report'] = True
            return StepResult.BRANCH  # This will trigger more citation requests
        
        self.final_report = report
        context['report'] = report
        return StepResult.SUCCESS
    
    def _handle_counterfactual_analysis(self, context: Dict[str, Any]) -> StepResult:
        """Handle counterfactual analysis."""
        report = context.get('report', self.final_report)
        
        counterfactual_analysis = self._execute_counterfactual_analysis(report)
        if counterfactual_analysis:
            self.counterfactual_analysis = counterfactual_analysis
            context['counterfactual_analysis'] = counterfactual_analysis
            logger.info(f"Counterfactual analysis completed: {len(counterfactual_analysis.counterfactual_questions)} questions generated")
        else:
            logger.info("Counterfactual analysis skipped or failed")
        
        return StepResult.SUCCESS  # This step can fail but workflow continues
    
    def _handle_search_contradictory_evidence(self, context: Dict[str, Any]) -> StepResult:
        """Handle searching for contradictory evidence."""
        # This is handled within the counterfactual analysis method
        return StepResult.SUCCESS
    
    def _handle_edit_comprehensive_report(self, context: Dict[str, Any]) -> StepResult:
        """Handle comprehensive report editing."""
        report = context.get('report', self.final_report)
        question = context.get('research_question')
        citations = context.get('citations', self.extracted_citations)
        counterfactual_analysis = context.get('counterfactual_analysis', self.counterfactual_analysis)
        
        comprehensive_report = self._execute_comprehensive_report_editing(
            report, question, citations, counterfactual_analysis
        )
        if comprehensive_report:
            self.comprehensive_report = comprehensive_report
            context['comprehensive_report'] = comprehensive_report
            logger.info(f"Comprehensive report generated: {comprehensive_report.word_count} words")
        else:
            logger.info("Comprehensive report editing failed, using original report")
        
        return StepResult.SUCCESS
    
    def _handle_export_report(self, context: Dict[str, Any]) -> StepResult:
        """Handle report export."""
        if self.ui.get_save_report_choice():
            comprehensive_report = context.get('comprehensive_report', self.comprehensive_report)
            report = context.get('report', self.final_report)
            question = context.get('research_question')
            
            # Use comprehensive report if available, otherwise use original report
            report_to_save = comprehensive_report if comprehensive_report else report
            filename = self.formatter.save_comprehensive_report_to_file(
                report_to_save, question, self.counterfactual_analysis, self.contradictory_evidence
            )
            logger.info(f"Report saved to file: {filename}")
        else:
            logger.info("Report saving skipped")
        
        return StepResult.SUCCESS
    
    def _handle_refine_query(self, context: Dict[str, Any]) -> StepResult:
        """Handle query refinement."""
        question = context.get('research_question')
        if not question:
            return StepResult.FAILURE
            
        # For now, just try the search again or ask for user input to refine
        logger.info("Query refinement step - asking user to refine the question")
        
        if self.config.auto_mode:
            # In auto mode, we can't refine, so fail
            logger.error("Auto mode: cannot refine query, failing")
            return StepResult.FAILURE
        else:
            # Ask user for a refined question
            self.ui.show_info_message("Please refine your research question to get better search results:")
            refined_question = self.ui.get_research_question()
            if refined_question:
                self.current_question = refined_question
                context['research_question'] = refined_question
                context['branch_to_step'] = WorkflowStep.SEARCH_DOCUMENTS
                logger.info(f"Query refined to: {refined_question}")
                return StepResult.BRANCH
            else:
                logger.info("User cancelled query refinement")
                return StepResult.USER_CANCELLED
    
    def _handle_adjust_scoring_thresholds(self, context: Dict[str, Any]) -> StepResult:
        """Handle scoring threshold adjustment."""
        # This would be implemented to allow threshold adjustments
        logger.info("Scoring threshold adjustment step - not yet implemented") 
        context['branch_to_step'] = WorkflowStep.EXTRACT_CITATIONS
        return StepResult.BRANCH
    
    def _handle_request_more_citations(self, context: Dict[str, Any]) -> StepResult:
        """Handle requests for more citations."""
        # This would be implemented to request more citations
        logger.info("More citations request step - not yet implemented")
        context['branch_to_step'] = WorkflowStep.EXTRACT_CITATIONS
        return StepResult.BRANCH
    
    def _handle_review_and_revise_report(self, context: Dict[str, Any]) -> StepResult:
        """Handle report review and revision."""
        # This would be implemented for iterative report improvement
        logger.info("Report review and revision step - not yet implemented")
        return StepResult.SUCCESS
    
    def _execute_document_search(self, question: str) -> List[Dict[str, Any]]:
        """Execute document search with query processing."""
        logger.info(f"Executing document search for: {question}")
        
        documents = self.query_processor.search_documents_with_review(question)
        
        if documents:
            logger.info(f"Document search successful: {len(documents)} documents found")
            return documents
        else:
            logger.warning(f"No documents found for question: {question}")
            if self.config.auto_mode:
                self.ui.show_error_message(f"No documents found for question: {question}")
            else:
                self.ui.show_warning_message(f"No documents found for question: {question}")
                self.ui.show_info_message("You can refine your search by going back to query refinement.")
            return []
    
    def _process_search_results(self, documents: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """Process search results with user interaction."""
        from .query_processing import DocumentProcessor
        
        doc_processor = DocumentProcessor(self.config, self.ui)
        
        logger.info(f"Processing search results: {len(documents)} documents")
        result = doc_processor.process_search_results(documents)
        
        if result is None:
            if self.config.auto_mode:
                # In auto mode, just return the documents without user retry
                logger.info("Auto mode: proceeding with all documents")
                return documents
            else:
                # In the new step-based system, we'll handle retry via step branching
                logger.info("User wants to search again - will trigger query refinement step")
                return None
        else:
            logger.info(f"Search results processed: {len(result)} documents approved")
            return result
    
    def _execute_document_scoring(self, question: str, documents: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """Execute document scoring with user review."""
        try:
            self.ui.show_progress_message(f"Scoring {len(documents)} documents for relevance to:")
            print(f'   "{question}"')
            self.ui.show_info_message("This may take a few minutes...")
            
            scored_docs = []
            
            # Score documents with progress indication
            for i, doc in enumerate(documents, 1):
                if self.config.show_progress:
                    print(f"   Scoring document {i}/{len(documents)}: {doc.get('title', 'Untitled')[:50]}...")
                
                score_result = self.scoring_agent.evaluate_document(question, doc)
                
                if score_result:
                    scored_docs.append((doc, score_result))
                else:
                    self.ui.show_warning_message(f"Failed to score document {i}")
            
            if not scored_docs:
                self.ui.show_error_message("No documents could be scored. Check Ollama connection.")
                return []
            
            # Sort by score (descending)
            scored_docs.sort(key=lambda x: x[1].get('score', 0), reverse=True)
            
            # User review of scores
            while True:
                choice = self.ui.display_document_scores(scored_docs, self.config.default_score_threshold)
                
                if choice == '1':
                    # Proceed with current threshold
                    return scored_docs
                
                elif choice == '2':
                    # Adjust score threshold
                    new_threshold = self.ui.get_score_threshold_adjustment(self.config.default_score_threshold)
                    if new_threshold is not None:
                        self.config.default_score_threshold = new_threshold
                        qualifying = len([doc for doc, score in scored_docs if score.get('score', 0) > new_threshold])
                        self.ui.show_success_message(f"New threshold: {new_threshold}")
                        print(f"   Documents that will qualify: {qualifying}")
                    continue
                
                elif choice == '3':
                    # Show detailed score review
                    self.ui.show_detailed_scores(scored_docs)
                    continue
                
                elif choice == '4':
                    # Re-score with different parameters
                    self.ui.show_info_message("Re-scoring documents...")
                    # Could implement different scoring parameters here
                    continue
                
                else:
                    self.ui.show_error_message("Invalid option. Please choose 1-4.")
        
        except Exception as e:
            self.ui.show_error_message(f"Error in document scoring: {e}")
            return []
    
    def _execute_citation_extraction(self, question: str, scored_docs: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> List[Citation]:
        """Execute citation extraction with user review."""
        try:
            while True:
                # Filter documents above threshold
                qualifying_docs = [
                    (doc, score) for doc, score in scored_docs 
                    if score.get('score', 0) > self.config.default_score_threshold
                ]
                
                self.ui.show_progress_message(f"Processing {len(qualifying_docs)} documents above threshold {self.config.default_score_threshold}")
                print(f'   Extracting citations for: "{question}"')
                self.ui.show_info_message("This may take several minutes...")
                
                # Extract citations with progress indication
                def progress_callback(current, total):
                    if self.config.show_progress:
                        percentage = (current / total) * 100
                        print(f"   Progress: {current}/{total} documents ({percentage:.1f}%)")
                
                citations = self.citation_agent.process_scored_documents_for_citations(
                    user_question=question,
                    scored_documents=qualifying_docs,
                    score_threshold=self.config.default_score_threshold,
                    min_relevance=self.config.default_min_relevance,
                    progress_callback=progress_callback
                )
                
                if not citations:
                    self.ui.show_error_message("No citations extracted.")
                    print("\nPossible reasons:")
                    print("• Score threshold too high")
                    print("• Minimum relevance threshold too high")
                    print("• Documents don't contain relevant passages")
                    print("• Ollama connection issues")
                    return []
                
                # User review of citations
                choice = self.ui.display_citations(citations, self.config.default_score_threshold, 
                                                 self.config.default_min_relevance)
                
                if choice == '1':
                    # Proceed with these citations
                    return citations
                
                elif choice == '2':
                    # Adjust relevance threshold
                    new_relevance = self.ui.get_relevance_threshold_adjustment(self.config.default_min_relevance)
                    if new_relevance is not None:
                        self.config.default_min_relevance = new_relevance
                        self.ui.show_success_message(f"New minimum relevance: {new_relevance}")
                        # Re-extract with new threshold - continue loop
                        continue
                
                elif choice == '3':
                    # Review individual citations
                    self.ui.show_detailed_citations(citations)
                    continue
                
                elif choice == '4':
                    # Go back to document scoring
                    return self._execute_document_scoring(question, [(doc, score) for doc, score in scored_docs])
                
                else:
                    self.ui.show_error_message("Invalid option. Please choose 1-4.")
        
        except Exception as e:
            self.ui.show_error_message(f"Error in citation extraction: {e}")
            return []
    
    def _execute_report_generation(self, question: str, citations: List[Citation]) -> Optional[Report]:
        """Execute report generation with user options for large citation sets."""
        try:
            self.ui.show_progress_message("Generating medical publication-style report...")
            print(f'   Research question: "{question}"')
            print(f"   Based on {len(citations)} citations")
            
            # Handle large citation sets
            if len(citations) > 20:
                choice = self.ui.handle_large_citation_set(len(citations))
                
                if choice == '1':
                    # Proceed with all citations
                    pass
                elif choice == '2':
                    # Use only top citations by relevance
                    sorted_citations = sorted(citations, key=lambda c: c.relevance_score, reverse=True)
                    citations = sorted_citations[:15]
                    self.ui.show_success_message(f"Using top {len(citations)} citations by relevance score")
                elif choice == '3':
                    # Go back to citation extraction
                    self.ui.show_info_message("Please go back to citation extraction step and adjust thresholds.")
                    return None
                else:
                    self.ui.show_error_message("Invalid option. Please choose 1-3.")
                    return None
            
            self.ui.show_progress_message(f"Synthesizing evidence from {len(citations)} citations...")
            
            # Check citation count and provide appropriate feedback
            if len(citations) == 1:
                self.ui.show_warning_message("Only 1 citation available - report will be limited in scope")
                self.ui.show_info_message("Consider lowering thresholds to get more citations for a comprehensive report")
            elif len(citations) < 5:
                self.ui.show_info_message(f"Small citation set ({len(citations)}) - report may be brief")
            
            self.ui.show_info_message("Using iterative processing to avoid context limits...")
            self.ui.show_info_message("Processing citations one by one - this may take a few minutes...")
            
            # Generate report using iterative approach
            # Adjust minimum citations based on available citations
            min_citations = min(2, len(citations)) if len(citations) > 0 else 1
            
            report = self.reporting_agent.synthesize_report(
                user_question=question,
                citations=citations,
                min_citations=min_citations
            )
            
            if not report:
                self.ui.show_error_message("Failed to generate report after multiple attempts.")
                print("Suggestions:")
                print("• Try with fewer citations (go back to citation step)")
                print("• Check Ollama model performance")
                print("• Ensure sufficient system resources")
                return None
            
            # Display the report
            self.ui.display_report(report, self.reporting_agent)
            
            return report
            
        except Exception as e:
            self.ui.show_error_message(f"Error generating report: {e}")
            print("\nSuggestions:")
            print("• Reduce the number of citations")
            print("• Check Ollama service is running properly")
            print("• Ensure sufficient memory and processing power")
            return None
    
    def _execute_counterfactual_analysis(self, report: Report) -> Optional[CounterfactualAnalysis]:
        """Execute counterfactual analysis on the generated report."""
        try:
            # Ask user if they want counterfactual analysis
            if not self.ui.get_counterfactual_analysis_choice():
                return None
            
            self.ui.show_progress_message("Analyzing report for potential contradictory evidence...")
            print("   This will identify claims and generate research questions")
            print("   to find evidence that might contradict the report's conclusions.")
            self.ui.show_info_message("Performing counterfactual analysis...")
            
            # Format the report content for analysis
            formatted_report = self.reporting_agent.format_report_output(report)
            
            # Perform counterfactual analysis
            analysis = self.counterfactual_agent.analyze_document(
                document_content=formatted_report,
                document_title=f"Research Report: {self.current_question[:50]}..."
            )
            
            if not analysis:
                self.ui.show_error_message("Failed to perform counterfactual analysis.")
                return None
            
            # Display results
            self.ui.display_counterfactual_analysis(analysis)
            
            # Ask if user wants to search for contradictory evidence
            if self.ui.get_contradictory_evidence_search_choice():
                contradictory_results = self._search_contradictory_evidence(analysis, formatted_report)
                if contradictory_results:
                    self.contradictory_evidence = contradictory_results
            
            return analysis
            
        except Exception as e:
            self.ui.show_error_message(f"Error in counterfactual analysis: {e}")
            return None
    
    def _search_contradictory_evidence(self, analysis: CounterfactualAnalysis, formatted_report: str) -> Optional[Dict[str, Any]]:
        """Search for contradictory evidence based on counterfactual analysis."""
        try:
            self.ui.show_progress_message("Searching for contradictory evidence...")
            print("   Using high-priority questions to find opposing studies")
            self.ui.show_info_message("This may take several minutes...")
            
            # Use the complete counterfactual workflow
            contradictory_results = self.counterfactual_agent.find_contradictory_literature(
                document_content=formatted_report,
                document_title=f"Research Report: {self.current_question[:50]}...",
                max_results_per_query=5,
                min_relevance_score=3,
                query_agent=self.query_agent,
                scoring_agent=self.scoring_agent,
                citation_agent=self.citation_agent
            )
            
            # Log and validate results structure
            logger.debug(f"Contradictory search returned: {type(contradictory_results)}")
            if contradictory_results:
                logger.debug(f"Result keys: {list(contradictory_results.keys()) if isinstance(contradictory_results, dict) else 'Not a dict'}")
            
            # Ensure we have a valid results structure
            if not isinstance(contradictory_results, dict):
                logger.warning("Contradictory results is not a dictionary, creating empty structure")
                contradictory_results = {
                    'contradictory_evidence': [],
                    'contradictory_citations': [],
                    'summary': {}
                }
            
            # Display results
            self.ui.display_contradictory_evidence_results(contradictory_results)
            
            return contradictory_results
                
        except Exception as e:
            self.ui.show_error_message(f"Error searching for contradictory evidence: {e}")
            return None
    
    def _execute_comprehensive_report_editing(
        self, 
        original_report: Report, 
        research_question: str,
        citations: List[Citation],
        counterfactual_analysis: Optional[CounterfactualAnalysis]
    ) -> Optional[EditedReport]:
        """Execute comprehensive report editing using EditorAgent."""
        try:
            self.ui.show_progress_message("Creating comprehensive balanced report...")
            print(f"   Integrating {len(citations)} citations with counterfactual analysis")
            self.ui.show_info_message("This may take a few minutes...")
            
            # Create comprehensive report using EditorAgent
            comprehensive_report = self.editor_agent.create_comprehensive_report(
                original_report=original_report,
                research_question=research_question,
                supporting_citations=citations,
                contradictory_evidence=self.contradictory_evidence,
                confidence_analysis=counterfactual_analysis
            )
            
            if not comprehensive_report:
                self.ui.show_error_message("Failed to generate comprehensive report.")
                return None
            
            # Display the comprehensive report
            self.ui.display_comprehensive_report(comprehensive_report, self.editor_agent)
            
            return comprehensive_report
            
        except Exception as e:
            self.ui.show_error_message(f"Error generating comprehensive report: {e}")
            return None
    
    def get_workflow_state(self) -> Dict[str, Any]:
        """Get current workflow state for potential resumption."""
        return {
            'current_question': self.current_question,
            'current_query': self.current_query,
            'search_results_count': len(self.search_results),
            'scored_documents_count': len(self.scored_documents),
            'extracted_citations_count': len(self.extracted_citations),
            'has_final_report': self.final_report is not None,
            'has_counterfactual_analysis': self.counterfactual_analysis is not None,
            'has_contradictory_evidence': self.contradictory_evidence is not None,
            'has_comprehensive_report': self.comprehensive_report is not None,
            'config': {
                'score_threshold': self.config.default_score_threshold,
                'min_relevance': self.config.default_min_relevance,
                'max_search_results': self.config.max_search_results
            }
        }
    
    def clear_workflow_state(self) -> None:
        """Clear current workflow state for a fresh start."""
        self.current_question = None
        self.current_query = None
        self.search_results = []
        self.scored_documents = []
        self.extracted_citations = []
        self.final_report = None
        self.counterfactual_analysis = None
        self.contradictory_evidence = None
        self.comprehensive_report = None