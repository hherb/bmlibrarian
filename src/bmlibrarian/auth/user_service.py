"""User authentication service for BMLibrarian.

This module provides user registration, authentication, and session management.
Uses PostgreSQL's public.users table for user storage and bmlsettings schema
for session management.
"""

import hashlib
import secrets
import logging
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from psycopg import Connection
from psycopg.rows import dict_row


# ============================================================================
# Exceptions
# ============================================================================


class AuthenticationError(Exception):
    """Base exception for authentication errors."""
    pass


class RegistrationError(Exception):
    """Base exception for registration errors."""
    pass


class UserNotFoundError(AuthenticationError):
    """Raised when user is not found."""
    pass


class InvalidCredentialsError(AuthenticationError):
    """Raised when credentials are invalid."""
    pass


class UsernameExistsError(RegistrationError):
    """Raised when username already exists."""
    pass


class EmailExistsError(RegistrationError):
    """Raised when email already exists."""
    pass


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class User:
    """Represents a user in the system."""
    id: int
    username: str
    email: str
    firstname: Optional[str] = None
    surname: Optional[str] = None


@dataclass
class Session:
    """Represents an active user session."""
    session_id: int
    user_id: int
    session_token: str
    created_at: datetime
    expires_at: datetime
    last_active: datetime
    client_type: Optional[str] = None
    client_version: Optional[str] = None
    hostname: Optional[str] = None


# ============================================================================
# Password Hashing
# ============================================================================

# Salt length in bytes
SALT_LENGTH = 32
# Number of hash iterations (PBKDF2)
HASH_ITERATIONS = 100000
# Hash algorithm
HASH_ALGORITHM = "sha256"


def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Hash a password using PBKDF2 with SHA-256.

    Args:
        password: The plaintext password to hash.
        salt: Optional salt bytes. If None, a new salt is generated.

    Returns:
        A string in format "salt$hash" where both are hex-encoded.
    """
    if salt is None:
        salt = secrets.token_bytes(SALT_LENGTH)

    # Use PBKDF2 for secure password hashing
    dk = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode('utf-8'),
        salt,
        HASH_ITERATIONS
    )

    # Store as "salt$hash" in hex format
    return f"{salt.hex()}${dk.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored hash.

    Args:
        password: The plaintext password to verify.
        stored_hash: The stored hash in "salt$hash" format.

    Returns:
        True if the password matches, False otherwise.
    """
    try:
        salt_hex, hash_hex = stored_hash.split('$')
        salt = bytes.fromhex(salt_hex)

        # Hash the provided password with the same salt
        new_hash = _hash_password(password, salt)

        # Compare in constant time to prevent timing attacks
        return secrets.compare_digest(new_hash, stored_hash)
    except (ValueError, AttributeError):
        # Invalid hash format
        return False


# ============================================================================
# User Service
# ============================================================================


