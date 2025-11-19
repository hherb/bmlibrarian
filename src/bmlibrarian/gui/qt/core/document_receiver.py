"""Document receiver interface for plugins that can receive documents.

This module defines the interface for plugins that can receive documents
from other plugins (e.g., from the Search tab's "Send to" context menu).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class IDocumentReceiver(ABC):
    """Interface for plugins that can receive documents from other plugins.

    Plugins that implement this interface can register themselves to appear
    in the "Send to" context menu on document cards. When a user selects
    this plugin from the menu, the receive_document() method will be called
    with the document data.

    Example:
        class MyLabTab(QWidget, IDocumentReceiver):
            def get_receiver_id(self) -> str:
                return "my_lab"

            def get_receiver_name(self) -> str:
                return "My Lab"

            def can_receive_document(self, document_data: Dict[str, Any]) -> bool:
                return True  # Accept all documents

            def receive_document(self, document_data: Dict[str, Any]):
                doc_id = document_data.get('document_id') or document_data.get('id')
                self.load_document_by_id(doc_id)
    """

    @abstractmethod
    def get_receiver_id(self) -> str:
        """Get unique identifier for this receiver.

        Returns:
            str: Unique ID (typically the plugin_id)
        """
        pass

    @abstractmethod
    def get_receiver_name(self) -> str:
        """Get display name for this receiver.

        This is shown in the "Send to" context menu.

        Returns:
            str: Human-readable name (e.g., "PICO Lab", "PRISMA 2020 Lab")
        """
        pass

    @abstractmethod
    def can_receive_document(self, document_data: Dict[str, Any]) -> bool:
        """Check if this receiver can accept the given document.

        This allows receivers to filter which documents they can process.
        For example, PRISMA 2020 Lab might only accept systematic reviews.

        Args:
            document_data: Document data dictionary containing at minimum:
                - 'id' or 'document_id': int
                - 'title': str
                - Other fields as available

        Returns:
            bool: True if this receiver can process the document
        """
        pass

    @abstractmethod
    def receive_document(self, document_data: Dict[str, Any]) -> None:
        """Receive and process a document.

        This method is called when a user selects this receiver from the
        context menu. The receiver should load the document and prepare
        its UI accordingly. The receiver may also want to switch to its
        tab using the EventBus.

        Args:
            document_data: Full document data dictionary
        """
        pass

    def get_receiver_icon(self) -> Optional[str]:
        """Get optional icon name for this receiver.

        Returns:
            Optional[str]: Icon filename or None for default icon
        """
        return None

    def get_receiver_description(self) -> Optional[str]:
        """Get optional tooltip description for this receiver.

        Returns:
            Optional[str]: Tooltip text or None
        """
        return None
