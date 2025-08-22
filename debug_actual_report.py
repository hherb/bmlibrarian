#!/usr/bin/env python3
"""
Debug script to see what's actually being generated in reports.
"""

import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.agents.citation_agent import Citation
from bmlibrarian.agents.reporting_agent import Report, Reference, MethodologyMetadata, ReportingAgent
from bmlibrarian.agents.editor_agent import EditorAgent, EditedReport
from datetime import datetime, timezone

# Create test data
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
    )
]

# Create mock edited report  
edited_report = EditedReport(
    title="Test Report",
    executive_summary="Test summary",
    methodology_section="Test methodology", 
    findings_section="Test findings",
    contradictory_evidence_section="Test contradictory",
    limitations_section="Test limitations",
    conclusions_section="Test conclusions",
    references=mock_references,
    evidence_quality_table=None,
    confidence_assessment="LIMITED",
    word_count=100
)

print("DEBUGGING ACTUAL REPORT GENERATION")
print("=" * 80)

# Test the current method being used
editor_agent = EditorAgent(show_model_info=False)

# Test both methods to see which one is being used
print("📄 OLD format_comprehensive_markdown method:")
old_format = editor_agent.format_comprehensive_markdown(edited_report)
print("-" * 40)
# Print just the references section
lines = old_format.split('\n')
in_refs = False
for line in lines:
    if line.startswith('## References'):
        in_refs = True
        print(line)
    elif in_refs:
        if line.startswith('## ') or line.startswith('---'):
            break
        print(line)

print("\n📄 NEW format_comprehensive_markdown_template method:")
new_format = editor_agent.format_comprehensive_markdown_template(edited_report)
print("-" * 40)
# Print just the references section
lines = new_format.split('\n')
in_refs = False
for line in lines:
    if line.startswith('## References'):
        in_refs = True
        print(line)
    elif in_refs:
        if line.startswith('## ') or line.startswith('---'):
            break
        print(line)

print(f"\n🔍 Comparison:")
print(f"OLD method has DOI: {'10.1007/s40257-015-0138-4' in old_format}")
print(f"NEW method has DOI: {'10.1007/s40257-015-0138-4' in new_format}")
print(f"OLD method has PMID: {'26159354' in old_format}")  
print(f"NEW method has PMID: {'26159354' in new_format}")

print(f"\n📍 Reference section positions:")
old_lines = old_format.split('\n')
new_lines = new_format.split('\n')

for i, line in enumerate(old_lines):
    if line.startswith('## References'):
        print(f"OLD method - References at line {i}")
        break

for i, line in enumerate(new_lines):
    if line.startswith('## References'):
        print(f"NEW method - References at line {i}")
        break