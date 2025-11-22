# BMLibrarian Authentication System

This document describes the authentication and user settings system architecture.

## Overview

The authentication system provides multi-user support for BMLibrarian with:

- User registration and authentication
- Session-based access control
- Per-user settings storage
- Database-backed configuration

## Architecture

### Database Schema

The system uses two database schemas:

1. **public.users** - User accounts (existing table)
2. **bmlsettings** - User settings and sessions (migration 012)

#### public.users Table

```sql
CREATE TABLE public.users (
    id integer PRIMARY KEY,
    username text NOT NULL UNIQUE,
    firstname text,
    surname text,
    email text NOT NULL UNIQUE,
    pwdhash text NOT NULL
);
```

#### bmlsettings Schema

```sql
-- Per-user settings (JSONB by category)
CREATE TABLE bmlsettings.user_settings (
    setting_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id),
    category TEXT NOT NULL,
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, category)
);

-- Session management
CREATE TABLE bmlsettings.user_sessions (
    session_id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id),
    session_token TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    last_active TIMESTAMP DEFAULT NOW(),
    client_type TEXT,
    client_version TEXT,
    hostname TEXT
);

-- System-wide defaults
CREATE TABLE bmlsettings.default_settings (
    default_id SERIAL PRIMARY KEY,
    category TEXT NOT NULL UNIQUE,
    settings JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by INTEGER REFERENCES public.users(id)
);
```

### Python Modules

#### src/bmlibrarian/auth/user_service.py

Provides user registration and authentication:

```python
from bmlibrarian.auth import UserService

with db_manager.get_connection() as conn:
    user_service = UserService(conn)

    # Register
    user = user_service.register(
        username="alice",
        email="alice@example.com",
        password="secure123"
    )

    # Authenticate
    user, session_token = user_service.authenticate(
        username="alice",
        password="secure123"
    )

    # Validate session
    user = user_service.validate_session(session_token)
```

**Password Hashing:**
- Algorithm: PBKDF2-HMAC-SHA256
- Iterations: 100,000
- Salt: 256-bit random (per password)
- Format: `{salt_hex}${hash_hex}`

#### src/bmlibrarian/auth/user_settings.py

Provides per-user settings management:

```python
from bmlibrarian.auth import UserSettingsManager

with db_manager.get_connection() as conn:
    settings = UserSettingsManager(conn, user_id=1)

    # Get settings by category
    models = settings.get('models')

    # Get specific value with default
    host = settings.get_value('ollama', 'host', 'http://localhost:11434')

    # Save settings
    settings.set('models', {'query_agent': 'gpt-oss:20b'})

    # Get all settings
    all_settings = settings.get_all()
```

**Settings Categories:**
- `models` - Model assignments per agent
- `ollama` - Ollama server settings
- `agents` - Agent-specific parameters
- `database` - Database query settings
- `search` - Search settings
- `query_generation` - Multi-model query settings
- `gui` - GUI-specific settings
- `openathens` - OpenAthens authentication
- `pdf` - PDF processing settings
- `general` - Miscellaneous settings

### GUI Components

#### src/bmlibrarian/gui/qt/dialogs/login_dialog.py

The login dialog provides:
- Two-tab interface (Login/Register + Database Connection)
- Database connection testing and saving
- User registration and authentication
- Session token generation

**Note:** This module intentionally uses `psycopg.connect()` directly instead of DatabaseManager because it runs before the database connection is configured.

## Database Functions

The bmlsettings schema includes utility functions:

```sql
-- Get settings with fallback to defaults
SELECT bmlsettings.get_user_settings(user_id, 'models');

-- Save settings (upsert)
SELECT bmlsettings.save_user_settings(user_id, 'models', '{"query_agent": "gpt-oss:20b"}');

-- Get all settings as single JSONB
SELECT bmlsettings.get_all_user_settings(user_id);

-- Session management
SELECT bmlsettings.create_session(user_id, 'qt_gui', 'v1.0', 'hostname', 24);
SELECT bmlsettings.validate_session('token_string');
SELECT bmlsettings.cleanup_expired_sessions();
```

## Integration Points

### Qt Application Flow

1. `BMLibrarianApplication.run()` calls `_show_login_dialog()`
2. `LoginDialog` authenticates user and establishes database connection
3. `BMLibrarianMainWindow` is created with `user_id` and `username`
4. Plugins can access `main_window.user_id` for user-specific operations

### Backwards Compatibility

The system maintains backwards compatibility:
- `.env` file still used for database connection
- `config.json` still loaded for non-user-specific settings
- User settings merge with and override defaults

## Security Considerations

1. **Password Storage**: PBKDF2 with high iteration count
2. **Session Tokens**: 256-bit cryptographically random
3. **Session Expiry**: 24-hour default
4. **Connection Config**: Stored locally, not in database
5. **Input Validation**: All inputs sanitized before use

## Future Improvements

Planned for Step 2:
- Refactor existing modules to use `UserSettingsManager`
- Add settings sync from/to JSON files
- Add user profile management in GUI
- Add role-based access control (optional)
