"""
Workflow Orchestration Module

Handles the main research workflow coordination, agent setup, and state management.
"""

import time
import logging
from typing import List, Dict, Any, Tuple, Optional
from bmlibrarian.agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent, 
    ReportingAgent, CounterfactualAgent, EditorAgent, AgentOrchestrator, 
    Citation, Report, CounterfactualAnalysis, EditedReport
)

# Get logger for workflow operations
logger = logging.getLogger('bmlibrarian.workflow')


class WorkflowOrchestrator:
    """Orchestrates the complete research workflow with agent coordination."""
    
    def __init__(self, config, ui, query_processor, formatter):
        self.config = config
        self.ui = ui
        self.query_processor = query_processor
        self.formatter = formatter
        
        # Agent components
        self.orchestrator: Optional[AgentOrchestrator] = None
        self.query_agent: Optional[QueryAgent] = None
        self.scoring_agent: Optional[DocumentScoringAgent] = None
        self.citation_agent: Optional[CitationFinderAgent] = None
        self.reporting_agent: Optional[ReportingAgent] = None
        self.counterfactual_agent: Optional[CounterfactualAgent] = None
        self.editor_agent: Optional[EditorAgent] = None
        
        # Workflow state
        self.current_question: Optional[str] = None
        self.current_query: Optional[str] = None
        self.search_results: List[Dict[str, Any]] = []
        self.scored_documents: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        self.extracted_citations: List[Citation] = []
        self.final_report: Optional[Report] = None
        self.counterfactual_analysis: Optional[CounterfactualAnalysis] = None
        self.contradictory_evidence: Optional[Dict[str, Any]] = None
        self.comprehensive_report: Optional[EditedReport] = None
    
    def setup_agents(self) -> bool:
        """Initialize and test all agents."""
        try:
            self.ui.show_progress_message("Setting up BMLibrarian agents...")
            
            # Initialize orchestrator
            self.orchestrator = AgentOrchestrator(
                max_workers=self.config.max_workers, 
                polling_interval=self.config.polling_interval
            )
            
            # Initialize agents
            self.query_agent = QueryAgent(orchestrator=self.orchestrator)
            self.scoring_agent = DocumentScoringAgent(orchestrator=self.orchestrator)
            self.citation_agent = CitationFinderAgent(orchestrator=self.orchestrator)
            self.reporting_agent = ReportingAgent(orchestrator=self.orchestrator)
            self.counterfactual_agent = CounterfactualAgent(orchestrator=self.orchestrator)
            self.editor_agent = EditorAgent(orchestrator=self.orchestrator)
            
            # Register agents
            self.orchestrator.register_agent("query_agent", self.query_agent)
            self.orchestrator.register_agent("document_scoring_agent", self.scoring_agent)
            self.orchestrator.register_agent("citation_finder_agent", self.citation_agent)
            self.orchestrator.register_agent("reporting_agent", self.reporting_agent)
            self.orchestrator.register_agent("counterfactual_agent", self.counterfactual_agent)
            self.orchestrator.register_agent("editor_agent", self.editor_agent)
            
            # Set query agent in processor
            self.query_processor.set_query_agent(self.query_agent)
            
            self.ui.show_success_message("Agents initialized")
            
            # Test connections
            return self._test_service_connections()
            
        except Exception as e:
            self.ui.show_error_message(f"Failed to setup agents: {e}")
            return False
    
    def _test_service_connections(self) -> bool:
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
        """Execute the complete research workflow with user interaction."""
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
            # Setup
            setup_start = time.time()
            if not self.setup_agents():
                logger.error("Agent setup failed")
                self.ui.show_error_message("Cannot proceed without proper agent setup.")
                return False
            
            logger.info(f"Agents setup completed in {(time.time() - setup_start)*1000:.2f}ms")
            
            # Start orchestrator
            self.orchestrator.start_processing()
            
            # Step 1: Get research question
            step1_start = time.time()
            logger.info("Step 1: Getting research question", extra={'structured_data': {
                'event_type': 'workflow_step',
                'workflow_id': workflow_id,
                'step_number': 1,
                'step_name': 'get_research_question',
                'timestamp': step1_start
            }})
            
            if self.config.auto_mode and auto_question:
                question = auto_question
                print(f"\n🔬 Auto-mode research question: {question}")
                logger.info(f"Using auto-mode question: {question}")
            else:
                question = self.ui.get_research_question()
                if not question:
                    if self.config.auto_mode:
                        logger.error("Auto mode requires a research question")
                        self.ui.show_error_message("Auto mode requires a research question to be provided.")
                    else:
                        logger.info("User cancelled question input")
                    return False
                logger.info(f"User provided question: {question}")
            
            self.current_question = question
            step1_time = (time.time() - step1_start) * 1000
            logger.info(f"Step 1 completed in {step1_time:.2f}ms")
            
            # Step 2: Search documents using QueryAgent
            step2_start = time.time()
            logger.info("Step 2: Document search", extra={'structured_data': {
                'event_type': 'workflow_step',
                'workflow_id': workflow_id,
                'step_number': 2,
                'step_name': 'document_search',
                'timestamp': step2_start
            }})
            
            documents = self._execute_document_search(question)
            if not documents:
                logger.error("No documents found in search")
                self.ui.show_error_message("Cannot proceed without documents.")
                return False
            
            step2_time = (time.time() - step2_start) * 1000
            logger.info(f"Step 2 completed: {len(documents)} documents found in {step2_time:.2f}ms")
            
            # Step 3: Display and review documents
            step3_start = time.time()
            logger.info("Step 3: Document review", extra={'structured_data': {
                'event_type': 'workflow_step',
                'workflow_id': workflow_id,
                'step_number': 3,
                'step_name': 'document_review',
                'document_count': len(documents),
                'timestamp': step3_start
            }})
            
            documents = self._process_search_results(documents)
            if not documents:
                logger.error("Document review cancelled or failed")
                return False
            
            self.search_results = documents
            step3_time = (time.time() - step3_start) * 1000
            logger.info(f"Step 3 completed: {len(documents)} documents approved in {step3_time:.2f}ms")
            
            # Step 4: Score documents using DocumentScoringAgent
            step4_start = time.time()
            logger.info("Step 4: Document scoring", extra={'structured_data': {
                'event_type': 'workflow_step',
                'workflow_id': workflow_id,
                'step_number': 4,
                'step_name': 'document_scoring',
                'document_count': len(documents),
                'timestamp': step4_start
            }})
            
            scored_docs = self._execute_document_scoring(question, documents)
            if not scored_docs:
                logger.error("Document scoring failed")
                self.ui.show_error_message("Cannot proceed without scored documents.")
                return False
            
            self.scored_documents = scored_docs
            step4_time = (time.time() - step4_start) * 1000
            logger.info(f"Step 4 completed: {len(scored_docs)} documents scored in {step4_time:.2f}ms")
            
            # Step 5: Extract citations using CitationFinderAgent
            step5_start = time.time()
            logger.info("Step 5: Citation extraction", extra={'structured_data': {
                'event_type': 'workflow_step',
                'workflow_id': workflow_id,
                'step_number': 5,
                'step_name': 'citation_extraction',
                'scored_document_count': len(scored_docs),
                'timestamp': step5_start
            }})
            
            citations = self._execute_citation_extraction(question, scored_docs)
            if not citations:
                logger.error("Citation extraction failed")
                self.ui.show_error_message("Cannot proceed without citations.")
                return False
            
            self.extracted_citations = citations
            step5_time = (time.time() - step5_start) * 1000
            logger.info(f"Step 5 completed: {len(citations)} citations extracted in {step5_time:.2f}ms")
            
            # Step 6: Generate report using ReportingAgent
            step6_start = time.time()
            logger.info("Step 6: Report generation", extra={'structured_data': {
                'event_type': 'workflow_step',
                'workflow_id': workflow_id,
                'step_number': 6,
                'step_name': 'report_generation',
                'citation_count': len(citations),
                'timestamp': step6_start
            }})
            
            report = self._execute_report_generation(question, citations)
            if not report:
                logger.error("Report generation failed")
                self.ui.show_error_message("Report generation failed.")
                return False
            
            self.final_report = report
            step6_time = (time.time() - step6_start) * 1000
            logger.info(f"Step 6 completed: Report generated in {step6_time:.2f}ms")
            
            # Step 7: Optional counterfactual analysis
            step7_start = time.time()
            logger.info("Step 7: Counterfactual analysis", extra={'structured_data': {
                'event_type': 'workflow_step',
                'workflow_id': workflow_id,
                'step_number': 7,
                'step_name': 'counterfactual_analysis',
                'timestamp': step7_start
            }})
            
            counterfactual_analysis = self._execute_counterfactual_analysis(report)
            if counterfactual_analysis:
                self.counterfactual_analysis = counterfactual_analysis
                logger.info(f"Counterfactual analysis completed: {len(counterfactual_analysis.counterfactual_questions)} questions generated")
            else:
                logger.info("Counterfactual analysis skipped or failed")
            
            step7_time = (time.time() - step7_start) * 1000
            logger.info(f"Step 7 completed in {step7_time:.2f}ms")
            
            # Step 8: Comprehensive report generation using EditorAgent
            step8_start = time.time()
            logger.info("Step 8: Comprehensive report editing", extra={'structured_data': {
                'event_type': 'workflow_step',
                'workflow_id': workflow_id,
                'step_number': 8,
                'step_name': 'comprehensive_report_editing',
                'timestamp': step8_start
            }})
            
            comprehensive_report = self._execute_comprehensive_report_editing(
                report, question, citations, counterfactual_analysis
            )
            if comprehensive_report:
                self.comprehensive_report = comprehensive_report
                logger.info(f"Comprehensive report generated: {comprehensive_report.word_count} words")
            else:
                logger.info("Comprehensive report editing failed, using original report")
            
            step8_time = (time.time() - step8_start) * 1000
            logger.info(f"Step 8 completed in {step8_time:.2f}ms")
            
            # Step 9: Save report (optional)
            step9_start = time.time()
            logger.info("Step 9: Report saving", extra={'structured_data': {
                'event_type': 'workflow_step',
                'workflow_id': workflow_id,
                'step_number': 9,
                'step_name': 'report_saving',
                'timestamp': step9_start
            }})
            
            if self.ui.get_save_report_choice():
                # Use comprehensive report if available, otherwise use original report
                report_to_save = comprehensive_report if comprehensive_report else report
                filename = self.formatter.save_comprehensive_report_to_file(
                    report_to_save, question, self.counterfactual_analysis, self.contradictory_evidence
                )
                logger.info(f"Report saved to file: {filename}")
            else:
                logger.info("Report saving skipped")
            
            step9_time = (time.time() - step9_start) * 1000
            logger.info(f"Step 9 completed in {step9_time:.2f}ms")
            
            # Final summary
            total_workflow_time = (time.time() - workflow_start_time) * 1000
            
            logger.info("Workflow completed successfully", extra={'structured_data': {
                'event_type': 'workflow_completion',
                'workflow_id': workflow_id,
                'success': True,
                'total_time_ms': total_workflow_time,
                'final_summary': {
                    'question': question,
                    'documents_found': len(documents),
                    'documents_scored': len(scored_docs),
                    'citations_extracted': len(citations),
                    'evidence_strength': report.evidence_strength,
                    'counterfactual_questions': len(counterfactual_analysis.counterfactual_questions) if counterfactual_analysis else 0
                },
                'timestamp': time.time()
            }})
            
            self.ui.show_workflow_summary(
                question, len(documents), len(scored_docs), 
                len(citations), report.evidence_strength, self.counterfactual_analysis
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
    
    def _execute_document_search(self, question: str) -> List[Dict[str, Any]]:
        """Execute document search with query processing."""
        while True:
            documents = self.query_processor.search_documents_with_review(question)
            
            if documents:
                return documents
            else:
                if self.config.auto_mode:
                    self.ui.show_error_message(f"No documents found for question: {question}")
                    return []
                
                # Give user option to try again or quit
                retry = input("\nWould you like to try a different question? (y/n): ").strip().lower()
                if retry not in ['y', 'yes']:
                    return []
                
                # Get new question
                new_question = self.ui.get_research_question()
                if not new_question:
                    return []
                
                question = new_question
                self.current_question = question
    
    def _process_search_results(self, documents: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """Process search results with user interaction."""
        from .query_processing import DocumentProcessor
        
        doc_processor = DocumentProcessor(self.config, self.ui)
        
        while True:
            result = doc_processor.process_search_results(documents)
            
            if result is None:
                if self.config.auto_mode:
                    # In auto mode, just return the documents without user retry
                    return documents
                
                # User wants to search again
                new_question = self.ui.get_research_question()
                if not new_question:
                    return None
                
                self.current_question = new_question
                new_documents = self._execute_document_search(new_question)
                if new_documents:
                    documents = new_documents
                    continue
                else:
                    return None
            else:
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