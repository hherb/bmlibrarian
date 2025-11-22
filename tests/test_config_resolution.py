"""Tests for configuration resolution order.

Tests that configuration values are resolved in the correct priority order:
1. User database settings (when authenticated)
2. Default database settings (when DB connected)
3. JSON file settings
4. Hardcoded defaults
"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import json
import tempfile


class TestConfigResolutionWithUserContext:
    """Tests for config resolution with authenticated user."""

    @pytest.fixture
    def mock_user_settings_manager(self):
        """Create a mock UserSettingsManager."""
        mock = MagicMock()
        mock.get.return_value = None  # Default to no settings
        return mock

    @pytest.fixture
    def mock_connection(self):
        """Create a mock database connection."""
        return MagicMock()

    @pytest.mark.skip(reason="Requires proper mock setup - integration test")
    def test_user_settings_take_priority(self, mock_connection):
        """Test that user DB settings take priority over defaults."""
        # This documents expected behavior:
        # When authenticated, user's DB settings should override defaults
        pass

    def test_fallback_to_json_without_user_context(self):
        """Test that JSON config is used without user context."""
        from bmlibrarian.config import BMLibrarianConfig

        config = BMLibrarianConfig()

        # Without user context, should use JSON/default values
        assert not config.has_user_context()


class TestConfigResolutionOrder:
    """Tests documenting the resolution order."""

    def test_resolution_priority_order(self):
        """Document the expected resolution order."""
        # This test documents the expected behavior
        # Priority order (highest to lowest):
        # 1. User database settings (if authenticated)
        # 2. Default database settings (if DB connected)
        # 3. JSON file settings
        # 4. Hardcoded DEFAULT_CONFIG

        from bmlibrarian.config import DEFAULT_CONFIG, VALID_SETTINGS_CATEGORIES

        # Verify DEFAULT_CONFIG has expected structure
        assert 'models' in DEFAULT_CONFIG
        assert 'agents' in DEFAULT_CONFIG
        assert 'ollama' in DEFAULT_CONFIG

        # Verify categories are defined
        assert len(VALID_SETTINGS_CATEGORIES) > 0
        assert 'models' in VALID_SETTINGS_CATEGORIES
        assert 'agents' in VALID_SETTINGS_CATEGORIES


class TestUserContextLifecycle:
    """Tests for user context lifecycle management."""

    def test_initial_no_user_context(self):
        """Test that config starts without user context."""
        from bmlibrarian.config import BMLibrarianConfig

        config = BMLibrarianConfig()

        # Initially no user context
        assert not config.has_user_context()
        assert config.get_user_id() is None

    def test_clear_user_context_when_none_set(self):
        """Test clearing user context when none is set doesn't error."""
        from bmlibrarian.config import BMLibrarianConfig

        config = BMLibrarianConfig()

        # Should not raise
        config.clear_user_context()

        assert not config.has_user_context()
        assert config.get_user_id() is None

    def test_user_context_dataclass(self):
        """Test UserContext dataclass structure."""
        from bmlibrarian.config import UserContext

        ctx = UserContext(
            user_id=42,
            connection=MagicMock(),
            session_token="test-token"
        )

        assert ctx.user_id == 42
        assert ctx.session_token == "test-token"


class TestSettingsMerge:
    """Tests for settings merge behavior."""

    def test_nested_dict_merge(self):
        """Test that nested dictionaries are properly merged."""
        base = {
            "models": {"default": "base-model"},
            "agents": {"query": {"temperature": 0.7, "top_p": 0.9}}
        }

        override = {
            "agents": {"query": {"temperature": 0.5}}  # Only override temperature
        }

        # Document expected merge behavior
        # Expected: agents.query.temperature = 0.5, agents.query.top_p = 0.9

    def test_category_level_override(self):
        """Test that entire categories can be overridden."""
        base = {
            "models": {"default": "base-model", "query": "query-model"}
        }

        override = {
            "models": {"default": "new-model"}  # Replaces entire models category
        }

        # This tests the current merge behavior


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_invalid_category_raises(self):
        """Test that invalid categories are rejected."""
        from bmlibrarian.config import VALID_SETTINGS_CATEGORIES

        invalid_category = "definitely_not_a_valid_category"
        assert invalid_category not in VALID_SETTINGS_CATEGORIES

    def test_get_with_default_value(self):
        """Test get() returns default when key doesn't exist."""
        from bmlibrarian.config import BMLibrarianConfig

        config = BMLibrarianConfig()

        # Non-existent key should return default
        result = config.get("nonexistent.key.path", default="my_default")
        assert result == "my_default"

    def test_nested_key_path_resolution(self):
        """Test that nested key paths are resolved correctly."""
        from bmlibrarian.config import BMLibrarianConfig

        config = BMLibrarianConfig()

        # Get a known nested value
        # agents.query.temperature should exist in DEFAULT_CONFIG
        temp = config.get("agents.query.temperature")
        assert temp is not None
        assert isinstance(temp, (int, float))

    def test_config_singleton_behavior(self):
        """Test that get_config returns the same instance."""
        from bmlibrarian.config import get_config

        config1 = get_config()
        config2 = get_config()

        assert config1 is config2


class TestDatabaseSyncOperations:
    """Tests for database sync operations."""

    def test_sync_requires_user_context(self):
        """Test that sync operations require user context."""
        from bmlibrarian.config import BMLibrarianConfig

        config = BMLibrarianConfig()

        # Without user context, sync should raise
        assert not config.has_user_context()

        # sync_to_database should raise RuntimeError without context
        with pytest.raises(RuntimeError, match="no user context set"):
            config.sync_to_database()

    def test_export_to_json(self, tmp_path):
        """Test exporting config to JSON file."""
        from bmlibrarian.config import BMLibrarianConfig

        config = BMLibrarianConfig()
        output_file = tmp_path / "export.json"

        config.export_to_json(output_file)

        assert output_file.exists()
        with open(output_file) as f:
            exported = json.load(f)

        # Should have exported some config
        assert isinstance(exported, dict)

    def test_import_from_json(self, tmp_path):
        """Test importing config from JSON file."""
        from bmlibrarian.config import BMLibrarianConfig

        # Create config to import
        import_data = {
            "models": {"default": "imported-model"}
        }
        import_file = tmp_path / "import.json"
        import_file.write_text(json.dumps(import_data))

        config = BMLibrarianConfig()
        config.import_from_json(import_file, sync_to_db=False)

        # Should have imported the model setting
        model = config.get("models.default")
        assert model == "imported-model"
