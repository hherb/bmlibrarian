"""Tests for BMLibrarian configuration user context functionality.

Tests the database-backed user settings integration with BMLibrarianConfig.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
import json
import tempfile

from bmlibrarian.config import (
    BMLibrarianConfig,
    UserContext,
    VALID_SETTINGS_CATEGORIES,
    DEFAULT_CONFIG,
    ENV_OVERRIDES,
    get_config,
    reload_config,
)


@pytest.fixture(autouse=True)
def _no_user_config_file():
    """Keep the developer's ~/.bmlibrarian/config.json out of these tests."""
    with patch('bmlibrarian.utils.config_loader.load_config_with_fallback', return_value={}):
        yield


@pytest.fixture(autouse=True)
def _no_env_overrides(monkeypatch: pytest.MonkeyPatch):
    """Keep the developer's BMLIB_* variables out of these tests."""
    for env_var in ENV_OVERRIDES:
        monkeypatch.delenv(env_var, raising=False)


class TestUserContext:
    """Tests for the UserContext dataclass."""

    def test_user_context_creation(self) -> None:
        """Test UserContext can be created with required fields."""
        mock_conn = MagicMock()
        context = UserContext(user_id=1, connection=mock_conn)

        assert context.user_id == 1
        assert context.connection == mock_conn
        assert context.session_token is None

    def test_user_context_with_session_token(self) -> None:
        """Test UserContext can include session token."""
        mock_conn = MagicMock()
        context = UserContext(
            user_id=42,
            connection=mock_conn,
            session_token="test-token-123"
        )

        assert context.user_id == 42
        assert context.session_token == "test-token-123"


class TestValidSettingsCategories:
    """Tests for VALID_SETTINGS_CATEGORIES constant."""

    def test_categories_match_expected(self) -> None:
        """Test that VALID_SETTINGS_CATEGORIES contains expected categories."""
        expected = {
            'models', 'ollama', 'agents', 'database', 'search',
            'query_generation', 'gui', 'openathens', 'pdf', 'general', 'document_qa',
            'discovery', 'embeddings'
        }
        assert VALID_SETTINGS_CATEGORIES == expected

    def test_categories_is_frozenset(self) -> None:
        """Test that categories is immutable."""
        assert isinstance(VALID_SETTINGS_CATEGORIES, frozenset)


class TestBMLibrarianConfigUserContext:
    """Tests for BMLibrarianConfig user context management."""

    @pytest.fixture
    def config(self) -> BMLibrarianConfig:
        """Create a fresh config instance for each test."""
        return BMLibrarianConfig()

    @pytest.fixture
    def mock_connection(self) -> Mock:
        """Create a mock database connection."""
        conn = MagicMock()
        cursor_mock = MagicMock()
        conn.cursor.return_value.__enter__ = Mock(return_value=cursor_mock)
        conn.cursor.return_value.__exit__ = Mock(return_value=False)
        # Mock get_all_user_settings to return empty dict
        cursor_mock.fetchone.return_value = [{}]
        return conn

    def test_initial_state_no_user_context(self, config: BMLibrarianConfig) -> None:
        """Test that config starts without user context."""
        assert config.has_user_context() is False
        assert config.get_user_id() is None
        assert config.get_user_context() is None

    @patch('bmlibrarian.config.BMLibrarianConfig._sync_from_database')
    def test_set_user_context(
        self,
        mock_sync: Mock,
        config: BMLibrarianConfig,
        mock_connection: Mock
    ) -> None:
        """Test setting user context."""
        config.set_user_context(user_id=1, connection=mock_connection)

        assert config.has_user_context() is True
        assert config.get_user_id() == 1
        assert config.get_user_context() is not None
        assert config.get_user_context().user_id == 1
        mock_sync.assert_called_once()

    @patch('bmlibrarian.config.BMLibrarianConfig._sync_from_database')
    def test_set_user_context_with_session_token(
        self,
        mock_sync: Mock,
        config: BMLibrarianConfig,
        mock_connection: Mock
    ) -> None:
        """Test setting user context with session token."""
        config.set_user_context(
            user_id=42,
            connection=mock_connection,
            session_token="test-token"
        )

        context = config.get_user_context()
        assert context is not None
        assert context.session_token == "test-token"

    @patch('bmlibrarian.config.BMLibrarianConfig._sync_from_database')
    def test_clear_user_context(
        self,
        mock_sync: Mock,
        config: BMLibrarianConfig,
        mock_connection: Mock
    ) -> None:
        """Test clearing user context reverts to default behavior."""
        # Set user context first
        config.set_user_context(user_id=1, connection=mock_connection)
        assert config.has_user_context() is True

        # Clear it
        config.clear_user_context()

        assert config.has_user_context() is False
        assert config.get_user_id() is None
        assert config.get_user_context() is None

    def test_get_model_without_context(self, config: BMLibrarianConfig) -> None:
        """Test get_model works without user context."""
        # Should return from DEFAULT_CONFIG
        model = config.get_model("query_agent")
        assert model == DEFAULT_CONFIG["models"]["query_agent"]

    def test_get_agent_config_without_context(self, config: BMLibrarianConfig) -> None:
        """Test get_agent_config works without user context."""
        agent_config = config.get_agent_config("scoring")
        assert agent_config == DEFAULT_CONFIG["agents"]["scoring"]

    def test_get_without_context(self, config: BMLibrarianConfig) -> None:
        """Test get() works without user context."""
        host = config.get("ollama.host")
        assert host == DEFAULT_CONFIG["ollama"]["host"]

    def test_get_with_default(self, config: BMLibrarianConfig) -> None:
        """Test get() returns default for missing keys."""
        value = config.get("nonexistent.key", "default_value")
        assert value == "default_value"


