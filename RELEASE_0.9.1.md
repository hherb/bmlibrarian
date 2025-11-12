# BMLibrarian v0.9.1 Release Notes

**Release Date:** November 2024

Version 0.9.1 brings significant infrastructure improvements with the fact-checker PostgreSQL migration, new data import capabilities with MedRxiv integration, and semantic search support through document embeddings.

---

## 🎯 Major Features

### MedRxiv Importer & Document Embeddings (PR #18)

**New Capabilities:**
- **MedRxiv Preprint Importer**: Import biomedical preprints from MedRxiv with metadata and PDF downloads
  - CLI tool: `medrxiv_import_cli.py` for fetching and managing preprints
  - Automatic metadata extraction and database storage
  - Optional PDF download with status tracking
- **Document Embedding Generation**: Generate semantic embeddings for improved search capabilities
  - CLI tool: `embed_documents_cli.py` for batch embedding generation
  - Support for multiple document sources (PubMed, MedRxiv)
  - Integration with existing pgvector infrastructure

**Commands:**
```bash
# Import MedRxiv preprints with PDFs
uv run python medrxiv_import_cli.py update --download-pdfs

# Generate embeddings for semantic search
uv run python embed_documents_cli.py embed --source medrxiv --limit 100

# Check embedding status
uv run python embed_documents_cli.py status
```

**User Documentation:**
- `doc/users/medrxiv_import_guide.md` - MedRxiv import guide
- `doc/users/document_embedding_guide.md` - Document embedding guide

---

### Fact-Checker PostgreSQL Migration (PR #17, #16, #15)

**Infrastructure Upgrade:**
- **Complete PostgreSQL Migration**: Migrated fact-checker system from SQLite to PostgreSQL
  - Improved scalability and multi-user support
  - Better integration with main BMLibrarian database
  - Enhanced query performance for large datasets
- **Migration Tooling**: SQLite to PostgreSQL migration script for existing databases
- **Schema Updates**: New `factcheck` schema in PostgreSQL with comprehensive tables

**Breaking Changes:**
- Fact-checker now uses PostgreSQL instead of SQLite by default
- Database connection configuration required in `.env` file
- Legacy SQLite databases can be migrated using provided migration script

**Migration Guide:**
```bash
# Migrate existing SQLite database to PostgreSQL
python src/bmlibrarian/factchecker/db/migrate_sqlite_to_postgres.py results.db
```

**Updated Documentation:**
- Complete rewrite of fact-checker documentation reflecting PostgreSQL architecture
- `doc/developers/fact_checker_system.md` - Technical architecture
- `doc/users/fact_checker_guide.md` - User guide with PostgreSQL examples

---

## 🚀 Enhancements

### Fact-Checker Review GUI Improvements

