# Counterfactual Checking Agent User Guide

The CounterfactualAgent is designed to critically analyze documents and research reports by generating targeted research questions that could help find contradictory evidence. This is essential for rigorous academic research and evidence validation.

## What is Counterfactual Checking?

Counterfactual checking involves systematically identifying potential weaknesses, biases, or limitations in research claims and formulating specific questions to investigate contradictory evidence. This process helps:

- Identify methodological limitations
- Consider alternative explanations
- Question generalizability of findings  
- Evaluate evidence strength
- Reduce confirmation bias

## Basic Usage

### Quick Start: Complete Workflow

For a one-stop solution to find contradictory literature:

```python
from bmlibrarian.agents import CounterfactualAgent

# Initialize the agent (uses medgemma-27b by default for focused keyword generation)
agent = CounterfactualAgent()

# Complete workflow: analyze document and find contradictory literature
document_content = """
Exercise and Cardiovascular Health Review

Regular physical activity has been consistently shown to improve cardiovascular 
outcomes. Multiple studies demonstrate that exercise reduces heart disease risk 
by approximately 30%. The benefits appear to be dose-dependent and universal 
across populations.
"""

# This performs the entire workflow automatically
result = agent.find_contradictory_literature(
    document_content=document_content,
    document_title="Exercise Review",
    min_relevance_score=3
)

# Check results
summary = result['summary']
print(f"Original confidence: {summary['original_confidence']}")
print(f"Contradictory citations found: {summary['contradictory_citations_extracted']}")

if result['contradictory_citations']:
    print("⚠️ Contradictory evidence found - review needed")
    for evidence in result['contradictory_citations']:
        citation = evidence['citation']
        print(f"- {citation.document_title}")
        print(f"  Finding: {citation.summary}")
else:
    print("✅ No contradictory evidence - claims appear robust")
```

### Step-by-Step Analysis

For more control over the process:

```python
from bmlibrarian.agents import CounterfactualAgent

# Initialize the agent
agent = CounterfactualAgent()

# Analyze a document (research paper, report, etc.)
analysis = agent.analyze_document(document_content, "Exercise Review")

if analysis:
    print(f"Document: {analysis.document_title}")
    print(f"Confidence Level: {analysis.confidence_level}")
    print(f"Main Claims: {len(analysis.main_claims)}")
    print(f"Counterfactual Questions: {len(analysis.counterfactual_questions)}")
```

### Analyzing Reports with Citations

```python
# For research reports with supporting citations
from bmlibrarian.agents import CitationFinderAgent

citation_agent = CitationFinderAgent()
counterfactual_agent = CounterfactualAgent()

# First generate a report with citations (example workflow)
user_question = "What are the cardiovascular benefits of exercise?"
citations = citation_agent.process_scored_documents_for_citations(
    user_question, scored_documents, score_threshold=2.5
)

# Now analyze the report and its evidence base
report_content = "Generated research report text..."
analysis = counterfactual_agent.analyze_report_citations(report_content, citations)
```

## Understanding the Results

### CounterfactualAnalysis Structure

The analysis returns a `CounterfactualAnalysis` object containing:

- **main_claims**: Key claims or conclusions identified in the document
- **counterfactual_questions**: List of research questions to find contradictory evidence
- **overall_assessment**: Brief evaluation of the document's evidence quality
- **confidence_level**: HIGH/MEDIUM/LOW confidence in the document's claims

### CounterfactualQuestion Structure

Each research question includes:

- **question**: The specific research question
- **reasoning**: Why this question is important for validation
- **target_claim**: Which claim this question targets
- **search_keywords**: Suggested keywords for literature searches
- **priority**: HIGH/MEDIUM/LOW importance level

## Working with Results

### Filtering High-Priority Questions

```python
# Get only the most critical questions to investigate
high_priority_questions = agent.get_high_priority_questions(analysis)

for question in high_priority_questions:
    print(f"Question: {question.question}")
    print(f"Target: {question.target_claim}")
    print(f"Keywords: {', '.join(question.search_keywords)}")
    print("---")
```

### Generating Database-Ready Search Queries

```python
# Method 1: Generate PostgreSQL to_tsquery formatted queries
search_queries = agent.format_questions_for_search(analysis.counterfactual_questions)

for query in search_queries:
    print(f"PostgreSQL Query: {query}")

# Method 2: Use QueryAgent integration for better formatting
from bmlibrarian.agents import QueryAgent

query_agent = QueryAgent()
research_queries = agent.generate_research_queries_with_agent(
    analysis.counterfactual_questions, 
    query_agent
)

for query_info in research_queries:
    print(f"Question: {query_info['question']}")
    print(f"Database Query: {query_info['db_query']}")
    print(f"Priority: {query_info['priority']}")
```

### Executing Database Searches

```python
# Use the generated queries to search the BMLibrarian database
from bmlibrarian.database import find_abstracts

for query_info in research_queries:
    if query_info['priority'] == 'HIGH':
        # Search for contradictory evidence
        results_generator = find_abstracts(
            query_info['db_query'], 
            max_rows=20,
            plain=False  # Use advanced to_tsquery syntax
        )
        results = list(results_generator)
        print(f"Found {len(results)} potential contradictory studies")
        
        for result in results[:5]:  # Show top 5
            print(f"- {result['title']}")
```

### Creating a Research Protocol

```python
# Generate a comprehensive research protocol
protocol = agent.generate_research_protocol(analysis)
print(protocol)

# Save to file for research planning
with open("counterfactual_research_protocol.md", "w") as f:
    f.write(protocol)
```

