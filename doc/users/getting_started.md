# Getting Started with BMLibrarian

BMLibrarian is a Python library for accessing biomedical literature databases. This guide will help you get started with installing and using the migration system to set up your database.

## Installation

BMLibrarian can be installed using pip:

```bash
pip install bmlibrarian
```

For development, you can install from source:

```bash
git clone <repository-url>
cd bmlibrarian
pip install -e .
```

## Prerequisites

Before using BMLibrarian, you need:

1. **PostgreSQL Database**: BMLibrarian requires PostgreSQL 12 or later
2. **PostgreSQL Extensions**: The following extensions should be available:
   - `pgvector` - For vector operations
   - `pg_trgm` - For text search
   - `plpython3u` - For Python-based functions (optional)

## Environment Configuration

Create a `.env` file in your project directory or set environment variables:

```bash
# Database connection settings
POSTGRES_HOST=localhost          # Database host (default: localhost)
POSTGRES_PORT=5432              # Database port (default: 5432)
POSTGRES_USER=your_username     # Database username (required)
POSTGRES_PASSWORD=your_password # Database password (required)
POSTGRES_DB=bmlibrarian_dev     # Database name (default: bmlibrarian_dev)

# Optional settings
PDF_BASE_DIR=~/knowledgebase/pdf # Base directory for PDF files
```

## Quick Start

### 1. Initialize Your Database

The first step is to initialize your database with the baseline schema:

```bash
bmlibrarian migrate init \
    --host localhost \
    --user your_username \
    --password your_password \
    --database your_database_name
```

This command will:
- Create the database if it doesn't exist
- Apply the baseline schema with all necessary tables and extensions
- Set up the migration tracking system

### 2. Verify Installation

You can verify that the migration system is working by checking for applied migrations:

```bash
bmlibrarian migrate apply \
    --host localhost \
    --user your_username \
    --password your_password \
    --database your_database_name
```

If everything is set up correctly, you should see: "No pending migrations to apply."

### 3. Using BMLibrarian in Your Code

Once your database is initialized, you can use BMLibrarian in your Python code:

```python
import bmlibrarian

# Initialize the application (applies any pending migrations)
bmlibrarian.initialize_app()

# Get a database connection
conn = bmlibrarian.get_database_connection()

# Use the connection for your biomedical literature queries
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM bmlibrarian_migrations")
    print(f"Applied migrations: {cur.fetchone()[0]}")

conn.close()
```

## Next Steps

- Read the [Migration System Guide](migration_system.md) to learn about managing database schema changes
- Check the [CLI Reference](cli_reference.md) for detailed command documentation
- See the [Troubleshooting Guide](troubleshooting.md) if you encounter issues

## Support

If you encounter issues:
1. Check the [Troubleshooting Guide](troubleshooting.md)
2. Review the error messages for specific guidance
3. Ensure your PostgreSQL server is running and accessible
4. Verify your environment variables are set correctly