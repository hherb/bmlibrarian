"""
Report Builder for BMLibrarian Research GUI

Handles the construction and formatting of comprehensive research reports
including counterfactual analysis and methodology sections.
"""

from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional


class ReportBuilder:
    """Builds comprehensive research reports with metadata and analysis sections."""
    
    def __init__(self, workflow_steps: List):
        self.workflow_steps = workflow_steps
    
    def build_final_report(self, research_question: str, report_content: str,
                          counterfactual_analysis: Any, documents: List[Dict], 
                          scored_documents: List[Tuple[Dict, Dict]], citations: List,
                          human_in_loop: bool, agent_model_info: Optional[Dict] = None) -> str:
        """Build the comprehensive final report.
        
        Args:
            research_question: The original research question
            report_content: Main report content from reporting agent
            counterfactual_analysis: Results from counterfactual analysis
            documents: List of all found documents
            scored_documents: List of scored documents above threshold
            citations: List of extracted citations
            human_in_loop: Whether the workflow was interactive
            
        Returns:
            Complete formatted research report as markdown string
        """
        print(f"_build_final_report called with report_content length: {len(report_content) if report_content else 0}")
        
        # Extract counterfactual analysis content
        counterfactual_content = self._format_counterfactual_analysis(counterfactual_analysis)
        
        # Build research summary section
        summary_section = self._build_summary_section(
            research_question, documents, scored_documents, citations
        )
        
        # Build methodology section
        methodology_section = self._build_methodology_section(counterfactual_analysis)
        
        # Build limitations section
        limitations_section = self._build_limitations_section(
            documents, scored_documents, citations, counterfactual_analysis
        )
        
        # Build metadata section
        metadata_section = self._build_metadata_section(human_in_loop)
        
        # Build model information footnotes
        model_footnotes = self._build_model_footnotes(agent_model_info)
        
        # Assemble the complete report
        final_report = f"""# Research Report: {research_question}

> ✅ **Generated using real BMLibrarian agents**

{summary_section}

---

{report_content}
{counterfactual_content}

{methodology_section}

{limitations_section}

---

{metadata_section}

{model_footnotes}

*This report was generated using BMLibrarian's AI-powered multi-agent research system with real database queries and LLM analysis.*
"""
        
        print(f"Returning final report with length: {len(final_report)}")
        return final_report
    
    def _format_counterfactual_analysis(self, counterfactual_analysis: Any) -> str:
        """Format the counterfactual analysis section.
        
        Args:
            counterfactual_analysis: Analysis results from counterfactual agent
            
        Returns:
            Formatted counterfactual analysis section
        """
        if not counterfactual_analysis:
            return ""
        
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
        
        return counterfactual_content
    
    def _build_summary_section(self, research_question: str, documents: List[Dict],
                             scored_documents: List[Tuple[Dict, Dict]], 
                             citations: List) -> str:
        """Build the research summary section.
        
        Args:
            research_question: The research question
            documents: All found documents
            scored_documents: Documents above relevance threshold
            citations: Extracted citations
            
        Returns:
            Formatted summary section
        """
        high_relevance_count = sum(1 for _, result in scored_documents 
                                 if result.get('score', 0) >= 4)
        
        return f"""## Research Summary

**Question**: {research_question}  
**Documents Found**: {len(documents)}  
**Documents Scored**: {len(scored_documents)} (threshold ≥ 2.5)  
**High Relevance Documents**: {high_relevance_count}  
**Citations Extracted**: {len(citations)}"""
    
    def _build_methodology_section(self, counterfactual_analysis: Any = None) -> str:
        """Build the methodology section.
        
        Args:
            counterfactual_analysis: Counterfactual analysis results to determine type
        
        Returns:
            Formatted methodology section
        """
        # Determine type of counterfactual analysis performed
        cf_description = "**Counterfactual Analysis**: Analyzed for potential contradictory evidence"
        if counterfactual_analysis:
            if hasattr(counterfactual_analysis, 'get') and counterfactual_analysis.get('contradictory_evidence'):
                cf_description = "**Comprehensive Counterfactual Analysis**: Performed literature search for contradictory evidence with citation extraction"
            elif hasattr(counterfactual_analysis, 'counterfactual_questions'):
                cf_description = "**Basic Counterfactual Analysis**: Analyzed claims and generated research questions for finding contradictory evidence"
        
        return f"""## Research Methodology

- **Query Generation**: Natural language converted to PostgreSQL query
- **Database Search**: Searched biomedical literature database  
- **Relevance Scoring**: AI-powered document scoring (1-5 scale)
- **Citation Extraction**: Extracted relevant passages from high-scoring documents
- **Report Synthesis**: Generated comprehensive medical research report
- {cf_description}"""
    
    def _build_limitations_section(self, documents: List[Dict], 
                                 scored_documents: List[Tuple[Dict, Dict]], 
                                 citations: List, counterfactual_analysis: Any) -> str:
        """Build the limitations and confidence section.
        
        Args:
            documents: All found documents
            scored_documents: Documents above relevance threshold
            citations: Extracted citations
            counterfactual_analysis: Counterfactual analysis results
            
        Returns:
            Formatted limitations section
        """
        return f"""## Limitations and Confidence

- Search limited to available database content
- Analysis performed on {len(documents)} documents
- {len(citations)} citations extracted from {len(scored_documents)} scored documents
- Counterfactual analysis {'performed' if counterfactual_analysis else 'not performed'}"""
    
    def _build_metadata_section(self, human_in_loop: bool) -> str:
        """Build the metadata section.
        
        Args:
            human_in_loop: Whether workflow was interactive
            
        Returns:
            Formatted metadata section
        """
        return f"""**Report Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Research Mode**: {'Interactive' if human_in_loop else 'Automated'} (Real Agents)  
**Processing Time**: Completed {len(self.workflow_steps)} workflow steps  
**Agent Status**: ✅ Real BMLibrarian Agents"""  
    
    def _build_model_footnotes(self, agent_model_info: Optional[Dict] = None) -> str:
        """Build the model information footnotes section.
        
        Args:
            agent_model_info: Dictionary containing model information for each agent
            
        Returns:
            Formatted model information footnotes
        """
        if not agent_model_info:
            return "## Model Information\n\n*Model information not available.*"
        
        footnotes = ["## Model Information\n"]
        footnotes.append("The following AI models and parameters were used for each workflow step:\n")
        
        for step_name, model_info in agent_model_info.items():
            model = model_info.get('model', 'Unknown')
            temperature = model_info.get('temperature', 'Unknown')
            top_p = model_info.get('top_p', 'Unknown')
            host = model_info.get('host', 'Unknown')
            
            # Format the model information
            footnotes.append(f"**{step_name}**:")
            footnotes.append(f"- Model: `{model}`")
            footnotes.append(f"- Temperature: `{temperature}`")
            footnotes.append(f"- Top-p: `{top_p}`")
            footnotes.append(f"- Host: `{host}`")
            footnotes.append("")  # Empty line
        
        # Add explanation of parameters
        footnotes.extend([
            "### Parameter Explanations\n",
            "- **Temperature**: Controls randomness in model responses (0.0 = deterministic, 1.0 = highly random)",
            "- **Top-p**: Nucleus sampling parameter controlling diversity of token selection",
            "- **Host**: Ollama server endpoint for local LLM inference"
        ])
        
        return "\n".join(footnotes)
    
    def build_preview_summary(self, research_question: str, documents: List[Dict],
                            scored_documents: List[Tuple[Dict, Dict]], 
                            citations: List) -> str:
        """Build a brief summary for preview purposes.
        
        Args:
            research_question: The research question
            documents: All found documents
            scored_documents: Documents above relevance threshold
            citations: Extracted citations
            
        Returns:
            Brief formatted summary
        """
        high_relevance = sum(1 for _, result in scored_documents 
                           if result.get('score', 0) >= 4)
        
        return f"""# Research Progress Summary

**Question**: {research_question}

**Current Status**:
- Found {len(documents)} documents
- Scored {len(scored_documents)} documents above threshold
- {high_relevance} high-relevance documents (≥4.0)
- Extracted {len(citations)} citations

**Next Steps**: Report generation and analysis in progress..."""
    
    def extract_report_statistics(self, documents: List[Dict], 
                                scored_documents: List[Tuple[Dict, Dict]]) -> Dict[str, Any]:
        """Extract statistical information from the research process.
        
        Args:
            documents: All found documents
            scored_documents: Documents above relevance threshold
            
        Returns:
            Dictionary with research statistics
        """
        if not scored_documents:
            return {
                'total_documents': len(documents),
                'scored_documents': 0,
                'score_distribution': {},
                'average_score': 0.0
            }
        
        scores = [result.get('score', 0) for _, result in scored_documents]
        score_distribution = {
            '5.0': sum(1 for s in scores if s >= 5.0),
            '4.0-4.9': sum(1 for s in scores if 4.0 <= s < 5.0),
            '3.0-3.9': sum(1 for s in scores if 3.0 <= s < 4.0),
            '2.5-2.9': sum(1 for s in scores if 2.5 <= s < 3.0)
        }
        
        return {
            'total_documents': len(documents),
            'scored_documents': len(scored_documents),
            'score_distribution': score_distribution,
            'average_score': sum(scores) / len(scores) if scores else 0.0,
            'highest_score': max(scores) if scores else 0,
            'lowest_score': min(scores) if scores else 0
        }