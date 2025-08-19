# Query Agent User Guide

## Overview

The BMLibrarian Query Agent is an intelligent assistant that helps you search biomedical literature using natural language. It combines AI-powered query conversion with direct database search capabilities, allowing you to find relevant research papers and abstracts by simply asking questions in plain English.

## What is the Query Agent?

The Query Agent uses artificial intelligence to understand your questions about biomedical topics and automatically:
1. Converts your natural language questions into optimized database queries
2. Searches the biomedical literature database
3. Returns formatted results with abstracts, authors, and publication details
4. Provides options for human review and real-time progress updates

### Examples

**Your Question:** "What are the effects of aspirin on heart disease?"

**What the Agent Creates:** A search that looks for papers containing "aspirin" AND ("heart" OR "cardiac" OR "cardiovascular") AND ("disease" OR "disorder" OR "condition")

**Your Question:** "How does diabetes affect kidney function?"

**What the Agent Creates:** A search for "diabetes" AND ("kidney" OR "renal" OR "nephro") AND ("function" OR "dysfunction" OR "disease")

## Getting Started

### Prerequisites

1. **Ollama Server**: You need Ollama running on your system
   - Download from: https://ollama.ai
   - Install and run Ollama
   - Download a model (recommended: `ollama pull llama3.2`)

2. **Python Environment**: Ensure you have the bmlibrarian package installed
   ```bash
   uv sync
   ```

### Basic Usage

```python
from bmlibrarian.agent import QueryAgent

# Create an agent
agent = QueryAgent()

# Test the connection
if agent.test_connection():
    print("Agent is ready!")
else:
    print("Please check your Ollama setup")

# Search for papers using natural language
question = "What treatments are effective for Alzheimer's disease?"
for doc in agent.find_abstracts(question, max_rows=10):
    print(f"Title: {doc['title']}")
    print(f"Authors: {', '.join(doc['authors'][:3])}")
    print(f"Date: {doc['publication_date']}")
    print()
```

## How to Ask Good Questions

### Best Practices

1. **Be Specific**: Include specific medical terms, drug names, or conditions
   - Good: "Effects of metformin on type 2 diabetes"
   - Less effective: "Medicine for diabetes"

2. **Use Medical Language**: The agent works best with biomedical terminology
   - Good: "Cardiovascular effects of statins"
   - Good: "Cardiac side effects of cholesterol medication"

3. **Focus on Research Topics**: Frame questions as research inquiries
   - Good: "Clinical trials of immunotherapy for lung cancer"
   - Good: "Efficacy of COVID-19 vaccines in elderly patients"

### Question Types That Work Well

- **Treatment Effects**: "What are the effects of [drug] on [condition]?"
- **Comparative Studies**: "Comparison of [treatment A] versus [treatment B] for [condition]"
- **Mechanisms**: "How does [drug/process] affect [biological system]?"
- **Clinical Outcomes**: "Clinical outcomes of [treatment] in [patient population]"
- **Side Effects**: "Adverse effects of [drug] in [patient group]"

### Examples of Effective Questions

| Question | Why It Works Well |
|----------|-------------------|
| "Effectiveness of ACE inhibitors in heart failure" | Specific drug class and clear condition |
| "Biomarkers for early Alzheimer's diagnosis" | Specific research focus and disease |
| "Side effects of chemotherapy in elderly cancer patients" | Clear treatment, patient population, and outcome |
| "Gene therapy for sickle cell disease clinical trials" | Specific treatment type and condition |

## Understanding Search Results

### Query Format
The agent creates queries in "to_tsquery" format:
- `&` means AND (both terms must appear)
- `|` means OR (either term can appear)
- Parentheses group related terms

### Example Breakdown
For "COVID-19 vaccine effectiveness":
```
(covid | coronavirus | sars-cov-2) & vaccine & (effectiveness | efficacy)
```
This searches for papers that contain:
- At least one COVID-19 related term, AND
- The word "vaccine", AND  
- At least one effectiveness-related term

## Troubleshooting

### Common Issues

**"Agent not responding"**
- Check if Ollama is running: Open terminal and type `ollama list`
- Ensure the model is downloaded: `ollama pull llama3.2`
- Verify the connection: Use `agent.test_connection()`

