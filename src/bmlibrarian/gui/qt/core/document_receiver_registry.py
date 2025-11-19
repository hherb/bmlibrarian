"""Registry for document receivers.

This module provides a singleton registry for managing document receivers.
It tracks which plugins can receive documents and provides the list for
context menu generation.
"""

from typing import List, Dict, Any, Optional
import logging
from .document_receiver import IDocumentReceiver


class DocumentReceiverRegistry:
    """Singleton registry for document receivers.

    This class maintains a registry of all plugins that can receive documents.
    It's used by the document card context menu system to build the "Send to"
    submenu dynamically based on active receivers.

    Features:
    - Register/unregister document receivers
    - Query available receivers for a specific document
    - Singleton pattern ensures single source of truth

    Example:
        # In a lab tab plugin
        registry = DocumentReceiverRegistry()
        registry.register_receiver(self.tab_widget)

        # In document card context menu
        registry = DocumentReceiverRegistry()
        receivers = registry.get_available_receivers(document_data)
        for receiver in receivers:
            menu.addAction(receiver.get_receiver_name())
    """

    _instance = None

    def __new__(cls):
        """Ensure only one registry instance exists (singleton)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the registry.

        This will only run once due to singleton pattern.
        """
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self.logger = logging.getLogger("bmlibrarian.gui.qt.core.DocumentReceiverRegistry")
            self._receivers: Dict[str, IDocumentReceiver] = {}
            self.logger.debug("DocumentReceiverRegistry initialized")

    def register_receiver(self, receiver: IDocumentReceiver) -> None:
        """Register a document receiver.

        Args:
            receiver: Object implementing IDocumentReceiver interface

        Raises:
            TypeError: If receiver doesn't implement IDocumentReceiver
            ValueError: If receiver ID is already registered
        """
        if not isinstance(receiver, IDocumentReceiver):
            raise TypeError(
                f"Receiver must implement IDocumentReceiver interface, "
                f"got {type(receiver).__name__}"
            )

        receiver_id = receiver.get_receiver_id()
        if receiver_id in self._receivers:
            self.logger.warning(
                f"Receiver '{receiver_id}' is already registered, replacing"
            )

        self._receivers[receiver_id] = receiver
        self.logger.info(
            f"Registered document receiver: '{receiver_id}' "
            f"({receiver.get_receiver_name()})"
        )

    def unregister_receiver(self, receiver_id: str) -> None:
        """Unregister a document receiver.

        Args:
            receiver_id: ID of receiver to unregister
        """
        if receiver_id in self._receivers:
            receiver_name = self._receivers[receiver_id].get_receiver_name()
            del self._receivers[receiver_id]
            self.logger.info(
                f"Unregistered document receiver: '{receiver_id}' ({receiver_name})"
            )
        else:
            self.logger.warning(
                f"Attempted to unregister unknown receiver: '{receiver_id}'"
            )

    def get_receiver(self, receiver_id: str) -> Optional[IDocumentReceiver]:
        """Get a specific receiver by ID.

        Args:
            receiver_id: ID of receiver to retrieve

        Returns:
            IDocumentReceiver if found, None otherwise
        """
        return self._receivers.get(receiver_id)

    def get_all_receivers(self) -> List[IDocumentReceiver]:
        """Get all registered receivers.

        Returns:
            List of all registered receivers (ordered by registration)
        """
        return list(self._receivers.values())

    def get_available_receivers(
        self,
        document_data: Dict[str, Any]
    ) -> List[IDocumentReceiver]:
        """Get receivers that can accept a specific document.

        This filters receivers based on their can_receive_document() method.

        Args:
            document_data: Document data dictionary

        Returns:
            List of receivers that can process this document
        """
        available = []
        for receiver in self._receivers.values():
            try:
                if receiver.can_receive_document(document_data):
                    available.append(receiver)
            except Exception as e:
                self.logger.error(
                    f"Error checking if receiver '{receiver.get_receiver_id()}' "
                    f"can receive document: {e}"
                )
                # Continue checking other receivers

        return available

    def send_document(
        self,
        receiver_id: str,
        document_data: Dict[str, Any]
    ) -> bool:
        """Send a document to a specific receiver.

        Args:
            receiver_id: ID of target receiver
            document_data: Document data to send

        Returns:
            bool: True if document was sent successfully, False otherwise
        """
        receiver = self._receivers.get(receiver_id)
        if not receiver:
            self.logger.error(f"Unknown receiver: '{receiver_id}'")
            return False

        try:
            # Check if receiver can accept this document
            if not receiver.can_receive_document(document_data):
                self.logger.warning(
                    f"Receiver '{receiver_id}' cannot accept this document"
                )
                return False

            # Send document
            receiver.receive_document(document_data)
            self.logger.info(
                f"Sent document {document_data.get('id', 'unknown')} "
                f"to receiver '{receiver_id}'"
            )
            return True

        except Exception as e:
            self.logger.error(
                f"Error sending document to receiver '{receiver_id}': {e}",
                exc_info=True
            )
            return False

    def clear_all_receivers(self) -> None:
        """Clear all registered receivers.

        Warning: This is mainly for testing. In production, plugins should
        properly unregister themselves during cleanup.
        """
        count = len(self._receivers)
        self._receivers.clear()
        self.logger.warning(f"Cleared all {count} document receivers")

    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics for debugging.

        Returns:
            Dict with statistics about registered receivers
        """
        return {
            "receiver_count": len(self._receivers),
            "receiver_ids": list(self._receivers.keys()),
            "receiver_names": [
                receiver.get_receiver_name()
                for receiver in self._receivers.values()
            ]
        }
