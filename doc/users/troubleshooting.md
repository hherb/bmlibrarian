# Troubleshooting Guide

This guide helps you resolve common issues when using BMLibrarian's migration system.

## Database Connection Issues

### "Connection refused" or "Could not connect to server"

**Symptoms:**
```
psycopg.OperationalError: connection to server at "localhost" (127.0.0.1), port 5432 failed: Connection refused
```

**Solutions:**

1. **Check if PostgreSQL is running:**
   ```bash
   # On macOS with Homebrew
   brew services list | grep postgresql
   brew services start postgresql
   
   # On Linux with systemd
   sudo systemctl status postgresql
   sudo systemctl start postgresql
   
   # On Windows
   net start postgresql-x64-13  # Adjust version as needed
   ```

2. **Verify connection parameters:**
   ```bash
   # Test direct connection
   psql -h localhost -p 5432 -U your_username -d postgres
   ```

3. **Check PostgreSQL configuration:**
   - Ensure `postgresql.conf` has `listen_addresses` configured
   - Check `pg_hba.conf` for authentication settings

### "Password authentication failed"

**Symptoms:**
```
psycopg.OperationalError: FATAL: password authentication failed for user "username"
```

**Solutions:**

1. **Verify credentials:**
   ```bash
   # Test with psql
   psql -h localhost -U your_username -d postgres
   ```

2. **Check environment variables:**
   ```bash
   echo $POSTGRES_USER
   echo $POSTGRES_PASSWORD
   ```

3. **Reset password if needed:**
   ```sql
   -- Connect as superuser and reset password
   ALTER USER your_username PASSWORD 'new_password';
   ```

### "Database does not exist"

**Symptoms:**
```
psycopg.OperationalError: FATAL: database "bmlibrarian_dev" does not exist
```

**Solutions:**

1. **For first-time setup:** Use `migrate init` instead of `migrate apply`
2. **Check database name:** Verify spelling and case sensitivity
3. **Create database manually:**
   ```sql
   CREATE DATABASE bmlibrarian_dev;
   ```

## Permission Issues

### "Permission denied to create database"

**Symptoms:**
```
psycopg.errors.InsufficientPrivilege: permission denied to create database
```

**Solutions:**

1. **Grant CREATEDB privilege:**
   ```sql
   -- Connect as superuser
   ALTER USER your_username CREATEDB;
   ```

2. **Use a superuser account for initial setup:**
   ```bash
   bmlibrarian migrate init --user postgres --password admin_password --database bmlibrarian_dev
   ```

3. **Create database with appropriate owner:**
   ```sql
   CREATE DATABASE bmlibrarian_dev OWNER your_username;
   ```

### "Permission denied for table"

**Symptoms:**
```
psycopg.errors.InsufficientPrivilege: permission denied for table bmlibrarian_migrations
```

**Solutions:**

1. **Grant necessary permissions:**
   ```sql
   GRANT ALL PRIVILEGES ON DATABASE bmlibrarian_dev TO your_username;
   GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_username;
   GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO your_username;
   ```

2. **Check table ownership:**
   ```sql
   SELECT tableowner FROM pg_tables WHERE tablename = 'bmlibrarian_migrations';
   ```

## Migration Issues

### "Migration file not found"

**Symptoms:**
```
Error: baseline_schema.sql not found. Please specify --baseline-schema
```

**Solutions:**

1. **Specify baseline schema explicitly:**
   ```bash
   bmlibrarian migrate init --baseline-schema /path/to/baseline_schema.sql ...
   ```

2. **Check file location:** Ensure `baseline_schema.sql` is in the project root

3. **Use absolute path:**
   ```bash
   bmlibrarian migrate init --baseline-schema "$(pwd)/baseline_schema.sql" ...
   ```

### "Migration already applied"

**Symptoms:**
```
Baseline schema has already been applied.
```

**Solutions:**

This is normal behavior. The migration system tracks applied migrations to prevent duplicate application.

1. **Check applied migrations:**
   ```sql
   SELECT * FROM bmlibrarian_migrations ORDER BY applied_at;
   ```

2. **To reapply (dangerous):**
   ```sql
   -- Only if you know what you're doing
   DELETE FROM bmlibrarian_migrations WHERE filename = 'baseline_schema.sql';
   ```

### "SQL syntax error in migration"

**Symptoms:**
```
psycopg.errors.SyntaxError: syntax error at or near "INVALID"
```

**Solutions:**

1. **Review migration file:** Check SQL syntax carefully
2. **Test migration separately:**
   ```bash
   psql -d bmlibrarian_dev -f ~/.bmlibrarian/migrations/001_problematic.sql
   ```

3. **Fix and rename migration:**
   ```bash
   # Fix the SQL file
   mv 001_problematic.sql 001_fixed_migration.sql
   ```

### "Checksum mismatch"

**Symptoms:**
Migration was modified after being applied.

**Solutions:**

1. **Don't modify applied migrations** - create a new one instead
2. **Create corrective migration:**
   ```sql
   -- In 002_fix_previous_migration.sql
   -- Add corrective statements here
   ```

## Environment Issues