**"Poor search results"**
- Try rephrasing your question with more medical terminology
- Be more specific about the condition or treatment
- Include alternative terms manually in your question

**"Connection errors"**
- Ensure Ollama is running on default port (11434)
- Check if your firewall is blocking the connection
- Try restarting Ollama service

### Getting Help

1. **Test Connection**: Always start by testing if the agent can connect
   ```python
   agent = QueryAgent()
   if not agent.test_connection():
       print("Connection issue - check Ollama setup")
   ```

2. **Check Available Models**: See what models are available
   ```python
   models = agent.get_available_models()
   print("Available models:", models)
   ```

3. **Try Different Models**: If one model doesn't work well, try another
   ```python
   agent = QueryAgent(model="mistral")
   ```

## Advanced Usage

### Custom Configuration

```python
# Use a different model
agent = QueryAgent(model="mistral")

# Connect to remote Ollama server
agent = QueryAgent(host="http://remote-server:11434")

# Combine custom settings
agent = QueryAgent(
    model="codellama",
    host="http://localhost:11434"
)
```

### Advanced Search Features

#### Search with Filters
```python
from datetime import date

# Search with date and source filters
results = list(agent.find_abstracts(
    question="COVID-19 vaccine effectiveness",
    max_rows=20,
    use_pubmed=True,      # Include PubMed papers
    use_medrxiv=False,    # Exclude medRxiv preprints
    from_date=date(2020, 1, 1),  # Papers from 2020 onwards
    use_ranking=True      # Sort by relevance
))
```

#### Human-in-the-Loop Review
```python
def review_query(generated_query):
    print(f"Generated query: {generated_query}")
    modified = input("Enter modified query (or press Enter to keep): ").strip()
    return modified if modified else generated_query

# Search with human review
results = list(agent.find_abstracts(
    question="Alzheimer's disease biomarkers",
    human_in_the_loop=True,
    human_query_modifier=review_query
))
```

#### Progress Callbacks
```python
def progress_callback(step, data):
    if step == "query_generated":
        print(f"🔍 Generated: {data}")
    elif step == "search_started":
        print("🔎 Searching...")

# Search with progress updates
results = list(agent.find_abstracts(
    question="cancer immunotherapy",
    callback=progress_callback
))
```

## Tips for Better Results

### Medical Terminology
- Use standard medical terms when possible
- Include both common and scientific names for conditions
- Consider synonyms that might appear in literature

### Question Structure
- Start with the main topic
- Include specific aspects you're interested in
- Mention patient populations if relevant

### Iterative Refinement
- Start with a broad question
- Refine based on initial results
- Add more specific terms if needed

## Supported Question Formats

The agent handles various question formats:

- **What questions**: "What are the side effects of..."
- **How questions**: "How does X affect Y?"
- **Treatment questions**: "Best treatments for..."
- **Comparison questions**: "X versus Y for treating..."
- **Mechanism questions**: "Mechanism of action of..."
- **Clinical questions**: "Clinical outcomes of..."

## Privacy and Data

### Local Processing
- All query processing happens locally through Ollama
- No data is sent to external services
- Your questions remain private

### Data Usage
- Questions are only used for generating search terms
- No personal information is stored or transmitted
- Database searches use only the generated terms

## Model Recommendations

### For General Use
- **llama3.2**: Good balance of speed and accuracy
- **mistral**: Faster responses, good for simple queries

### For Complex Medical Queries
- **llama3.2**: Better understanding of complex medical relationships
- **codellama**: Good for structured query generation

### Performance vs. Accuracy
- Larger models: More accurate but slower
- Smaller models: Faster but may miss nuances
- Choose based on your speed requirements

## Getting the Most from Your Searches

1. **Start Broad, Then Narrow**: Begin with general questions, refine based on results
2. **Use Medical Databases**: Leverage the agent's knowledge of biomedical terminology
3. **Consider Synonyms**: The agent automatically includes related terms
4. **Review Generated Queries**: Check if the search terms match your intent
5. **Iterate**: Refine your questions based on search results

Remember: The Query Agent is a tool to help you search more effectively. The quality of results depends on both the questions you ask and the content available in the database.