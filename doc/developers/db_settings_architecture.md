# Database-Backed Settings Architecture

**Module**: `bmlibrarian.config` + `bmlibrarian.auth`
**Status**: Implementation Phase 1
**Last Updated**: 2025-11-22

## Overview

This document describes the technical architecture for BMLibrarian's database-backed user settings system. The system enables per-user configuration storage in PostgreSQL while maintaining backward compatibility with JSON file-based configuration.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Application Layer                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │  Qt GUI      │  │  Flet GUI    │  │  CLI Apps    │  │  Agent Factory   │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘ │
└─────────┼─────────────────┼─────────────────┼───────────────────┼───────────┘
          │                 │                 │                   │
          ▼                 ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Configuration API Layer                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      BMLibrarianConfig (Singleton)                   │    │
│  │  ┌────────────────────┐  ┌────────────────────────────────────────┐ │    │
│  │  │ Public Interface   │  │ Internal State                         │ │    │
│  │  │ - get_model()      │  │ - _config: Dict                        │ │    │
│  │  │ - get_agent_config │  │ - _user_context: Optional[UserContext] │ │    │
│  │  │ - get()            │  │ - _settings_manager: Optional[USM]     │ │    │
│  │  │ - set()            │  │ - _config_loaded: bool                 │ │    │
│  │  │ - save_config()    │  └────────────────────────────────────────┘ │    │
│  │  │ - set_user_context │                                             │    │
│  │  └────────────────────┘                                             │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          │                           │                           │
          ▼                           ▼                           ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  User Settings   │      │ Default Settings │      │   JSON Files     │
│  (PostgreSQL)    │      │  (PostgreSQL)    │      │ (~/.bmlibrarian) │
│                  │      │                  │      │                  │
│ bmlsettings.     │      │ bmlsettings.     │      │ config.json      │
│ user_settings    │      │ default_settings │      │                  │
└──────────────────┘      └──────────────────┘      └──────────────────┘
```

## Core Components

### 1. BMLibrarianConfig (Extended)

The `BMLibrarianConfig` class is extended to support user context while maintaining full backward compatibility.

**Location**: `src/bmlibrarian/config.py`

```python
@dataclass
class UserContext:
    """Holds user session information for config resolution."""
    user_id: int
    connection: Connection
    session_token: Optional[str] = None


class BMLibrarianConfig:
    """Configuration manager with user context support."""

    def __init__(self):
        self._config = DEFAULT_CONFIG.copy()
        self._config_loaded = False
        self._user_context: Optional[UserContext] = None
        self._settings_manager: Optional[UserSettingsManager] = None
        self._load_config()

    # === User Context Management ===

    def set_user_context(
        self,
        user_id: int,
        connection: Connection,
        session_token: Optional[str] = None
    ) -> None:
        """Set user context for database-backed settings.

        When user context is set, all get() operations will first check
        the user's database settings before falling back to defaults.

        Args:
            user_id: The authenticated user's ID
            connection: Active database connection
            session_token: Optional session token for validation
        """
        self._user_context = UserContext(
            user_id=user_id,
            connection=connection,
            session_token=session_token
        )
        self._settings_manager = UserSettingsManager(connection, user_id)
        # Refresh config from database
        self._sync_from_database()

    def clear_user_context(self) -> None:
        """Clear user context, reverting to JSON/default config."""
        self._user_context = None
        self._settings_manager = None
        # Reload from JSON
        self._config = DEFAULT_CONFIG.copy()
        self._config_loaded = False
        self._load_config()

    def has_user_context(self) -> bool:
        """Check if user context is currently set."""
        return self._user_context is not None

    def get_user_id(self) -> Optional[int]:
        """Get current user ID if context is set."""
        return self._user_context.user_id if self._user_context else None
```

### 2. Configuration Resolution

The configuration resolution follows a priority chain:

```python
def _get_category_config(self, category: str) -> Dict[str, Any]:
    """Get configuration for a category with fallback chain.

    Resolution order:
    1. User settings (if user context set)
    2. Database defaults (if DB connected)
    3. JSON file settings
    4. Hardcoded DEFAULT_CONFIG
    """
    # Try user settings first
    if self._settings_manager is not None:
        try:
            user_settings = self._settings_manager.get(category)
            if user_settings:
                return self._merge_with_defaults(category, user_settings)
        except Exception as e:
            logger.warning(f"Failed to load user settings for {category}: {e}")

    # Fall back to in-memory config (from JSON or defaults)
    return self._config.get(category, DEFAULT_CONFIG.get(category, {}))

