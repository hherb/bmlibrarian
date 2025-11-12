# Fact-Checker Review GUI User Guide

## Overview

The Fact-Checker Review GUI is a desktop application for human reviewers to annotate and validate AI-generated fact-checking results. Built with the Flet framework, it provides an intuitive interface for reviewing biomedical statements, their AI evaluations, and supporting evidence **directly from PostgreSQL**.

**New in v2.0**: Simplified database-only architecture - all data stored in PostgreSQL factcheck schema with no intermediate files.

## Features

- **PostgreSQL Integration**: Direct connection to factcheck schema for real-time data access
- **Multi-User Support**: Username tracking for human annotations with annotator profiles
- **Statement-by-Statement Review**: Navigate through statements with clear progress tracking
- **Annotation Comparison**: View original annotations, AI evaluations, and provide human annotations side-by-side
- **Evidence Review**: Examine supporting citations with stance indicators and full abstracts
- **Incremental Mode**: Filter to show only statements you haven't annotated yet
- **Blind Mode**: Hide original and AI annotations for unbiased human review
- **Real-Time Persistence**: All annotations saved directly to PostgreSQL as you review
- **Export Options**: Export annotations to JSON for analysis and reporting

## Getting Started

### Prerequisites

- Python ≥3.12
- BMLibrarian installed with GUI dependencies
- PostgreSQL with factcheck schema initialized
- Flet framework (automatically installed with BMLibrarian)

### Installation

The Fact-Checker Review GUI is included with BMLibrarian. No additional installation is required.

### Running the Application

```bash
# Start the Fact-Checker Review GUI (with login)
uv run python fact_checker_review_gui.py

# Skip login dialog with username
uv run python fact_checker_review_gui.py --user alice

# Incremental mode: only show statements you haven't annotated yet
uv run python fact_checker_review_gui.py --user alice --incremental

# Blind mode: hide AI and original annotations for unbiased review
uv run python fact_checker_review_gui.py --user bob --blind
```

The application will open in a desktop window and prompt you to log in (unless `--user` is specified).

### Command-Line Options

- `--user USERNAME`: Skip login dialog and use specified username
- `--incremental`: Filter to show only statements without your annotations
- `--blind`: Hide original and AI annotations from human annotator (unbiased mode)

## Using the Review Interface

### 1. Login and User Profile

Upon launch, you'll see a login dialog:

**Login Dialog:**
- **Username**: Required (used for annotation tracking)
- **Full Name**: Optional (display name)
- **Email**: Optional (contact information)
- **Expertise Level**: Optional (expert/intermediate/novice)
- **Institution**: Optional (affiliation)

Your profile is stored in the `factcheck.annotators` table and can be updated on subsequent logins.

### 2. Main Review Interface

The review interface displays:

#### Progress Section
- **Statement counter**: Shows current position (e.g., "Statement 1 of 50")
- **Progress bar**: Visual indicator of completion
- **User info**: Displays your username and mode (incremental/blind if active)

#### Statement Section
- The biomedical statement being fact-checked
- Statement ID and source information

#### Annotations Section (3 Columns)

**Column 1 - Original Annotation**
- Shows the original yes/no/maybe annotation from the input
- Purple badge displays the expected answer
- May show "N/A" if no original annotation was provided
- **Hidden in blind mode**

**Column 2 - AI Fact-Checker**
- Shows the AI's evaluation (yes/no/maybe)
- Blue badge displays the AI's decision
- **AI Rationale**: Detailed explanation of the AI's reasoning
- **Metadata**: Documents reviewed, citation counts, confidence level
- **Hidden in blind mode**

**Column 3 - Human Review**
- **Your Annotation**: Dropdown to select yes/no/maybe
- **Explanation**: Optional text field for justification
- **Confidence**: Optional confidence rating (high/medium/low)
- Green section highlights this is your input
- **Always visible** (even in blind mode)

#### Citations Section
- Scrollable list of supporting evidence with **expandable citation cards**
- Each citation card shows:
  - **Collapsed view**:
    - Citation number and truncated text
    - **Stance badge**: ✓ Supports | ✗ Contradicts | ? Neutral
    - **Relevance score badge**: Color-coded relevance rating (1-5)
    - **Identifiers**: PMID, DOI, Document ID
  - **Expanded view** (click to expand):
    - **Metadata**: Full stance, relevance score, document identifiers
    - **Extracted Citation**: The specific passage cited (highlighted in yellow)
    - **Full Abstract with Highlighting**: Complete abstract from PostgreSQL with the cited passage highlighted in yellow (like a text marker)
    - Text highlighting helps verify context and accuracy of citations