## Practical Examples

### Example 1: Medical Research Paper

```python
paper_content = """
Omega-3 Fatty Acids and Cognitive Function

This meta-analysis of 15 randomized controlled trials found that omega-3 
supplementation significantly improved cognitive function in older adults 
(p<0.001). The effect was consistent across all age groups and appeared 
stronger with higher doses.
"""

analysis = agent.analyze_document(paper_content, "Omega-3 Meta-Analysis")

# Example output might include questions like:
# - "Are there studies showing no cognitive benefit from omega-3 in certain populations?"
# - "Do any trials report negative cognitive effects from omega-3 supplementation?"
# - "Are there methodological concerns with the included studies?"
```

### Example 2: Treatment Guidelines

```python
guidelines_content = """
Clinical Practice Guidelines: Hypertension Management

First-line treatment for hypertension should be ACE inhibitors or ARBs.
These medications reduce cardiovascular events by 25-30% and have
minimal side effects in most patients.
"""

analysis = agent.analyze_document(guidelines_content, "Hypertension Guidelines")

# Might generate questions about:
# - Population-specific contraindications
# - Comparative effectiveness with other drug classes
# - Long-term safety concerns
# - Cost-effectiveness considerations
```

## Model Configuration

BMLibrarian uses a centralized configuration system for easy model management:

### Configuration File

Models are configured in `bmlibrarian_config.json`:

```json
{
  "models": {
    "counterfactual_agent": "medgemma-27b-text-it-Q8_0:latest",
    "query_agent": "medgemma-27b-text-it-Q8_0:latest",
    "scoring_agent": "medgemma-27b-text-it-Q8_0:latest",
    "citation_agent": "medgemma-27b-text-it-Q8_0:latest",
    "reporting_agent": "gpt-oss:20b"
  }
}
```

### Quick Model Switching

```bash
# Create sample configuration
uv run python scripts/manage_config.py create

# Switch all agents to fast models
uv run python scripts/manage_config.py switch fast

# Switch to medical-focused models  
uv run python scripts/manage_config.py switch medical

# Switch to complex reasoning models
uv run python scripts/manage_config.py switch complex

# Set specific agent model
uv run python scripts/manage_config.py set counterfactual "gpt-oss:20b"

# Show current configuration
uv run python scripts/manage_config.py show

# Test all configured models
uv run python scripts/manage_config.py test
```

### Programmatic Override

You can still override models in code when needed:

```python
# Use configured model (recommended)
agent = CounterfactualAgent()

# Override for testing
agent = CounterfactualAgent(model="gpt-oss:20b")
```

### Model Presets

- **fast**: `medgemma4B_it_q8:latest` - Fastest execution, basic reasoning
- **medical**: `medgemma-27b-text-it-Q8_0:latest` - Medical domain knowledge, focused keywords
- **complex**: `gpt-oss:20b` - Complex reasoning, verbose but thorough analysis

## Best Practices

### 1. Document Preparation
- Provide complete document text for thorough analysis
- Include title, abstract, and key conclusions
- For reports with citations, analyze both together

### 2. Interpreting Results
- Focus on HIGH priority questions first
- Consider the confidence level when planning research
- Use search keywords as starting points, not exhaustive lists

### 3. Research Planning
- Use the generated protocol as a systematic framework
- Prioritize questions based on practical constraints
- Document your findings to complete the validation process

### 4. Integration with Other Agents
```python
# Complete workflow example
from bmlibrarian.agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent, 
    ReportingAgent, CounterfactualAgent
)

# 1. Generate initial research report
query_agent = QueryAgent()
scoring_agent = DocumentScoringAgent()
citation_agent = CitationFinderAgent()
reporting_agent = ReportingAgent()
counterfactual_agent = CounterfactualAgent()

user_question = "What are the benefits of intermittent fasting?"

# Standard workflow to generate report
documents = query_agent.search_documents(user_question)
scored_docs = [(doc, scoring_agent.evaluate_document(user_question, doc)) 
               for doc in documents]
citations = citation_agent.process_scored_documents_for_citations(
    user_question, scored_docs, score_threshold=3.0
)
report = reporting_agent.generate_citation_based_report(
    user_question, citations
)

# 2. Perform counterfactual analysis
counterfactual_analysis = counterfactual_agent.analyze_report_citations(
    report, citations
)

# 3. Generate research protocol for validation
if counterfactual_analysis:
    protocol = counterfactual_agent.generate_research_protocol(counterfactual_analysis)
    
    # Save both the original report and validation protocol
    with open("intermittent_fasting_report.md", "w") as f:
        f.write(report)
    
    with open("intermittent_fasting_validation_protocol.md", "w") as f:
        f.write(protocol)
```

## Troubleshooting

### Common Issues

1. **Empty Results**: Ensure document content is not empty or too short
2. **Connection Errors**: Verify Ollama is running and the model is available
3. **JSON Parsing Errors**: Check logs for malformed LLM responses

### Error Handling

```python
analysis = agent.analyze_document(document_content, document_title)

if analysis is None:
    print("Analysis failed. Check:")
    print("- Document content is not empty")
    print("- Ollama service is running")
    print("- Model is available")
    print("- Check logs for detailed errors")
else:
    # Process successful analysis
    pass
```

### Logging

Enable detailed logging to troubleshoot issues:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('bmlibrarian.agents.counterfactual_agent')
```

This agent provides a systematic approach to critical evaluation of research claims, helping ensure thorough and unbiased evidence assessment in your biomedical literature analysis.