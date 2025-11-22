"""BMLibrarian Authentication Module.

This module provides user authentication and session management functionality.
"""

from .user_service import (
    UserService,
    AuthenticationError,
    RegistrationError,
    UserNotFoundError,
    InvalidCredentialsError,
    UsernameExistsError,
    EmailExistsError,
)
from .user_settings import UserSettingsManager

__all__ = [
    "UserService",
    "AuthenticationError",
    "RegistrationError",
    "UserNotFoundError",
    "InvalidCredentialsError",
    "UsernameExistsError",
    "EmailExistsError",
    "UserSettingsManager",
]
