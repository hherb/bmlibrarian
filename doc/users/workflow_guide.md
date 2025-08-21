# BMLibrarian Workflow User Guide

## Overview

BMLibrarian uses an advanced enum-based workflow system to guide you through comprehensive medical literature research. This flexible system supports iterative refinement, allowing agents to request additional evidence and enabling you to enhance your research quality through multiple passes.

## Workflow Steps

The BMLibrarian research workflow consists of 12 main steps that can be executed linearly or with iterative refinement:

### 1. Research Question Collection
**What it does**: Collects your medical research question
**User interaction**: You provide your research question in natural language
**Iterative**: No
**Auto mode**: Uses provided question automatically

**Example**: "What are the cardiovascular benefits of exercise?"

### 2. Query Generation & Editing  
**What it does**: Converts your question to a database search query
**User interaction**: Review and optionally edit the generated PostgreSQL query
**Iterative**: Yes - you can refine the query multiple times
**Auto mode**: Uses AI-generated query automatically

**Example**: Generated query: `exercise & (cardiovascular | cardiac | heart) & (health | wellness | function)`

### 3. Document Search
**What it does**: Searches the medical literature database
**User interaction**: Review search progress and results
**Iterative**: Can branch to query refinement if no documents found
**Auto mode**: Executes search automatically

**Typical results**: 10-100 relevant medical papers

### 4. Search Results Review
**What it does**: Displays found documents for review and approval
**User interaction**: Review titles/abstracts, approve or request new search
**Iterative**: Can return to query refinement if results unsatisfactory
**Auto mode**: Automatically approves all results

**Options**:
- Proceed with current results
- Refine search query
- Adjust search parameters

### 5. Document Relevance Scoring
**What it does**: AI scores each document (1-5) for relevance to your question
**User interaction**: Review scores, adjust threshold if needed
**Iterative**: Can repeat with different thresholds
**Auto mode**: Uses default threshold (2.0 in quick mode)

**Scoring criteria**:
- 5: Highly relevant, directly addresses question
- 4: Very relevant, substantial content related to question  
- 3: Moderately relevant, some useful information
- 2: Somewhat relevant, limited useful content
- 1: Minimally relevant, tangential information

### 6. Citation Extraction
**What it does**: Extracts specific passages that answer your question
**User interaction**: Review extracted citations, adjust relevance threshold
**Iterative**: Can request more citations or adjust thresholds
**Auto mode**: Uses default relevance threshold (0.6 in quick mode)

**Output**: Specific quotes with document references and relevance scores

### 7. Report Generation
**What it does**: Synthesizes citations into a medical publication-style report
**User interaction**: Review generated report
**Iterative**: Agents may request more citations if evidence insufficient
**Auto mode**: Generates report automatically

**Report includes**:
- Executive summary
- Detailed findings with citations
- Evidence strength assessment
- Limitations and caveats

### 8. Counterfactual Analysis (Optional)
**What it does**: Analyzes the report to identify claims and generate research questions for finding contradictory evidence
**User interaction**: Choose whether to perform analysis
**Iterative**: No
**Auto mode**: Performs analysis automatically

**Generates**:
- Main claims identified in the report
- Research questions to find contradictory evidence
- Confidence level recommendations

### 9. Contradictory Evidence Search (Optional)
**What it does**: Searches for studies that might contradict the report findings
**User interaction**: Choose whether to search for contradictory evidence  
**Iterative**: No
**Auto mode**: Performs search automatically

**Purpose**: Provides balanced perspective and identifies potential study limitations

### 10. Comprehensive Report Editing
**What it does**: Creates a balanced final report integrating all evidence
**User interaction**: Review comprehensive report
**Iterative**: Can request revisions
**Auto mode**: Generates comprehensive report automatically

**Enhanced report includes**:
- Balanced presentation of findings
- Integration of contradictory evidence
- Evidence quality tables
- Confidence assessments

### 11. Report Review & Revision (Optional)
**What it does**: Allows iterative improvement of the final report
**User interaction**: Request specific revisions or improvements
**Iterative**: Yes - can repeat multiple times
**Auto mode**: Skips revision step

### 12. Report Export
**What it does**: Saves the final report to a markdown file
**User interaction**: Choose whether to save report
**Iterative**: No
**Auto mode**: Saves automatically if requested

## Iterative Workflow Features

### Query Refinement
If your initial search doesn't yield sufficient results, you can:
- Refine your research question
- Adjust search terms
- Use different medical terminology
- Broaden or narrow the scope

### Threshold Adjustment  
Fine-tune evidence quality by adjusting:
- **Document score threshold**: Minimum relevance score for documents (1-5)
- **Citation relevance threshold**: Minimum relevance for extracted passages (0-1)

### Citation Enhancement
During report generation, agents may automatically:
- Request additional citations if evidence is thin
- Suggest lowering thresholds to get more citations
- Recommend broader searches for comprehensive coverage