class TestBMLibrarianConfigSyncOperations:
    """Tests for BMLibrarianConfig sync operations."""

    @pytest.fixture
    def config(self) -> BMLibrarianConfig:
        """Create a fresh config instance for each test."""
        return BMLibrarianConfig()

    def test_sync_to_database_without_context_raises(
        self,
        config: BMLibrarianConfig
    ) -> None:
        """Test sync_to_database raises when no user context."""
        with pytest.raises(RuntimeError, match="no user context set"):
            config.sync_to_database()

    @patch('bmlibrarian.config.BMLibrarianConfig._sync_from_database')
    def test_sync_to_database_with_context(
        self,
        mock_sync: Mock,
        config: BMLibrarianConfig
    ) -> None:
        """Test sync_to_database works with user context."""
        mock_conn = MagicMock()
        cursor_mock = MagicMock()
        mock_conn.cursor.return_value.__enter__ = Mock(return_value=cursor_mock)
        mock_conn.cursor.return_value.__exit__ = Mock(return_value=False)
        cursor_mock.fetchone.return_value = [{}]

        config.set_user_context(user_id=1, connection=mock_conn)

        # Mock the settings manager
        config._settings_manager = MagicMock()
        config._settings_manager.set = MagicMock(return_value=True)

        result = config.sync_to_database()
        assert result is True

    def test_failed_load_at_login_blocks_saving(
        self,
        config: BMLibrarianConfig
    ) -> None:
        """A failed settings load must not let Save overwrite stored settings (#437)."""
        manager = MagicMock()
        manager.get_own_settings.side_effect = RuntimeError("connection lost")
        with patch('bmlibrarian.auth.user_settings.UserSettingsManager', return_value=manager):
            config.set_user_context(user_id=1, connection=MagicMock())

        assert config.has_user_context() is True  # login still goes on
        with pytest.raises(RuntimeError, match="could not be loaded"):
            config.sync_to_database()
        manager.set.assert_not_called()

    def test_successful_reload_lifts_the_block(
        self,
        config: BMLibrarianConfig
    ) -> None:
        """Loading from the database again after a failure allows saving."""
        manager = MagicMock()
        manager.get_own_settings.side_effect = [RuntimeError("connection lost"), {}]
        with patch('bmlibrarian.auth.user_settings.UserSettingsManager', return_value=manager):
            config.set_user_context(user_id=1, connection=MagicMock())

        config._sync_from_database()
        assert config.sync_to_database() is True
        manager.set.assert_called()

    def test_explicit_reload_failure_raises(
        self,
        config: BMLibrarianConfig
    ) -> None:
        """A 'Sync from database' request reports the failure to its caller."""
        manager = MagicMock()
        manager.get_own_settings.side_effect = [{}, RuntimeError("connection lost")]
        with patch('bmlibrarian.auth.user_settings.UserSettingsManager', return_value=manager):
            config.set_user_context(user_id=1, connection=MagicMock())

        with pytest.raises(RuntimeError, match="connection lost"):
            config._sync_from_database()
        with pytest.raises(RuntimeError, match="could not be loaded"):
            config.sync_to_database()

    def test_failed_merge_after_load_blocks_saving(
        self,
        config: BMLibrarianConfig
    ) -> None:
        """A malformed database reply (not a mapping) must also block saving (#437)."""
        manager = MagicMock()
        manager.get_own_settings.return_value = ["not", "a", "mapping"]
        with patch('bmlibrarian.auth.user_settings.UserSettingsManager', return_value=manager):
            config.set_user_context(user_id=1, connection=MagicMock())

        assert config.settings_load_failed() is True
        with pytest.raises(RuntimeError, match="could not be loaded"):
            config.sync_to_database()
        manager.set.assert_not_called()

    def test_successful_load_merges_and_saves_database_values(
        self,
        config: BMLibrarianConfig
    ) -> None:
        """Database values replace local ones in memory and are what Save writes back."""
        manager = MagicMock()
        manager.get_own_settings.return_value = {'models': {'query_agent': 'from-db'}}
        with patch('bmlibrarian.auth.user_settings.UserSettingsManager', return_value=manager):
            config.set_user_context(user_id=1, connection=MagicMock())

        assert config.settings_load_failed() is False
        assert config.get('models.query_agent') == 'from-db'
        assert config.sync_to_database() is True
        saved_models = dict(c.args for c in manager.set.call_args_list)['models']
        assert saved_models['query_agent'] == 'from-db'

    def test_login_keeps_env_overrides_over_database_values(
        self,
        config: BMLibrarianConfig,
        monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BMLIB_* env vars still win after the user's rows are merged (#438)."""
        monkeypatch.setenv('BMLIB_OLLAMA_HOST', 'http://gpu:11434')
        manager = MagicMock()
        manager.get_own_settings.return_value = {
            'ollama': {'host': 'http://localhost:11434'},
            'models': {'query_agent': 'from-db'},
        }
        with patch('bmlibrarian.auth.user_settings.UserSettingsManager', return_value=manager):
            config.set_user_context(user_id=1, connection=MagicMock())

        assert config.get('ollama.host') == 'http://gpu:11434'
        assert config.get('models.query_agent') == 'from-db'
        manager.get_all.assert_not_called()  # get_all() includes the seeded defaults

    def test_login_merges_saved_category_missing_from_defaults(
        self,
        config: BMLibrarianConfig
    ) -> None:
        """A saved category absent from DEFAULT_CONFIG (e.g. gui) is not dropped."""
        assert 'gui' not in DEFAULT_CONFIG
        manager = MagicMock()
        manager.get_own_settings.return_value = {'gui': {'theme': 'dark'}}
        with patch('bmlibrarian.auth.user_settings.UserSettingsManager', return_value=manager):
            config.set_user_context(user_id=1, connection=MagicMock())

        assert config.get('gui.theme') == 'dark'

    def test_get_own_settings_reads_only_user_rows(self) -> None:
        """get_own_settings() queries user_settings, not the defaults-merging function."""
        from bmlibrarian.auth.user_settings import UserSettingsManager

        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            ('models', {'query_agent': 'mine'}),
            ('not_a_category', {'x': 1}),
            ('ollama', 'not a dict'),
        ]
        own = UserSettingsManager(conn, user_id=7).get_own_settings()

        assert own == {'models': {'query_agent': 'mine'}}
        sql, params = cursor.execute.call_args.args
        assert 'bmlsettings.user_settings' in sql and 'get_all_user_settings' not in sql
        assert params == (7,)

    def test_import_from_json_raises_when_a_category_fails_to_save(
        self,
        config: BMLibrarianConfig,
        tmp_path: Path
    ) -> None:
        """import_from_json reports a partial database save instead of ignoring it."""
        manager = MagicMock()
        manager.get_own_settings.return_value = {}
        with patch('bmlibrarian.auth.user_settings.UserSettingsManager', return_value=manager):
            config.set_user_context(user_id=1, connection=MagicMock())
        source = tmp_path / "import.json"
        source.write_text(json.dumps({'models': {'query_agent': 'imported'}}))

        with patch.object(config, 'sync_to_database', return_value=False):
            with pytest.raises(RuntimeError, match="failed to save"):
                config.import_from_json(source)

    def test_refusal_names_the_sync_from_database_button(
        self,
        config: BMLibrarianConfig
    ) -> None:
        """The refusal tells the user which control lifts it."""
        manager = MagicMock()
        manager.get_own_settings.side_effect = RuntimeError("connection lost")
        with patch('bmlibrarian.auth.user_settings.UserSettingsManager', return_value=manager):
            config.set_user_context(user_id=1, connection=MagicMock())

        with pytest.raises(RuntimeError, match="Sync from Database"):
            config.sync_to_database()

    def test_export_to_json(self, config: BMLibrarianConfig) -> None:
        """Test export_to_json creates valid JSON file."""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ) as f:
            temp_path = Path(f.name)

        try:
            config.export_to_json(temp_path)

            # Verify file was created with valid JSON
            assert temp_path.exists()
            with open(temp_path, 'r') as f:
                exported = json.load(f)

            # Check some expected keys
            assert "models" in exported
            assert "ollama" in exported
            assert "agents" in exported
        finally:
            temp_path.unlink(missing_ok=True)

    def test_import_from_json(self, config: BMLibrarianConfig) -> None:
        """Test import_from_json loads settings correctly."""
        # Create a test config file
        test_config = {
            "models": {
                "query_agent": "test-model:latest"
            }
        }

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ) as f:
            json.dump(test_config, f)
            temp_path = Path(f.name)

        try:
            config.import_from_json(temp_path, sync_to_db=False)

            # Verify the setting was imported
            assert config.get("models.query_agent") == "test-model:latest"
        finally:
            temp_path.unlink(missing_ok=True)


