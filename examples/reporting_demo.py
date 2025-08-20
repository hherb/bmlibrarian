#!/usr/bin/env python3
"""
Reporting Agent Demonstration

Shows how to use the ReportingAgent to synthesize citations into 
medical publication-style reports with proper reference formatting.

This demo demonstrates:
1. Basic report generation from citations
2. Evidence strength assessment and validation
3. Vancouver-style reference formatting
4. Integration with citation extraction workflow
5. Quality control and error handling

Usage:
    python examples/reporting_demo.py
"""

import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bmlibrarian.agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent, ReportingAgent,
    AgentOrchestrator, Citation, Reference, Report
)


def setup_agents():
    """Set up orchestrator with all required agents."""
    print("🔧 Setting up orchestrator and agents...")
    
    orchestrator = AgentOrchestrator(max_workers=4, polling_interval=0.5)
    
    query_agent = QueryAgent(orchestrator=orchestrator)
    scoring_agent = DocumentScoringAgent(orchestrator=orchestrator)
    citation_agent = CitationFinderAgent(orchestrator=orchestrator)
    reporting_agent = ReportingAgent(orchestrator=orchestrator)
    
    orchestrator.register_agent("query_agent", query_agent)
    orchestrator.register_agent("document_scoring_agent", scoring_agent)
    orchestrator.register_agent("citation_finder_agent", citation_agent)
    orchestrator.register_agent("reporting_agent", reporting_agent)
    
    return orchestrator, query_agent, scoring_agent, citation_agent, reporting_agent


def create_sample_citations() -> List[Citation]:
    """Create sample citations for demonstration with realistic database IDs."""
    
    citations = [
        Citation(
            passage="Meta-analysis of 15 randomized controlled trials involving 165,000 participants demonstrated that regular aerobic exercise reduces cardiovascular mortality by 35% (95% CI: 28-42%, P<0.001) compared to sedentary controls.",
            summary="Strong evidence for cardiovascular mortality reduction with aerobic exercise",
            relevance_score=0.95,
            document_id="123456789",
            document_title="Aerobic Exercise and Cardiovascular Mortality: Systematic Review and Meta-Analysis",
            authors=["Johnson, M.A.", "Smith, R.K.", "Davis, L.M.", "Brown, P.J."],
            publication_date="2023-03-15",
            pmid="37123456"
        ),
        Citation(
            passage="High-intensity interval training (HIIT) improved left ventricular ejection fraction by 8.2% ± 3.1% in patients with heart failure (p=0.003), with significant improvements in peak oxygen consumption (12.3 ± 4.2 mL/kg/min increase).",
            summary="HIIT shows specific cardiac functional improvements in heart failure patients",
            relevance_score=0.91,
            document_id="123456790",
            document_title="High-Intensity Interval Training in Heart Failure: Cardiac Function Outcomes",
            authors=["Anderson, K.L.", "Wilson, T.R.", "Garcia, M.S.", "Miller, J.D.", "Thompson, A.B."],
            publication_date="2023-05-22",
            pmid="37234567"
        ),
        Citation(
            passage="Exercise training programs lasting ≥12 weeks resulted in significant reductions in systolic blood pressure (mean reduction: 6.9 mmHg, 95% CI: 5.1-8.7) and diastolic blood pressure (mean reduction: 4.7 mmHg, 95% CI: 3.2-6.1) in hypertensive individuals.",
            summary="Sustained exercise training provides clinically meaningful blood pressure reductions",
            relevance_score=0.88,
            document_id="123456791",
            document_title="Exercise Training and Blood Pressure Control in Hypertension: Duration-Response Analysis",
            authors=["Taylor, S.M.", "White, B.L.", "Jones, N.K."],
            publication_date="2023-01-10",
            pmid="37345678"
        ),
        Citation(
            passage="Resistance training combined with aerobic exercise demonstrated superior lipid profile improvements compared to aerobic exercise alone, with HDL cholesterol increases of 12.3% vs 7.1% (p=0.012) and triglyceride reductions of 18.7% vs 11.2% (p=0.008).",
            summary="Combined exercise modalities show additive benefits for lipid metabolism",
            relevance_score=0.84,
            document_id="123456792",
            document_title="Combined Aerobic and Resistance Exercise Effects on Lipid Metabolism",
            authors=["Lee, H.J.", "Chen, X.Y.", "Patel, R.S.", "Kumar, V.N.", "Singh, A.K.", "Williams, D.C.", "Rodriguez, E.M."],
            publication_date="2023-04-08",
            pmid="37456789"
        ),
        Citation(
            passage="Long-term follow-up (median 8.3 years) of exercise intervention participants showed sustained cardiovascular benefits with 28% lower incidence of major adverse cardiovascular events (MACE) compared to control groups, even after accounting for medication use and other lifestyle factors.",
            summary="Exercise benefits persist long-term with sustained cardiovascular event reduction",
            relevance_score=0.89,
            document_id="123456793",
            document_title="Long-term Cardiovascular Outcomes of Exercise Interventions: 8-Year Follow-up Study",
            authors=["Cooper, R.T.", "Nelson, M.P.", "Green, S.L.", "Hall, K.J."],
            publication_date="2023-06-30",
            pmid="37567890"
        )
    ]
    
    return citations


