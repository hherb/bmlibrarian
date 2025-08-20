#!/usr/bin/env python3
"""
Counterfactual Checking Agent Demonstration

This script demonstrates how to use the CounterfactualAgent to analyze documents
and generate research questions for finding contradictory evidence. This is essential
for rigorous academic research and evidence validation.

Usage:
    uv run python examples/counterfactual_demo.py
"""

import sys
import os
import logging
from typing import List

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bmlibrarian.agents import (
    CounterfactualAgent, 
    CounterfactualQuestion, 
    CounterfactualAnalysis
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def demo_basic_document_analysis():
    """Demonstrate basic document analysis with counterfactual checking."""
    print("="*80)
    print("DEMO 1: Basic Document Analysis")
    print("="*80)
    
    # Initialize the agent (uses configuration for model selection)
    agent = CounterfactualAgent()
    
    # Test connection
    if not agent.test_connection():
        print("❌ Cannot connect to Ollama. Please ensure Ollama is running.")
        print("   Start Ollama with: ollama serve")
        print("   And ensure the configured model is available")
        print("   Check bmlibrarian_config.json to see which models are configured")
        return
    
    print("✅ Connected to Ollama successfully")
    
    # Sample research paper content
    document_content = """
    Exercise and Cardiovascular Health: A Meta-Analysis
    
    Background: Physical activity has been widely promoted for cardiovascular health benefits.
    
    Methods: We conducted a systematic review and meta-analysis of 45 randomized controlled 
    trials involving 125,000 participants. Studies were included if they examined the effects 
    of structured exercise programs on cardiovascular outcomes.
    
    Results: Regular aerobic exercise was associated with a 35% reduction in cardiovascular 
    disease risk (RR=0.65, 95% CI: 0.58-0.73, p<0.001). The benefits were consistent across 
    all age groups, with stronger effects observed in participants over 60 years old. 
    High-intensity interval training showed superior results compared to moderate continuous exercise.
    
    Conclusions: Structured exercise programs provide substantial cardiovascular protection 
    across all populations. The benefits appear to be dose-dependent and universal. 
    Healthcare providers should recommend at least 150 minutes of moderate-intensity 
    exercise per week for optimal cardiovascular protection.
    """
    
    print("📄 Analyzing document: Exercise and Cardiovascular Health Meta-Analysis")
    print("⏳ Performing counterfactual analysis...")
    
    # Perform analysis
    analysis = agent.analyze_document(document_content, "Exercise Meta-Analysis")
    
    if not analysis:
        print("❌ Analysis failed. Check logs for details.")
        return
    
    print(f"✅ Analysis complete! Generated {len(analysis.counterfactual_questions)} research questions")
    print()
    
    # Display results
    print("📋 MAIN CLAIMS IDENTIFIED:")
    for i, claim in enumerate(analysis.main_claims, 1):
        print(f"   {i}. {claim}")
    print()
    
    print(f"🎯 CONFIDENCE LEVEL: {analysis.confidence_level}")
    print(f"📝 OVERALL ASSESSMENT: {analysis.overall_assessment}")
    print()
    
    # Show high priority questions
    high_priority = agent.get_high_priority_questions(analysis)
    if high_priority:
        print("🚨 HIGH PRIORITY RESEARCH QUESTIONS:")
        for i, question in enumerate(high_priority, 1):
            print(f"\n   Question {i}:")
            print(f"   ❓ {question.question}")
            print(f"   🎯 Target: {question.target_claim}")
            print(f"   💭 Reasoning: {question.reasoning}")
            print(f"   🔍 Keywords: {', '.join(question.search_keywords)}")
    
    return analysis


def demo_research_protocol_generation(analysis: CounterfactualAnalysis):
    """Demonstrate research protocol generation."""
    print("\n" + "="*80)
    print("DEMO 2: Research Protocol Generation")
    print("="*80)
    
    if not analysis:
        print("❌ No analysis available for protocol generation")
        return
    
    agent = CounterfactualAgent()
    
    print("📋 Generating systematic research protocol...")
    protocol = agent.generate_research_protocol(analysis)
    
    print("✅ Research protocol generated!")
    print("\n" + "-"*60)
    print(protocol)
    print("-"*60)
    
    # Save protocol to file
    protocol_filename = "counterfactual_research_protocol.md"
    try:
        with open(protocol_filename, "w", encoding="utf-8") as f:
            f.write(protocol)
        print(f"💾 Protocol saved to: {protocol_filename}")
    except Exception as e:
        print(f"❌ Failed to save protocol: {e}")


def demo_search_query_generation(analysis: CounterfactualAnalysis):
    """Demonstrate search query formatting."""
    print("\n" + "="*80) 
    print("DEMO 3: Database Query Generation")
    print("="*80)
    
    if not analysis:
        print("❌ No analysis available for search query generation")
        return
    
    agent = CounterfactualAgent()
    
    # Import QueryAgent for proper database query formatting
    from bmlibrarian.agents import QueryAgent
    query_agent = QueryAgent()
    
    print("🔍 GENERATING DATABASE-READY QUERIES...")
    
    # Generate proper database queries using QueryAgent integration
    research_queries = agent.generate_research_queries_with_agent(
        analysis.counterfactual_questions[:3], # Limit to first 3 for demo
        query_agent
    )
    
    print("✅ PostgreSQL to_tsquery formatted queries:")
    for i, query_info in enumerate(research_queries, 1):
        print(f"\n   Query {i} (Priority: {query_info['priority']}):")
        print(f"   ❓ Research Question: {query_info['question']}")
        print(f"   🎯 Target Claim: {query_info['target_claim']}")
        print(f"   🔍 Database Query: {query_info['db_query']}")
        print(f"   📝 Keywords: {', '.join(query_info['search_keywords'])}")
    
    # Also show the simpler format
    print("\n" + "-"*60)
    print("🏃‍♂️ QUICK FORMAT (without QueryAgent):")
    simple_queries = agent.format_questions_for_search(analysis.counterfactual_questions[:2])
    for i, query in enumerate(simple_queries, 1):
        print(f"\n   Simple Query {i}: {query}")
    
    # Show how to use with database
    print("\n📚 USAGE WITH BMLibrarian DATABASE:")
    print("   from bmlibrarian.database import find_abstracts")
    print("   results = find_abstracts(query, limit=20)")
    print("   # Use results to find contradictory evidence")
    
    # Demonstrate actual database search (if available)
    try:
        from bmlibrarian.database import find_abstracts
        if research_queries:
            print("\n🔍 TESTING FIRST QUERY AGAINST DATABASE:")
            test_query = research_queries[0]['db_query']
            print(f"   Query: {test_query}")
            
            results_generator = find_abstracts(test_query, max_rows=3, plain=False)
            results = list(results_generator)
            if results:
                print(f"   ✅ Found {len(results)} potential contradictory studies:")
                for i, result in enumerate(results[:2], 1):
                    title = result.get('title', 'No title')[:100] + "..." if len(result.get('title', '')) > 100 else result.get('title', 'No title')
                    print(f"      {i}. {title}")
            else:
                print("   📭 No results found (query may be too specific)")
    except ImportError:
        print("   💡 Database module not available in demo environment")
    except Exception as e:
        print(f"   ⚠️  Database query failed: {e}")


def demo_medical_guideline_analysis():
    """Demonstrate analysis of clinical practice guidelines."""
    print("\n" + "="*80)
    print("DEMO 4: Clinical Guideline Analysis")
    print("="*80)
    
    agent = CounterfactualAgent()
    
    guideline_content = """
    Clinical Practice Guidelines: Management of Type 2 Diabetes
    
    Recommendation 1: Metformin should be the first-line pharmacological therapy 
    for all patients with type 2 diabetes, unless contraindicated. 
    (Strong recommendation, high-quality evidence)
    
    Recommendation 2: Target HbA1c should be <7% for most adults with diabetes. 
    More stringent goals (<6.5%) may be appropriate for selected patients if 
    achievable without significant hypoglycemia or other adverse effects.
    
    Recommendation 3: Lifestyle modifications including dietary changes and 
    physical activity should be implemented at diagnosis and maintained throughout 
    treatment. These interventions can reduce HbA1c by 1-2% when implemented effectively.
    
    Recommendation 4: SGLT2 inhibitors or GLP-1 receptor agonists should be 
    considered as second-line therapy in patients with established cardiovascular 
    disease or at high cardiovascular risk.
    """
    
    print("📄 Analyzing clinical practice guidelines...")
    analysis = agent.analyze_document(guideline_content, "Diabetes Management Guidelines")
    
    if analysis:
        print(f"✅ Guideline analysis complete!")
        print(f"   Main recommendations identified: {len(analysis.main_claims)}")
        print(f"   Counterfactual questions generated: {len(analysis.counterfactual_questions)}")
        print(f"   Confidence in recommendations: {analysis.confidence_level}")
        
        # Show a few sample questions
        print("\n🔍 SAMPLE VALIDATION QUESTIONS:")
        for i, question in enumerate(analysis.counterfactual_questions[:3], 1):
            print(f"\n   {i}. {question.question}")
            print(f"      Priority: {question.priority}")
    else:
        print("❌ Guideline analysis failed")


def demo_progress_tracking():
    """Demonstrate progress tracking with callbacks."""
    print("\n" + "="*80)
    print("DEMO 5: Progress Tracking")
    print("="*80)
    
    # Define a callback function
    progress_steps = []
    
    def progress_callback(step: str, data: str):
        progress_steps.append((step, data))
        print(f"📊 Progress: [{step}] {data}")
    
    # Initialize agent with callback
    agent = CounterfactualAgent(callback=progress_callback)
    
    sample_content = """
    Omega-3 Fatty Acids and Cognitive Function in Aging
    
    A recent randomized controlled trial of 2,000 elderly participants found that 
    daily omega-3 supplementation (2g EPA/DHA) significantly improved cognitive 
    test scores over 12 months compared to placebo (p<0.05). The benefits were 
    most pronounced in participants with mild cognitive impairment at baseline.
    """
    
    print("🧠 Analyzing omega-3 and cognitive function study with progress tracking...")
    
    analysis = agent.analyze_document(sample_content, "Omega-3 Cognitive Study")
    
    print(f"\n📈 Progress tracking complete! Captured {len(progress_steps)} steps:")
    for step, data in progress_steps:
        print(f"   • {step}: {data}")
    
    if analysis:
        print(f"\n✅ Analysis generated {len(analysis.counterfactual_questions)} questions")


def main():
    """Run all counterfactual checking demonstrations."""
    print("🧠 BMLibrarian Counterfactual Checking Agent Demo")
    print("This demo shows how to critically analyze research documents")
    print("and generate questions to find contradictory evidence.\n")
    
    try:
        # Demo 1: Basic analysis
        analysis = demo_basic_document_analysis()
        
        if analysis:
            # Demo 2: Protocol generation
            demo_research_protocol_generation(analysis)
            
            # Demo 3: Search queries
            demo_search_query_generation(analysis)
        
        # Demo 4: Clinical guidelines
        demo_medical_guideline_analysis()
        
        # Demo 5: Progress tracking
        demo_progress_tracking()
        
        print("\n" + "="*80)
        print("✅ DEMO COMPLETE")
        print("="*80)
        print("Key takeaways:")
        print("• Counterfactual checking helps identify potential weaknesses in research")
        print("• Generated questions target methodological limitations and alternative explanations")
        print("• Research protocols provide systematic frameworks for validation")
        print("• The agent integrates with existing BMLibrarian workflows")
        print("\nNext steps:")
        print("• Use generated search queries to find contradictory studies")
        print("• Incorporate validation findings into your research reports")
        print("• Apply counterfactual checking to your own research documents")
        
    except KeyboardInterrupt:
        print("\n❌ Demo interrupted by user")
    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)
        print(f"❌ Demo failed: {e}")


if __name__ == "__main__":
    main()