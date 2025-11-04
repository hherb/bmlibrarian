"""Data types for multi-model query generation."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class QueryGenerationResult:
    """Result from a single query generation attempt.

    Attributes:
        model: The model name used for generation
        query: The generated query string
        generation_time: Time taken to generate the query (seconds)
        temperature: Temperature parameter used
        attempt_number: Which attempt this was (1, 2, or 3)
        error: Error message if generation failed
    """
    model: str
    query: str
    generation_time: float
    temperature: float
    attempt_number: int  # 1, 2, or 3
    error: Optional[str] = None


@dataclass
class MultiModelQueryResult:
    """Aggregated results from multi-model query generation.

    Attributes:
        all_queries: All generated queries (including duplicates)
        unique_queries: De-duplicated list of queries
        model_count: Number of models used
        total_queries: Total number of queries generated
        total_generation_time: Total time for all generations (seconds)
        question: The original user question
    """
    all_queries: List[QueryGenerationResult]
    unique_queries: List[str]  # De-duplicated
    model_count: int
    total_queries: int
    total_generation_time: float
    question: str
