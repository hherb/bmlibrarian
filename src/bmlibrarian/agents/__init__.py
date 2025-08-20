"""
BMLibrarian Agents Module

This module provides AI-powered agents for various biomedical literature tasks.
All agents are built on a common BaseAgent foundation with specialized capabilities.

Available Agents:
- QueryAgent: Natural language to PostgreSQL query conversion
- DocumentScoringAgent: Document relevance scoring for user questions
- CitationFinderAgent: Extracts relevant passages and citations from scored documents

Queue System:
- QueueManager: SQLite-based task queuing for memory-efficient processing
- AgentOrchestrator: Multi-agent workflow coordination and handover management
- TaskStatus/TaskPriority: Queue task management enums
- Workflow/WorkflowStep: Multi-step agent workflow definition
"""

from .base import BaseAgent
from .query_agent import QueryAgent
from .scoring_agent import DocumentScoringAgent, ScoringResult
from .citation_agent import CitationFinderAgent, Citation
from .queue_manager import QueueManager, TaskStatus, TaskPriority
from .orchestrator import AgentOrchestrator, Workflow, WorkflowStep

__all__ = [
    "BaseAgent", 
    "QueryAgent", 
    "DocumentScoringAgent",
    "ScoringResult",
    "CitationFinderAgent",
    "Citation",
    "QueueManager", 
    "TaskStatus", 
    "TaskPriority",
    "AgentOrchestrator",
    "Workflow",
    "WorkflowStep"
]