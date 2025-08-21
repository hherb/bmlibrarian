# BMLibrarian CLI Guide

This guide explains how to use the BMLibrarian Command Line Interface (CLI) for interactive medical literature research.

## What is the BMLibrarian CLI?

The BMLibrarian CLI is an interactive command-line application that guides you through the complete process of evidence-based medical literature research. It provides human-in-the-loop interaction at every step, ensuring you maintain control while leveraging AI-powered analysis.

**Two CLI Versions Available:**
- **bmlibrarian_cli_refactored.py** - **RECOMMENDED** - Modular architecture with enhanced features and counterfactual analysis
- **bmlibrarian_cli.py** - Legacy version maintained for compatibility

## Features

### Enhanced Features (Refactored CLI)
- 🔍 **Interactive Research Workflow**: Enhanced 8-step guidance through literature research
- 🤖 **AI-Assisted Query Generation**: Generate and edit database queries with AI help
- 📊 **Real-time Document Scoring**: AI evaluates document relevance with human review
- 📝 **Citation Extraction**: Extract relevant passages from high-scoring documents
- 📄 **Professional Reports**: Generate medical publication-style reports
- 🧠 **Counterfactual Analysis**: Optional analysis to find contradictory evidence
- 💾 **Enhanced Markdown Export**: Save reports with optional counterfactual analysis
- ⚙️ **Configurable Thresholds**: Adjust scoring and relevance parameters
- 🔄 **Iterative Refinement**: Go back and adjust parameters at any step
- 🏗️ **Modular Architecture**: Cleaner, more maintainable codebase

### Legacy Features (Original CLI)
- All core workflow features without counterfactual analysis
- Compatible with existing workflows and scripts

## Quick Start

### 1. Prerequisites

Ensure you have:
- PostgreSQL database with biomedical literature
- Ollama service running locally
- Required AI models installed
- Environment variables configured

### 2. Launch the CLI

**Recommended (Refactored CLI):**
```bash
# Simple launch
uv run python bmlibrarian_cli_refactored.py

# With options
uv run python bmlibrarian_cli_refactored.py --quick
uv run python bmlibrarian_cli_refactored.py --max-results 50 --timeout 10
```

**Legacy CLI:**
```bash
# Simple launch
uv run python bmlibrarian_cli.py
```

### 3. Follow the Enhanced Interactive Workflow

The refactored CLI guides you through 8 steps:
1. **Research Question** - Enter your medical question
2. **Query Generation** - AI generates database query (with editing)
3. **Document Search** - Execute search and review results
4. **Relevance Scoring** - AI scores documents for relevance
5. **Citation Extraction** - Extract relevant passages
6. **Report Generation** - Create professional report
7. **Counterfactual Analysis** - **NEW** Optional analysis for contradictory evidence
8. **Export** - Save as enhanced markdown file

### 4. Command Line Options

The refactored CLI supports additional configuration options:

```bash
# Quick testing mode (reduced limits for faster execution)
uv run python bmlibrarian_cli_refactored.py --quick

# Custom limits
uv run python bmlibrarian_cli_refactored.py --max-results 50 --timeout 10

# Adjust thresholds
uv run python bmlibrarian_cli_refactored.py --score-threshold 3.0 --min-relevance 0.8
```

## Detailed Workflow

### Step 1: Research Question

Enter a clear, specific medical research question:

**Good Examples:**
- "What are the cardiovascular benefits of exercise?"
- "How effective is metformin for diabetes management?"
- "What are the side effects of statins in elderly patients?"
- "Does cognitive behavioral therapy help with depression?"

**Tips:**
- Be specific rather than too broad
- Include key medical terms
- Focus on a single research question
- Use complete sentences

### Step 2: Query Generation and Editing

The AI generates a PostgreSQL query based on your question.

**Options Available:**
1. **Use as-is** - Accept the generated query
2. **Edit manually** - Modify the query in a text editor
3. **Generate new** - Ask AI to create a different query
4. **Custom query** - Enter your own PostgreSQL query