**New Features:**
- **Blind Mode**: Hide AI evaluations during human review to prevent annotation bias (PR #12)
  - Enables unbiased human annotation without AI influence
  - Command: `uv run python fact_checker_review_gui.py --blind --user alice`
- **Database-Only Mode**: Simplified GUI focusing on PostgreSQL integration (PR #17)
- **Improved Metadata Display**: Correct document titles and source information (PR #15)
- **Format Compatibility**: Support for both JSON formats in fact-checker (PR #17)

### Citation Quality Improvements

**Bug Fixes:**
- **Citation Hallucination Prevention**: Validation system ensures all citations reference real database documents (PR #14)
- **Removed Hard Limits**: Eliminated artificial citation limits that restricted evidence quality
- **Evidence Field Fixes**: Corrected Evidence dataclass field name in fact_checker_agent.py

---

## 🐛 Bug Fixes

### Fact-Checker Fixes
- Fixed Evidence dataclass field name causing serialization issues (c58581d1)
- Support for both JSON formats with optimized incremental mode (e33e617)
- Complete PostgreSQL migration for review GUI (562e5b9)
- Display correct document titles and metadata in review interface (83c951e)
- Initial bug cleanup after automated code generation (4fc7a23)

### Citation Processing
- Eliminated citation hallucination in FactCheckerAgent with validation system (e1e9c65)
- Removed hard limit on fact-checker citations that restricted evidence (3515683)

---

## 📚 Documentation Updates

### New Documentation
- **MedRxiv Import Guide**: Complete guide for importing biomedical preprints
- **Document Embedding Guide**: Instructions for generating and using semantic embeddings
- **Fact-Checker PostgreSQL Migration**: Updated all fact-checker documentation

### Updated Documentation
- **README**: Comprehensive update with Fact Checker System documentation (PR #14)
- **Fact-Checker System Docs**: Complete rewrite for PostgreSQL architecture (PR #17)

---

## 🔧 Technical Changes

### Database & Infrastructure
- PostgreSQL `factcheck` schema with tables for statements, evidence, evaluations, and annotations
- Migration script for converting legacy SQLite databases
- Enhanced database connection management for fact-checker module

### Module Organization
- `src/bmlibrarian/importers/` - New importer module for external data sources
- `src/bmlibrarian/embeddings/` - Document embedding generation module
- Improved modular architecture for fact-checker components

---

## 📦 New CLI Tools

### MedRxiv Importer
```bash
medrxiv_import_cli.py update [--download-pdfs]    # Import latest preprints
medrxiv_import_cli.py fetch-pdfs [--limit N]      # Download missing PDFs
medrxiv_import_cli.py status                       # Show import statistics
```

### Document Embeddings
```bash
embed_documents_cli.py embed --source SOURCE       # Generate embeddings
embed_documents_cli.py count --source SOURCE       # Count documents needing embeddings
embed_documents_cli.py status                      # Show embedding statistics
```

### Fact-Checker Enhancements
```bash
fact_checker_review_gui.py --blind                 # Blind mode (hide AI annotations)
fact_checker_review_gui.py --user USERNAME         # Track reviewer identity
```

---

## 🔄 Migration Notes

### For Existing Fact-Checker Users

**PostgreSQL Setup Required:**
1. Ensure PostgreSQL is running with pgvector extension
2. Update `.env` file with database credentials:
   ```bash
   POSTGRES_USER=your_username
   POSTGRES_PASSWORD=your_password
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_DB=knowledgebase
   ```

**Migrate Existing SQLite Databases:**
```bash
# Migrate fact-checker data to PostgreSQL
python src/bmlibrarian/factchecker/db/migrate_sqlite_to_postgres.py old_results.db

# Continue using fact-checker with PostgreSQL
uv run python fact_checker_cli.py statements.json
```

---

## 🎓 Use Cases Enabled

### Academic Research
- Import latest MedRxiv preprints for cutting-edge research analysis
- Generate semantic embeddings for similarity-based document discovery
- Track evolving research with periodic MedRxiv updates

### LLM Training Data Auditing
- Blind mode review for unbiased human annotation
- PostgreSQL scalability for large training datasets
- Multi-user annotation tracking for quality control

---

## 🙏 Acknowledgments

This release includes contributions and improvements across multiple areas:
- Infrastructure upgrades for scalability and performance
- New data import capabilities expanding literature coverage
- Enhanced fact-checking workflows with blind review mode
- Comprehensive documentation updates

---

## 📊 Statistics

**Changes since v0.9-alpha:**
- 16 commits with new features and bug fixes
- 3 major pull requests merged
- 2 new CLI tools added
- 2 new documentation guides created
- Complete PostgreSQL migration for fact-checker system

---

## 🔜 What's Next

Looking ahead to future releases:
- Enhanced semantic search capabilities with embeddings
- Additional literature source importers (bioRxiv, etc.)
- Multi-user collaboration features in fact-checker
- Performance optimizations for large-scale document processing

---

## 📖 Getting Started

### Installation
```bash
git clone <repository-url>
cd bmlibrarian
git checkout v0.9.1
uv sync
```

### Quick Start
```bash
# Import MedRxiv preprints
uv run python medrxiv_import_cli.py update --download-pdfs

# Generate embeddings for semantic search
uv run python embed_documents_cli.py embed --source medrxiv --limit 100

# Run fact-checker with blind review
uv run python fact_checker_cli.py statements.json
uv run python fact_checker_review_gui.py --blind --user reviewer1
```

---

**Full Changelog**: https://github.com/hherb/bmlibrarian/compare/v0.9-alpha...v0.9.1
