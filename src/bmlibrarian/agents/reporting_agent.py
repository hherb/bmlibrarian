"""
Reporting Agent for synthesizing citations into cohesive medical publication-style reports.

Takes extracted citations and generates evidence-based reports with proper
reference formatting in the style of peer-reviewed medical publications.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

from .base import BaseAgent
from .citation_agent import Citation

logger = logging.getLogger(__name__)


@dataclass
class Reference:
    """Represents a formatted reference for a report."""
    number: int
    authors: List[str]
    title: str
    publication_date: str
    document_id: str
    pmid: Optional[str] = None
    
    def format_vancouver_style(self) -> str:
        """Format reference in Vancouver style for medical publications."""
        # Format authors (up to 6, then et al.)
        if len(self.authors) <= 6:
            author_str = ", ".join(self.authors)
        else:
            author_str = ", ".join(self.authors[:6]) + ", et al."
        
        # Format publication year
        year = self.publication_date.split('-')[0] if '-' in self.publication_date else self.publication_date
        
        # Basic Vancouver format
        formatted = f"{author_str}. {self.title}. {year}"
        
        if self.pmid:
            formatted += f"; PMID: {self.pmid}"
        
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
    
    def __post_init__(self):
        if not isinstance(self.created_at, datetime):
            self.created_at = datetime.now(timezone.utc)


class ReportingAgent(BaseAgent):
    """
    Agent for synthesizing citations into cohesive medical publication-style reports.
    
    Takes output from CitationFinderAgent and creates evidence-based reports
    with proper reference formatting and medical publication style.
    """
    
    def __init__(self, orchestrator=None, ollama_url: str = "http://localhost:11434", 
                 model: str = "gpt-oss:20b"):
        super().__init__(model=model, host=ollama_url, orchestrator=orchestrator)
        self.agent_type = "reporting_agent"
        # Higher temperature for more natural writing
        self.temperature = 0.3
    
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
                    pmid=citation.pmid
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
                         min_citations: int = 2) -> Optional[Report]:
        """
        Synthesize citations into a cohesive medical publication-style report.
        
        Args:
            user_question: Original research question
            citations: List of extracted citations
            min_citations: Minimum citations required for report generation
            
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
            
            # Build prompt for synthesis
            citations_text = "\n\n".join([
                f"Citation {doc_to_ref.get(c.document_id, '?')}: {c.passage}\n"
                f"Source: {c.document_title}\n"
                f"Summary: {c.summary}\n"
                f"Relevance: {c.relevance_score:.2f}"
                for c in citations
            ])
            
            prompt = f"""You are a medical writing expert tasked with synthesizing research citations into a cohesive, evidence-based answer in the style of a peer-reviewed medical publication.

Research Question: "{user_question}"

Available Citations:
{citations_text}

Your task:
1. Write a comprehensive, evidence-based answer that synthesizes information from the citations
2. Use formal medical writing style appropriate for peer-reviewed publications
3. Include in-text citations using numbered references [1], [2], etc.
4. Ensure all claims are supported by the provided citations
5. Be objective and present limitations where evidence is incomplete
6. Structure the response with clear paragraphs and logical flow

Guidelines:
- Start with a clear statement addressing the research question
- Present evidence in a logical sequence
- Use medical terminology appropriately
- Include numbered citations [1], [2] etc. after relevant statements
- Conclude with a summary of findings and their implications
- Mention any limitations of the available evidence

Response format (JSON):
{{
    "synthesized_answer": "Your comprehensive, well-structured answer with numbered citations",
    "methodology_note": "Brief note about the synthesis methodology and any limitations"
}}

Write in the formal, objective style of medical literature. Ensure every major claim is supported by appropriate citations."""
            
            # Make request to Ollama
            import requests
            
            response = requests.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "top_p": self.top_p
                    }
                },
                timeout=60
            )
            
            if response.status_code != 200:
                logger.error(f"Ollama request failed: {response.status_code}")
                return None
            
            result = response.json()
            llm_response = result.get('response', '').strip()
            
            if not llm_response:
                logger.warning("Empty response from model for report synthesis")
                return None
            
            # Parse JSON response
            try:
                synthesis_data = json.loads(llm_response)
            except json.JSONDecodeError:
                # Try to extract JSON from response if wrapped in text
                import re
                json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
                if json_match:
                    synthesis_data = json.loads(json_match.group())
                else:
                    logger.error(f"Could not parse JSON from synthesis response: {llm_response}")
                    return None
            
            # Assess evidence strength
            evidence_strength = self.assess_evidence_strength(citations)
            
            # Create report
            report = Report(
                user_question=user_question,
                synthesized_answer=synthesis_data['synthesized_answer'],
                references=references,
                evidence_strength=evidence_strength,
                methodology_note=synthesis_data.get('methodology_note', ''),
                created_at=datetime.now(timezone.utc),
                citation_count=len(citations),
                unique_documents=len(references)
            )
            
            logger.info(f"Successfully synthesized report with {len(citations)} citations from {len(references)} documents")
            return report
            
        except Exception as e:
            logger.error(f"Error synthesizing report: {e}")
            return None
    
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
                                     format_output: bool = True) -> Optional[str]:
        """
        Complete workflow: synthesize citations and format for output.
        
        Args:
            user_question: Research question
            citations: List of citations to synthesize
            format_output: Whether to format for display
            
        Returns:
            Formatted report string or None if synthesis failed
        """
        report = self.synthesize_report(user_question, citations)
        
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