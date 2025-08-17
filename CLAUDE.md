# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python library that provides high-level access to a biomedical literature database running in PostgreSQL with pgvector extension support. The project is in early development stages.

## Dependencies and Environment

- **Python**: Requires Python >=3.12
- **Database**: PostgreSQL with pgvector extension
- **Main dependency**: psycopg >=3.2.9 for PostgreSQL connectivity
- **Package manager**: Uses `uv` for dependency management (uv.lock present)

## Configuration

- Environment variables are configured in `.env` file
- Database connection parameters:
  - `POSTGRES_DB`: Database name (default: "knowledgebase")  
  - `POSTGRES_USER`: Database user
  - `POSTGRES_PASSWORD`: Database password
  - `POSTGRES_HOST`: Database host (default: "localhost")
  - `POSTGRES_PORT`: Database port (default: "5432")
- `PDF_BASE_DIR`: Base directory for PDF files (default: "~/knowledgebase/pdf")

## Development Commands

Since this project uses `uv` for package management:
- `uv sync` - Install/sync dependencies
- `uv run python -m [module]` - Run Python modules in the virtual environment

## Architecture

- **Source code**: Located in `src/` directory (currently empty - project in early development)
- **Documentation**: `doc/` directory (currently empty)
- **Database**: PostgreSQL backend with vector extension for biomedical literature storage and retrieval
- **Authentication**: Database authentication handled through environment variables

## Project Structure

```
bmlibrarian/
├── src/              # Main source code (to be developed)
├── doc/              # Documentation
├── pyproject.toml    # Project configuration and dependencies
├── uv.lock          # Locked dependency versions
├── .env             # Environment configuration
└── README.md        # Project description
```

## Development Notes

- This is a new project with minimal source code currently implemented
- The project focuses on biomedical literature database access
- Uses modern Python packaging standards with pyproject.toml
- Designed to work with PostgreSQL's vector extension for advanced search capabilities
- make sure you wil never ever modify or drpop the production database "knowledgebase". If we try migration and want to create a new database, it should e called "bmlibrartian_dev"
- for every new module, write appropriate unit tests in the standard python way as well as documentation suitable for both prgrammers joining the project as well as for end users in the diretories doc/users and doc/developers