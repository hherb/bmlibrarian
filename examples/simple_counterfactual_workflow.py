#!/usr/bin/env python3
"""
Simple Counterfactual Literature Search Example

This script demonstrates the complete workflow using the CounterfactualAgent's
find_contradictory_literature() method - a one-stop solution for finding
contradictory evidence in the literature.

Usage:
    uv run python examples/simple_counterfactual_workflow.py
"""

import sys
import os
import logging

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bmlibrarian.agents import CounterfactualAgent

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def progress_callback(step: str, data: str):
    """Callback to track workflow progress."""
    print(f"📊 {step.upper()}: {data}")

def main():
    print("🧠 Simple Counterfactual Literature Search")
    print("Using the complete workflow method")
    print("="*60)
    
    # Sample document claiming strong benefits
    document_content = """
    Intermittent Fasting and Metabolic Health: A Comprehensive Review
    
    Introduction: Intermittent fasting (IF) has gained popularity as a weight 
    management and health optimization strategy.
    
    Methods: We systematically reviewed 42 randomized controlled trials 
    involving 12,000 participants examining various IF protocols (16:8, 5:2, 
    alternate day fasting) on metabolic outcomes.
    
    Results: IF demonstrated significant benefits across multiple metrics:
    - Average weight loss: 8.2% of body weight (p<0.001)
    - Improved insulin sensitivity: 25% reduction in HOMA-IR (p<0.001)  
    - Reduced inflammation: 30% decrease in CRP levels (p<0.001)
    - Enhanced autophagy markers increased by 40% (p<0.001)
    - No significant adverse effects reported
    
    The benefits were consistent across all IF protocols and appeared 
    independent of caloric restriction. Effects were observed in both 
    healthy individuals and those with metabolic syndrome.
    
    Conclusions: Intermittent fasting provides robust metabolic benefits 
    that exceed simple caloric restriction effects. The evidence supports 
    recommending IF as a first-line intervention for metabolic health 
    optimization in all adult populations.
    """
    
    # Initialize CounterfactualAgent with progress tracking (uses config for model)
    agent = CounterfactualAgent()
    agent.set_callback(progress_callback)
    
    if not agent.test_connection():
        print("❌ Cannot connect to Ollama")
        return
    
    print("🔍 Starting complete counterfactual literature search...")
    print("This will:")
    print("  1. Analyze claims in the document")
    print("  2. Generate research questions for contradictory evidence") 
    print("  3. Search BMLibrarian database")
    print("  4. Score and filter results")
    print("  5. Extract specific contradictory citations")
    print()
    
    # Execute the complete workflow
    result = agent.find_contradictory_literature(
        document_content=document_content,
        document_title="Intermittent Fasting Review",
        max_results_per_query=15,
        min_relevance_score=3
    )
    
    # Display results
    print("\n" + "="*60)
    print("📋 WORKFLOW RESULTS")
    print("="*60)
    
    summary = result['summary']
    print(f"📄 Document: {summary.get('document_title', 'Unknown')}")
    print(f"🎯 Original Confidence: {summary.get('original_confidence', 'Unknown')}")
    print(f"📊 Claims Analyzed: {summary.get('claims_analyzed', 0)}")
    print(f"❓ Research Questions Generated: {summary.get('questions_generated', 0)}")
    print(f"🚨 High Priority Questions: {summary.get('high_priority_questions', 0)}")
    print(f"🔍 Database Searches: {summary.get('database_searches', 0)}")
    
    if summary.get('database_available', False):
        print(f"📚 Contradictory Documents Found: {summary.get('contradictory_documents_found', 0)}")
        print(f"📖 Contradictory Citations Extracted: {summary.get('contradictory_citations_extracted', 0)}")
        print(f"🎯 Revised Confidence: {summary.get('revised_confidence', 'Unknown')}")
        
        # Show main claims that were analyzed
        analysis = result['analysis']
        if analysis:
            print(f"\n📋 MAIN CLAIMS ANALYZED:")
            for i, claim in enumerate(analysis.main_claims, 1):
                print(f"   {i}. {claim}")
        
        # Show contradictory evidence found
        contradictory_citations = result.get('contradictory_citations', [])
        if contradictory_citations:
            print(f"\n🚨 CONTRADICTORY EVIDENCE FOUND:")
            
            for i, evidence in enumerate(contradictory_citations[:3], 1):  # Show top 3
                citation = evidence['citation']
                print(f"\n--- Evidence {i} ---")
                print(f"🎯 Targets Claim: {evidence['original_claim']}")
                print(f"❓ Research Question: {evidence['counterfactual_question']}")
                print(f"📚 Source: {citation.document_title}")
                print(f"👥 Authors: {', '.join(citation.authors[:2])}{'...' if len(citation.authors) > 2 else ''}")
                print(f"📅 Published: {citation.publication_date}")
                print(f"⭐ Relevance Score: {citation.relevance_score:.2f}")
                print(f"📊 Document Score: {evidence['document_score']}/5")
                print(f"📝 Key Finding: {citation.summary}")
                print(f"📖 Contradictory Passage:")
                print(f"    \"{citation.passage[:250]}...\"")
                
                if citation.pmid:
                    print(f"🔗 PMID: {citation.pmid}")
            
            if len(contradictory_citations) > 3:
                print(f"\n... and {len(contradictory_citations) - 3} more contradictory citations")
                
            print(f"\n⚠️  IMPLICATIONS:")
            print(f"   • The original document's claims may be overstated")
            print(f"   • Consider population-specific limitations")
            print(f"   • Review methodological differences") 
            print(f"   • Additional research may be needed")
            
        else:
            print(f"\n✅ NO SIGNIFICANT CONTRADICTORY EVIDENCE FOUND")
            print(f"   The original document's claims appear robust against current literature")
    else:
        print(f"💡 Database not available - analysis completed but no literature search performed")
    
    # Generate final recommendation
    print(f"\n🎯 FINAL RECOMMENDATION")
    print("-" * 40)
    
    if result.get('contradictory_citations'):
        print("🔄 CRITICAL REVIEW NEEDED")
        print("Strong contradictory evidence found. Recommend:")
        print("• Reviewing methodology of original studies")
        print("• Considering population-specific effects")  
        print("• Investigating potential confounding factors")
        print("• Updating conclusions to reflect limitations")
    else:
        print("✅ CLAIMS APPEAR ROBUST")
        print("No significant contradictory evidence found.")
        print("Original document conclusions appear well-supported.")
    
    print(f"\n📊 Confidence Assessment:")
    original_conf = summary.get('original_confidence', 'UNKNOWN')
    revised_conf = summary.get('revised_confidence', original_conf)
    
    if original_conf != revised_conf:
        print(f"   Original: {original_conf} → Revised: {revised_conf}")
        print("   ⚠️  Confidence decreased due to contradictory findings")
    else:
        print(f"   Maintained: {original_conf}")
        print("   ✅ No contradictory evidence found")

if __name__ == "__main__":
    try:
        main()
        
        print("\n" + "="*60)
        print("✅ COUNTERFACTUAL ANALYSIS COMPLETE")
        print("="*60)
        print("This workflow provides:")
        print("• Systematic claim validation")
        print("• Automated contradictory evidence discovery")
        print("• Confidence level adjustment based on findings")
        print("• Actionable recommendations for further research")
        
    except KeyboardInterrupt:
        print("\n❌ Analysis interrupted by user")
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        logging.exception("Analysis failed")