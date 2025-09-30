"""
Reporting Agent for synthesizing citations into cohesive medical publication-style reports.

Takes extracted citations and generates evidence-based reports with proper
reference formatting in the style of peer-reviewed medical publications.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from .base import BaseAgent
from .citation_agent import Citation

logger = logging.getLogger(__name__)


@dataclass
class MethodologyMetadata:
    """Metadata about the research methodology and workflow."""
    # Original query information
    human_question: str
    generated_query: str
    
    # Initial search results
    total_documents_found: int
    
    # Document scoring information
    scoring_threshold: float
    documents_by_score: Dict[int, int]  # score -> count mapping
    documents_above_threshold: int
    
    # Citation extraction details
    documents_processed_for_citations: int
    citation_extraction_threshold: float
    
    # Counterfactual analysis (optional)
    counterfactual_performed: bool = False
    counterfactual_queries_generated: int = 0
    counterfactual_documents_found: int = 0
    counterfactual_citations_extracted: int = 0
    
    # Processing details
    iterative_processing_used: bool = True
    context_window_management: bool = True


@dataclass
class Reference:
    """Represents a formatted reference for a report."""
    number: int
    authors: List[str]
    title: str
    publication_date: str
    document_id: str
    pmid: Optional[str] = None
    doi: Optional[str] = None
    publication: Optional[str] = None
    
    def format_vancouver_style(self) -> str:
        """Format reference in Vancouver style for medical publications."""
        # Format authors (up to 6, then et al.)
        if len(self.authors) <= 6:
            author_str = ", ".join(self.authors)
        else:
            author_str = ", ".join(self.authors[:6]) + ", et al."
        
        # Format publication year
        # Handle both string and datetime.date objects
        if hasattr(self.publication_date, 'year'):
            # It's a datetime.date object
            year = str(self.publication_date.year)
        elif isinstance(self.publication_date, str):
            # It's a string - extract year
            year = self.publication_date.split('-')[0] if '-' in self.publication_date else self.publication_date
        else:
            # Fallback to string representation
            year = str(self.publication_date)
        
        # Start with author and title
        formatted = f"{author_str}. {self.title}."
        
        # Add journal/publication if available
        if self.publication and self.publication.strip() and self.publication.lower() != 'unknown':
            formatted += f" {self.publication}."
        
        # Add year
        formatted += f" {year}."
        
        # Add identifiers
        identifiers = []
        if self.pmid:
            identifiers.append(f"PMID: {self.pmid}")
        if self.doi:
            identifiers.append(f"DOI: {self.doi}")
        
        if identifiers:
            formatted += f" {'; '.join(identifiers)}."
        
        return formatted


@dataclass
class Report:
    """Represents a synthesized report with citations and references."""
    user_question: str
    synthesized_answer: str
    references: List[Reference]
    evidence_strength: str  # "Strong", "Moderate", "Limited", "Insufficient"
    methodology_note: str
    created_at: datetime
    citation_count: int
    unique_documents: int
    methodology_metadata: Optional[MethodologyMetadata] = None
    
    def __post_init__(self):
        if not isinstance(self.created_at, datetime):
            self.created_at = datetime.now(timezone.utc)


class ReportingAgent(BaseAgent):
    """
    Agent for synthesizing citations into cohesive medical publication-style reports.
    
    Takes output from CitationFinderAgent and creates evidence-based reports
    with proper reference formatting and medical publication style.
    """
    
    def __init__(self,
                 model: str = "gpt-oss:20b",
                 host: str = "http://localhost:11434",
                 temperature: float = 0.3,
                 top_p: float = 0.9,
                 callback: Optional[Callable[[str, str], None]] = None,
                 orchestrator=None,
                 show_model_info: bool = True):
        """
        Initialize the ReportingAgent.
        
        Args:
            model: The name of the Ollama model to use (default: gpt-oss:20b)
            host: The Ollama server host URL (default: http://localhost:11434)
            temperature: Model temperature for natural writing (default: 0.3)
            top_p: Model top-p sampling parameter (default: 0.9)
            callback: Optional callback function for progress updates
            orchestrator: Optional orchestrator for queue-based processing
            show_model_info: Whether to display model information on initialization
        """
        super().__init__(model=model, host=host, temperature=temperature, top_p=top_p,
                        callback=callback, orchestrator=orchestrator, show_model_info=show_model_info)
        self.agent_type = "reporting_agent"
    
    def get_agent_type(self) -> str:
        """Get the agent type identifier."""
        return "reporting_agent"
    
    def test_connection(self) -> bool:
        """Test connection to Ollama service."""
        try:
            import requests
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Cannot connect to Ollama at {self.host}: {e}")
            return False
    
    def create_references(self, citations: List[Citation]) -> List[Reference]:
        """
        Create numbered references from citations.
        
        Args:
            citations: List of citations to convert to references
            
        Returns:
            List of formatted references with numbers
        """
        references = []
        seen_docs = set()
        ref_number = 1
        
        for citation in citations:
            # Avoid duplicate references for the same document
            if citation.document_id not in seen_docs:
                reference = Reference(
                    number=ref_number,
                    authors=citation.authors,
                    title=citation.document_title,
                    publication_date=citation.publication_date,
                    document_id=citation.document_id,
                    pmid=citation.pmid,
                    doi=getattr(citation, 'doi', None),
                    publication=getattr(citation, 'publication', None)
                )
                references.append(reference)
                seen_docs.add(citation.document_id)
                ref_number += 1
        
        return references
    
    def map_citations_to_references(self, citations: List[Citation], 
                                  references: List[Reference]) -> Dict[str, int]:
        """
        Create mapping from document IDs to reference numbers.
        
        Args:
            citations: List of citations
            references: List of references with numbers
            
        Returns:
            Dictionary mapping document_id to reference number
        """
        doc_to_ref = {}
        for ref in references:
            doc_to_ref[ref.document_id] = ref.number
        return doc_to_ref
    
    def generate_detailed_methodology(self, metadata: MethodologyMetadata) -> str:
        """
        Generate a detailed methodology section based on workflow metadata.
        
        Args:
            metadata: MethodologyMetadata containing workflow details
            
        Returns:
            Formatted methodology section string
        """
        sections = []
        
        # Query Generation Section
        sections.append("**Search Strategy:**")
        sections.append(f"The research question '{metadata.human_question}' was converted into a database query: '{metadata.generated_query}'. ")
        sections.append(f"This query identified {metadata.total_documents_found:,} potentially relevant documents from the biomedical literature database.")
        sections.append("")
        
        # Document Scoring Section
        sections.append("**Document Relevance Assessment:**")
        sections.append(f"All {metadata.total_documents_found:,} documents were scored for relevance using AI-powered assessment with a threshold of {metadata.scoring_threshold}. ")
        
        # Score distribution
        if metadata.documents_by_score:
            score_dist = []
            for score in sorted(metadata.documents_by_score.keys(), reverse=True):
                count = metadata.documents_by_score[score]
                score_dist.append(f"score {score}: {count} documents")
            sections.append(f"Score distribution: {'; '.join(score_dist)}. ")
        
        sections.append(f"{metadata.documents_above_threshold} documents exceeded the relevance threshold and were selected for citation extraction.")
        sections.append("")
        
        # Citation Extraction Section
        sections.append("**Citation Extraction:**")
        sections.append(f"{metadata.documents_processed_for_citations} high-scoring documents were processed for citation extraction using a relevance threshold of {metadata.citation_extraction_threshold}. ")
        
        if metadata.iterative_processing_used:
            sections.append("Iterative processing was employed to ensure comprehensive coverage while managing context window limitations. ")
        
        if metadata.context_window_management:
            sections.append("Context window management techniques were used to handle large document sets efficiently.")
        
        sections.append("")
        
        # Counterfactual Analysis Section (if performed)
        if metadata.counterfactual_performed:
            sections.append("**Counterfactual Analysis:**")
            sections.append(f"To assess evidence completeness, {metadata.counterfactual_queries_generated} counterfactual research questions were generated to search for contradictory evidence. ")
            sections.append(f"This identified {metadata.counterfactual_documents_found} additional documents, yielding {metadata.counterfactual_citations_extracted} citations that provided alternative perspectives or contradictory findings.")
            sections.append("")
        
        return "\n".join(sections).strip()
    
    def assess_evidence_strength(self, citations: List[Citation]) -> str:
        """
        Assess the strength of evidence based on citation quality and quantity.
        
        Args:
            citations: List of citations to assess
            
        Returns:
            Evidence strength rating
        """
        if not citations:
            return "Insufficient"
        
        avg_relevance = sum(c.relevance_score for c in citations) / len(citations)
        citation_count = len(citations)
        unique_docs = len(set(c.document_id for c in citations))
        
        # Evidence strength criteria
        if citation_count >= 5 and unique_docs >= 3 and avg_relevance >= 0.85:
            return "Strong"
        elif citation_count >= 3 and unique_docs >= 2 and avg_relevance >= 0.75:
            return "Moderate" 
        elif citation_count >= 2 and avg_relevance >= 0.70:
            return "Limited"
        else:
            return "Insufficient"
    
    def synthesize_report(self, user_question: str, citations: List[Citation],
                         min_citations: int = 2, methodology_metadata: Optional[MethodologyMetadata] = None) -> Optional[Report]:
        """
        Synthesize citations into a cohesive medical publication-style report using iterative processing.
        
        Args:
            user_question: Original research question
            citations: List of extracted citations
            min_citations: Minimum citations required for report generation
            methodology_metadata: Optional metadata about the research workflow
            
        Returns:
            Synthesized report or None if insufficient evidence
        """
        if len(citations) < min_citations:
            logger.warning(f"Insufficient citations ({len(citations)}) for report generation")
            return None

        if not self.test_connection():
            logger.error("Cannot connect to Ollama - report synthesis unavailable")
            return None

        try:
            # Create references and mapping
            references = self.create_references(citations)
            doc_to_ref = self.map_citations_to_references(citations, references)
            
            # Process citations iteratively to build the report
            synthesized_content = self.iterative_synthesis(user_question, citations, doc_to_ref)
            
            if not synthesized_content:
                logger.error("Failed to synthesize content from citations")
                return None
            
            # Generate methodology note
            if methodology_metadata:
                methodology_note = self.generate_detailed_methodology(methodology_metadata)
            else:
                # Fallback to simple methodology note
                methodology_note = f"Evidence synthesis based on {len(citations)} citations from {len(references)} documents using iterative processing to ensure comprehensive coverage while avoiding context limits."
            
            # Assess evidence strength
            evidence_strength = self.assess_evidence_strength(citations)
            
            # Create report
            report = Report(
                user_question=user_question,
                synthesized_answer=synthesized_content,
                references=references,
                evidence_strength=evidence_strength,
                methodology_note=methodology_note,
                created_at=datetime.now(timezone.utc),
                citation_count=len(citations),
                unique_documents=len(references),
                methodology_metadata=methodology_metadata
            )
            
            logger.info(f"Successfully synthesized report with {len(citations)} citations from {len(references)} documents")
            return report
            
        except Exception as e:
            logger.error(f"Error synthesizing report: {e}")
            return None
    
    def iterative_synthesis(self, user_question: str, citations: List[Citation], 
                          doc_to_ref: Dict[str, int]) -> Optional[str]:
        """
        Iteratively process citations to build a cohesive report.
        
        Process one citation at a time, checking if it adds new information
        or should be combined with existing content.
        """
        import requests
        
        # Start with empty content
        current_content = ""
        processed_citations = []
        
        # Sort citations by relevance score (highest first)
        sorted_citations = sorted(citations, key=lambda c: c.relevance_score, reverse=True)
        
        for i, citation in enumerate(sorted_citations):
            ref_number = doc_to_ref.get(citation.document_id, '?')
            
            logger.info(f"Processing citation {i+1}/{len(citations)}: {citation.document_title[:50]}...")
            
            # Create prompt for this specific citation
            if not current_content:
                # First citation - create initial content
                prompt = f"""You are a medical writing expert. Create the opening statement for a medical research report.

Research Question: "{user_question}"

Citation to process:
Passage: "{citation.passage}"
Summary: {citation.summary}
Reference: [{ref_number}]

Your task:
1. Write 1-2 sentences that directly address the research question using this citation
2. Use formal medical writing style
3. Include the reference number [{ref_number}] after relevant statements
4. Start with a clear topic sentence
5. IMPORTANT: Use specific years instead of vague temporal references (e.g., "In a 2023 study" NOT "In a recent study")

Response format (JSON):
{{
    "content": "Your medical writing with reference [{ref_number}]",
    "addresses_question": "Brief note on how this addresses the research question"
}}

Write concisely and professionally."""
            else:
                # Subsequent citations - check if new information
                prompt = f"""You are a medical writing expert. You have existing content for a medical research report and need to decide how to incorporate a new citation.

Research Question: "{user_question}"

Current content:
{current_content}

New citation to process:
Passage: "{citation.passage}"
Summary: {citation.summary}
Reference: [{ref_number}]

Your task:
1. Determine if this citation adds NEW information not already covered
2. If NEW: Write 1-2 additional sentences with reference [{ref_number}]
3. If SUPPORTING existing point: Add reference [{ref_number}] to existing sentence
4. Maintain formal medical writing style
5. IMPORTANT: Use specific years instead of vague temporal references (e.g., "In a 2023 study" NOT "In a recent study")

Response format (JSON):
{{
    "action": "add_new" or "add_reference",
    "content": "New sentence(s) with [{ref_number}] OR updated existing content with added [{ref_number}]",
    "reasoning": "Brief explanation of decision"
}}

Be concise and avoid redundancy."""
            
            try:
                response = requests.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": self.temperature,
                            "top_p": self.top_p,
                            "num_predict": getattr(self, 'max_tokens', 2000)  # Use config max_tokens or default to 2000
                        }
                    },
                    timeout=60  # Short timeout for individual citations
                )
                
                if response.status_code != 200:
                    logger.warning(f"Failed to process citation {i+1}: HTTP {response.status_code}")
                    continue
                
                result = response.json()
                llm_response = result.get('response', '').strip()
                
                if not llm_response:
                    logger.warning(f"Empty response for citation {i+1}")
                    continue
                
                # Parse JSON response
                try:
                    citation_data = json.loads(llm_response)
                except json.JSONDecodeError:
                    # Try to extract JSON from response
                    import re
                    json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
                    if json_match:
                        citation_data = json.loads(json_match.group())
                    else:
                        logger.warning(f"Could not parse JSON for citation {i+1}: {llm_response}")
                        continue
                
                # Process the result
                if not current_content:
                    # First citation
                    current_content = citation_data.get('content', '')
                else:
                    # Subsequent citation
                    action = citation_data.get('action', 'add_new')
                    new_content = citation_data.get('content', '')
                    
                    if action == 'add_new' and new_content:
                        # Add new content
                        current_content += " " + new_content
                    elif action == 'add_reference' and new_content:
                        # Replace current content with updated version
                        current_content = new_content
                
                processed_citations.append(citation)
                
            except Exception as e:
                logger.warning(f"Error processing citation {i+1}: {e}")
                continue
        
        if not current_content:
            logger.error("No content generated from citations")
            return None
        
        # Final step: Reformat into cohesive report
        final_content = self.final_formatting(user_question, current_content)
        return final_content or current_content
    
    def final_formatting(self, user_question: str, content: str) -> Optional[str]:
        """Final formatting pass to ensure cohesive medical writing."""
        import requests
        
        prompt = f"""You are a medical writing expert. Review and reformat the following content into a cohesive medical publication-style paragraph.

Research Question: "{user_question}"

Current content:
{content}

Your task:
1. Ensure smooth transitions between sentences
2. Maintain formal medical writing style
3. Preserve all reference numbers exactly as they appear
4. Create a logical flow of information
5. Add a concluding statement if appropriate
6. IMPORTANT: Use specific years instead of vague temporal references (e.g., "In a 2023 study" NOT "In a recent study")

Response format (JSON):
{{
    "formatted_content": "Your polished, cohesive medical writing with all references preserved"
}}

Do not add or remove any reference numbers. Only improve readability and flow."""
        
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "num_predict": getattr(self, 'max_tokens', 3000)  # Use config max_tokens or default to 3000
                    }
                },
                timeout=60
            )
            
            if response.status_code != 200:
                logger.warning("Failed final formatting, using unformatted content")
                return None
            
            result = response.json()
            llm_response = result.get('response', '').strip()
            
            if not llm_response:
                return None
            
            # Parse JSON response
            try:
                format_data = json.loads(llm_response)
                return format_data.get('formatted_content')
            except json.JSONDecodeError:
                # Try to extract JSON
                import re
                json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
                if json_match:
                    format_data = json.loads(json_match.group())
                    return format_data.get('formatted_content')
                else:
                    logger.warning("Could not parse final formatting response")
                    return None
        
        except Exception as e:
            logger.warning(f"Error in final formatting: {e}")
            return None
    
    def format_report_output_template(self, report: Report) -> str:
        """
        Format report using template approach - LLM content + programmatic sections.
        
        Args:
            report: Report to format
            
        Returns:
            Formatted report string with programmatic references and methodology
        """
        output = []
        
        # Header
        output.append(f"# {report.user_question}")
        output.append("")
        output.append(f"**Evidence Strength:** {report.evidence_strength}")
        output.append("")
        
        # Main synthesized answer (this comes from LLM)
        output.append("## Key Findings")
        output.append(report.synthesized_answer)
        output.append("")
        
        # Programmatically generated methodology section
        if report.methodology_metadata:
            methodology_section = self.generate_detailed_methodology(report.methodology_metadata)
            output.append("## Methodology")
            output.append(methodology_section)
            output.append("")
        elif report.methodology_note:
            output.append("## Methodology")
            output.append(report.methodology_note)
            output.append("")
        
        # Programmatically generated references section (never touched by LLM)
        output.append("## References")
        for ref in report.references:
            formatted_ref = ref.format_vancouver_style()
            output.append(f"{ref.number}. {formatted_ref}")
        output.append("")
        
        # Report metadata
        output.append("## Report Information")
        output.append(f"- **Generated:** {report.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        output.append(f"- **Citations analyzed:** {report.citation_count}")
        output.append(f"- **Unique references:** {report.unique_documents}")
        output.append(f"- **Evidence strength:** {report.evidence_strength}")
        
        return "\n".join(output)

    def format_report_output(self, report: Report) -> str:
        """
        Format report for display with proper reference list.
        
        Args:
            report: Report to format
            
        Returns:
            Formatted report string
        """
        output = []
        
        # Header
        output.append(f"Research Question: {report.user_question}")
        output.append("=" * 80)
        output.append("")
        
        # Evidence strength indicator
        output.append(f"Evidence Strength: {report.evidence_strength}")
        output.append("")
        
        # Main synthesized answer
        output.append(report.synthesized_answer)
        output.append("")
        
        # References section
        output.append("REFERENCES")
        output.append("-" * 20)
        output.append("")
        
        for ref in report.references:
            formatted_ref = ref.format_vancouver_style()
            output.append(f"{ref.number}. {formatted_ref}")
        
        output.append("")
        
        # Methodology note
        if report.methodology_note:
            output.append("METHODOLOGY")
            output.append("-" * 20)
            output.append(report.methodology_note)
            output.append("")
        
        # Report metadata
        output.append("REPORT METADATA")
        output.append("-" * 20)
        output.append(f"Generated: {report.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        output.append(f"Citations analyzed: {report.citation_count}")
        output.append(f"Unique references: {report.unique_documents}")
        output.append(f"Evidence strength: {report.evidence_strength}")
        
        return "\n".join(output)
    
    def generate_citation_based_report(self, user_question: str, citations: List[Citation],
                                     format_output: bool = True, methodology_metadata: Optional[MethodologyMetadata] = None) -> Optional[str]:
        """
        Complete workflow: synthesize citations and format for output.
        
        Args:
            user_question: Research question
            citations: List of citations to synthesize
            format_output: Whether to format for display
            methodology_metadata: Optional metadata about the research workflow
            
        Returns:
            Formatted report string or None if synthesis failed
        """
        report = self.synthesize_report(user_question, citations, methodology_metadata=methodology_metadata)
        
        if not report:
            return None
        
        if format_output:
            return self.format_report_output(report)
        else:
            return report.synthesized_answer
    
    def validate_citations(self, citations: List[Citation]) -> Tuple[List[Citation], List[str]]:
        """
        Validate citations and return valid ones with error messages.
        
        Args:
            citations: List of citations to validate
            
        Returns:
            Tuple of (valid_citations, error_messages)
        """
        valid_citations = []
        errors = []
        
        for i, citation in enumerate(citations):
            # Check required fields
            if not citation.passage or not citation.passage.strip():
                errors.append(f"Citation {i+1}: Empty passage")
                continue
                
            if not citation.document_id:
                errors.append(f"Citation {i+1}: Missing document ID")
                continue
                
            if not citation.document_title:
                errors.append(f"Citation {i+1}: Missing document title")
                continue
                
            if citation.relevance_score < 0 or citation.relevance_score > 1:
                errors.append(f"Citation {i+1}: Invalid relevance score ({citation.relevance_score})")
                continue
            
            valid_citations.append(citation)
        
        return valid_citations, errors