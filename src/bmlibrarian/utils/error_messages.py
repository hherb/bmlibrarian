"""Standardized Error Messages for BMLibrarian.

Provides user-friendly error messages for common operations,
ensuring consistent messaging across the application while
maintaining technical details for logging.
"""

import logging
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories of errors for consistent messaging."""
    NETWORK = "network"
    FILE = "file"
    AUTHENTICATION = "authentication"
    CONFIGURATION = "configuration"
    PERMISSION = "permission"
    TIMEOUT = "timeout"
    VALIDATION = "validation"
    INTERNAL = "internal"


class UserFriendlyError:
    """Encapsulates an error with both user-friendly and technical details.

    Attributes:
        user_message: Message suitable for display to end users
        technical_message: Detailed message for logging/debugging
        category: Error category for routing/handling
        original_exception: Original exception if available
    """

    def __init__(
        self,
        user_message: str,
        technical_message: Optional[str] = None,
        category: ErrorCategory = ErrorCategory.INTERNAL,
        original_exception: Optional[Exception] = None
    ):
        """Initialize user-friendly error.

        Args:
            user_message: Message to display to the user
            technical_message: Detailed technical message for logs
            category: Error category
            original_exception: Original exception that caused this error
        """
        self.user_message = user_message
        self.technical_message = technical_message or user_message
        self.category = category
        self.original_exception = original_exception

    def __str__(self) -> str:
        """Return user-friendly message."""
        return self.user_message

    def log(self, level: int = logging.ERROR) -> None:
        """Log the technical error details."""
        logger.log(level, self.technical_message, exc_info=self.original_exception)


def format_pdf_download_error(
    error: Exception,
    doc_id: Optional[int] = None,
    url: Optional[str] = None
) -> UserFriendlyError:
    """Format a PDF download error with user-friendly message.

    Args:
        error: The original exception
        doc_id: Document ID if available
        url: URL that was being accessed if available

    Returns:
        UserFriendlyError with appropriate messaging
    """
    error_str = str(error).lower()
    doc_context = f" for document {doc_id}" if doc_id else ""

    # Check for specific error patterns and provide user-friendly messages
    if "403" in error_str:
        return UserFriendlyError(
            user_message=f"Access restricted{doc_context}. This content may require institutional subscription.",
            technical_message=f"HTTP 403 - Access denied{doc_context}: {error}",
            category=ErrorCategory.PERMISSION,
            original_exception=error
        )

    if "404" in error_str:
        return UserFriendlyError(
            user_message=f"PDF not found{doc_context}. The document may have been moved or removed.",
            technical_message=f"HTTP 404 - Not found{doc_context}: {error}",
            category=ErrorCategory.FILE,
            original_exception=error
        )

    if "timeout" in error_str or "timed out" in error_str:
        return UserFriendlyError(
            user_message=f"Download timed out{doc_context}. Please try again or check your connection.",
            technical_message=f"Timeout error{doc_context}: {error}",
            category=ErrorCategory.TIMEOUT,
            original_exception=error
        )

    if "connection" in error_str or "network" in error_str:
        return UserFriendlyError(
            user_message=f"Network error{doc_context}. Please check your internet connection.",
            technical_message=f"Network error{doc_context}: {error}",
            category=ErrorCategory.NETWORK,
            original_exception=error
        )

    if "ssl" in error_str or "certificate" in error_str:
        return UserFriendlyError(
            user_message=f"Secure connection failed{doc_context}. The server's security certificate may be invalid.",
            technical_message=f"SSL/TLS error{doc_context}: {error}",
            category=ErrorCategory.NETWORK,
            original_exception=error
        )

    if isinstance(error, FileNotFoundError):
        return UserFriendlyError(
            user_message=f"File not found{doc_context}. The download may have failed.",
            technical_message=f"File not found{doc_context}: {error}",
            category=ErrorCategory.FILE,
            original_exception=error
        )

    if isinstance(error, PermissionError):
        return UserFriendlyError(
            user_message=f"Permission denied{doc_context}. Check folder permissions.",
            technical_message=f"Permission error{doc_context}: {error}",
            category=ErrorCategory.PERMISSION,
            original_exception=error
        )

    if isinstance(error, ValueError):
        return UserFriendlyError(
            user_message=f"Invalid data received{doc_context}. The PDF may be corrupted.",
            technical_message=f"Validation error{doc_context}: {error}",
            category=ErrorCategory.VALIDATION,
            original_exception=error
        )

    # Generic fallback
    return UserFriendlyError(
        user_message=f"Download failed{doc_context}. Please try again.",
        technical_message=f"Download error{doc_context}: {error}",
        category=ErrorCategory.INTERNAL,
        original_exception=error
    )


def format_configuration_error(
    error: Exception,
    config_key: Optional[str] = None
) -> UserFriendlyError:
    """Format a configuration error with user-friendly message.

    Args:
        error: The original exception
        config_key: Configuration key that caused the error

    Returns:
        UserFriendlyError with appropriate messaging
    """
    key_context = f" ({config_key})" if config_key else ""

    if "url" in str(error).lower():
        return UserFriendlyError(
            user_message=f"Invalid URL in configuration{key_context}. Please check your settings.",
            technical_message=f"URL configuration error{key_context}: {error}",
            category=ErrorCategory.CONFIGURATION,
            original_exception=error
        )

    if "timeout" in str(error).lower():
        return UserFriendlyError(
            user_message=f"Invalid timeout value{key_context}. Please use a value between the allowed range.",
            technical_message=f"Timeout configuration error{key_context}: {error}",
            category=ErrorCategory.CONFIGURATION,
            original_exception=error
        )

    return UserFriendlyError(
        user_message=f"Configuration error{key_context}. Please check your settings.",
        technical_message=f"Configuration error{key_context}: {error}",
        category=ErrorCategory.CONFIGURATION,
        original_exception=error
    )


def format_authentication_error(
    error: Exception,
    service: str = "service"
) -> UserFriendlyError:
    """Format an authentication error with user-friendly message.

    Args:
        error: The original exception
        service: Name of the service that failed authentication

    Returns:
        UserFriendlyError with appropriate messaging
    """
    error_str = str(error).lower()

    if "expired" in error_str:
        return UserFriendlyError(
            user_message=f"Your {service} session has expired. Please log in again.",
            technical_message=f"Session expired for {service}: {error}",
            category=ErrorCategory.AUTHENTICATION,
            original_exception=error
        )

    if "invalid" in error_str or "incorrect" in error_str:
        return UserFriendlyError(
            user_message=f"Invalid credentials for {service}. Please check your login details.",
            technical_message=f"Invalid credentials for {service}: {error}",
            category=ErrorCategory.AUTHENTICATION,
            original_exception=error
        )

    return UserFriendlyError(
        user_message=f"Authentication failed for {service}. Please try again.",
        technical_message=f"Authentication error for {service}: {error}",
        category=ErrorCategory.AUTHENTICATION,
        original_exception=error
    )
