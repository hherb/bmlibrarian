#!/usr/bin/env python3
"""
Enhanced Query Agent Demo - BMLibrarian

This script demonstrates the enhanced QueryAgent capabilities including:
- Natural language to PostgreSQL query conversion
- Database search integration
- Human-in-the-loop query modification
- UI callback hooks for real-time updates
- Various search options and filters

Requirements:
- Ollama server running with a medical model (e.g., medgemma4B_it_q8:latest)
- PostgreSQL database with bmlibrarian data
- Environment variables configured in .env file

Usage:
    python enhanced_agent_demo.py
"""

import sys
import time
from datetime import date, datetime
from typing import Dict, List

# Add the src directory to Python path
sys.path.insert(0, '../src')

from bmlibrarian.agents import QueryAgent


def print_separator(title: str = ""):
    """Print a visual separator with optional title."""
    print("\n" + "=" * 80)
    if title:
        print(f" {title} ".center(80, "="))
        print("=" * 80)
    print()


def ui_callback(step: str, data: str):
    """
    Callback function to demonstrate UI integration.
    
    This function receives updates at each step of the search process
    and can be used to update a UI, log progress, or trigger other actions.
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    callbacks = {
        "conversion_started": f"🔄 [{timestamp}] Converting question to database query...",
        "query_generated": f"✅ [{timestamp}] Generated query: {data}",
        "conversion_failed": f"❌ [{timestamp}] Query conversion failed: {data}",
        "human_review_started": f"👤 [{timestamp}] Human review requested for: {data}",
        "query_modified": f"✏️  [{timestamp}] Query modified to: {data}",
        "query_unchanged": f"📝 [{timestamp}] Query unchanged: {data}",
        "human_review_failed": f"⚠️  [{timestamp}] Human review failed: {data}",
        "search_started": f"🔍 [{timestamp}] Searching database with: {data}",
        "search_completed": f"✅ [{timestamp}] Search completed successfully",
        "search_failed": f"❌ [{timestamp}] Database search failed: {data}"
    }
    
    message = callbacks.get(step, f"📝 [{timestamp}] {step}: {data}")
    print(message)


def human_query_modifier(query: str) -> str:
    """
    Human-in-the-loop query modification function.
    
    This function is called when human_in_the_loop=True, allowing
    users to review and modify the generated PostgreSQL query.
    """
    print(f"\n🤖 Generated query: {query}")
    print("🧑 You can modify this query or press Enter to continue as-is:")
    
    try:
        modified = input("📝 Enter modified query (or press Enter to keep): ").strip()
        return modified if modified else query
    except (KeyboardInterrupt, EOFError):
        print("\n⏭️  Keeping original query...")
        return query


def display_results(results: List[Dict], max_display: int = 5):
    """Display search results in a formatted way."""
    count = 0
    total_results = 0
    
    for doc in results:
        total_results += 1
        
        if count < max_display:
            print(f"\n📄 Document {count + 1}:")
            print(f"   Title: {doc.get('title', 'N/A')}")
            print(f"   Authors: {', '.join(doc.get('authors', [])[:3])}{'...' if len(doc.get('authors', [])) > 3 else ''}")
            print(f"   Publication: {doc.get('publication', 'N/A')}")
            print(f"   Date: {doc.get('publication_date', 'N/A')}")
            print(f"   Source: {doc.get('source_name', 'N/A')}")
            
            # Show full abstract (no truncation for auditability)
            abstract = doc.get('abstract', '')
            if abstract:
                print(f"   Abstract: {abstract}")
            
            if doc.get('doi'):
                print(f"   DOI: {doc['doi']}")
            
            count += 1
    
    if total_results > max_display:
        print(f"\n... and {total_results - max_display} more results")
    
    print(f"\n📊 Total results found: {total_results}")


def demo_basic_search(agent: QueryAgent):
    """Demonstrate basic natural language search."""
    print_separator("Basic Natural Language Search")
    
    question = "What are the effects of aspirin on cardiovascular disease?"
    print(f"🔤 Question: {question}")
    
    try:
        results = list(agent.find_abstracts(
            question=question,
            max_rows=10,
            callback=ui_callback
        ))
        
        display_results(results)
        
    except Exception as e:
        print(f"❌ Error: {e}")


def demo_human_in_the_loop(agent: QueryAgent):
    """Demonstrate human-in-the-loop query modification."""
    print_separator("Human-in-the-Loop Search")
    
    question = "Studies on diabetes and kidney complications"
    print(f"🔤 Question: {question}")
    print("👤 You'll be able to review and modify the generated query...")
    
    try:
        results = list(agent.find_abstracts(
            question=question,
            max_rows=5,
            human_in_the_loop=True,
            human_query_modifier=human_query_modifier,
            callback=ui_callback
        ))
        
        display_results(results)
        
    except Exception as e:
        print(f"❌ Error: {e}")


def demo_filtered_search(agent: QueryAgent):
    """Demonstrate search with date and source filters."""
    print_separator("Filtered Search with Date Range")
    
    question = "COVID-19 vaccine effectiveness"
    from_date = date(2020, 1, 1)
    to_date = date(2023, 12, 31)
    
    print(f"🔤 Question: {question}")
    print(f"📅 Date range: {from_date} to {to_date}")
    print(f"📚 Sources: PubMed only")
    
    try:
        results = list(agent.find_abstracts(
            question=question,
            max_rows=8,
            use_pubmed=True,
            use_medrxiv=False,
            use_others=False,
            from_date=from_date,
            to_date=to_date,
            use_ranking=True,  # Enable relevance ranking
            callback=ui_callback
        ))
        
        display_results(results)
        
    except Exception as e:
        print(f"❌ Error: {e}")


def demo_query_conversion_only(agent: QueryAgent):
    """Demonstrate query conversion without database search."""
    print_separator("Query Conversion Only")
    
    questions = [
        "What are the side effects of metformin?",
        "Research on Alzheimer's disease biomarkers",
        "Studies comparing different COVID vaccines",
        "Treatment options for myocardial infarction",
        "Effects of exercise on mental health"
    ]
    
    print("🔄 Converting natural language questions to PostgreSQL queries:\n")
    
    for i, question in enumerate(questions, 1):
        try:
            ts_query = agent.convert_question(question)
            print(f"{i}. Question: {question}")
            print(f"   Query: {ts_query}")
            print()
        except Exception as e:
            print(f"{i}. Question: {question}")
            print(f"   Error: {e}")
            print()


def test_agent_connection(agent: QueryAgent):
    """Test the agent's connection to Ollama."""
    print_separator("Testing Agent Connection")
    
    try:
        if agent.test_connection():
            print("✅ Successfully connected to Ollama")
            print(f"🤖 Using model: {agent.model}")
            
            # Show available models
            models = agent.get_available_models()
            print(f"📋 Available models: {', '.join(models[:5])}{'...' if len(models) > 5 else ''}")
            return True
        else:
            print("❌ Failed to connect to Ollama")
            return False
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False


