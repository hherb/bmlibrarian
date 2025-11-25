"""
Semantic Chunk Processor for Iterative Context Processing

This module provides a concrete implementation of IterativeContextProcessor
for processing semantic search chunks (text, score tuples). It uses an LLM
to extract relevant information from batches of chunks without truncation.

The processor is designed for use with agents that perform semantic search
and need to consolidate large amounts of context (e.g., PRISMA assessments,
citation finding, document interrogation).

Usage:
    from bmlibrarian.agents.context_processor import (
        ProcessingConfig,
        SemanticChunkProcessor,
    )

    processor = SemanticChunkProcessor(
        llm_client=ollama_client,
        model="gpt-oss:20b",
        extraction_prompt_template=EXTRACTION_PROMPT,
    )
    result = processor.process(
        items=chunks,  # List of (text, score) tuples
        query="What search strategy was used?",
    )
    context = result.content  # Consolidated without truncation
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import IterativeContextProcessor, ProgressCallback
from .data_types import (
    ExtractionResult,
    ProcessingConfig,
    DEFAULT_MAX_CONTEXT_CHARS,
)

logger = logging.getLogger(__name__)


# Type alias for semantic search chunks
SemanticChunk = Tuple[str, float]  # (text, score)

# Default extraction prompt template
DEFAULT_EXTRACTION_PROMPT = """Extract the key information relevant to this query.

Query: {query}

Content:
{content}

INSTRUCTIONS:
- Focus on information directly addressing the query
- Preserve important details, facts, and evidence
- Be concise but do not lose relevant information
- Return the extracted information as plain text

Extracted Information:"""

# Default consolidation prompt template (used at recursion levels > 0)
DEFAULT_CONSOLIDATION_PROMPT = """Consolidate and synthesize these extracted passages.

Query: {query}

Previously Extracted Information:
{content}

INSTRUCTIONS:
- Merge overlapping or redundant information
- Preserve all unique relevant details
- Maintain logical organization
- Return consolidated information as plain text

Consolidated Information:"""

# Response format for structured extraction
STRUCTURED_EXTRACTION_PROMPT = """Extract the key information relevant to this query.

Query: {query}

Content:
{content}

INSTRUCTIONS:
- Focus on information directly addressing the query
- Preserve important details, facts, and evidence
- Assess your confidence in the extraction (0.0 to 1.0)

Response format (JSON only):
{{
    "extracted_content": "The extracted information...",
    "confidence": 0.9,
    "key_findings": ["finding 1", "finding 2"]
}}

