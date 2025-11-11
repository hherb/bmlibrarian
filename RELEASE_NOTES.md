# BMLibrarian Release Notes

## Version 0.9.0 (2025-01-XX)

This major release introduces the **Fact-Checker System** for LLM training data auditing, **HyDE (Hypothetical Document Embeddings) search**, and significant enhancements to the GUI applications and database infrastructure.

### 🎉 Major New Features

#### Fact-Checker System for LLM Training Data Auditing
A comprehensive new system for evaluating biomedical statements against literature evidence:

- **FactCheckerAgent**: New AI agent that evaluates biomedical statements with yes/no/maybe verdicts based on literature evidence (#7, #9)
- **Fact-Checker CLI**: Command-line interface for batch processing of biomedical statements
  ```bash
  uv run python fact_checker_cli.py input.json -o results.json
  ```
- **Fact-Checker Review GUI**: Human review and annotation interface with expandable citation cards (fdb50a5)
  - Statement-by-statement review workflow
  - Side-by-side comparison of original, AI, and human annotations
  - Full abstract display with evidence highlighting
  - Export capabilities for reviewed annotations
- **SQLite Database Integration**: Persistent storage for fact-checking results with intelligent JSON import (b711d25, 30f06c5)
  - Automatic database creation from JSON files
  - Intelligent merging of new statements without overwriting existing annotations
  - Real-time persistence of all human annotations
- **Incremental Mode**: Intelligent processing of only unannotated statements (0883fac, bc256cf)
  - `--incremental` flag for efficient review workflows
  - Multi-user support with annotator tracking
  - GUI filtering for incremental mode
- **Modular Architecture**: Fact-checker refactored into `bmlibrarian.factchecker` module (f25c3a9)
- **Real-Time Progress Analysis**: Live tracking of fact-checking progress during batch operations (bd023c2)
- **Comprehensive Documentation**:
  - User guide: `doc/users/fact_checker_guide.md`
  - User guide: `doc/users/fact_checker_review_guide.md`
  - Developer docs: `doc/developers/fact_checker_system.md`
  - Workflow examples: `examples/fact_checker_demo.py`

#### HyDE (Hypothetical Document Embeddings) Search
Advanced search capability using hypothetical document generation:

- **HyDE Search Implementation**: Generate hypothetical relevant documents to improve semantic search (#6, 03d2a41)
  - Converts research questions into hypothetical document embeddings
  - Significantly improves recall for complex biomedical queries
  - Integrates seamlessly with existing semantic search infrastructure
- **Code Quality Improvements**: Comprehensive code review fixes and design guideline compliance (#8, fe91d07)
- **Documentation**: Complete HyDE search documentation with usage examples (983f536)
- **PostgreSQL Integration**: Semantic document search convenience function (8a17bb9)
  - Extends `semantic_search` with document metadata
  - Optimized for performance with pgvector

#### Enhanced Search Infrastructure
Major improvements to search capabilities and database functions:

- **PostgreSQL Search Functions**: New database-level search functions for improved performance (bc0706e)
  - BM25 full-text search implementation
  - Semantic search with vector embeddings
  - Unified search interface
- **Hybrid Search Orchestration**: Combines multiple search strategies with full audit trail (45cf66a, 21e215f)
  - `search_hybrid()` function for multi-strategy search
  - Methodology metadata tracking for reproducibility
- **Iterative Search with Query Broadening**: Automatic query refinement when initial results are insufficient (868b9c3)
- **Full-Text Search Function**: New `fulltext_search` database function (f386dc4)

### 🎨 GUI Enhancements

#### Fact-Checker Review GUI Improvements
- **Database Integration**: Seamless SQLite database workflow with JSON import (4cbb878)
- **Dropdown Display Fixes**: Resolved display issues with evaluation dropdowns (4cbb878)
- **Expandable Citation Cards**: Full abstract display with evidence highlighting (ba73479)
  - Color-coded stance indicators
  - Relevance score display
  - Evidence enrichment
- **macOS Compatibility**: Command-line file input workaround for Flet FilePicker bug (f624968)

#### Research GUI Improvements
- **Rejected Citations Display**: Comprehensive audit trail showing rejected citations with reasoning (b6aea7e)
  - Full transparency into citation validation process
  - User override capability for expert review
- **Text Clipping Fixes**: Ensure full title and abstract display without truncation (807305b, a7f43d8)
- **Search Strategy Configuration**: New comprehensive tab for search strategy settings (b5aca58)

#### Configuration GUI Enhancements
- **Settings Integration**: Configuration now fully integrated into main application (600c2f0)
- **UI Overhaul**: Comprehensive redesign of settings and configuration interface (600c2f0)
- **Multi-Model Query Configuration**: Dedicated GUI tab for multi-model query generation (6d31aba)

### 🔧 Technical Improvements

#### Database and Infrastructure
- **Database Function Integration**: Complete integration of PostgreSQL search functions (#5, ec66b00)
- **Search Strategy Infrastructure**: Methodology metadata and database function support (813d879)
- **Configuration System**: Fixed hybrid search configuration reading (282676e)
- **Source IDs Access**: Corrected source_ids handling in search functions (71bd84e)

#### Code Quality and Reliability
- **Code Review Improvements**: Multiple rounds of code review and refinements (1c9130f, 93d5e64)
- **Serialization Fixes**: Resolved datetime and scoring result JSON export bugs (ee7d957)
- **Reference Formatting**: Improved reference formatting in generated reports (f386dc4)

#### Performance and Optimization
- **Indexing Experiments**: Various indexing strategies for embedding-based semantic searches (9904a51)
- **Abstract Display**: Removed artificial truncation from display code (a7f43d8)
- **Efficient Batch Processing**: Improved fact-checker batch processing with progress tracking

### 📚 Documentation

#### New Documentation
- **Fact-Checker User Guide**: Complete guide for using the fact-checker system
- **Fact-Checker Review Guide**: Human review and annotation workflow guide
- **Fact-Checker System Documentation**: Technical architecture and developer guide
- **HyDE Search Documentation**: Comprehensive guide with usage examples (983f536)

#### Updated Documentation
- **README**: Updated to reflect current development status and major features (a4fb131)
- **Configuration Guides**: Enhanced with new search and fact-checker settings
- **API Documentation**: Expanded agent module documentation

### 🐛 Bug Fixes

- **Fact-Checker GUI**: Fixed database integration and dropdown display issues (4cbb878)
- **Flet FilePicker**: Workaround for macOS file picker bug with command-line input (f624968)
- **Text Display**: Fixed text clipping in Flet GUI components (807305b)
- **Configuration Reading**: Fixed hybrid search config section access (282676e)
- **Source IDs**: Corrected source_ids access in search functions (71bd84e)
- **JSON Export**: Fixed serialization of datetime objects and scoring results (ee7d957)

### 🔄 Refactoring and Code Organization

- **Fact-Checker Modularization**: Moved fact-checker code to dedicated `bmlibrarian.factchecker` module (f25c3a9)
- **Code Cleanup**: Various code quality improvements and cleanup (f386dc4)
- **Design Guideline Compliance**: HyDE implementation updated to follow project guidelines (3470176)

### 📦 Dependencies

No major dependency changes in this release. Continues to use:
- Python ≥3.12
- PostgreSQL with pgvector extension
- Ollama for local LLM inference
- Flet ≥0.24.1 for GUI applications

### 🔄 Migration Notes

#### Fact-Checker Database
- New SQLite database format for fact-checking results
- Automatic migration from JSON to database format
- Backward compatible with existing JSON files

#### PostgreSQL Functions
- New search functions added to database
- Automatic function creation on first use
- No manual migration required

### 📋 Pull Requests Merged

- #11: Implement incremental mode filtering in fact checker GUI
- #10: Refactor fact checker into bmlibrarian.factchecker module
- #9: Fact-checker implementation with review GUI and database support
- #8: HyDE code review fixes
- #7: Add FactCheckerAgent for LLM training data auditing
- #6: Implement HyDE (Hypothetical Document Embeddings) search
- #5: Integrate PostgreSQL search functions

### 🎯 Breaking Changes

None. This release maintains full backward compatibility with existing workflows and configurations.

### 🔜 What's Next (Future Roadmap)

- Multi-model query generation enhancements
- PostgreSQL audit trail system for research workflows
- Query performance tracking and optimization
- Database migration system with automatic startup
- Additional search strategies and hybrid search improvements

### 🙏 Acknowledgments

This release represents significant contributions to the fact-checking capabilities, search infrastructure, and overall system reliability. Special thanks to all contributors and the biomedical research community for feedback and feature requests.

---

## Installation and Upgrade

### New Installation
```bash
git clone <repository-url>
cd bmlibrarian
uv sync
```

### Upgrading from Previous Version
```bash
git pull origin master
uv sync
# Database migrations run automatically on first startup
```

### Testing the Release
```bash
# Test fact-checker
uv run python fact_checker_cli.py examples/input.json -o results.json
uv run python fact_checker_review_gui.py --input-file results.json

# Test HyDE search (via CLI or GUI)
uv run python bmlibrarian_cli.py --quick

# Test GUI applications
uv run python bmlibrarian_research_gui.py
uv run python bmlibrarian_config_gui.py
```

---

For detailed usage instructions, please refer to the documentation in the `doc/` directory.
