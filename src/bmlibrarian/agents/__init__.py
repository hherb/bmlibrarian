"""
BMLibrarian Agents Module

This module provides AI-powered agents for various biomedical literature tasks.
All agents are built on a common BaseAgent foundation with specialized capabilities.

Available Agents:
- QueryAgent: Natural language to PostgreSQL query conversion
- DocumentScoringAgent: Document relevance scoring for user questions
- CitationFinderAgent: Extracts relevant passages and citations from scored documents
- ReportingAgent: Synthesizes citations into medical publication-style reports
- CounterfactualAgent: Analyzes documents to generate research questions for finding contradictory evidence
- EditorAgent: Creates balanced, comprehensive reports combining original findings with contradictory evidence
- FactCheckerAgent: Evaluates biomedical statements against literature evidence for training data auditing

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
from .reporting_agent import ReportingAgent, Reference, Report
from .counterfactual_agent import CounterfactualAgent
from .models.counterfactual import CounterfactualQuestion, CounterfactualAnalysis
from .editor_agent import EditorAgent, EditedReport
from .fact_checker_agent import FactCheckerAgent, FactCheckResult, EvidenceReference
from .queue_manager import QueueManager, TaskStatus, TaskPriority
from .orchestrator import AgentOrchestrator, Workflow, WorkflowStep
from .human_edit_logger import HumanEditLogger, get_human_edit_logger
from .factory import AgentFactory

__all__ = [
    "BaseAgent",
    "QueryAgent",
    "DocumentScoringAgent",
    "ScoringResult",
    "CitationFinderAgent",
    "Citation",
    "ReportingAgent",
    "Reference",
    "Report",
    "CounterfactualAgent",
    "CounterfactualQuestion",
    "CounterfactualAnalysis",
    "EditorAgent",
    "EditedReport",
    "FactCheckerAgent",
    "FactCheckResult",
    "EvidenceReference",
    "QueueManager",
    "TaskStatus",
    "TaskPriority",
    "AgentOrchestrator",
    "Workflow",
    "WorkflowStep",
    "HumanEditLogger",
    "get_human_edit_logger",
    "AgentFactory"
]