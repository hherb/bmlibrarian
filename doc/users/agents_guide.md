# Agents User Guide

## Overview

BMLibrarian now provides a modular agents system that makes it easy to search and analyze biomedical literature using AI. Each agent is specialized for specific tasks, and they can work together to provide comprehensive research assistance.

## Available Agents

### QueryAgent - Smart Search
Converts your natural language questions into database searches automatically.

**What it does:**
- Understands questions like "How effective are COVID vaccines?"
- Converts them to optimized database queries
- Searches biomedical literature and returns results
- Handles complex medical terminology and synonyms

### DocumentScoringAgent - Relevance Assessment  
Evaluates how well documents answer your questions.

**What it does:**
- Scores documents from 0-5 based on relevance to your question
- Provides clear reasoning for each score
- Helps you focus on the most relevant papers
- Works with any documents from your search results

## Getting Started

### Installation and Setup

1. **Ensure Ollama is running** with appropriate models:
```bash
# For QueryAgent (lightweight, fast)
ollama pull llama3.2

# For DocumentScoringAgent (more powerful for assessment)
ollama pull gpt-oss:20b
```

2. **Install BMLibrarian** and sync dependencies:
```bash
uv sync
```

3. **Configure your environment** (.env file with database credentials)

### Basic Usage

```python
from bmlibrarian.agents import QueryAgent, DocumentScoringAgent

# Search for papers
query_agent = QueryAgent()
documents = list(query_agent.find_abstracts("diabetes treatment options"))

# Score papers for relevance
scoring_agent = DocumentScoringAgent()
for doc in documents[:3]:  # Score first 3 results
    result = scoring_agent.evaluate_document("diabetes treatment options", doc)
    print(f"Score: {result['score']}/5 - {doc['title']}")
    print(f"Why: {result['reasoning']}\n")
```

## QueryAgent Guide

### How to Ask Good Questions

The QueryAgent works best with medical and scientific language:

**✅ Good Examples:**
- "COVID-19 vaccine effectiveness in elderly patients"
- "Side effects of chemotherapy in breast cancer"
- "Biomarkers for early Alzheimer's disease diagnosis"
- "Treatment outcomes for type 2 diabetes with metformin"

**❌ Less Effective:**
- "Tell me about vaccines" (too broad)
- "What's good for diabetes?" (too casual)
- "Help with cancer" (not specific enough)

### Search Options

```python
query_agent = QueryAgent()

# Basic search
results = query_agent.find_abstracts("heart disease treatment")

# Advanced options
results = query_agent.find_abstracts(
    question="aspirin cardiovascular effects",
    max_rows=20,                    # Limit results
    use_pubmed=True,               # Include PubMed
    use_medrxiv=False,             # Exclude preprints
    from_date=date(2020, 1, 1),    # Recent papers only
    use_ranking=True               # Sort by relevance
)
```

### Human-in-the-Loop Review

You can review and modify the generated database query:

```python
def review_query(generated_query):
    print(f"Generated: {generated_query}")
    modified = input("Modify (or press Enter to keep): ")
    return modified if modified else generated_query

results = query_agent.find_abstracts(
    "diabetes complications",
    human_in_the_loop=True,
    human_query_modifier=review_query
)
```

### Progress Callbacks

Track search progress in real-time:

```python
def show_progress(step, data):
    if step == "query_generated":
        print(f"🔍 Searching for: {data}")
    elif step == "search_completed":
        print("✅ Search finished!")

query_agent = QueryAgent(callback=show_progress)
results = query_agent.find_abstracts("COVID vaccine safety")
```

## DocumentScoringAgent Guide

### Understanding Scores

The DocumentScoringAgent uses a 0-5 scale:

- **0**: Not related to your question
- **1**: Tangentially related, minimal relevance  
- **2**: Somewhat related, some useful information
- **3**: Significantly relevant, addresses key aspects
- **4**: Highly relevant, substantial useful content
- **5**: Completely answers your question

### Scoring Single Documents

```python
scoring_agent = DocumentScoringAgent()

# Document from your search results
document = {
    'title': 'COVID-19 Vaccine Efficacy in Clinical Trials',
    'abstract': 'This study shows 95% effectiveness...',
    'authors': ['Smith, J.', 'Johnson, M.'],
    'publication_date': '2021-03-15'
}

result = scoring_agent.evaluate_document(
    "How effective are COVID vaccines?", 
    document
)

print(f"Relevance Score: {result['score']}/5")
print(f"Reasoning: {result['reasoning']}")
```

### Batch Scoring

Score multiple documents efficiently:

```python
# Get documents from search
documents = list(query_agent.find_abstracts("cancer immunotherapy"))

# Score all documents
scored_results = scoring_agent.batch_evaluate_documents(
    "cancer immunotherapy effectiveness",
    documents
)

# Display results sorted by relevance
for doc, score_result in sorted(scored_results, key=lambda x: x[1]['score'], reverse=True):
    print(f"{score_result['score']}/5: {doc['title']}")
```

### Getting Top Documents

Automatically filter and rank documents:

```python
# Get only the most relevant documents
top_documents = scoring_agent.get_top_documents(
    question="heart failure treatment",
    documents=search_results,
    top_k=5,           # Return top 5
    min_score=3        # Only scores 3+ 
)

print("Most Relevant Papers:")
for i, (doc, score_result) in enumerate(top_documents, 1):
    print(f"{i}. [{score_result['score']}/5] {doc['title']}")
    print(f"   {score_result['reasoning']}\n")
```

## Combined Workflows

### Intelligent Search Pipeline

Combine both agents for the best results:

