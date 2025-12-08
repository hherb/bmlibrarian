"""
Exceptions for the Systematic Review Agent module.

This module defines all exception classes used by the systematic review
agent and its sub-components.
"""


class SystematicReviewError(Exception):
    """Base exception for systematic review errors."""

    pass


class SearchPlanningError(SystematicReviewError):
    """Exception raised when search plan generation fails."""

    pass


class SearchExecutionError(SystematicReviewError):
    """Exception raised when search execution fails."""

    pass


class ScoringError(SystematicReviewError):
    """Exception raised when document scoring fails."""

    pass


class QualityAssessmentError(SystematicReviewError):
    """Exception raised when quality assessment fails."""

    pass


class ReportGenerationError(SystematicReviewError):
    """Exception raised when report generation fails."""

    pass


class LLMConnectionError(SystematicReviewError):
    """Exception raised when LLM connection fails."""

    pass


class DatabaseConnectionError(SystematicReviewError):
    """Exception raised when database connection fails."""

    pass


class CheckpointError(SystematicReviewError):
    """Exception raised when checkpoint operations fail."""

    pass


class ResumeError(SystematicReviewError):
    """Exception raised when resuming from checkpoint fails."""

    pass
