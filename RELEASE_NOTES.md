# BMLibrarian v1.0 Release Notes

**Release Date:** 23 December 2025

This major release represents a significant evolution of BMLibrarian, with 923 commits adding approximately 400,000 lines of new code across 1,026 files. This release introduces a comprehensive Systematic Review system, enhanced PDF discovery, LLM backend abstraction, and numerous quality-of-life improvements.

---

## Highlights

### Systematic Review Agent
A comprehensive multi-phase systematic review system aligned with Cochrane methodology:
- **Phase 1-6 implementation** with checkpoint-based resume capability
- **PRISMA 2020 compliance** assessment for systematic reviews
- **Quality assessment caching** with agent versioning
- **Evidence synthesis** with map-reduce pattern for large citation sets
- **Phased search execution** with relevance scoring
- **GUI with tabbed interface** for review management

### Enhanced PDF Discovery System
Intelligent full-text PDF retrieval using multiple legal sources:
- **Multi-source discovery**: PMC, Unpaywall, CrossRef, DOI.org
- **OpenAthens institutional access** via SAML authentication flow
- **Browser fallback** for Cloudflare-protected and anti-bot sites
- **PDF verification** to detect wrong/mismatched downloads
- **DOI fallback** for browser-based downloads when no sources found

### LLM Backend Abstraction Layer
Unified interface for multiple LLM providers:
- **Provider-agnostic API** through `bmlibrarian.llm.LLMClient`
- **Ollama integration** for local inference
- **Anthropic Claude** support for cloud-based processing
- **Seamless provider switching** without code changes

### BMLibrarian Lite
A lightweight standalone version without PostgreSQL dependency is now available as a separate project:
- **Repository**: https://github.com/hherb/bmlibrarian_lite
- ChromaDB + SQLite storage, FastEmbed for embeddings, Anthropic Claude API
- PubMed API search without requiring a local database mirror

---

## New Features

### Data Import & Management
- **Parallel PubMed baseline download/import** with real-time progress tracking
- **PMC Open Access bulk download CLI** for offline work with full-text NXML
- **MeSH vocabulary import system** with local database lookup
- **PubMed API search module** for users without local mirrors
- **medRxiv importer date clamping** to launch date (June 6, 2019)

### GUI Improvements
- **PubMed Search Lab** - Interactive GUI for API search without database storage
- **Paper Weight Assessment Lab** - Evaluate evidential weight of research papers
- **Paper Checker Lab** - Medical abstract fact-checking with step-by-step visualization
- **Audit Validation GUI** - Human review of automated evaluations
- **Document Interrogation tab** - Interactive Q&A with documents
- **Collapsible workflow step cards** with intermediate results display
- **PDF viewer improvements** - Text selection, search, fit-width zoom

### Agents & Analysis
- **PaperCheckerAgent** - Validates medical abstract claims against literature
- **StudyAssessmentAgent** - Evaluates research quality and trustworthiness
- **PRISMA2020Agent** - Assesses systematic review compliance
- **SemanticQueryAgent** - Adaptive semantic search with hybrid RRF
- **Multi-model query generation** - Diverse queries from multiple LLMs

### Developer Experience
- **Cross-platform font support** - Eliminates macOS font warnings
- **Centralized `list_ollama_models()` utility** for consistent model access
- **DPI-aware scaling system** for high-resolution displays
- **Stylesheet generator** for consistent theming
- **Document Card Factory** - Unified document card creation pattern

---

## Improvements

### Performance
- **6.3x speedup** in adaptive text chunking
- **Optimized N+1 query patterns** in paper assessment
- **Regex compilation caching** for filtering
- **Session validation caching** for OpenAthens (configurable TTL)
- **ID-only queries** for faster document retrieval

### Reliability
- **FTP download resilience** for PubMed bulk importer
- **Retry logic with exponential backoff** for embedding generation
- **Jitter in retry delays** to prevent thundering herd effects
- **Gzip magic byte validation** before tar extraction
- **Corrupted PMC package recovery**

### Security
- **JSON serialization** for OpenAthens sessions (replaces pickle)
- **600 file permissions** for session files
- **HTTPS enforcement** for institutional URLs
- **Cookie pattern matching** for SAML/Shibboleth authentication

---

## Bug Fixes

### Critical Fixes
- Fixed Ollama `list_models()` for library version >= 0.4.0
- Fixed HTTP 414 errors for long PubMed queries (now uses POST)
- Fixed PMC resolver returning wrong PDFs from citing articles
- Fixed RuntimeError when Qt widgets deleted during PDF discovery
- Fixed report generation and citation display in Qt workflow
- Fixed embedding type conversion for ChromaDB compatibility
- Fixed PostgreSQL type casting for evaluation functions

### UI Fixes
- Fixed PDF viewer not displaying downloaded PDFs
- Fixed citation links opening wrong PDFs
- Fixed DPI scale key names across lab GUIs
- Fixed validation status not updating after save
- Fixed QThread crash on application close

### Data Integrity
- Fixed premature auth detection in OpenAthens
- Fixed PDF mismatch detection and verification
- Fixed checkpoint resume for systematic reviews
- Fixed datetime serialization for evaluation data

---

## Breaking Changes

- **LLM communication**: All model interactions should now use the LLM abstraction layer (`bmlibrarian.llm.LLMClient`) instead of direct Ollama calls
- **Configuration**: Some configuration keys have been reorganized for consistency
- **Database schema**: New migrations required for systematic review and quality assessment features

---

## Migration Guide

1. **Update dependencies**: `uv sync`
2. **Run database migrations**: Migrations are now auto-applied by DatabaseManager
3. **Update configuration**: Review `~/.bmlibrarian/config.json` for new options

---

## Statistics

- **Commits**: 923
- **Files changed**: 1,026
- **Lines added**: ~400,000
- **Lines removed**: ~9,500
- **Contributors**: Horst Herb, Claude (AI pair programmer)

---

## Documentation

Comprehensive documentation has been added:
- User guides in `doc/users/` for all new features
- Developer documentation in `doc/developers/`
- Wiki pages for plugin development and user guides
- Architecture essays for complex systems (PDF discovery, hybrid search, etc.)

---

## Acknowledgments

This release represents a significant collaborative effort between human expertise and AI assistance. Special thanks to the medical research community for feedback and feature requests that shaped this release.

---

## What's Next

- Enhanced cloud provider support (OpenAI, Google)
- Improved citation network analysis
- Real-time collaborative review features
- Mobile-friendly web interface
