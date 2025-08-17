# API Reference

This document provides a complete reference for BMLibrarian's public APIs.

## Module: `bmlibrarian.migrations`

### Class: `MigrationManager`

The central class for managing database migrations.

#### Constructor

```python
MigrationManager(host: str, port: str, user: str, password: str, database: str)
```

Creates a new MigrationManager instance.

**Parameters:**
- `host` (str): PostgreSQL server hostname
- `port` (str): PostgreSQL server port number
- `user` (str): Database username
- `password` (str): Database password
- `database` (str): Target database name

**Example:**
```python
from bmlibrarian.migrations import MigrationManager

manager = MigrationManager(
    host="localhost",
    port="5432",
    user="bmlib_user",
    password="secure_password",
    database="bmlibrarian_dev"
)
```

#### Methods

##### `initialize_database(baseline_schema_path: Path) -> None`

Initializes a database with the baseline schema.

**Parameters:**
- `baseline_schema_path` (Path): Path to the baseline SQL schema file

**Raises:**
- `FileNotFoundError`: If the baseline schema file doesn't exist
- `psycopg.Error`: If database operations fail

**Example:**
```python
from pathlib import Path

manager.initialize_database(Path("baseline_schema.sql"))
```

**Behavior:**
1. Checks if the database exists, creates it if necessary
2. Creates the migration tracking table
3. Checks if baseline has already been applied
4. Applies the baseline schema if not already applied
5. Records the baseline as an applied migration

##### `apply_pending_migrations(migrations_dir: Path) -> int`

Applies all pending migrations from the specified directory.

**Parameters:**
- `migrations_dir` (Path): Directory containing migration files

**Returns:**
- `int`: Number of migrations that were applied

**Raises:**
- `Exception`: If any migration fails (exits with code 1)

**Example:**
```python
from pathlib import Path

applied_count = manager.apply_pending_migrations(
    Path.home() / ".bmlibrarian" / "migrations"
)
print(f"Applied {applied_count} migrations")
```

**Behavior:**
1. Creates migrations directory if it doesn't exist
2. Ensures migration tracking table exists
3. Discovers migration files (*.sql with numeric prefixes)
4. Applies migrations in filename order
5. Records each successful migration
6. Stops on first failure and exits

#### Private Methods

These methods are internal implementation details and may change:

##### `_get_connection(database: str = None) -> psycopg.Connection`

Gets a database connection.

##### `_database_exists(database_name: str) -> bool`

Checks if a database exists.

##### `_create_database(database_name: str) -> None`

Creates a new database.

##### `_create_migrations_table() -> None`

Creates the migration tracking table.

##### `_get_applied_migrations() -> List[Tuple[str, str]]`

Returns list of applied migrations with their checksums.

##### `_calculate_checksum(content: str) -> str`

Calculates SHA-256 checksum of migration content.

##### `_apply_sql_file(sql_file_path: Path) -> None`

Executes a SQL file against the database.

##### `_record_migration(filename: str, checksum: str) -> None`

Records a migration as applied in the tracking table.

## Module: `bmlibrarian.app`

### Function: `initialize_app() -> None`

Initializes the BMLibrarian application and applies pending migrations.

**Environment Variables Required:**
- `POSTGRES_USER`: Database username
- `POSTGRES_PASSWORD`: Database password

**Environment Variables Optional:**
- `POSTGRES_HOST`: Database host (default: "localhost")
- `POSTGRES_PORT`: Database port (default: "5432")
- `POSTGRES_DB`: Database name (default: "bmlibrarian_dev")

**Raises:**
- `ValueError`: If required environment variables are not set

**Example:**
```python
import os
import bmlibrarian

# Set up environment
os.environ['POSTGRES_USER'] = 'bmlib_user'
os.environ['POSTGRES_PASSWORD'] = 'secure_password'

# Initialize app (applies pending migrations)
bmlibrarian.initialize_app()
```

**Behavior:**
1. Reads database configuration from environment variables
2. Creates a MigrationManager instance
3. Applies pending migrations from `~/.bmlibrarian/migrations/`
4. Prints status messages for applied migrations
5. Handles migration errors gracefully with warnings

### Function: `get_database_connection() -> psycopg.Connection`

Gets a database connection using environment configuration.

**Environment Variables Required:**
- `POSTGRES_USER`: Database username
- `POSTGRES_PASSWORD`: Database password

**Environment Variables Optional:**
- `POSTGRES_HOST`: Database host (default: "localhost")
- `POSTGRES_PORT`: Database port (default: "5432")
- `POSTGRES_DB`: Database name (default: "bmlibrarian_dev")

**Returns:**
- `psycopg.Connection`: Active database connection

**Raises:**
- `ValueError`: If required environment variables are not set
- `psycopg.Error`: If database connection fails

**Example:**
```python
import bmlibrarian

# Get connection
conn = bmlibrarian.get_database_connection()

# Use connection
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM bmlibrarian_migrations")
    count = cur.fetchone()[0]
    print(f"Applied migrations: {count}")

# Clean up
conn.close()
```

## Module: `bmlibrarian.cli`

### Function: `create_parser() -> argparse.ArgumentParser`

Creates the command-line argument parser.

**Returns:**
- `argparse.ArgumentParser`: Configured argument parser

**Example:**
```python
from bmlibrarian.cli import create_parser

parser = create_parser()
args = parser.parse_args(["migrate", "init", "--host", "localhost"])
```