### Report Revision
Iteratively improve your final report by requesting:
- Additional analysis of specific aspects
- Integration of new evidence
- Restructuring for clarity
- Enhanced methodology sections

## Usage Modes

### Interactive Mode (Recommended)
Full human-in-the-loop workflow with:
- Manual review at each step
- Ability to refine and iterate
- Quality control checkpoints
- Flexible threshold adjustment

**Start with**: `uv run python bmlibrarian_cli_refactored.py`

### Auto Mode
Automated execution with minimal interaction:
- Uses AI decisions throughout
- Default thresholds and parameters
- Faster execution
- Good for exploratory research

**Start with**: `uv run python bmlibrarian_cli_refactored.py --auto "Your research question"`

### Quick Mode
Reduced scope for rapid testing:
- 20 documents maximum
- 2-minute timeout
- Lower quality thresholds
- Faster processing

**Start with**: `uv run python bmlibrarian_cli_refactored.py --quick`

## Best Practices

### Research Question Formulation
- **Be specific**: "Effects of high-intensity interval training on Type 2 diabetes" vs "Exercise and diabetes"
- **Use medical terminology**: Include relevant clinical terms
- **Define scope**: Specify population, intervention, outcome
- **Consider timeframe**: Recent studies vs historical analysis

### Search Strategy
- **Start broad**: Begin with general terms, then refine
- **Review results**: Always check if search captured intended studies
- **Iterate**: Don't hesitate to refine your query multiple times
- **Use synonyms**: Try alternative medical terminology

### Quality Control
- **Review scores**: Check if document relevance scores make sense
- **Read citations**: Verify extracted passages actually answer your question  
- **Check references**: Ensure cited studies are real and accessible
- **Assess evidence strength**: Consider study quality and quantity

### Report Enhancement
- **Use counterfactual analysis**: Get a balanced perspective
- **Review contradictory evidence**: Understand limitations
- **Request revisions**: Iterate to improve clarity and completeness
- **Save your work**: Export the final report for future reference

## Troubleshooting

### No Documents Found
1. Check research question for typos
2. Try more general terms
3. Use alternative medical terminology
4. Verify the topic is covered in the database

### Low-Quality Citations
1. Lower the relevance threshold
2. Increase the document score threshold
3. Refine your research question for clarity
4. Request additional citations

### Incomplete Reports
1. Request more citations in step 6
2. Lower scoring thresholds to get more evidence
3. Broaden your search query
4. Use report revision to request specific improvements

### Auto Mode Failures
1. Switch to interactive mode for complex queries
2. Verify your research question is clear and specific
3. Check that the topic has sufficient literature coverage
4. Use quick mode for initial exploration

## Advanced Features

### Context Preservation
The workflow maintains context across all steps:
- Your research question persists throughout
- Previous results inform subsequent decisions
- Agent recommendations build on prior analysis

### Agent-Driven Refinement
AI agents can autonomously:
- Request more evidence during report generation
- Suggest threshold adjustments
- Identify gaps in the literature coverage
- Recommend query refinements

### Progress Tracking
The system provides detailed logging:
- Step execution times
- Document processing progress
- Citation extraction status
- Error reporting and recovery

### Quality Assurance
Built-in safeguards ensure:
- Real document references (no hallucinated citations)
- Evidence strength assessment
- Confidence level reporting
- Contradiction identification

## Getting Help

If you encounter issues:

1. **Check logs**: Review the session log file for detailed error information
2. **Try quick mode**: Use `--quick` flag for faster testing
3. **Use interactive mode**: Switch from auto mode for more control
4. **Verify connections**: Ensure database and Ollama services are running
5. **Check documentation**: Refer to CLAUDE.md for troubleshooting tips

## Example Session

Here's a complete example session:

```bash
# Start interactive workflow
uv run python bmlibrarian_cli_refactored.py

# 1. Enter research question
"What are the effects of Mediterranean diet on cardiovascular disease prevention?"

# 2. Review and approve generated query
# AI generates: mediterranean & diet & (cardiovascular | cardiac | heart) & (disease | prevention)

# 3. Review search results 
# Found 45 relevant studies

# 4. Review document scores
# 15 documents scored 3+ for relevance

# 5. Review extracted citations
# 23 high-quality citations extracted

# 6. Review generated report
# Comprehensive report with evidence synthesis

# 7. Perform counterfactual analysis
# Identified 3 potential contradictory research questions

# 8. Search contradictory evidence
# Found 2 studies with conflicting results

# 9. Review comprehensive report
# Balanced analysis including contradictory evidence

# 10. Export final report
# Saved to: Mediterranean_Diet_Cardiovascular_Prevention_Report_20241221_143022.md
```

This workflow provides you with a thorough, evidence-based analysis that considers multiple perspectives and maintains scientific rigor throughout the research process.