#!/usr/bin/env python3
"""
Complete Counterfactual Literature Search Example

This script demonstrates the full workflow:
1. Analyze a document with CounterfactualAgent
2. Generate database queries with QueryAgent integration
3. Search the BMLibrarian database for contradictory evidence
4. Present findings with document scores and citations

Usage:
    uv run python examples/counterfactual_literature_search.py
"""

import sys
import os
import logging
from typing import List, Dict, Any

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bmlibrarian.agents import (
    CounterfactualAgent,
    QueryAgent,
    DocumentScoringAgent,
    CitationFinderAgent
)

try:
    from bmlibrarian.database import find_abstracts
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    print("⚠️  Database not available in this environment")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main_example():
    """Complete example of finding contradictory literature."""
    print("🧠 BMLibrarian Counterfactual Literature Search")
    print("Complete workflow from document analysis to contradictory evidence discovery")
    print("="*80)
    
    # Sample research document to analyze
    document_content = """
    Mediterranean Diet and Cognitive Decline Prevention
    
    Background: The Mediterranean diet has been extensively studied for its potential 
    cognitive benefits in aging populations.
    
    Methods: We conducted a systematic review of 23 randomized controlled trials 
    involving 45,000 participants aged 60-85 years. Studies examined adherence to 
    Mediterranean diet patterns and cognitive outcomes over 2-10 years.
    
    Results: High adherence to Mediterranean diet was associated with a 35% reduction 
    in cognitive decline risk (HR=0.65, 95% CI: 0.52-0.81, p<0.001). The protective 
    effects were strongest for executive function and memory domains. Benefits were 
    observed across all age groups and education levels, with no significant 
    heterogeneity between studies.
    
    Conclusions: Mediterranean diet provides robust protection against cognitive 
    decline in older adults. The evidence supports universal dietary recommendations 
    for dementia prevention. Healthcare providers should actively promote 
    Mediterranean dietary patterns for all patients over 60 years old.
    """
    
    document_title = "Mediterranean Diet and Cognitive Decline Prevention"
    
    # Step 1: Analyze document for counterfactual questions
    print("📄 STEP 1: Analyzing document for potential contradictory evidence needs")
    print("-" * 60)
    
    counterfactual_agent = CounterfactualAgent()
    
    if not counterfactual_agent.test_connection():
        print("❌ Cannot connect to Ollama. Please ensure Ollama is running.")
        return
    
    print("⏳ Performing counterfactual analysis...")
    analysis = counterfactual_agent.analyze_document(document_content, document_title)
    
    if not analysis:
        print("❌ Counterfactual analysis failed")
        return
    
    print(f"✅ Analysis complete!")
    print(f"   📋 Main claims identified: {len(analysis.main_claims)}")
    print(f"   ❓ Research questions generated: {len(analysis.counterfactual_questions)}")
    print(f"   🎯 Confidence in original claims: {analysis.confidence_level}")
    
    # Show the main claims
    print("\n📋 MAIN CLAIMS TO VALIDATE:")
    for i, claim in enumerate(analysis.main_claims, 1):
        print(f"   {i}. {claim}")
    
    # Step 2: Generate database queries
    print(f"\n🔍 STEP 2: Generating database queries for contradictory evidence")
    print("-" * 60)
    
    query_agent = QueryAgent()  # Uses config for model selection
    
    # Focus on high priority questions
    high_priority_questions = counterfactual_agent.get_high_priority_questions(analysis)
    print(f"🚨 Focusing on {len(high_priority_questions)} HIGH PRIORITY questions:")
    
    research_queries = counterfactual_agent.generate_research_queries_with_agent(
        high_priority_questions, query_agent
    )
    
    for i, query_info in enumerate(research_queries, 1):
        print(f"\n   Question {i}:")
        print(f"   ❓ {query_info['question']}")
        print(f"   🎯 Targets: {query_info['target_claim']}")
        print(f"   🔍 Database Query: {query_info['db_query']}")
    
    # Step 3: Search for contradictory literature
    print(f"\n📚 STEP 3: Searching BMLibrarian database for contradictory evidence")
    print("-" * 60)
    
    if not DATABASE_AVAILABLE:
        print("💡 Database not available - showing simulated results")
        simulate_database_results(research_queries)
        return
    
    all_contradictory_evidence = []
    
    for i, query_info in enumerate(research_queries, 1):
        print(f"\n🔍 Searching for evidence against: {query_info['target_claim']}")
        print(f"   Query: {query_info['db_query']}")
        
        try:
            # find_abstracts returns a generator and uses max_rows parameter
            results_generator = find_abstracts(
                query_info['db_query'], 
                max_rows=10,
                plain=False  # Use advanced to_tsquery syntax
            )
            results = list(results_generator)
            
            if results:
                print(f"   ✅ Found {len(results)} potentially contradictory studies")
                
                # Score the documents for relevance to the counterfactual question
                print("   📊 Scoring documents for relevance...")
                scoring_agent = DocumentScoringAgent()  # Uses config for model selection
                
                scored_results = []
                for result in results:
                    score_result = scoring_agent.evaluate_document(
                        query_info['question'], result
                    )
                    if score_result and score_result['score'] >= 3:  # Only high-relevance docs
                        scored_results.append({
                            'document': result,
                            'score': score_result['score'],
                            'reasoning': score_result['reasoning'],
                            'query_info': query_info
                        })
                
                if scored_results:
                    print(f"   🎯 {len(scored_results)} highly relevant contradictory studies found")
                    all_contradictory_evidence.extend(scored_results)
                    
                    # Show top results
                    for j, evidence in enumerate(scored_results[:3], 1):
                        doc = evidence['document']
                        title = doc.get('title', 'Unknown Title')[:100] + "..." if len(doc.get('title', '')) > 100 else doc.get('title', 'Unknown Title')
                        print(f"      {j}. [{evidence['score']}/5] {title}")
                        print(f"         Relevance: {evidence['reasoning'][:100]}...")
                else:
                    print("   📭 No highly relevant contradictory evidence found")
            else:
                print("   📭 No results found for this query")
                
        except Exception as e:
            print(f"   ❌ Database search failed: {e}")
    
    # Step 4: Extract citations from contradictory evidence
    if all_contradictory_evidence:
        print(f"\n📖 STEP 4: Extracting specific contradictory citations")
        print("-" * 60)
        
        citation_agent = CitationFinderAgent()  # Uses config for model selection
        contradictory_citations = []
        
        for evidence in all_contradictory_evidence[:5]:  # Process top 5 pieces of evidence
            doc = evidence['document']
            query_info = evidence['query_info']
            
            print(f"📄 Extracting citations from: {doc.get('title', 'Unknown')[:80]}...")
            
            citation = citation_agent.extract_citation_from_document(
                query_info['question'], doc, min_relevance=0.6
            )
            
            if citation:
                contradictory_citations.append({
                    'citation': citation,
                    'original_claim': query_info['target_claim'],
                    'counterfactual_question': query_info['question']
                })
        
        # Step 5: Present final contradictory evidence report
        print(f"\n📋 STEP 5: Contradictory Evidence Report")
        print("=" * 60)
        
        if contradictory_citations:
            print(f"🚨 FOUND {len(contradictory_citations)} PIECES OF CONTRADICTORY EVIDENCE:")
            
            for i, evidence in enumerate(contradictory_citations, 1):
                citation = evidence['citation']
                print(f"\n--- CONTRADICTORY EVIDENCE {i} ---")
                print(f"🎯 Original Claim: {evidence['original_claim']}")
                print(f"❓ Research Question: {evidence['counterfactual_question']}")
                print(f"📚 Source: {citation.document_title}")
                print(f"👥 Authors: {', '.join(citation.authors[:3])}{'...' if len(citation.authors) > 3 else ''}")
                print(f"📅 Published: {citation.publication_date}")
                print(f"⭐ Relevance Score: {citation.relevance_score:.2f}")
                print(f"📝 Summary: {citation.summary}")
                print(f"📖 Key Passage:")
                print(f"    \"{citation.passage[:300]}...\"")
                
                if citation.pmid:
                    print(f"🔗 PMID: {citation.pmid}")
        else:
            print("✅ No strong contradictory evidence found - original claims appear robust")
    
    else:
        print("\n✅ CONCLUSION: No significant contradictory evidence discovered")
        print("The original document's claims appear to be well-supported by current literature.")
    
    # Generate final assessment
    print(f"\n🎯 FINAL ASSESSMENT")
    print("-" * 40)
    print(f"Document analyzed: {document_title}")
    print(f"Research questions generated: {len(analysis.counterfactual_questions)}")
    print(f"High-priority questions: {len(high_priority_questions)}")
    print(f"Database searches performed: {len(research_queries)}")
    if DATABASE_AVAILABLE:
        print(f"Contradictory evidence pieces found: {len(all_contradictory_evidence)}")
        if all_contradictory_evidence:
            print(f"Strong contradictory citations: {len(contradictory_citations) if 'contradictory_citations' in locals() else 0}")
            print("\n💡 RECOMMENDATION: Review contradictory evidence and consider:")
            print("   • Limitations in original study populations")
            print("   • Methodological differences between studies") 
            print("   • Potential confounding factors")
            print("   • Need for additional research")
        else:
            print(f"✅ The original document's claims appear robust against contradictory evidence.")
    
    print(f"\nOriginal confidence level: {analysis.confidence_level}")
    if DATABASE_AVAILABLE and all_contradictory_evidence:
        print("Revised confidence level: MEDIUM-LOW (due to contradictory evidence found)")
    else:
        print("Confidence level maintained: Claims appear well-supported")


