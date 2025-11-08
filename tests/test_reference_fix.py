#!/usr/bin/env python3
"""
Test script to verify reference and methodology fixes.
"""

import sys
import logging
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.database import DatabaseManager, find_abstracts
from bmlibrarian.agents import QueryAgent, DocumentScoringAgent, CitationFinderAgent, ReportingAgent
from bmlibrarian.agents.reporting_agent import MethodologyMetadata

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_database_metadata():
    """Test what metadata the database actually returns."""
    print("=" * 80)
    print("TESTING DATABASE METADATA EXTRACTION")
    print("=" * 80)
    
    db = DatabaseManager()
    
    # Test a simple search to see what fields are returned
    test_query = "exercise & cardiovascular"
    print(f"Executing test query: {test_query}")
    
    documents = list(find_abstracts(test_query, max_rows=3))
    
    if not documents:
        print("No documents found!")
        return False
    
    print(f"Found {len(documents)} documents. Analyzing first document metadata:")
    print("-" * 60)
    
    doc = documents[0]
    print(f"Document ID: {doc.get('id')}")
    print(f"Title: {doc.get('title', 'Unknown')}")
    print(f"Authors: {doc.get('authors', [])}")
    print(f"Publication: {doc.get('publication', 'Unknown')}")
    print(f"Publication Date: {doc.get('publication_date', 'Unknown')}")
    print(f"DOI: {doc.get('doi', 'None')}")
    print(f"PMID: {doc.get('pmid', 'None')}")
    print(f"External ID: {doc.get('external_id', 'None')}")
    
    # Check if any documents have DOI/PMID
    docs_with_doi = [d for d in documents if d.get('doi')]
    docs_with_pmid = [d for d in documents if d.get('pmid')]
    
    print(f"\nDocs with DOI: {len(docs_with_doi)}/{len(documents)}")
    print(f"Docs with PMID: {len(docs_with_pmid)}/{len(documents)}")
    
    if docs_with_doi:
        print(f"Example DOI: {docs_with_doi[0]['doi']}")
    if docs_with_pmid:
        print(f"Example PMID: {docs_with_pmid[0]['pmid']}")
    
    return True

def test_citation_creation():
    """Test citation creation with metadata."""
    print("\n" + "=" * 80)
    print("TESTING CITATION CREATION WITH METADATA")
    print("=" * 80)
    
    db = DatabaseManager()
    
    # Get some documents
    test_query = "exercise & cardiovascular"
    documents = list(find_abstracts(test_query, max_rows=2))
    
    if not documents:
        print("No documents found!")
        return False
    
    # Test citation creation
    citation_agent = CitationFinderAgent(show_model_info=False)
    
    if not citation_agent.test_connection():
        print("Cannot connect to Ollama - skipping citation test")
        return False
    
    print("Testing citation extraction...")
    
    user_question = "What are the cardiovascular benefits of exercise?"
    citation = citation_agent.extract_citation_from_document(
        user_question=user_question,
        document=documents[0],
        min_relevance=0.5
    )
    
    if citation:
        print("Citation created successfully!")
        print(f"DOI: {citation.doi}")
        print(f"PMID: {citation.pmid}")
        print(f"Publication: {citation.publication}")
        print(f"Authors: {citation.authors}")
    else:
        print("No citation created")
    
    return True

def test_methodology_metadata():
    """Test methodology metadata generation."""
    print("\n" + "=" * 80)
    print("TESTING METHODOLOGY METADATA")
    print("=" * 80)
    
    # Create test methodology metadata
    metadata = MethodologyMetadata(
        human_question="What are the cardiovascular benefits of exercise?",
        generated_query="exercise & cardiovascular & (benefit | advantage | effect)",
        total_documents_found=150,
        scoring_threshold=2.5,
        documents_by_score={1: 20, 2: 35, 3: 45, 4: 30, 5: 20},
        documents_above_threshold=95,
        documents_processed_for_citations=95,
        citation_extraction_threshold=0.7,
        counterfactual_performed=True,
        counterfactual_queries_generated=8,
        counterfactual_documents_found=25,
        counterfactual_citations_extracted=12
    )
    
    # Test methodology generation
    reporting_agent = ReportingAgent(show_model_info=False)
    methodology_text = reporting_agent.generate_detailed_methodology(metadata)
    
    print("Generated methodology section:")
    print("-" * 60)
    print(methodology_text)
    
    # Check if all expected elements are present
    expected_elements = [
        metadata.human_question,
        metadata.generated_query,
        str(metadata.total_documents_found),
        str(metadata.scoring_threshold),
        str(metadata.documents_above_threshold),
        str(metadata.counterfactual_queries_generated)
    ]
    
    missing_elements = []
    for element in expected_elements:
        if element not in methodology_text:
            missing_elements.append(element)
    
    if missing_elements:
        print(f"\nMISSING ELEMENTS: {missing_elements}")
        return False
    else:
        print(f"\nAll expected elements found in methodology!")
        return True

def main():
    """Run all tests."""
    print("REFERENCE AND METHODOLOGY FIX VERIFICATION")
    print("=" * 80)
    
    success = True
    
    try:
        success &= test_database_metadata()
        success &= test_citation_creation()
        success &= test_methodology_metadata()
        
        print("\n" + "=" * 80)
        if success:
            print("✅ ALL TESTS PASSED - References and methodology should work correctly!")
        else:
            print("❌ SOME TESTS FAILED - Issues may remain")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        success = False
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)