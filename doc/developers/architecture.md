# BMLibrarian Architecture

This document describes the architecture and design principles of the BMLibrarian migration system.

## Overview

BMLibrarian is designed as a modular Python library for biomedical literature database management. The migration system is a core component that ensures database schema consistency across environments and versions.

## System Architecture

```
BMLibrarian
├── Migration System
│   ├── MigrationManager (core logic)
│   ├── CLI Interface (user interaction)
│   └── App Integration (automatic migrations)
├── Database Layer
│   ├── PostgreSQL + pgvector
│   └── Connection Management
└── Future Modules
    ├── Literature Indexing
    ├── Search Engine
    └── API Layer
```

## Core Components

### 1. MigrationManager (`src/bmlibrarian/migrations.py`)

The central class responsible for all migration operations.

**Responsibilities:**
- Database connection management
- Migration discovery and validation
- Schema application and tracking
- Error handling and rollback safety

**Key Methods:**
- `initialize_database()`: Sets up new database with baseline schema
- `apply_pending_migrations()`: Applies unapplied migrations
- `_database_exists()`: Checks database existence
- `_migration_lock()`: Holds the migration lock (session advisory lock) for one run
- `_apply_migration()`: Executes one migration and records it in the same transaction

**Design Principles:**
- **Idempotent operations**: Safe to run multiple times
- **Atomic transactions**: A migration's SQL and its record commit together
- **One process at a time**: Concurrent runs wait for the migration lock
- **Checksums**: Each applied migration's SHA-256 is recorded (not yet
  compared on later runs)
- **Ordered execution**: Numeric prefixes ensure proper sequencing

### 2. CLI Interface (`src/bmlibrarian/cli.py`)

Command-line interface for migration management.

**Structure:**
```
bmlibrarian
└── migrate
    ├── init    (initialize database)
    └── apply   (apply migrations)
```

**Features:**
- Argument parsing with validation
- Environment variable integration
- Comprehensive error reporting
- Security-conscious credential handling

### 3. App Integration (`src/bmlibrarian/app.py`)

Provides seamless integration with Python applications.

**Functions:**
- `initialize_app()`: Auto-applies pending migrations on startup
- `get_database_connection()`: Provides configured database connections

**Integration Pattern:**
```python
import bmlibrarian

# Automatically handles migrations
bmlibrarian.initialize_app()

# Ready-to-use database connection
conn = bmlibrarian.get_database_connection()
```

## Database Schema

### Migration Tracking Table

```sql
CREATE TABLE bmlibrarian_migrations (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL UNIQUE,
    checksum VARCHAR(64) NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Purpose:**
- Track which migrations have been applied
- Prevent duplicate application
- Maintain application order history
- Detect unauthorized modifications (via checksum)

### Baseline Schema

The baseline schema includes:
- Core biomedical literature tables
- Required PostgreSQL extensions (pgvector, pg_trgm)
- Indexes for performance
- Initial data if needed

## Migration Lifecycle

```mermaid
graph TD
    A[Migration Created] --> B[Files Discovered]
    B --> D[Read Applied Set]
    D --> E{Any Pending?}
    E -->|No| M[Complete]
    E -->|Yes| P[Take Migration Lock, once per run]
    P --> G[Next Pending File: Begin Transaction]
    G --> Q{Applied Meanwhile?}
    Q -->|Yes| F[Skip File]
    Q -->|No| H[Execute SQL]
    H --> I{Success?}
    I -->|No| K[Rollback & Error]
    I -->|Yes| C{CONCURRENTLY Indexes?}
    C -->|No| J[Record and Commit]
    C -->|Yes| R[Commit, Build Indexes, Check Valid]
    R --> S[Record and Commit]
    F --> T{More Files?}
    J --> T
    S --> T
    T -->|Yes| G
    T -->|No| M
    K --> N[Exit with Error]
