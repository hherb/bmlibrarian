#!/usr/bin/env python3
"""
BMLibrarian CLI - Interactive Medical Literature Research Tool

A comprehensive command-line interface for conducting evidence-based medical literature research
using the full BMLibrarian multi-agent workflow with human-in-the-loop interaction.

Features:
- Interactive query generation and editing
- Database search with real-time results
- Document relevance scoring with user review
- Citation extraction from high-scoring documents
- Medical publication-style report generation
- Markdown report export with proper formatting

Usage:
    python bmlibrarian_cli.py

Requirements:
- PostgreSQL database with biomedical literature
- Ollama service running locally
- BMLibrarian agents properly configured
"""

import os
import sys
import json
import time
import tempfile
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.agents import (
    QueryAgent, DocumentScoringAgent, CitationFinderAgent, 
    ReportingAgent, CounterfactualAgent, AgentOrchestrator, 
    Citation, Report, CounterfactualAnalysis
)


class MedicalResearchCLI:
    """Interactive CLI for medical literature research using BMLibrarian agents."""
    
    def __init__(self):
        """Initialize CLI with agent orchestrator and setup."""
        print("🏥 BMLibrarian Medical Research CLI")
        print("=" * 60)
        
        self.orchestrator = None
        self.query_agent = None
        self.scoring_agent = None
        self.citation_agent = None
        self.reporting_agent = None
        self.counterfactual_agent = None
        
        # Session state
        self.current_question = None
        self.current_query = None
        self.search_results = []
        self.scored_documents = []
        self.extracted_citations = []
        self.final_report = None
        
        # Configuration
        self.max_documents_display = 10
        self.default_score_threshold = 2.5
        self.default_min_relevance = 0.7
        self.max_search_results = 100  # Default max search results
        self.timeout_minutes = 5  # Default timeout in minutes
    
    def test_database_connection(self) -> bool:
        """Test database connection."""
        try:
            from bmlibrarian.database import get_db_manager
            
            db_manager = get_db_manager()
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    result = cur.fetchone()
                    return result is not None
        except Exception as e:
            print(f"   Database connection error: {e}")
            return False
        
    def setup_agents(self) -> bool:
        """Initialize and test all agents."""
        try:
            print("\n🔧 Setting up BMLibrarian agents...")
            
            # Initialize orchestrator
            self.orchestrator = AgentOrchestrator(max_workers=4, polling_interval=0.5)
            
            # Initialize agents
            self.query_agent = QueryAgent(orchestrator=self.orchestrator)
            self.scoring_agent = DocumentScoringAgent(orchestrator=self.orchestrator)
            self.citation_agent = CitationFinderAgent(orchestrator=self.orchestrator)
            self.reporting_agent = ReportingAgent(orchestrator=self.orchestrator)
            self.counterfactual_agent = CounterfactualAgent(orchestrator=self.orchestrator)
            
            # Register agents
            self.orchestrator.register_agent("query_agent", self.query_agent)
            self.orchestrator.register_agent("document_scoring_agent", self.scoring_agent)
            self.orchestrator.register_agent("citation_finder_agent", self.citation_agent)
            self.orchestrator.register_agent("reporting_agent", self.reporting_agent)
            self.orchestrator.register_agent("counterfactual_agent", self.counterfactual_agent)
            
            print("   ✅ Agents initialized")
            
            # Test connections
            print("\n🔍 Testing service connections...")
            
            # Test database connection
            db_connected = self.test_database_connection()
            print(f"   Database: {'✅ Connected' if db_connected else '❌ Failed'}")
            
            # Test Ollama connections
            scoring_connected = self.scoring_agent.test_connection()
            print(f"   Scoring Agent (Ollama): {'✅ Connected' if scoring_connected else '❌ Failed'}")
            
            citation_connected = self.citation_agent.test_connection()
            print(f"   Citation Agent (Ollama): {'✅ Connected' if citation_connected else '❌ Failed'}")
            
            reporting_connected = self.reporting_agent.test_connection()
            print(f"   Reporting Agent (Ollama): {'✅ Connected' if reporting_connected else '❌ Failed'}")
            
            counterfactual_connected = self.counterfactual_agent.test_connection()
            print(f"   Counterfactual Agent (Ollama): {'✅ Connected' if counterfactual_connected else '❌ Failed'}")
            
            # Check if all critical services are available
            if not (scoring_connected and citation_connected and reporting_connected and counterfactual_connected):
                print("\n⚠️  Some AI services are unavailable. Please ensure:")
                print("   - Ollama is running: ollama serve")
                print("   - Required models are installed:")
                print("     ollama pull gpt-oss:20b")
                print("     ollama pull medgemma4B_it_q8:latest")
                return False
            
            print("\n✅ All services connected and ready!")
            return True
            
        except Exception as e:
            print(f"\n❌ Failed to setup agents: {e}")
            return False
    
    def get_user_question(self) -> str:
        """Get research question from user with validation."""
        print("\n" + "=" * 60)
        print("Step 1: Research Question")
        print("=" * 60)
        
        while True:
            print("\nPlease enter your medical research question:")
            print("Examples:")
            print("• What are the cardiovascular benefits of exercise?")
            print("• How effective is metformin for diabetes management?")
            print("• What are the side effects of statins in elderly patients?")
            
            question = input("\n🔬 Your question: ").strip()
            
            if not question:
                print("❌ Please enter a valid question.")
                continue
            
            if len(question) < 10:
                print("❌ Please provide a more detailed question (at least 10 characters).")
                continue
            
            # Confirm question
            print(f"\n📋 Your research question: \"{question}\"")
            confirm = input("Is this correct? (y/n): ").strip().lower()
            
            if confirm in ['y', 'yes']:
                self.current_question = question
                return question
            
            print("Let's try again...")
    
    def search_documents_with_review(self, question: str) -> List[Dict[str, Any]]:
        """Use QueryAgent to search documents with human-in-the-loop query editing."""
        print("\n" + "=" * 60)
        print("Step 2: Database Query Generation & Search")
        print("=" * 60)
        
        try:
            # Step 2a: Generate initial to_tsquery string
            print(f"\n🔍 Generating database query for: \"{question}\"")
            print("⏳ Converting natural language to PostgreSQL to_tsquery format...")
            
            initial_query = self.query_agent.convert_question(question)
            
            if not initial_query:
                print("❌ Failed to generate database query.")
                return []
            
            # Step 2b: Show generated query and allow editing
            current_query = initial_query
            
            while True:
                print(f"\n📋 Generated PostgreSQL Query:")
                print("=" * 50)
                print(f"to_tsquery: {current_query}")
                print("=" * 50)
                
                print(f"\nQuery explanation:")
                print("• '&' means AND (all terms must appear)")
                print("• '|' means OR (any of these terms can appear)")
                print("• Parentheses group related terms")
                print("• Multi-word phrases are kept together")
                
                print(f"\nOptions:")
                print("1. Use this query for search")
                print("2. Edit the query manually")
                print("3. Regenerate query with different approach")
                print("4. Go back to change research question")
                
                choice = input("Choose option (1-4): ").strip()
                
                if choice == '1':
                    # Proceed with current query
                    self.current_query = current_query
                    break
                    
                elif choice == '2':
                    # Manual editing
                    print(f"\n✏️  Manual Query Editing:")
                    print("Current query:", current_query)
                    print("\nTips for editing:")
                    print("• Use & for AND, | for OR")
                    print("• Use parentheses to group terms")
                    print("• Keep medical terminology")
                    print("• Example: (diabetes | diabetic) & (treatment | therapy)")
                    
                    new_query = input("\nEnter your edited query: ").strip()
                    
                    if new_query:
                        # Basic validation
                        if self._validate_tsquery(new_query):
                            current_query = new_query
                            print("✅ Query updated successfully")
                        else:
                            print("⚠️  Warning: Query format may be invalid, but proceeding...")
                            current_query = new_query
                    else:
                        print("❌ No changes made - keeping original query")
                    continue
                    
                elif choice == '3':
                    # Regenerate with different approach
                    print(f"\n🔄 Regenerating query...")
                    print("Trying different keyword extraction approach...")
                    
                    # You could implement different generation strategies here
                    # For now, we'll just regenerate with the same method
                    regenerated_query = self.query_agent.convert_question(question)
                    
                    if regenerated_query and regenerated_query != current_query:
                        current_query = regenerated_query
                        print("✅ New query generated")
                    else:
                        print("⚠️  Generated same query - no change")
                    continue
                    
                elif choice == '4':
                    # Go back to question entry
                    return []
                    
                else:
                    print("❌ Invalid option. Please choose 1-4.")
                    continue
            
            # Step 2c: Execute the search with the final query
            print(f"\n🔍 Executing search with query: {current_query}")
            print("⏳ Searching database...")
            
            # Use the raw database search with the validated query
            from bmlibrarian.database import find_abstracts
            
            documents = []
            results_generator = find_abstracts(
                current_query,
                max_rows=self.max_search_results,
                plain=False  # Use to_tsquery format
            )
            
            for doc in results_generator:
                documents.append(doc)
            
            if not documents:
                print("❌ No documents found with this query.")
                print("\nSuggestions:")
                print("• Try broader search terms")
                print("• Use fewer AND (&) operators")
                print("• Add more OR (|) alternatives")
                print("• Check spelling of medical terms")
                
                retry = input("\nWould you like to modify the query and try again? (y/n): ").strip().lower()
                if retry in ['y', 'yes']:
                    return self.search_documents_with_review(question)
                else:
                    return []
            
            print(f"\n✅ Found {len(documents)} documents")
            return documents
            
        except Exception as e:
            print(f"❌ Error in query generation/search: {e}")
            print("\nPossible issues:")
            print("• Database connection problem")
            print("• Invalid query syntax")
            print("• Ollama service unavailable")
            
            return []
    
    def _validate_tsquery(self, query: str) -> bool:
        """Basic validation of to_tsquery format."""
        try:
            # Simple validation checks
            if not query.strip():
                return False
            
            # Check for balanced parentheses
            if query.count('(') != query.count(')'):
                return False
            
            # Check for valid operators (basic check)
            invalid_patterns = ['&&', '||', '&|', '|&', '& &', '| |']
            for pattern in invalid_patterns:
                if pattern in query:
                    return False
            
            # Check for empty parentheses
            if '()' in query:
                return False
            
            # Check for operators at start/end
            stripped = query.strip()
            if stripped.startswith(('&', '|')) or stripped.endswith(('&', '|')):
                return False
            
            return True
        except:
            return False
    
    def display_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Display documents to user and get confirmation to proceed."""
        print("\n" + "=" * 60)
        print("Step 3: Document Review")
        print("=" * 60)
        
        if not documents:
            return documents
        
        # Display sample results
        print(f"\n📄 Showing first {min(self.max_documents_display, len(documents))} documents:")
        print("=" * 80)
        
        for i, doc in enumerate(documents[:self.max_documents_display], 1):
            print(f"\n{i}. Title: {doc.get('title', 'No title')}")
            print(f"   ID: {doc.get('id', 'Unknown')}")
            authors = doc.get('authors', [])
            if isinstance(authors, list):
                authors_str = ', '.join(authors)[:100]
            else:
                authors_str = str(authors)[:100]
            print(f"   Authors: {authors_str}")
            print(f"   Date: {doc.get('publication_date', 'Unknown')}")
            
            # Show abstract preview
            abstract = doc.get('abstract', '')
            if abstract:
                preview = abstract[:200] + "..." if len(abstract) > 200 else abstract
                print(f"   Abstract: {preview}")
            else:
                print("   Abstract: Not available")
            
            if doc.get('pmid'):
                print(f"   PMID: {doc['pmid']}")
            
            print("-" * 80)
        
        if len(documents) > self.max_documents_display:
            print(f"\n... and {len(documents) - self.max_documents_display} more documents")
        
        # Ask user if they want to proceed
        while True:
            print(f"\nFound {len(documents)} total documents.")
            print("Options:")
            print("1. Proceed with these results")
            print("2. Search again with different terms")
            print("3. Show more document details")
            
            choice = input("Choose option (1-3): ").strip()
            
            if choice == '1':
                self.search_results = documents
                return documents
            
            elif choice == '2':
                # Get new question and search again
                new_question = self.get_user_question()
                return self.search_documents_with_review(new_question)
            
            elif choice == '3':
                # Show detailed view of documents
                self.show_detailed_documents(documents)
                continue
            
            else:
                print("❌ Invalid option. Please choose 1-3.")
    
    def show_detailed_documents(self, documents: List[Dict[str, Any]]):
        """Show detailed view of documents."""
        start_idx = 0
        while start_idx < len(documents):
            end_idx = min(start_idx + 5, len(documents))
            print(f"\n📋 Documents {start_idx + 1}-{end_idx} of {len(documents)}:")
            print("=" * 80)
            
            for i in range(start_idx, end_idx):
                doc = documents[i]
                print(f"\n{i + 1}. {doc.get('title', 'No title')}")
                print(f"    ID: {doc.get('id')}")
                authors = doc.get('authors', [])
                if isinstance(authors, list):
                    authors_str = ', '.join(authors)
                else:
                    authors_str = str(authors)
                print(f"    Authors: {authors_str}")
                print(f"    Date: {doc.get('publication_date', 'Unknown')}")
                print(f"    Abstract: {doc.get('abstract', 'Not available')}")
                print("-" * 80)
            
            if end_idx < len(documents):
                cont = input(f"\nShow next 5 documents? (y/n): ").strip().lower()
                if cont not in ['y', 'yes']:
                    break
                start_idx = end_idx
            else:
                break
    
    def score_documents_with_review(self, question: str, documents: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """Score documents and allow user to review scores."""
        print("\n" + "=" * 60)
        print("Step 4: Document Relevance Scoring")
        print("=" * 60)
        
        try:
            print(f"\n🎯 Scoring {len(documents)} documents for relevance to:")
            print(f'   "{question}"')
            print("\n⏳ This may take a few minutes...")
            
            scored_docs = []
            
            # Score documents with progress indication
            for i, doc in enumerate(documents, 1):
                print(f"   Scoring document {i}/{len(documents)}: {doc.get('title', 'Untitled')[:50]}...")
                
                score_result = self.scoring_agent.evaluate_document(question, doc)
                
                if score_result:
                    scored_docs.append((doc, score_result))
                else:
                    print(f"   ⚠️  Failed to score document {i}")
            
            if not scored_docs:
                print("❌ No documents could be scored. Check Ollama connection.")
                return []
            
            # Sort by score (descending)
            scored_docs.sort(key=lambda x: x[1].get('score', 0), reverse=True)
            
            print(f"\n✅ Successfully scored {len(scored_docs)} documents")
            
            # Display scoring results
            print("\n📊 Document Scores (1-5 scale, 5=most relevant):")
            print("=" * 80)
            
            for i, (doc, score_result) in enumerate(scored_docs[:10], 1):
                score = score_result.get('score', 0)
                reasoning = score_result.get('reasoning', 'No reasoning provided')
                
                # Color coding for scores
                if score >= 4:
                    score_display = f"🟢 {score}/5"
                elif score >= 3:
                    score_display = f"🟡 {score}/5"
                elif score >= 2:
                    score_display = f"🟠 {score}/5"
                else:
                    score_display = f"🔴 {score}/5"
                
                print(f"\n{i}. {score_display} - {doc.get('title', 'No title')[:60]}")
                print(f"   ID: {doc.get('id')}")
                print(f"   Reasoning: {reasoning}")
                print("-" * 80)
            
            if len(scored_docs) > 10:
                print(f"\n... and {len(scored_docs) - 10} more scored documents")
            
            # Show score distribution
            score_counts = {}
            for _, score_result in scored_docs:
                score = int(score_result.get('score', 0))
                score_counts[score] = score_counts.get(score, 0) + 1
            
            print(f"\n📈 Score Distribution:")
            for score in range(5, 0, -1):
                count = score_counts.get(score, 0)
                bar = "█" * min(count, 20)
                print(f"   {score}/5: {count:3d} docs {bar}")
            
            # Ask about score threshold
            while True:
                print(f"\n⚙️  Configuration:")
                high_scoring = len([doc for doc, score in scored_docs if score.get('score', 0) > self.default_score_threshold])
                print(f"   Current threshold: {self.default_score_threshold}")
                print(f"   Documents above threshold: {high_scoring}")
                
                print("\nOptions:")
                print("1. Proceed with current threshold")
                print("2. Adjust score threshold")
                print("3. Review individual scores")
                print("4. Re-score with different parameters")
                
                choice = input("Choose option (1-4): ").strip()
                
                if choice == '1':
                    self.scored_documents = scored_docs
                    return scored_docs
                
                elif choice == '2':
                    while True:
                        try:
                            new_threshold = float(input(f"Enter new threshold (current: {self.default_score_threshold}): "))
                            if 0 <= new_threshold <= 5:
                                self.default_score_threshold = new_threshold
                                qualifying = len([doc for doc, score in scored_docs if score.get('score', 0) > new_threshold])
                                print(f"✅ New threshold: {new_threshold}")
                                print(f"   Documents that will qualify: {qualifying}")
                                break
                            else:
                                print("❌ Threshold must be between 0 and 5")
                        except ValueError:
                            print("❌ Please enter a valid number")
                    continue
                
                elif choice == '3':
                    # Show detailed score review
                    self.show_detailed_scores(scored_docs)
                    continue
                
                elif choice == '4':
                    print("Re-scoring documents...")
                    # Could implement different scoring parameters here
                    continue
                
                else:
                    print("❌ Invalid option. Please choose 1-4.")
        
        except Exception as e:
            print(f"❌ Error in document scoring: {e}")
            return []
    
    def show_detailed_scores(self, scored_docs: List[Tuple[Dict[str, Any], Dict[str, Any]]]):
        """Show detailed view of document scores."""
        print("\n📋 Detailed Score Review:")
        print("=" * 80)
        
        for i, (doc, score_result) in enumerate(scored_docs, 1):
            print(f"\n{i}. Score: {score_result.get('score', 0)}/5")
            print(f"   Title: {doc.get('title', 'No title')}")
            print(f"   Authors: {', '.join(doc.get('authors', []))}")
            print(f"   Date: {doc.get('publication_date', 'Unknown')}")
            print(f"   Reasoning: {score_result.get('reasoning', 'No reasoning')}")
            print(f"   Abstract preview: {doc.get('abstract', '')[:150]}...")
            print("-" * 80)
            
            if i % 5 == 0 and i < len(scored_docs):
                cont = input(f"\nContinue viewing? ({i}/{len(scored_docs)}) (y/n): ").strip().lower()
                if cont not in ['y', 'yes']:
                    break
    
    def extract_citations_with_review(self, question: str, scored_docs: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> List[Citation]:
        """Extract citations and allow user review."""
        print("\n" + "=" * 60)
        print("Step 5: Citation Extraction")
        print("=" * 60)
        
        try:
            # Filter documents above threshold
            qualifying_docs = [
                (doc, score) for doc, score in scored_docs 
                if score.get('score', 0) > self.default_score_threshold
            ]
            
            print(f"\n📄 Processing {len(qualifying_docs)} documents above threshold {self.default_score_threshold}")
            print(f'   Extracting citations for: "{question}"')
            print("\n⏳ This may take several minutes...")
            
            # Extract citations with progress indication
            def progress_callback(current, total):
                percentage = (current / total) * 100
                print(f"   Progress: {current}/{total} documents ({percentage:.1f}%)")
            
            citations = self.citation_agent.process_scored_documents_for_citations(
                user_question=question,
                scored_documents=qualifying_docs,
                score_threshold=self.default_score_threshold,
                min_relevance=self.default_min_relevance,
                progress_callback=progress_callback
            )
            
            if not citations:
                print("❌ No citations extracted.")
                print("\nPossible reasons:")
                print("• Score threshold too high")
                print("• Minimum relevance threshold too high")
                print("• Documents don't contain relevant passages")
                print("• Ollama connection issues")
                return []
            
            print(f"\n✅ Extracted {len(citations)} citations")
            
            # Display citations
            print("\n📝 Extracted Citations:")
            print("=" * 80)
            
            for i, citation in enumerate(citations, 1):
                print(f"\n{i}. Relevance: {citation.relevance_score:.3f}")
                print(f"   Document: {citation.document_title[:70]}")
                print(f"   Authors: {', '.join(citation.authors[:3])}{'...' if len(citation.authors) > 3 else ''}")
                print(f"   Passage: \"{citation.passage}\"")
                print(f"   Summary: {citation.summary}")
                print(f"   Document ID: {citation.document_id}")
                print("-" * 80)
            
            # Show citation statistics
            stats = self.citation_agent.get_citation_stats(citations)
            print(f"\n📊 Citation Statistics:")
            print(f"   Total citations: {stats['total_citations']}")
            print(f"   Unique documents: {stats['unique_documents']}")
            print(f"   Average relevance: {stats['average_relevance']:.3f}")
            print(f"   Relevance range: {stats['min_relevance']:.3f} - {stats['max_relevance']:.3f}")
            
            while True:
                print(f"\nCitation options:")
                print("1. Proceed with these citations")
                print("2. Adjust relevance threshold")
                print("3. Review individual citations")
                print("4. Go back to adjust document scores")
                
                choice = input("Choose option (1-4): ").strip()
                
                if choice == '1':
                    self.extracted_citations = citations
                    return citations
                
                elif choice == '2':
                    while True:
                        try:
                            new_relevance = float(input(f"Enter new minimum relevance (current: {self.default_min_relevance}): "))
                            if 0 <= new_relevance <= 1:
                                self.default_min_relevance = new_relevance
                                print(f"✅ New minimum relevance: {new_relevance}")
                                
                                # Re-extract with new threshold
                                return self.extract_citations_with_review(question, scored_docs)
                            else:
                                print("❌ Relevance must be between 0 and 1")
                        except ValueError:
                            print("❌ Please enter a valid number")
                
                elif choice == '3':
                    # Show detailed citation review
                    for i, citation in enumerate(citations, 1):
                        print(f"\n{'='*60}")
                        print(f"Citation {i} of {len(citations)}")
                        print(f"{'='*60}")
                        print(f"Document: {citation.document_title}")
                        print(f"Authors: {', '.join(citation.authors)}")
                        print(f"Date: {citation.publication_date}")
                        print(f"Relevance Score: {citation.relevance_score:.3f}")
                        print(f"Document ID: {citation.document_id}")
                        print(f"\nPassage:")
                        print(f'"{citation.passage}"')
                        print(f"\nSummary:")
                        print(f"{citation.summary}")
                        
                        if i < len(citations):
                            cont = input(f"\nContinue to next citation? (y/n): ").strip().lower()
                            if cont not in ['y', 'yes']:
                                break
                    continue
                
                elif choice == '4':
                    # Return to document scoring
                    return self.score_documents_with_review(question, [(doc, score) for doc, score in scored_docs])
                
                else:
                    print("❌ Invalid option. Please choose 1-4.")
        
        except Exception as e:
            print(f"❌ Error in citation extraction: {e}")
            return []
    
    def generate_final_report(self, question: str, citations: List[Citation]) -> Optional[Report]:
        """Generate final medical publication-style report."""
        print("\n" + "=" * 60)
        print("Step 6: Report Generation")
        print("=" * 60)
        
        try:
            print(f"\n📄 Generating medical publication-style report...")
            print(f'   Research question: "{question}"')
            print(f"   Based on {len(citations)} citations")
            
            # Check if we have too many citations for reliable processing
            if len(citations) > 20:
                print(f"\n⚠️  You have {len(citations)} citations. Large citation sets may:")
                print("• Take a long time to process (5-10 minutes)")
                print("• Cause timeouts with the AI model")
                print("• Produce less focused reports")
                
                while True:
                    print(f"\nOptions:")
                    print("1. Proceed with all citations (may be slow)")
                    print("2. Use only the top citations by relevance")
                    print("3. Go back and increase citation thresholds")
                    
                    choice = input("Choose option (1-3): ").strip()
                    
                    if choice == '1':
                        break
                    elif choice == '2':
                        # Sort by relevance and take top 15
                        sorted_citations = sorted(citations, key=lambda c: c.relevance_score, reverse=True)
                        citations = sorted_citations[:15]
                        print(f"✅ Using top {len(citations)} citations by relevance score")
                        break
                    elif choice == '3':
                        print("Please go back to citation extraction step and adjust thresholds.")
                        return None
                    else:
                        print("❌ Invalid option. Please choose 1-3.")
            
            print(f"\n⏳ Synthesizing evidence from {len(citations)} citations...")
            print("   Using iterative processing to avoid context limits...")
            print("   Processing citations one by one - this may take a few minutes...")
            
            # Generate report using iterative approach
            report = self.reporting_agent.synthesize_report(
                user_question=question,
                citations=citations,
                min_citations=2
            )
            
            if not report:
                print("❌ Failed to generate report after multiple attempts.")
                print("Suggestions:")
                print("• Try with fewer citations (go back to citation step)")
                print("• Check Ollama model performance")
                print("• Ensure sufficient system resources")
                return None
            
            print(f"\n✅ Report generated successfully!")
            print(f"   Evidence strength: {report.evidence_strength}")
            print(f"   Citations analyzed: {report.citation_count}")
            print(f"   Unique references: {report.unique_documents}")
            
            # Format and display report
            formatted_report = self.reporting_agent.format_report_output(report)
            
            print("\n" + "=" * 80)
            print("GENERATED RESEARCH REPORT")
            print("=" * 80)
            print(formatted_report)
            print("=" * 80)
            
            self.final_report = report
            return report
            
        except Exception as e:
            print(f"❌ Error generating report: {e}")
            print("\nSuggestions:")
            print("• Reduce the number of citations")
            print("• Check Ollama service is running properly")
            print("• Ensure sufficient memory and processing power")
            return None
    
    def save_report_as_markdown(self, report: Report, counterfactual_analysis: Optional[CounterfactualAnalysis] = None) -> bool:
        """Save the generated report as a markdown file."""
        print("\n" + "=" * 60)
        print("Step 8: Save Report")
        print("=" * 60)
        
        try:
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            question_slug = "".join(c if c.isalnum() or c in [' ', '-'] else '' for c in self.current_question)
            question_slug = "_".join(question_slug.split()[:5])  # First 5 words
            
            default_filename = f"bmlibrarian_report_{question_slug}_{timestamp}.md"
            
            print(f"\n💾 Save report as markdown file:")
            filename = input(f"Filename (default: {default_filename}): ").strip()
            
            if not filename:
                filename = default_filename
            
            if not filename.endswith('.md'):
                filename += '.md'
            
            # Convert report to markdown format
            markdown_content = self.format_report_as_markdown(report, counterfactual_analysis)
            
            # Save file
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            
            print(f"✅ Report saved as: {filename}")
            print(f"   File size: {os.path.getsize(filename)} bytes")
            
            # Show file preview
            print(f"\n📄 File preview (first 300 characters):")
            print("-" * 50)
            print(markdown_content[:300] + ("..." if len(markdown_content) > 300 else ""))
            print("-" * 50)
            
            return True
            
        except Exception as e:
            print(f"❌ Error saving report: {e}")
            return False
    
    def format_report_as_markdown(self, report: Report, counterfactual_analysis: Optional[CounterfactualAnalysis] = None) -> str:
        """Format report as markdown with proper structure."""
        lines = []
        
        # Title and metadata
        lines.append(f"# Medical Literature Research Report")
        lines.append("")
        lines.append(f"**Generated by BMLibrarian CLI**  ")
        lines.append(f"**Date:** {report.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}  ")
        lines.append(f"**Evidence Strength:** {report.evidence_strength}  ")
        lines.append("")
        
        # Research question
        lines.append("## Research Question")
        lines.append("")
        lines.append(f"> {report.user_question}")
        lines.append("")
        
        # Evidence assessment
        lines.append("## Evidence Assessment")
        lines.append("")
        lines.append(f"- **Evidence Strength:** {report.evidence_strength}")
        lines.append(f"- **Citations Analyzed:** {report.citation_count}")
        lines.append(f"- **Unique References:** {report.unique_documents}")
        lines.append("")
        
        # Synthesized answer
        lines.append("## Findings")
        lines.append("")
        lines.append(report.synthesized_answer)
        lines.append("")
        
        # References
        lines.append("## References")
        lines.append("")
        for ref in report.references:
            formatted_ref = ref.format_vancouver_style()
            lines.append(f"{ref.number}. {formatted_ref}")
        lines.append("")
        
        # Methodology
        if report.methodology_note:
            lines.append("## Methodology")
            lines.append("")
            lines.append(report.methodology_note)
            lines.append("")
        
        # Technical details
        lines.append("## Technical Details")
        lines.append("")
        lines.append("This report was generated using the BMLibrarian multi-agent system:")
        lines.append("")
        lines.append("1. **Query Generation:** Natural language question converted to database query")
        lines.append("2. **Document Retrieval:** PostgreSQL full-text search with pgvector extension")
        lines.append("3. **Relevance Scoring:** AI-powered document scoring (1-5 scale)")
        lines.append("4. **Citation Extraction:** Relevant passage extraction from high-scoring documents")
        lines.append("5. **Report Synthesis:** Medical publication-style report generation")
        lines.append("")
        lines.append("**AI Models Used:**")
        lines.append("- Document scoring and citation extraction: LLM via Ollama")
        lines.append("- Report synthesis: Medical writing-focused language model")
        lines.append("")
        lines.append("**Quality Controls:**")
        lines.append("- Document ID verification prevents citation hallucination")
        lines.append("- Evidence strength assessment based on citation quality and quantity")
        lines.append("- Human-in-the-loop validation at each processing step")
        
        # Add counterfactual analysis section if available
        if counterfactual_analysis:
            lines.append("")
            lines.append("## Counterfactual Analysis")
            lines.append("")
            lines.append(f"**Original Confidence Level:** {counterfactual_analysis.confidence_level}")
            lines.append("")
            lines.append("### Main Claims Analyzed")
            lines.append("")
            for i, claim in enumerate(counterfactual_analysis.main_claims, 1):
                lines.append(f"{i}. {claim}")
            lines.append("")
            
            lines.append("### Research Questions for Contradictory Evidence")
            lines.append("")
            
            # Group questions by priority
            high_priority = [q for q in counterfactual_analysis.counterfactual_questions if q.priority == "HIGH"]
            medium_priority = [q for q in counterfactual_analysis.counterfactual_questions if q.priority == "MEDIUM"]
            low_priority = [q for q in counterfactual_analysis.counterfactual_questions if q.priority == "LOW"]
            
            if high_priority:
                lines.append("#### High Priority Questions")
                lines.append("")
                for i, question in enumerate(high_priority, 1):
                    lines.append(f"**Question {i}:** {question.question}")
                    lines.append("")
                    lines.append(f"*Target Claim:* {question.target_claim}")
                    lines.append("")
                    lines.append(f"*Reasoning:* {question.reasoning}")
                    lines.append("")
                    lines.append(f"*Search Keywords:* {', '.join(question.search_keywords)}")
                    lines.append("")
                    lines.append("---")
                    lines.append("")
            
            if medium_priority:
                lines.append("#### Medium Priority Questions")
                lines.append("")
                for i, question in enumerate(medium_priority, 1):
                    lines.append(f"**Question {i}:** {question.question}")
                    lines.append("")
                    lines.append(f"*Target Claim:* {question.target_claim}")
                    lines.append("")
                    lines.append(f"*Search Keywords:* {', '.join(question.search_keywords)}")
                    lines.append("")
            
            if low_priority:
                lines.append("#### Low Priority Questions")
                lines.append("")
                for i, question in enumerate(low_priority, 1):
                    lines.append(f"**Question {i}:** {question.question}")
                    lines.append("")
            
            lines.append("### Overall Assessment")
            lines.append("")
            lines.append(counterfactual_analysis.overall_assessment)
            lines.append("")
        
        return "\n".join(lines)
    
    def perform_counterfactual_analysis(self, report: Report) -> Optional[CounterfactualAnalysis]:
        """Perform counterfactual analysis on the generated report."""
        print("\n" + "=" * 60)
        print("Step 7: Counterfactual Analysis")
        print("=" * 60)
        
        try:
            print(f"\n🔍 Analyzing report for potential contradictory evidence...")
            print("   This will identify claims and generate research questions")
            print("   to find evidence that might contradict the report's conclusions.")
            print("\n⏳ Performing counterfactual analysis...")
            
            # Format the report content for analysis
            formatted_report = self.reporting_agent.format_report_output(report)
            
            # Perform counterfactual analysis
            analysis = self.counterfactual_agent.analyze_document(
                document_content=formatted_report,
                document_title=f"Research Report: {self.current_question[:50]}..."
            )
            
            if not analysis:
                print("❌ Failed to perform counterfactual analysis.")
                return None
            
            print(f"\n✅ Counterfactual analysis completed!")
            print(f"   Confidence in original claims: {analysis.confidence_level}")
            print(f"   Main claims identified: {len(analysis.main_claims)}")
            print(f"   Research questions generated: {len(analysis.counterfactual_questions)}")
            
            # Display main claims
            print("\n📋 Main Claims Identified:")
            for i, claim in enumerate(analysis.main_claims, 1):
                print(f"   {i}. {claim}")
            
            # Display counterfactual questions by priority
            high_priority = [q for q in analysis.counterfactual_questions if q.priority == "HIGH"]
            medium_priority = [q for q in analysis.counterfactual_questions if q.priority == "MEDIUM"]
            low_priority = [q for q in analysis.counterfactual_questions if q.priority == "LOW"]
            
            if high_priority:
                print(f"\n🔴 HIGH PRIORITY Research Questions ({len(high_priority)}):")
                for i, question in enumerate(high_priority, 1):
                    print(f"   {i}. {question.question}")
                    print(f"      Target: {question.target_claim}")
                    print(f"      Keywords: {', '.join(question.search_keywords)}")
                    print()
            
            if medium_priority:
                print(f"\n🟡 MEDIUM PRIORITY Research Questions ({len(medium_priority)}):")
                for i, question in enumerate(medium_priority, 1):
                    print(f"   {i}. {question.question}")
                    print()
            
            if low_priority:
                print(f"\n🟢 LOW PRIORITY Research Questions ({len(low_priority)}):")
                for i, question in enumerate(low_priority, 1):
                    print(f"   {i}. {question.question}")
                    print()
            
            print(f"\n📊 Overall Assessment:")
            print(f"   {analysis.overall_assessment}")
            
            # Ask if user wants to search for contradictory evidence
            while True:
                search_choice = input("\n🔍 Search database for contradictory evidence? (y/n): ").strip().lower()
                if search_choice in ['y', 'yes']:
                    self.search_contradictory_evidence(analysis)
                    break
                elif search_choice in ['n', 'no']:
                    print("Skipping contradictory evidence search.")
                    break
                else:
                    print("Please enter 'y' or 'n'.")
            
            return analysis
            
        except Exception as e:
            print(f"❌ Error in counterfactual analysis: {e}")
            return None
    
    def search_contradictory_evidence(self, analysis: CounterfactualAnalysis):
        """Search for contradictory evidence based on counterfactual analysis."""
        print("\n" + "=" * 60)
        print("Contradictory Evidence Search")
        print("=" * 60)
        
        try:
            print(f"\n🔍 Searching for contradictory evidence...")
            print("   Using high-priority questions to find opposing studies")
            print("\n⏳ This may take several minutes...")
            
            # Get formatted report content for the search
            formatted_report = self.reporting_agent.format_report_output(self.final_report)
            
            # Use the complete counterfactual workflow
            contradictory_results = self.counterfactual_agent.find_contradictory_literature(
                document_content=formatted_report,
                document_title=f"Research Report: {self.current_question[:50]}...",
                max_results_per_query=5,
                min_relevance_score=3,
                query_agent=self.query_agent,
                scoring_agent=self.scoring_agent,
                citation_agent=self.citation_agent
            )
            
            if contradictory_results['contradictory_evidence']:
                print(f"\n✅ Found {len(contradictory_results['contradictory_evidence'])} contradictory documents")
                
                # Display top contradictory evidence
                print("\n📄 Top Contradictory Evidence:")
                sorted_evidence = sorted(
                    contradictory_results['contradictory_evidence'], 
                    key=lambda x: x['score'], 
                    reverse=True
                )
                
                for i, evidence in enumerate(sorted_evidence[:3], 1):
                    doc = evidence['document']
                    print(f"\n{i}. Score: {evidence['score']}/5")
                    print(f"   Title: {doc.get('title', 'No title')}")
                    print(f"   Authors: {', '.join(doc.get('authors', [])[:3])}")
                    print(f"   Target Claim: {evidence['query_info']['target_claim']}")
                    print(f"   Reasoning: {evidence['reasoning']}")
                
                if contradictory_results['contradictory_citations']:
                    print(f"\n📝 Extracted {len(contradictory_results['contradictory_citations'])} contradictory citations")
                    
                    # Display key contradictory citations
                    for i, cit_info in enumerate(contradictory_results['contradictory_citations'][:2], 1):
                        citation = cit_info['citation']
                        print(f"\n{i}. Citation:")
                        print(f"   Document: {citation.document_title}")
                        print(f"   Relevance: {citation.relevance_score:.3f}")
                        print(f"   Passage: \"{citation.passage[:150]}...\"")
                        print(f"   Contradicts: {cit_info['original_claim']}")
                
                # Update analysis summary
                summary = contradictory_results['summary']
                if summary['contradictory_citations_extracted'] > 0:
                    print(f"\n⚠️  RECOMMENDATION: Consider revising confidence level to {summary['revised_confidence']}")
                    print("   Contradictory evidence was found that may challenge some claims.")
                else:
                    print(f"\n✅ No strong contradictory evidence found.")
                    print("   Original report confidence level appears justified.")
            else:
                print(f"\n✅ No contradictory evidence found in the database.")
                print("   This supports the confidence in the original report.")
                
        except Exception as e:
            print(f"❌ Error searching for contradictory evidence: {e}")
    
    def run_complete_workflow(self):
        """Execute the complete research workflow with user interaction."""
        try:
            # Setup
            if not self.setup_agents():
                print("\n❌ Cannot proceed without proper agent setup.")
                return
            
            # Start orchestrator
            self.orchestrator.start_processing()
            
            # Step 1: Get research question
            question = self.get_user_question()
            
            # Step 2: Search documents using QueryAgent
            documents = self.search_documents_with_review(question)
            if not documents:
                print("❌ Cannot proceed without documents.")
                return
            
            # Step 3: Display and review documents
            documents = self.display_documents(documents)
            if not documents:
                return
            
            # Step 4: Score documents using DocumentScoringAgent
            scored_docs = self.score_documents_with_review(question, documents)
            if not scored_docs:
                print("❌ Cannot proceed without scored documents.")
                return
            
            # Step 5: Extract citations using CitationFinderAgent
            citations = self.extract_citations_with_review(question, scored_docs)
            if not citations:
                print("❌ Cannot proceed without citations.")
                return
            
            # Step 6: Generate report using ReportingAgent
            report = self.generate_final_report(question, citations)
            if not report:
                print("❌ Report generation failed.")
                return
            
            # Step 7: Optional counterfactual analysis
            counterfactual_analysis = None
            while True:
                counter_choice = input("\n🔍 Perform counterfactual analysis to find contradictory evidence? (y/n): ").strip().lower()
                if counter_choice in ['y', 'yes']:
                    counterfactual_analysis = self.perform_counterfactual_analysis(report)
                    break
                elif counter_choice in ['n', 'no']:
                    print("Skipping counterfactual analysis.")
                    break
                else:
                    print("Please enter 'y' or 'n'.")
            
            # Step 8: Save report
            while True:
                save_choice = input("\n💾 Save report as markdown file? (y/n): ").strip().lower()
                if save_choice in ['y', 'yes']:
                    self.save_report_as_markdown(report, counterfactual_analysis)
                    break
                elif save_choice in ['n', 'no']:
                    print("Report not saved.")
                    break
                else:
                    print("Please enter 'y' or 'n'.")
            
            # Final summary
            print(f"\n🎉 Research workflow completed successfully!")
            print(f"   Question: {question[:60]}...")
            print(f"   Documents found: {len(documents)}")
            print(f"   Documents scored: {len(scored_docs)}")
            print(f"   Citations extracted: {len(citations)}")
            print(f"   Evidence strength: {report.evidence_strength}")
            if counterfactual_analysis:
                print(f"   Counterfactual analysis: {len(counterfactual_analysis.counterfactual_questions)} questions generated")
                print(f"   Original confidence: {counterfactual_analysis.confidence_level}")
            
        except KeyboardInterrupt:
            print(f"\n\n⏹️  Workflow interrupted by user.")
        except Exception as e:
            print(f"\n❌ Workflow error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.orchestrator:
                self.orchestrator.stop_processing()
    
    def show_configuration_menu(self):
        """Show and modify configuration settings."""
        while True:
            print(f"\n⚙️  Configuration Settings")
            print("=" * 40)
            print(f"1. Max search results: {self.max_search_results}")
            print(f"2. Timeout duration: {self.timeout_minutes} minutes")
            print(f"3. Score threshold: {self.default_score_threshold}")
            print(f"4. Min relevance: {self.default_min_relevance}")
            print(f"5. Documents display limit: {self.max_documents_display}")
            print("6. Reset to defaults")
            print("7. Back to main menu")
            
            choice = input("\nChoose option (1-7): ").strip()
            
            if choice == '1':
                try:
                    new_max = int(input(f"Enter max search results (current: {self.max_search_results}): "))
                    if 1 <= new_max <= 1000:
                        self.max_search_results = new_max
                        print(f"✅ Max search results set to {new_max}")
                    else:
                        print("❌ Please enter a number between 1 and 1000")
                except ValueError:
                    print("❌ Please enter a valid number")
            
            elif choice == '2':
                try:
                    new_timeout = float(input(f"Enter timeout in minutes (current: {self.timeout_minutes}): "))
                    if 0.5 <= new_timeout <= 30:
                        self.timeout_minutes = new_timeout
                        print(f"✅ Timeout set to {new_timeout} minutes")
                    else:
                        print("❌ Please enter a number between 0.5 and 30 minutes")
                except ValueError:
                    print("❌ Please enter a valid number")
            
            elif choice == '3':
                try:
                    new_threshold = float(input(f"Enter score threshold (current: {self.default_score_threshold}): "))
                    if 0 <= new_threshold <= 5:
                        self.default_score_threshold = new_threshold
                        print(f"✅ Score threshold set to {new_threshold}")
                    else:
                        print("❌ Please enter a number between 0 and 5")
                except ValueError:
                    print("❌ Please enter a valid number")
            
            elif choice == '4':
                try:
                    new_relevance = float(input(f"Enter min relevance (current: {self.default_min_relevance}): "))
                    if 0 <= new_relevance <= 1:
                        self.default_min_relevance = new_relevance
                        print(f"✅ Min relevance set to {new_relevance}")
                    else:
                        print("❌ Please enter a number between 0 and 1")
                except ValueError:
                    print("❌ Please enter a valid number")
            
            elif choice == '5':
                try:
                    new_display = int(input(f"Enter documents display limit (current: {self.max_documents_display}): "))
                    if 1 <= new_display <= 50:
                        self.max_documents_display = new_display
                        print(f"✅ Documents display limit set to {new_display}")
                    else:
                        print("❌ Please enter a number between 1 and 50")
                except ValueError:
                    print("❌ Please enter a valid number")
            
            elif choice == '6':
                self.max_search_results = 100
                self.timeout_minutes = 5
                self.default_score_threshold = 2.5
                self.default_min_relevance = 0.7
                self.max_documents_display = 10
                print("✅ All settings reset to defaults")
            
            elif choice == '7':
                break
            
            else:
                print("❌ Invalid option. Please choose 1-7.")
    
    def show_main_menu(self):
        """Display main menu and handle user choices."""
        while True:
            print(f"\n🏥 BMLibrarian Medical Research CLI")
            print("=" * 50)
            print("1. Start new research workflow")
            print("2. Resume previous session")
            print("3. Test system connections")
            print("4. Configuration settings")
            print("5. View documentation")
            print("6. Exit")
            
            choice = input("\nChoose option (1-6): ").strip()
            
            if choice == '1':
                self.run_complete_workflow()
            elif choice == '2':
                print("❌ Session resume not implemented yet.")
            elif choice == '3':
                self.setup_agents()
            elif choice == '4':
                self.show_configuration_menu()
            elif choice == '5':
                self.show_documentation()
            elif choice == '6':
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid option. Please choose 1-6.")
    
    def show_documentation(self):
        """Show basic documentation and help."""
        print(f"\n📚 BMLibrarian CLI Documentation")
        print("=" * 50)
        print()
        print("This CLI provides an interactive workflow for evidence-based medical research:")
        print()
        print("1. **Research Question:** Enter your medical research question")
        print("2. **Query Generation:** AI generates PostgreSQL to_tsquery with human editing")
        print("3. **Document Search:** Execute database search and review results")
        print("4. **Relevance Scoring:** AI scores documents (1-5) for relevance")
        print("5. **Citation Extraction:** Extract relevant passages from high-scoring documents")
        print("6. **Report Generation:** Create medical publication-style report")
        print("7. **Counterfactual Analysis:** (Optional) Analyze report for contradictory evidence")
        print("8. **Export:** Save report as markdown file")
        print()
        print("**Requirements:**")
        print("• PostgreSQL database with biomedical literature")
        print("• Ollama service running locally (http://localhost:11434)")
        print("• Models: gpt-oss:20b, medgemma4B_it_q8:latest")
        print()
        print("**Tips:**")
        print("• Be specific in your research questions")
        print("• Review and edit generated queries for better results")
        print("• Adjust score thresholds based on your needs")
        print("• Higher thresholds = fewer but more relevant results")
        print()
        
        input("Press Enter to continue...")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="BMLibrarian Interactive Medical Literature Research CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bmlibrarian_cli.py                    # Default settings
  python bmlibrarian_cli.py --max-results 50  # Limit search to 50 documents  
  python bmlibrarian_cli.py --timeout 10      # Set 10-minute timeout
  python bmlibrarian_cli.py --quick           # Quick testing mode (20 results, 2 min timeout)
        """
    )
    
    parser.add_argument(
        '--max-results', 
        type=int, 
        default=100,
        metavar='N',
        help='Maximum number of search results to retrieve (default: 100)'
    )
    
    parser.add_argument(
        '--timeout',
        type=float,
        default=5.0,
        metavar='M',
        help='Timeout duration in minutes for report generation (default: 5.0)'
    )
    
    parser.add_argument(
        '--score-threshold',
        type=float,
        default=2.5,
        metavar='S',
        help='Default document score threshold (default: 2.5)'
    )
    
    parser.add_argument(
        '--min-relevance',
        type=float,
        default=0.7,
        metavar='R',
        help='Default minimum citation relevance (default: 0.7)'
    )
    
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Quick testing mode (20 results, 2-minute timeout, lower thresholds)'
    )
    
    return parser.parse_args()