def demo_basic_report_generation():
    """Demonstrate basic report generation from citations."""
    print("\n" + "="*60)
    print("📄 Basic Report Generation Demo")
    print("="*60)
    
    orchestrator, query_agent, scoring_agent, citation_agent, reporting_agent = setup_agents()
    
    try:
        if not reporting_agent.test_connection():
            print("❌ Cannot connect to Ollama - using mock demonstration")
            return
        
        print("✅ Connected to Ollama")
        
        # Create sample citations
        citations = create_sample_citations()
        user_question = "What are the cardiovascular benefits of exercise?"
        
        print(f"❓ Question: {user_question}")
        print(f"📄 Processing {len(citations)} citations...")
        
        # Generate report
        start_time = time.time()
        formatted_report = reporting_agent.generate_citation_based_report(
            user_question=user_question,
            citations=citations,
            format_output=True
        )
        generation_time = time.time() - start_time
        
        if formatted_report:
            print(f"\n✅ Report generated in {generation_time:.1f} seconds")
            print("\n" + "="*80)
            print("GENERATED REPORT")
            print("="*80)
            print(formatted_report)
            print("="*80)
        else:
            print("❌ Report generation failed")
    
    except Exception as e:
        print(f"❌ Error in report generation demo: {e}")
        import traceback
        traceback.print_exc()


def demo_evidence_assessment_and_validation():
    """Demonstrate evidence assessment and citation validation."""
    print("\n" + "="*60)
    print("🔍 Evidence Assessment and Validation Demo")
    print("="*60)
    
    orchestrator, query_agent, scoring_agent, citation_agent, reporting_agent = setup_agents()
    
    try:
        citations = create_sample_citations()
        
        print("📋 Citation Validation:")
        print("-" * 30)
        
        # Validate citations
        valid_citations, errors = reporting_agent.validate_citations(citations)
        
        print(f"   Valid citations: {len(valid_citations)}")
        print(f"   Validation errors: {len(errors)}")
        
        if errors:
            for error in errors:
                print(f"   ❌ {error}")
        else:
            print("   ✅ All citations valid")
        
        print("\n📊 Evidence Strength Assessment:")
        print("-" * 30)
        
        # Assess evidence strength
        strength = reporting_agent.assess_evidence_strength(valid_citations)
        print(f"   Evidence strength: {strength}")
        
        # Calculate statistics for context
        if valid_citations:
            avg_relevance = sum(c.relevance_score for c in valid_citations) / len(valid_citations)
            unique_docs = len(set(c.document_id for c in valid_citations))
            
            print(f"   Citation count: {len(valid_citations)}")
            print(f"   Unique documents: {unique_docs}")
            print(f"   Average relevance: {avg_relevance:.3f}")
            
            # Provide interpretation
            if strength == "Strong":
                print("   ✅ High confidence in findings - comprehensive evidence base")
            elif strength == "Moderate":
                print("   ⚠️  Good evidence quality - findings likely reliable")
            elif strength == "Limited":
                print("   ⚠️  Limited evidence - interpret findings cautiously")
            else:
                print("   ❌ Insufficient evidence for reliable conclusions")
        
        print("\n📚 Reference Creation and Formatting:")
        print("-" * 30)
        
        # Create and display references
        references = reporting_agent.create_references(valid_citations)
        print(f"   Created {len(references)} unique references")
        
        print("\n   Vancouver-Style References:")
        for ref in references[:3]:  # Show first 3 as examples
            formatted = ref.format_vancouver_style()
            print(f"   {ref.number}. {formatted}")
        
        if len(references) > 3:
            print(f"   ... and {len(references) - 3} more references")
    
    except Exception as e:
        print(f"❌ Error in validation demo: {e}")
        import traceback
        traceback.print_exc()


