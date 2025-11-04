"""Multi-model query generator with serial execution."""

import time
import logging
import ollama
from typing import List, Optional, Callable

from .data_types import QueryGenerationResult, MultiModelQueryResult

logger = logging.getLogger(__name__)


class MultiModelQueryGenerator:
    """Generates queries using multiple models with SERIAL execution.

    Optimized for local Ollama + PostgreSQL instances where parallel
    execution provides no performance benefit and could create bottlenecks.
    """

    def __init__(self, ollama_host: str, callback: Optional[Callable] = None):
        """Initialize the multi-model query generator.

        Args:
            ollama_host: Ollama server URL (e.g., 'http://localhost:11434')
            callback: Optional callback for progress updates
        """
        self.ollama_host = ollama_host
        self.callback = callback
        self.client = ollama.Client(host=ollama_host)

    def generate_queries(
        self,
        question: str,
        system_prompt: str,
        models: List[str],
        queries_per_model: int,
        temperature: float = 0.1,
        top_p: float = 0.9
    ) -> MultiModelQueryResult:
        """Generate queries SERIALLY using multiple models.

        Process (SERIAL execution):
        1. For each model (serial loop):
            a. For each attempt (1 to queries_per_model):
                - Generate one query
                - Track time and result
        2. De-duplicate queries (case-insensitive comparison)
        3. Return MultiModelQueryResult

        Args:
            question: The user's natural language question
            system_prompt: System prompt for query generation
            models: List of model names to use (1-3 models)
            queries_per_model: Number of queries per model (1-3)
            temperature: Temperature parameter for generation
            top_p: Top-p parameter for generation

        Returns:
            MultiModelQueryResult with all queries and metadata
        """
        all_queries = []
        start_time = time.time()

        logger.info(f"Starting serial query generation: {len(models)} models, {queries_per_model} queries/model")

        # SERIAL execution - simple for-loops
        for model in models:
            for attempt in range(1, queries_per_model + 1):
                try:
                    result = self._generate_single_query(
                        model=model,
                        question=question,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        top_p=top_p,
                        attempt=attempt
                    )
                    all_queries.append(result)

                    if self.callback:
                        self.callback("query_generated", {
                            "model": model,
                            "attempt": attempt,
                            "query": result.query,
                            "time": result.generation_time
                        })

                    logger.info(f"Generated query {attempt} from {model}: {result.query[:50]}...")

                except Exception as e:
                    logger.error(f"Failed to generate query with {model} (attempt {attempt}): {e}")
                    # Create error result
                    error_result = QueryGenerationResult(
                        model=model,
                        query="",
                        generation_time=0.0,
                        temperature=temperature,
                        attempt_number=attempt,
                        error=str(e)
                    )
                    all_queries.append(error_result)

                    if self.callback:
                        self.callback("query_generation_failed", {
                            "model": model,
                            "attempt": attempt,
                            "error": str(e)
                        })

        # De-duplicate queries (filter out errors first)
        valid_queries = [q.query for q in all_queries if not q.error and q.query]
        unique_queries = self._deduplicate_queries(valid_queries)

        total_time = time.time() - start_time

        logger.info(f"Query generation complete: {len(all_queries)} total, {len(unique_queries)} unique")

        return MultiModelQueryResult(
            all_queries=all_queries,
            unique_queries=unique_queries,
            model_count=len(models),
            total_queries=len(all_queries),
            total_generation_time=total_time,
            question=question
        )

    def _generate_single_query(
        self,
        model: str,
        question: str,
        system_prompt: str,
        temperature: float,
        top_p: float,
        attempt: int
    ) -> QueryGenerationResult:
        """Generate a single query using one model.

        Uses the same Ollama request pattern as QueryAgent.convert_question()
        but returns QueryGenerationResult for structured tracking.

        Args:
            model: Model name to use
            question: User's question
            system_prompt: System prompt for generation
            temperature: Temperature parameter
            top_p: Top-p parameter
            attempt: Attempt number (1, 2, or 3)

        Returns:
            QueryGenerationResult with query and metadata
        """
        start_time = time.time()

        try:
            messages = [{'role': 'user', 'content': question}]

            # Add system message
            messages = [{'role': 'system', 'content': system_prompt}] + messages

            # Make Ollama request
            response = self.client.chat(
                model=model,
                messages=messages,
                options={
                    'temperature': temperature,
                    'top_p': top_p,
                    'num_predict': 100  # Short response for query generation
                }
            )

            query = response['message']['content'].strip()
            generation_time = time.time() - start_time

            return QueryGenerationResult(
                model=model,
                query=query,
                generation_time=generation_time,
                temperature=temperature,
                attempt_number=attempt,
                error=None
            )

        except Exception as e:
            generation_time = time.time() - start_time
            logger.error(f"Query generation failed for {model}: {e}")
            raise  # Re-raise to be caught by caller

    def _deduplicate_queries(self, queries: List[str]) -> List[str]:
        """Remove duplicate queries using case-insensitive comparison.

        Args:
            queries: List of query strings (may contain duplicates)

        Returns:
            List of unique queries (preserving original case)
        """
        seen = set()
        unique = []

        for query in queries:
            # Normalize for comparison
            normalized = query.lower().strip()

            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(query)  # Keep original case

        logger.debug(f"De-duplication: {len(queries)} → {len(unique)} queries")

        return unique
