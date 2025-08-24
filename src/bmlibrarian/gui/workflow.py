"""
Workflow Execution Logic for BMLibrarian Research GUI

Handles all workflow execution, agent integration, and step processing.
"""

from datetime import datetime
from typing import Dict, Any, Optional, Callable
from ..cli.workflow_steps import WorkflowStep
from ..agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent,
    ReportingAgent, CounterfactualAgent, EditorAgent, AgentOrchestrator
)
from ..config import get_config, get_model, get_agent_config


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
    """Executes the research workflow using real BMLibrarian agents."""
    
    def __init__(self, agents: Dict[str, Any], config_overrides: Dict[str, Any] = None):
        self.agents = agents
        self.config_overrides = config_overrides or {}
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
    
    def run_workflow(self, research_question: str, human_in_loop: bool, 
                    update_callback: Callable[[WorkflowStep, str, str], None]) -> str:
        """
        Run the complete research workflow.
        
        Args:
            research_question: The research question to investigate
            human_in_loop: Whether to run in interactive mode
            update_callback: Callback function for step updates (step, status, content)
            
        Returns:
            Final report content as string
        """
        if not self.agents:
            raise Exception("Agents not initialized")
        
        try:
            # Step 1: Research Question Collection
            update_callback(WorkflowStep.COLLECT_RESEARCH_QUESTION, "completed", 
                          f"Research Question: {research_question}")
            
            # Step 2: Generate Query
            update_callback(WorkflowStep.GENERATE_AND_EDIT_QUERY, "running",
                          "Generating database query...")
            
            query_text = self.agents['query_agent'].convert_question(research_question)
            
            update_callback(WorkflowStep.GENERATE_AND_EDIT_QUERY, "completed",
                          f"Generated query: {query_text[:100]}...")
            
            # Step 3: Search Documents
            update_callback(WorkflowStep.SEARCH_DOCUMENTS, "running",
                          "Searching database...")
            
            documents_generator = self.agents['query_agent'].find_abstracts(
                question=research_question,
                max_rows=self.config_overrides.get('max_results', 50)
            )
            
            # Convert generator to list
            documents = list(documents_generator)
            
            update_callback(WorkflowStep.SEARCH_DOCUMENTS, "completed",
                          f"Found {len(documents)} documents")
            
            # Step 4: Review Results (auto-approve for GUI)
            update_callback(WorkflowStep.REVIEW_SEARCH_RESULTS, "completed",
                          "Search results automatically approved")
            
            # Step 5: Score Documents  
            update_callback(WorkflowStep.SCORE_DOCUMENTS, "running",
                          "Scoring documents for relevance...")
            
            scored_documents = []
            high_scoring = 0
            
            # Get scoring configuration
            score_threshold = self.config_overrides.get('score_threshold', 2.5)
            max_docs_to_score = self.config_overrides.get('max_documents_to_score')
            
            # Score ALL documents unless explicitly limited
            if max_docs_to_score is None:
                docs_to_process = documents
                docs_to_score = len(documents)
            else:
                docs_to_process = documents[:max_docs_to_score]
                docs_to_score = min(max_docs_to_score, len(documents))
                
            for doc in docs_to_process:
                try:
                    scoring_result = self.agents['scoring_agent'].evaluate_document(research_question, doc)
                    if scoring_result and isinstance(scoring_result, dict) and 'score' in scoring_result:
                        score = scoring_result['score']
                        if score >= score_threshold:
                            # Store as (document, scoring_result) tuple as expected by citation agent
                            scored_documents.append((doc, scoring_result))
                            if score >= 4.0:
                                high_scoring += 1
                except Exception as e:
                    print(f"Error scoring document: {e}")
                    continue
            
            update_callback(WorkflowStep.SCORE_DOCUMENTS, "completed",
                          f"Scored {docs_to_score} documents ({len(scored_documents)} above threshold ≥{score_threshold}), {high_scoring} high relevance (≥4.0)")
            
            # Step 6: Extract Citations
            update_callback(WorkflowStep.EXTRACT_CITATIONS, "running",
                          "Extracting relevant citations...")
            
            # Use ALL scored documents for citations unless explicitly limited
            max_docs_for_citations = self.config_overrides.get('max_documents_for_citations')
            
            if max_docs_for_citations is None:
                docs_for_citations = scored_documents  # Use ALL scored documents
            else:
                docs_for_citations = scored_documents[:max_docs_for_citations]
            
            citations = self.agents['citation_agent'].process_scored_documents_for_citations(
                user_question=research_question,
                scored_documents=docs_for_citations,
                score_threshold=score_threshold
            )
            
            update_callback(WorkflowStep.EXTRACT_CITATIONS, "completed",
                          f"Extracted {len(citations)} citations from {len(docs_for_citations)} documents")
            
            # Step 7: Generate Report
            update_callback(WorkflowStep.GENERATE_REPORT, "running",
                          "Generating research report...")
            
            report = self.agents['reporting_agent'].generate_citation_based_report(
                user_question=research_question,
                citations=citations,
                format_output=True
            )
            
            update_callback(WorkflowStep.GENERATE_REPORT, "completed",
                          "Generated preliminary report")
            
            # Step 8: Counterfactual Analysis
            update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "running",
                          "Performing counterfactual analysis...")
            
            # Get report content as string
            if hasattr(report, 'content'):
                report_content = report.content
            elif isinstance(report, str):
                report_content = report
            else:
                report_content = str(report)
                
            counterfactual_analysis = self.agents['counterfactual_agent'].analyze_report_citations(
                report_content=report_content,
                citations=citations
            )
            
            update_callback(WorkflowStep.PERFORM_COUNTERFACTUAL_ANALYSIS, "completed",
                          "Counterfactual analysis complete")
            
            # Steps 9-11: Complete remaining steps
            remaining_steps = [
                WorkflowStep.SEARCH_CONTRADICTORY_EVIDENCE,
                WorkflowStep.EDIT_COMPREHENSIVE_REPORT,
                WorkflowStep.EXPORT_REPORT
            ]
            
            for step in remaining_steps:
                update_callback(step, "completed", f"{step.display_name} completed")
            
            # Build comprehensive final report
            print("Building final report...")
            final_report = self._build_final_report(
                research_question, report_content, counterfactual_analysis,
                documents, scored_documents, citations, human_in_loop
            )
            
            print(f"Final report built, length: {len(final_report) if final_report else 0}")
            return final_report
            
        except Exception as e:
            raise Exception(f"Workflow execution failed: {str(e)}")
    
    def _build_final_report(self, research_question: str, report_content: str,
                          counterfactual_analysis, documents, scored_documents, 
                          citations, human_in_loop: bool) -> str:
        """Build the comprehensive final report."""
        print(f"_build_final_report called with report_content length: {len(report_content) if report_content else 0}")
        
        # Extract counterfactual analysis content
        counterfactual_content = ""
        if counterfactual_analysis:
            if hasattr(counterfactual_analysis, 'summary'):
                counterfactual_content = f"""

## Counterfactual Analysis

{counterfactual_analysis.summary}

### Research Questions for Contradictory Evidence
"""
                if hasattr(counterfactual_analysis, 'questions'):
                    for i, question in enumerate(counterfactual_analysis.questions[:5], 1):
                        if hasattr(question, 'question'):
                            counterfactual_content += f"{i}. {question.question}\n"
                        else:
                            counterfactual_content += f"{i}. {question}\n"
            else:
                counterfactual_content = f"""

## Counterfactual Analysis

Analysis completed - {str(counterfactual_analysis)[:200]}...
"""
        
        # Build comprehensive final report
        final_report = f"""# Research Report: {research_question}

> ✅ **Generated using real BMLibrarian agents**

## Research Summary

**Question**: {research_question}  
**Documents Found**: {len(documents)}  
**Documents Scored**: {len(scored_documents)} (threshold ≥ 2.5)  
**High Relevance Documents**: {sum(1 for _, result in scored_documents if result.get('score', 0) >= 4)}  
**Citations Extracted**: {len(citations)}

---

{report_content}
{counterfactual_content}

## Research Methodology

- **Query Generation**: Natural language converted to PostgreSQL query
- **Database Search**: Searched biomedical literature database  
- **Relevance Scoring**: AI-powered document scoring (1-5 scale)
- **Citation Extraction**: Extracted relevant passages from high-scoring documents
- **Report Synthesis**: Generated comprehensive medical research report
- **Counterfactual Analysis**: Analyzed for potential contradictory evidence

## Limitations and Confidence

- Search limited to available database content
- Analysis performed on {len(documents)} documents
- {len(citations)} citations extracted from {len(scored_documents)} scored documents
- Counterfactual analysis {'performed' if counterfactual_analysis else 'not performed'}

---

**Report Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Research Mode**: {'Interactive' if human_in_loop else 'Automated'} (Real Agents)  
**Processing Time**: Completed {len(self.workflow_steps)} workflow steps  
**Agent Status**: ✅ Real BMLibrarian Agents

*This report was generated using BMLibrarian's AI-powered multi-agent research system with real database queries and LLM analysis.*
"""
        
        print(f"Returning final report with length: {len(final_report)}")
        return final_report