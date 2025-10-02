"""
Editor Agent for creating balanced, comprehensive medical research reports.

This agent takes original research reports and counterfactual evidence to create
balanced, well-structured markdown reports that present both supporting evidence
and contradictory findings with proper academic formatting.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from .base import BaseAgent
from ..config import get_config, get_model, get_agent_config

logger = logging.getLogger(__name__)


@dataclass
class EditedReport:
    """Represents a comprehensively edited research report."""
    title: str
    executive_summary: str
    methodology_section: str
    findings_section: str
    contradictory_evidence_section: Optional[str]
    limitations_section: str
    conclusions_section: str
    references: List[Dict[str, str]]
    evidence_quality_table: Optional[str]
    confidence_assessment: str
    word_count: int
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


class EditorAgent(BaseAgent):
    """
    Agent for creating balanced, comprehensive medical research reports.
    
    This agent performs editorial synthesis by:
    1. Analyzing original research reports and supporting evidence
    2. Incorporating counterfactual evidence and contradictory findings
    3. Creating balanced presentations of evidence strength
    4. Generating structured markdown with tables and proper references
    5. Providing confidence assessments and methodology transparency
    """
    
    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        callback: Optional[Callable[[str, str], None]] = None,
        orchestrator: Optional["AgentOrchestrator"] = None,
        show_model_info: bool = True
    ):
        """
        Initialize the EditorAgent.
        
        Args:
            model: The name of the Ollama model to use (default: from config)
            host: The Ollama server host URL (default: from config)
            temperature: Model temperature for balanced writing (default: from config)
            top_p: Model top-p sampling parameter (default: from config) 
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information on initialization
        """
        # Load configuration
        config = get_config()
        agent_config = get_agent_config("editor")
        ollama_config = config.get_ollama_config()
        
        # Use provided values or fall back to configuration
        model = model or get_model("editor_agent")
        host = host or ollama_config["host"]
        temperature = temperature if temperature is not None else agent_config.get("temperature", 0.1)
        top_p = top_p if top_p is not None else agent_config.get("top_p", 0.8)
        
        super().__init__(model, host, temperature, top_p, callback, orchestrator, show_model_info)
        
        # System prompt for comprehensive editorial work
        self.system_prompt = """You are a medical research editor specializing in evidence-based literature synthesis. Your role is to create balanced, comprehensive, and academically rigorous reports that present both supporting evidence and contradictory findings.

Your task is to:
1. Synthesize original research findings with contradictory evidence
2. Create balanced presentations that acknowledge evidence limitations
3. Generate structured markdown reports with proper academic formatting
4. Include evidence quality tables and confidence assessments
5. Provide transparent methodology sections explaining data sources
6. Create proper reference lists with consistent formatting

Guidelines for balanced reporting:
- Present supporting evidence clearly but acknowledge limitations
- Integrate contradictory evidence objectively without bias
- Use evidence grading (strong, moderate, limited, insufficient)
- Include confidence intervals and effect sizes when available
- Acknowledge methodological limitations and potential biases
- Provide clear recommendations with appropriate caveats
- Use tables and structured formatting for complex data
- Maintain academic tone while being accessible

CRITICAL TRUTHFULNESS REQUIREMENTS:
- NEVER fabricate methodology details, databases, or review processes
- ONLY describe the actual data sources provided (PubMed and medRxiv articles)
- NEVER claim systematic review methodology unless explicitly performed
- NEVER invent reviewer counts, search strategies, or inclusion criteria
- NEVER reference databases not used (e.g., Embase, Cochrane CENTRAL)
- Base methodology section ONLY on the actual process: AI-powered literature search and synthesis
- Acknowledge the automated nature of the evidence collection and analysis process
- Do NOT claim manual data extraction, independent reviewers, or consensus processes that did not occur

