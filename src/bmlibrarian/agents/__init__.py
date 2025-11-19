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
- DocumentInterrogationAgent: Answers questions about documents using sliding window chunk processing
- PICOAgent: Extracts Population, Intervention, Comparison, and Outcome components from research papers
- StudyAssessmentAgent: Evaluates research quality, study type, and trustworthiness of evidence

Note: FactCheckerAgent has been moved to bmlibrarian.factchecker module (import from there directly)

Queue System:
- QueueManager: SQLite-based task queuing for memory-efficient processing
- AgentOrchestrator: Multi-agent workflow coordination and handover management
- TaskStatus/TaskPriority: Queue task management enums
- Workflow/WorkflowStep: Multi-step agent workflow definition

Text Processing:
- TextChunker: Sliding window text chunking with configurable overlap
- TextChunk: Text chunk dataclass with position metadata
"""

from .base import BaseAgent
from .query_agent import QueryAgent
from .scoring_agent import DocumentScoringAgent, ScoringResult
from .citation_agent import CitationFinderAgent, Citation
from .reporting_agent import ReportingAgent, Reference, Report
from .counterfactual_agent import CounterfactualAgent
from .models.counterfactual import CounterfactualQuestion, CounterfactualAnalysis
from .editor_agent import EditorAgent, EditedReport
from .document_interrogation_agent import (
    DocumentInterrogationAgent,
    DocumentAnswer,
    RelevantSection,
    ProcessingMode,
    DatabaseChunk
)
from .pico_agent import PICOAgent, PICOExtraction
from .study_assessment_agent import StudyAssessmentAgent, StudyAssessment
from .text_chunking import TextChunker, TextChunk, chunk_text, DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP
from .queue_manager import QueueManager, TaskStatus, TaskPriority
from .orchestrator import AgentOrchestrator, Workflow, WorkflowStep
from .human_edit_logger import HumanEditLogger, get_human_edit_logger
from .factory import AgentFactory

# NOTE: FactCheckerAgent has been moved to bmlibrarian.factchecker module
# Import it from there directly: from bmlibrarian.factchecker import FactCheckerAgent

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
    "DocumentInterrogationAgent",
    "DocumentAnswer",
    "RelevantSection",
    "ProcessingMode",
    "DatabaseChunk",
    "PICOAgent",
    "PICOExtraction",
    "StudyAssessmentAgent",
    "StudyAssessment",
    "TextChunker",
    "TextChunk",
    "chunk_text",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_CHUNK_OVERLAP",
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