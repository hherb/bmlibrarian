"""
Study Assessment Lab Plugin.

Interactive interface for evaluating research quality, study design,
and trustworthiness of biomedical evidence.
"""

from .plugin import create_plugin, StudyAssessmentLabPlugin
from .study_assessment_tab import StudyAssessmentTabWidget

__all__ = [
    'create_plugin',
    'StudyAssessmentLabPlugin',
    'StudyAssessmentTabWidget'
]
