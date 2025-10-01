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
        if report_content:
            print(f"📝 Input report_content ends with: ...{report_content[-200:]}")
        
        # Extract counterfactual analysis content
        counterfactual_content = self._format_counterfactual_analysis(counterfactual_analysis)
        print(f"📊 Counterfactual content length: {len(counterfactual_content) if counterfactual_content else 0}")
        
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
        
        # Handle the complex nested structure we discovered
        if isinstance(counterfactual_analysis, dict):
            return self._format_comprehensive_counterfactual(counterfactual_analysis)
        elif hasattr(counterfactual_analysis, 'summary'):
            return self._format_basic_counterfactual(counterfactual_analysis)
        else:
            return f"""

## Counterfactual Analysis

Analysis completed - {str(counterfactual_analysis)[:200]}...
"""
    
    def _format_comprehensive_counterfactual(self, analysis: dict) -> str:
        """Format comprehensive counterfactual analysis with evidence and citations.
        
        Args:
            analysis: Dictionary containing nested counterfactual analysis structure
            
        Returns:
            Formatted comprehensive counterfactual section
        """
        # Check if we have the new formatted report structure
        if 'formatted_report' in analysis:
            return self._format_structured_counterfactual(analysis['formatted_report'])
        
        # Fallback to original formatting for backwards compatibility
        content = ["\n## Counterfactual Analysis"]
        
        # Extract summary information
        summary = analysis.get('summary', {})
        if summary:
            content.append("\n### Analysis Summary")
            
            claims_analyzed = summary.get('claims_analyzed', 0)
            questions_generated = summary.get('questions_generated', 0)
            contradictory_docs = summary.get('contradictory_documents_found', 0)
            citations_extracted = summary.get('contradictory_citations_extracted', 0)
            
            if summary.get('original_confidence') and summary.get('revised_confidence'):
                content.append(f"**Confidence Assessment**: {summary['original_confidence']} → {summary['revised_confidence']}")
            
            content.append(f"**Analysis Scope**: {claims_analyzed} claims analyzed, {questions_generated} research questions generated")
            content.append(f"**Literature Search**: {contradictory_docs} contradictory studies found, {citations_extracted} citations extracted")
        
        # Extract and format contradictory evidence
        contradictory_evidence = analysis.get('contradictory_evidence', [])
        if contradictory_evidence:
            content.append("\n### Contradictory Evidence Found")
            content.append("\nThe following studies present evidence that challenges aspects of the original findings:\n")
            
            for i, evidence_item in enumerate(contradictory_evidence, 1):
                if isinstance(evidence_item, dict) and 'document' in evidence_item:
                    doc = evidence_item['document']
                    score = evidence_item.get('score', 'N/A')
                    reasoning = evidence_item.get('reasoning', 'No reasoning provided')
                    
                    title = doc.get('title', 'Untitled Document')
                    authors = doc.get('authors', 'Unknown authors')
                    year = self._extract_year_from_publication_date(doc.get('publication_date', ''))
                    publication = doc.get('publication', 'Unknown journal')
                    
                    content.append(f"**{i}. {title}**")
                    content.append(f"- *Authors*: {authors}")
                    content.append(f"- *Publication*: {publication} ({year})")
                    content.append(f"- *Relevance Score*: {score}")
                    content.append(f"- *Reasoning*: {reasoning}")
                    
                    # Add abstract excerpt if available
                    abstract = doc.get('abstract', '')
                    if abstract:
                        abstract_excerpt = abstract[:300] + "..." if len(abstract) > 300 else abstract
                        content.append(f"- *Abstract*: {abstract_excerpt}")
                    
                    # Add reference information
                    pmid = doc.get('pmid')
                    doi = doc.get('doi')
                    ref_info = []
                    if pmid:
                        ref_info.append(f"PMID: {pmid}")
                    if doi:
                        ref_info.append(f"DOI: {doi}")
                    if ref_info:
                        content.append(f"- *Reference*: {', '.join(ref_info)}")
                    
                    content.append("")  # Empty line between studies
        
        # Extract and format contradictory citations
        contradictory_citations = analysis.get('contradictory_citations', [])
        if contradictory_citations:
            content.append("### Key Contradictory Findings")
            content.append("\nSpecific passages that challenge the original claims:\n")
            
            for i, citation_item in enumerate(contradictory_citations, 1):
                if isinstance(citation_item, dict) and 'citation' in citation_item:
                    citation = citation_item['citation']
                    original_claim = citation_item.get('original_claim', 'Unknown claim')
                    question = citation_item.get('counterfactual_question', 'Unknown question')
                    
                    # Extract citation details
                    if hasattr(citation, 'document_title'):
                        doc_title = citation.document_title
                        summary = getattr(citation, 'summary', 'No summary available')
                        passage = getattr(citation, 'passage', 'No passage available')
                        relevance = getattr(citation, 'relevance_score', 0)
                    else:
                        doc_title = str(citation)[:100]
                        summary = "Citation data unavailable"
                        passage = str(citation)[:200]
                        relevance = 0
                    
                    content.append(f"**Citation {i}: {doc_title}**")
                    content.append(f"- *Challenges Claim*: {original_claim}")
                    content.append(f"- *Research Question*: {question}")
                    content.append(f"- *Relevance Score*: {relevance:.3f}")
                    content.append(f"- *Summary*: {summary}")
                    content.append(f"- *Key Passage*: \"{passage}\"")
                    content.append("")
        
        # Add methodology note
        if contradictory_evidence or contradictory_citations:
            content.append("### Methodology Note")
            content.append("This counterfactual analysis systematically searched for evidence that might contradict or challenge the primary findings. The goal is to provide a balanced assessment of the evidence base and identify potential limitations or alternative interpretations.")
        
        return "\n".join(content)
    
    def _format_basic_counterfactual(self, analysis: Any) -> str:
        """Format basic counterfactual analysis without literature search.
        
        Args:
            analysis: Basic counterfactual analysis object
            
        Returns:
            Formatted basic counterfactual section
        """
        content = ["\n## Counterfactual Analysis", "\n### Research Questions for Finding Contradictory Evidence"]
        
        if hasattr(analysis, 'summary'):
            content.append(f"\n{analysis.summary}")
        
        if hasattr(analysis, 'questions'):
            content.append("\nThe following research questions were generated to systematically search for contradictory evidence:\n")
            for i, question in enumerate(analysis.questions[:5], 1):
                if hasattr(question, 'question'):
                    content.append(f"{i}. {question.question}")
                else:
                    content.append(f"{i}. {question}")
        
        content.append("\n*Note: This analysis identified potential areas for contradictory evidence but did not perform literature search.*")
        return "\n".join(content)
    
    def _format_structured_counterfactual(self, formatted_report: dict) -> str:
        """Format the new structured counterfactual report for inclusion in final report.

        Args:
            formatted_report: Dictionary with items, summary_statement, and statistics

        Returns:
            Formatted markdown section for the counterfactual analysis
        """
        content = ["\n## Counterfactual Evidence Analysis"]

        items = formatted_report.get('items', [])
        summary_statement = formatted_report.get('summary_statement', '')
        statistics = formatted_report.get('statistics', {})

        if not items:
            content.append("\nNo claims were analyzed for counterfactual evidence.")
            return "\n".join(content)

        # Count claims with and without evidence
        claims_with_evidence = [item for item in items if item.get('evidence_found', False)]
        claims_without_evidence = [item for item in items if not item.get('evidence_found', False)]

        content.append(f"\nThis analysis examined {len(items)} claims from the original report:")
        content.append(f"- **{len(claims_with_evidence)} claims** have contradictory evidence")
        content.append(f"- **{len(claims_without_evidence)} claims** have no contradictory evidence found")

        # Format each claim with its counterfactual evidence and assessment
        for i, item in enumerate(items, 1):
            claim = item.get('claim', 'Unknown claim')
            counterfactual_statement = item.get('counterfactual_statement', '')
            evidence_list = item.get('counterfactual_evidence', [])
            evidence_found = item.get('evidence_found', False)
            critical_assessment = item.get('critical_assessment', '')

            content.append(f"\n### Claim {i}")
            content.append(f"**Original Claim**: {claim}")
            content.append(f"\n**Counterfactual Question**: {counterfactual_statement}")

            if evidence_found and evidence_list:
                # Show contradictory evidence with details
                content.append(f"\n**Contradictory Evidence Found**: {len(evidence_list)} citation(s)")
                content.append("")

                for j, evidence in enumerate(evidence_list, 1):
                    title = evidence.get('title', 'Unknown title')
                    citation_content = evidence.get('content', 'No content available')
                    passage = evidence.get('passage', '')
                    relevance_score = evidence.get('relevance_score', 0)
                    document_score = evidence.get('document_score', 0)
                    score_reasoning = evidence.get('score_reasoning', '')

                    content.append(f"{j}. **{title}**")
                    content.append(f"   - **Relevance Scores**: Citation {relevance_score:.2f}/1.0, Document {document_score}/5")
                    content.append(f"   - **Summary**: {citation_content}")
                    if passage:
                        # Truncate long passages
                        display_passage = passage[:400] + "..." if len(passage) > 400 else passage
                        content.append(f"   - **Key Passage**: \"{display_passage}\"")
                    if score_reasoning:
                        content.append(f"   - **Scoring Rationale**: {score_reasoning}")
                    content.append("")

                # Critical assessment
                content.append(f"**Critical Assessment**: {critical_assessment}")
            else:
                # No evidence found
                content.append(f"\n**Contradictory Evidence Found**: None")
                content.append("")
                content.append(f"**Assessment**: {critical_assessment}")

        # Add overall summary
        if summary_statement:
            content.append(f"\n## Overall Counterfactual Analysis Summary")
            content.append(summary_statement)

        return "\n".join(content)
    
    def _extract_year_from_publication_date(self, pub_date: str) -> str:
        """Extract year from publication date string."""
        if not pub_date or pub_date in ['Unknown', '']:
            return 'Unknown year'
        
        # Extract year from date string (e.g., "2023-06-15" -> "2023")
        if '-' in str(pub_date):
            return str(pub_date).split('-')[0]
        
        return str(pub_date)
    
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
            if isinstance(counterfactual_analysis, dict) and counterfactual_analysis.get('contradictory_evidence'):
                contradictory_docs = len(counterfactual_analysis.get('contradictory_evidence', []))
                contradictory_citations = len(counterfactual_analysis.get('contradictory_citations', []))
                cf_description = f"**Comprehensive Counterfactual Analysis**: Literature search performed, found {contradictory_docs} contradictory studies and extracted {contradictory_citations} citations"
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
        # Get counterfactual analysis details
        cf_info = "not performed"
        if counterfactual_analysis:
            if isinstance(counterfactual_analysis, dict):
                contradictory_docs = len(counterfactual_analysis.get('contradictory_evidence', []))
                contradictory_citations = len(counterfactual_analysis.get('contradictory_citations', []))
                cf_info = f"comprehensive analysis performed, found {contradictory_docs} contradictory studies"
            else:
                cf_info = "basic analysis performed"
        
        return f"""## Limitations and Confidence

- Search limited to available database content
- Analysis performed on {len(documents)} documents
- {len(citations)} citations extracted from {len(scored_documents)} scored documents
- Counterfactual analysis: {cf_info}
- Results represent current database content and may not reflect all available literature"""
    
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