"""
Study Assessment Lab plugin for BMLibrarian Qt GUI.

This plugin provides an interactive laboratory for experimenting with the
StudyAssessmentAgent and evaluating research quality, study design, methodological
rigor, bias risk, and overall trustworthiness of biomedical evidence.

Features:
- Load documents by ID from the database
- Analyze study design and methodology
- Assess quality scores (0-10 scale)
- Evaluate bias risks (selection, performance, detection, attrition, reporting)
- View strengths and limitations
- Assess overall confidence in findings
- Classify evidence levels
"""

from .plugin import StudyAssessmentLabPlugin, create_plugin
from .study_assessment_lab_tab import StudyAssessmentLabTabWidget

__all__ = [
    'StudyAssessmentLabPlugin',
    'StudyAssessmentLabTabWidget',
    'create_plugin'
]