def main():
    """Main entry point for the CLI application."""
    try:
        # Parse command line arguments
        args = parse_args()
        
        # Create CLI with custom settings
        cli = MedicalResearchCLI()
        
        # Apply command line arguments
        if args.quick:
            cli.max_search_results = 20
            cli.timeout_minutes = 2
            cli.default_score_threshold = 2.0
            cli.default_min_relevance = 0.6
            print("🚀 Quick testing mode enabled!")
        else:
            cli.max_search_results = args.max_results
            cli.timeout_minutes = args.timeout
            cli.default_score_threshold = args.score_threshold
            cli.default_min_relevance = args.min_relevance
        
        # Show current configuration if non-default
        if (args.max_results != 100 or args.timeout != 5.0 or 
            args.score_threshold != 2.5 or args.min_relevance != 0.7 or args.quick):
            print(f"\n⚙️  Configuration:")
            print(f"   Max search results: {cli.max_search_results}")
            print(f"   Timeout: {cli.timeout_minutes} minutes")
            print(f"   Score threshold: {cli.default_score_threshold}")
            print(f"   Min relevance: {cli.default_min_relevance}")
        
        cli.show_main_menu()
    except KeyboardInterrupt:
        print(f"\n\n👋 Exiting BMLibrarian CLI...")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()