**Query Editing Tips:**
- The query should return documents with 'id', 'title', 'abstract' columns
- Use ILIKE for case-insensitive text search
- Consider using full-text search operators
- Add WHERE clauses to filter by date, journal, etc.
- Use LIMIT to control result size

**Example Query:**
```sql
SELECT id, title, abstract, authors, publication_date, pmid 
FROM documents 
WHERE to_tsvector('english', title || ' ' || abstract) 
      @@ plainto_tsquery('english', 'exercise cardiovascular benefits') 
ORDER BY ts_rank(to_tsvector('english', title || ' ' || abstract), 
                  plainto_tsquery('english', 'exercise cardiovascular benefits')) DESC 
LIMIT 100;
```

### Step 3: Document Search and Review

Execute the query and review results:

**What You'll See:**
- Total number of documents found
- Preview of first 10 documents with:
  - Title and authors
  - Publication date
  - Abstract preview
  - Document ID and PMID

**Options:**
1. **Proceed** - Continue with these results
2. **Modify query** - Go back and edit the search query
3. **Show more details** - View full abstracts and metadata

**Tips:**
- Look for recent, relevant publications
- Check that abstracts relate to your question
- Consider the variety of sources and publication dates
- If results seem off-topic, refine your query

### Step 4: Document Relevance Scoring

AI evaluates each document's relevance to your question (1-5 scale).

**Scoring Scale:**
- **5/5** 🟢 Highly relevant - directly answers your question
- **4/5** 🟢 Very relevant - contains significant relevant information
- **3/5** 🟡 Moderately relevant - some useful information
- **2/5** 🟠 Somewhat relevant - tangentially related
- **1/5** 🔴 Not relevant - little to no relevant content

**What You'll See:**
- Progress as documents are scored
- Score distribution histogram
- Top-scoring documents with reasoning
- Configurable score threshold (default: 2.5)

**Options:**
1. **Proceed** - Continue with current threshold
2. **Adjust threshold** - Change minimum score for processing
3. **Review scores** - Examine detailed scoring rationale
4. **Re-score** - Run scoring again with different parameters

**Threshold Guidelines:**
- **High threshold (≥3.5):** Very focused results, fewer documents
- **Medium threshold (2.0-3.5):** Balanced approach (recommended)
- **Low threshold (≤2.0):** Broader results, more documents

### Step 5: Citation Extraction

Extract relevant passages from high-scoring documents.

**Process:**
- Only documents above score threshold are processed
- AI identifies passages that answer your question
- Each passage gets a relevance score (0.0-1.0)
- Only passages above minimum relevance are kept

**What You'll See:**
- Progress through qualifying documents
- Extracted citations with:
  - Relevant passage text
  - Summary of why it's relevant
  - Relevance score
  - Source document information
- Citation statistics

**Configuration Options:**
- **Score threshold:** Minimum document score to process
- **Relevance threshold:** Minimum passage relevance to accept

**Quality Indicators:**
- **High-quality citations:** Relevance ≥0.8, specific passages
- **Medium-quality citations:** Relevance 0.7-0.8, good content
- **Review carefully:** Relevance <0.7, may be tangential

### Step 6: Report Generation

AI synthesizes citations into a medical publication-style report.

**Report Includes:**
- **Research Question:** Your original question
- **Evidence Assessment:** Strength rating and statistics
- **Synthesized Findings:** Professional medical writing with numbered citations
- **References:** Vancouver-style reference list
- **Methodology:** Description of analysis approach

**Evidence Strength Levels:**
- **Strong:** ≥5 citations, ≥3 sources, high relevance (≥0.85)
- **Moderate:** 3-4 citations, ≥2 sources, good relevance (≥0.75)
- **Limited:** 2-3 citations, adequate relevance (≥0.70)
- **Insufficient:** <2 citations or low relevance

**Report Format:**
```
Research Question: [Your question]
================================================================================

Evidence Strength: [Strong/Moderate/Limited/Insufficient]

[Synthesized answer with numbered citations [1], [2], [3]...]

REFERENCES
--------------------
1. [Vancouver-formatted reference]
2. [Vancouver-formatted reference]
...

METHODOLOGY
--------------------
[Description of synthesis approach]

REPORT METADATA
--------------------
Generated: [Timestamp]
Citations analyzed: [Number]
Unique references: [Number]
Evidence strength: [Assessment]
```

