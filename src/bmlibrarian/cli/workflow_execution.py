"""
Workflow Execution Module

Handles core document processing operations and execution logic.
"""

import logging
from typing import List, Dict, Any, Tuple, Optional
from bmlibrarian.agents import Citation, Report, CounterfactualAnalysis, EditedReport

logger = logging.getLogger('bmlibrarian.workflow.execution')


class WorkflowExecutionManager:
    """Handles core document processing and execution operations."""
    
    def __init__(self, config, ui, query_processor, agent_manager, state_manager):
        self.config = config
        self.ui = ui
        self.query_processor = query_processor
        self.agent_manager = agent_manager
        self.state_manager = state_manager
    
    def execute_document_search(self, question: str) -> List[Dict[str, Any]]:
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
    
    def process_search_results(self, documents: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
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
    
    def execute_document_scoring(self, question: str, documents: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
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
                
                score_result = self.agent_manager.scoring_agent.evaluate_document(question, doc)
                
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
    
    def execute_citation_extraction(self, question: str, scored_docs: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> List[Citation]:
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
                
                citations = self.agent_manager.citation_agent.process_scored_documents_for_citations(
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
                    documents = [doc for doc, score in scored_docs]
                    return self.execute_citation_extraction(question, self.execute_document_scoring(question, documents))
                
                else:
                    self.ui.show_error_message("Invalid option. Please choose 1-4.")
        
        except Exception as e:
            self.ui.show_error_message(f"Error in citation extraction: {e}")
            return []
    
    def execute_report_generation(self, question: str, citations: List[Citation]) -> Optional[Report]:
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
            
            report = self.agent_manager.reporting_agent.synthesize_report(
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
            self.ui.display_report(report, self.agent_manager.reporting_agent)
            
            return report
            
        except Exception as e:
            self.ui.show_error_message(f"Error generating report: {e}")
            print("\nSuggestions:")
            print("• Reduce the number of citations")
            print("• Check Ollama service is running properly")
            print("• Ensure sufficient memory and processing power")
            return None
    
    def execute_counterfactual_analysis(self, report: Report) -> Optional[CounterfactualAnalysis]:
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
            formatted_report = self.agent_manager.reporting_agent.format_report_output(report)
            
            # Perform counterfactual analysis
            analysis = self.agent_manager.counterfactual_agent.analyze_document(
                document_content=formatted_report,
                document_title=f"Research Report: {self.state_manager.current_question[:50]}..."
            )
            
            if not analysis:
                self.ui.show_error_message("Failed to perform counterfactual analysis.")
                return None
            
            # Display results
            self.ui.display_counterfactual_analysis(analysis)
            
            # Ask if user wants to search for contradictory evidence
            if self.ui.get_contradictory_evidence_search_choice():
                contradictory_results = self.search_contradictory_evidence(analysis, formatted_report)
                if contradictory_results:
                    self.state_manager.update_contradictory_evidence(contradictory_results)
            
            return analysis
            
        except Exception as e:
            self.ui.show_error_message(f"Error in counterfactual analysis: {e}")
            return None
    
    def search_contradictory_evidence(self, analysis: CounterfactualAnalysis, formatted_report: str) -> Optional[Dict[str, Any]]:
        """Search for contradictory evidence based on counterfactual analysis."""
        try:
            self.ui.show_progress_message("Searching for contradictory evidence...")
            print("   Using high-priority questions to find opposing studies")
            self.ui.show_info_message("This may take several minutes...")
            
            # Use the complete counterfactual workflow
            contradictory_results = self.agent_manager.counterfactual_agent.find_contradictory_literature(
                document_content=formatted_report,
                document_title=f"Research Report: {self.state_manager.current_question[:50]}...",
                max_results_per_query=5,
                min_relevance_score=3,
                query_agent=self.agent_manager.query_agent,
                scoring_agent=self.agent_manager.scoring_agent,
                citation_agent=self.agent_manager.citation_agent
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
    
    def execute_comprehensive_report_editing(
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
            comprehensive_report = self.agent_manager.editor_agent.create_comprehensive_report(
                original_report=original_report,
                research_question=research_question,
                supporting_citations=citations,
                contradictory_evidence=self.state_manager.contradictory_evidence,
                confidence_analysis=counterfactual_analysis
            )
            
            if not comprehensive_report:
                self.ui.show_error_message("Failed to generate comprehensive report.")
                return None
            
            # Display the comprehensive report
            self.ui.display_comprehensive_report(comprehensive_report, self.agent_manager.editor_agent)
            
            return comprehensive_report
            
        except Exception as e:
            self.ui.show_error_message(f"Error generating comprehensive report: {e}")
            return None