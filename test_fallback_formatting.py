#!/usr/bin/env python3
"""
Test script to verify the fallback formatting method works correctly.
"""

import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.agents.reporting_agent import Report, Reference, MethodologyMetadata
from bmlibrarian.cli.formatting import ReportFormatter
from bmlibrarian.cli.config import CLIConfig
from bmlibrarian.cli.ui import UserInterface
from datetime import datetime, timezone

def test_fallback_formatting():
    """Test that the fallback formatting method now uses programmatic references."""
    print("=" * 80)
    print("TESTING FALLBACK FORMATTING WITH REAL REFERENCES")
    print("=" * 80)
    
    # Create test data with real metadata
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
    
    # Create methodology metadata
    methodology_metadata = MethodologyMetadata(
        human_question="What are current management recommendations for melioidosis sepsis?",
        generated_query="melioidosis & sepsis & (management | treatment | therapy)",
        total_documents_found=185,
        scoring_threshold=2.5,
        documents_by_score={1: 35, 2: 48, 3: 62, 4: 25, 5: 15},
        documents_above_threshold=102,
        documents_processed_for_citations=102,
        citation_extraction_threshold=0.7,
        counterfactual_performed=True,
        counterfactual_queries_generated=8,
        counterfactual_documents_found=22,
        counterfactual_citations_extracted=9
    )
    
    # Create a Report object (not EditedReport - this triggers fallback)
    report = Report(
        user_question="What are current management recommendations for melioidosis sepsis?",
        synthesized_answer="Current evidence suggests that meropenem provides improved outcomes for severe melioidosis sepsis compared to traditional therapies [1]. Standard two-phase antibiotic regimens remain the foundation of treatment [2].",
        references=mock_references,
        evidence_strength="Limited",
        methodology_note="Evidence synthesis based on 2 citations.",
        created_at=datetime.now(timezone.utc),
        citation_count=2,
        unique_documents=2,
        methodology_metadata=methodology_metadata
    )
    
    print("✅ Created Report object (not EditedReport) to trigger fallback formatting")
    
    # Test the fallback formatting
    config = CLIConfig()
    ui = UserInterface(config)
    formatter = ReportFormatter(config, ui)
    
    formatted_content = formatter.format_enhanced_report_as_markdown(
        report,
        methodology_metadata=methodology_metadata
    )
    
    print(f"\n📄 Fallback formatting output (first 1500 chars):")
    print("-" * 60)
    print(formatted_content[:1500] + "..." if len(formatted_content) > 1500 else formatted_content)
    
    # Check for real data
    success = True
    
    # Check for real DOI and PMID data
    real_identifiers = ["26159354", "15105132", "10.1007/s40257-015-0138-4", "10.1128/AAC.48.5.1763-1765.2004"]
    for identifier in real_identifiers:
        if identifier in formatted_content:
            print(f"✅ REAL IDENTIFIER '{identifier}' found in fallback output")
        else:
            print(f"❌ REAL IDENTIFIER '{identifier}' NOT FOUND in fallback output!")
            success = False
    
    # Check for programmatic methodology elements
    methodology_elements = [
        "melioidosis & sepsis & (management | treatment | therapy)",
        "185",  # total documents
        "102",  # documents above threshold 
        "8"     # counterfactual queries generated
    ]
    
    for element in methodology_elements:
        if element in formatted_content:
            print(f"✅ METHODOLOGY ELEMENT '{element}' found in fallback output")
        else:
            print(f"❌ METHODOLOGY ELEMENT '{element}' NOT FOUND in fallback output!")
            success = False
    
    # Check that references are at the bottom
    lines = formatted_content.split('\n')
    ref_line_num = None
    methodology_line_num = None
    
    for i, line in enumerate(lines):
        if line.startswith('## References'):
            ref_line_num = i
        elif line.startswith('## Methodology'):
            methodology_line_num = i
    
    if ref_line_num is not None and methodology_line_num is not None:
        if ref_line_num < methodology_line_num:
            print(f"✅ References (line {ref_line_num}) appear before Methodology (line {methodology_line_num})")
        else:
            print(f"❌ References (line {ref_line_num}) should appear before Methodology (line {methodology_line_num})!")
            success = False
    else:
        print(f"❌ Could not find References or Methodology sections!")
        success = False
    
    # Check that fake data patterns are NOT present
    fake_patterns = ["12345678", "Journal of Disaster Medicine", "Clinical Infectious Diseases"]
    for pattern in fake_patterns:
        if pattern in formatted_content:
            print(f"❌ FAKE DATA PATTERN '{pattern}' found in output!")
            success = False
    
    return success

def main():
    """Run the test."""
    print("FALLBACK FORMATTING FIX VERIFICATION")
    print("=" * 80)
    
    try:
        success = test_fallback_formatting()
        
        print("\n" + "=" * 80)
        if success:
            print("✅ FALLBACK FORMATTING NOW WORKS CORRECTLY!")
            print("🔧 Both EditorAgent template AND fallback method use real data")
            print("📝 All report generation paths now have proper references")
        else:
            print("❌ FALLBACK FORMATTING STILL HAS ISSUES!")
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