def _merge_with_defaults(
    self,
    category: str,
    user_settings: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge user settings with defaults for complete config."""
    defaults = DEFAULT_CONFIG.get(category, {})
    result = defaults.copy()
    self._deep_merge(result, user_settings)
    return result
```

### 3. Settings Sync Operations

```python
def sync_to_database(self) -> None:
    """Push current in-memory config to user's database settings.

    Requires user context to be set. Each category is saved separately
    to the bmlsettings.user_settings table.

    Raises:
        RuntimeError: If no user context is set
    """
    if self._settings_manager is None:
        raise RuntimeError("Cannot sync to database: no user context set")

    for category in VALID_CATEGORIES:
        if category in self._config:
            self._settings_manager.set(category, self._config[category])

def sync_from_database(self) -> None:
    """Pull user's database settings into memory.

    Requires user context to be set. Overwrites in-memory config
    with database values.
    """
    if self._settings_manager is None:
        raise RuntimeError("Cannot sync from database: no user context set")

    db_settings = self._settings_manager.get_all()
    for category, settings in db_settings.items():
        if category in self._config:
            self._config[category] = settings

def export_to_json(self, file_path: Path) -> None:
    """Export current configuration to JSON file.

    Exports the effective configuration (merged user + defaults).
    Useful for backup or sharing settings.
    """
    config_to_export = {}
    for category in VALID_CATEGORIES:
        config_to_export[category] = self._get_category_config(category)

    with open(file_path, 'w') as f:
        json.dump(config_to_export, f, indent=2)

def import_from_json(self, file_path: Path) -> None:
    """Import configuration from JSON file.

    If user context is set, imports to database.
    Otherwise, saves to default JSON location.
    """
    with open(file_path, 'r') as f:
        imported_config = json.load(f)

    if self._settings_manager is not None:
        # Import to database
        for category, settings in imported_config.items():
            if category in VALID_CATEGORIES:
                self._settings_manager.set(category, settings)
        self.sync_from_database()
    else:
        # Import to memory and JSON
        self._merge_config(imported_config)
        self.save_config()
```

### 4. UserSettingsManager

**Location**: `src/bmlibrarian/auth/user_settings.py`

The `UserSettingsManager` provides the database interface for user-specific settings.

```python
VALID_CATEGORIES = frozenset([
    'models', 'ollama', 'agents', 'database', 'search',
    'query_generation', 'gui', 'openathens', 'pdf', 'general'
])

class UserSettingsManager:
    """Database-backed per-user settings manager."""

    def __init__(self, connection: Connection, user_id: int):
        self._conn = connection
        self._user_id = user_id
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, category: str, use_cache: bool = True) -> Dict[str, Any]:
        """Get settings with automatic fallback to defaults."""
        # Uses bmlsettings.get_user_settings() which handles fallback

    def set(self, category: str, settings: Dict[str, Any]) -> bool:
        """Save settings for category (upsert)."""
        # Uses bmlsettings.save_user_settings()

    def get_all(self, use_cache: bool = True) -> Dict[str, Dict[str, Any]]:
        """Get all settings as single dict."""
        # Uses bmlsettings.get_all_user_settings()

    def reset_category(self, category: str) -> bool:
        """Delete user settings, revert to defaults."""

    def reset_all(self) -> bool:
        """Reset all settings to defaults."""
```

## Database Schema

### Tables

```sql
-- User-specific settings
CREATE TABLE bmlsettings.user_settings (
    setting_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (category IN (
        'models', 'ollama', 'agents', 'database', 'search',
        'query_generation', 'gui', 'openathens', 'pdf', 'general'
    )),
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, category)
);

-- System-wide defaults
CREATE TABLE bmlsettings.default_settings (
    default_id SERIAL PRIMARY KEY,
    category TEXT UNIQUE NOT NULL CHECK (category IN (...)),
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Session management
CREATE TABLE bmlsettings.user_sessions (
    session_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    session_token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_active TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    client_type TEXT CHECK (client_type IN ('qt_gui', 'flet_gui', 'cli', 'api')),
    client_version TEXT,
    hostname TEXT
);
```

### Functions

```sql
-- Get user settings with fallback to defaults
CREATE FUNCTION bmlsettings.get_user_settings(
    p_user_id INTEGER,
    p_category TEXT
) RETURNS JSONB AS $$
    SELECT COALESCE(
        (SELECT settings FROM bmlsettings.user_settings
         WHERE user_id = p_user_id AND category = p_category),
        (SELECT settings FROM bmlsettings.default_settings
         WHERE category = p_category),
        '{}'::JSONB
    );
$$ LANGUAGE SQL STABLE;

-- Save user settings (upsert)
CREATE FUNCTION bmlsettings.save_user_settings(
    p_user_id INTEGER,
    p_category TEXT,
    p_settings JSONB
) RETURNS BOOLEAN AS $$
    INSERT INTO bmlsettings.user_settings (user_id, category, settings)
    VALUES (p_user_id, p_category, p_settings)
    ON CONFLICT (user_id, category)
    DO UPDATE SET settings = p_settings, updated_at = CURRENT_TIMESTAMP;
    SELECT TRUE;
$$ LANGUAGE SQL;

-- Get all user settings as single JSONB object
CREATE FUNCTION bmlsettings.get_all_user_settings(
    p_user_id INTEGER
) RETURNS JSONB AS $$
    SELECT jsonb_object_agg(
        category,
        bmlsettings.get_user_settings(p_user_id, category)
    )
    FROM unnest(ARRAY[
        'models', 'ollama', 'agents', 'database', 'search',
        'query_generation', 'gui', 'openathens', 'pdf', 'general'
    ]) AS category;
$$ LANGUAGE SQL STABLE;
```

## Integration Points

### CLI Integration

```python
# src/bmlibrarian/cli/auth_helper.py

def authenticate_cli(
    username: Optional[str] = None,
    password: Optional[str] = None,
    session_token: Optional[str] = None
) -> Optional[Tuple[int, str]]:
    """Authenticate user for CLI session.

    Args:
        username: Username for login
        password: Password for login
        session_token: Existing session token to validate

    Returns:
        Tuple of (user_id, session_token) if authenticated, None otherwise
    """
    from bmlibrarian.database import get_db_manager
    from bmlibrarian.auth import UserService

    db = get_db_manager()
    with db.get_connection() as conn:
        service = UserService(conn)

        if session_token:
            # Validate existing session
            user = service.validate_session(session_token)
            if user:
                return (user.id, session_token)

        if username and password:
            # New login
            session = service.authenticate(
                username, password, client_type='cli'
            )
            return (session.user_id, session.session_token)

    return None


def setup_config_with_auth(
    args: argparse.Namespace
) -> BMLibrarianConfig:
    """Setup configuration with optional authentication.

    Checks for --user/--password or --session-token args.
    If present, authenticates and sets user context.
    """
    config = get_config()

    auth_result = authenticate_cli(
        username=getattr(args, 'user', None),
        password=getattr(args, 'password', None),
        session_token=getattr(args, 'session_token', None)
    )

    if auth_result:
        user_id, token = auth_result
        db = get_db_manager()
        conn = db.get_connection()
        config.set_user_context(user_id, conn, token)

    return config
```

### GUI Integration

```python
# In Qt application after login

def on_login_successful(self, login_result: LoginResult):
    """Handle successful login by setting user context."""
    from bmlibrarian.config import get_config

    config = get_config()
    config.set_user_context(
        user_id=login_result.user_id,
        connection=self.db_connection,
        session_token=login_result.session_token
    )

    # Config now returns user-specific settings
    self.load_configuration_tabs()
```

## Caching Strategy

The `UserSettingsManager` implements a simple in-memory cache:

```python
class UserSettingsManager:
    def __init__(self, connection: Connection, user_id: int):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, category: str, use_cache: bool = True) -> Dict[str, Any]:
        if use_cache and category in self._cache:
            return self._cache[category].copy()

        # Load from database
        settings = self._load_from_db(category)
        self._cache[category] = settings
        return settings.copy()

    def set(self, category: str, settings: Dict[str, Any]) -> bool:
        self._save_to_db(category, settings)
        self._cache[category] = settings.copy()
        return True

    def clear_cache(self) -> None:
        self._cache.clear()
```

**Cache invalidation** occurs when:
- `set()` is called (updates cache with new value)
- `clear_cache()` is called explicitly
- User context is changed

## Error Handling

```python
def get(self, key_path: str, default=None) -> Any:
    """Get config value with graceful error handling."""
    try:
        if self._settings_manager:
            category, *rest = key_path.split('.', 1)
            if category in VALID_CATEGORIES:
                settings = self._settings_manager.get(category)
                if rest:
                    return self._navigate_path(settings, rest[0], default)
                return settings
    except Exception as e:
        logger.warning(f"Database config lookup failed: {e}")
        # Fall through to JSON/default

    # Fallback to in-memory config
    return self._get_from_memory(key_path, default)
```

## Migration Considerations

### JSON to Database Migration

```python
def migrate_json_to_database(
    json_path: Path,
    user_id: int,
    connection: Connection
) -> Dict[str, int]:
    """Migrate JSON config to database settings.

    Args:
        json_path: Path to JSON config file
        user_id: User ID to migrate settings for
        connection: Database connection

    Returns:
        Dict with counts: {'migrated': N, 'skipped': M, 'errors': K}
    """
    manager = UserSettingsManager(connection, user_id)

    with open(json_path, 'r') as f:
        json_config = json.load(f)

    stats = {'migrated': 0, 'skipped': 0, 'errors': 0}

    for category in VALID_CATEGORIES:
        if category in json_config:
            try:
                # Only migrate if user doesn't have custom settings
                if not manager.has_custom_settings(category):
                    manager.set(category, json_config[category])
                    stats['migrated'] += 1
                else:
                    stats['skipped'] += 1
            except Exception as e:
                logger.error(f"Failed to migrate {category}: {e}")
                stats['errors'] += 1

    return stats
```

## Security Considerations

1. **Session Validation**: User context includes session token for validation
2. **Connection Reuse**: Connection passed to settings manager, not stored globally
3. **No Credential Storage**: Passwords never stored in config
4. **Audit Trail**: `created_at`/`updated_at` timestamps on all settings

## Performance Notes

1. **Lazy Loading**: Settings only loaded when accessed
2. **Caching**: Category-level caching reduces database queries
3. **Batch Operations**: `get_all()` uses single query for all categories
4. **Connection Pooling**: Uses application's database connection pool

## Testing Guidelines

```python
# Fixtures for testing

@pytest.fixture
def mock_user_context():
    """Create mock user context for testing."""
    return UserContext(
        user_id=1,
        connection=mock_connection,
        session_token="test-token"
    )

@pytest.fixture
def config_with_user():
    """Config instance with user context set."""
    config = BMLibrarianConfig()
    config.set_user_context(1, mock_connection)
    return config

# Test cases

def test_get_falls_back_to_json_without_context(config):
    """Without user context, config uses JSON file."""
    assert config.has_user_context() is False
    # Should load from JSON/defaults

def test_get_uses_database_with_context(config_with_user):
    """With user context, config queries database."""
    assert config_with_user.has_user_context() is True
    # Mock database to verify query
```

---

## Appendix: Category to Config Key Mapping

| Category | JSON Keys | Notes |
|----------|-----------|-------|
| `models` | `models.*` | Model names for each agent |
| `ollama` | `ollama.*` | Ollama server settings |
| `agents` | `agents.*` | Per-agent parameters |
| `database` | `database.*` | Database query settings |
| `search` | `search.*`, `search_strategy.*` | Search configuration |
| `query_generation` | `query_generation.*` | Multi-model settings |
| `gui` | N/A (new) | GUI-specific settings |
| `openathens` | `openathens.*` | Proxy authentication |
| `pdf` | N/A (new) | PDF processing settings |
| `general` | N/A (new) | General app settings |

---

**Document History**:
- 2025-11-22: Initial architecture document
