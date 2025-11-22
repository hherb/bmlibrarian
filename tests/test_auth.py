"""Tests for BMLibrarian authentication module.

Tests password hashing, user service, and settings manager functionality.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from bmlibrarian.auth.user_service import (
    _hash_password,
    _verify_password,
    UserService,
    User,
    AuthenticationError,
    RegistrationError,
    UserNotFoundError,
    InvalidCredentialsError,
    UsernameExistsError,
    EmailExistsError,
    SALT_LENGTH_BYTES,
    MIN_PASSWORD_LENGTH,
    HASH_ITERATIONS,
    HASH_ALGORITHM,
)
from bmlibrarian.auth.user_settings import (
    UserSettingsManager,
    VALID_CATEGORIES,
)


class TestPasswordHashing:
    """Tests for password hashing functions."""

    def test_hash_password_returns_salted_hash(self) -> None:
        """Test that _hash_password returns a salted hash in correct format."""
        password = "test_password_123"
        result = _hash_password(password)

        # Should contain exactly one $ separator
        assert result.count('$') == 1

        # Should have two hex-encoded parts
        salt_hex, hash_hex = result.split('$')
        assert len(salt_hex) == SALT_LENGTH_BYTES * 2  # Hex encoding doubles length
        assert len(hash_hex) > 0

        # Should be valid hex
        bytes.fromhex(salt_hex)
        bytes.fromhex(hash_hex)

    def test_hash_password_with_same_salt_is_deterministic(self) -> None:
        """Test that same password and salt produce same hash."""
        password = "test_password"
        salt = b'\x00' * SALT_LENGTH_BYTES

        hash1 = _hash_password(password, salt)
        hash2 = _hash_password(password, salt)

        assert hash1 == hash2

    def test_hash_password_different_salts_produce_different_hashes(self) -> None:
        """Test that different salts produce different hashes."""
        password = "test_password"
        salt1 = b'\x00' * SALT_LENGTH_BYTES
        salt2 = b'\xff' * SALT_LENGTH_BYTES

        hash1 = _hash_password(password, salt1)
        hash2 = _hash_password(password, salt2)

        assert hash1 != hash2

    def test_verify_password_correct(self) -> None:
        """Test that correct password verifies successfully."""
        password = "correct_password"
        stored_hash = _hash_password(password)

        assert _verify_password(password, stored_hash) is True

    def test_verify_password_incorrect(self) -> None:
        """Test that incorrect password fails verification."""
        stored_hash = _hash_password("correct_password")

        assert _verify_password("wrong_password", stored_hash) is False

    def test_verify_password_invalid_format(self) -> None:
        """Test that invalid hash format returns False."""
        assert _verify_password("password", "invalid_hash_format") is False
        assert _verify_password("password", "") is False
        assert _verify_password("password", "no_separator") is False

    def test_verify_password_empty_inputs(self) -> None:
        """Test empty inputs handling."""
        stored_hash = _hash_password("password")
        assert _verify_password("", stored_hash) is False


class TestUserServiceValidation:
    """Tests for UserService input validation."""

    @pytest.fixture
    def mock_connection(self) -> Mock:
        """Create a mock database connection."""
        conn = MagicMock()
        conn.cursor.return_value.__enter__ = Mock(return_value=MagicMock())
        conn.cursor.return_value.__exit__ = Mock(return_value=False)
        return conn

    def test_register_empty_username_raises(self, mock_connection: Mock) -> None:
        """Test that empty username raises RegistrationError."""
        service = UserService(mock_connection)

        with pytest.raises(RegistrationError, match="Username cannot be empty"):
            service.register("", "test@test.com", "password")

        with pytest.raises(RegistrationError, match="Username cannot be empty"):
            service.register("   ", "test@test.com", "password")

    def test_register_empty_email_raises(self, mock_connection: Mock) -> None:
        """Test that empty email raises RegistrationError."""
        service = UserService(mock_connection)

        with pytest.raises(RegistrationError, match="Email cannot be empty"):
            service.register("username", "", "password")

    def test_register_empty_password_raises(self, mock_connection: Mock) -> None:
        """Test that empty password raises RegistrationError."""
        service = UserService(mock_connection)

        with pytest.raises(RegistrationError, match="Password cannot be empty"):
            service.register("username", "test@test.com", "")

    def test_register_short_password_raises(self, mock_connection: Mock) -> None:
        """Test that short password raises RegistrationError."""
        service = UserService(mock_connection)
        short_password = "a" * (MIN_PASSWORD_LENGTH - 1)

        with pytest.raises(RegistrationError, match=f"at least {MIN_PASSWORD_LENGTH}"):
            service.register("username", "test@test.com", short_password)

    def test_authenticate_empty_credentials_raises(self, mock_connection: Mock) -> None:
        """Test that empty credentials raise InvalidCredentialsError."""
        service = UserService(mock_connection)

        with pytest.raises(InvalidCredentialsError, match="required"):
            service.authenticate("", "password")

        with pytest.raises(InvalidCredentialsError, match="required"):
            service.authenticate("username", "")


class TestUserSettingsManagerValidation:
    """Tests for UserSettingsManager input validation."""

    @pytest.fixture
    def mock_connection(self) -> Mock:
        """Create a mock database connection."""
        conn = MagicMock()
        conn.cursor.return_value.__enter__ = Mock(return_value=MagicMock())
        conn.cursor.return_value.__exit__ = Mock(return_value=False)
        return conn

    def test_valid_categories_constant(self) -> None:
        """Test that VALID_CATEGORIES contains expected categories."""
        expected = {
            'models', 'ollama', 'agents', 'database', 'search',
            'query_generation', 'gui', 'openathens', 'pdf', 'general'
        }
        assert VALID_CATEGORIES == expected

    def test_get_invalid_category_raises(self, mock_connection: Mock) -> None:
        """Test that invalid category raises ValueError."""
        manager = UserSettingsManager(mock_connection, user_id=1)

        with pytest.raises(ValueError, match="Invalid category"):
            manager.get("invalid_category")

    def test_set_invalid_category_raises(self, mock_connection: Mock) -> None:
        """Test that invalid category raises ValueError."""
        manager = UserSettingsManager(mock_connection, user_id=1)

        with pytest.raises(ValueError, match="Invalid category"):
            manager.set("invalid_category", {"key": "value"})

    def test_user_id_property(self, mock_connection: Mock) -> None:
        """Test that user_id property returns correct value."""
        manager = UserSettingsManager(mock_connection, user_id=42)
        assert manager.user_id == 42


class TestConstants:
    """Tests for module constants."""

    def test_salt_length_is_reasonable(self) -> None:
        """Test salt length is cryptographically reasonable (at least 16 bytes)."""
        assert SALT_LENGTH_BYTES >= 16

    def test_hash_iterations_is_reasonable(self) -> None:
        """Test hash iterations is reasonable for security."""
        # OWASP recommends at least 10,000 for PBKDF2-SHA256
        assert HASH_ITERATIONS >= 10000

    def test_hash_algorithm_is_secure(self) -> None:
        """Test hash algorithm is a secure choice."""
        secure_algorithms = {"sha256", "sha384", "sha512"}
        assert HASH_ALGORITHM in secure_algorithms

    def test_min_password_length_is_reasonable(self) -> None:
        """Test minimum password length is at least 4."""
        assert MIN_PASSWORD_LENGTH >= 4
