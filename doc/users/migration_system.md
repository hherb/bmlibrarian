# BMLibrarian Migration System

The BMLibrarian migration system provides a robust way to manage database schema changes over time. It ensures that your database structure stays synchronized with the application requirements and allows for safe upgrades.

## Overview

The migration system consists of:

- **Baseline Schema**: The initial database structure applied when first setting up BMLibrarian
- **Incremental Migrations**: Additional SQL files that modify the database structure
- **Migration Tracking**: A system that tracks which migrations have been applied
- **Automatic Application**: Migrations are automatically applied when starting the application

## How It Works

### 1. Migration Tracking

BMLibrarian creates a `bmlibrarian_migrations` table to track applied migrations:

```sql
CREATE TABLE bmlibrarian_migrations (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL UNIQUE,
    checksum VARCHAR(64) NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. Migration Discovery

The system looks for migration files in `~/.bmlibrarian/migrations/` directory. Migration files must:

- Have a `.sql` extension
- Start with a numeric prefix for ordering (e.g., `001_`, `002_`)
- Follow the naming pattern: `NNN_description.sql`

Example migration files:
```
~/.bmlibrarian/migrations/
├── 001_add_author_indexes.sql
├── 002_create_paper_categories.sql
└── 003_add_fulltext_search.sql
```

### 3. Migration Application

Migrations are applied in numeric order based on their filename prefix. Each migration is:

1. **Checked**: Verified that it hasn't been applied before
2. **Applied**: Executed against the database
3. **Recorded**: Added to the tracking table with a checksum

## Creating Migrations

### 1. Create Migration Directory

If it doesn't exist, create the migrations directory:

```bash
mkdir -p ~/.bmlibrarian/migrations
```

### 2. Create Migration File

Create a new migration file with a sequential number:

```bash
# Example: Adding an index for better performance
cat > ~/.bmlibrarian/migrations/001_add_author_indexes.sql << EOF
-- Add indexes for better author lookup performance

CREATE INDEX IF NOT EXISTS idx_authors_name ON authors(name);
CREATE INDEX IF NOT EXISTS idx_papers_author_id ON papers(author_id);

-- Add a comment for tracking
COMMENT ON INDEX idx_authors_name IS 'Improves author name search performance';
EOF
```

### 3. Apply Migration

Migrations can be applied in two ways:

**Manual Application:**
```bash
bmlibrarian migrate apply \
    --host localhost \
    --user your_username \
    --password your_password \
    --database your_database_name
```

**Automatic Application:**
Migrations are automatically applied when you call `bmlibrarian.initialize_app()` in your Python code.

## Migration Best Practices

### 1. Naming Conventions

- Use descriptive names: `001_add_author_indexes.sql`
- Include the purpose: `002_create_user_preferences_table.sql`
- Keep names concise but clear

### 2. Writing Safe Migrations

Always write migrations that are:

**Idempotent**: Can be run multiple times safely
```sql
-- Good: Uses IF NOT EXISTS
CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title);

-- Bad: Will fail if index already exists
CREATE INDEX idx_papers_title ON papers(title);
```

**Backward Compatible**: Don't break existing functionality
```sql
-- Good: Add new column with default value
ALTER TABLE papers ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'published';

-- Potentially problematic: Removing columns immediately
-- ALTER TABLE papers DROP COLUMN old_column;
```

**Atomic**: Each migration should be a complete unit
```sql
-- Good: Related changes in one migration
BEGIN;
CREATE TABLE paper_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);
ALTER TABLE papers ADD COLUMN category_id INTEGER REFERENCES paper_categories(id);
COMMIT;
```

### 3. Testing Migrations

Before applying to production:

1. Test on a copy of production data
2. Verify the migration runs without errors
3. Check that the application works with the new schema
4. Ensure you can rollback if needed

### 4. Data Migrations

For migrations that modify data, be extra careful:

```sql
-- Example: Safely updating existing data
UPDATE papers 
SET status = 'published' 
WHERE status IS NULL AND created_at < NOW() - INTERVAL '1 day';

-- Add NOT NULL constraint after setting defaults
ALTER TABLE papers ALTER COLUMN status SET NOT NULL;
```

## Migration Commands

### Initialize Database

Set up a new database with the baseline schema:

```bash
bmlibrarian migrate init \
    --host localhost \
    --user username \
    --password password \
    --database database_name \
    [--baseline-schema /path/to/schema.sql]
```

### Apply Pending Migrations

Apply all unapplied migrations:

```bash
bmlibrarian migrate apply \
    --host localhost \
    --user username \
    --password password \
    --database database_name \
    [--migrations-dir /custom/migrations/path]
```

## Troubleshooting

### Migration Failed

If a migration fails:

1. **Check the error message** for specific SQL issues
2. **Fix the migration file** (you may need to increment the number)
3. **Remove the failed migration record** from `bmlibrarian_migrations` if it was partially applied
4. **Re-run the migration**

### Migration Already Applied

If you get "already applied" errors:

```sql
-- Check which migrations are recorded
SELECT * FROM bmlibrarian_migrations ORDER BY filename;

-- Remove a specific migration record if needed (use with caution)
DELETE FROM bmlibrarian_migrations WHERE filename = 'problematic_migration.sql';
```

### Checksum Mismatch

If a migration file was modified after being applied:

1. **Don't modify applied migrations** - create a new migration instead
2. If you must fix an error in an applied migration:
   - Create a new migration to fix the issue
   - Or remove the migration record and re-apply (risky)

## Security Considerations

- **Store credentials securely**: Use environment variables, not hardcoded passwords
- **Limit database permissions**: Use accounts with minimal required privileges
- **Review migrations**: All migrations should be code-reviewed before application
- **Backup before migrations**: Always backup production data before applying migrations

## Advanced Usage

### Custom Migration Directory

You can specify a custom migrations directory:

```bash
bmlibrarian migrate apply --migrations-dir /path/to/custom/migrations
```

### Environment-Based Configuration

Use environment variables for different environments:

```bash
# Development
export POSTGRES_DB=bmlibrarian_dev
bmlibrarian migrate apply --host localhost --user dev_user --password dev_pass --database $POSTGRES_DB

# Production
export POSTGRES_DB=bmlibrarian_prod
bmlibrarian migrate apply --host prod-db --user prod_user --password $PROD_PASSWORD --database $POSTGRES_DB
```