Respond ONLY with valid JSON."""


class SemanticChunkProcessor(IterativeContextProcessor):
    """
    Process semantic search chunks using iterative LLM extraction.

    This processor takes (text, score) tuples from semantic search and
    extracts relevant information in batches, consolidating recursively
    until the result fits within context limits.

    Unlike truncation-based approaches, this preserves information by
    using LLM summarization at each level.

    Attributes:
        llm_client: Ollama client for LLM calls.
        model: Model name for LLM calls.
        extraction_prompt_template: Template for extraction prompts.
        consolidation_prompt_template: Template for consolidation prompts.
        use_structured_output: If True, use JSON output format for extraction.
        temperature: LLM temperature setting.
        max_tokens: Maximum tokens for LLM response.
    """

    def __init__(
        self,
        llm_client: Any,
        model: str,
        extraction_prompt_template: Optional[str] = None,
        consolidation_prompt_template: Optional[str] = None,
        config: Optional[ProcessingConfig] = None,
        progress_callback: Optional[ProgressCallback] = None,
        use_structured_output: bool = False,
        temperature: float = 0.1,
        max_tokens: int = 1000,
    ):
        """
        Initialize the semantic chunk processor.

        Args:
            llm_client: Ollama client instance for LLM calls.
            model: Name of the LLM model to use.
            extraction_prompt_template: Custom template for extraction prompts.
                Must include {query} and {content} placeholders.
            consolidation_prompt_template: Custom template for consolidation prompts.
                Must include {query} and {content} placeholders.
            config: Processing configuration. Uses defaults if not provided.
            progress_callback: Optional callback for progress updates.
            use_structured_output: If True, use JSON output format for extraction.
            temperature: LLM temperature for response generation.
            max_tokens: Maximum tokens for LLM response.
        """
        super().__init__(config, progress_callback)
        self.llm_client = llm_client
        self.model = model
        self.extraction_prompt_template = (
            extraction_prompt_template or DEFAULT_EXTRACTION_PROMPT
        )
        self.consolidation_prompt_template = (
            consolidation_prompt_template or DEFAULT_CONSOLIDATION_PROMPT
        )
        self.use_structured_output = use_structured_output
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Validate prompt templates
        self._validate_prompt_template(
            self.extraction_prompt_template, "extraction_prompt_template"
        )
        self._validate_prompt_template(
            self.consolidation_prompt_template, "consolidation_prompt_template"
        )

    def _validate_prompt_template(self, template: str, name: str) -> None:
        """
        Validate that a prompt template contains required placeholders.

        Args:
            template: The prompt template string.
            name: Name of the template for error messages.

        Raises:
            ValueError: If required placeholders are missing.
        """
        required_placeholders = ["{query}", "{content}"]
        for placeholder in required_placeholders:
            if placeholder not in template:
                raise ValueError(
                    f"{name} must contain '{placeholder}' placeholder"
                )

    def format_item(self, item: Any, index: int) -> str:
        """
        Format a semantic chunk for inclusion in a batch.

        Handles both original (text, score) tuples and consolidated
        (content, metadata) tuples from recursive processing.

        Args:
            item: Either a (text, score) tuple or (content, metadata) tuple.
            index: The index of this item in the current batch.

        Returns:
            Formatted string representation of the chunk.
        """
        # Handle original semantic chunks (text, score)
        if isinstance(item, tuple) and len(item) == 2:
            first_element, second_element = item
            if isinstance(first_element, str) and isinstance(second_element, (int, float)):
                # Original chunk: (text, score)
                text, score = first_element, float(second_element)
                return f"[Chunk {index + 1}, Score: {score:.2f}]\n{text}"
            elif isinstance(first_element, str) and isinstance(second_element, dict):
                # Consolidated item: (content, metadata)
                content, metadata = first_element, second_element
                level = metadata.get("recursion_level", 0)
                return f"[Consolidated Level {level}, Item {index + 1}]\n{content}"

        # Handle string items (from truncation fallback or split)
        if isinstance(item, str):
            return f"[Item {index + 1}]\n{item}"

        # Fallback for unknown types
        logger.warning(f"Unknown item type: {type(item).__name__}")
        return f"[Item {index + 1}]\n{str(item)}"

    def split_oversized_item(
        self,
        item: Any,
        max_chars: int,
        overlap: int = 0,
    ) -> List[Any]:
        """
        Split an oversized semantic chunk into smaller pieces.

        For (text, score) tuples, splits the text while preserving the score.
        Each piece retains the original score since they come from the same chunk.

        Args:
            item: The item to split (typically a (text, score) tuple).
            max_chars: Maximum characters per piece.
            overlap: Number of characters to overlap between pieces.

        Returns:
            List of smaller items that each fit within max_chars.
        """
        # Handle (text, score) tuples
        if isinstance(item, tuple) and len(item) == 2:
            first_element, second_element = item
            if isinstance(first_element, str) and isinstance(second_element, (int, float)):
                # Original chunk: split text, preserve score
                text, score = first_element, float(second_element)
                pieces = self._split_string(text, max_chars, overlap)
                return [(piece, score) for piece in pieces]
            elif isinstance(first_element, str) and isinstance(second_element, dict):
                # Consolidated item: split content, preserve metadata
                content, metadata = first_element, second_element
                pieces = self._split_string(content, max_chars, overlap)
                return [(piece, metadata.copy()) for piece in pieces]

        # Delegate to parent for other types
        return super().split_oversized_item(item, max_chars, overlap)

    def extract_from_batch(
        self,
        batch_content: str,
        query: str,
        batch_metadata: Dict[str, Any],
    ) -> ExtractionResult:
        """
        Extract relevant information from a batch of chunks using LLM.

        Uses different prompts for initial extraction vs. consolidation
        at higher recursion levels.

        Args:
            batch_content: The formatted, concatenated batch content.
            query: The query guiding the extraction.
            batch_metadata: Metadata about the batch (includes recursion_level).

        Returns:
            ExtractionResult containing extracted content and confidence.

        Raises:
            RuntimeError: If LLM extraction fails.
        """
        recursion_level = batch_metadata.get("recursion_level", 0)

        # Choose prompt based on recursion level
        if recursion_level == 0:
            prompt_template = self.extraction_prompt_template
        else:
            prompt_template = self.consolidation_prompt_template

        # Build the prompt
        prompt = prompt_template.format(query=query, content=batch_content)

        try:
            # Call LLM
            response = self.llm_client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            )

            extracted_content = response["message"]["content"].strip()
            confidence = 0.9  # Default confidence

            # Try to parse structured output if enabled
            if self.use_structured_output and recursion_level == 0:
                try:
                    parsed = json.loads(extracted_content)
                    extracted_content = parsed.get(
                        "extracted_content", extracted_content
                    )
                    confidence = float(parsed.get("confidence", 0.9))
                    batch_metadata["key_findings"] = parsed.get("key_findings", [])
                except (json.JSONDecodeError, ValueError):
                    # Keep the raw content if JSON parsing fails
                    logger.debug("Could not parse structured output, using raw content")

            logger.debug(
                f"Extracted {len(extracted_content)} chars from batch "
                f"(level {recursion_level}, index {batch_metadata.get('batch_index', 0)})"
            )

            return ExtractionResult(
                content=extracted_content,
                metadata=batch_metadata,
                confidence=confidence,
            )

        except Exception as e:
            error_msg = f"LLM extraction failed: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e


def create_prisma_chunk_processor(
    llm_client: Any,
    model: str,
    item_name: str,
    item_description: str,
    original_score: float,
    original_explanation: str,
    document_title: str,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    progress_callback: Optional[ProgressCallback] = None,
) -> SemanticChunkProcessor:
    """
    Create a SemanticChunkProcessor configured for PRISMA re-assessment.

    This factory function creates a processor with prompts tailored for
    PRISMA 2020 item re-assessment using semantic search context.

    Args:
        llm_client: Ollama client instance.
        model: LLM model name.
        item_name: Name of the PRISMA item (e.g., 'search_strategy').
        item_description: Description of what the item requires.
        original_score: Original score from first-pass assessment.
        original_explanation: Original explanation from first-pass assessment.
        document_title: Title of the document being assessed.
        max_context_chars: Maximum characters per batch.
        progress_callback: Optional progress callback.

    Returns:
        Configured SemanticChunkProcessor for PRISMA re-assessment.
    """
    # PRISMA-specific extraction prompt
    extraction_prompt = f"""You are extracting evidence for PRISMA 2020 compliance assessment.

