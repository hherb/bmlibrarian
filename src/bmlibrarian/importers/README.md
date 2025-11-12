# BMLibrarian Importers

This directory contains importers for external biomedical literature sources.

## Available Importers

### MedRxivImporter

Imports biomedical preprints from the [medRxiv](https://www.medrxiv.org) preprint server.

**Features:**
- Fetch metadata from medRxiv API
- Download PDFs
- Extract full text as markdown
- Incremental updates
- Batch processing

**Usage:**

```python
from bmlibrarian.importers import MedRxivImporter

# Initialize importer
importer = MedRxivImporter()

# Update database with recent papers
stats = importer.update_database(
    download_pdfs=True,
    days_to_fetch=30
)

# Download missing PDFs
count = importer.fetch_missing_pdfs(limit=100)
```

**CLI:**

```bash
# Update database
uv run python medrxiv_import_cli.py update --download-pdfs --days-to-fetch 30

# Download missing PDFs
uv run python medrxiv_import_cli.py fetch-pdfs --limit 100

# Check status
uv run python medrxiv_import_cli.py status
```

See [MedRxiv Import Guide](../../../doc/users/medrxiv_import_guide.md) for detailed documentation.

## Future Importers

Planned importers for:
- **PubMed**: Import from NCBI PubMed via E-utilities API
- **bioRxiv**: General biology preprints
- **arXiv**: Physics, mathematics, and computer science preprints (q-bio section)
- **ClinicalTrials.gov**: Clinical trial data
- **PubMed Central**: Full-text articles from PMC

## Architecture

All importers follow a common pattern:

1. **Initialization**: Connect to database, set up storage directories
2. **Metadata Fetching**: Query external API for paper metadata
3. **PDF Download**: Download full-text PDFs when available
4. **Text Extraction**: Convert PDFs to searchable markdown
5. **Database Storage**: Store in BMLibrarian's unified `document` table

All importers use:
- `bmlibrarian.database.DatabaseManager` for database operations
- Connection pooling for efficient database access
- Proper error handling and retry logic
- Progress tracking with tqdm
- Logging for observability

## Adding New Importers

To add a new importer:

1. Create a new module in this directory (e.g., `pubmed_importer.py`)
2. Implement a class following the pattern:

```python
from bmlibrarian.database import get_db_manager
import logging

logger = logging.getLogger(__name__)

class YourImporter:
    def __init__(self):
        self.db_manager = get_db_manager()
        self.source_id = self._get_source_id('your_source')

    def _get_source_id(self, source_name: str):
        # Get or create source ID
        pass

    def fetch_metadata(self, **kwargs):
        # Fetch from external API
        pass

    def update_database(self, **kwargs):
        # Main update function
        pass
```

3. Add to `__init__.py`:
```python
from .your_importer import YourImporter
__all__ = ['MedRxivImporter', 'YourImporter']
```

4. Create a CLI script (e.g., `your_source_import_cli.py`)
5. Add documentation to `doc/users/`
6. Add tests to `tests/`

## Database Integration

All importers store documents in the unified `document` table with:

**Required fields:**
- `source_id`: Foreign key to `sources` table
- `external_id`: External identifier (DOI, PMID, etc.)
- `title`: Paper title
- `abstract`: Paper abstract

**Optional fields:**
- `doi`: Digital Object Identifier
- `authors`: Array of author names
- `publication`: Journal/venue name
- `publication_date`: Publication date
- `url`: Paper URL
- `pdf_url`: PDF download URL
- `pdf_filename`: Local PDF filename
- `full_text`: Extracted full text (markdown)
- `keywords`, `mesh_terms`: Metadata arrays

The `search_vector` field is automatically generated from `title` and `abstract` for full-text search.

## Dependencies

Common dependencies for importers:

```toml
[project.optional-dependencies]
importers = [
    "requests>=2.31.0",      # HTTP requests
    "pymupdf4llm>=0.0.3",    # PDF to markdown
    "tqdm>=4.65.0",          # Progress bars
    "beautifulsoup4>=4.12.0", # HTML parsing
]
```

Install with:
```bash
uv pip install requests pymupdf4llm tqdm beautifulsoup4
```