class UserService:
    """Service for user authentication and management.

    This service handles:
    - User registration
    - User authentication (login)
    - Session management
    - Password verification

    Example:
        from bmlibrarian.database import get_db_manager

        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            user_service = UserService(conn)

            # Register a new user
            user = user_service.register(
                username="john_doe",
                email="john@example.com",
                password="secure_password123"
            )

            # Authenticate
            user, session_token = user_service.authenticate(
                username="john_doe",
                password="secure_password123"
            )
    """

    # Session duration in hours
    DEFAULT_SESSION_DURATION_HOURS = 24

    def __init__(self, connection: Connection):
        """Initialize the user service.

        Args:
            connection: A psycopg database connection.
        """
        self._conn = connection
        self._logger = logging.getLogger("bmlibrarian.auth.UserService")

    def register(
        self,
        username: str,
        email: str,
        password: str,
        firstname: Optional[str] = None,
        surname: Optional[str] = None
    ) -> User:
        """Register a new user.

        Args:
            username: Unique username for the user.
            email: Email address (must be unique).
            password: Plaintext password (will be hashed).
            firstname: Optional first name.
            surname: Optional surname.

        Returns:
            The newly created User object.

        Raises:
            UsernameExistsError: If username already exists.
            EmailExistsError: If email already exists.
            RegistrationError: For other registration failures.
        """
        # Validate inputs
        if not username or not username.strip():
            raise RegistrationError("Username cannot be empty")
        if not email or not email.strip():
            raise RegistrationError("Email cannot be empty")
        if not password:
            raise RegistrationError("Password cannot be empty")
        if len(password) < 4:
            raise RegistrationError("Password must be at least 4 characters")

        username = username.strip()
        email = email.strip().lower()

        # Check if username exists
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM public.users WHERE username = %s",
                (username,)
            )
            if cur.fetchone():
                raise UsernameExistsError(f"Username '{username}' already exists")

            # Check if email exists
            cur.execute(
                "SELECT id FROM public.users WHERE email = %s",
                (email,)
            )
            if cur.fetchone():
                raise EmailExistsError(f"Email '{email}' already registered")

            # Hash password
            password_hash = _hash_password(password)

            # Insert new user
            cur.execute(
                """
                INSERT INTO public.users (username, email, pwdhash, firstname, surname)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (username, email, password_hash, firstname, surname)
            )
            result = cur.fetchone()
            if not result:
                raise RegistrationError("Failed to create user")

            user_id = result[0]

        self._conn.commit()
        self._logger.info(f"Registered new user: {username} (id={user_id})")

        return User(
            id=user_id,
            username=username,
            email=email,
            firstname=firstname,
            surname=surname
        )

    def authenticate(
        self,
        username: str,
        password: str,
        client_type: str = "qt_gui",
        client_version: Optional[str] = None,
        hostname: Optional[str] = None,
        create_session: bool = True
    ) -> tuple[User, Optional[str]]:
        """Authenticate a user and optionally create a session.

        Args:
            username: The username to authenticate.
            password: The plaintext password.
            client_type: Type of client (qt_gui, flet_gui, cli, api).
            client_version: Version of the client application.
            hostname: Hostname of the client machine.
            create_session: Whether to create a session token.

        Returns:
            Tuple of (User, session_token). session_token is None if
            create_session is False.

        Raises:
            UserNotFoundError: If user does not exist.
            InvalidCredentialsError: If password is incorrect.
        """
        if not username or not password:
            raise InvalidCredentialsError("Username and password are required")

        username = username.strip()

        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, username, email, pwdhash, firstname, surname
                FROM public.users
                WHERE username = %s
                """,
                (username,)
            )
            row = cur.fetchone()

        if not row:
            self._logger.warning(f"Login attempt for non-existent user: {username}")
            raise UserNotFoundError(f"User '{username}' not found")

        # Verify password
        if not _verify_password(password, row['pwdhash']):
            self._logger.warning(f"Invalid password for user: {username}")
            raise InvalidCredentialsError("Invalid password")

        user = User(
            id=row['id'],
            username=row['username'],
            email=row['email'],
            firstname=row['firstname'],
            surname=row['surname']
        )

        session_token = None
        if create_session:
            session_token = self._create_session(
                user.id,
                client_type=client_type,
                client_version=client_version,
                hostname=hostname
            )

        self._logger.info(f"User authenticated: {username}")
        return user, session_token

    def _create_session(
        self,
        user_id: int,
        client_type: str = "qt_gui",
        client_version: Optional[str] = None,
        hostname: Optional[str] = None,
        duration_hours: int = DEFAULT_SESSION_DURATION_HOURS
    ) -> str:
        """Create a new session for a user.

        Args:
            user_id: The user's ID.
            client_type: Type of client.
            client_version: Client version string.
            hostname: Client hostname.
            duration_hours: Session duration in hours.

        Returns:
            The session token string.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT bmlsettings.create_session(%s, %s, %s, %s, %s)
                """,
                (user_id, client_type, client_version, hostname, duration_hours)
            )
            result = cur.fetchone()
            session_token = result[0] if result else None

        self._conn.commit()
        return session_token

    def validate_session(self, session_token: str) -> Optional[User]:
        """Validate a session token and return the user.

        Args:
            session_token: The session token to validate.

        Returns:
            The User object if session is valid, None otherwise.
        """
        if not session_token:
            return None

        with self._conn.cursor(row_factory=dict_row) as cur:
            # Validate session and get user_id
            cur.execute(
                "SELECT bmlsettings.validate_session(%s)",
                (session_token,)
            )
            result = cur.fetchone()
            user_id = result[0] if result else None

            if not user_id:
                return None

            # Get user details
            cur.execute(
                """
                SELECT id, username, email, firstname, surname
                FROM public.users
                WHERE id = %s
                """,
                (user_id,)
            )
            row = cur.fetchone()

        if not row:
            return None

        self._conn.commit()
        return User(
            id=row['id'],
            username=row['username'],
            email=row['email'],
            firstname=row['firstname'],
            surname=row['surname']
        )

    def logout(self, session_token: str) -> bool:
        """Invalidate a session (logout).

        Args:
            session_token: The session token to invalidate.

        Returns:
            True if session was found and deleted, False otherwise.
        """
        if not session_token:
            return False

        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM bmlsettings.user_sessions
                WHERE session_token = %s
                """,
                (session_token,)
            )
            deleted = cur.rowcount > 0

        self._conn.commit()
        return deleted

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get a user by their ID.

        Args:
            user_id: The user's ID.

        Returns:
            The User object if found, None otherwise.
        """
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, username, email, firstname, surname
                FROM public.users
                WHERE id = %s
                """,
                (user_id,)
            )
            row = cur.fetchone()

        if not row:
            return None

        return User(
            id=row['id'],
            username=row['username'],
            email=row['email'],
            firstname=row['firstname'],
            surname=row['surname']
        )

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by their username.

        Args:
            username: The username to look up.

        Returns:
            The User object if found, None otherwise.
        """
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, username, email, firstname, surname
                FROM public.users
                WHERE username = %s
                """,
                (username,)
            )
            row = cur.fetchone()

        if not row:
            return None

        return User(
            id=row['id'],
            username=row['username'],
            email=row['email'],
            firstname=row['firstname'],
            surname=row['surname']
        )

    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions from the database.

        Returns:
            Number of sessions deleted.
        """
        with self._conn.cursor() as cur:
            cur.execute("SELECT bmlsettings.cleanup_expired_sessions()")
            result = cur.fetchone()
            count = result[0] if result else 0

        self._conn.commit()
        return count