- Fetched in real-time from `public.document` table via foreign key

### 3. Provide Human Annotations

For each statement:

1. **Review the evidence**: Read the statement, AI evaluation (if visible), rationale, and citations
2. **Select your annotation**: Choose yes/no/maybe from the dropdown
3. **Add explanation (recommended)**: Describe your reasoning, especially if you disagree with the AI
4. **Set confidence (optional)**: Rate your confidence in the annotation
5. **Navigate**: Use Previous/Next buttons to move between statements
6. **Auto-save**: Your annotation is automatically saved to PostgreSQL when you navigate away

**Annotation Guidelines:**
- **Yes**: The statement is supported by the evidence
- **No**: The statement is contradicted by the evidence
- **Maybe**: Evidence is insufficient, mixed, or inconclusive
- **Blank**: Leave blank if you want to skip this statement

### 4. Navigation and Filtering

**Navigation Buttons:**
- **Previous**: Go to the previous statement (disabled on first statement)
- **Next**: Go to the next statement (disabled on last statement)
- **Jump to Statement**: Enter statement number directly

**Filtering (via command-line):**
- **Incremental mode** (`--incremental`): Shows only statements you haven't annotated yet
- **All statements mode** (default): Shows all statements in database

**Blind Mode (`--blind`):**
- Hides original and AI annotations from view
- Shows only the statement, evidence, and your annotation fields
- Prevents anchoring bias in human review
- Useful for inter-annotator agreement studies

### 5. Export Annotations

The Review GUI provides two export options:

**Database Export** (recommended):
- All annotations are automatically saved to PostgreSQL in real-time
- Use CLI to export database to JSON:
  ```bash
  python fact_checker_cli.py --export results.json
  ```

**Direct JSON Export** (from GUI):
- Click **"Export to JSON"** button
- Select export type (full/ai_only/human_annotated/summary)
- Choose output file location

## Data Storage Architecture

### PostgreSQL Schema

All data is stored in the **factcheck schema**:

**Tables:**
- `statements`: Biomedical statements to be fact-checked
- `ai_evaluations`: AI-generated evaluations with evidence
- `evidence`: Literature citations (FK to `public.document` - NO DUPLICATION)
- `human_annotations`: Your annotations (multi-user support)
- `annotators`: User profiles for all human reviewers
- `processing_metadata`: Session tracking
- `export_history`: Export audit trail

### No Data Duplication

- Evidence citations reference `public.document(id)` directly (foreign key)
- Full abstracts fetched on-demand from `public.document` table
- No SQLite intermediate storage (v2.0 simplification)
- Single source of truth in PostgreSQL

### Multi-User Workflow

The factcheck system supports collaborative annotation:

1. **Multiple reviewers** can annotate the same statements
2. **Username tracking** identifies who made each annotation
3. **Incremental mode** shows only statements **you** haven't annotated yet
4. **Blind mode** prevents bias from AI or other reviewers' annotations
5. **Inter-annotator agreement** can be calculated from database

**Example Multi-User Workflow:**
```bash
# Reviewer Alice annotates statements 1-100
uv run python fact_checker_review_gui.py --user alice --incremental

# Reviewer Bob independently annotates same statements (blind mode)
uv run python fact_checker_review_gui.py --user bob --blind --incremental

# Calculate inter-annotator agreement (SQL or Python script)
SELECT * FROM factcheck.calculate_inter_annotator_agreement();
```

## Incremental Mode

Incremental mode filters statements to show **only those you haven't annotated yet**:

```bash
# Show only statements without annotations from user 'alice'
uv run python fact_checker_review_gui.py --user alice --incremental
```

**How it works:**
1. Queries database for all statements without human annotations from your username
2. Filters display to show only unannotated statements
3. As you annotate, statements are marked complete
4. Progress bar shows completion percentage for your assigned workload

**Use cases:**
- Resume annotation after interruption
- Distribute workload among multiple reviewers
- Track individual reviewer progress

## Blind Mode

Blind mode hides AI and original annotations to prevent anchoring bias:

```bash
# Hide AI and original annotations
uv run python fact_checker_review_gui.py --user alice --blind
```

