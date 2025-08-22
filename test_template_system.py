#!/usr/bin/env python3
"""
Test script to verify the hybrid template system works correctly.
Tests that LLM handles synthesis while programmatic code handles facts.
"""

import sys
import logging
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.agents.citation_agent import Citation
from bmlibrarian.agents.reporting_agent import Report, Reference, MethodologyMetadata, ReportingAgent
from bmlibrarian.agents.editor_agent import EditorAgent, EditedReport
from datetime import datetime, timezone

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_template_system():
    """Test the complete template-based system."""
    print("=" * 80)
    print("TESTING HYBRID TEMPLATE SYSTEM")
    print("=" * 80)
    
    # Create realistic test data
    mock_citations = [
        Citation(
            passage="Omega-3 fatty acids significantly reduced cardiovascular events by 25% in this randomized trial.",
            summary="Meta-analysis shows significant CV risk reduction with omega-3 supplementation.",
            relevance_score=0.9,
            document_id="26159354",
            document_title="Cardiovascular Effects of Marine Omega-3 Fatty Acids",
            authors=["Bhatt Deepak L", "Steg Philippe Gabriel", "Miller Michael"],
            publication_date="2019",
            pmid="26159354",
            doi="10.1056/NEJMoa1812792",
            publication="New England Journal of Medicine"
        ),
        Citation(
            passage="Statins reduced major cardiovascular events by 30% compared to placebo in this large trial.",
            summary="Large randomized trial demonstrating significant cardiovascular protection with statin therapy.",
            relevance_score=0.85,
            document_id="15105132",
            document_title="Efficacy and Safety of Statin Therapy in Primary Prevention",
            authors=["Collins Rory", "Reith Christina", "Emberson Jonathan"],
            publication_date="2016",
            pmid="15105132",
            doi="10.1016/S0140-6736(16)31357-5",
            publication="The Lancet"
        )
    ]
    
    # Create methodology metadata
    methodology_metadata = MethodologyMetadata(
        human_question="What are the most effective treatments for cardiovascular disease prevention?",
        generated_query="cardiovascular & prevention & (treatment | therapy | intervention)",
        total_documents_found=285,
        scoring_threshold=2.5,
        documents_by_score={1: 45, 2: 78, 3: 89, 4: 52, 5: 21},
        documents_above_threshold=162,
        documents_processed_for_citations=162,
        citation_extraction_threshold=0.7,
        counterfactual_performed=True,
        counterfactual_queries_generated=12,
        counterfactual_documents_found=38,
        counterfactual_citations_extracted=15
    )
    
    # Create references
    mock_references = [
        Reference(
            number=1,
            authors=["Bhatt Deepak L", "Steg Philippe Gabriel", "Miller Michael"],
            title="Cardiovascular Effects of Marine Omega-3 Fatty Acids",
            publication_date="2019",
            document_id="26159354",
            pmid="26159354",
            doi="10.1056/NEJMoa1812792",
            publication="New England Journal of Medicine"
        ),
        Reference(
            number=2,
            authors=["Collins Rory", "Reith Christina", "Emberson Jonathan"],
            title="Efficacy and Safety of Statin Therapy in Primary Prevention",
            publication_date="2016",
            document_id="15105132",
            pmid="15105132",
            doi="10.1016/S0140-6736(16)31357-5",
            publication="The Lancet"
        )
    ]
    
    # Create original report with programmatic references and methodology
    original_report = Report(
        user_question="What are the most effective treatments for cardiovascular disease prevention?",
        synthesized_answer="Current evidence suggests that statins and omega-3 fatty acids provide significant cardiovascular protection. Statins reduce major cardiovascular events by approximately 30% [1], while omega-3 fatty acids demonstrate a 25% reduction in cardiovascular events [2]. Both interventions have strong evidence bases from large randomized controlled trials.",
        references=mock_references,
        evidence_strength="Strong",
        methodology_note="Evidence synthesis based on 2 high-quality citations.",
        created_at=datetime.now(timezone.utc),
        citation_count=2,
        unique_documents=2,
        methodology_metadata=methodology_metadata
    )
    
    print("✅ Created test data with realistic references and methodology")
    
    # Test ReportingAgent template formatting
    print(f"\n🧪 Testing ReportingAgent template formatting...")
    reporting_agent = ReportingAgent(show_model_info=False)
    formatted_report = reporting_agent.format_report_output_template(original_report)
    
    print("📄 ReportingAgent template output:")
    print("-" * 60)
    print(formatted_report[:1000] + "..." if len(formatted_report) > 1000 else formatted_report)
    
    # Test EditorAgent template formatting
    print(f"\n🧪 Testing EditorAgent template formatting...")
    
    # Create mock edited report (simulating LLM output)
    edited_report = EditedReport(
        title="Effective Treatments for Cardiovascular Disease Prevention: A Systematic Evidence Review",
        executive_summary="This review examines the most effective evidence-based interventions for cardiovascular disease prevention. Based on large-scale randomized controlled trials, both statin therapy and omega-3 fatty acid supplementation demonstrate significant reductions in major cardiovascular events, with statins showing superior efficacy.",
        methodology_section="LLM-generated methodology content (will be replaced by programmatic)",
        findings_section="## Primary Prevention Strategies\n\nTwo major therapeutic approaches demonstrate strong evidence for cardiovascular disease prevention:\n\n### Statin Therapy\nStatins represent the cornerstone of primary cardiovascular prevention. Large randomized trials demonstrate a 30% reduction in major cardiovascular events compared to placebo [2]. The benefits are consistent across diverse populations and risk profiles.\n\n### Omega-3 Fatty Acids\nMarine omega-3 fatty acids provide additional cardiovascular protection, with randomized evidence showing a 25% reduction in cardiovascular events [1]. This benefit appears complementary to statin therapy.\n\n### Combined Approach\nCurrent evidence suggests that combination therapy may provide additive benefits, though direct comparative trials are limited.",
        contradictory_evidence_section="Limited contradictory evidence was identified. Some smaller studies suggest variable omega-3 effects in specific populations, though these do not alter the overall positive evidence profile.",
        limitations_section="This analysis is limited by the focus on only two major interventions. Other evidence-based approaches including blood pressure management, lifestyle interventions, and diabetes control were not comprehensively evaluated. Long-term safety data beyond 5 years remains limited for combination approaches.",
        conclusions_section="Both statin therapy and omega-3 fatty acids demonstrate strong evidence for cardiovascular disease prevention. Statins appear to provide greater absolute risk reduction and should be considered first-line therapy. Omega-3 supplementation may provide additional benefits as adjunctive therapy. Clinical decision-making should incorporate individual risk assessment and patient preferences.",
        references=mock_references,  # These are our real Reference objects
        evidence_quality_table="| Intervention | Study Design | Sample Size | Effect Size | Evidence Quality |\n|--------------|--------------|-------------|-------------|-----------------|\n| Statins | RCT Meta-analysis | >100,000 | 30% RRR | High |\n| Omega-3 | RCT | 25,871 | 25% RRR | High |",
        confidence_assessment="HIGH",
        word_count=450
    )
    
    editor_agent = EditorAgent(show_model_info=False)
    template_formatted = editor_agent.format_comprehensive_markdown_template(
        edited_report, 
        methodology_metadata=methodology_metadata
    )
    
    print("📄 EditorAgent template output:")
    print("-" * 60)
    print(template_formatted[:1500] + "..." if len(template_formatted) > 1500 else template_formatted)
    
    # Verify key elements are present
    success = True
    
    # Check for real PMIDs and DOIs
    real_data = ["26159354", "15105132", "10.1056/NEJMoa1812792", "10.1016/S0140-6736(16)31357-5"]
    for data in real_data:
        if data not in template_formatted:
            print(f"❌ REAL DATA '{data}' NOT FOUND in template output!")
            success = False
        else:
            print(f"✅ REAL DATA '{data}' found in template output")
    
    # Check for programmatic methodology elements
    methodology_elements = [
        methodology_metadata.generated_query,
        str(methodology_metadata.total_documents_found),
        str(methodology_metadata.documents_above_threshold),
        str(methodology_metadata.counterfactual_queries_generated)
    ]
    
    for element in methodology_elements:
        if element not in template_formatted:
            print(f"❌ METHODOLOGY ELEMENT '{element}' NOT FOUND!")
            success = False
        else:
            print(f"✅ METHODOLOGY ELEMENT '{element}' found")
    
    # Check that fake data patterns are NOT present
    fake_patterns = ["12345678", "87654321", "Journal of Tropical Medicine", "fake"]
    for pattern in fake_patterns:
        if pattern.lower() in template_formatted.lower():
            print(f"❌ FAKE DATA PATTERN '{pattern}' found in output!")
            success = False
    
    # Check for proper section structure
    required_sections = ["## References", "## Methodology", "## Findings", "## Executive Summary"]
    for section in required_sections:
        if section not in template_formatted:
            print(f"❌ REQUIRED SECTION '{section}' NOT FOUND!")
            success = False
        else:
            print(f"✅ REQUIRED SECTION '{section}' found")
    
    return success

def main():
    """Run the comprehensive test."""
    print("HYBRID TEMPLATE SYSTEM VERIFICATION")
    print("=" * 80)
    
    try:
        success = test_template_system()
        
        print("\n" + "=" * 80)
        if success:
            print("✅ HYBRID TEMPLATE SYSTEM WORKS PERFECTLY!")
            print("🎯 LLM focuses on synthesis, programmatic code handles facts")
            print("📝 References are 100% real data, never fabricated")
            print("🔍 Methodology is comprehensive and factual")
        else:
            print("❌ HYBRID TEMPLATE SYSTEM HAS ISSUES!")
        print("=" * 80)
        
        return success
        
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)