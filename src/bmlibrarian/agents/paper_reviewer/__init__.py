"""
Paper Reviewer Agent - Comprehensive Paper Quality Assessment

This module provides a unified paper assessment tool that combines multiple
existing agents to provide thorough analysis of research papers.

Components:
- PaperReviewerAgent: Main orchestrator
- DocumentResolver: Resolves DOI/PMID/PDF/text to document dicts
- SummaryGenerator: Creates brief summaries and extracts hypotheses
- StudyTypeDetector: Detects study type for PICO/PRISMA applicability
- ContradictoryEvidenceFinder: Searches for contradicting literature

Output includes:
- Brief 2-3 sentence summary
- Core statement/hypothesis
- PICO analysis (where applicable)
- PRISMA assessment (where applicable)
- Paper weight assessment (multi-dimensional)
- Study quality assessment
- Strengths and weaknesses summary
- Contradictory literature search results
"""

from .models import (
    PaperReviewResult,
    ContradictoryPaper,
    StudyTypeResult,
    ReviewStep,
    ReviewStepStatus,
)
from .resolver import DocumentResolver
from .summarizer import SummaryGenerator
from .study_detector import StudyTypeDetector
from .contradictory_finder import ContradictoryEvidenceFinder
from .agent import PaperReviewerAgent

__all__ = [
    # Main agent
    "PaperReviewerAgent",
    # Sub-components
    "DocumentResolver",
    "SummaryGenerator",
    "StudyTypeDetector",
    "ContradictoryEvidenceFinder",
    # Data models
    "PaperReviewResult",
    "ContradictoryPaper",
    "StudyTypeResult",
    "ReviewStep",
    "ReviewStepStatus",
]
