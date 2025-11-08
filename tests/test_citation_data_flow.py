#!/usr/bin/env python3
"""
Test script to verify citation data flow through the workflow.
"""

import sys
import logging
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.database import find_abstracts
from bmlibrarian.agents import CitationFinderAgent, ReportingAgent
from bmlibrarian.agents.reporting_agent import MethodologyMetadata

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_citation_with_real_data():
    """Test that citations preserve real database metadata."""
    print("=" * 80)
    print("TESTING CITATION DATA PRESERVATION")
    print("=" * 80)
    
    # Get a document from database
    test_query = "omega-3 & cardiovascular"
    documents = list(find_abstracts(test_query, max_rows=5))
    
    if not documents:
        print("No documents found!")
        return False
    
    # Find a document with DOI/PMID
    doc_with_metadata = None
    for doc in documents:
        if doc.get('doi') and doc.get('pmid'):
            doc_with_metadata = doc
            break
    
    if not doc_with_metadata:
        print("No documents with DOI/PMID found!")
        return False
    
    print(f"Testing with document: {doc_with_metadata['title'][:60]}...")
    print(f"Original DOI: {doc_with_metadata['doi']}")
    print(f"Original PMID: {doc_with_metadata['pmid']}")
    print(f"Original Publication: {doc_with_metadata.get('publication', 'None')}")
    
    # Create citation
    citation_agent = CitationFinderAgent(show_model_info=False)
    
    if not citation_agent.test_connection():
        print("Cannot connect to Ollama - skipping citation test")
        return False
    
    user_question = "What are the cardiovascular benefits of omega-3 fatty acids?"
    citation = citation_agent.extract_citation_from_document(
        user_question=user_question,
        document=doc_with_metadata,
        min_relevance=0.5
    )
    
    if citation:
        print("\n✅ Citation created!")
        print(f"Citation DOI: {citation.doi}")
        print(f"Citation PMID: {citation.pmid}")
        print(f"Citation Publication: {citation.publication}")
        
        # Check if data matches
        doi_match = citation.doi == doc_with_metadata['doi']
        pmid_match = citation.pmid == doc_with_metadata['pmid']
        pub_match = citation.publication == doc_with_metadata.get('publication')
        
        print(f"\nData preservation check:")
        print(f"DOI preserved: {doi_match}")
        print(f"PMID preserved: {pmid_match}")
        print(f"Publication preserved: {pub_match}")
        
        if not all([doi_match, pmid_match, pub_match]):
            print("❌ Metadata not properly preserved!")
            return False
        
        # Test reference formatting
        reporting_agent = ReportingAgent(show_model_info=False)
        references = reporting_agent.create_references([citation])
        
        if references:
            reference = references[0]
            formatted_ref = reference.format_vancouver_style()
            
            print(f"\n✅ Reference formatted:")
            print(f"Formatted reference: {formatted_ref}")
            
            # Check if DOI/PMID appear in formatted reference
            doi_in_ref = citation.doi in formatted_ref if citation.doi else True
            pmid_in_ref = citation.pmid in formatted_ref if citation.pmid else True
            
            print(f"DOI in formatted reference: {doi_in_ref}")
            print(f"PMID in formatted reference: {pmid_in_ref}")
            
            if not all([doi_in_ref, pmid_in_ref]):
                print("❌ DOI/PMID not appearing in formatted reference!")
                return False
            
            return True
        else:
            print("❌ Failed to create reference!")
            return False
    else:
        print("❌ No citation created (may be due to relevance threshold)")
        return False

def main():
    """Run the test."""
    print("CITATION DATA FLOW VERIFICATION")
    print("=" * 80)
    
    try:
        success = test_citation_with_real_data()
        
        print("\n" + "=" * 80)
        if success:
            print("✅ CITATION DATA FLOW WORKS CORRECTLY!")
            print("The issue must be elsewhere in the workflow.")
        else:
            print("❌ CITATION DATA FLOW HAS ISSUES!")
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