### Step 7: Counterfactual Analysis (Optional - Refactored CLI Only)

**NEW in Refactored CLI:** Analyze your report to identify potential contradictory evidence.

The counterfactual analysis helps validate your research findings by:
- **Identifying Main Claims:** Extracts key assertions from your report
- **Generating Research Questions:** Creates targeted questions to find contradictory evidence
- **Prioritizing Questions:** Ranks questions by importance (High/Medium/Low priority)
- **Database Search:** Optionally searches for studies that might contradict your findings

**What You'll See:**
```
🔍 Perform counterfactual analysis to find contradictory evidence? (y/n): y

✅ Counterfactual analysis completed!
   Confidence in original claims: MEDIUM
   Main claims identified: 3
   Research questions generated: 5

📋 Main Claims Identified:
   1. Mediterranean diet improves cognitive function in elderly populations
   2. Exercise prevents cardiovascular disease
   3. Regular physical activity reduces mortality risk

🔴 HIGH PRIORITY Research Questions (2):
   1. Are there studies showing Mediterranean diet has no cognitive benefits?
      Target: Mediterranean diet improves cognitive function
      Keywords: Mediterranean diet, cognitive decline, no effect

🔍 Search database for contradictory evidence? (y/n): y
```

**Benefits:**
- **Evidence Validation:** Identify potential weaknesses in your findings
- **Research Integrity:** Follow best practices for critical analysis
- **Confidence Assessment:** Get recommendations for evidence strength
- **Comprehensive Review:** Consider both supporting and opposing evidence

### Step 8: Export Report

Save your enhanced report as a markdown file for further use.

**Enhanced Features (Refactored CLI):**
- **Counterfactual Analysis Section:** Includes all generated research questions and assessments
- **Priority-Grouped Questions:** High/Medium/Low priority questions for contradictory evidence
- **Confidence Assessment:** Original confidence level and recommendations
- Automatic filename generation based on question and timestamp
- Custom filename option
- Proper markdown formatting with headers and lists
- Technical details about methodology
- Metadata about the research process

**Legacy Features (Original CLI):**
- All export features without counterfactual analysis section

**Enhanced File Structure (with Counterfactual Analysis):**
```markdown
# Medical Literature Research Report

**Generated by BMLibrarian CLI**
**Date:** 2023-06-15 14:25:30 UTC
**Evidence Strength:** Moderate

## Research Question
> What are the cardiovascular benefits of exercise?

## Evidence Assessment
- **Evidence Strength:** Moderate
- **Citations Analyzed:** 5
- **Unique References:** 4

## Findings
[Synthesized content with citations]

## References
1. [Vancouver-style references]
...

## Counterfactual Analysis
**Original Confidence Level:** MEDIUM

### Main Claims Analyzed
1. Regular exercise reduces cardiovascular disease risk
2. Physical activity improves heart function
3. Exercise training decreases mortality

### Research Questions for Contradictory Evidence

#### High Priority Questions
**Question 1:** Are there studies showing exercise has no cardiovascular benefits?
*Target Claim:* Regular exercise reduces cardiovascular disease risk
*Reasoning:* Critical to validate the primary claim
*Search Keywords:* exercise, cardiovascular, no effect, ineffective

### Overall Assessment
Report claims are generally well-supported but should be verified...

## Methodology
[Analysis approach]

## Technical Details
[System information and quality controls]
```

## Configuration and Customization

### Adjustable Parameters

**Score Threshold** (default: 2.5)
- Controls which documents are processed for citations
- Higher = fewer, more relevant documents
- Lower = more documents, broader coverage

**Relevance Threshold** (default: 0.7)
- Controls which citations are accepted
- Higher = fewer, more relevant citations
- Lower = more citations, broader content

**Display Limits**
- Document preview count (default: 10)
- Detail view pagination (5 documents at a time)

### Best Practices

#### For High-Quality Research
- Use specific, focused questions
- Set higher thresholds (score ≥3.0, relevance ≥0.8)
- Review and validate key citations manually
- Check evidence strength before drawing conclusions