def simulate_database_results(research_queries: List[Dict[str, Any]]):
    """Simulate database results when database is not available."""
    print("🎭 SIMULATING DATABASE SEARCH RESULTS:")
    
    # Simulated contradictory findings
    simulated_findings = [
        {
            'title': 'Mediterranean Diet Effects in Populations with Genetic Predispositions to Dementia',
            'authors': ['Smith, J.', 'Johnson, M.', 'Williams, R.'],
            'year': '2023',
            'finding': 'No significant cognitive benefits observed in APOE ε4 carriers',
            'relevance_score': 4.2
        },
        {
            'title': 'Socioeconomic Factors and Mediterranean Diet Compliance: A Confounding Analysis', 
            'authors': ['Garcia, A.', 'Brown, K.', 'Davis, L.'],
            'year': '2022',
            'finding': 'Benefits may be confounded by education and income levels',
            'relevance_score': 3.8
        },
        {
            'title': 'Long-term Mediterranean Diet Adherence and Cognitive Outcomes: Null Results',
            'authors': ['Wilson, P.', 'Moore, C.', 'Taylor, S.'],
            'year': '2023', 
            'finding': 'No cognitive benefits after 15-year follow-up in large cohort',
            'relevance_score': 4.5
        }
    ]
    
    for i, query_info in enumerate(research_queries[:2], 1):  # Show first 2 queries
        print(f"\n🔍 Query {i}: {query_info['db_query']}")
        print(f"   Target: {query_info['target_claim']}")
        print("   📚 Simulated contradictory evidence found:")
        
        for j, finding in enumerate(simulated_findings, 1):
            if j > 2:  # Limit to 2 per query
                break
            print(f"      {j}. [{finding['relevance_score']}/5] {finding['title']}")
            print(f"         Key Finding: {finding['finding']}")
            print(f"         Authors: {', '.join(finding['authors'])}")
            print(f"         Year: {finding['year']}")
    
    print(f"\n🎯 SIMULATED CONCLUSION:")
    print(f"   • Found potential methodological limitations")
    print(f"   • Identified population-specific exceptions") 
    print(f"   • Discovered confounding factors")
    print(f"   • Recommended further investigation of genetic and socioeconomic variables")


if __name__ == "__main__":
    try:
        main_example()
        
        print("\n" + "="*80)
        print("✅ COUNTERFACTUAL LITERATURE SEARCH COMPLETE")
        print("="*80)
        print("This workflow demonstrates:")
        print("• Systematic analysis of research claims")
        print("• Intelligent generation of counterfactual research questions")
        print("• Database-ready query generation") 
        print("• Automated literature search for contradictory evidence")
        print("• Document scoring and relevance assessment")
        print("• Citation extraction from contradictory sources")
        print("• Comprehensive evidence evaluation report")
        
    except KeyboardInterrupt:
        print("\n❌ Search interrupted by user")
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        print(f"❌ Search failed: {e}")