Paper Title: {document_title}
PRISMA Item: {item_name.replace('_', ' ').title()}
Requirement: {item_description}

Original Assessment (based on abstract):
- Score: {original_score}/2.0
- Explanation: {original_explanation}

Query: {{query}}

Relevant Text Chunks:
{{content}}

INSTRUCTIONS:
Extract and summarize all information from these chunks that is relevant to
assessing the "{item_name.replace('_', ' ')}" PRISMA item. Focus on:
- Specific methods, procedures, or descriptions mentioned
- Evidence that addresses the PRISMA requirement
- Details that might improve or confirm the original assessment

Provide a concise summary of the relevant evidence found."""

    # PRISMA-specific consolidation prompt
    consolidation_prompt = f"""Consolidate evidence for PRISMA 2020 compliance assessment.

Paper Title: {document_title}
PRISMA Item: {item_name.replace('_', ' ').title()}
Requirement: {item_description}

Query: {{query}}

Previously Extracted Evidence:
{{content}}

INSTRUCTIONS:
Merge and consolidate this evidence into a single coherent summary.
- Combine overlapping information
- Preserve all unique relevant details
- Organize logically for assessment purposes

Consolidated Evidence:"""

    config = ProcessingConfig(
        max_context_chars=max_context_chars,
        max_recursion_depth=3,  # Limit recursion for single-item assessment
        min_items_for_recursion=2,
        continue_on_error=True,
    )

    return SemanticChunkProcessor(
        llm_client=llm_client,
        model=model,
        extraction_prompt_template=extraction_prompt,
        consolidation_prompt_template=consolidation_prompt,
        config=config,
        progress_callback=progress_callback,
        temperature=0.1,
        max_tokens=800,
    )
