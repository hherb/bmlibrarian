"""Example tab plugin demonstrating the plugin architecture.

This plugin serves as a template and example for developers creating new plugins.
It demonstrates:
- Plugin metadata
- Widget creation
- Signal usage
- Configuration management
- Resource cleanup
- Event bus communication
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QGroupBox
)
from PySide6.QtCore import Slot
from typing import Dict, Any

from ..base_tab import BaseTabPlugin, TabPluginMetadata
from ...core.event_bus import EventBus


class ExampleTabWidget(QWidget):
    """Example tab widget with demonstration UI."""

    def __init__(self, plugin, parent=None):
        """Initialize the example widget.

        Args:
            plugin: Parent plugin instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.plugin = plugin
        self.event_bus = EventBus()

        self._build_ui()

    def _build_ui(self):
        """Build the user interface."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("<h1>Example Plugin</h1>")
        layout.addWidget(header)

        description = QLabel(
            "This is an example plugin demonstrating the BMLibrarian "
            "plugin architecture. Use this as a template for creating "
            "new plugins."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        # Features group
        features_group = QGroupBox("Plugin Features Demonstrated")
        features_layout = QVBoxLayout(features_group)

        features_text = QLabel(
            "• Plugin metadata (ID, display name, version, etc.)\n"
            "• Widget creation and layout\n"
            "• Qt signals and slots\n"
            "• Event bus communication\n"
            "• Configuration management\n"
            "• Resource cleanup\n"
            "• Status bar updates\n"
            "• Tab navigation"
        )
        features_layout.addWidget(features_text)
        layout.addWidget(features_group)

        # Interactive section
        interactive_group = QGroupBox("Interactive Examples")
        interactive_layout = QVBoxLayout(interactive_group)

        # Status update button
        status_button_layout = QHBoxLayout()
        status_button = QPushButton("Update Status Bar")
        status_button.clicked.connect(self._on_status_button_clicked)
        status_button_layout.addWidget(status_button)
        status_button_layout.addStretch()
        interactive_layout.addLayout(status_button_layout)

        # Event bus button
        event_button_layout = QHBoxLayout()
        event_button = QPushButton("Publish Event Bus Message")
        event_button.clicked.connect(self._on_event_button_clicked)
        event_button_layout.addWidget(event_button)
        event_button_layout.addStretch()
        interactive_layout.addLayout(event_button_layout)

        # Navigation button
        nav_button_layout = QHBoxLayout()
        nav_button = QPushButton("Request Navigation to Configuration")
        nav_button.clicked.connect(self._on_nav_button_clicked)
        nav_button_layout.addWidget(nav_button)
        nav_button_layout.addStretch()
        interactive_layout.addLayout(nav_button_layout)

        layout.addWidget(interactive_group)

        # Log area
        log_group = QGroupBox("Activity Log")
        log_layout = QVBoxLayout(log_group)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(150)
        log_layout.addWidget(self.log_area)

        layout.addWidget(log_group)

        # Add stretch at bottom
        layout.addStretch()

        self._log("Example plugin initialized")

    def _log(self, message: str):
        """Add message to log area.

        Args:
            message: Message to log
        """
        self.log_area.append(f"• {message}")

    @Slot()
    def _on_status_button_clicked(self):
        """Handle status button click."""
        self.plugin.status_changed.emit("Status updated from example plugin!")
        self._log("Status bar updated")

    @Slot()
    def _on_event_button_clicked(self):
        """Handle event bus button click."""
        self.event_bus.publish_data("example", {
            "event": "example_event",
            "message": "Hello from example plugin!",
            "timestamp": "now"
        })
        self._log("Published event to event bus")

    @Slot()
    def _on_nav_button_clicked(self):
        """Handle navigation button click."""
        self.plugin.request_navigation.emit("configuration")
        self._log("Requested navigation to configuration tab")

    def on_activated(self):
        """Called when tab is activated."""
        self._log("Tab activated")

    def on_deactivated(self):
        """Called when tab is deactivated."""
        self._log("Tab deactivated")


class ExamplePlugin(BaseTabPlugin):
    """Example tab plugin.

    This plugin demonstrates the minimum required implementation for a
    BMLibrarian Qt GUI plugin.
    """

    def __init__(self):
        """Initialize the example plugin."""
        super().__init__()
        self.widget = None

    def get_metadata(self) -> TabPluginMetadata:
        """Return plugin metadata.

        Returns:
            TabPluginMetadata: Metadata describing this plugin
        """
        return TabPluginMetadata(
            plugin_id="example",
            display_name="Example Plugin",
            description="Demonstrates plugin architecture and serves as a template",
            version="1.0.0",
            icon=None,  # No icon for example plugin
            requires=[]  # No dependencies
        )

    def create_widget(self, parent=None) -> QWidget:
        """Create the example tab widget.

        Args:
            parent: Parent widget

        Returns:
            QWidget: The example widget
        """
        self.widget = ExampleTabWidget(self, parent)
        return self.widget

    def on_tab_activated(self):
        """Called when this tab becomes active."""
        self.status_changed.emit("Example plugin activated")
        if self.widget:
            self.widget.on_activated()

    def on_tab_deactivated(self):
        """Called when this tab is deactivated."""
        if self.widget:
            self.widget.on_deactivated()

    def get_config(self) -> Dict[str, Any]:
        """Get plugin configuration.

        Returns:
            Dict[str, Any]: Configuration dictionary
        """
        return {
            "example_setting": True,
            "example_value": 42
        }

    def set_config(self, config: Dict[str, Any]):
        """Update plugin configuration.

        Args:
            config: New configuration dictionary
        """
        # In a real plugin, you would update behavior based on config
        self.logger.info(f"Configuration updated: {config}")

    def cleanup(self):
        """Cleanup resources when plugin is unloaded."""
        self.logger.debug("Cleaning up example plugin")

        # Cleanup widget resources
        if self.widget:
            self.widget.log_area.clear()
            self.widget = None

        # Call parent cleanup
        super().cleanup()


def create_plugin() -> BaseTabPlugin:
    """Plugin entry point.

    This function is called by the PluginManager to instantiate the plugin.

    Returns:
        BaseTabPlugin: The example plugin instance
    """
    return ExamplePlugin()
