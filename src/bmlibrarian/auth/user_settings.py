"""User settings manager for BMLibrarian.

This module provides per-user settings storage and retrieval using the
bmlsettings PostgreSQL schema.
"""

import json
import logging
from typing import Any, Dict, Optional

from psycopg import Connection
from psycopg.rows import dict_row


# Valid settings categories
VALID_CATEGORIES = frozenset([
    'models', 'ollama', 'agents', 'database', 'search',
    'query_generation', 'gui', 'openathens', 'pdf', 'general'
])


class UserSettingsManager:
    """Manager for per-user settings stored in PostgreSQL.

    This class provides a simple interface for loading and saving user-specific
    settings, with automatic fallback to system defaults when user settings
    are not defined.

    Example:
        from bmlibrarian.database import get_db_manager
        from bmlibrarian.auth import UserSettingsManager

        db_manager = get_db_manager()
        with db_manager.get_connection() as conn:
            settings_manager = UserSettingsManager(conn, user_id=1)

            # Get settings for a category
            models = settings_manager.get('models')

            # Get a specific value with default
            host = settings_manager.get_value('ollama', 'host', 'http://localhost:11434')

            # Save settings
            settings_manager.set('models', {'query_agent': 'gpt-oss:20b'})

            # Get all settings as a single dict
            all_settings = settings_manager.get_all()
    """

    def __init__(self, connection: Connection, user_id: int):
        """Initialize the settings manager.

        Args:
            connection: A psycopg database connection.
            user_id: The user's ID for loading/saving settings.
        """
        self._conn = connection
        self._user_id = user_id
        self._logger = logging.getLogger("bmlibrarian.auth.UserSettingsManager")
        self._cache: Dict[str, Dict[str, Any]] = {}

    @property
    def user_id(self) -> int:
        """Get the current user ID."""
        return self._user_id

    def get(self, category: str, use_cache: bool = True) -> Dict[str, Any]:
        """Get settings for a category.

        Settings are loaded from user's custom settings first, falling back
        to system defaults if not found.

        Args:
            category: The settings category (e.g., 'models', 'ollama').
            use_cache: Whether to use cached settings.

        Returns:
            Dictionary of settings for the category.

        Raises:
            ValueError: If category is not valid.
        """
        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. "
                f"Valid categories: {', '.join(sorted(VALID_CATEGORIES))}"
            )

        # Check cache
        if use_cache and category in self._cache:
            return self._cache[category].copy()

        # Load from database
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT bmlsettings.get_user_settings(%s, %s)",
                (self._user_id, category)
            )
            result = cur.fetchone()
            settings = result[0] if result else {}

        # Cache and return
        self._cache[category] = settings or {}
        return self._cache[category].copy()

    def get_value(
        self,
        category: str,
        key: str,
        default: Any = None,
        use_cache: bool = True
    ) -> Any:
        """Get a specific value from a settings category.

        Args:
            category: The settings category.
            key: The key within the category (supports dot notation for nested keys).
            default: Default value if key is not found.
            use_cache: Whether to use cached settings.

        Returns:
            The value for the key, or default if not found.
        """
        settings = self.get(category, use_cache=use_cache)

        # Support dot notation for nested keys
        keys = key.split('.')
        value = settings
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, category: str, settings: Dict[str, Any]) -> bool:
        """Set settings for a category.

        This replaces all settings for the category with the provided dict.

        Args:
            category: The settings category.
            settings: Dictionary of settings to save.

        Returns:
            True if settings were saved successfully.

        Raises:
            ValueError: If category is not valid.
        """
        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. "
                f"Valid categories: {', '.join(sorted(VALID_CATEGORIES))}"
            )

        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT bmlsettings.save_user_settings(%s, %s, %s)",
                (self._user_id, category, json.dumps(settings))
            )

        self._conn.commit()

        # Update cache
        self._cache[category] = settings.copy()
        self._logger.debug(f"Saved settings for category '{category}'")
        return True

    def set_value(self, category: str, key: str, value: Any) -> bool:
        """Set a specific value within a settings category.

        Args:
            category: The settings category.
            key: The key to set (supports dot notation for nested keys).
            value: The value to set.

        Returns:
            True if the value was saved successfully.
        """
        settings = self.get(category, use_cache=True)

        # Support dot notation for nested keys
        keys = key.split('.')
        current = settings
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value

        return self.set(category, settings)

    def get_all(self, use_cache: bool = True) -> Dict[str, Dict[str, Any]]:
        """Get all settings for the user as a single dictionary.

        Args:
            use_cache: Whether to use cached settings.

        Returns:
            Dictionary with category names as keys and settings dicts as values.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT bmlsettings.get_all_user_settings(%s)",
                (self._user_id,)
            )
            result = cur.fetchone()
            all_settings = result[0] if result else {}

        # Update cache
        for category, settings in all_settings.items():
            self._cache[category] = settings

        return all_settings.copy()

    def reset_category(self, category: str) -> bool:
        """Reset a category to system defaults by deleting user settings.

        Args:
            category: The settings category to reset.

        Returns:
            True if settings were reset successfully.

        Raises:
            ValueError: If category is not valid.
        """
        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. "
                f"Valid categories: {', '.join(sorted(VALID_CATEGORIES))}"
            )

        with self._conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM bmlsettings.user_settings
                WHERE user_id = %s AND category = %s
                """,
                (self._user_id, category)
            )

        self._conn.commit()

        # Clear cache for this category
        self._cache.pop(category, None)
        self._logger.debug(f"Reset settings for category '{category}' to defaults")
        return True

    def reset_all(self) -> bool:
        """Reset all settings to system defaults.

        Returns:
            True if all settings were reset successfully.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bmlsettings.user_settings WHERE user_id = %s",
                (self._user_id,)
            )

        self._conn.commit()

        # Clear cache
        self._cache.clear()
        self._logger.debug("Reset all settings to defaults")
        return True

    def clear_cache(self) -> None:
        """Clear the settings cache."""
        self._cache.clear()

    def has_custom_settings(self, category: str) -> bool:
        """Check if the user has custom settings for a category.

        Args:
            category: The settings category to check.

        Returns:
            True if user has custom settings for this category.
        """
        if category not in VALID_CATEGORIES:
            return False

        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM bmlsettings.user_settings
                WHERE user_id = %s AND category = %s
                """,
                (self._user_id, category)
            )
            return cur.fetchone() is not None

    def get_defaults(self, category: str) -> Dict[str, Any]:
        """Get system default settings for a category.

        Args:
            category: The settings category.

        Returns:
            Dictionary of default settings.

        Raises:
            ValueError: If category is not valid.
        """
        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. "
                f"Valid categories: {', '.join(sorted(VALID_CATEGORIES))}"
            )

        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT settings FROM bmlsettings.default_settings
                WHERE category = %s
                """,
                (category,)
            )
            result = cur.fetchone()
            return result[0] if result else {}