```

## Security Model

### Principles

1. **Least Privilege**: Database users should have minimal required permissions
2. **Credential Protection**: No passwords in code or logs
3. **Input Validation**: All user inputs are validated
4. **SQL Injection Prevention**: Use parameterized queries

### Permission Requirements

**For Database Initialization (`migrate init`):**
- `CREATEDB` privilege (to create databases)
- `CREATE` privilege on target database
- `INSERT`, `SELECT` on migration table

**For Migration Application (`migrate apply`):**
- `CREATE` privilege (for schema changes)
- `INSERT`, `SELECT` on migration table
- Specific permissions for migration operations

### Credential Management

**Environment Variables (Recommended):**
```bash
export POSTGRES_USER=username
export POSTGRES_PASSWORD=password
```

**Command Line (Development Only):**
```bash
bmlibrarian migrate init --user username --password password
```

**Future Enhancements:**
- Support for `.pgpass` files
- Integration with credential management systems
- SSL/TLS connection configuration

## Error Handling Strategy

### Categories

1. **Connection Errors**: Database unavailable, wrong credentials
2. **Permission Errors**: Insufficient database privileges
3. **Migration Errors**: SQL syntax errors, constraint violations
4. **File System Errors**: Missing files, permission issues

### Recovery Mechanisms

**Atomic Transactions (#439):**
- Each migration's SQL and its `bmlibrarian_migrations` record run in one
  transaction on one connection, so a failure leaves neither (before, the SQL
  committed on its own connection and a failed record insert made the
  migration re-run, which failed for good on a non-idempotent file). Any line
  that is only `BEGIN;` or `COMMIT;` is dropped; the runner owns the
  transaction. One connection serves the whole run, so `RESET ALL` follows
  each file's SQL: the pg_dump baseline empties `search_path` for the
  session, which would otherwise reach the record insert and later files.
- One process migrates at a time: the run holds a session advisory lock
  (`MIGRATION_LOCK_KEY`), polled with `pg_try_advisory_lock` every second (a
  waiter blocked in a statement would hold a snapshot that `CREATE INDEX
  CONCURRENTLY` in the holder waits on). Under the lock each pending file is
  checked again, so a second process starting at the same time skips what
  the first applied (before, both applied it and the second failed on
  `UNIQUE(filename)`). With nothing pending, no lock is taken. A failure to
  take the lock (lost connection, or held for
  `MIGRATION_LOCK_TIMEOUT_SECONDS`) is a `MigrationError`, so startup stops
  instead of carrying on with pending migrations.
- `CREATE [UNIQUE] INDEX CONCURRENTLY` statements can't run in a transaction;
  they run after the rest of the file has committed. An INVALID index left by
  an earlier failed build is dropped first (`IF NOT EXISTS` would skip it),
  each index must be valid afterwards, and only then is the migration
  recorded. Such a statement must name its index, checked before any of the
  file runs. The rest of that file runs again on a retry, so it must be
  idempotent.
- Tests: `tests/test_migrations.py` (mocked), `tests/test_migrations_live.py`
  (a scratch database; four contending runs, a failed record rolling back,
  an INVALID index rebuilt).

**Failed auto-migration is fatal (#342):**
- `DatabaseManager` (auto-migrate on) applies pending migrations when it is
  created. A migration that fails while being applied raises
  `bmlibrarian.migrations.MigrationError` (a `RuntimeError`); the manager
  closes its pool and re-raises, so nothing runs against an outdated schema
  (before, this was a log warning and writes failed later at runtime).
- A pending file that cannot be read, applied or recorded raises
  `MigrationError`. Being unable to *check* (no migrations directory, no
  `MigrationManager`, the tracking table neither creatable nor readable) is
  not fatal (debug log or printed warning). If only creating the tracking
  table fails (a role without CREATE on the schema) but it can be read,
  pending migrations are still applied.
- The Qt app and the standalone windows check right after startup with
  `gui/qt/core/schema_check.check_schema_current()`: the main app
  (`BMLibrarianApplication._check_schema_current`, after login),
  `standalone.run_plugin_standalone` / `run_widget_standalone` (the
  Query/PICO/PRISMA/Study labs and `fact_checker_review_gui.py`, which
  skips the check with `--db-file`), `systematic_review_gui.py`,
  `audit_validation_gui.py`, `scripts/pdf_verification_gui.py`,
  `scripts/pdflab.py` and the Paper Weight / Paper Checker / Paper
  Reviewer / Transparency / PubMed Search labs. On `MigrationError` they
  show "Database Migration Failed" and exit with status 1; other manager
  errors (no credentials, server down) are left to the widgets (#378).
  Whenever the startup check lets the window start, it also registers a
  handler with `database.set_migration_failure_handler()`. That matters
  when the check could not create the manager (no credentials, server
  down): when a later `get_db_manager()` (usually on a worker thread)
  first hits a `MigrationError`, the handler queues the same dialog onto
  the GUI thread, closes the windows (so `closeEvent` cleanup runs) and
  ends the event loop with exit code 1 (#381). In the Qt apps, code that
  needs the database uses `get_db_manager()`, not its own
  `DatabaseManager()`, so it shares the remembered failure, and it never
  closes the shared pool (only `close_database()` does, e.g.
  `pubmed_bulk_cli.py` before an import-profile restart).
  `bmlibrarian_cli.py` stops in agent setup with the message. Other CLIs
  should fail at their first database use (not checked per CLI).
- `get_db_manager()` remembers the `MigrationError` and re-raises it on
  every later call without re-running the migration (#379), so code that
  swallows the error and calls again does not retake locks or re-run a slow
  failing DDL. Fix the cause and restart; `close_database()` clears the
  remembered error (one more attempt in-process).

**Idempotent Operations:**
- Safe to retry failed operations
- Use `IF NOT EXISTS` and similar constructs
- Graceful handling of already-applied state

**Detailed Error Messages:**
- Specific error descriptions
- Suggested remediation steps
- Context about what was being attempted

## Testing Strategy

### Unit Tests (`tests/`)

**Coverage Areas:**
- All public methods of MigrationManager
- CLI argument parsing and command execution
- App integration functions
- Error conditions and edge cases

**Testing Approach:**
- Mock database connections for isolation
- Temporary files for filesystem operations
- Comprehensive fixture management
- 98%+ code coverage requirement

**Test Categories:**
```
tests/
├── test_migrations.py    # MigrationManager core logic
├── test_cli.py          # Command-line interface
├── test_app.py          # Application integration
└── conftest.py          # Shared fixtures
```

### Integration Testing

**Database Testing:**
- Real PostgreSQL instances for integration tests
- Test with multiple PostgreSQL versions
- Verify extension compatibility

**End-to-End Testing:**
- Full migration workflows
- CLI command integration
- Error scenario validation

## Performance Considerations

### Migration Performance

**Large Schema Changes:**
- Use `CONCURRENTLY` for index creation
- Batch data modifications
- Consider maintenance windows for major changes

**Connection Management:**
- Connection pooling for high-frequency operations
- Proper connection cleanup
- Timeout configuration

### Scalability

**Migration File Management:**
- Efficient file discovery algorithms
- Checksum caching for large migration sets
- Parallel migration application (future enhancement)

## Extension Points

### Custom Migration Directories

```python
migration_manager.apply_pending_migrations(custom_directory)
```

### Custom Database Configurations

```python
manager = MigrationManager(
    host="custom-host",
    port="5433",
    user="custom-user",
    password="custom-pass",
    database="custom-db"
)
```

### Environment-Specific Configurations

Different configurations for development, testing, and production environments.

## Development Workflow

### Adding New Features

1. **Design**: Document architecture changes
2. **Implementation**: Follow existing patterns
3. **Testing**: Comprehensive unit and integration tests
4. **Documentation**: Update user and developer docs
5. **Review**: Code review process

### Migration Best Practices

**For Developers:**
- Always test migrations on sample data
- Write reversible migrations when possible
- Document complex migration logic
- Use descriptive naming conventions

**Code Review Checklist:**
- [ ] Migration is idempotent
- [ ] Proper error handling
- [ ] Security considerations addressed
- [ ] Tests cover new functionality
- [ ] Documentation updated

## Future Enhancements

### Planned Features

1. **Migration Rollback**: Support for reversing migrations
2. **Parallel Execution**: Concurrent migration application
3. **Advanced Logging**: Structured logging with correlation IDs
4. **Configuration Files**: YAML/TOML configuration support
5. **Migration Templates**: Code generation for common patterns

### Architecture Evolution

**Microservice Support:**
- Service-specific migration directories
- Distributed migration coordination
- Cross-service dependency management

**Cloud Integration:**
- Cloud database service support
- Managed PostgreSQL integration
- Kubernetes deployment patterns

**Monitoring and Observability:**
- Migration performance metrics
- Health check endpoints
- Integration with monitoring systems

## Debugging and Maintenance

### Debugging Tools

**Built-in Diagnostics:**
```python
# Check migration status
manager._get_applied_migrations()

# Verify database connectivity
manager._database_exists("database_name")

# Validate migration files
manager._calculate_checksum(content)
```

**External Tools:**
- PostgreSQL logs for SQL execution details
- Application logs for migration workflow
- Database monitoring for performance analysis

### Maintenance Tasks

**Regular Maintenance:**
- Monitor migration application times
- Review migration file organization
- Update documentation for schema changes
- Backup critical migration files

**Troubleshooting:**
- Check migration table consistency
- Validate file checksums
- Review permission settings
- Analyze connection patterns

This architecture provides a solid foundation for reliable database schema management while maintaining flexibility for future enhancements.