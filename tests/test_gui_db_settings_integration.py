"""Tests for GUI database settings integration.

Tests the Phase 3 GUI integration for database-backed settings:
- Application user context setup after login
- Configuration tab database sync controls
- User profile widget functionality

Note: All tests are skipped if PySide6/Qt is not available in the test environment.
"""

import json

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
from typing import Iterator

# The settings/configuration tabs list Ollama models when built.
pytestmark = pytest.mark.usefixtures("offline_model_list")


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


@pytest.fixture(autouse=True)
def qapp():
    """Provide a real QApplication before any Qt code runs.

    Without one, Qt aborts the whole interpreter (not just the test) on the
    first font/widget use, e.g. get_font_scale() in BMLibrarianApplication,
    whose own QApplication is patched out below. Other Qt test modules used
    to create it first, so this module only passed in a full-suite run.
    """
    if not _check_pyside6_available():
        yield None
        return
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


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
            # _setup_user_context imports get_config locally from bmlibrarian.config
            with patch('bmlibrarian.config.get_config') as mock_get_config:
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

    def test_save_with_failed_database_sync_warns_instead_of_success(self):
        """A Save whose database part fails is not reported as a success (#437)."""
        module = 'bmlibrarian.gui.qt.plugins.configuration.config_tab'
        with patch(f'{module}.get_config') as mock_get_config, \
                patch(f'{module}.QMessageBox') as mock_box:
            mock_config = MagicMock()
            mock_config.has_user_context.return_value = False
            mock_config._config = {'models': {}, 'ollama': {}, 'agents': {}}
            mock_get_config.return_value = mock_config

            from bmlibrarian.gui.qt.plugins.configuration.config_tab import ConfigurationTabWidget

            widget = ConfigurationTabWidget()
            mock_config.has_user_context.return_value = True
            mock_config.sync_to_database.side_effect = RuntimeError("could not be loaded")

            widget._save_to_default()

            mock_box.information.assert_not_called()
            mock_box.warning.assert_called_once()
            assert "could not be loaded" in mock_box.warning.call_args.args[2]


@skip_if_no_qt
class TestConfigurationTabEnvOverrides:
    """The Configuration tab never saves or drops a BMLIB_* value (#477, #480)."""

    MODULE = 'bmlibrarian.gui.qt.plugins.configuration.config_tab'
    ENV_HOST = 'http://gpu:11434'

    @pytest.fixture
    def tab(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple]:
        """A tab on a real config with BMLIB_OLLAMA_HOST set and HOME in tmp_path.

        Yields:
            (ConfigurationTabWidget, BMLibrarianConfig) pair.
        """
        from bmlibrarian.config import BMLibrarianConfig, ENV_OVERRIDES

        for env_var in ENV_OVERRIDES:
            monkeypatch.delenv(env_var, raising=False)
        monkeypatch.setenv('BMLIB_OLLAMA_HOST', self.ENV_HOST)
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)
        with patch('bmlibrarian.utils.config_loader.load_config_with_fallback', return_value={}):
            config = BMLibrarianConfig()
        with patch(f'{self.MODULE}.get_config', return_value=config), \
                patch(f'{self.MODULE}.list_ollama_models', return_value=[]), \
                patch(f'{self.MODULE}.QMessageBox'):
            from bmlibrarian.gui.qt.plugins.configuration.config_tab import ConfigurationTabWidget
            yield ConfigurationTabWidget(), config

    def test_save_after_reset_keeps_env_value_in_memory(self, tab: tuple, tmp_path: Path) -> None:
        """Saving the reset fields writes the default but the env value still applies."""
        from bmlibrarian.config import DEFAULT_CONFIG

        widget, config = tab
        assert widget.general_widget.ollama_url_input.text() == self.ENV_HOST
        widget.general_widget.update_from_config(DEFAULT_CONFIG)  # what Reset does

        widget._save_to_default()

        saved = json.loads((tmp_path / '.bmlibrarian' / 'config.json').read_text())
        assert saved['ollama']['host'] == DEFAULT_CONFIG['ollama']['host']
        assert config.get('ollama.host') == self.ENV_HOST

    def test_save_as_leaves_env_value_out(self, tab: tuple, tmp_path: Path) -> None:
        """Save As writes the value underneath the env one, and keeps a user edit."""
        from bmlibrarian.config import DEFAULT_CONFIG

        widget, _ = tab
        target = tmp_path / 'out.json'
        with patch(f'{self.MODULE}.QFileDialog.getSaveFileName', return_value=(str(target), '')):
            widget._save_config_as()
            assert json.loads(target.read_text())['ollama']['host'] == DEFAULT_CONFIG['ollama']['host']

            widget.general_widget.ollama_url_input.setText('http://mine:11434')
            widget._save_config_as()
            assert json.loads(target.read_text())['ollama']['host'] == 'http://mine:11434'


@skip_if_no_qt
class TestSettingsLoadFailureAtLogin:
    """A failed settings load at login is shown to the user (#437)."""

    def test_failed_load_is_recorded_and_shown_as_toast(self):
        """_setup_user_context records the failure and a warning toast reports it."""
        from bmlibrarian.gui.qt.core.application import BMLibrarianApplication
        from bmlibrarian.gui.qt.dialogs import LoginResult
        from bmlibrarian.gui.qt.widgets.toast import ToastLevel

        with patch('bmlibrarian.gui.qt.core.application.QApplication'), \
                patch('bmlibrarian.config.get_config') as mock_get_config:
            mock_config = MagicMock()
            mock_config.settings_load_failed.return_value = True
            mock_get_config.return_value = mock_config

            app = BMLibrarianApplication(['test'])
            app._login_result = LoginResult(
                user_id=42, username="testuser", email="t@example.com",
                session_token="tok",
            )
            app._db_connection = MagicMock()
            app._setup_user_context()
            assert app._settings_load_failed is True

            app.main_window = MagicMock()
            with patch('bmlibrarian.gui.qt.core.application.show_toast') as mock_toast:
                app._warn_if_settings_load_failed()

            mock_toast.assert_called_once()
            assert mock_toast.call_args.args[0] is app.main_window
            assert mock_toast.call_args.args[2] == ToastLevel.WARNING


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
