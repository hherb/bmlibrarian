"""
Lite agents for BMLibrarian Lite.

This module provides simplified, stateless agents that work without PostgreSQL,
using ChromaDB and SQLite for persistence and online LLM providers for inference.

Agents:
    LiteBaseAgent: Base class with LLM communication
    LiteSearchAgent: PubMed search and caching
    LiteScoringAgent: Document relevance scoring
    LiteCitationAgent: Citation extraction
    LiteReportingAgent: Report generation
    LiteInterrogationAgent: Document Q&A

Usage:
    from bmlibrarian.lite.agents import (
        LiteSearchAgent,
        LiteScoringAgent,
        LiteCitationAgent,
        LiteReportingAgent,
        LiteInterrogationAgent,
    )

    # Create agents with shared config
    from bmlibrarian.lite import LiteConfig, LiteStorage

    config = LiteConfig.load()
    storage = LiteStorage(config)

    search_agent = LiteSearchAgent(storage=storage, config=config)
    scoring_agent = LiteScoringAgent(config=config)
    citation_agent = LiteCitationAgent(config=config)
    reporting_agent = LiteReportingAgent(config=config)
    interrogation_agent = LiteInterrogationAgent(storage=storage, config=config)

    # Execute a research workflow
    session, documents = search_agent.search("cardiovascular effects of exercise")
    scored = scoring_agent.score_documents("cardiovascular effects", documents)
    citations = citation_agent.extract_all_citations("cardiovascular effects", scored)
    report = reporting_agent.generate_report("cardiovascular effects", citations)
"""

from .base import LiteBaseAgent
from .search_agent import LiteSearchAgent
from .scoring_agent import LiteScoringAgent
from .citation_agent import LiteCitationAgent
from .reporting_agent import LiteReportingAgent
from .interrogation_agent import LiteInterrogationAgent

__all__ = [
    "LiteBaseAgent",
    "LiteSearchAgent",
    "LiteScoringAgent",
    "LiteCitationAgent",
    "LiteReportingAgent",
    "LiteInterrogationAgent",
]