def demo_quality_control_features():
    """Demonstrate quality control with problematic citations."""
    print("\n" + "="*60)
    print("🛡️ Quality Control Demo")
    print("="*60)
    
    orchestrator, query_agent, scoring_agent, citation_agent, reporting_agent = setup_agents()
    
    try:
        # Create mix of good and problematic citations
        good_citations = create_sample_citations()[:2]  # Take first 2 good ones
        
        # Add problematic citations
        problematic_citations = [
            Citation(
                passage="",  # Empty passage
                summary="Test summary",
                relevance_score=0.8,
                document_id="bad_citation_1",
                document_title="Test Study",
                authors=["Test Author"],
                publication_date="2023-01-01"
            ),
            Citation(
                passage="Valid passage content",
                summary="Test summary",
                relevance_score=1.5,  # Invalid score > 1.0
                document_id="bad_citation_2", 
                document_title="Another Test Study",
                authors=["Another Author"],
                publication_date="2023-01-01"
            ),
            Citation(
                passage="Another valid passage",
                summary="Test summary",
                relevance_score=0.7,
                document_id="",  # Empty document ID
                document_title="Third Test Study",
                authors=["Third Author"],
                publication_date="2023-01-01"
            ),
            Citation(
                passage="Low relevance passage",
                summary="Not very relevant content",
                relevance_score=0.4,  # Very low relevance
                document_id="low_relevance",
                document_title="Low Relevance Study",
                authors=["Low Relevance Author"],
                publication_date="2023-01-01"
            )
        ]
        
        all_citations = good_citations + problematic_citations
        
        print(f"🧪 Testing with {len(all_citations)} citations ({len(good_citations)} good, {len(problematic_citations)} problematic)")
        
        # Validate citations
        valid_citations, errors = reporting_agent.validate_citations(all_citations)
        
        print(f"\n📋 Validation Results:")
        print(f"   Input citations: {len(all_citations)}")
        print(f"   Valid citations: {len(valid_citations)}")
        print(f"   Validation errors: {len(errors)}")
        
        if errors:
            print("\n   ❌ Issues Found:")
            for error in errors:
                print(f"      • {error}")
        
        # Evidence assessment with different citation sets
        print(f"\n📊 Evidence Assessment Comparison:")
        
        # Good citations only
        good_strength = reporting_agent.assess_evidence_strength(good_citations)
        print(f"   Good citations only ({len(good_citations)}): {good_strength}")
        
        # Valid citations (after filtering)
        valid_strength = reporting_agent.assess_evidence_strength(valid_citations)
        print(f"   After validation ({len(valid_citations)}): {valid_strength}")
        
        # Single citation (insufficient)
        single_strength = reporting_agent.assess_evidence_strength(good_citations[:1])
        print(f"   Single citation only (1): {single_strength}")
        
        # Empty citations
        empty_strength = reporting_agent.assess_evidence_strength([])
        print(f"   No citations (0): {empty_strength}")
        
        # Try to generate report with validated citations
        print(f"\n📄 Report Generation Test:")
        if len(valid_citations) >= 2:
            print(f"   ✅ Attempting report with {len(valid_citations)} valid citations...")
            
            if reporting_agent.test_connection():
                report = reporting_agent.synthesize_report(
                    user_question="What are the cardiovascular benefits of exercise?",
                    citations=valid_citations,
                    min_citations=2
                )
                
                if report:
                    print(f"   ✅ Report generated successfully")
                    print(f"      Evidence strength: {report.evidence_strength}")
                    print(f"      References created: {len(report.references)}")
                else:
                    print(f"   ❌ Report synthesis failed")
            else:
                print(f"   ⚠️  Ollama not available - skipping synthesis test")
        else:
            print(f"   ❌ Insufficient valid citations ({len(valid_citations)}) for report generation")
    
    except Exception as e:
        print(f"❌ Error in quality control demo: {e}")
        import traceback
        traceback.print_exc()


