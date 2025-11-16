"""Central event bus for inter-plugin communication.

This module provides the EventBus singleton for communication between plugins
without tight coupling. It supports event filtering to improve performance when
many plugins are loaded.
"""

from PySide6.QtCore import QObject, Signal
from typing import Any, Dict, List, Optional, Callable
import logging


class EventBus(QObject):
    """Central event bus for inter-plugin communication.

    This singleton class provides a centralized mechanism for plugins to
    communicate without direct dependencies. It uses Qt signals for
    thread-safe event delivery.

    Features:
    - Publish/subscribe pattern for loose coupling
    - Event filtering to reduce overhead with many plugins
    - Type-safe event data through dictionaries
    - Thread-safe signal delivery (Qt signals)

    Performance Optimization:
    - Event filtering allows targeting specific plugins
    - Reduces unnecessary signal processing
    - Important for applications with many plugins

    Example:
        # In plugin A
        event_bus = EventBus()
        event_bus.publish_data("plugin_a", {
            "event": "data_ready",
            "value": 42
        })

        # In plugin B
        event_bus = EventBus()
        event_bus.data_shared.connect(self._on_data_received)

        def _on_data_received(self, source_id: str, data: Dict):
            if source_id == "plugin_a":
                print(f"Received: {data}")
    """

    # Global signals for inter-plugin communication
    data_shared = Signal(str, dict)  # (source_plugin_id, data)
    navigation_requested = Signal(str)  # target_plugin_id
    status_updated = Signal(str)  # message
    workflow_state_changed = Signal(str, dict)  # (state, context)

    # Filtered signals (emit to specific subscribers only)
    # Note: Qt signals can't be truly filtered at signal level, but we can
    # provide filtered emit methods that check subscriptions before emitting
    filtered_data = Signal(str, str, dict)  # (source_plugin_id, target_plugin_id, data)

    _instance = None

    def __new__(cls):
        """Ensure only one EventBus instance exists (singleton)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the event bus.

        This will only run once due to singleton pattern.
        """
        if not hasattr(self, '_initialized'):
            super().__init__()
            self._initialized = True
            self.logger = logging.getLogger("bmlibrarian.gui.qt.core.EventBus")

            # Event filtering support
            # Maps event_type -> set of plugin_ids interested in this event
            self._event_subscriptions: Dict[str, set] = {}

            # Track all connected plugins for debugging
            self._registered_plugins: set = set()

            self.logger.debug("EventBus initialized")

    def register_plugin(self, plugin_id: str):
        """Register a plugin with the event bus.

        This is optional but helps with debugging and statistics.

        Args:
            plugin_id: ID of plugin to register
        """
        self._registered_plugins.add(plugin_id)
        self.logger.debug(f"Plugin '{plugin_id}' registered with EventBus")

    def unregister_plugin(self, plugin_id: str):
        """Unregister a plugin from the event bus.

        This removes the plugin from all event subscriptions and registrations.

        Args:
            plugin_id: ID of plugin to unregister
        """
        # Remove from registered plugins
        self._registered_plugins.discard(plugin_id)

        # Remove from all event subscriptions
        for event_type in list(self._event_subscriptions.keys()):
            self._event_subscriptions[event_type].discard(plugin_id)
            if not self._event_subscriptions[event_type]:
                del self._event_subscriptions[event_type]

        self.logger.debug(f"Plugin '{plugin_id}' unregistered from EventBus")

    def subscribe_to_event(self, plugin_id: str, event_type: str):
        """Subscribe a plugin to a specific event type.

        This enables event filtering - only subscribed plugins will receive
        events when using publish_data_filtered().

        Args:
            plugin_id: ID of plugin subscribing
            event_type: Type of event to subscribe to (e.g., "search_completed")

        Example:
            event_bus.subscribe_to_event("research", "search_completed")
            event_bus.subscribe_to_event("research", "document_scored")
        """
        if event_type not in self._event_subscriptions:
            self._event_subscriptions[event_type] = set()

        self._event_subscriptions[event_type].add(plugin_id)
        self.logger.debug(
            f"Plugin '{plugin_id}' subscribed to event '{event_type}'"
        )

    def unsubscribe_from_event(self, plugin_id: str, event_type: str):
        """Unsubscribe a plugin from a specific event type.

        Args:
            plugin_id: ID of plugin unsubscribing
            event_type: Type of event to unsubscribe from
        """
        if event_type in self._event_subscriptions:
            self._event_subscriptions[event_type].discard(plugin_id)
            if not self._event_subscriptions[event_type]:
                del self._event_subscriptions[event_type]

        self.logger.debug(
            f"Plugin '{plugin_id}' unsubscribed from event '{event_type}'"
        )

    def get_subscribers(self, event_type: str) -> set:
        """Get set of plugin IDs subscribed to an event type.

        Args:
            event_type: Event type to query

        Returns:
            set: Set of plugin IDs subscribed to this event
        """
        return self._event_subscriptions.get(event_type, set()).copy()

    def publish_data(self, source_plugin_id: str, data: Dict[str, Any]):
        """Publish data from a plugin to all listeners.

        This emits the data_shared signal which all connected plugins can receive.
        Use this for broadcasts that all plugins might be interested in.

        Args:
            source_plugin_id: ID of plugin publishing the data
            data: Dictionary containing event data. Should include:
                  - "event": str - Event type identifier
                  - Other fields as needed for the event

        Example:
            event_bus.publish_data("search", {
                "event": "search_completed",
                "query": "diabetes treatment",
                "result_count": 150
            })
        """
        self.data_shared.emit(source_plugin_id, data)
        self.logger.debug(
            f"Published data from '{source_plugin_id}': "
            f"event={data.get('event', 'unknown')}"
        )

    def publish_data_filtered(
        self,
        source_plugin_id: str,
        event_type: str,
        data: Dict[str, Any],
        target_plugins: Optional[List[str]] = None
    ):
        """Publish data with filtering to reduce overhead.

        This is the performance-optimized version that only emits to plugins
        that have subscribed to this event_type, or to explicitly specified
        target plugins.

        Args:
            source_plugin_id: ID of plugin publishing
            event_type: Type of event (used for subscription filtering)
            data: Event data dictionary
            target_plugins: Optional list of specific plugin IDs to target.
                          If None, uses subscription-based filtering.

        Example:
            # Emit only to subscribers of "document_scored"
            event_bus.publish_data_filtered(
                "scoring",
                "document_scored",
                {"doc_id": 123, "score": 4.5}
            )

            # Emit only to specific plugins
            event_bus.publish_data_filtered(
                "research",
                "custom_event",
                {"message": "hello"},
                target_plugins=["search", "fact_checker"]
            )
        """
        # Determine which plugins should receive this event
        if target_plugins is not None:
            # Explicit targeting
            recipients = set(target_plugins)
        else:
            # Subscription-based filtering
            recipients = self.get_subscribers(event_type)

        if not recipients:
            self.logger.debug(
                f"No recipients for event '{event_type}' from '{source_plugin_id}'"
            )
            return

        # Emit filtered signal for each target
        for target_id in recipients:
            self.filtered_data.emit(source_plugin_id, target_id, data)

        self.logger.debug(
            f"Published filtered data from '{source_plugin_id}' "
            f"to {len(recipients)} recipients: event={event_type}"
        )

    def request_navigation(self, target_plugin_id: str):
        """Request navigation to a specific tab.

        Args:
            target_plugin_id: ID of plugin/tab to navigate to

        Example:
            event_bus.request_navigation("configuration")
        """
        self.navigation_requested.emit(target_plugin_id)
        self.logger.debug(f"Navigation requested to '{target_plugin_id}'")

    def update_status(self, message: str):
        """Update application status bar.

        Args:
            message: Status message to display

        Example:
            event_bus.update_status("Processing documents...")
        """
        self.status_updated.emit(message)

    def notify_workflow_state(self, state: str, context: Dict[str, Any]):
        """Notify all plugins of workflow state change.

        This is useful for coordinating multi-plugin workflows.

        Args:
            state: Workflow state identifier (e.g., "query_completed")
            context: Dictionary with workflow context data

        Example:
            event_bus.notify_workflow_state("scoring_complete", {
                "total_documents": 150,
                "high_score_count": 25
            })
        """
        self.workflow_state_changed.emit(state, context)
        self.logger.debug(f"Workflow state changed: {state}")

    def get_statistics(self) -> Dict[str, Any]:
        """Get EventBus statistics for debugging.

        Returns:
            Dict with statistics about registered plugins and subscriptions
        """
        return {
            "registered_plugins": len(self._registered_plugins),
            "plugin_ids": list(self._registered_plugins),
            "event_types": len(self._event_subscriptions),
            "event_subscriptions": {
                event_type: len(subscribers)
                for event_type, subscribers in self._event_subscriptions.items()
            },
            "total_subscriptions": sum(
                len(subs) for subs in self._event_subscriptions.values()
            ),
        }

    def clear_all_subscriptions(self):
        """Clear all event subscriptions.

        Warning: This is mainly for testing. In production, plugins should
        properly unregister themselves during cleanup.
        """
        self._event_subscriptions.clear()
        self._registered_plugins.clear()
        self.logger.warning("All EventBus subscriptions cleared")