CRITICAL FORMATTING REQUIREMENTS:
- Use proper markdown syntax (##, ###, *, **, etc.)
- Create tables using markdown table format
- Use numbered references [1], [2], etc.
- Include evidence strength indicators (★★★★☆, etc.)
- Use appropriate medical terminology consistently
- Format citations in consistent academic style
- IMPORTANT: Use specific years instead of vague temporal references (e.g., "In a 2023 study" NOT "In a recent study")

Response Format:
Return ONLY a valid JSON object with this exact structure:

{
    "title": "Descriptive title for the research question",
    "executive_summary": "3-4 paragraph summary of key findings and conclusions",
    "methodology_section": "Truthful description of the AI-powered literature search using PubMed and medRxiv data sources - do NOT fabricate systematic review processes",
    "findings_section": "Detailed presentation of supporting evidence with subheadings",
    "contradictory_evidence_section": "Balanced presentation of conflicting or limiting evidence (null if none)",
    "limitations_section": "Discussion of study limitations, biases, and methodological concerns", 
    "conclusions_section": "Balanced conclusions with confidence levels and recommendations",
    "evidence_quality_table": "Markdown table showing evidence quality assessment (null if not applicable)",
    "confidence_assessment": "HIGH|MODERATE|LIMITED - overall confidence in conclusions",
    "word_count": 0
}

Be thorough, balanced, and maintain high academic standards throughout."""

    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "editor_agent"
    
    def create_comprehensive_report(
        self, 
        original_report: Any,
        research_question: str,
        supporting_citations: List[Any],
        contradictory_evidence: Optional[Dict[str, Any]] = None,
        confidence_analysis: Optional[Any] = None
    ) -> Optional[EditedReport]:
        """
        Create a comprehensive, balanced research report.
        
        Args:
            original_report: The original research report (Report object)
            research_question: The original research question
            supporting_citations: List of Citation objects supporting the report
            contradictory_evidence: Optional dict with contradictory evidence from counterfactual analysis
            confidence_analysis: Optional CounterfactualAnalysis object
            
        Returns:
            EditedReport object with comprehensive balanced report, None if editing fails
        """
        if not original_report or not research_question:
            logger.error("Original report and research question are required")
            return None
            
        self._call_callback("comprehensive_editing", f"Creating balanced report for: {research_question[:50]}...")
        
        # Prepare content for analysis
        content_package = self._prepare_content_package(
            original_report, research_question, supporting_citations, 
            contradictory_evidence, confidence_analysis
        )
        
        # Retry mechanism for comprehensive reports
        max_retries = 2
        for attempt in range(max_retries):
            try:
                # Prepare the editing request
                messages = [
                    {
                        'role': 'user',
                        'content': f"""Please create a comprehensive, balanced medical research report based on the following information:

RESEARCH QUESTION: {research_question}

ORIGINAL REPORT CONTENT:
{content_package['original_content']}

SUPPORTING EVIDENCE:
{content_package['supporting_evidence']}

CONTRADICTORY EVIDENCE:
{content_package['contradictory_evidence']}

CONFIDENCE ANALYSIS:
{content_package['confidence_analysis']}

Create a balanced, academically rigorous report that presents both supporting evidence and contradictory findings. Use proper markdown formatting, include evidence quality tables where appropriate, and provide transparent confidence assessments.

IMPORTANT FOR METHODOLOGY SECTION: The methodology should accurately describe the AI-powered literature search and synthesis process used. Only reference PubMed and medRxiv as data sources. Do NOT fabricate systematic review processes, independent reviewers, search dates, inclusion/exclusion criteria, or analysis methods that were not actually performed. Be truthful about the automated nature of the evidence collection and analysis."""
                    }
                ]
                
                # Get response from LLM with increased token limit for comprehensive reports
                token_limit = 6000 + (attempt * 2000)  # 6000, 8000
                response = self._make_ollama_request(
                    messages=messages,
                    system_prompt=self.system_prompt,
                    num_predict=token_limit,
                    temperature=self.temperature + (attempt * 0.05)
                )
                
                # Parse the JSON response
                try:
                    # Parse JSON response using inherited robust method from BaseAgent
                    result_data = self._parse_json_response(response)
                    
                    # Validate required fields
                    required_fields = [
                        'title', 'executive_summary', 'methodology_section', 
                        'findings_section', 'limitations_section', 'conclusions_section',
                        'references', 'confidence_assessment'
                    ]
                    for field in required_fields:
                        if field not in result_data:
                            raise ValueError(f"Missing required field: {field}")
                    
                    # Count words in main content sections
                    word_count = self._count_words([
                        result_data.get('executive_summary', ''),
                        result_data.get('methodology_section', ''),
                        result_data.get('findings_section', ''),
                        result_data.get('contradictory_evidence_section', '') or '',
                        result_data.get('limitations_section', ''),
                        result_data.get('conclusions_section', '')
                    ])
                    
                    # Create EditedReport object
                    edited_report = EditedReport(
                        title=result_data['title'],
                        executive_summary=result_data['executive_summary'],
                        methodology_section=result_data['methodology_section'],
                        findings_section=result_data['findings_section'],
                        contradictory_evidence_section=result_data.get('contradictory_evidence_section'),
                        limitations_section=result_data['limitations_section'],
                        conclusions_section=result_data['conclusions_section'],
                        references=original_report.references if hasattr(original_report, 'references') else [],
                        evidence_quality_table=result_data.get('evidence_quality_table'),
                        confidence_assessment=result_data['confidence_assessment'].upper(),
                        word_count=word_count
                    )
                    
                    self._call_callback("editing_complete", f"Generated comprehensive report ({word_count} words)")
                    return edited_report
                    
                except json.JSONDecodeError as e:
                    if len(response) < 200 or not response.strip().endswith('}'):
                        logger.warning(f"Attempt {attempt + 1}: Incomplete JSON response, retrying...")
                        if attempt < max_retries - 1:
                            continue
                    
                    logger.error(f"Failed to parse JSON response on attempt {attempt + 1}: {e}")
                    logger.error(f"Response length: {len(response)}")
                    if attempt == max_retries - 1:
                        return None
                    continue
                    
                except ValueError as e:
                    logger.warning(f"Attempt {attempt + 1}: Invalid response structure: {e}")
                    if attempt < max_retries - 1:
                        continue
                    logger.error(f"Invalid response structure after {max_retries} attempts: {e}")
                    return None
                    
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}: Error during comprehensive editing: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Error during comprehensive editing after {max_retries} attempts: {e}")
                    return None
                continue
        
        return None
    
    def _prepare_content_package(
        self, 
        original_report: Any,
        research_question: str,
        supporting_citations: List[Any],
        contradictory_evidence: Optional[Dict[str, Any]],
        confidence_analysis: Optional[Any]
    ) -> Dict[str, str]:
        """Prepare organized content package for the editor."""
        
        # Extract original report content
        original_content = []
        if hasattr(original_report, 'synthesized_answer'):
            original_content.append(f"MAIN FINDINGS:\n{original_report.synthesized_answer}")
        if hasattr(original_report, 'evidence_strength'):
            original_content.append(f"EVIDENCE STRENGTH: {original_report.evidence_strength}")
        if hasattr(original_report, 'citation_count'):
            original_content.append(f"CITATIONS ANALYZED: {original_report.citation_count}")
        
        # Format supporting citations
        supporting_evidence = []
        for i, citation in enumerate(supporting_citations[:20], 1):  # Limit to top 20 for context
            if hasattr(citation, 'document_title') and hasattr(citation, 'summary'):
                supporting_evidence.append(
                    f"{i}. {citation.document_title}\n"
                    f"   Relevance: {getattr(citation, 'relevance_score', 'N/A')}\n"
                    f"   Summary: {citation.summary}\n"
                    f"   Authors: {', '.join(getattr(citation, 'authors', [])[:3])}"
                )
        
        # Format contradictory evidence
        contradictory_content = "None identified."
        if contradictory_evidence and contradictory_evidence.get('contradictory_citations'):
            contradictory_items = []
            for i, item in enumerate(contradictory_evidence['contradictory_citations'][:10], 1):
                citation = item.get('citation', {})
                if hasattr(citation, 'document_title'):
                    contradictory_items.append(
                        f"{i}. {citation.document_title}\n"
                        f"   Contradicts: {item.get('original_claim', 'N/A')}\n"
                        f"   Evidence: {getattr(citation, 'summary', 'N/A')}\n"
                        f"   Score: {item.get('document_score', 'N/A')}/5"
                    )
            if contradictory_items:
                contradictory_content = "\n\n".join(contradictory_items)
        
        # Format confidence analysis
        confidence_content = "No confidence analysis performed."
        if confidence_analysis:
            confidence_items = []
            if hasattr(confidence_analysis, 'confidence_level'):
                confidence_items.append(f"Original Confidence: {confidence_analysis.confidence_level}")
            if hasattr(confidence_analysis, 'main_claims'):
                confidence_items.append(f"Main Claims: {len(confidence_analysis.main_claims)}")
                for i, claim in enumerate(confidence_analysis.main_claims[:5], 1):
                    confidence_items.append(f"  {i}. {claim}")
            if hasattr(confidence_analysis, 'overall_assessment'):
                confidence_items.append(f"Assessment: {confidence_analysis.overall_assessment}")
            
            if confidence_items:
                confidence_content = "\n".join(confidence_items)
        
        return {
            'original_content': "\n\n".join(original_content) if original_content else "No original content available.",
            'supporting_evidence': "\n\n".join(supporting_evidence) if supporting_evidence else "No supporting citations available.",
            'contradictory_evidence': contradictory_content,
            'confidence_analysis': confidence_content
        }
    
    def _count_words(self, text_sections: List[str]) -> int:
        """Count words in multiple text sections."""
        total_words = 0
        for section in text_sections:
            if section:
                # Simple word count - split by whitespace
                words = section.split()
                total_words += len(words)
        return total_words
    
    def format_comprehensive_markdown_template(
        self, 
        edited_report: EditedReport, 
        methodology_metadata: Optional[Any] = None
    ) -> str:
        """
        Format comprehensive report using template approach.
        LLM generates synthesis content, programmatic sections for facts.
        
        Args:
            edited_report: The edited report from LLM
            methodology_metadata: Optional methodology metadata for programmatic generation
            
        Returns:
            Formatted markdown string with programmatic references and methodology
        """
        lines = []
        
        # Title and header
        lines.append(f"# {edited_report.title}")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Evidence Confidence:** {edited_report.confidence_assessment}")
        lines.append(f"**Word Count:** {edited_report.word_count}")
        lines.append("")
        
        # Executive Summary (from LLM)
        lines.append("## Executive Summary")
        lines.append(edited_report.executive_summary)
        lines.append("")
        
        # Programmatically generated methodology section
        if methodology_metadata:
            from .reporting_agent import ReportingAgent
            reporting_agent = ReportingAgent(show_model_info=False)
            methodology_section = reporting_agent.generate_detailed_methodology(methodology_metadata)
            lines.append("## Methodology")
            lines.append(methodology_section)
        else:
            # Fallback to LLM-generated methodology if no metadata available
            lines.append("## Methodology")
            lines.append(edited_report.methodology_section)
        lines.append("")
        
        # Evidence Quality Assessment (from LLM if available)
        if edited_report.evidence_quality_table:
            lines.append("## Evidence Quality Assessment")
            lines.append(edited_report.evidence_quality_table)
            lines.append("")
        
        # Findings (from LLM)
        lines.append("## Findings")
        lines.append(edited_report.findings_section)
        lines.append("")
        
        # Contradictory Evidence (from LLM if available)
        if edited_report.contradictory_evidence_section:
            lines.append("## Contradictory Evidence")
            lines.append(edited_report.contradictory_evidence_section)
            lines.append("")
        
        # Limitations (from LLM)
        lines.append("## Limitations")
        lines.append(edited_report.limitations_section)
        lines.append("")
        
        # Conclusions (from LLM)
        lines.append("## Conclusions")
        lines.append(edited_report.conclusions_section)
        lines.append("")
        
        # Programmatically generated references section (NEVER touched by LLM)
        if edited_report.references:
            lines.append("## References")
            for ref in edited_report.references:
                # Use proper Vancouver-style formatting for Reference objects
                if hasattr(ref, 'format_vancouver_style'):
                    formatted_ref = ref.format_vancouver_style()
                    lines.append(f"{ref.number}. {formatted_ref}")
                else:
                    # Fallback for dictionary format (shouldn't happen with our fix)
                    lines.append(f"{ref.get('number', 'N/A')}. {ref.get('citation', 'Citation not available')}")
                    if ref.get('pmid'):
                        lines.append(f"   PMID: {ref['pmid']}")
            lines.append("")
        
        # Footer
        lines.append("---")
        lines.append("*Report generated by BMLibrarian Editor Agent*")
        
        return "\n".join(lines)

    def format_comprehensive_markdown(self, edited_report: EditedReport) -> str:
        """
        Format the edited report as comprehensive markdown.
        
        Args:
            edited_report: EditedReport object to format
            
        Returns:
            Complete markdown-formatted report as string
        """
        lines = []
        
        # Title
        lines.append(f"# {edited_report.title}")
        lines.append("")
        
        # Metadata
        lines.append(f"**Generated:** {edited_report.created_at.strftime('%Y-%m-%d %H:%M:%S') if edited_report.created_at else 'Unknown'}")
        lines.append(f"**Evidence Confidence:** {edited_report.confidence_assessment}")
        lines.append(f"**Word Count:** {edited_report.word_count}")
        lines.append("")
        
        # Executive Summary
        lines.append("## Executive Summary")
        lines.append(edited_report.executive_summary)
        lines.append("")
        
        # Methodology
        lines.append("## Methodology")
        lines.append(edited_report.methodology_section)
        lines.append("")
        
        # Evidence Quality Table (if available)
        if edited_report.evidence_quality_table:
            lines.append("## Evidence Quality Assessment")
            lines.append(edited_report.evidence_quality_table)
            lines.append("")
        
        # Main Findings
        lines.append("## Findings")
        lines.append(edited_report.findings_section)
        lines.append("")
        
        # Contradictory Evidence (if available)
        if edited_report.contradictory_evidence_section:
            lines.append("## Contradictory Evidence")
            lines.append(edited_report.contradictory_evidence_section)
            lines.append("")
        
        # Limitations
        lines.append("## Limitations")
        lines.append(edited_report.limitations_section)
        lines.append("")
        
        # Conclusions
        lines.append("## Conclusions")
        lines.append(edited_report.conclusions_section)
        lines.append("")
        
        # References
        if edited_report.references:
            lines.append("## References")
            for ref in edited_report.references:
                # Use proper Vancouver-style formatting for Reference objects
                if hasattr(ref, 'format_vancouver_style'):
                    formatted_ref = ref.format_vancouver_style()
                    lines.append(f"[{ref.number}] {formatted_ref}")
                else:
                    # Fallback for dictionary format (shouldn't happen with our fix)
                    lines.append(f"[{ref.get('number', 'N/A')}] {ref.get('citation', 'Citation not available')}")
                    if ref.get('pmid'):
                        lines.append(f"   PMID: {ref['pmid']}")
                lines.append("")
        
        # Footer
        lines.append("---")
        lines.append("*Report generated by BMLibrarian Editor Agent*")
        
        return "\n".join(lines)
    
    def create_evidence_summary_table(
        self, 
        supporting_citations: List[Any],
        contradictory_citations: List[Any] = None
    ) -> str:
        """
        Create a markdown table summarizing evidence strength.
        
        Args:
            supporting_citations: List of supporting Citation objects
            contradictory_citations: Optional list of contradictory citations
            
        Returns:
            Markdown table as string
        """
        lines = []
        lines.append("| Evidence Type | Count | Average Relevance | Strength |")
        lines.append("|---------------|-------|------------------|----------|")
        
        # Supporting evidence
        if supporting_citations:
            avg_relevance = sum(getattr(c, 'relevance_score', 0.0) for c in supporting_citations) / len(supporting_citations)
            strength = "★★★★☆" if avg_relevance >= 0.8 else "★★★☆☆" if avg_relevance >= 0.6 else "★★☆☆☆"
            lines.append(f"| Supporting | {len(supporting_citations)} | {avg_relevance:.2f} | {strength} |")
        
        # Contradictory evidence
        if contradictory_citations:
            avg_relevance = sum(getattr(c.get('citation', {}), 'relevance_score', 0.0) for c in contradictory_citations) / len(contradictory_citations)
            strength = "★★★★☆" if avg_relevance >= 0.8 else "★★★☆☆" if avg_relevance >= 0.6 else "★★☆☆☆"
            lines.append(f"| Contradictory | {len(contradictory_citations)} | {avg_relevance:.2f} | {strength} |")
        else:
            lines.append("| Contradictory | 0 | N/A | No evidence |")
        
        return "\n".join(lines)