### Function: `main() -> None`

Main entry point for the CLI application.

**Behavior:**
1. Parses command-line arguments
2. Validates required parameters
3. Executes the appropriate command
4. Handles errors and exits with appropriate code

**Example:**
```python
import sys
from bmlibrarian.cli import main

# Simulate CLI call
sys.argv = ["bmlibrarian", "migrate", "init", "--host", "localhost", 
           "--user", "testuser", "--password", "testpass", "--database", "testdb"]
main()
```

## Package-Level Imports

The main package provides convenient access to key functionality:

```python
import bmlibrarian

# Available functions
bmlibrarian.initialize_app()        # Auto-apply migrations
bmlibrarian.get_database_connection()  # Get DB connection
bmlibrarian.MigrationManager         # Migration management class
```

## Error Handling

### Exception Hierarchy

BMLibrarian uses standard Python and psycopg exceptions:

**Database Errors:**
- `psycopg.Error`: Base database error
- `psycopg.OperationalError`: Connection and operational errors
- `psycopg.ProgrammingError`: SQL syntax and programming errors

**Application Errors:**
- `ValueError`: Invalid configuration or parameters
- `FileNotFoundError`: Missing migration or schema files
- `SystemExit`: CLI command failures

### Error Context

Most errors include helpful context:

```python
try:
    manager.initialize_database(Path("missing_file.sql"))
except FileNotFoundError as e:
    print(f"Schema file not found: {e}")
    # Output: Schema file not found: Baseline schema file not found: missing_file.sql
```

## Environment Configuration

### Required Variables

```bash
export POSTGRES_USER=your_username
export POSTGRES_PASSWORD=your_password
```

### Optional Variables

```bash
export POSTGRES_HOST=localhost      # Default: localhost
export POSTGRES_PORT=5432          # Default: 5432
export POSTGRES_DB=bmlibrarian_dev # Default: bmlibrarian_dev
```

### Configuration Validation

```python
# Check if environment is properly configured
import os

required_vars = ['POSTGRES_USER', 'POSTGRES_PASSWORD']
missing_vars = [var for var in required_vars if not os.environ.get(var)]

if missing_vars:
    raise ValueError(f"Missing environment variables: {missing_vars}")
```

## Usage Patterns

### Basic Application Integration

```python
import bmlibrarian

# Simple setup for most applications
bmlibrarian.initialize_app()
conn = bmlibrarian.get_database_connection()

# Use connection for your application logic
try:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM your_table")
        results = cur.fetchall()
finally:
    conn.close()
```

### Custom Migration Management

```python
from bmlibrarian.migrations import MigrationManager
from pathlib import Path

# Custom configuration
manager = MigrationManager(
    host="custom-host",
    port="5433",
    user="admin",
    password="secret",
    database="production_db"
)

# Initialize new database
manager.initialize_database(Path("custom_schema.sql"))

# Apply migrations from custom directory
applied = manager.apply_pending_migrations(Path("/opt/migrations"))
print(f"Applied {applied} custom migrations")
```

### CLI Integration

```python
import subprocess
import sys

# Run CLI commands from Python
def run_migration_command(args):
    """Run bmlibrarian CLI command."""
    cmd = ["bmlibrarian"] + args
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e.stderr}")
        sys.exit(e.returncode)

# Initialize database
run_migration_command([
    "migrate", "init",
    "--host", "localhost",
    "--user", "testuser",
    "--password", "testpass",
    "--database", "testdb"
])
```

## Thread Safety

**MigrationManager:** Not thread-safe. Create separate instances for concurrent use.

**Database Connections:** psycopg connections are thread-safe at the connection level but not at the cursor level.

**Example for concurrent use:**
```python
import threading
from bmlibrarian.migrations import MigrationManager

def worker_thread(thread_id):
    # Each thread gets its own manager
    manager = MigrationManager(
        host="localhost",
        port="5432", 
        user="worker",
        password="password",
        database=f"worker_db_{thread_id}"
    )
    # Perform operations...

# Start multiple worker threads
threads = []
for i in range(3):
    t = threading.Thread(target=worker_thread, args=(i,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()
```

## Performance Considerations

### Connection Management

- Create MigrationManager instances only when needed
- Close database connections promptly
- Use connection pooling for high-frequency operations

### Migration Performance

- Large migrations should use transactions judiciously
- Consider `CONCURRENTLY` for index creation
- Monitor migration execution time

### Memory Usage

- Migration files are read entirely into memory
- Large SQL files may impact memory usage
- Consider breaking up very large migrations

## Debugging

### Enable Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# BMLibrarian operations will now include debug output
bmlibrarian.initialize_app()
```

### Inspect Migration State

```python
from bmlibrarian.migrations import MigrationManager

manager = MigrationManager(...)

# Check applied migrations
applied = manager._get_applied_migrations()
print("Applied migrations:")
for filename, checksum in applied:
    print(f"  {filename}: {checksum[:8]}...")

# Check if database exists
exists = manager._database_exists("test_db")
print(f"Database exists: {exists}")
```

## Version Compatibility

**Python:** Requires Python 3.12+
**PostgreSQL:** Requires PostgreSQL 12+
**psycopg:** Requires psycopg 3.2.9+

### Checking Versions

```python
import sys
import psycopg
import bmlibrarian

print(f"Python: {sys.version}")
print(f"psycopg: {psycopg.__version__}")
print(f"BMLibrarian: {bmlibrarian.__version__}")
```