### "Environment variable not set"

**Symptoms:**
```
ValueError: Database credentials not configured. Please set POSTGRES_USER and POSTGRES_PASSWORD environment variables.
```

**Solutions:**

1. **Set required environment variables:**
   ```bash
   export POSTGRES_USER=your_username
   export POSTGRES_PASSWORD=your_password
   export POSTGRES_HOST=localhost
   export POSTGRES_PORT=5432
   export POSTGRES_DB=bmlibrarian_dev
   ```

2. **Use .env file:**
   ```bash
   # Create .env file
   cat > .env << EOF
   POSTGRES_USER=your_username
   POSTGRES_PASSWORD=your_password
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_DB=bmlibrarian_dev
   EOF
   ```

3. **Specify parameters explicitly:**
   ```bash
   bmlibrarian migrate apply --host localhost --user username --password password --database dbname
   ```

## Installation Issues

### "Command not found: bmlibrarian"

**Symptoms:**
```bash
bmlibrarian: command not found
```

**Solutions:**

1. **Install BMLibrarian:**
   ```bash
   pip install bmlibrarian
   ```

2. **Check PATH:**
   ```bash
   pip show bmlibrarian
   which bmlibrarian
   ```

3. **Use full path:**
   ```bash
   python -m bmlibrarian.cli migrate --help
   ```

4. **Activate virtual environment:**
   ```bash
   source venv/bin/activate  # or your venv path
   bmlibrarian --help
   ```

### "Module not found" errors

**Symptoms:**
```
ModuleNotFoundError: No module named 'psycopg'
```

**Solutions:**

1. **Install missing dependencies:**
   ```bash
   pip install psycopg[binary]
   ```

2. **Reinstall BMLibrarian:**
   ```bash
   pip uninstall bmlibrarian
   pip install bmlibrarian
   ```

3. **Check virtual environment:**
   ```bash
   pip list | grep bmlibrarian
   pip list | grep psycopg
   ```

## Extension Issues

### "Extension does not exist"

**Symptoms:**
```
psycopg.errors.UndefinedObject: extension "pgvector" does not exist
```

**Solutions:**

1. **Install required PostgreSQL extensions:**
   ```bash
   # On Ubuntu/Debian
   sudo apt-get install postgresql-contrib postgresql-14-pgvector
   
   # On macOS with Homebrew
   brew install pgvector
   
   # On CentOS/RHEL
   sudo yum install postgresql-contrib
   ```

2. **Enable extensions manually:**
   ```sql
   -- Connect as superuser
   CREATE EXTENSION IF NOT EXISTS pgvector;
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   ```

3. **Check available extensions:**
   ```sql
   SELECT * FROM pg_available_extensions WHERE name LIKE '%vector%';
   ```

## Performance Issues

### "Migration taking too long"

**Symptoms:**
Large migrations hang or take excessive time.

**Solutions:**

1. **Check for locks:**
   ```sql
   SELECT * FROM pg_locks WHERE NOT granted;
   ```

2. **Break up large migrations:**
   ```sql
   -- Instead of one large migration, create multiple smaller ones
   -- 001_create_indexes_part1.sql
   -- 002_create_indexes_part2.sql
   ```

3. **Run during maintenance window:**
   - Schedule large migrations during low-traffic periods
   - Consider using `CONCURRENTLY` for index creation

## Debugging Tips

### Enable Verbose Logging

1. **PostgreSQL logging:**
   ```sql
   -- In postgresql.conf
   log_statement = 'all'
   log_min_duration_statement = 0
   ```

2. **Python logging:**
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

### Check Migration Status

```sql
-- See all applied migrations
SELECT filename, applied_at FROM bmlibrarian_migrations ORDER BY applied_at;

-- Check migration table structure
\d bmlibrarian_migrations

-- See database size
SELECT pg_size_pretty(pg_database_size('bmlibrarian_dev'));
```

### Manual Recovery

If the migration system gets into a bad state:

1. **Backup your data:**
   ```bash
   pg_dump bmlibrarian_dev > backup.sql
   ```

2. **Reset migration state:**
   ```sql
   -- DANGER: Only if you know what you're doing
   DROP TABLE IF EXISTS bmlibrarian_migrations;
   ```

3. **Reinitialize:**
   ```bash
   bmlibrarian migrate init --database bmlibrarian_dev ...
   ```

## Getting Further Help

If these solutions don't resolve your issue:

1. **Check the logs:** Look for detailed error messages
2. **Verify your setup:** Ensure all prerequisites are met
3. **Test with minimal configuration:** Try with a fresh database
4. **Check documentation:** Review the relevant documentation sections
5. **Create a test case:** Try to reproduce with minimal example

### Useful Commands for Debugging

```bash
# Check PostgreSQL version
psql --version

# Check BMLibrarian version
python -c "import bmlibrarian; print(bmlibrarian.__version__)"

# Test database connection
psql -h localhost -U username -d database_name -c "SELECT version();"

# Check Python environment
pip list | grep -E "(bmlibrarian|psycopg)"

# List migration files
ls -la ~/.bmlibrarian/migrations/
```