def main():
    """Main demo function."""
    print_separator("BMLibrarian Enhanced Query Agent Demo")
    
    print("🧬 This demo showcases the enhanced QueryAgent capabilities:")
    print("   • Natural language to PostgreSQL query conversion")
    print("   • Database search integration")
    print("   • Human-in-the-loop query modification")
    print("   • Real-time UI callbacks")
    print("   • Search filtering and ranking")
    
    # Initialize the agent
    try:
        agent = QueryAgent()
        print("\n🚀 Initializing QueryAgent...")
        
        # Test connection first
        if not test_agent_connection(agent):
            print("\n⚠️  Cannot proceed without Ollama connection.")
            print("   Please ensure Ollama is running with a medical model.")
            return 1
        
        # Run demonstrations
        demo_basic_search(agent)
        
        demo_filtered_search(agent)
        
        demo_query_conversion_only(agent)
        
        # Interactive demo (optional)
        print_separator("Interactive Demo")
        print("🎮 Would you like to try the human-in-the-loop search? (y/n)")
        
        try:
            if input().lower().startswith('y'):
                demo_human_in_the_loop(agent)
            else:
                print("⏭️  Skipping interactive demo.")
        except (KeyboardInterrupt, EOFError):
            print("\n⏭️  Skipping interactive demo.")
        
        print_separator("Demo Complete")
        print("✅ All demonstrations completed successfully!")
        print("🔧 You can now integrate the QueryAgent into your applications.")
        
        return 0
        
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)