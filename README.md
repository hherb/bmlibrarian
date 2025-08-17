# BMLibrarian

A Python library for accessing and managing biomedical literature databases with PostgreSQL and pgvector extension support.

## Overview

BMLibrarian provides a robust migration system and high-level access to biomedical literature databases. It's designed for researchers and developers who need reliable database schema management and literature data access.

## Features

- **🗄️ Database Migration System**: Automated schema initialization and incremental updates
- **🔧 CLI Tools**: Command-line interface for database management
- **🐍 Python API**: Programmatic access for application integration
- **🛡️ Production-Ready**: Security-conscious design with comprehensive error handling
- **📊 PostgreSQL + pgvector**: Built for PostgreSQL with vector extension support

## Quick Start

### Installation

```bash
pip install bmlibrarian
```

### Prerequisites

- Python 3.12+
- PostgreSQL 12+ with pgvector extension
- Required PostgreSQL extensions: `pgvector`, `pg_trgm`

### Basic Usage

1. **Set up environment variables:**
```bash
export POSTGRES_USER=your_username
export POSTGRES_PASSWORD=your_password
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=bmlibrarian_dev
```

2. **Initialize your database:**
```bash
bmlibrarian migrate init \
    --host localhost \
    --user your_username \
    --password your_password \
    --database bmlibrarian_dev
```

3. **Use in your Python application:**
```python
import bmlibrarian

# Initialize app (auto-applies pending migrations)
bmlibrarian.initialize_app()

# Get database connection
conn = bmlibrarian.get_database_connection()

# Your application logic here
with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM bmlibrarian_migrations")
    print(f"Applied migrations: {cur.fetchone()[0]}")

conn.close()
```

## Migration System

BMLibrarian includes a comprehensive database migration system:

### Initialize New Database
```bash
bmlibrarian migrate init --host localhost --user username --password password --database mydb
```

### Apply Pending Migrations
```bash
bmlibrarian migrate apply --host localhost --user username --password password --database mydb
```

### Custom Migration Directory
```bash
bmlibrarian migrate apply --migrations-dir /path/to/custom/migrations --host localhost --user username --password password --database mydb
```

## Creating Migrations

1. **Create migrations directory:**
```bash
mkdir -p ~/.bmlibrarian/migrations
```

2. **Add migration files:**
```sql
-- ~/.bmlibrarian/migrations/001_add_indexes.sql
CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title);
CREATE INDEX IF NOT EXISTS idx_authors_name ON authors(name);
```

3. **Apply migrations:**
```bash
bmlibrarian migrate apply --host localhost --user username --password password --database mydb
```

## Documentation

Comprehensive documentation is available in the `doc/` directory:

- **[User Guide](doc/users/getting_started.md)** - Installation and basic usage
- **[Migration System](doc/users/migration_system.md)** - Complete migration guide
- **[CLI Reference](doc/users/cli_reference.md)** - Command-line interface documentation
- **[Troubleshooting](doc/users/troubleshooting.md)** - Solutions to common problems
- **[Developer Guide](doc/developers/contributing.md)** - Development and contribution guidelines
- **[API Reference](doc/developers/api_reference.md)** - Complete API documentation

## Configuration

### Environment Variables

```bash
# Required
POSTGRES_USER=your_username
POSTGRES_PASSWORD=your_password

# Optional (with defaults)
POSTGRES_HOST=localhost          # Default: localhost
POSTGRES_PORT=5432              # Default: 5432
POSTGRES_DB=bmlibrarian_dev     # Default: bmlibrarian_dev
PDF_BASE_DIR=~/knowledgebase/pdf # Base directory for PDF files
```

### Using .env Files

Create a `.env` file in your project directory:
```env
POSTGRES_USER=bmlib_user
POSTGRES_PASSWORD=secure_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=bmlibrarian_dev
```

## Development

### Setting Up Development Environment

1. **Clone the repository:**
```bash
git clone <repository-url>
cd bmlibrarian
```

2. **Install development dependencies:**
```bash
uv sync
# or
pip install -e .[dev]
```

3. **Run tests:**
```bash
uv run pytest tests/
# or
pytest tests/
```

### Running Tests

```bash
# Run all tests with coverage
uv run pytest tests/ --cov=src/bmlibrarian

# Run specific test file
uv run pytest tests/test_migrations.py

# Run without integration tests
uv run pytest tests/ -m "not integration"
```

Current test coverage: **98.43%**

## Security

- **Credentials**: Never hardcode passwords; use environment variables
- **Permissions**: Use database accounts with minimal required privileges
- **SSL**: Use secure connections in production environments
- **Validation**: All inputs are validated and sanitized

## Contributing

We welcome contributions! Please see our [Contributing Guide](doc/developers/contributing.md) for details on:

- Development setup
- Code style guidelines
- Testing requirements
- Pull request process

## License

[License information to be added]

## Support

- **Documentation**: Check the [doc/](doc/) directory for comprehensive guides
- **Issues**: Report bugs and feature requests via GitHub issues
- **Questions**: Review the [Troubleshooting Guide](doc/users/troubleshooting.md)

## Changelog

### v0.1.0
- Initial release
- Complete migration system
- CLI interface
- Python API
- Comprehensive documentation
- 98%+ test coverage