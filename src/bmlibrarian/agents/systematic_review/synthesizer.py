"""
Evidence Synthesizer for Systematic Reviews.

This module provides the EvidenceSynthesizer class which extracts relevant
citations from included papers and synthesizes them into a narrative
conclusion that directly addresses the research question.

The synthesis process follows these steps:
1. Extract key passages from each included paper using CitationFinderAgent
2. Group citations by theme/finding
3. Synthesize findings into a cohesive narrative
4. Assess overall evidence strength
5. Identify limitations and gaps

This addresses the gap between paper selection and meaningful conclusions
in systematic reviews.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import ollama

from ..citation_agent import Citation, CitationFinderAgent
from .data_models import AssessedPaper, ScoredPaper

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

DEFAULT_SYNTHESIS_MODEL = "gpt-oss:20b"
DEFAULT_CITATION_MIN_RELEVANCE = 0.7
DEFAULT_MAX_CITATIONS_PER_PAPER = 3
DEFAULT_SYNTHESIS_TEMPERATURE = 0.3

# LLM generation settings
SYNTHESIS_MAX_TOKENS = 2000

# Formatting constants
MAX_AUTHORS_BEFORE_ET_AL = 3
FALLBACK_SUMMARY_MAX_LENGTH = 500
FALLBACK_MAX_FINDINGS = 5

# Evidence strength thresholds (based on citation count)
EVIDENCE_STRENGTH_MODERATE_THRESHOLD = 5
EVIDENCE_STRENGTH_LIMITED_THRESHOLD = 2


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class ExtractedCitation:
    """
    A citation extracted from a paper for the synthesis.

    Attributes:
        document_id: Database ID of the source document
        paper_title: Title of the source paper
        authors: List of author names
        year: Publication year
        passage: Exact text extracted from abstract
        summary: Brief summary of how this addresses the question
        relevance_score: Confidence in relevance (0-1)
        pmid: PubMed ID if available
        doi: DOI if available
    """

    document_id: int
    paper_title: str
    authors: List[str]
    year: int
    passage: str
    summary: str
    relevance_score: float
    pmid: Optional[str] = None
    doi: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "document_id": self.document_id,
            "paper_title": self.paper_title,
            "authors": self.authors,
            "year": self.year,
            "passage": self.passage,
            "summary": self.summary,
            "relevance_score": self.relevance_score,
            "pmid": self.pmid,
            "doi": self.doi,
        }

    @classmethod
    def from_citation(
        cls,
        citation: Citation,
        paper: AssessedPaper,
    ) -> "ExtractedCitation":
        """
        Create ExtractedCitation from Citation and AssessedPaper.

        Args:
            citation: Citation from CitationFinderAgent
            paper: Source AssessedPaper

        Returns:
            New ExtractedCitation instance
        """
        return cls(
            document_id=paper.scored_paper.paper.document_id,
            paper_title=paper.scored_paper.paper.title,
            authors=paper.scored_paper.paper.authors,
            year=paper.scored_paper.paper.year,
            passage=citation.passage,
            summary=citation.summary,
            relevance_score=citation.relevance_score,
            pmid=paper.scored_paper.paper.pmid,
            doi=paper.scored_paper.paper.doi,
        )


@dataclass
class EvidenceSynthesis:
    """
    Synthesized evidence from the included papers.

    Attributes:
        research_question: The original research question
        executive_summary: Direct answer to the research question (2-3 sentences)
        evidence_narrative: Full narrative synthesizing all findings
        key_findings: List of main findings with supporting citations
        evidence_strength: Overall evidence strength (Strong/Moderate/Limited/Insufficient)
        limitations: Identified gaps and limitations
        citations: All extracted citations used in synthesis
        citation_count: Total number of citations extracted
        paper_count: Number of papers with citations
    """

    research_question: str
    executive_summary: str
    evidence_narrative: str
    key_findings: List[Dict[str, Any]]
    evidence_strength: str
    limitations: List[str]
    citations: List[ExtractedCitation]
    citation_count: int
    paper_count: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "research_question": self.research_question,
            "executive_summary": self.executive_summary,
            "evidence_narrative": self.evidence_narrative,
            "key_findings": self.key_findings,
            "evidence_strength": self.evidence_strength,
            "limitations": self.limitations,
            "citations": [c.to_dict() for c in self.citations],
            "citation_count": self.citation_count,
            "paper_count": self.paper_count,
        }


# =============================================================================
# LLM Prompts
# =============================================================================

SYNTHESIS_SYSTEM_PROMPT = """You are an expert medical researcher synthesizing evidence from a systematic review.
Your task is to analyze extracted citations and produce a cohesive narrative that directly answers the research question.

