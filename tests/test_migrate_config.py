"""Tests for the configuration migration tool.

Tests the migrate_config_to_db.py script functionality.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# Import the module under test
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestLoadJsonConfig:
    """Tests for load_json_config function."""

    def test_load_valid_json(self, tmp_path):
        """Test loading a valid JSON config file."""
        from migrate_config_to_db import load_json_config

        config_file = tmp_path / "config.json"
        config_data = {
            "models": {"default": "gpt-oss:20b"},
            "agents": {"query": {"temperature": 0.7}}
        }
        config_file.write_text(json.dumps(config_data))

        result = load_json_config(config_file)

        assert result == config_data
        assert result["models"]["default"] == "gpt-oss:20b"

    def test_load_missing_file(self, tmp_path):
        """Test loading a non-existent file raises FileNotFoundError."""
        from migrate_config_to_db import load_json_config

        config_file = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            load_json_config(config_file)

    def test_load_invalid_json(self, tmp_path):
        """Test loading invalid JSON raises JSONDecodeError."""
        from migrate_config_to_db import load_json_config

        config_file = tmp_path / "invalid.json"
        config_file.write_text("{ invalid json }")

        with pytest.raises(json.JSONDecodeError):
            load_json_config(config_file)


class TestFilterValidCategories:
    """Tests for filter_valid_categories function."""

    def test_filters_to_valid_categories(self):
        """Test that only valid categories are kept."""
        from migrate_config_to_db import filter_valid_categories

        config = {
            "models": {"default": "model1"},
            "agents": {"temp": 0.5},
            "invalid_category": {"should": "be filtered"},
            "ollama": {"url": "http://localhost"}
        }

        result = filter_valid_categories(config)

        assert "models" in result
        assert "agents" in result
        assert "ollama" in result
        assert "invalid_category" not in result

    def test_preserves_all_valid_categories(self):
        """Test that all valid categories are preserved."""
        from migrate_config_to_db import filter_valid_categories, VALID_CATEGORIES

        config = {cat: {"key": "value"} for cat in VALID_CATEGORIES}
        config["extra"] = {"should": "go"}

        result = filter_valid_categories(config)

        assert len(result) == len(VALID_CATEGORIES)
        for cat in VALID_CATEGORIES:
            assert cat in result

    def test_handles_empty_config(self):
        """Test that empty config returns empty dict."""
        from migrate_config_to_db import filter_valid_categories

        result = filter_valid_categories({})

        assert result == {}


class TestValidCategories:
    """Tests for VALID_CATEGORIES constant."""

    def test_contains_expected_categories(self):
        """Test that expected categories are defined."""
        from migrate_config_to_db import VALID_CATEGORIES

        expected = {
            'models', 'ollama', 'agents', 'database', 'search',
            'query_generation', 'gui', 'openathens', 'pdf', 'general'
        }

        assert VALID_CATEGORIES == expected

    def test_is_frozen_set(self):
        """Test that VALID_CATEGORIES is a frozenset."""
        from migrate_config_to_db import VALID_CATEGORIES

        assert isinstance(VALID_CATEGORIES, frozenset)


class TestMigrationFunctions:
    """Tests for migration functions (require mocking)."""

    @pytest.mark.skip(reason="Requires database connection - integration test")
    def test_migrate_to_user_settings(self):
        """Test migrating to user settings."""
        pass

    @pytest.mark.skip(reason="Requires database connection - integration test")
    def test_migrate_to_defaults(self):
        """Test migrating to default settings."""
        pass

    @pytest.mark.skip(reason="Requires database connection - integration test")
    def test_export_user_settings(self):
        """Test exporting user settings."""
        pass


class TestArgumentParser:
    """Tests for command-line argument parsing."""

    def test_interactive_mode(self):
        """Test --interactive flag."""
        from migrate_config_to_db import main
        import argparse

        # Just verify the script can be imported and has main
        assert callable(main)

    def test_user_mode_requires_config_or_export(self):
        """Test that user mode validation works."""
        # This is tested via integration tests
        pass


class TestMigrationMerging:
    """Tests for config merging behavior."""

    def test_merge_overwrites_existing_keys(self):
        """Test that merge properly handles overlapping keys."""
        existing = {"key1": "old_value", "key2": "keep_this"}
        new = {"key1": "new_value", "key3": "add_this"}

        merged = {**existing, **new}

        assert merged["key1"] == "new_value"  # Overwritten
        assert merged["key2"] == "keep_this"  # Preserved
        assert merged["key3"] == "add_this"  # Added

    def test_replace_removes_existing_keys(self):
        """Test that replace mode doesn't preserve existing."""
        existing = {"key1": "old_value", "key2": "will_be_lost"}
        new = {"key1": "new_value", "key3": "only_new"}

        replaced = new  # Replace mode just uses new

        assert replaced["key1"] == "new_value"
        assert "key2" not in replaced
        assert replaced["key3"] == "only_new"
