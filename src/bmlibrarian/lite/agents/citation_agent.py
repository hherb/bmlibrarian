"""
Lite citation extraction agent.

This agent extracts relevant passages from documents that help answer
a research question. It identifies specific quotes and findings that
can be used as citations in a research report.
"""

import json
import logging
import re
from typing import Optional, Callable

from ..data_models import Citation, ScoredDocument
from .base import LiteBaseAgent

logger = logging.getLogger(__name__)

# System prompt for citation extraction
CITATION_SYSTEM_PROMPT = """You are a medical research citation extractor. Your task is to identify the most relevant passages from a document that help answer a research question.

Extract 1-3 key passages that:
1. Directly address the research question
2. Contain specific findings, data, or conclusions
3. Are self-contained and understandable out of context
4. Could be quoted in a research summary

Guidelines:
- Extract exact quotes from the abstract when possible
- Focus on passages with specific numbers, percentages, or outcomes
- Include key conclusions or recommendations
- Each passage should add unique value

Respond in JSON format:
{
    "passages": [
        {
            "text": "<exact or close quote from the abstract>",
            "relevance": "<brief explanation of why this passage is relevant>"
        }
    ]
}"""


class LiteCitationAgent(LiteBaseAgent):
    """
    Stateless citation extraction agent.

    Extracts relevant passages from documents that answer a research question.
    These passages can be used as citations in a research report.

    This agent:
    1. Takes a research question and scored document
    2. Uses LLM to identify relevant passages
    3. Returns citations with source attribution
    """

    def extract_citations(
        self,
        question: str,
        scored_doc: ScoredDocument,
    ) -> list[Citation]:
        """
        Extract citations from a scored document.

        Args:
            question: Research question
            scored_doc: Document with relevance score

        Returns:
            List of extracted citations
        """
        doc = scored_doc.document

        user_prompt = f"""Research Question: {question}

Document Title: {doc.title}
Authors: {doc.formatted_authors}
Year: {doc.year or 'Unknown'}
Journal: {doc.journal or 'Unknown'}
Relevance Score: {scored_doc.score}/5

Abstract:
{doc.abstract}

Extract the most relevant passages that help answer the research question."""

        messages = [
            self._create_system_message(CITATION_SYSTEM_PROMPT),
            self._create_user_message(user_prompt),
        ]

        try:
            response = self._chat(messages, temperature=0.1, json_mode=True)
            passages = self._parse_citation_response(response)

            citations = []
            for passage in passages:
                citation = Citation(
                    document=doc,
                    passage=passage["text"],
                    relevance_score=scored_doc.score,
                    context=passage.get("relevance", ""),
                )
                citations.append(citation)

            return citations

        except Exception as e:
            logger.error(f"Failed to extract citations from {doc.id}: {e}")
            # Return a basic citation using the abstract
            truncated = doc.abstract[:500] if len(doc.abstract) > 500 else doc.abstract
            return [Citation(
                document=doc,
                passage=truncated,
                relevance_score=scored_doc.score,
                context="Full abstract (extraction failed)",
            )]

    def extract_all_citations(
        self,
        question: str,
        scored_documents: list[ScoredDocument],
        min_score: int = 3,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[Citation]:
        """
        Extract citations from all scored documents.

        Args:
            question: Research question
            scored_documents: Documents to extract from
            min_score: Minimum score to process
            progress_callback: Optional callback(current, total)

        Returns:
            List of all extracted citations
        """
        all_citations = []
        eligible = [d for d in scored_documents if d.score >= min_score]
        total = len(eligible)

        logger.info(f"Extracting citations from {total} documents")

        for i, scored_doc in enumerate(eligible):
            if progress_callback:
                progress_callback(i + 1, total)

            citations = self.extract_citations(question, scored_doc)
            all_citations.extend(citations)

            logger.debug(
                f"Extracted {len(citations)} citations from {scored_doc.document.id}"
            )

        logger.info(
            f"Extracted {len(all_citations)} total citations from {total} documents"
        )
        return all_citations

    def _parse_citation_response(self, response: str) -> list[dict]:
        """
        Parse LLM response to extract passages.

        Args:
            response: LLM response text

        Returns:
            List of passage dictionaries
        """
        try:
            # Try to find JSON with passages array
            # Handle various JSON formats
            json_match = re.search(
                r'\{\s*"passages"\s*:\s*\[.*?\]\s*\}',
                response,
                re.DOTALL
            )
            if json_match:
                data = json.loads(json_match.group())
                passages = data.get("passages", [])
                # Validate passages
                valid_passages = []
                for p in passages:
                    if isinstance(p, dict) and "text" in p:
                        valid_passages.append(p)
                return valid_passages

            # Try parsing the entire response as JSON
            data = json.loads(response)
            if "passages" in data:
                return data["passages"]

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.debug(f"JSON parsing failed: {e}")

        # Fallback: return empty list
        logger.warning(f"Could not parse citations from: {response[:100]}...")
        return []

    def group_citations_by_document(
        self,
        citations: list[Citation],
    ) -> dict[str, list[Citation]]:
        """
        Group citations by their source document.

        Args:
            citations: List of citations

        Returns:
            Dictionary mapping document IDs to their citations
        """
        grouped: dict[str, list[Citation]] = {}
        for citation in citations:
            doc_id = citation.document.id
            if doc_id not in grouped:
                grouped[doc_id] = []
            grouped[doc_id].append(citation)
        return grouped

    def deduplicate_citations(
        self,
        citations: list[Citation],
    ) -> list[Citation]:
        """
        Remove duplicate citations based on passage text.

        Args:
            citations: List of citations

        Returns:
            Deduplicated list of citations
        """
        seen_passages: set[str] = set()
        unique_citations = []

        for citation in citations:
            # Normalize passage for comparison
            normalized = citation.passage.strip().lower()
            if normalized not in seen_passages:
                seen_passages.add(normalized)
                unique_citations.append(citation)

        return unique_citations