#### For Exploratory Research
- Use broader questions initially
- Set moderate thresholds (score ≥2.0, relevance ≥0.7)
- Review more documents and citations
- Iterate and refine based on initial results

#### For Systematic Reviews
- Start with broad search terms
- Use lower thresholds initially (score ≥2.0)
- Process large document sets
- Export and combine multiple reports

## Troubleshooting

### Common Issues

**"No documents found"**
- Check database connection
- Verify query syntax and search terms
- Try broader search terms
- Check if database contains relevant literature

**"Document scoring failed"**
- Ensure Ollama is running (`curl http://localhost:11434/api/tags`)
- Check if required models are installed
- Verify network connectivity
- Try with fewer documents

**"Citation extraction failed"**
- Check Ollama connection and models
- Verify document abstracts are available
- Try lowering score threshold
- Check minimum relevance threshold

**"Report generation failed"**
- Ensure sufficient citations (≥2)
- Check Ollama service status
- Verify model availability
- Review citation quality

### Connection Issues

**Database Connection:**
```bash
# Test PostgreSQL connection
psql -h localhost -U your_username -d knowledgebase -c "SELECT COUNT(*) FROM documents;"
```

**Ollama Service:**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama if needed
ollama serve

# Check available models
ollama list
```

**Install Required Models:**
```bash
# Install default model for complex tasks
ollama pull gpt-oss:20b

# Install fast model for testing
ollama pull medgemma4B_it_q8:latest
```

### Performance Tips

**For Large Document Sets:**
- Start with higher score thresholds to reduce processing time
- Process in smaller batches if needed
- Use faster models for initial exploration
- Save intermediate results

**For Better Quality:**
- Use specific medical terminology in questions
- Review and edit generated queries
- Manually validate high-impact citations
- Cross-reference with known literature

**For Faster Processing:**
- Use `medgemma4B_it_q8:latest` model for speed
- Set higher thresholds to process fewer documents
- Limit search results with query LIMIT clauses
- Process during off-peak hours for database performance

## Advanced Usage

### Custom Database Queries

You can write custom PostgreSQL queries for specific needs:

**Date Range Filtering:**
```sql
SELECT * FROM documents 
WHERE publication_date BETWEEN '2020-01-01' AND '2023-12-31'
  AND abstract ILIKE '%your search terms%'
ORDER BY publication_date DESC;
```

**Journal-Specific Search:**
```sql
SELECT * FROM documents 
WHERE journal_name IN ('Nature', 'Science', 'Cell')
  AND to_tsvector('english', abstract) @@ plainto_tsquery('english', 'cancer treatment')
LIMIT 50;
```

**Author-Specific Search:**
```sql
SELECT * FROM documents 
WHERE authors::text ILIKE '%Smith, J%'
  AND abstract ILIKE '%clinical trial%'
ORDER BY publication_date DESC;
```

### Batch Processing

For processing multiple related questions:

1. Complete one full workflow
2. Save results with descriptive filenames
3. Start new workflow with refined questions
4. Compare results across different approaches
5. Combine insights from multiple reports

### Integration with External Tools

**Export to Reference Managers:**
- Extract PMID numbers from reports
- Import into Zotero, Mendeley, or EndNote
- Cross-reference with existing libraries

**Further Analysis:**
- Use citation data for meta-analyses
- Export structured data for statistical analysis
- Integrate with institutional research workflows

## Getting Help

### Built-in Documentation
- Use option 4 in main menu for basic help
- Review error messages for specific guidance
- Check system connection status (option 3)

### System Requirements
- Ensure all prerequisites are met
- Verify service connections before starting
- Check disk space for large document processing
- Monitor memory usage with large result sets

### Best Practices for Support
1. Note the specific step where issues occur
2. Check connection status for all services
3. Try with simpler queries first
4. Review logs for detailed error messages
5. Test with example questions to isolate issues

The BMLibrarian CLI provides a comprehensive, interactive approach to evidence-based medical literature research. By following this guide and adapting the workflow to your specific needs, you can efficiently conduct high-quality literature reviews with proper citations and professional reporting.