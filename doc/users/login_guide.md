# BMLibrarian Login Guide

This guide explains how to use the login system in BMLibrarian's Qt GUI application.

## Overview

BMLibrarian supports multiple users, each with their own settings and preferences. The login system provides:

- User registration and authentication
- PostgreSQL database connection configuration
- Session management for secure access

## Starting the Application

When you start the Qt GUI application, a login dialog will appear with two tabs:

1. **Login / Register** - For authentication
2. **Database Connection** - For configuring the PostgreSQL database

### First-Time Setup

If this is your first time using BMLibrarian:

1. Go to the **Database Connection** tab
2. Enter your PostgreSQL connection details:
   - **Host**: Usually `localhost` for local installations
   - **Port**: Default is `5432`
   - **Database**: Usually `knowledgebase`
   - **Username**: Your PostgreSQL username
   - **Password**: Your PostgreSQL password
3. Click **Test Connection** to verify the settings
4. Click **Save Settings** to save the configuration

The connection settings are saved to `~/.bmlibrarian/.env`.

### Registering a New Account

1. Go to the **Login / Register** tab
2. In the **New User Registration** section:
   - Enter a unique username
   - Enter your email address
   - Choose a password (minimum 4 characters)
   - Confirm your password
3. Click **Register**

After successful registration, you'll be automatically logged in.

### Logging In

1. Go to the **Login / Register** tab
2. In the **Login** section:
   - Enter your username
   - Enter your password
3. Click **Login** or press Enter

## Session Management

- Sessions are automatically created on login
- Sessions expire after 24 hours of inactivity
- You can use the same account on multiple computers

## Troubleshooting

### "Connection failed" error

- Verify your PostgreSQL server is running
- Check the connection parameters in the Database Connection tab
- Ensure the database exists and the schema is up to date

### "User not found" error

- Check your username for typos
- If you haven't registered, use the Registration section first

### "Invalid password" error

- Check your password for typos
- Passwords are case-sensitive

## Database Requirements

The login system requires the following database components:

1. **public.users table** - For user accounts
2. **bmlsettings schema** - For user settings and sessions

These are created automatically when you run the database migrations:

```bash
# Run migrations to set up the database schema
uv run python initial_setup_and_download.py your_database.env
```

## Configuration Files

The login system uses the following configuration files:

| File | Purpose |
|------|---------|
| `~/.bmlibrarian/.env` | Database connection settings |
| `~/.bmlibrarian/config.json` | Application settings |
| `~/.bmlibrarian/bmlibrarian_qt_config.json` | GUI-specific settings |

## Security Notes

- Passwords are hashed using PBKDF2-SHA256 with 100,000 iterations
- Session tokens are cryptographically random 256-bit values
- Sessions expire automatically after 24 hours
- Connection settings are stored locally (not in the database)
