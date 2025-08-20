#!/usr/bin/env python3
"""
Citation Finder Agent Demonstration

Shows how to use the CitationFinderAgent to extract relevant passages
from high-scoring documents and build a queue of verifiable citations.

This demo demonstrates:
1. Processing scored documents to find qualifying citations
2. Queue-based citation extraction for memory efficiency
3. Citation verification and statistics
4. Integration with scoring workflow
5. Citation output formatting

Usage:
    python examples/citation_demo.py
"""

import os
import sys
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bmlibrarian.agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent,
    AgentOrchestrator, QueueManager, TaskPriority, TaskStatus,
    Citation, ScoringResult
)


def setup_agents():
    """Set up orchestrator with all required agents."""
    print("🔧 Setting up orchestrator and agents...")
    
    orchestrator = AgentOrchestrator(max_workers=4, polling_interval=0.5)
    
    query_agent = QueryAgent(orchestrator=orchestrator)
    scoring_agent = DocumentScoringAgent(orchestrator=orchestrator)
    citation_agent = CitationFinderAgent(orchestrator=orchestrator)
    
    orchestrator.register_agent("query_agent", query_agent)
    orchestrator.register_agent("document_scoring_agent", scoring_agent)
    orchestrator.register_agent("citation_finder_agent", citation_agent)
    
    return orchestrator, query_agent, scoring_agent, citation_agent


