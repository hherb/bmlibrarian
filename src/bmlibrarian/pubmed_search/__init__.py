"""
PubMed API Search Module for BMLibrarian.

This module enables users without local PubMed mirrors to search PubMed
directly via the NCBI E-utilities API. It converts natural language research
questions into optimized PubMed queries using MeSH terms, field tags, and
boolean operators.

Quick Start:
    from bmlibrarian.pubmed_search import (
        QueryConverter,
        PubMedSearchClient,
        ResultProcessor,
        SearchAndImportOrchestrator,
    )

    # Simple workflow using orchestrator
    orchestrator = SearchAndImportOrchestrator()
    session = orchestrator.search_and_import(
        question="What are the cardiovascular benefits of exercise in elderly?",
        max_results=200,
    )
    print(f"Imported {session.import_result.articles_imported} articles")

    # Manual workflow with more control
    converter = QueryConverter()
    result = converter.convert("cardiovascular benefits of exercise")
    print(result.primary_query.query_string)

    client = PubMedSearchClient(email="user@example.com")
    search_result = client.search(result.primary_query, max_results=100)

    processor = ResultProcessor()
    import_result = processor.import_articles(
        client.fetch_articles(search_result.pmids)
    )

Components:
    - QueryConverter: LLM-based natural language to PubMed query conversion
    - MeSHLookup: MeSH term validation and expansion with caching
    - PubMedSearchClient: E-utilities API client with rate limiting
    - ResultProcessor: Database storage with duplicate detection
    - SearchAndImportOrchestrator: Complete workflow coordination

Configuration:
    Add to ~/.bmlibrarian/config.json:
    {
        "pubmed_api": {
            "email": "user@example.com",
            "api_key": null,
            "default_max_results": 200,
            "validate_mesh": true,
            "expand_keywords": true
        }
    }
"""

# Data types
from .data_types import (
    PublicationType,
    SearchStatus,
    MeSHTerm,
    QueryConcept,
    DateRange,
    PubMedQuery,
    SearchResult,
    ArticleMetadata,
    ImportResult,
    SearchSession,
    QueryConversionResult,
)

# Constants
from .constants import (
    DEFAULT_MAX_RESULTS,
    MAX_RESULTS_LIMIT,
    DEFAULT_BATCH_SIZE,
    DEFAULT_QUERY_MODEL,
)

# Core components
from .mesh_lookup import MeSHLookup
from .query_converter import QueryConverter
from .search_client import PubMedSearchClient, validate_email
from .result_processor import ResultProcessor, SearchAndImportOrchestrator

__all__ = [
    # Data types
    "PublicationType",
    "SearchStatus",
    "MeSHTerm",
    "QueryConcept",
    "DateRange",
    "PubMedQuery",
    "SearchResult",
    "ArticleMetadata",
    "ImportResult",
    "SearchSession",
    "QueryConversionResult",
    # Constants
    "DEFAULT_MAX_RESULTS",
    "MAX_RESULTS_LIMIT",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_QUERY_MODEL",
    # Core components
    "MeSHLookup",
    "QueryConverter",
    "PubMedSearchClient",
    "ResultProcessor",
    "SearchAndImportOrchestrator",
    # Utility functions
    "validate_email",
]
