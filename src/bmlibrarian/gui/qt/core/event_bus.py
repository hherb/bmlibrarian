"""
Event bus for inter-plugin communication in BMLibrarian Qt GUI.

Provides a centralized event system for plugins to communicate without
direct dependencies.
"""

from typing import Dict, Any, Callable
from PySide6.QtCore import QObject, Signal


class EventBus(QObject):
    """
    Centralized event bus for inter-plugin communication.

    Plugins can emit and subscribe to events without knowing about each other.
    """

    # Signals for different event types
    data_published = Signal(str, dict)  # (source_plugin_id, data)
    command_issued = Signal(str, str, dict)  # (source, command_name, params)
    status_update = Signal(str, str)  # (source, status_message)

    def __init__(self):
        """Initialize the event bus."""
        super().__init__()
        self._data_store: Dict[str, Any] = {}
        self._subscribers: Dict[str, list[Callable]] = {}

    def publish_data(self, source: str, data: Dict[str, Any]):
        """
        Publish data from a plugin.

        Args:
            source: Plugin ID publishing the data
            data: Data dictionary to publish
        """
        # Store data
        self._data_store[source] = data

        # Emit signal
        self.data_published.emit(source, data)

        # Notify subscribers
        if source in self._subscribers:
            for callback in self._subscribers[source]:
                try:
                    callback(data)
                except Exception as e:
                    print(f"Error in event subscriber callback: {e}")

    def get_data(self, source: str) -> Dict[str, Any] | None:
        """
        Get latest data from a plugin.

        Args:
            source: Plugin ID to get data from

        Returns:
            Data dictionary or None if no data available
        """
        return self._data_store.get(source)

    def subscribe(self, source: str, callback: Callable[[Dict[str, Any]], None]):
        """
        Subscribe to data updates from a plugin.

        Args:
            source: Plugin ID to subscribe to
            callback: Function to call when data is published
        """
        if source not in self._subscribers:
            self._subscribers[source] = []
        self._subscribers[source].append(callback)

    def unsubscribe(self, source: str, callback: Callable[[Dict[str, Any]], None]):
        """
        Unsubscribe from data updates.

        Args:
            source: Plugin ID to unsubscribe from
            callback: Callback function to remove
        """
        if source in self._subscribers and callback in self._subscribers[source]:
            self._subscribers[source].remove(callback)

    def issue_command(self, source: str, command: str, params: Dict[str, Any] | None = None):
        """
        Issue a command that plugins can respond to.

        Args:
            source: Plugin ID issuing the command
            command: Command name
            params: Optional command parameters
        """
        params = params or {}
        self.command_issued.emit(source, command, params)

    def update_status(self, source: str, message: str):
        """
        Emit a status update.

        Args:
            source: Plugin ID updating status
            message: Status message
        """
        self.status_update.emit(source, message)

    def clear_data(self, source: str | None = None):
        """
        Clear stored data.

        Args:
            source: Optional plugin ID. If None, clears all data.
        """
        if source is None:
            self._data_store.clear()
        elif source in self._data_store:
            del self._data_store[source]
