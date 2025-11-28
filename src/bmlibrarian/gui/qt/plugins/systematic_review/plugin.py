"""
Systematic Review plugin for BMLibrarian Qt GUI.

Provides checkpoint-based workflow monitoring and resume functionality
for systematic literature reviews. Key features:
- Monitor systematic review progress in real-time
- Resume from checkpoints with modified parameters
- Prevent redundant computation by loading existing work
- Modify thresholds and weights when resuming
"""

from ...plugins.base_tab import BaseTabPlugin, TabPluginMetadata
from .systematic_review_tab import SystematicReviewTabWidget
from PySide6.QtWidgets import QWidget
from typing import Optional


class SystematicReviewPlugin(BaseTabPlugin):
    """
    Systematic Review workflow plugin.

    Implements the checkpoint-based systematic review interface with:
    - Checkpoint listing and selection
    - Parameter modification for resume
    - Real-time progress monitoring
    - Prevents redundant computation
    """

    def __init__(self) -> None:
        """Initialize systematic review plugin."""
        super().__init__()
        self.tab_widget: Optional[SystematicReviewTabWidget] = None

    def get_metadata(self) -> TabPluginMetadata:
        """
        Get plugin metadata.

        Returns:
            Plugin metadata
        """
        return TabPluginMetadata(
            plugin_id="systematic_review",
            display_name="Systematic Review",
            description="Checkpoint-based systematic literature review workflow",
            version="1.0.0",
            icon=None,
        )

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        """
        Create the systematic review tab widget.

        Args:
            parent: Optional parent widget

        Returns:
            Systematic review tab widget instance
        """
        self.tab_widget = SystematicReviewTabWidget(parent=parent)

        # Connect widget signals to plugin signals
        self.tab_widget.status_message.connect(
            lambda msg: self.status_changed.emit(msg)
        )

        return self.tab_widget

    def on_tab_activated(self) -> None:
        """Called when systematic review tab becomes active."""
        self._is_active = True
        self.status_changed.emit("Systematic Review tab activated")

        # Refresh checkpoint list when tab becomes active
        if self.tab_widget:
            self.tab_widget.refresh_checkpoints()

    def on_tab_deactivated(self) -> None:
        """Called when systematic review tab is deactivated."""
        self._is_active = False

    def cleanup(self) -> None:
        """Cleanup resources and disconnect signals."""
        try:
            if self.tab_widget:
                try:
                    self.tab_widget.status_message.disconnect()
                except RuntimeError:
                    pass  # Already disconnected

                if hasattr(self.tab_widget, 'cleanup'):
                    self.tab_widget.cleanup()

            super().cleanup()

        except Exception as e:
            self.logger.error(
                f"Error during systematic review plugin cleanup: {e}",
                exc_info=True
            )


def create_plugin() -> BaseTabPlugin:
    """
    Plugin factory function.

    Returns:
        SystematicReviewPlugin instance
    """
    return SystematicReviewPlugin()
