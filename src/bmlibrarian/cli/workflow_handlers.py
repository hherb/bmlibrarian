"""
Workflow Step Handlers Module

Handles individual workflow step execution logic.
"""

import logging
from typing import Dict, Any
from .workflow_steps import WorkflowStep, StepResult

logger = logging.getLogger('bmlibrarian.workflow.handlers')


class WorkflowStepHandlers:
    """Handles execution of individual workflow steps."""
    
    def __init__(self, config, ui, agent_manager, state_manager, execution_manager):
        self.config = config
        self.ui = ui
        self.agent_manager = agent_manager
        self.state_manager = state_manager
        self.execution_manager = execution_manager
    
    def handle_workflow_step(self, step: WorkflowStep, context: Dict[str, Any]) -> StepResult:
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
        
        self.state_manager.update_question(question)
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
        
        documents = self.execution_manager.execute_document_search(question)
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
        
        self.state_manager.update_search_results(documents)
        context['documents'] = documents
        return StepResult.SUCCESS
    
    def _handle_review_search_results(self, context: Dict[str, Any]) -> StepResult:
        """Handle search results review."""
        documents = context.get('documents', self.state_manager.search_results)
        
        reviewed_documents = self.execution_manager.process_search_results(documents)
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
        
        self.state_manager.update_search_results(reviewed_documents)
        context['documents'] = reviewed_documents
        return StepResult.SUCCESS
    
    def _handle_score_documents(self, context: Dict[str, Any]) -> StepResult:
        """Handle document scoring."""
        question = context.get('research_question')
        documents = context.get('documents', self.state_manager.search_results)
        
        scored_docs = self.execution_manager.execute_document_scoring(question, documents)
        if not scored_docs:
            logger.error("Document scoring failed")
            self.ui.show_error_message("Cannot proceed without scored documents.")
            return StepResult.FAILURE
        
        self.state_manager.update_scored_documents(scored_docs)
        context['scored_documents'] = scored_docs
        return StepResult.SUCCESS
    
    def _handle_extract_citations(self, context: Dict[str, Any]) -> StepResult:
        """Handle citation extraction."""
        question = context.get('research_question')
        scored_docs = context.get('scored_documents', self.state_manager.scored_documents)
        
        citations = self.execution_manager.execute_citation_extraction(question, scored_docs)
        if not citations:
            logger.error("Citation extraction failed")
            self.ui.show_error_message("Cannot proceed without citations.")
            context['insufficient_citations'] = True
            return StepResult.BRANCH  # This will trigger threshold adjustment
        
        self.state_manager.update_citations(citations)
        context['citations'] = citations
        return StepResult.SUCCESS
    
    def _handle_generate_report(self, context: Dict[str, Any]) -> StepResult:
        """Handle report generation."""
        question = context.get('research_question')
        citations = context.get('citations', self.state_manager.extracted_citations)
        
        report = self.execution_manager.execute_report_generation(question, citations)
        if not report:
            logger.error("Report generation failed")
            self.ui.show_error_message("Report generation failed.")
            context['insufficient_evidence_for_report'] = True
            return StepResult.BRANCH  # This will trigger more citation requests
        
        self.state_manager.update_final_report(report)
        context['report'] = report
        return StepResult.SUCCESS
    
    def _handle_counterfactual_analysis(self, context: Dict[str, Any]) -> StepResult:
        """Handle counterfactual analysis."""
        report = context.get('report', self.state_manager.final_report)
        
        counterfactual_analysis = self.execution_manager.execute_counterfactual_analysis(report)
        if counterfactual_analysis:
            self.state_manager.update_counterfactual_analysis(counterfactual_analysis)
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
        report = context.get('report', self.state_manager.final_report)
        question = context.get('research_question')
        citations = context.get('citations', self.state_manager.extracted_citations)
        counterfactual_analysis = context.get('counterfactual_analysis', self.state_manager.counterfactual_analysis)
        
        comprehensive_report = self.execution_manager.execute_comprehensive_report_editing(
            report, question, citations, counterfactual_analysis
        )
        if comprehensive_report:
            self.state_manager.update_comprehensive_report(comprehensive_report)
            context['comprehensive_report'] = comprehensive_report
            logger.info(f"Comprehensive report generated: {comprehensive_report.word_count} words")
        else:
            logger.info("Comprehensive report editing failed, using original report")
        
        return StepResult.SUCCESS
    
    def _handle_export_report(self, context: Dict[str, Any]) -> StepResult:
        """Handle report export."""
        if self.ui.get_save_report_choice():
            from .formatting import ReportFormatter
            formatter = ReportFormatter(self.config, self.ui)
            
            comprehensive_report = context.get('comprehensive_report', self.state_manager.comprehensive_report)
            report = context.get('report', self.state_manager.final_report)
            question = context.get('research_question', "Unknown Research Question")
            
            # Use comprehensive report if available, otherwise use original report
            report_to_save = comprehensive_report if comprehensive_report else report
            filename = formatter.save_comprehensive_report_to_file(
                report_to_save, question, self.state_manager.counterfactual_analysis, self.state_manager.contradictory_evidence
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
                self.state_manager.update_question(refined_question)
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