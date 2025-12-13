"""
MeSH (Medical Subject Headings) module for BMLibrarian.

This module provides local MeSH database storage and lookup functionality
with automatic fallback to NLM's public API when local data is unavailable.

Example usage:
    from bmlibrarian.mesh import MeSHService, MeSHResult

    # Create service (automatically uses local DB if available)
    service = MeSHService()

    # Look up a term
    result = service.lookup("heart attack")
    if result.found:
        print(f"Descriptor: {result.descriptor_name}")
        print(f"Entry terms: {result.entry_terms}")

    # Expand a term to all synonyms
    synonyms = service.expand("MI")  # Returns all terms for Myocardial Infarction

    # Search MeSH by partial match
    results = service.search("cardio", limit=10)
"""

from .lookup import MeSHService, MeSHResult, MeSHSource
from .data_types import (
    MeSHDescriptorInfo,
    MeSHTermInfo,
    MeSHTreeInfo,
    MeSHSearchResult,
)

__all__ = [
    "MeSHService",
    "MeSHResult",
    "MeSHSource",
    "MeSHDescriptorInfo",
    "MeSHTermInfo",
    "MeSHTreeInfo",
    "MeSHSearchResult",
]
