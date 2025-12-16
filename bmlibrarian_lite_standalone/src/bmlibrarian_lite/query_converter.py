"""
Simplified query converter for BMLibrarian Lite.

Generates concise, focused PubMed queries without excessive synonym expansion.
This is optimized for quick searches that actually return results, rather than
comprehensive queries that often fail due to length limits.

Usage:
    from bmlibrarian_lite.query_converter import LiteQueryConverter

    converter = LiteQueryConverter(llm_client=client, model="anthropic:claude-sonnet-4")
    query = converter.convert("What is the normal optic nerve sheath diameter?")
    print(query.query_string)
    # Output: optic nerve sheath diameter[tiab] AND normal[tiab] OR reference[tiab]
"""

import json
import logging
import re
from typing import Optional

from bmlibrarian_lite.llm import LLMClient, LLMMessage
from bmlibrarian_lite.pubmed.data_types import PubMedQuery

logger = logging.getLogger(__name__)


# Maximum terms per concept to keep queries manageable
MAX_MESH_TERMS_PER_CONCEPT = 2
MAX_KEYWORDS_PER_CONCEPT = 3
MAX_TOTAL_QUERY_LENGTH = 1500


LITE_QUERY_PROMPT = """Convert this research question into a concise PubMed search query.

Research Question: {question}

Instructions:
1. Identify 2-4 key concepts from the question
2. For each concept, provide:
   - 1-2 MeSH terms (official PubMed Medical Subject Headings)
   - 1-3 important keywords for title/abstract search
3. Keep it CONCISE - fewer, more specific terms find better results than many broad terms
4. DO NOT add excessive synonyms or abbreviations

Output ONLY valid JSON:
{{
  "concepts": [
    {{
      "name": "brief description",
      "mesh_terms": ["MeSH Term 1"],
      "keywords": ["keyword1", "keyword2"]
    }}
  ],
  "filters": {{
    "humans_only": true,
    "has_abstract": true
  }}
}}

Example for "What are cardiovascular benefits of exercise in elderly?":
{{
  "concepts": [
    {{"name": "exercise", "mesh_terms": ["Exercise"], "keywords": ["physical activity"]}},
    {{"name": "cardiovascular", "mesh_terms": ["Cardiovascular System"], "keywords": ["heart", "cardiac"]}},
    {{"name": "elderly", "mesh_terms": ["Aged"], "keywords": ["elderly", "older adults"]}}
  ],
  "filters": {{"humans_only": true, "has_abstract": true}}
}}

Generate concise JSON for the research question:"""


class LiteQueryConverter:
    """
    Simplified query converter for BMLibrarian Lite.

    Generates focused, concise PubMed queries that actually work,
    without excessive synonym expansion that causes HTTP 400/414 errors.

    Attributes:
        llm_client: LLM client for query conversion
        model: Model to use for conversion
    """

    def __init__(
        self,
        llm_client: LLMClient,
        model: str,
        temperature: float = 0.1,
    ) -> None:
        """
        Initialize the lite query converter.

        Args:
            llm_client: LLM client for query conversion
            model: Model string (e.g., "anthropic:claude-sonnet-4")
            temperature: LLM temperature (low for consistency)
        """
        self.llm_client = llm_client
        self.model = model
        self.temperature = temperature

    def convert(self, question: str) -> PubMedQuery:
        """
        Convert a natural language question to a PubMed query.

        Args:
            question: Natural language research question

        Returns:
            PubMedQuery with a concise, focused query string
        """
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")

        logger.info(f"Converting question to lite PubMed query: {question[:80]}...")

        try:
            # Get LLM to extract concepts
            prompt = LITE_QUERY_PROMPT.format(question=question)
            response = self.llm_client.chat(
                messages=[LLMMessage(role="user", content=prompt)],
                model=self.model,
                temperature=self.temperature,
                max_tokens=1000,
                json_mode=True,
            )

            data = self._parse_json(response.content)
            if data is None:
                logger.warning("Failed to parse LLM response, using fallback")
                return self._create_fallback_query(question)

            # Build query from concepts
            query_string = self._build_query(data)

            # Ensure query isn't too long
            if len(query_string) > MAX_TOTAL_QUERY_LENGTH:
                logger.warning(
                    f"Query too long ({len(query_string)} chars), using fallback"
                )
                return self._create_fallback_query(question)

            logger.info(f"Generated query ({len(query_string)} chars): {query_string[:100]}...")

            return PubMedQuery(
                original_question=question,
                query_string=query_string,
                generation_model=self.model,
                confidence_score=0.8,
            )

        except Exception as e:
            logger.error(f"Query conversion failed: {e}")
            return self._create_fallback_query(question)

    def _parse_json(self, response: str) -> Optional[dict]:
        """Parse JSON from LLM response."""
        # Try direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to extract from markdown code block
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find JSON object
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _build_query(self, data: dict) -> str:
        """
        Build a PubMed query string from parsed LLM data.

        Args:
            data: Parsed JSON with concepts and filters

        Returns:
            PubMed query string
        """
        concepts = data.get("concepts", [])
        filters = data.get("filters", {})

        if not concepts:
            return ""

        # Build clause for each concept
        concept_clauses = []
        for concept in concepts:
            terms = []

            # Add MeSH terms (limited)
            mesh_terms = concept.get("mesh_terms", [])[:MAX_MESH_TERMS_PER_CONCEPT]
            for term in mesh_terms:
                terms.append(f'"{term}"[MeSH Terms]')

            # Add keywords (limited)
            keywords = concept.get("keywords", [])[:MAX_KEYWORDS_PER_CONCEPT]
            for kw in keywords:
                # Quote multi-word phrases
                if " " in kw:
                    terms.append(f'"{kw}"[Title/Abstract]')
                else:
                    terms.append(f"{kw}[Title/Abstract]")

            if terms:
                # OR within concept
                concept_clauses.append("(" + " OR ".join(terms) + ")")

        if not concept_clauses:
            return ""

        # AND between concepts
        query_parts = ["(" + " AND ".join(concept_clauses) + ")"]

        # Add filters
        if filters.get("humans_only", True):
            query_parts.append("humans[MeSH Terms]")

        if filters.get("has_abstract", True):
            query_parts.append("hasabstract")

        return " AND ".join(query_parts)

    def _create_fallback_query(self, question: str) -> PubMedQuery:
        """
        Create a simple fallback query from keywords.

        Args:
            question: Original research question

        Returns:
            PubMedQuery with simple keyword search
        """
        # Extract meaningful words
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "what", "which", "who",
            "how", "when", "where", "why", "that", "this", "these",
            "those", "and", "or", "but", "if", "for", "of", "in", "on",
            "to", "with", "by", "from", "at", "as", "into", "about",
        }

        words = re.findall(r'\b[a-zA-Z]{3,}\b', question.lower())
        keywords = [w for w in words if w not in stop_words][:5]

        if not keywords:
            # Last resort: use cleaned question
            query_string = f'"{question}"[Title/Abstract]'
        else:
            # Simple keyword search
            keyword_clauses = [f"{kw}[Title/Abstract]" for kw in keywords]
            query_string = " AND ".join(keyword_clauses) + " AND hasabstract"

        logger.info(f"Using fallback query: {query_string}")

        return PubMedQuery(
            original_question=question,
            query_string=query_string,
            generation_model="fallback",
            confidence_score=0.4,
        )