```python
from bmlibrarian.agents import QueryAgent, DocumentScoringAgent

def intelligent_search(question, max_results=10):
    """Search and rank documents by relevance."""
    
    # Step 1: Search for documents
    query_agent = QueryAgent()
    print(f"🔍 Searching for: {question}")
    documents = list(query_agent.find_abstracts(question, max_rows=20))
    
    if not documents:
        print("No documents found.")
        return []
    
    print(f"📄 Found {len(documents)} documents")
    
    # Step 2: Score for relevance
    scoring_agent = DocumentScoringAgent()  
    print("📊 Scoring relevance...")
    
    top_docs = scoring_agent.get_top_documents(
        question, documents, top_k=max_results, min_score=2
    )
    
    # Step 3: Display ranked results
    print(f"\n🏆 Top {len(top_docs)} most relevant results:\n")
    
    for i, (doc, result) in enumerate(top_docs, 1):
        print(f"{i}. Score: {result['score']}/5")
        print(f"   Title: {doc['title']}")
        print(f"   Authors: {', '.join(doc.get('authors', [])[:3])}")
        print(f"   Date: {doc.get('publication_date', 'Unknown')}")
        print(f"   Why relevant: {result['reasoning']}")
        print()
    
    return top_docs

# Use the intelligent search
results = intelligent_search("Alzheimer's disease biomarkers")
```

### Research Assistant Workflow

```python
def research_assistant(topic, num_papers=15):
    """Complete research workflow with quality filtering."""
    
    query_agent = QueryAgent()
    scoring_agent = DocumentScoringAgent()
    
    # Search broadly first
    print(f"🔬 Researching: {topic}")
    documents = list(query_agent.find_abstracts(topic, max_rows=50))
    
    # Filter for high-quality, relevant papers
    relevant_docs = scoring_agent.get_top_documents(
        topic, documents, top_k=num_papers, min_score=3
    )
    
    # Categorize by relevance
    perfect_match = [(d, s) for d, s in relevant_docs if s['score'] == 5]
    high_relevance = [(d, s) for d, s in relevant_docs if s['score'] == 4]
    good_relevance = [(d, s) for d, s in relevant_docs if s['score'] == 3]
    
    # Report findings
    print(f"\n📊 Research Summary for '{topic}':")
    print(f"   Perfect matches: {len(perfect_match)}")
    print(f"   High relevance: {len(high_relevance)}")  
    print(f"   Good relevance: {len(good_relevance)}")
    print(f"   Total quality papers: {len(relevant_docs)}")
    
    return {
        'perfect': perfect_match,
        'high': high_relevance, 
        'good': good_relevance,
        'all': relevant_docs
    }

# Research a topic comprehensively
research_results = research_assistant("COVID-19 vaccine side effects")
```

## Configuration and Customization

### Model Selection

Choose models based on your needs:

```python
# Fast query conversion (recommended for QueryAgent)
query_agent = QueryAgent(model="llama3.2")

# Powerful assessment (recommended for DocumentScoringAgent)  
scoring_agent = DocumentScoringAgent(model="gpt-oss:20b")

# Custom configuration
query_agent = QueryAgent(
    model="mistral",
    host="http://remote-ollama:11434",
    temperature=0.05,  # More deterministic
    callback=my_progress_function
)
```

### Error Handling

```python
from bmlibrarian.agents import QueryAgent, DocumentScoringAgent

try:
    query_agent = QueryAgent()
    
    # Test connection first
    if not query_agent.test_connection():
        print("❌ Cannot connect to Ollama")
        exit(1)
    
    results = query_agent.find_abstracts("my research question")
    
except ValueError as e:
    print(f"Input error: {e}")
except ConnectionError as e:
    print(f"Connection problem: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Troubleshooting

### Common Issues

**"Cannot connect to Ollama"**
- Check if Ollama is running: `ollama list`
- Verify the model is available: `ollama pull llama3.2`
- Check the host URL in agent initialization

**"Poor search results"**
- Try more specific medical terminology
- Include key terms and synonyms in your question
- Use the human-in-the-loop feature to modify queries

**"Scoring seems inconsistent"**
- Ensure you're using a capable model (gpt-oss:20b recommended)
- Try adjusting temperature for more consistent scoring
- Check that document has title and abstract fields

**"Slow performance"**
- Use smaller, faster models for QueryAgent
- Reduce batch sizes for scoring operations
- Consider caching results for repeated queries

### Getting Help

1. **Test agent connections:**
```python
agents = [QueryAgent(), DocumentScoringAgent()]
for agent in agents:
    if agent.test_connection():
        print(f"✅ {agent.get_agent_type()} connected")
    else:
        print(f"❌ {agent.get_agent_type()} failed")
```

2. **Check available models:**
```python
agent = QueryAgent()
models = agent.get_available_models()
print("Available models:", models)
```

3. **Enable debug logging:**
```python
import logging
logging.getLogger('bmlibrarian.agents').setLevel(logging.DEBUG)
```

## Import Path

All agents are now imported from the `bmlibrarian.agents` module:

```python
from bmlibrarian.agents import QueryAgent, DocumentScoringAgent
```

This provides access to all the specialized AI agents in the BMLibrarian system.

## Best Practices

1. **Question Formulation**: Use specific medical terminology and clear research questions
2. **Result Filtering**: Combine search with relevance scoring for best results  
3. **Batch Processing**: Use batch methods for evaluating multiple documents
4. **Progress Tracking**: Use callbacks for long-running operations
5. **Error Handling**: Always test connections and handle errors gracefully
6. **Model Selection**: Choose appropriate models for each task's requirements

The agents system makes biomedical literature research more efficient and targeted. Start with simple searches and gradually incorporate relevance scoring and advanced workflows as you become familiar with the capabilities.