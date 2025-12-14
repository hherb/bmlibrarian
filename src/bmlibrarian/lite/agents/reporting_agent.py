"""
Lite report generation agent.

This agent synthesizes evidence from multiple citations into a coherent,
professional research summary with proper attribution.
"""

import logging
from typing import Optional

from ..data_models import Citation
from .base import LiteBaseAgent

logger = logging.getLogger(__name__)

# System prompt for report generation
REPORTING_SYSTEM_PROMPT = """You are a medical research report writer. Your task is to synthesize evidence from multiple sources into a coherent, professional research summary.

Guidelines:
1. Write in clear, professional medical prose
2. Cite sources using [Author, Year] format in the text
3. Organize findings by themes or topics, not by source
4. Include specific data and findings when available
5. Note any conflicting or contrasting evidence
6. Conclude with a summary of the key findings
7. Use specific years (e.g., "In a 2023 study") - NEVER use vague phrases like "recent studies" or "recently"

Structure your report with:
- An introduction addressing the research question
- Body paragraphs organized thematically
- A conclusion summarizing key findings

Do NOT simply list sources - synthesize the information into a flowing narrative."""


class LiteReportingAgent(LiteBaseAgent):
    """
    Stateless report generation agent.

    Synthesizes citations into a coherent research report with proper
    attribution and a references section.

    This agent:
    1. Takes a research question and list of citations
    2. Uses LLM to synthesize findings into a narrative
    3. Returns a formatted report with references
    """

    def generate_report(
        self,
        question: str,
        citations: list[Citation],
    ) -> str:
        """
        Generate a research report from citations.

        Args:
            question: Research question
            citations: List of citations to synthesize

        Returns:
            Formatted research report as markdown
        """
        if not citations:
            return self._generate_no_evidence_report(question)

        # Format citations for the prompt
        formatted_citations = self._format_citations_for_prompt(citations)

        user_prompt = f"""Research Question: {question}

Evidence from {len(citations)} source passages:

{formatted_citations}

Write a comprehensive research summary that synthesizes this evidence to answer the research question. Include proper citations in [Author, Year] format throughout the text."""

        messages = [
            self._create_system_message(REPORTING_SYSTEM_PROMPT),
            self._create_user_message(user_prompt),
        ]

        try:
            report = self._chat(messages, temperature=0.3, max_tokens=4096)

            # Add references section
            references = self._format_references(citations)
            full_report = f"{report}\n\n## References\n\n{references}"

            return full_report

        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            return f"Error generating report: {str(e)}"

    def generate_brief_summary(
        self,
        question: str,
        citations: list[Citation],
        max_length: int = 500,
    ) -> str:
        """
        Generate a brief summary of findings.

        Args:
            question: Research question
            citations: List of citations
            max_length: Approximate maximum length in characters

        Returns:
            Brief summary text
        """
        if not citations:
            return "No relevant evidence was found for this research question."

        formatted_citations = self._format_citations_for_prompt(citations[:5])  # Limit for brevity

        user_prompt = f"""Research Question: {question}

Evidence from selected sources:

{formatted_citations}

Write a brief summary (approximately {max_length} characters) of the key findings. Include citations."""

        messages = [
            self._create_system_message(
                "You are a concise medical summarizer. "
                "Provide brief, accurate summaries with citations."
            ),
            self._create_user_message(user_prompt),
        ]

        try:
            return self._chat(messages, temperature=0.2, max_tokens=1024)
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return f"Error generating summary: {str(e)}"

    def _generate_no_evidence_report(self, question: str) -> str:
        """
        Generate a report when no evidence is found.

        Args:
            question: Research question

        Returns:
            Report text explaining no evidence was found
        """
        return f"""## Research Summary

**Research Question:** {question}

No relevant evidence was found in the searched literature. This may indicate:

1. The topic has limited published research
2. The search terms may need refinement
3. The research question may need to be rephrased

### Recommendations

- Try broadening the search terms
- Consider related topics that may provide indirect evidence
- Check if the question can be broken into sub-questions
- Search additional databases or preprint servers

---

*No citations available*
"""

    def _format_citations_for_prompt(self, citations: list[Citation]) -> str:
        """
        Format citations for the LLM prompt.

        Args:
            citations: List of citations

        Returns:
            Formatted string with numbered citations
        """
        formatted = []
        for i, citation in enumerate(citations, 1):
            doc = citation.document
            formatted.append(f"""[{i}] {doc.formatted_authors} ({doc.year or 'n.d.'})
Title: {doc.title}
Journal: {doc.journal or 'Unknown'}
Passage: "{citation.passage}"
""")
        return "\n".join(formatted)

    def _format_references(self, citations: list[Citation]) -> str:
        """
        Format reference list for the report.

        Args:
            citations: List of citations

        Returns:
            Formatted reference list
        """
        # Deduplicate by document ID
        seen: set[str] = set()
        unique_citations = []
        for citation in citations:
            if citation.document.id not in seen:
                seen.add(citation.document.id)
                unique_citations.append(citation)

        references = []
        for i, citation in enumerate(unique_citations, 1):
            doc = citation.document
            ref = f"{i}. {doc.formatted_authors}"
            if doc.year:
                ref += f" ({doc.year})"
            ref += f". {doc.title}"
            if doc.journal:
                ref += f". *{doc.journal}*"
            if doc.doi:
                ref += f". DOI: {doc.doi}"
            if doc.pmid:
                ref += f". PMID: {doc.pmid}"
            references.append(ref)

        return "\n".join(references)

    def get_citation_count(self, citations: list[Citation]) -> int:
        """
        Get unique document count from citations.

        Args:
            citations: List of citations

        Returns:
            Number of unique source documents
        """
        return len(set(c.document.id for c in citations))

    def export_report_with_metadata(
        self,
        question: str,
        report: str,
        citations: list[Citation],
    ) -> dict:
        """
        Export report with metadata for saving.

        Args:
            question: Research question
            report: Generated report text
            citations: List of citations used

        Returns:
            Dictionary with report and metadata
        """
        unique_docs = set()
        for c in citations:
            unique_docs.add(c.document.id)

        return {
            "research_question": question,
            "report": report,
            "citation_count": len(citations),
            "unique_source_count": len(unique_docs),
            "sources": [
                {
                    "id": c.document.id,
                    "title": c.document.title,
                    "authors": c.document.formatted_authors,
                    "year": c.document.year,
                    "pmid": c.document.pmid,
                    "passage": c.passage,
                }
                for c in citations
            ],
        }
