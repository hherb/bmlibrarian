"""
Fact Checker Review GUI Module

Provides graphical interface for reviewing and annotating fact-check results.
"""

from .review_app import FactCheckerReviewApp
from .data_manager import FactCheckDataManager
from .statement_display import StatementDisplay
from .annotation_manager import AnnotationManager

__all__ = [
    'FactCheckerReviewApp',
    'FactCheckDataManager',
    'StatementDisplay',
    'AnnotationManager'
]