class TestBMLibrarianConfigResetToDefaults:
    """Tests for BMLibrarianConfig reset_to_defaults method."""

    @pytest.fixture
    def config(self) -> BMLibrarianConfig:
        """Create a fresh config instance for each test."""
        return BMLibrarianConfig()

    def test_reset_specific_categories(self, config: BMLibrarianConfig) -> None:
        """Test resetting specific categories to defaults."""
        # Modify a setting
        original_model = config.get("models.query_agent")
        config.set("models.query_agent", "modified-model")
        assert config.get("models.query_agent") == "modified-model"

        # Reset models category
        config.reset_to_defaults(categories=["models"])

        # Should be back to default
        assert config.get("models.query_agent") == original_model

    def test_reset_all_categories(self, config: BMLibrarianConfig) -> None:
        """Test resetting all categories to defaults."""
        # Modify settings in multiple categories
        config.set("models.query_agent", "modified-model")
        config.set("ollama.host", "http://modified:11434")

        # Reset all
        config.reset_to_defaults()

        # Should be back to defaults
        assert config.get("models.query_agent") == DEFAULT_CONFIG["models"]["query_agent"]
        assert config.get("ollama.host") == DEFAULT_CONFIG["ollama"]["host"]


class TestDeepCopyConfig:
    """Tests for _deep_copy_config static method."""

    def test_deep_copy_creates_independent_copy(self) -> None:
        """Test that deep copy creates an independent copy."""
        original = {"a": {"b": [1, 2, 3]}}
        copy = BMLibrarianConfig._deep_copy_config(original)

        # Modify the copy
        copy["a"]["b"].append(4)

        # Original should be unchanged
        assert original["a"]["b"] == [1, 2, 3]
        assert copy["a"]["b"] == [1, 2, 3, 4]

    def test_deep_copy_handles_nested_dicts(self) -> None:
        """Test deep copy works with deeply nested structures."""
        original = {
            "level1": {
                "level2": {
                    "level3": {
                        "value": "original"
                    }
                }
            }
        }

        copy = BMLibrarianConfig._deep_copy_config(original)
        copy["level1"]["level2"]["level3"]["value"] = "modified"

        assert original["level1"]["level2"]["level3"]["value"] == "original"


class TestGlobalConfigInstance:
    """Tests for global config instance management."""

    def test_get_config_returns_singleton(self) -> None:
        """Test that get_config returns the same instance."""
        # Need to reload to ensure clean state
        reload_config()
        config1 = get_config()
        config2 = get_config()

        assert config1 is config2

    def test_reload_config_creates_new_instance(self) -> None:
        """Test that reload_config creates a new instance."""
        config1 = get_config()
        reload_config()
        config2 = get_config()

        # Should be different objects
        assert config1 is not config2