**What's hidden in blind mode:**
- Original expected answer (purple badge)
- AI evaluation result (blue badge)
- AI rationale and reasoning
- AI confidence level

**What's still visible:**
- Statement text
- Evidence citations and abstracts
- Your annotation fields (yes/no/maybe, explanation, confidence)

**Benefits:**
- Prevents confirmation bias from AI suggestions
- Enables unbiased inter-annotator agreement studies
- Supports gold standard dataset creation

## Citation Display Features

### Expandable Citation Cards

Citations use expandable cards (similar to main research GUI):
- **Click any citation** to expand and see full details
- **Collapsible design** saves screen space while reviewing
- **Progressive disclosure**: See summary first, expand for details

### Citation Stance Indicators

- **Green badge (✓)**: Supports the statement
- **Red badge (✗)**: Contradicts the statement
- **Grey badge (?)**: Neutral or unclear stance

### Relevance Scoring

Color-coded relevance scores (1-5 scale):
- **Red (1-2)**: Low relevance
- **Yellow (3)**: Medium relevance
- **Green (4-5)**: High relevance

### Abstract Highlighting

**Real-Time Abstract Fetching:**
- Full abstracts fetched from `public.document` table via foreign key
- No duplicate storage of abstract text
- Efficient database queries with connection pooling

**Citation Highlighting:**
- Cited passages highlighted in **yellow** (like text marker)
- 📌 markers indicate exact citation location in abstract
- ⚠️ markers indicate approximate/fuzzy matches
- Helps verify citations are used in proper context

## Tips for Effective Review

1. **Read citations carefully**: The AI's evaluation is based on these evidence passages
2. **Expand citations**: Click to see full abstract context for better understanding
3. **Check stance accuracy**: Verify that citation stance labels (supports/contradicts/neutral) are correct
4. **Consider evidence quality**: Look at relevance scores and source identifiers (PMID/DOI)
5. **Explain disagreements**: When your annotation differs from the AI's, add an explanation
6. **Use blind mode for unbiased review**: Especially important for gold standard creation
7. **Review systematically**: Go through statements in order for consistency
8. **Save frequently**: Although auto-save is enabled, periodic manual saves are good practice

## Common Use Cases

### Quality Control
Review AI fact-checking results to validate accuracy and identify systematic errors.

**Workflow:**
```bash
# Review all statements (see AI annotations)
uv run python fact_checker_review_gui.py --user qa_reviewer
```

### Training Data Creation
Generate human-annotated datasets for improving fact-checking models.

**Workflow:**
```bash
# Blind review for unbiased training data
uv run python fact_checker_review_gui.py --user annotator1 --blind
```

### Disagreement Analysis
Identify cases where AI and human reviewers disagree to understand model limitations.

**Workflow:**
```bash
# Review with AI annotations visible
uv run python fact_checker_review_gui.py --user analyst

# Export data and filter for disagreements
python analyze_disagreements.py results.json
```

### Evidence Assessment
Evaluate the quality and relevance of citations extracted by the system.

**Workflow:**
```bash
# Focus on citations by expanding each one
uv run python fact_checker_review_gui.py --user evidence_reviewer
```

### Multi-Reviewer Inter-Annotator Agreement
Calculate agreement between multiple human reviewers.

**Workflow:**
```bash
# Reviewer 1 (blind mode)
uv run python fact_checker_review_gui.py --user reviewer1 --blind

# Reviewer 2 (blind mode, same statements)
uv run python fact_checker_review_gui.py --user reviewer2 --blind

# Calculate agreement from database
SELECT * FROM factcheck.calculate_inter_annotator_agreement();
```

## Troubleshooting

### Common Issues

**"Cannot connect to database":**
- **Cause**: PostgreSQL not running or incorrect credentials
- **Solution**: Check PostgreSQL status and verify connection settings in `~/.bmlibrarian/config.json`

**"No statements found":**
- **Cause**: No statements in factcheck.statements table, or all statements already annotated (in incremental mode)
- **Solution**: Run fact-checker CLI first to populate database, or disable incremental mode

**"Abstracts not loading":**
- **Cause**: Document IDs in evidence table don't match public.document table
- **Solution**: Verify foreign key constraints and check that document IDs are valid

**"Annotation not saving":**
- **Cause**: Database connection lost or transaction error
- **Solution**: Check PostgreSQL logs, verify write permissions

