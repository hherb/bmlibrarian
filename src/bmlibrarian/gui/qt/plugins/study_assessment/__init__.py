"""
Study Assessment Lab Plugin.

Interactive interface for evaluating research quality, study design,
and trustworthiness of biomedical evidence.
"""

# Note: create_plugin is imported directly by PluginManager from plugin.py
# Don't import it here to avoid circular imports

from .study_assessment_tab import StudyAssessmentTabWidget

__all__ = [
    'StudyAssessmentTabWidget'
]