def create_sample_scored_documents() -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Create sample scored documents for demonstration."""
    
    # Sample documents with realistic database-style IDs  
    # NOTE: In production, these would come from actual database queries
    documents = [
        {
            "id": 123456789,  # Realistic database ID
            "title": "COVID-19 Vaccine Effectiveness in Healthcare Workers",
            "abstract": "This study evaluated the effectiveness of COVID-19 vaccines in preventing infection among healthcare workers. We conducted a prospective cohort study of 5,000 healthcare workers over 12 months. The mRNA vaccines showed 94% effectiveness against symptomatic infection and 97% effectiveness against severe disease. Breakthrough infections were rare and typically mild.",
            "authors": ["Smith, J.", "Johnson, A.", "Brown, K."],
            "publication_date": "2023-06-15",
            "pmid": "37123456"
        },
        {
            "id": 123456790, 
            "title": "Safety Profile of mRNA COVID-19 Vaccines in Large Population Study",
            "abstract": "We analyzed adverse events following COVID-19 vaccination in a population of 2.5 million individuals. Serious adverse events were rare, occurring in 0.01% of recipients. The most common side effects were pain at injection site (78%), fatigue (63%), and headache (45%). No increased risk of myocarditis was observed in this population.",
            "authors": ["Davis, M.", "Wilson, R.", "Garcia, L."],
            "publication_date": "2023-04-22",
            "pmid": "37234567"
        },
        {
            "id": 123456791,
            "title": "Diabetes Management with Continuous Glucose Monitoring",
            "abstract": "Continuous glucose monitoring (CGM) systems have revolutionized diabetes management by providing real-time glucose readings. Our randomized controlled trial of 800 patients showed that CGM use resulted in improved glycemic control with HbA1c reduction of 0.8%. Patients reported higher satisfaction and quality of life scores.",
            "authors": ["Anderson, P.", "Taylor, S.", "Miller, D."],
            "publication_date": "2023-03-10",
            "pmid": "37345678"
        },
        {
            "id": 123456792,
            "title": "Immunotherapy Advances in Non-Small Cell Lung Cancer",
            "abstract": "Recent advances in cancer immunotherapy have dramatically improved outcomes for patients with non-small cell lung cancer (NSCLC). Pembrolizumab monotherapy showed overall survival benefit in patients with high PD-L1 expression (≥50%), with median survival increasing from 10.4 to 30.0 months. Combination therapy with chemotherapy further improved response rates.",
            "authors": ["Thompson, C.", "White, B.", "Jones, N."],
            "publication_date": "2023-05-30",
            "pmid": "37456789"
        },
        {
            "id": 123456793,
            "title": "Machine Learning in Medical Diagnosis: Current Applications",
            "abstract": "Machine learning algorithms are increasingly being applied to medical diagnosis across multiple specialties. Deep learning models have shown promising results in radiology, with some algorithms achieving diagnostic accuracy comparable to human experts. However, challenges remain regarding model interpretability, bias, and clinical integration.",
            "authors": ["Lee, H.", "Chen, X.", "Patel, R."],
            "publication_date": "2023-07-12", 
            "pmid": "37567890"
        }
    ]
    
    # Create scoring results - simulate different relevance scores
    scoring_results = [
        {"score": 4.5, "reasoning": "Directly addresses vaccine effectiveness with specific statistics"},
        {"score": 4.2, "reasoning": "Provides comprehensive safety data for COVID-19 vaccines"},
        {"score": 1.8, "reasoning": "About diabetes management, not directly relevant to COVID-19 vaccines"},
        {"score": 2.1, "reasoning": "Cancer treatment, somewhat medical but not vaccine-related"},
        {"score": 1.5, "reasoning": "General medical AI, not specific to vaccines or COVID-19"}
    ]
    
    return list(zip(documents, scoring_results))


def demo_direct_citation_extraction():
    """Demonstrate direct citation extraction from documents."""
    print("\n" + "="*60)
    print("📝 Direct Citation Extraction Demo")
    print("="*60)
    
    orchestrator, query_agent, scoring_agent, citation_agent = setup_agents()
    
    try:
        if not citation_agent.test_connection():
            print("❌ Cannot connect to Ollama - using mock extraction")
            return
        
        print("✅ Connected to Ollama")
        
        # Create sample data
        scored_documents = create_sample_scored_documents()
        user_question = "What is the effectiveness and safety of COVID-19 vaccines?"
        
        print(f"❓ Question: {user_question}")
        print(f"📄 Processing {len(scored_documents)} scored documents...")
        
        # Extract citations from high-scoring documents
        citations = citation_agent.process_scored_documents_for_citations(
            user_question=user_question,
            scored_documents=scored_documents,
            score_threshold=3.0,  # Only documents scoring > 3.0
            min_relevance=0.7,
            progress_callback=lambda current, total: print(f"   📊 Progress: {current}/{total}")
        )
        
        print(f"\n✅ Extracted {len(citations)} citations")
        
        # Display citations
        if citations:
            print("\n📋 Extracted Citations:")
            print("-" * 50)
            
            for i, citation in enumerate(citations, 1):
                print(f"\n{i}. Document: {citation.document_title}")
                print(f"   ID: {citation.document_id}")
                print(f"   Authors: {', '.join(citation.authors)}")
                print(f"   Date: {citation.publication_date}")
                print(f"   Relevance: {citation.relevance_score:.2f}")
                print(f"   Passage: \"{citation.passage}\"")
                print(f"   Summary: {citation.summary}")
                if citation.pmid:
                    print(f"   PMID: {citation.pmid}")
        
        # Show statistics
        stats = citation_agent.get_citation_stats(citations)
        print(f"\n📊 Citation Statistics:")
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"   {key}: {value:.3f}")
            else:
                print(f"   {key}: {value}")
    
    except Exception as e:
        print(f"❌ Error in citation extraction demo: {e}")
        import traceback
        traceback.print_exc()


def demo_queue_based_citation_processing():
    """Demonstrate queue-based citation processing for scalability."""
    print("\n" + "="*60)
    print("🔄 Queue-Based Citation Processing Demo")
    print("="*60)
    
    orchestrator, query_agent, scoring_agent, citation_agent = setup_agents()
    
    try:
        if not citation_agent.test_connection():
            print("❌ Cannot connect to Ollama - skipping queue demo")
            return
        
        print("✅ Connected to Ollama")
        orchestrator.start_processing()
        
        # Create sample data with more documents
        scored_documents = create_sample_scored_documents()
        # Add more documents to simulate larger dataset
        base_docs = scored_documents.copy()
        for i in range(5, 15):  # Add 10 more documents
            doc, score = base_docs[i % len(base_docs)]
            new_doc = doc.copy()
            new_doc["id"] = 123456794 + i  # Sequential database-style IDs
            new_doc["title"] = f"Extended Study {i+1}: {doc['title']}"
            scored_documents.append((new_doc, score))
        
        user_question = "What is the effectiveness and safety of COVID-19 vaccines?"
        
        print(f"❓ Question: {user_question}")
        print(f"📄 Processing {len(scored_documents)} documents via queue...")
        
        # Process citations using queue system
        citations = []
        start_time = time.time()
        
        def progress_tracker(current, total):
            percent = (current / total) * 100
            print(f"   📊 Queue Progress: {current}/{total} ({percent:.1f}%)")
        
        for doc, citation in citation_agent.process_citation_queue(
            user_question=user_question,
            scored_documents=scored_documents,
            score_threshold=3.0,
            progress_callback=progress_tracker,
            batch_size=5
        ):
            if citation:
                citations.append(citation)
        
        processing_time = time.time() - start_time
        print(f"\n⏱️  Queue processing time: {processing_time:.1f} seconds")
        print(f"✅ Found {len(citations)} citations from queue processing")
        
        # Display sample citations
        if citations:
            print("\n🏆 Top Citations from Queue:")
            print("-" * 50)
            
            # Sort by relevance score
            sorted_citations = sorted(citations, key=lambda c: c.relevance_score, reverse=True)
            
            for i, citation in enumerate(sorted_citations[:3], 1):
                print(f"\n{i}. {citation.document_title}")
                print(f"   Relevance: {citation.relevance_score:.3f}")
                print(f"   Summary: {citation.summary}")
                print(f"   Document ID: {citation.document_id}")
        
        # Compare processing methods
        print(f"\n📈 Processing Comparison:")
        print(f"   Total documents: {len(scored_documents)}")
        print(f"   Above threshold: {len([d for d, s in scored_documents if s['score'] > 3.0])}")
        print(f"   Citations found: {len(citations)}")
        print(f"   Processing rate: {len(scored_documents)/processing_time:.1f} docs/sec")
        
    except Exception as e:
        print(f"❌ Error in queue processing demo: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        orchestrator.stop_processing()


def demo_citation_workflow_integration():
    """Demonstrate full workflow: scoring → citation → reporting."""
    print("\n" + "="*60)
    print("🔗 Integrated Citation Workflow Demo") 
    print("="*60)
    
    orchestrator, query_agent, scoring_agent, citation_agent = setup_agents()
    
    try:
        # Check connections
        scoring_available = scoring_agent.test_connection()
        citation_available = citation_agent.test_connection()
        
        if not (scoring_available and citation_available):
            print("❌ Ollama not available - using mock workflow")
            return
        
        print("✅ All services connected")
        orchestrator.start_processing()
        
        # Sample documents (without pre-calculated scores)
        documents = [doc for doc, _ in create_sample_scored_documents()]
        user_question = "What is the effectiveness and safety of COVID-19 vaccines?"
        
        print(f"❓ Question: {user_question}")
        print(f"📄 Starting with {len(documents)} documents")
        
        print("\n1️⃣ Step 1: Document Scoring")
        print("-" * 30)
        
        # Score documents first
        scored_results = []
        for doc in documents:
            result = scoring_agent.evaluate_document(user_question, doc)
            if result:
                scored_results.append((doc, result))
                print(f"   📊 {doc['id']}: {result['score']}/5 - {result['reasoning']}")
        
        print(f"\n✅ Scored {len(scored_results)} documents")
        
        print("\n2️⃣ Step 2: Citation Extraction")
        print("-" * 30)
        
        # Count qualifying documents
        qualifying_docs = [doc for doc, score in scored_results if score['score'] > 2.5]
        print(f"   Found {len(qualifying_docs)} documents above threshold 2.5")
        
        # Extract citations from high-scoring documents
        # Use threshold 2.5 to include documents scoring 3/5
        citations = citation_agent.process_scored_documents_for_citations(
            user_question=user_question,
            scored_documents=scored_results,
            score_threshold=2.5,  # Lower threshold to include score 3 documents
            min_relevance=0.7
        )
        
        print(f"✅ Extracted {len(citations)} citations")
        
        print("\n3️⃣ Step 3: Citation Summary Report")
        print("-" * 30)
        
        if citations:
            # Group citations by document and create summary
            print("📋 Citation Summary Report:")
            print("=" * 50)
            
            for citation in sorted(citations, key=lambda c: c.relevance_score, reverse=True):
                print(f"\n• **{citation.document_title}**")
                print(f"  Authors: {', '.join(citation.authors[:3])}{'...' if len(citation.authors) > 3 else ''}")
                print(f"  Published: {citation.publication_date}")
                print(f"  Document ID: {citation.document_id}")
                if citation.pmid:
                    print(f"  PMID: {citation.pmid}")
                print(f"  \"{citation.passage}\"")
                print(f"  ➤ {citation.summary}")
                print(f"  Relevance: {citation.relevance_score:.3f}")
            
            # Final statistics
            stats = citation_agent.get_citation_stats(citations)
            print(f"\n📊 Final Report Statistics:")
            print(f"   Total citations extracted: {stats['total_citations']}")
            print(f"   Average relevance score: {stats['average_relevance']:.3f}")
            print(f"   Unique documents cited: {stats['unique_documents']}")
            print(f"   Citations per document: {stats['citations_per_document']:.1f}")
            
            if 'date_range' in stats:
                print(f"   Publication date range: {stats['date_range']['earliest']} to {stats['date_range']['latest']}")
        
        else:
            print("❌ No citations met the relevance threshold")
    
    except Exception as e:
        print(f"❌ Error in workflow integration demo: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        orchestrator.stop_processing()


def main():
    """Run all citation finder demonstrations."""
    print("🎯 Citation Finder Agent Demonstration")
    print("=" * 60)
    print("This demo shows how to extract verifiable citations from")
    print("high-scoring documents to build evidence-based reports.")
    print()
    
    try:
        # Run demonstrations
        demo_direct_citation_extraction()
        demo_queue_based_citation_processing()
        demo_citation_workflow_integration()
        
        print("\n" + "="*60)
        print("✅ All citation finder demonstrations completed!")
        print("\nKey Features Demonstrated:")
        print("• Direct citation extraction from documents")
        print("• Queue-based processing for scalability")
        print("• Document ID verification and integrity")
        print("• Relevance scoring and filtering")
        print("• Integration with scoring workflow")
        print("• Citation statistics and reporting")
        print("• Memory-efficient batch processing")
        
        print("\nCitation Benefits:")
        print("• Verifiable document references") 
        print("• Extracted passages with context")
        print("• Relevance scoring for quality control")
        print("• Programmatic document ID assignment")
        print("• Protection against hallucinated citations")
        
    except KeyboardInterrupt:
        print("\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()