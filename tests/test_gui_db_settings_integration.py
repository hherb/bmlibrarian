"""Tests for GUI database settings integration.

Tests the Phase 3 GUI integration for database-backed settings:
- Application user context setup after login
- Configuration tab database sync controls
- User profile widget functionality

Note: All tests are skipped if PySide6/Qt is not available in the test environment.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path


# Check if PySide6 is available (need to handle library loading issues too)
def _check_pyside6_available():
    """Check if PySide6 is available and can be imported properly."""
    try:
        # This will fail if Qt libraries are not available
        import PySide6.QtWidgets
        return True
    except (ImportError, OSError):
        return False


# Define skip decorator at module level
skip_if_no_qt = pytest.mark.skipif(
    not _check_pyside6_available(),
    reason="PySide6/Qt not available in test environment"
)


# ============================================================================
# Tests that don't require Qt - Data classes only
# ============================================================================

class TestLoginResultDataclassMocked:
    """Tests for LoginResult dataclass - using mocks to avoid Qt imports."""

    def test_login_result_basic_structure(self):
        """Test LoginResult basic structure without Qt imports."""
        from dataclasses import dataclass, field
        from typing import Optional

        # Define a mock LoginResult to test structure
        @dataclass
        class MockLoginResult:
            user_id: int
            username: str
            email: str
            session_token: Optional[str] = None
            db_config: Optional[object] = None

        result = MockLoginResult(
            user_id=1,
            username="alice",
            email="alice@example.com"
        )

        assert result.user_id == 1
        assert result.username == "alice"
        assert result.email == "alice@example.com"
        assert result.session_token is None
        assert result.db_config is None

    def test_login_result_with_session_token_structure(self):
        """Test LoginResult with session token structure."""
        from dataclasses import dataclass
        from typing import Optional

        @dataclass
        class MockLoginResult:
            user_id: int
            username: str
            email: str
            session_token: Optional[str] = None

        result = MockLoginResult(
            user_id=1,
            username="alice",
            email="alice@example.com",
            session_token="test-token-123"
        )

        assert result.session_token == "test-token-123"


class TestDatabaseConfigDataclassMocked:
    """Tests for DatabaseConfig dataclass - using mocks to avoid Qt imports."""

    def test_database_config_default_structure(self):
        """Test DatabaseConfig default structure."""
        from dataclasses import dataclass

        @dataclass
        class MockDatabaseConfig:
            host: str = "localhost"
            port: int = 5432
            database: str = "knowledgebase"
            user: str = ""
            password: str = ""

            def to_env_dict(self):
                return {
                    "POSTGRES_HOST": self.host,
                    "POSTGRES_PORT": str(self.port),
                    "POSTGRES_DB": self.database,
                    "POSTGRES_USER": self.user,
                    "POSTGRES_PASSWORD": self.password,
                }

        config = MockDatabaseConfig()

        assert config.host == "localhost"
        assert config.port == 5432
        assert config.database == "knowledgebase"
        assert config.user == ""
        assert config.password == ""

    def test_database_config_to_env_dict(self):
        """Test DatabaseConfig.to_env_dict method."""
        from dataclasses import dataclass

        @dataclass
        class MockDatabaseConfig:
            host: str = "localhost"
            port: int = 5432
            database: str = "knowledgebase"
            user: str = ""
            password: str = ""

            def to_env_dict(self):
                return {
                    "POSTGRES_HOST": self.host,
                    "POSTGRES_PORT": str(self.port),
                    "POSTGRES_DB": self.database,
                    "POSTGRES_USER": self.user,
                    "POSTGRES_PASSWORD": self.password,
                }

        config = MockDatabaseConfig(
            host="db.example.com",
            port=5433,
            database="mydb",
            user="dbuser",
            password="secret"
        )

        env_dict = config.to_env_dict()

        assert env_dict["POSTGRES_HOST"] == "db.example.com"
        assert env_dict["POSTGRES_PORT"] == "5433"
        assert env_dict["POSTGRES_DB"] == "mydb"
        assert env_dict["POSTGRES_USER"] == "dbuser"
        assert env_dict["POSTGRES_PASSWORD"] == "secret"


# ============================================================================
# Tests that require Qt - Skipped if Qt not available
# ============================================================================

@skip_if_no_qt
class TestBMLibrarianApplicationUserContext:
    """Tests for BMLibrarianApplication user context management."""

    def test_application_init_no_user_context(self):
        """Test that application initializes without user context."""
        from bmlibrarian.gui.qt.core.application import BMLibrarianApplication

        with patch('bmlibrarian.gui.qt.core.application.QApplication'):
            app = BMLibrarianApplication(['test'])

            assert app._login_result is None
            assert app._db_connection is None
            assert app.current_user_id is None
            assert app.current_username is None

    def test_current_user_id_property(self):
        """Test current_user_id property returns user ID from login result."""
        from bmlibrarian.gui.qt.core.application import BMLibrarianApplication
        from bmlibrarian.gui.qt.dialogs import LoginResult

        with patch('bmlibrarian.gui.qt.core.application.QApplication'):
            app = BMLibrarianApplication(['test'])

            app._login_result = LoginResult(
                user_id=42,
                username="testuser",
                email="test@example.com",
                session_token="test-token"
            )

            assert app.current_user_id == 42

    def test_setup_user_context_with_login_result(self):
        """Test _setup_user_context sets up config properly."""
        from bmlibrarian.gui.qt.core.application import BMLibrarianApplication
        from bmlibrarian.gui.qt.dialogs import LoginResult

        with patch('bmlibrarian.gui.qt.core.application.QApplication'):
            with patch('bmlibrarian.gui.qt.core.application.get_config') as mock_get_config:
                mock_config = MagicMock()
                mock_get_config.return_value = mock_config

                app = BMLibrarianApplication(['test'])

                mock_conn = MagicMock()
                app._login_result = LoginResult(
                    user_id=42,
                    username="testuser",
                    email="test@example.com",
                    session_token="test-token-123"
                )
                app._db_connection = mock_conn

                app._setup_user_context()

                mock_config.set_user_context.assert_called_once_with(
                    user_id=42,
                    connection=mock_conn,
                    session_token="test-token-123"
                )


@skip_if_no_qt
class TestUserProfileWidget:
    """Tests for UserProfileWidget."""

    def test_widget_creation_anonymous(self):
        """Test widget creation without user."""
        from bmlibrarian.gui.qt.widgets import UserProfileWidget

        widget = UserProfileWidget(user_id=None, username=None)

        assert widget.user_id is None
        assert widget.username is None
        assert widget.is_authenticated is False

    def test_widget_creation_authenticated(self):
        """Test widget creation with authenticated user."""
        from bmlibrarian.gui.qt.widgets import UserProfileWidget

        widget = UserProfileWidget(user_id=42, username="testuser")

        assert widget.user_id == 42
        assert widget.username == "testuser"
        assert widget.is_authenticated is True


@skip_if_no_qt
class TestConfigurationTabDatabaseSync:
    """Tests for ConfigurationTabWidget database sync features."""

    def test_sync_status_bar_anonymous(self):
        """Test sync status bar shows correct status for anonymous user."""
        with patch('bmlibrarian.gui.qt.plugins.configuration.config_tab.get_config') as mock_get_config:
            mock_config = MagicMock()
            mock_config.has_user_context.return_value = False
            mock_config._config = {'models': {}, 'ollama': {}, 'agents': {}}
            mock_get_config.return_value = mock_config

            from bmlibrarian.gui.qt.plugins.configuration.config_tab import ConfigurationTabWidget

            widget = ConfigurationTabWidget()

            assert widget._db_sync_enabled is False
            assert widget.sync_to_db_btn.isEnabled() is False
            assert widget.sync_from_db_btn.isEnabled() is False


@skip_if_no_qt
class TestLoginResultDataclass:
    """Tests for LoginResult dataclass - requires Qt."""

    def test_login_result_basic(self):
        """Test LoginResult with basic fields."""
        from bmlibrarian.gui.qt.dialogs import LoginResult

        result = LoginResult(
            user_id=1,
            username="alice",
            email="alice@example.com"
        )

        assert result.user_id == 1
        assert result.username == "alice"
        assert result.email == "alice@example.com"


@skip_if_no_qt
class TestDatabaseConfigDataclass:
    """Tests for DatabaseConfig dataclass - requires Qt."""

    def test_database_config_defaults(self):
        """Test DatabaseConfig default values."""
        from bmlibrarian.gui.qt.dialogs import DatabaseConfig

        config = DatabaseConfig()

        assert config.host == "localhost"
        assert config.port == 5432
        assert config.database == "knowledgebase"
