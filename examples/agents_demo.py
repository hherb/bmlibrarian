#!/usr/bin/env python3
"""
BMLibrarian Agents Demo - Modern Architecture

This script demonstrates the new modular agents architecture including:
- QueryAgent for natural language to PostgreSQL conversion
- DocumentScoringAgent for document relevance assessment
- Combined workflows for intelligent document ranking

Requirements:
- Ollama server running with appropriate models
- PostgreSQL database with bmlibrarian data
- Environment variables configured in .env file

Usage:
    python agents_demo.py
"""

import sys
import time
from datetime import date, datetime
from typing import Dict, List

# Add the src directory to Python path
sys.path.insert(0, '../src')

from bmlibrarian.agents import QueryAgent, DocumentScoringAgent


def print_separator(title: str = ""):
    """Print a visual separator with optional title."""
    print("\n" + "=" * 80)
    if title:
        print(f" {title} ".center(80, "="))
        print("=" * 80)
    print()


def progress_callback(step: str, data: str):
    """Callback function for progress updates."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    callbacks = {
        "conversion_started": f"🔄 [{timestamp}] Converting question to query...",
        "query_generated": f"✅ [{timestamp}] Generated query: {data}",
        "evaluation_started": f"🔄 [{timestamp}] Evaluating document relevance...",
        "evaluation_completed": f"✅ [{timestamp}] {data}",
        "search_started": f"🔍 [{timestamp}] Searching database...",
        "search_completed": f"✅ [{timestamp}] Search completed",
    }
    
    message = callbacks.get(step, f"📝 [{timestamp}] {step}: {data}")
    print(message)


def demo_query_agent():
    """Demonstrate QueryAgent functionality."""
    print_separator("Query Agent Demo")
    
    print("🧠 Testing natural language to PostgreSQL query conversion...")
    
    try:
        # Initialize QueryAgent with callback
        query_agent = QueryAgent(callback=progress_callback)
        
        if not query_agent.test_connection():
            print("❌ Cannot connect to Ollama. Please ensure it's running.")
            return
        
        print(f"✅ Connected to Ollama using model: {query_agent.model}")
        
        # Test questions
        questions = [
            "What are the effects of aspirin on cardiovascular disease?",
            "COVID-19 vaccine effectiveness in elderly patients",
            "Biomarkers for early Alzheimer's disease diagnosis",
            "Side effects of chemotherapy in cancer patients"
        ]
        
        print("\n🔤 Converting questions to database queries:\n")
        
        for i, question in enumerate(questions, 1):
            try:
                print(f"{i}. Question: {question}")
                ts_query = query_agent.convert_question(question)
                print(f"   Query: {ts_query}")
                print()
            except Exception as e:
                print(f"   Error: {e}")
                print()
        
        # Demo search functionality (limit results for demo)
        print("🔍 Testing integrated search functionality...")
        question = "Effects of metformin on diabetes"
        print(f"Question: {question}")
        
        results = list(query_agent.find_abstracts(question, max_rows=3))
        
        if results:
            print(f"\n📄 Found {len(results)} documents:")
            for i, doc in enumerate(results, 1):
                print(f"\n{i}. {doc.get('title', 'N/A')}")
                print(f"   Authors: {', '.join(doc.get('authors', [])[:2])}")
                print(f"   Date: {doc.get('publication_date', 'N/A')}")
        else:
            print("No documents found.")
            
    except Exception as e:
        print(f"❌ QueryAgent demo failed: {e}")


def demo_scoring_agent():
    """Demonstrate DocumentScoringAgent functionality."""
    print_separator("Document Scoring Agent Demo")
    
    print("📊 Testing document relevance scoring...")
    
    try:
        # Initialize DocumentScoringAgent
        scoring_agent = DocumentScoringAgent(callback=progress_callback)
        
        if not scoring_agent.test_connection():
            print("❌ Cannot connect to Ollama. Please ensure it's running.")
            return
        
        print(f"✅ Connected to Ollama using model: {scoring_agent.model}")
        
        # Sample documents for scoring
        sample_documents = [
            {
                'title': 'COVID-19 Vaccine Effectiveness in Clinical Trials',
                'abstract': 'This randomized controlled trial evaluates the efficacy of COVID-19 vaccines in preventing symptomatic infection. Results show 95% effectiveness in preventing COVID-19 disease.',
                'authors': ['Smith, J.A.', 'Johnson, M.K.', 'Williams, R.T.'],
                'publication': 'New England Journal of Medicine',
                'publication_date': '2021-03-15'
            },
            {
                'title': 'Cardiovascular Effects of Statins in Elderly Patients',
                'abstract': 'A comprehensive review of statin therapy outcomes in patients over 65 years of age, focusing on cardiovascular event reduction and safety profiles.',
                'authors': ['Brown, L.', 'Davis, K.'],
                'publication': 'Cardiology Review',
                'publication_date': '2022-08-20'
            },
            {
                'title': 'Machine Learning Applications in Drug Discovery',
                'abstract': 'This paper explores the use of artificial intelligence and machine learning algorithms to accelerate pharmaceutical research and drug development processes.',
                'authors': ['Chen, W.', 'Patel, S.', 'Rodriguez, M.'],
                'publication': 'Nature Biotechnology',
                'publication_date': '2023-01-10'
            }
        ]
        
        user_question = "How effective are COVID-19 vaccines?"
        print(f"\n🔤 User Question: {user_question}")
        print("\n📊 Scoring documents for relevance:\n")
        
        for i, doc in enumerate(sample_documents, 1):
            try:
                print(f"{i}. Evaluating: {doc['title']}")
                
                result = scoring_agent.evaluate_document(user_question, doc)
                
                print(f"   Score: {result['score']}/5")
                print(f"   Reasoning: {result['reasoning']}")
                print()
                
            except Exception as e:
                print(f"   Error scoring document: {e}")
                print()
        
        # Demo batch evaluation
        print("🔄 Testing batch evaluation...")
        batch_results = scoring_agent.batch_evaluate_documents(user_question, sample_documents)
        
        print("\n📈 Batch Results Summary:")
        for doc, result in batch_results:
            print(f"   {result['score']}/5 - {doc['title'][:50]}...")
        
        # Demo top documents selection
        print("\n🏆 Getting top documents with score >= 3...")
        top_docs = scoring_agent.get_top_documents(
            user_question, 
            sample_documents, 
            top_k=2, 
            min_score=3
        )
        
        if top_docs:
            print("Top relevant documents:")
            for i, (doc, result) in enumerate(top_docs, 1):
                print(f"   {i}. Score {result['score']}/5: {doc['title']}")
        else:
            print("   No documents met the minimum score threshold.")
            
    except Exception as e:
        print(f"❌ DocumentScoringAgent demo failed: {e}")


def demo_combined_workflow():
    """Demonstrate combined QueryAgent + DocumentScoringAgent workflow."""
    print_separator("Combined Workflow Demo")
    
    print("🚀 Testing intelligent search with document scoring...")
    
    try:
        # Initialize both agents
        query_agent = QueryAgent()
        scoring_agent = DocumentScoringAgent()
        
        # Test connections
        if not (query_agent.test_connection() and scoring_agent.test_connection()):
            print("❌ Cannot connect to Ollama for both agents.")
            return
        
        user_question = "Treatment options for type 2 diabetes"
        print(f"🔤 User Question: {user_question}")
        
        # Step 1: Search for documents
        print("\n1️⃣ Searching for relevant documents...")
        documents = list(query_agent.find_abstracts(user_question, max_rows=5))
        
        if not documents:
            print("   No documents found.")
            return
        
        print(f"   Found {len(documents)} documents")
        
        # Step 2: Score documents for relevance
        print("\n2️⃣ Scoring documents for relevance...")
        scored_docs = scoring_agent.batch_evaluate_documents(user_question, documents)
        
        # Step 3: Rank and display results
        print("\n3️⃣ Final ranked results:")
        
        # Sort by score (descending)
        ranked_docs = sorted(scored_docs, key=lambda x: x[1]['score'], reverse=True)
        
        for i, (doc, result) in enumerate(ranked_docs, 1):
            print(f"\n{i}. Score: {result['score']}/5")
            print(f"   Title: {doc.get('title', 'N/A')}")
            print(f"   Authors: {', '.join(doc.get('authors', [])[:2])}")
            print(f"   Date: {doc.get('publication_date', 'N/A')}")
            print(f"   Reasoning: {result['reasoning']}")
        
        # Show statistics
        scores = [result['score'] for _, result in ranked_docs]
        avg_score = sum(scores) / len(scores)
        high_relevance = sum(1 for score in scores if score >= 4)
        
        print(f"\n📊 Summary Statistics:")
        print(f"   Average relevance score: {avg_score:.1f}/5")
        print(f"   High relevance documents (≥4): {high_relevance}/{len(scores)}")
        
    except Exception as e:
        print(f"❌ Combined workflow demo failed: {e}")


def test_agent_connections():
    """Test connections to all agent types."""
    print_separator("Testing Agent Connections")
    
    agents = [
        ("QueryAgent", QueryAgent),
        ("DocumentScoringAgent", DocumentScoringAgent)
    ]
    
    for agent_name, agent_class in agents:
        try:
            print(f"🔗 Testing {agent_name}...")
            agent = agent_class()
            
            if agent.test_connection():
                print(f"   ✅ {agent_name} connected successfully")
                print(f"   🤖 Model: {agent.model}")
                
                # Show available models
                models = agent.get_available_models()
                model_list = ', '.join(models[:3])
                if len(models) > 3:
                    model_list += f" (and {len(models) - 3} others)"
                print(f"   📋 Available models: {model_list}")
            else:
                print(f"   ❌ {agent_name} connection failed")
        
        except Exception as e:
            print(f"   ❌ {agent_name} error: {e}")
        
        print()


def main():
    """Main demo function."""
    print_separator("BMLibrarian Agents Architecture Demo")
    
    print("🧬 This demo showcases the new modular agents architecture:")
    print("   • BaseAgent: Common functionality for all agents")
    print("   • QueryAgent: Natural language to PostgreSQL conversion")
    print("   • DocumentScoringAgent: Document relevance assessment")
    print("   • Combined workflows for intelligent search")
    
    # Test connections first
    test_agent_connections()
    
    # Run individual agent demos
    demo_query_agent()
    demo_scoring_agent()
    
    # Combined workflow demo
    demo_combined_workflow()
    
    print_separator("Demo Complete")
    print("✅ All demonstrations completed!")
    print("🔧 You can now use the new agents architecture in your applications.")
    print()
    print("📚 Usage Examples:")
    print("   from bmlibrarian.agents import QueryAgent, DocumentScoringAgent")
    print("   query_agent = QueryAgent()")
    print("   scoring_agent = DocumentScoringAgent()")
    print()
    print("⚠️  Note: Old imports from bmlibrarian.agent still work but are deprecated.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Demo interrupted by user.")
    except Exception as e:
        print(f"\n\n❌ Demo failed: {e}")
        sys.exit(1)