def demo_integrated_workflow():
    """Demonstrate complete workflow from scoring to final report."""
    print("\n" + "="*60)
    print("🔗 Integrated Workflow Demo")
    print("="*60)
    
    orchestrator, query_agent, scoring_agent, citation_agent, reporting_agent = setup_agents()
    
    try:
        # Check all services
        citation_available = citation_agent.test_connection()
        reporting_available = reporting_agent.test_connection()
        
        if not (citation_available and reporting_available):
            print("❌ Ollama not available - using mock workflow demonstration")
            return
        
        print("✅ All services connected")
        orchestrator.start_processing()
        
        # Sample documents with realistic content
        documents = [
            {
                "id": 234567890,
                "title": "Exercise Training and Cardiac Rehabilitation: Systematic Review",
                "abstract": "Systematic review of 45 studies examining exercise training in cardiac rehabilitation programs. Exercise interventions lasting 12-24 weeks showed significant improvements in cardiovascular outcomes, with 32% reduction in cardiac mortality and 25% improvement in exercise capacity. Programs combining aerobic and resistance training demonstrated superior outcomes compared to aerobic training alone.",
                "authors": ["Martinez, A.", "Johnson, B.", "Smith, C."],
                "publication_date": "2023-02-15",
                "pmid": "38123456"
            },
            {
                "id": 234567891,
                "title": "Blood Pressure Response to Exercise: Dose-Response Meta-Analysis", 
                "abstract": "Meta-analysis of 73 randomized controlled trials examining blood pressure responses to exercise training. Aerobic exercise training reduced systolic blood pressure by 5.2 mmHg (95% CI: 4.1-6.3) and diastolic blood pressure by 3.8 mmHg (95% CI: 2.9-4.7). Optimal effects observed with moderate-intensity training 3-5 days per week for 30-60 minutes.",
                "authors": ["Thompson, D.", "Wilson, E.", "Davis, F.", "Brown, G."],
                "publication_date": "2023-04-20",
                "pmid": "38234567"
            },
            {
                "id": 234567892,
                "title": "Lipid Profile Changes with Exercise Training in Metabolic Syndrome",
                "abstract": "Randomized controlled trial of 180 participants with metabolic syndrome examining lipid changes after 16 weeks of supervised exercise training. HDL cholesterol increased by 14.2% (p<0.001), triglycerides decreased by 19.8% (p<0.001), and LDL cholesterol decreased by 8.7% (p=0.012). Benefits were maintained at 6-month follow-up.",
                "authors": ["Chen, H.", "Kim, J.", "Patel, K.", "Singh, L.", "Wang, M."],
                "publication_date": "2023-06-10",
                "pmid": "38345678"
            }
        ]
        
        user_question = "What are the cardiovascular benefits of exercise training?"
        
        print(f"❓ Research Question: {user_question}")
        print(f"📄 Starting with {len(documents)} documents")
        
        print("\n1️⃣ Step 1: Document Scoring")
        print("-" * 30)
        
        # Score documents
        scored_results = []
        for doc in documents:
            result = scoring_agent.evaluate_document(user_question, doc)
            if result:
                scored_results.append((doc, result))
                print(f"   📊 Doc {doc['id']}: {result['score']}/5 - {result['reasoning'][:60]}...")
        
        print(f"\n✅ Scored {len(scored_results)} documents")
        
        print("\n2️⃣ Step 2: Citation Extraction")
        print("-" * 30)
        
        # Extract citations
        citations = citation_agent.process_scored_documents_for_citations(
            user_question=user_question,
            scored_documents=scored_results,
            score_threshold=2.5,
            min_relevance=0.75
        )
        
        print(f"✅ Extracted {len(citations)} citations")
        
        if citations:
            # Show sample citations
            print("\n   Sample Citations:")
            for i, citation in enumerate(citations[:2], 1):
                print(f"   {i}. \"{citation.passage[:80]}...\"")
                print(f"      Relevance: {citation.relevance_score:.3f}")
                print(f"      Source: {citation.document_title[:50]}...")
        
        print("\n3️⃣ Step 3: Report Generation")
        print("-" * 30)
        
        if len(citations) >= 2:
            # Generate comprehensive report
            start_time = time.time()
            report = reporting_agent.synthesize_report(
                user_question=user_question,
                citations=citations,
                min_citations=2
            )
            synthesis_time = time.time() - start_time
            
            if report:
                print(f"✅ Report generated in {synthesis_time:.1f} seconds")
                print(f"   Evidence strength: {report.evidence_strength}")
                print(f"   Citations analyzed: {report.citation_count}")
                print(f"   Unique references: {report.unique_documents}")
                
                # Display formatted report
                print("\n" + "="*80)
                print("COMPLETE RESEARCH REPORT")
                print("="*80)
                
                formatted_report = reporting_agent.format_report_output(report)
                print(formatted_report)
                
                print("="*80)
                
                print(f"\n🎯 Workflow Summary:")
                print(f"   Documents processed: {len(documents)}")
                print(f"   Documents above threshold: {len([d for d, s in scored_results if s['score'] > 2.5])}")
                print(f"   Citations extracted: {len(citations)}")
                print(f"   Report evidence level: {report.evidence_strength}")
                print(f"   Total processing time: {synthesis_time + 2:.1f} seconds")  # Rough estimate including scoring
            else:
                print("❌ Report synthesis failed")
        else:
            print(f"❌ Insufficient citations ({len(citations)}) for report generation")
    
    except Exception as e:
        print(f"❌ Error in integrated workflow demo: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        orchestrator.stop_processing()


def demo_reference_formatting_styles():
    """Demonstrate different reference formatting options."""
    print("\n" + "="*60)
    print("📚 Reference Formatting Demo")
    print("="*60)
    
    orchestrator, query_agent, scoring_agent, citation_agent, reporting_agent = setup_agents()
    
    try:
        citations = create_sample_citations()
        
        print("📋 Creating References from Citations:")
        print("-" * 40)
        
        # Create references
        references = reporting_agent.create_references(citations)
        print(f"   Generated {len(references)} unique references from {len(citations)} citations")
        
        # Demonstrate Vancouver formatting
        print("\n📖 Vancouver-Style Formatting:")
        print("-" * 40)
        
        for ref in references:
            formatted = ref.format_vancouver_style()
            print(f"\n{ref.number}. {formatted}")
            print(f"   Document ID: {ref.document_id}")
            if ref.pmid:
                print(f"   PubMed URL: https://pubmed.ncbi.nlm.nih.gov/{ref.pmid}")
        
        # Show handling of many authors (et al. formatting)
        print(f"\n✂️  Author Handling Examples:")
        print("-" * 40)
        
        # Find reference with many authors
        many_author_refs = [ref for ref in references if len(ref.authors) > 6]
        if many_author_refs:
            ref = many_author_refs[0]
            print(f"   Original authors ({len(ref.authors)}): {ref.authors}")
            formatted = ref.format_vancouver_style()
            print(f"   Vancouver format: {formatted}")
            print(f"   ✅ Correctly uses 'et al.' for >6 authors")
        
        # Demonstrate citation mapping
        print(f"\n🔗 Citation-to-Reference Mapping:")
        print("-" * 40)
        
        doc_to_ref = reporting_agent.map_citations_to_references(citations, references)
        
        print("   Document ID → Reference Number:")
        for doc_id, ref_num in doc_to_ref.items():
            print(f"      {doc_id} → [{ref_num}]")
        
        # Show how this would appear in text
        print(f"\n📝 In-Text Citation Example:")
        print("-" * 40)
        
        sample_text = f"Exercise training provides significant cardiovascular benefits [{doc_to_ref[citations[0].document_id]}]. "
        sample_text += f"High-intensity interval training shows particular promise [{doc_to_ref[citations[1].document_id]}], "
        sample_text += f"while sustained programs effectively reduce blood pressure [{doc_to_ref[citations[2].document_id]}]."
        
        print(f"   {sample_text}")
    
    except Exception as e:
        print(f"❌ Error in reference formatting demo: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Run all reporting agent demonstrations."""
    print("🎯 Reporting Agent Demonstration")
    print("=" * 60)
    print("This demo shows how to synthesize citations into professional")
    print("medical publication-style reports with proper reference formatting.")
    print()
    
    try:
        # Run demonstrations
        demo_basic_report_generation()
        demo_evidence_assessment_and_validation()
        demo_quality_control_features()
        demo_reference_formatting_styles()
        demo_integrated_workflow()
        
        print("\n" + "="*60)
        print("✅ All reporting agent demonstrations completed!")
        print("\nKey Features Demonstrated:")
        print("• Medical publication-style report synthesis")
        print("• Vancouver-style reference formatting")
        print("• Evidence strength assessment")
        print("• Citation validation and quality control")
        print("• Integration with citation extraction workflow")
        print("• Professional report formatting with metadata")
        
        print("\nReporting Benefits:")
        print("• Professional medical writing style")
        print("• Proper citation numbering and formatting")
        print("• Evidence-based synthesis with quality assessment")
        print("• Comprehensive reports with methodology notes")
        print("• Integration with existing research workflows")
        
        print("\nNext Steps:")
        print("• Use with real citations from Citation Finder Agent")
        print("• Integrate into research and clinical workflows") 
        print("• Customize report formatting for specific needs")
        print("• Export reports for external documentation systems")
        
    except KeyboardInterrupt:
        print("\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()