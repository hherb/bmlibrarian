# CLI Reference

BMLibrarian provides a command-line interface for managing database migrations and other operations.

## Overview

The `bmlibrarian` command provides access to various functionality:

```bash
bmlibrarian [COMMAND] [OPTIONS]
```

## Global Options

- `--help, -h`: Show help message and exit

## Commands

### `migrate`

Database migration management commands.

```bash
bmlibrarian migrate [ACTION] [OPTIONS]
```

#### Actions

##### `init`

Initialize a database with the baseline schema.

**Usage:**
```bash
bmlibrarian migrate init [OPTIONS]
```

**Required Options:**
- `--host HOST`: PostgreSQL host
- `--user USER`: PostgreSQL username  
- `--password PASSWORD`: PostgreSQL password
- `--database DATABASE`: Database name to create

**Optional Options:**
- `--port PORT`: PostgreSQL port (default: 5432)
- `--baseline-schema PATH`: Path to baseline schema file (default: auto-detected)

**Examples:**

Initialize a new database:
```bash
bmlibrarian migrate init \
    --host localhost \
    --user bmlib_user \
    --password mypassword \
    --database bmlibrarian_production
```

Initialize with custom baseline schema:
```bash
bmlibrarian migrate init \
    --host db.example.com \
    --port 5433 \
    --user admin \
    --password secret \
    --database my_bmlib_db \
    --baseline-schema /path/to/custom_schema.sql
```

**What it does:**
1. Connects to PostgreSQL server
2. Creates the specified database if it doesn't exist
3. Creates the migration tracking table
4. Applies the baseline schema
5. Records the baseline as the first migration

##### `apply`

Apply pending migrations to the database.

**Usage:**
```bash
bmlibrarian migrate apply [OPTIONS]
```

**Required Options:**
- `--host HOST`: PostgreSQL host
- `--user USER`: PostgreSQL username
- `--password PASSWORD`: PostgreSQL password  
- `--database DATABASE`: Database name

**Optional Options:**
- `--port PORT`: PostgreSQL port (default: 5432)
- `--migrations-dir PATH`: Custom migrations directory (default: ~/.bmlibrarian/migrations)

**Examples:**

Apply pending migrations:
```bash
bmlibrarian migrate apply \
    --host localhost \
    --user bmlib_user \
    --password mypassword \
    --database bmlibrarian_production
```

Apply from custom directory:
```bash
bmlibrarian migrate apply \
    --host localhost \
    --user bmlib_user \
    --password mypassword \
    --database bmlibrarian_production \
    --migrations-dir /opt/bmlibrarian/custom_migrations
```

**What it does:**
1. Connects to the specified database
2. Ensures migration tracking table exists
3. Discovers migration files in the migrations directory
4. Applies migrations that haven't been applied yet (in filename order)
5. Records each successful migration

## Exit Codes

The CLI commands return standard exit codes:

- `0`: Success
- `1`: General error (invalid arguments, missing files, etc.)
- `2`: Database connection error
- `3`: Migration application error

## Environment Variables

You can use environment variables to provide default values:

- `POSTGRES_HOST`: Default database host
- `POSTGRES_PORT`: Default database port  
- `POSTGRES_USER`: Default database username
- `POSTGRES_PASSWORD`: Default database password
- `POSTGRES_DB`: Default database name

**Example with environment variables:**
```bash
export POSTGRES_HOST=localhost
export POSTGRES_USER=bmlib_user
export POSTGRES_PASSWORD=mypassword
export POSTGRES_DB=bmlibrarian_dev

# Now you can run commands with fewer options
bmlibrarian migrate init --database $POSTGRES_DB
```

## Configuration Files

The CLI currently uses environment variables and command-line arguments. Future versions may support configuration files.

## Logging and Output

### Verbose Output

All commands provide detailed output about their operations:

```
$ bmlibrarian migrate init --host localhost --user test --password test --database testdb
Checking if database 'testdb' exists...
Creating database 'testdb'...
Creating migrations tracking table...
Applying baseline schema...
Baseline schema applied successfully!
Database initialized successfully!
```

### Error Messages

Error messages are designed to be helpful and actionable:

```
$ bmlibrarian migrate init --host badhost --user test --password test --database testdb
Error: Could not connect to database server at badhost:5432
Please check:
- Database server is running
- Host and port are correct
- Network connectivity
```

## Security Considerations

### Password Handling

- Never use passwords directly in scripts that might be logged
- Use environment variables for passwords:
  ```bash
  export POSTGRES_PASSWORD=mysecretpassword
  bmlibrarian migrate init --host localhost --user bmlib --password "$POSTGRES_PASSWORD" --database mydb
  ```
- Consider using `.pgpass` file for PostgreSQL authentication
- Use connection strings with proper escaping if needed

### Database Permissions

The user account should have minimal required permissions:

**For `migrate init`:**
- `CREATEDB` privilege (to create databases)
- `CREATE` privilege on the target database
- `INSERT`, `SELECT` on migration tracking table

**For `migrate apply`:**
- `CREATE` privilege on the target database (for tables, indexes)
- `INSERT`, `SELECT` on migration tracking table
- Appropriate permissions for migration operations

### Network Security

- Use SSL connections in production:
  ```bash
  # Most PostgreSQL clients support SSL by default
  bmlibrarian migrate apply --host secure-db.example.com --user bmlib --password "$PASSWORD" --database production
  ```
- Restrict database server access via firewall rules
- Use VPN or private networks for database access

## Troubleshooting

### Common Issues

**"Command not found: bmlibrarian"**
- Ensure BMLibrarian is installed: `pip install bmlibrarian`
- Check if it's in your PATH
- Try with full path or virtual environment activation

**"Permission denied"**
- Check database user permissions
- Verify the user can connect to PostgreSQL
- Ensure user has required privileges for the operation

**"Database does not exist"**
- For `migrate apply`: Run `migrate init` first
- Check database name spelling
- Verify connection parameters

**"Migration already applied"**
- This is normal - migrations are idempotent
- Check `bmlibrarian_migrations` table to see applied migrations

**"Connection refused"**
- Check PostgreSQL server is running
- Verify host and port
- Check firewall settings
- Ensure PostgreSQL is configured to accept connections

### Getting Help

**Command-specific help:**
```bash
bmlibrarian --help
bmlibrarian migrate --help
bmlibrarian migrate init --help
bmlibrarian migrate apply --help
```

**Version information:**
```bash
python -c "import bmlibrarian; print(bmlibrarian.__version__)"
```

**Check installation:**
```bash
pip show bmlibrarian
```