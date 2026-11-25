# Settings Migration Guide

This guide explains how to migrate your BMLibrarian configuration from JSON files to database-backed user settings.

## Overview

BMLibrarian now supports database-backed settings that:
- Sync across all your devices
- Are tied to your user account
- Persist even if you reinstall the application
- Allow per-user customization on shared systems

## Automatic Migration (Recommended)

Your `~/.bmlibrarian/config.json` is used as soon as you log in; nothing
has to be imported for it to apply. If you have no settings saved in the
database yet, the Qt GUI shows a short notice after login. To keep your
settings in your user profile, click **Sync to Database** in the
Configuration tab. The notice stops once you have saved.

### What Gets Migrated

The following configuration categories are migrated:

| Category | Description |
|----------|-------------|
| `models` | Default AI model assignments |
| `ollama` | Ollama server configuration |
| `agents` | Agent-specific parameters (temperature, etc.) |
| `database` | Database connection settings |
| `search` | Search behavior settings |
| `query_generation` | Multi-model query generation settings |
| `gui` | GUI preferences and layout |
| `openathens` | OpenAthens authentication config |
| `pdf` | PDF handling settings |
| `general` | General application settings |

### What's Preserved

- Your original `~/.bmlibrarian/config.json` file is **not deleted**
- It serves as a backup and for offline use
- You can still use JSON config if not authenticated

## Manual Migration

### Using the Migration Script

For command-line migration, use the `migrate_config_to_db.py` script:

```bash
# Interactive mode (recommended for first time)
uv run python migrate_config_to_db.py --interactive

# Migrate specific config to your user account
uv run python migrate_config_to_db.py \
    --user your_username \
    --config ~/.bmlibrarian/config.json

# Migrate and replace existing settings (not merge)
uv run python migrate_config_to_db.py \
    --user your_username \
    --config /path/to/config.json \
    --replace
```

### Using the Configuration Tab

1. Open the BMLibrarian Qt application and log in
2. Navigate to the **Configuration** tab
3. Click **Load Configuration** to load a JSON file
4. Make any adjustments needed
5. Click **Save to ~/.bmlibrarian** - this will also sync to the database

### Exporting Settings

To export your database settings back to JSON:

```bash
# Export user settings
uv run python migrate_config_to_db.py \
    --export \
    --user your_username \
    --output my_settings_backup.json

# Export default settings (admin)
uv run python migrate_config_to_db.py \
    --export \
    --defaults \
    --output default_settings.json
```

## Administrator Operations

### Setting Default Settings

Administrators can set system-wide default settings:

```bash
# Import a config as the default settings
uv run python migrate_config_to_db.py \
    --defaults \
    --config /path/to/default_config.json
```

These defaults are not applied to the configuration at login: a user who
hasn't saved a category keeps the value from their `config.json` (or the
built-in default). They are what the settings manager returns for a category
the user never saved, and what `--export --defaults` writes.

### Environment Variables

The migration script uses these environment variables for database connection:

```bash
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=knowledgebase
export POSTGRES_USER=your_db_user
export POSTGRES_PASSWORD=your_db_password
```

## Configuration Resolution Order

When you use BMLibrarian, settings are resolved in this priority order:

### With User Authentication:
1. `BMLIB_*` environment variables (highest priority; the agent models
   and the Ollama host/timeout)
2. User's database settings (only categories you saved)
3. JSON file (`~/.bmlibrarian/config.json`)
4. Hardcoded application defaults

### Without Authentication (CLI/Batch):
1. `BMLIB_*` environment variables
2. JSON file (`~/.bmlibrarian/config.json`)
3. Hardcoded application defaults

### Offline Mode:
1. `BMLIB_*` environment variables
2. JSON file (`~/.bmlibrarian/config.json`)
3. Hardcoded application defaults

`BMLIB_*` values apply only while the variable is set. Saving (Save,
Sync to Database, Export) stores the value underneath them, not the
environment value, so it does not outlive the variable. If you change an
overridden setting yourself before saving, your value is saved (unless it is
the same as the variable's value).

When `migrate_config_to_db.py` imports into a user, merging (the default;
`--replace` turns it off) combines the JSON with that user's own saved
settings, never with the system defaults; `--export --user` likewise
exports only what the user saved.

## Troubleshooting

### Migration Failed

If automatic migration fails:

1. Check that the database connection is working
2. Verify your JSON config file is valid:
   ```bash
   python -m json.tool ~/.bmlibrarian/config.json
   ```
3. Try manual migration with verbose output:
   ```bash
   uv run python migrate_config_to_db.py -v --interactive
   ```

### Settings Not Syncing

If your settings aren't syncing between devices:

1. Verify you're logged in with the same account
2. Check the sync status in the Configuration tab
3. Try clicking "Sync from Database" to refresh

### Reverting to JSON Config

To use JSON config instead of database settings:

1. Log out of the application
2. Use CLI tools without the `--user` flag
3. Your JSON config will be used automatically

## Database Schema

Settings are stored in the `bmlsettings` schema:

- `user_settings` - Per-user settings (category, settings JSONB)
- `default_settings` - System-wide defaults
- `user_sessions` - Session management

See [Database Settings Architecture](../developers/db_settings_architecture.md) for technical details.
