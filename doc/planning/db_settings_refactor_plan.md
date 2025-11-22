# Database-Backed Settings Refactoring Plan

**Date**: 2025-11-22
**Status**: Planning Phase
**Related PR**: #143 (GUI Login System with User-Specific Settings Storage)

## Executive Summary

This document outlines the plan to refactor BMLibrarian's configuration system from JSON file-based storage to database-backed per-user settings. The goal is to enable multi-user support where each user has their own configuration profile stored in PostgreSQL, while maintaining backward compatibility with JSON files for migration and offline usage.

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Target Architecture](#target-architecture)
3. [Phased Implementation Plan](#phased-implementation-plan)
4. [Migration Strategy](#migration-strategy)
5. [File Changes Required](#file-changes-required)
6. [Testing Strategy](#testing-strategy)
7. [Rollback Plan](#rollback-plan)
8. [Risk Assessment](#risk-assessment)

---

## Current State Analysis

### Existing Configuration System

The current configuration system is JSON file-based with a singleton pattern:

**Core Module**: `src/bmlibrarian/config.py`
- `BMLibrarianConfig` class: Main configuration manager
- `DEFAULT_CONFIG`: Hardcoded default values
- Singleton pattern via `get_config()` function
- Configuration loading priority:
  1. `~/.bmlibrarian/config.json` (primary)
  2. `./bmlibrarian_config.json` (legacy fallback)
  3. Environment variables override
  4. Hardcoded defaults

**Key Methods**:
```python
get_config() -> BMLibrarianConfig      # Get singleton instance
get_model(agent_type) -> str           # Get model name for agent
get_agent_config(agent_type) -> dict   # Get agent configuration
get_ollama_config() -> dict            # Get Ollama server settings
get_search_config() -> dict            # Get search settings
```

**Configuration Categories** (10 total):
- `models` - Model names for each agent type
- `ollama` - Ollama server connection settings
- `agents` - Per-agent parameters (temperature, top_p, etc.)
- `database` - Database query settings
- `search` - Search behavior settings
- `query_generation` - Multi-model query settings
- `search_strategy` - Hybrid search configuration
- `openathens` - OpenAthens proxy settings
- `gui` - GUI-specific settings (new)
- `general` - General application settings (new)
- `pdf` - PDF processing settings (new)

### New Authentication & Settings System (PR #143)

**Database Schema**: `migrations/012_create_bmlsettings_schema.sql`
- Schema: `bmlsettings`
- Tables:
  - `user_settings(user_id, category, settings JSONB)`
  - `user_sessions(session_token, user_id, expires_at, ...)`
  - `default_settings(category, settings JSONB)`
- Utility functions:
  - `get_user_settings(user_id, category)` - Returns merged user + defaults
  - `save_user_settings(user_id, category, settings)` - Upsert user settings
  - `get_all_user_settings(user_id)` - Returns all as single JSONB

**Auth Module**: `src/bmlibrarian/auth/`
- `UserService`: Registration, login, session management
- `UserSettingsManager`: Database-backed per-user settings
  - `get(category)` - Get settings with fallback to defaults
  - `set(category, settings)` - Save settings for category
  - `get_all()` - Get all settings as dict
  - `reset_category(category)` - Revert to defaults

### Current Usage Locations

**CLI Modules**:
- `bmlibrarian_cli.py` - Main CLI application
- `src/bmlibrarian/cli/config.py` - CLI configuration management
- `fact_checker_cli.py` - Fact checker CLI
- All lab modules (query_lab.py, pico_lab.py, etc.)

**GUI Modules**:
- `src/bmlibrarian/gui/flet/config_app.py` - Flet configuration GUI
- `src/bmlibrarian/gui/qt/plugins/configuration/config_tab.py` - Qt config tab
- `src/bmlibrarian/gui/qt/dialogs/login_dialog.py` - Login dialog

**Agent Modules**:
- `src/bmlibrarian/agents/factory.py` - Agent creation factory
- All individual agent modules via `get_model()` and `get_agent_config()`

---

## Target Architecture

### Design Goals

1. **User-Specific Settings**: Each authenticated user has their own configuration
2. **Backward Compatibility**: JSON files continue to work for migration/offline
3. **Transparent Integration**: Existing code using `get_config()` works unchanged
4. **Session-Based**: Settings tied to authenticated sessions
5. **Fallback Chain**: User settings → Default settings → JSON file → Hardcoded defaults

### Architecture Overview

```
                         ┌─────────────────────────────────────┐
                         │           Application               │
                         └──────────────┬──────────────────────┘
                                        │
                                        ▼
                         ┌─────────────────────────────────────┐
                         │    BMLibrarianConfig (Singleton)    │
                         │    - set_user_context(user_id, conn)│
                         │    - get_model(), get_agent_config()│
                         └──────────────┬──────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
                    ▼                   ▼                   ▼
            ┌───────────────┐  ┌───────────────┐   ┌───────────────┐
            │ User Context  │  │ No User Auth  │   │ Offline Mode  │
            │   Present?    │  │  (CLI/batch)  │   │  (no DB conn) │
            └───────┬───────┘  └───────┬───────┘   └───────┬───────┘
                    │                  │                   │
                    ▼                  ▼                   ▼
            ┌───────────────┐  ┌───────────────┐   ┌───────────────┐
            │UserSettings   │  │DefaultSettings│   │   JSON File   │
            │Manager (DB)   │  │   (DB)        │   │  + Hardcoded  │
            └───────────────┘  └───────────────┘   └───────────────┘
```

### BMLibrarianConfig Enhanced Interface

```python
class BMLibrarianConfig:
    """Enhanced configuration manager with user context support."""

    # Existing interface (unchanged)
    def get_model(self, agent_type: str, default: Optional[str] = None) -> str
    def get_agent_config(self, agent_type: str) -> Dict[str, Any]
    def get_ollama_config(self) -> Dict[str, Any]
    def get_database_config(self) -> Dict[str, Any]
    def get_search_config(self) -> Dict[str, Any]
    def get(self, key_path: str, default=None) -> Any
    def set(self, key_path: str, value: Any) -> None
    def save_config(self, file_path: Optional[str] = None) -> None

    # New interface for user context
    def set_user_context(self, user_id: int, connection: Connection) -> None
    def clear_user_context(self) -> None
    def has_user_context(self) -> bool
    def get_user_id(self) -> Optional[int]

    # New interface for sync operations
    def sync_to_database(self) -> None
    def sync_from_database(self) -> None
    def export_to_json(self, file_path: Path) -> None
    def import_from_json(self, file_path: Path) -> None
```

### Configuration Resolution Order

When `get()` or `get_model()` is called:

1. **With User Context**:
   - Check `UserSettingsManager.get(category)` (DB user settings)
   - Falls back to `bmlsettings.default_settings` (DB defaults)
   - Falls back to `DEFAULT_CONFIG` (hardcoded)

2. **Without User Context** (batch/CLI mode):
   - Check `bmlsettings.default_settings` if DB connected
   - Falls back to JSON file (`~/.bmlibrarian/config.json`)
   - Falls back to `DEFAULT_CONFIG` (hardcoded)

3. **Offline Mode** (no DB connection):
   - Use JSON file only
   - Falls back to `DEFAULT_CONFIG`

---

## Phased Implementation Plan

### Phase 1: Core Infrastructure (Week 1)

**Objective**: Extend `BMLibrarianConfig` to support user context without breaking existing usage.

**Tasks**:

1.1. **Extend BMLibrarianConfig class**
   - Add `_user_context: Optional[UserContext]` dataclass
   - Add `_settings_manager: Optional[UserSettingsManager]`
   - Implement `set_user_context()` and `clear_user_context()`
   - Modify `_get_effective_config()` to check user context first

1.2. **Create UserContext dataclass**
   ```python
   @dataclass
   class UserContext:
       user_id: int
       connection: Connection
       session_token: Optional[str] = None
   ```

1.3. **Update config resolution methods**
   - `get()`: Check user settings first if context exists
   - `get_model()`: Use user settings fallback
   - `get_agent_config()`: Use user settings fallback

1.4. **Add settings sync utilities**
   - `sync_to_database()`: Push current config to user settings
   - `sync_from_database()`: Pull user settings into memory
   - `export_to_json()`: Export user settings to JSON
   - `import_from_json()`: Import JSON into user settings

**Files Modified**:
- `src/bmlibrarian/config.py`

**Tests**:
- Unit tests for user context management
- Integration tests for config resolution order

---

### Phase 2: CLI Integration (Week 2)

**Objective**: Add optional user authentication to CLI applications.

**Tasks**:

2.1. **Add auth options to CLI modules**
   - Add `--user` and `--password` arguments
   - Add `--session-token` for token-based auth
   - Implement session persistence (optional login caching)

2.2. **Create CLI auth helper module**
   ```python
   # src/bmlibrarian/cli/auth_helper.py
   def authenticate_cli(args) -> Optional[UserContext]:
       """Authenticate user for CLI session if credentials provided."""

   def setup_config_with_auth(args) -> BMLibrarianConfig:
       """Setup config with optional user authentication."""
   ```

2.3. **Update main CLI entry points**
   - `bmlibrarian_cli.py`
   - `fact_checker_cli.py`
   - `paper_checker_cli.py`
   - All lab modules

2.4. **Add config sync commands**
   ```bash
   uv run python bmlibrarian_cli.py config --sync-to-db
   uv run python bmlibrarian_cli.py config --sync-from-db
   uv run python bmlibrarian_cli.py config --export settings.json
   uv run python bmlibrarian_cli.py config --import settings.json
   ```

**Files Modified**:
- `src/bmlibrarian/cli/config.py`
- `bmlibrarian_cli.py`
- `fact_checker_cli.py`
- `paper_checker_cli.py`
- Lab modules

**New Files**:
- `src/bmlibrarian/cli/auth_helper.py`

---

### Phase 3: GUI Integration (Week 3)

**Objective**: Connect GUI applications to user-specific settings.

**Tasks**:

3.1. **Update Qt GUI after login**
   - Pass `user_id` and `connection` to config after login
   - Call `config.set_user_context()` on successful login
   - Load user settings into configuration tabs

3.2. **Update Qt configuration plugin**
   - Save changes to database instead of JSON
   - Add "Sync from JSON" button for migration
   - Add "Export to JSON" button for backup
   - Show "User Settings" vs "Default Settings" indicator

3.3. **Add user profile management tab**
   - View/edit current user profile
   - Reset categories to defaults
   - Import/export personal settings

3.4. **Update Flet GUI** (if keeping both)
   - Similar changes to config_app.py
   - Add login support

**Files Modified**:
- `src/bmlibrarian/gui/qt/core/application.py`
- `src/bmlibrarian/gui/qt/plugins/configuration/config_tab.py`
- `src/bmlibrarian/gui/qt/plugins/configuration/agent_config_widget.py`
- `src/bmlibrarian/gui/flet/config_app.py`

**New Files**:
- `src/bmlibrarian/gui/qt/plugins/configuration/user_profile_tab.py`

---

### Phase 4: Migration Tools (Week 4)

**Objective**: Provide tools for migrating existing JSON configurations to database.

**Tasks**:

4.1. **Create migration script**
   ```bash
   uv run python migrate_config_to_db.py --user <username> --config ~/.bmlibrarian/config.json
   ```

4.2. **Add first-login migration prompt**
   - Detect existing JSON config on first login
   - Offer to import settings to user profile
   - Don't delete JSON (keep as backup)

4.3. **Batch migration tool for admins**
   - Import default settings from JSON
   - Update `bmlsettings.default_settings`

4.4. **Documentation**
   - Migration guide for existing users
   - Update CLAUDE.md with new config system
   - Update user documentation

**New Files**:
- `migrate_config_to_db.py`
- `doc/users/settings_migration_guide.md`
- `doc/developers/db_settings_architecture.md`

---

### Phase 5: Testing & Polish (Week 5)

**Objective**: Comprehensive testing and edge case handling.

**Tasks**:

5.1. **Unit tests**
   - Config resolution order tests
   - User context lifecycle tests
   - Settings merge behavior tests

5.2. **Integration tests**
   - Full workflow with authenticated user
   - Fallback behavior without authentication
   - Offline mode behavior

5.3. **Edge cases**
   - Session expiry handling
   - Connection loss during settings save
   - Concurrent settings updates
   - Category validation

5.4. **Performance testing**
   - Config access latency with DB
   - Caching effectiveness

---

## Migration Strategy

### For Existing Users

1. **JSON Config Preserved**
   - Existing `~/.bmlibrarian/config.json` remains valid
   - Used as fallback when not authenticated
   - Never automatically deleted

2. **First Login Migration Flow**
   ```
   User logs in → Detect existing JSON config →
   Prompt: "Import your existing settings?" →
   If yes: Copy JSON values to user_settings →
   Continue with DB-backed settings
   ```

3. **Gradual Adoption**
   - Users can continue using JSON without login
   - Authenticated users get personalized settings
   - Settings sync available for both directions

### For System Administrators

1. **Update Default Settings**
   ```bash
   # Update database defaults from JSON
   uv run python migrate_config_to_db.py --defaults-only --config site_defaults.json
   ```

2. **Pre-provision User Settings**
   ```sql
   -- Copy defaults to specific user
   INSERT INTO bmlsettings.user_settings (user_id, category, settings)
   SELECT 123, category, settings FROM bmlsettings.default_settings;
   ```

---

## File Changes Required

### Modified Files

| File | Changes |
|------|---------|
| `src/bmlibrarian/config.py` | Add user context support, sync methods |
| `src/bmlibrarian/cli/config.py` | Add auth integration, sync commands |
| `bmlibrarian_cli.py` | Add --user/--password args |
| `fact_checker_cli.py` | Add auth args |
| `paper_checker_cli.py` | Add auth args |
| `src/bmlibrarian/gui/qt/core/application.py` | Set user context after login |
| `src/bmlibrarian/gui/qt/plugins/configuration/config_tab.py` | Save to DB |
| `src/bmlibrarian/gui/flet/config_app.py` | Add login/auth support |
| `src/bmlibrarian/agents/factory.py` | No changes (uses config API) |

### New Files

| File | Purpose |
|------|---------|
| `src/bmlibrarian/cli/auth_helper.py` | CLI authentication utilities |
| `src/bmlibrarian/gui/qt/plugins/configuration/user_profile_tab.py` | User profile management |
| `migrate_config_to_db.py` | Migration script |
| `doc/users/settings_migration_guide.md` | User migration documentation |
| `doc/developers/db_settings_architecture.md` | Technical architecture docs |
| `tests/test_config_user_context.py` | User context tests |
| `tests/test_settings_migration.py` | Migration tests |

---

## Testing Strategy

### Unit Tests

```python
# test_config_user_context.py

def test_config_without_user_context():
    """Config loads from JSON when no user context."""

def test_config_with_user_context():
    """Config loads from database when user context set."""

def test_config_resolution_order():
    """User settings → defaults → JSON → hardcoded."""

def test_set_value_with_user_context():
    """set() updates database when user context present."""

def test_clear_user_context():
    """Clearing context reverts to JSON-based config."""
```

### Integration Tests

```python
# test_settings_integration.py

def test_full_workflow_authenticated():
    """Test complete workflow with authenticated user."""

def test_session_expiry_handling():
    """Test behavior when session expires mid-operation."""

def test_import_export_roundtrip():
    """JSON export → import produces identical settings."""

def test_migration_preserves_all_settings():
    """All JSON settings correctly migrate to database."""
```

### Manual Testing Checklist

- [ ] Login with new user, verify defaults loaded
- [ ] Change settings in GUI, verify persisted to DB
- [ ] Logout/login, verify settings preserved
- [ ] Use CLI without auth, verify JSON fallback works
- [ ] Use CLI with auth, verify DB settings used
- [ ] Export settings to JSON, verify format correct
- [ ] Import JSON settings, verify all values applied
- [ ] Test offline mode (no DB), verify JSON-only mode
- [ ] Test concurrent settings updates from multiple clients

---

## Rollback Plan

### Phase 1 Rollback
- Revert `config.py` changes
- User context code is additive, minimal risk

### Phase 2 Rollback
- Remove CLI auth arguments
- Delete `auth_helper.py`
- CLI continues working with JSON config

### Phase 3 Rollback
- Revert GUI changes
- Configuration tabs save to JSON again
- Login still works but doesn't affect config

### Full Rollback
- Keep `bmlsettings` schema (no data loss)
- Configuration system uses JSON only
- Database settings remain but unused
- Can re-enable later without data loss

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing JSON users | Low | High | Preserve JSON fallback, never auto-delete |
| Performance degradation | Medium | Medium | Implement caching in UserSettingsManager |
| Session expiry mid-operation | Medium | Low | Graceful fallback to cached/JSON config |
| Settings sync conflicts | Low | Medium | Last-write-wins, add conflict detection later |
| Migration data loss | Low | High | Preserve original JSON, validate migration |

---

## Success Criteria

1. **Functional**
   - Authenticated users can save/load personal settings
   - Non-authenticated users continue using JSON
   - Settings persist across sessions
   - Import/export works correctly

2. **Performance**
   - Config access < 10ms with caching
   - Initial load < 100ms

3. **Compatibility**
   - All existing tests pass
   - No changes to agent behavior
   - JSON config files remain valid

4. **Documentation**
   - Migration guide published
   - Architecture documentation updated
   - CLAUDE.md updated with new system

---

## Appendix A: Category Mapping

| JSON Key | DB Category | Notes |
|----------|-------------|-------|
| `models` | `models` | Model names for agents |
| `ollama` | `ollama` | Ollama server config |
| `agents` | `agents` | Per-agent parameters |
| `database` | `database` | Database query settings |
| `search` | `search` | Search behavior |
| `query_generation` | `query_generation` | Multi-model queries |
| `search_strategy` | `search_strategy` | Hybrid search (→ `search`?) |
| `openathens` | `openathens` | Proxy authentication |
| N/A | `gui` | GUI-specific settings |
| N/A | `general` | General app settings |
| N/A | `pdf` | PDF processing settings |

## Appendix B: Database Schema Reference

```sql
-- User settings table
CREATE TABLE bmlsettings.user_settings (
    setting_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES public.users(id),
    category TEXT NOT NULL,
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, category)
);

-- Default settings table
CREATE TABLE bmlsettings.default_settings (
    default_id SERIAL PRIMARY KEY,
    category TEXT UNIQUE NOT NULL,
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Key functions
SELECT bmlsettings.get_user_settings(user_id, category);
SELECT bmlsettings.get_all_user_settings(user_id);
SELECT bmlsettings.save_user_settings(user_id, category, settings);
```

---

**Document History**:
- 2025-11-22: Initial draft created