**Slow citation expansion:**
- **Cause**: Large abstracts or slow database connection
- **Solution**: Optimize PostgreSQL queries, ensure connection pooling is enabled

### Error Messages

**"Database schema not found":**
- **Symptom**: "relation 'factcheck.statements' does not exist"
- **Solution**: Run database migrations to create factcheck schema
- **Command**: See BMLibrarian database migration documentation

**"Duplicate username":**
- **Symptom**: Username already exists with different profile
- **Solution**: Use existing username or choose a new one

**"Invalid annotation value":**
- **Symptom**: Annotation field shows error
- **Solution**: Select yes/no/maybe from dropdown (don't type manually)

## Integration with Fact-Checking Workflow

The review GUI integrates with BMLibrarian's fact-checking workflow:

1. **Generate Results**: Use `fact_checker_cli.py` to populate PostgreSQL factcheck schema
2. **Review Results**: Launch `fact_checker_review_gui.py` for human annotation
3. **Export and Analyze**: Export to JSON and analyze with custom scripts

**Example Complete Workflow:**
```bash
# Step 1: Run fact-checker on training data
uv run python fact_checker_cli.py training_statements.json

# Step 2: Review with multiple annotators (blind mode)
uv run python fact_checker_review_gui.py --user alice --blind --incremental
uv run python fact_checker_review_gui.py --user bob --blind --incremental

# Step 3: Calculate inter-annotator agreement
python scripts/calculate_agreement.py

# Step 4: Export final annotations
uv run python fact_checker_cli.py --export final_annotations.json

# Step 5: Analyze disagreements
python scripts/analyze_disagreements.py final_annotations.json
```

## Technical Details

### Database Queries

**Statements Query** (incremental mode):
```sql
SELECT s.* FROM factcheck.statements s
LEFT JOIN factcheck.human_annotations ha
  ON s.statement_id = ha.statement_id
  AND ha.annotator_id = (SELECT annotator_id FROM factcheck.annotators WHERE username = 'alice')
WHERE ha.annotation_id IS NULL;
```

**Evidence Query** (with abstract):
```sql
SELECT e.*, d.abstract
FROM factcheck.evidence e
JOIN public.document d ON e.document_id = d.id
WHERE e.evaluation_id = %s;
```

### UI Components

Built using Flet framework:
- **ExpansionTiles**: Collapsible citation cards for space efficiency
- **Text Highlighting**: Yellow-highlighted passages in abstracts
- **Badges**: Color-coded stance and relevance indicators
- **Dialogs**: Login, export, and error notifications
- **Database Integration**: Direct PostgreSQL connection with connection pooling
- **Responsive Layout**: Adapts to different screen sizes

### Performance Optimization

- **Connection Pooling**: Reuses database connections for efficiency
- **Lazy Loading**: Abstracts fetched only when citations are expanded
- **Batch Queries**: Multiple evidence items fetched in single query
- **Caching**: User profile cached for session duration

## See Also

- **Fact-Checker CLI Guide**: `doc/users/fact_checker_guide.md`
- **Developer Documentation**: `doc/developers/fact_checker_system.md`
- **Database Schema**: `src/bmlibrarian/factchecker/db/database.py`
- **PostgreSQL Functions**: `factcheck.sql` migration script

## Version History

- **v2.0.0** (2025-11-12): PostgreSQL Migration
  - Migrated from SQLite to PostgreSQL factcheck schema
  - Database-only architecture (no intermediate files)
  - Multi-user annotation support with blind mode
  - Direct foreign key to public.document (no data duplication)
  - Incremental mode for resuming annotation
  - Real-time abstract fetching from database

- **v1.2.0** (2025-11-11): Enhanced Citation Display
  - Expandable citation cards with full abstract display
  - Automatic abstract fetching from database
  - Yellow highlighting of cited passages within abstracts
  - Fuzzy matching support with visual indicators
  - Collapsible cards for improved space efficiency
  - SQLite database support

- **v1.1.0** (2025-11-11): File Loading Improvements
  - Added `--input-file` command-line argument
  - Automatic file loading on startup
  - SQLite database auto-creation from JSON

- **v1.0.0** (2025-11-11): Initial Release
  - Statement-by-statement review interface
  - Citation display with stance indicators
  - Human annotation input with explanations
  - JSON export with metadata