Guidelines:
1. Focus on what the evidence actually shows, not speculation
2. Note the strength and consistency of findings across studies
3. Identify any contradictory findings and explain possible reasons
4. Be specific about effect sizes, outcomes, and population characteristics
5. Acknowledge limitations and gaps in the evidence
6. Use clear, academic language suitable for medical publication
7. Reference studies using [author, year] format inline"""

SYNTHESIS_PROMPT_TEMPLATE = """Based on the following evidence from a systematic review, synthesize a comprehensive answer to the research question.

## Research Question
{research_question}

## Evidence from Included Studies

{evidence_text}

## Instructions

Provide your synthesis in the following JSON format:
{{
    "executive_summary": "A 2-3 sentence direct answer to the research question based on the evidence",
    "evidence_narrative": "A comprehensive 3-5 paragraph narrative synthesizing all findings, citing studies inline as [Author, Year]",
    "key_findings": [
        {{
            "finding": "Main finding statement",
            "supporting_studies": ["Author1 2023", "Author2 2022"],
            "strength": "strong|moderate|limited"
        }}
    ],
    "limitations": ["List of identified gaps or limitations in the evidence"],
    "evidence_strength": "Strong|Moderate|Limited|Insufficient"
}}

Respond ONLY with the JSON object, no additional text."""


# =============================================================================
# Evidence Synthesizer
# =============================================================================


class EvidenceSynthesizer:
    """
    Synthesizes evidence from included papers into narrative conclusions.

    This class:
    1. Extracts relevant citations from each included paper
    2. Synthesizes citations into a cohesive narrative answer
    3. Assesses overall evidence strength
    4. Identifies limitations and gaps

    Example:
        >>> synthesizer = EvidenceSynthesizer()
        >>> synthesis = synthesizer.synthesize(
        ...     research_question="What are the effects of NSAIDs on UTI symptoms?",
        ...     included_papers=assessed_papers,
        ... )
        >>> print(synthesis.executive_summary)
    """

    def __init__(
        self,
        model: str = DEFAULT_SYNTHESIS_MODEL,
        citation_model: Optional[str] = None,
        temperature: float = DEFAULT_SYNTHESIS_TEMPERATURE,
        citation_min_relevance: float = DEFAULT_CITATION_MIN_RELEVANCE,
        max_citations_per_paper: int = DEFAULT_MAX_CITATIONS_PER_PAPER,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ):
        """
        Initialize the EvidenceSynthesizer.

        Args:
            model: LLM model for synthesis
            citation_model: LLM model for citation extraction (defaults to model)
            temperature: Temperature for synthesis generation
            citation_min_relevance: Minimum relevance score for citations
            max_citations_per_paper: Maximum citations to extract per paper
            progress_callback: Optional callback(message, current, total)
        """
        self.model = model
        self.citation_model = citation_model or model
        self.temperature = temperature
        self.citation_min_relevance = citation_min_relevance
        self.max_citations_per_paper = max_citations_per_paper
        self.progress_callback = progress_callback

        # Statistics
        self._papers_processed = 0
        self._citations_extracted = 0
        self._extraction_failures = 0

    def synthesize(
        self,
        research_question: str,
        included_papers: List[AssessedPaper],
    ) -> EvidenceSynthesis:
        """
        Synthesize evidence from included papers.

        Args:
            research_question: The research question to answer
            included_papers: Papers that passed quality gate

        Returns:
            EvidenceSynthesis with narrative answer and citations
        """
        logger.info(
            f"Synthesizing evidence from {len(included_papers)} papers "
            f"for question: {research_question[:100]}..."
        )

        # Step 1: Extract citations from each paper
        all_citations = self._extract_citations(research_question, included_papers)

        if not all_citations:
            logger.warning("No citations extracted, returning empty synthesis")
            return self._create_empty_synthesis(research_question)

        # Step 2: Synthesize citations into narrative
        synthesis = self._synthesize_narrative(research_question, all_citations)

        logger.info(
            f"Synthesis complete: {len(all_citations)} citations from "
            f"{self._papers_processed} papers, strength={synthesis.evidence_strength}"
        )

        return synthesis

    def _extract_citations(
        self,
        research_question: str,
        papers: List[AssessedPaper],
    ) -> List[ExtractedCitation]:
        """
        Extract relevant citations from all papers.

        Args:
            research_question: Research question for context
            papers: Papers to extract from

        Returns:
            List of ExtractedCitation objects
        """
        # Initialize citation agent
        citation_agent = CitationFinderAgent(model=self.citation_model)

        all_citations: List[ExtractedCitation] = []
        self._papers_processed = 0
        self._citations_extracted = 0
        self._extraction_failures = 0

        for i, paper in enumerate(papers):
            if self.progress_callback:
                self.progress_callback(
                    f"Extracting citations from: {paper.scored_paper.paper.title[:50]}...",
                    i + 1,
                    len(papers),
                )

            try:
                # Build document dict for citation agent
                document = {
                    "id": str(paper.scored_paper.paper.document_id),
                    "title": paper.scored_paper.paper.title,
                    "abstract": paper.scored_paper.paper.abstract or "",
                    "authors": paper.scored_paper.paper.authors,
                    "publication_date": str(paper.scored_paper.paper.year),
                    "pmid": paper.scored_paper.paper.pmid,
                    "doi": paper.scored_paper.paper.doi,
                }

                # Extract citation
                citation = citation_agent.extract_citation_from_document(
                    user_question=research_question,
                    document=document,
                    min_relevance=self.citation_min_relevance,
                )

                if citation:
                    extracted = ExtractedCitation.from_citation(citation, paper)
                    all_citations.append(extracted)
                    self._citations_extracted += 1

                    # Store in paper for later use
                    if paper.scored_paper.relevant_citations is None:
                        paper.scored_paper.relevant_citations = []
                    paper.scored_paper.relevant_citations.append(extracted.to_dict())

                self._papers_processed += 1

            except Exception as e:
                logger.warning(
                    f"Failed to extract citation from paper {paper.scored_paper.paper.document_id}: {e}"
                )
                self._extraction_failures += 1

        logger.info(
            f"Citation extraction complete: {self._citations_extracted} citations "
            f"from {self._papers_processed} papers, {self._extraction_failures} failures"
        )

        return all_citations

    def _synthesize_narrative(
        self,
        research_question: str,
        citations: List[ExtractedCitation],
    ) -> EvidenceSynthesis:
        """
        Synthesize citations into a narrative answer.

        Args:
            research_question: Research question to answer
            citations: Extracted citations to synthesize

        Returns:
            EvidenceSynthesis with narrative and findings
        """
        # Build evidence text for prompt
        evidence_text = self._format_evidence_for_prompt(citations)

        # Generate synthesis using LLM
        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
            research_question=research_question,
            evidence_text=evidence_text,
        )

        try:
            response = ollama.generate(
                model=self.model,
                prompt=prompt,
                system=SYNTHESIS_SYSTEM_PROMPT,
                options={
                    "temperature": self.temperature,
                    "num_predict": SYNTHESIS_MAX_TOKENS,
                },
            )

            response_text = response.get("response", "").strip()

            # Parse JSON response
            synthesis_data = self._parse_synthesis_response(response_text)

            return EvidenceSynthesis(
                research_question=research_question,
                executive_summary=synthesis_data.get("executive_summary", ""),
                evidence_narrative=synthesis_data.get("evidence_narrative", ""),
                key_findings=synthesis_data.get("key_findings", []),
                evidence_strength=synthesis_data.get("evidence_strength", "Insufficient"),
                limitations=synthesis_data.get("limitations", []),
                citations=citations,
                citation_count=len(citations),
                paper_count=self._papers_processed,
            )

        except Exception as e:
            logger.error(f"Failed to synthesize narrative: {e}")
            return self._create_fallback_synthesis(research_question, citations)

    def _format_evidence_for_prompt(
        self,
        citations: List[ExtractedCitation],
    ) -> str:
        """
        Format citations for the synthesis prompt.

        Args:
            citations: Citations to format

        Returns:
            Formatted evidence text
        """
        evidence_parts = []

        for i, citation in enumerate(citations, 1):
            # Format author list
            if len(citation.authors) > MAX_AUTHORS_BEFORE_ET_AL:
                author_str = f"{citation.authors[0]} et al."
            else:
                author_str = ", ".join(citation.authors)

            evidence_parts.append(
                f"### Study {i}: {author_str} ({citation.year})\n"
                f"**Title:** {citation.paper_title}\n"
                f"**Key Passage:** \"{citation.passage}\"\n"
                f"**Summary:** {citation.summary}\n"
                f"**Relevance Score:** {citation.relevance_score:.2f}\n"
            )

        return "\n".join(evidence_parts)

    def _parse_synthesis_response(self, response_text: str) -> Dict[str, Any]:
        """
        Parse JSON response from synthesis LLM.

        Args:
            response_text: Raw LLM response

        Returns:
            Parsed synthesis data
        """
        import json

        # Handle markdown code blocks
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()

        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse synthesis JSON: {e}")
            # Try to extract what we can
            return {
                "executive_summary": response_text[:FALLBACK_SUMMARY_MAX_LENGTH] if response_text else "",
                "evidence_narrative": response_text,
                "key_findings": [],
                "limitations": [],
                "evidence_strength": "Insufficient",
            }

    def _create_empty_synthesis(self, research_question: str) -> EvidenceSynthesis:
        """Create an empty synthesis when no citations are available."""
        return EvidenceSynthesis(
            research_question=research_question,
            executive_summary="Insufficient evidence to answer the research question.",
            evidence_narrative="No relevant citations could be extracted from the included papers.",
            key_findings=[],
            evidence_strength="Insufficient",
            limitations=["No citations extracted from included papers"],
            citations=[],
            citation_count=0,
            paper_count=0,
        )

    def _create_fallback_synthesis(
        self,
        research_question: str,
        citations: List[ExtractedCitation],
    ) -> EvidenceSynthesis:
        """Create a fallback synthesis when LLM synthesis fails."""
        # Create basic findings from citations
        key_findings = []
        for citation in citations[:FALLBACK_MAX_FINDINGS]:
            key_findings.append({
                "finding": citation.summary,
                "supporting_studies": [f"{citation.authors[0] if citation.authors else 'Unknown'} {citation.year}"],
                "strength": "limited",
            })

        # Assess evidence strength based on citation count
        if len(citations) >= EVIDENCE_STRENGTH_MODERATE_THRESHOLD:
            strength = "Moderate"
        elif len(citations) >= EVIDENCE_STRENGTH_LIMITED_THRESHOLD:
            strength = "Limited"
        else:
            strength = "Insufficient"

        return EvidenceSynthesis(
            research_question=research_question,
            executive_summary=f"Based on {len(citations)} extracted citations from {self._papers_processed} papers.",
            evidence_narrative="Automated synthesis failed. Please review individual citations below.",
            key_findings=key_findings,
            evidence_strength=strength,
            limitations=["Automated synthesis failed - manual review recommended"],
            citations=citations,
            citation_count=len(citations),
            paper_count=self._papers_processed,
        )

    def get_statistics(self) -> Dict[str, int]:
        """
        Get extraction statistics.

        Returns:
            Dictionary with extraction stats
        """
        return {
            "papers_processed": self._papers_processed,
            "citations_extracted": self._citations_extracted,
            "extraction_failures": self._extraction_failures,
        }
