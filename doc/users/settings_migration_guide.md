# Settings Migration Guide

This guide explains how to migrate your BMLibrarian configuration from JSON files to database-backed user settings.

## Overview

BMLibrarian now supports database-backed settings that:
- Sync across all your devices
- Are tied to your user account
- Persist even if you reinstall the application
- Allow per-user customization on shared systems

## Automatic Migration (Recommended)

When you log in to the BMLibrarian Qt GUI for the first time, the application will:

1. Detect if you have an existing `~/.bmlibrarian/config.json` file
2. Check if you already have settings in the database
3. If no database settings exist, offer to import your local config

Simply click **Yes** when prompted to import your settings.

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

These defaults are used when:
- A user hasn't customized a particular category
- Running in batch/CLI mode without authentication

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
1. User's database settings (highest priority)
2. Default database settings
3. Hardcoded application defaults

### Without Authentication (CLI/Batch):
1. Default database settings
2. JSON file (`~/.bmlibrarian/config.json`)
3. Hardcoded application defaults

### Offline Mode:
1. JSON file only
2. Hardcoded application defaults

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
