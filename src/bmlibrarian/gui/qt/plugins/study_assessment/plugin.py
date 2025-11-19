"""
Study Assessment Lab Plugin for BMLibrarian Qt GUI.

Provides an interactive interface for evaluating research quality,
study design, and trustworthiness of biomedical evidence using
StudyAssessmentAgent.
"""

from PySide6.QtWidgets import QWidget
from typing import Optional

from ..base_tab import BaseTabPlugin, TabPluginMetadata
from .study_assessment_tab import StudyAssessmentTabWidget


class StudyAssessmentLabPlugin(BaseTabPlugin):
    """Plugin for Study Assessment Laboratory interface."""

    def __init__(self):
        """Initialize Study Assessment Lab plugin."""
        super().__init__()
        self.tab_widget: Optional[StudyAssessmentTabWidget] = None

    def get_metadata(self) -> TabPluginMetadata:
        """
        Get plugin metadata.

        Returns:
            Plugin metadata including ID, name, and description
        """
        return TabPluginMetadata(
            plugin_id="study_assessment",
            display_name="Study Assessment Lab",
            description="Interactive laboratory for evaluating research quality, study design, and trustworthiness of biomedical evidence",
            version="1.0.0",
            icon="experiment",
            requires=[]
        )

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        Create the main widget for this tab.

        Args:
            parent: Optional parent widget

        Returns:
            Main Study Assessment Lab tab widget
        """
        self.tab_widget = StudyAssessmentTabWidget(parent)

        # Connect signals
        self.tab_widget.status_message.connect(
            lambda msg: self.status_changed.emit(msg)
        )

        return self.tab_widget

    def on_tab_activated(self):
        """Called when this tab becomes active."""
        self.status_changed.emit("Study Assessment Lab activated - Ready to assess study quality")

    def on_tab_deactivated(self):
        """Called when this tab is deactivated."""
        pass

    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        if self.tab_widget:
            self.tab_widget.cleanup()


def create_plugin() -> BaseTabPlugin:
    """
    Plugin factory function.

    Returns:
        Initialized StudyAssessmentLabPlugin instance
    """
    return StudyAssessmentLabPlugin()
