#!/usr/bin/env python3
"""
Debug script to test reference formatting specifically.
"""

import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.agents.reporting_agent import Reference

# Test reference formatting
test_ref = Reference(
    number=1,
    authors=["Bandino Justin P", "Hang Anna", "Norton Scott A"],
    title="The Infectious and Noninfectious Dermatological Consequences of Flooding",
    publication_date="2015",
    document_id="26159354",
    pmid="26159354",
    doi="10.1007/s40257-015-0138-4",
    publication="American journal of clinical dermatology"
)

print("DEBUGGING REFERENCE FORMATTING")
print("=" * 60)
print(f"Reference object attributes:")
print(f"  number: {test_ref.number}")
print(f"  authors: {test_ref.authors}")
print(f"  title: {test_ref.title}")
print(f"  publication_date: {test_ref.publication_date}")
print(f"  pmid: {test_ref.pmid}")
print(f"  doi: {test_ref.doi}")
print(f"  publication: {test_ref.publication}")

print(f"\nVancouver formatted:")
formatted = test_ref.format_vancouver_style()
print(f"  {formatted}")

print(f"\nChecking for DOI/PMID in output:")
print(f"  Contains DOI: {'10.1007/s40257-015-0138-4' in formatted}")
print(f"  Contains PMID: {'26159354' in formatted}")
print(f"  Contains publication: {'American journal of clinical dermatology' in formatted}")