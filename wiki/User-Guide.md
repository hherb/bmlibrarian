# BMLibrarian User Guide

**Complete guide to using BMLibrarian for biomedical literature research**

## Table of Contents

1. [Introduction](#introduction)
2. [Research Workflow](#research-workflow)
3. [Qt GUI Application](#qt-gui-application)
4. [Command-Line Interface](#command-line-interface)
5. [Fact Checker](#fact-checker)
6. [Advanced Features](#advanced-features)
7. [Best Practices](#best-practices)

## Introduction

BMLibrarian helps researchers interact with biomedical literature through AI-powered natural language processing. The system employs multiple specialized AI agents that work together to convert research questions into comprehensive, evidence-based reports.

### What BMLibrarian Does

1. **Converts natural language questions** to database queries
2. **Searches millions of documents** (PubMed, medRxiv)
3. **Scores documents** for relevance to your question
4. **Extracts specific citations** that answer your question
5. **Generates comprehensive reports** with proper references
6. **Finds contradictory evidence** for balanced analysis
7. **Validates biomedical statements** against literature

## Research Workflow

The typical research workflow in BMLibrarian:

### Step 1: Research Question

Formulate your research question in natural language:

**Examples:**
- "What are the cardiovascular benefits of regular exercise?"
- "Is aspirin effective for preventing heart attacks?"
- "What are the side effects of metformin in type 2 diabetes?"
- "How does sleep deprivation affect cognitive performance?"

### Step 2: Query Generation

BMLibrarian's **QueryAgent** converts your question to a PostgreSQL full-text search query:

```sql
SELECT * FROM find_abstracts(
    ts_query_str := 'cardiovascular & exercise & (benefit | effect)',
    max_rows := 100,
    use_pubmed := true,
    use_medrxiv := true,
    plain := false
);
```

You can review and edit the query before execution.

### Step 3: Document Retrieval

Search the database for relevant documents. Results include:
- Title
- Authors
- Publication date
- Abstract
- Source (PubMed, medRxiv)
- PMID/DOI

### Step 4: Relevance Scoring

**DocumentScoringAgent** evaluates each document (1-5 scale):

- **5**: Highly relevant, directly answers the question
- **4**: Very relevant, strong connection to question
- **3**: Moderately relevant, some useful information
- **2**: Marginally relevant, tangential connection
- **1**: Not relevant, off-topic

**Default threshold**: 2.5 (documents scoring ≥2.5 proceed to citation extraction)

### Step 5: Citation Extraction

**CitationFinderAgent** extracts specific passages that answer your question:

```
Study found that regular aerobic exercise reduced cardiovascular
disease risk by 30% in adults aged 40-65 (Smith et al. 2023).
```

Each citation includes:
- Relevant passage
- Document metadata
- Document ID (validated against database)

### Step 6: Report Generation

**ReportingAgent** synthesizes citations into a comprehensive medical report:

```markdown
# Cardiovascular Benefits of Regular Exercise

## Introduction
Regular physical exercise has been extensively studied for its
effects on cardiovascular health...

## Evidence from Literature

### Reduced Cardiovascular Disease Risk
A 2023 cohort study found that regular aerobic exercise reduced
cardiovascular disease risk by 30% in adults aged 40-65 [1].

### Improved Lipid Profile
Research from 2022 demonstrated that moderate-intensity exercise
improved HDL cholesterol levels by an average of 15mg/dL [2].

## References
1. Smith, J. et al. (2023). "Effects of aerobic exercise..."
   PMID: 12345678
2. Johnson, A. et al. (2022). "Impact of exercise on lipids..."
   PMID: 23456789
```

### Step 7: Counterfactual Analysis (Optional)

**CounterfactualAgent** generates questions to find contradictory evidence:

- "Are there studies showing no cardiovascular benefit from exercise?"
- "When might exercise be harmful for cardiovascular health?"

This ensures balanced reports that acknowledge limitations and alternative viewpoints.

### Step 8: Export

Export your report in Markdown format for use in:
- Publications
- Grant proposals
- Systematic reviews
- Clinical guidelines
- Educational materials

## Qt GUI Application

### Launching the GUI

```bash
uv run python bmlibrarian_qt.py
```

### Main Tabs

#### Research Tab

**Purpose**: Automated literature research workflow

**Features:**
- Multi-line text input for research questions
- Interactive/automated workflow toggle
- Visual workflow progress with step cards
- Real-time agent execution status
- Formatted markdown report preview
- Direct file save functionality

**Workflow:**
1. Enter your research question
2. Click "Start Research" (automated) or follow step-by-step prompts
3. Monitor progress through visual step cards
4. Review generated report
5. Save to file

#### Configuration Tab

**Purpose**: Customize agent behavior and system settings

**Settings:**
- **Agent Models**: Select Ollama models for each agent
- **Parameters**: Adjust temperature, top-p, max tokens
- **Search Settings**: Max results, relevance thresholds
- **Multi-Model Query**: Enable/configure multiple models
- **Ollama Server**: Configure server URL

#### Query Lab Tab

**Purpose**: Interactive query development and testing

**Features:**
- Natural language input
- Generated SQL query display
- Query editing
- Execute and view results
- Export queries

#### PICO Lab Tab

**Purpose**: Extract PICO components for systematic reviews

**PICO Components:**
- **P**opulation: Who was studied?
- **I**ntervention: What was done?
- **C**omparison: Compared to what?
- **O**utcome: What was measured?

**Use Cases:**
- Systematic reviews
- Meta-analyses
- Evidence synthesis
- Clinical question formulation

#### Document Interrogation Tab

**Purpose**: AI-powered Q&A with specific documents

**Features:**
- Load PDF, Markdown, or text files
- Chat interface with dialogue bubbles
- Ask questions about the document
- Get AI-generated answers with context
- Message history

## Command-Line Interface

### Interactive CLI

```bash
uv run python bmlibrarian_cli.py
```

**Interactive Mode:**
- Follow prompts for each workflow step
- Review and edit queries
- Adjust relevance thresholds
- Request more citations
- Iterative refinement

### Automated Mode

```bash
uv run python bmlibrarian_cli.py --auto "What are the benefits of exercise?"
```

**Automated Mode:**
- No user interaction required
- Uses default settings
- Ideal for batch processing
- Returns JSON output

### CLI Options

```bash
# Quick mode (faster, fewer documents)
uv run python bmlibrarian_cli.py --quick

# Custom parameters
uv run python bmlibrarian_cli.py --max-results 50 --score-threshold 3.0

# Timeout configuration
uv run python bmlibrarian_cli.py --timeout 10
```

## Fact Checker

### Purpose

Validate biomedical statements against literature evidence.

**Use Cases:**
- LLM training data auditing
- Medical knowledge validation
- Dataset quality control
- Research claim verification

### Fact Checker CLI

#### Step 1: Create Statements File

Create `statements.json`:

```json
[
  {
    "id": 1,
    "statement": "Aspirin reduces the risk of cardiovascular events.",
    "expected_answer": "yes"
  },
  {
    "id": 2,
    "statement": "Vitamin C prevents the common cold.",
    "expected_answer": "no"
  }
]
```

#### Step 2: Run Fact Checker

```bash
uv run python fact_checker_cli.py statements.json -o results.json
```

This creates:
- `results.json` - JSON output with evaluations
- `results.db` - SQLite database with persistent storage

#### Step 3: Review Results

```bash
# View evaluation summary
cat results.json | jq '.evaluations[] | {statement: .statement, answer: .answer, confidence: .confidence}'

# Launch GUI for detailed review
uv run python fact_checker_review_gui.py --input-file results.db
```

### Fact Checker GUI

**Features:**
- Statement-by-statement navigation
- AI evaluation display (yes/no/maybe)
- Supporting/contradicting citations
- Expandable citation cards with full abstracts
- Human annotation interface
- Blind mode (hide AI evaluations)
- Incremental mode (only unannotated statements)
- Export annotations

**Blind Mode:**
```bash
uv run python fact_checker_review_gui.py --input-file results.db --blind --user alice
```

Hides AI evaluations to prevent bias during human annotation.

**Incremental Mode:**
```bash
uv run python fact_checker_review_gui.py --input-file results.db --incremental --user alice
```

Shows only statements not yet annotated by the user.

### Evaluation Output

Each statement evaluation includes:
- **Answer**: yes/no/maybe
- **Confidence**: high/medium/low
- **Reasoning**: Explanation of evaluation
- **Supporting Citations**: Evidence that supports the statement
- **Contradicting Citations**: Evidence that contradicts the statement
- **Neutral Citations**: Related but neutral evidence

## Advanced Features

### Multi-Model Query Generation

Use multiple AI models to generate diverse queries for better document retrieval.

**Configuration** (`~/.bmlibrarian/config.json`):

```json
{
  "query_generation": {
    "multi_model_enabled": true,
    "models": [
      "medgemma-27b-text-it-Q8_0:latest",
      "gpt-oss:20b",
      "medgemma4B_it_q8:latest"
    ],
    "queries_per_model": 1,
    "show_all_queries_to_user": true,
    "allow_query_selection": true
  }
}
```

**Benefits:**
- 20-40% more relevant documents
- Diverse query perspectives
- Better coverage of research question

**Trade-offs:**
- 2-3x slower than single-model
- More Ollama resource usage

### Query Performance Tracking

BMLibrarian tracks which models and parameters find the best documents:

**Metrics Tracked:**
- Queries generated per model
- Documents found per query
- Unique documents per model
- Overlap between model results
- Average relevance scores

**View Statistics:**

```sql
-- View performance by model
SELECT * FROM audit.v_model_query_performance;

-- View session history
SELECT * FROM audit.v_research_session_summary;
```

### OpenAthens Authentication

Access paywalled PDFs through institutional subscriptions:

**Setup:**

1. Install Playwright:
   ```bash
   uv add playwright
   uv run python -m playwright install chromium
   ```

2. Configure in `~/.bmlibrarian/config.json`:
   ```json
   {
     "openathens": {
       "institution_url": "https://your-institution.openathens.net/login",
       "session_max_age_hours": 24
     }
   }
   ```

3. Authenticate (interactive browser login):
   ```python
   from bmlibrarian.utils.openathens_auth import OpenAthensAuth
   import asyncio

   auth = OpenAthensAuth(config)
   asyncio.run(auth.login_interactive())
   ```

4. Download PDFs with authentication:
   ```python
   from bmlibrarian.utils.pdf_manager import PDFManager

   pdf_manager = PDFManager(openathens_auth=auth)
   pdf_path = pdf_manager.download_pdf(document)
   ```

### PDF Import and Matching

Import local PDFs with automatic metadata extraction and database matching:

```bash
# Import single PDF
uv run python pdf_import_cli.py file /path/to/paper.pdf

# Import directory of PDFs
uv run python pdf_import_cli.py directory /path/to/pdfs/ --recursive

# Dry run (preview without changes)
uv run python pdf_import_cli.py file paper.pdf --dry-run

# View import statistics
uv run python pdf_import_cli.py status
```

**Matching Strategy:**
1. Extract DOI/PMID from PDF metadata or text
2. Search database for exact matches
3. Fall back to title similarity matching
4. LLM-based metadata extraction if needed

### HyDE (Hypothetical Document Embeddings)

Generate hypothetical document embeddings for improved semantic search:

**How it works:**
1. LLM generates a hypothetical abstract answering your question
2. Embed the hypothetical abstract
3. Search for similar real documents

**Benefits:**
- Better semantic matching
- Finds relevant documents with different terminology
- Improved recall for complex queries

**Enable in configuration:**
```json
{
  "search": {
    "use_hyde": true,
    "hyde_model": "gpt-oss:20b"
  }
}
```

## Best Practices

### Writing Research Questions

**Good:**
- Specific and focused
- Includes key terms
- Clear information need

**Examples:**
- ✅ "What are the long-term cardiovascular effects of statins in elderly patients?"
- ✅ "Is mindfulness meditation effective for reducing anxiety in adults?"
- ❌ "Tell me about medicine"
- ❌ "What's good for health?"

### Query Refinement

If search results are poor:

1. **Review generated query** - Check if query captures your intent
2. **Edit query terms** - Add synonyms, remove overly specific terms
3. **Adjust boolean operators** - Use OR for synonyms, AND for required terms
4. **Try multi-model** - Enable multi-model query generation
5. **Use HyDE** - Enable hypothetical document embeddings

### Relevance Threshold

Adjust based on your needs:

- **High precision** (few false positives): Threshold 3.5+
- **Balanced** (default): Threshold 2.5-3.0
- **High recall** (don't miss relevant documents): Threshold 1.5-2.0

### Citation Extraction

Request more citations if report is thin:

```python
# During report generation, agents can request more citations
# if evidence is insufficient

if len(citations) < 10:
    request_more_citations(score_threshold=2.0)  # Lower threshold
```

### Report Quality

For best reports:

1. **Use counterfactual analysis** - Ensures balanced perspective
2. **Request sufficient citations** - Aim for 15-20 citations minimum
3. **Verify document IDs** - BMLibrarian validates all citations
4. **Review references** - Check that citations match your question

### Data Import

For best search results:

1. **Import recent literature** - Keep database updated
   ```bash
   uv run python medrxiv_import_cli.py update --days 30
   ```

2. **Import by topic** - Target relevant literature
   ```bash
   uv run python pubmed_import_cli.py search "your research area" --max-results 50000
   ```

3. **Generate embeddings** - For semantic search
   ```bash
   uv run python embed_documents_cli.py embed --source medrxiv --limit 10000
   ```

## Troubleshooting

### No Documents Found

**Possible causes:**
- Query too specific
- Database empty or limited
- Search terms incorrect

**Solutions:**
- Broaden query (use OR instead of AND)
- Import more documents
- Try different search terms
- Enable multi-model query generation

### Low Relevance Scores

**Possible causes:**
- Question doesn't match literature
- Documents off-topic
- Scoring agent misconfigured

**Solutions:**
- Refine research question
- Review generated query
- Lower relevance threshold
- Try different scoring model

### No Citations Generated

**Possible causes:**
- No high-scoring documents
- Extraction threshold too high
- Documents don't contain direct answers

**Solutions:**
- Lower score threshold
- Lower extraction threshold
- Request more citations
- Broaden search query

### Ollama Connection Failed

**Solution:**
- Ensure Ollama is running: `ollama serve`
- Check configuration: `~/.bmlibrarian/config.json`
- Verify model is pulled: `ollama pull gpt-oss:20b`

### Database Connection Failed

**Solution:**
- Check PostgreSQL is running
- Verify credentials in `.env`
- Test connection: `psql -h localhost -U your_user -d knowledgebase`

## Next Steps

- [Configuration Guide](Configuration-Guide) - Customize BMLibrarian
- [Multi-Model Queries](Multi-Model-Queries) - Use multiple AI models
- [Query Optimization](Query-Optimization) - Improve search results
- [Fact Checker Guide](Fact-Checker-Guide) - Validate biomedical statements

**Need help?** Check [Troubleshooting](Troubleshooting) or ask in [GitHub Discussions](https://github.com/hherb/bmlibrarian/discussions).

---

**Happy Researching!** 🔬📚
