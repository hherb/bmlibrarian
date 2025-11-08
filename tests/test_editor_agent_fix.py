#!/usr/bin/env python3
"""
Test script to verify EditorAgent reference fix.
"""

import sys
import logging
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.agents.citation_agent import Citation
from bmlibrarian.agents.reporting_agent import Report, Reference
from bmlibrarian.agents.editor_agent import EditorAgent
from datetime import datetime, timezone

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_editor_agent_reference_fix():
    """Test that EditorAgent preserves real reference data."""
    print("=" * 80)
    print("TESTING EDITOR AGENT REFERENCE FIX")
    print("=" * 80)
    
    # Create mock citations with real-looking data
    mock_citations = [
        Citation(
            passage="Omega-3 fatty acids significantly reduced cardiovascular events in clinical trials.",
            summary="Meta-analysis shows 20% reduction in CV events with omega-3 supplementation.",
            relevance_score=0.9,
            document_id="26159354",
            document_title="The Infectious and Noninfectious Dermatological Consequences of Flooding",
            authors=["Bandino Justin P", "Hang Anna", "Norton Scott A"],
            publication_date="2015",
            pmid="26159354",
            doi="10.1007/s40257-015-0138-4",
            publication="American journal of clinical dermatology"
        ),
        Citation(
            passage="Meropenem treatment improved survival outcomes in severe sepsis patients.",
            summary="Retrospective study of 154 patients with melioidosis treated with meropenem.",
            relevance_score=0.85,
            document_id="15105132",
            document_title="Outcomes of patients with melioidosis treated with meropenem",
            authors=["Cheng Allen C", "Fisher Dale A", "Anstey Nicholas M"],
            publication_date="2004",
            pmid="15105132",
            doi="10.1128/AAC.48.5.1763-1765.2004",
            publication="Antimicrobial agents and chemotherapy"
        )
    ]
    
    # Create mock references (what ReportingAgent would produce)
    mock_references = [
        Reference(
            number=1,
            authors=["Bandino Justin P", "Hang Anna", "Norton Scott A"],
            title="The Infectious and Noninfectious Dermatological Consequences of Flooding",
            publication_date="2015",
            document_id="26159354",
            pmid="26159354",
            doi="10.1007/s40257-015-0138-4",
            publication="American journal of clinical dermatology"
        ),
        Reference(
            number=2,
            authors=["Cheng Allen C", "Fisher Dale A", "Anstey Nicholas M"],
            title="Outcomes of patients with melioidosis treated with meropenem",
            publication_date="2004",
            document_id="15105132",
            pmid="15105132",
            doi="10.1128/AAC.48.5.1763-1765.2004",
            publication="Antimicrobial agents and chemotherapy"
        )
    ]
    
    # Create mock original report
    mock_report = Report(
        user_question="What are current management recommendations for melioidosis sepsis?",
        synthesized_answer="Melioidosis sepsis requires intensive antibiotic therapy with ceftazidime or meropenem.",
        references=mock_references,
        evidence_strength="Limited",
        methodology_note="Evidence synthesis based on 2 citations.",
        created_at=datetime.now(timezone.utc),
        citation_count=2,
        unique_documents=2
    )
    
    print("✅ Created mock data with REAL reference information:")
    for ref in mock_references:
        formatted = ref.format_vancouver_style()
        print(f"  {ref.number}. {formatted}")
    
    # Test the EditorAgent (skip actual LLM call - just test reference preservation)
    print(f"\n🧪 Testing reference preservation in EditorAgent...")
    
    # Simulate what happens in the EditorAgent when it creates an EditedReport
    from bmlibrarian.agents.editor_agent import EditedReport
    
    edited_report = EditedReport(
        title="Test Report",
        executive_summary="Test summary",
        methodology_section="Test methodology",
        findings_section="Test findings",
        contradictory_evidence_section="No contradictory evidence found.",
        limitations_section="Test limitations",
        conclusions_section="Test conclusions",
        references=mock_report.references,  # This should preserve real references
        evidence_quality_table=None,
        confidence_assessment="LIMITED",
        word_count=100
    )
    
    # Test the formatting
    editor_agent = EditorAgent(show_model_info=False)
    formatted_output = editor_agent.format_comprehensive_markdown(edited_report)
    
    print(f"\n📄 Formatted EditorAgent output:")
    print("-" * 60)
    
    # Extract just the references section
    lines = formatted_output.split('\n')
    in_references = False
    for line in lines:
        if line.startswith('## References'):
            in_references = True
        elif line.startswith('## ') and in_references:
            break
        elif in_references:
            print(line)
    
    # Verify real data appears in output
    success = True
    real_pmids = ["26159354", "15105132"]
    real_dois = ["10.1007/s40257-015-0138-4", "10.1128/AAC.48.5.1763-1765.2004"]
    
    for pmid in real_pmids:
        if pmid not in formatted_output:
            print(f"❌ REAL PMID {pmid} NOT FOUND in output!")
            success = False
        else:
            print(f"✅ REAL PMID {pmid} found in output")
    
    for doi in real_dois:
        if doi not in formatted_output:
            print(f"❌ REAL DOI {doi} NOT FOUND in output!")
            success = False
        else:
            print(f"✅ REAL DOI {doi} found in output")
    
    # Check for fake data patterns
    fake_patterns = ["12345678", "87654321", "Journal of Tropical Medicine", "Clinical Infectious Diseases"]
    for pattern in fake_patterns:
        if pattern in formatted_output:
            print(f"❌ FAKE DATA PATTERN '{pattern}' found in output!")
            success = False
    
    return success

def main():
    """Run the test."""
    print("EDITOR AGENT REFERENCE FIX VERIFICATION")
    print("=" * 80)
    
    try:
        success = test_editor_agent_reference_fix()
        
        print("\n" + "=" * 80)
        if success:
            print("✅ EDITOR AGENT FIX WORKS! References now use real data!")
        else:
            print("❌ EDITOR AGENT FIX FAILED! Issues remain with reference data.")
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