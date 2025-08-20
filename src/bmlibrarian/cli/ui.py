"""
User Interface Module

Handles all user interaction, display functions, and input validation for the CLI.
"""

from typing import List, Dict, Any, Tuple, Optional
from bmlibrarian.agents import Citation, Report


class UserInterface:
    """Handles user interface components and interactions."""
    
    def __init__(self, config):
        self.config = config
    
    def show_header(self) -> None:
        """Display the CLI header."""
        print("🏥 BMLibrarian Medical Research CLI")
        print("=" * 60)
    
    def show_main_menu(self) -> str:
        """Display main menu and get user choice."""
        print(f"\n🏥 BMLibrarian Medical Research CLI")
        print("=" * 50)
        print("1. Start new research workflow")
        print("2. Resume previous session")
        print("3. Test system connections")
        print("4. Configuration settings")
        print("5. View documentation")
        print("6. Exit")
        
        return input("\nChoose option (1-6): ").strip()
    
    def get_research_question(self) -> Optional[str]:
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
                return question
            
            print("Let's try again...")
    
    def display_query_review(self, question: str, current_query: str) -> str:
        """Display generated query and get user choice for editing."""
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
        
        return input("Choose option (1-4): ").strip()
    
    def get_manual_query_edit(self, current_query: str) -> str:
        """Handle manual query editing."""
        print(f"\n✏️  Manual Query Editing:")
        print("Current query:", current_query)
        print("\nTips for editing:")
        print("• Use & for AND, | for OR")
        print("• Use parentheses to group terms")
        print("• Keep medical terminology")
        print("• Example: (diabetes | diabetic) & (treatment | therapy)")
        
        new_query = input("\nEnter your edited query: ").strip()
        return new_query if new_query else current_query
    
    def display_search_results(self, documents: List[Dict[str, Any]]) -> str:
        """Display search results and get user choice."""
        print("\n" + "=" * 60)
        print("Step 3: Document Review")
        print("=" * 60)
        
        if not documents:
            return "empty"
        
        # Display sample results
        print(f"\n📄 Showing first {min(self.config.max_documents_display, len(documents))} documents:")
        print("=" * 80)
        
        for i, doc in enumerate(documents[:self.config.max_documents_display], 1):
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
        
        if len(documents) > self.config.max_documents_display:
            print(f"\n... and {len(documents) - self.config.max_documents_display} more documents")
        
        # Ask user if they want to proceed
        print(f"\nFound {len(documents)} total documents.")
        print("Options:")
        print("1. Proceed with these results")
        print("2. Search again with different terms")
        print("3. Show more document details")
        
        return input("Choose option (1-3): ").strip()
    
    def show_detailed_documents(self, documents: List[Dict[str, Any]]) -> None:
        """Show detailed view of documents with pagination."""
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
    
    def display_document_scores(self, scored_docs: List[Tuple[Dict[str, Any], Dict[str, Any]]], 
                               score_threshold: float) -> str:
        """Display document scores and get user choice."""
        print("\n" + "=" * 60)
        print("Step 4: Document Relevance Scoring")
        print("=" * 60)
        
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
        self._show_score_distribution(scored_docs)
        
        # Ask about score threshold
        high_scoring = len([doc for doc, score in scored_docs if score.get('score', 0) > score_threshold])
        print(f"\n⚙️  Configuration:")
        print(f"   Current threshold: {score_threshold}")
        print(f"   Documents above threshold: {high_scoring}")
        
        print("\nOptions:")
        print("1. Proceed with current threshold")
        print("2. Adjust score threshold")
        print("3. Review individual scores")
        print("4. Re-score with different parameters")
        
        return input("Choose option (1-4): ").strip()
    
    def _show_score_distribution(self, scored_docs: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> None:
        """Show score distribution chart."""
        score_counts = {}
        for _, score_result in scored_docs:
            score = int(score_result.get('score', 0))
            score_counts[score] = score_counts.get(score, 0) + 1
        
        print(f"\n📈 Score Distribution:")
        for score in range(5, 0, -1):
            count = score_counts.get(score, 0)
            bar = "█" * min(count, 20)
            print(f"   {score}/5: {count:3d} docs {bar}")
    
    def show_detailed_scores(self, scored_docs: List[Tuple[Dict[str, Any], Dict[str, Any]]]) -> None:
        """Show detailed view of document scores with pagination."""
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
    
    def get_score_threshold_adjustment(self, current_threshold: float) -> Optional[float]:
        """Get new score threshold from user."""
        while True:
            try:
                new_threshold = float(input(f"Enter new threshold (current: {current_threshold}): "))
                if 0 <= new_threshold <= 5:
                    return new_threshold
                else:
                    print("❌ Threshold must be between 0 and 5")
            except ValueError:
                print("❌ Please enter a valid number")
    
    def display_citations(self, citations: List[Citation], score_threshold: float, 
                         min_relevance: float) -> str:
        """Display extracted citations and get user choice."""
        print("\n" + "=" * 60)
        print("Step 5: Citation Extraction")
        print("=" * 60)
        
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
        stats = self._calculate_citation_stats(citations)
        print(f"\n📊 Citation Statistics:")
        print(f"   Total citations: {stats['total_citations']}")
        print(f"   Unique documents: {stats['unique_documents']}")
        print(f"   Average relevance: {stats['average_relevance']:.3f}")
        print(f"   Relevance range: {stats['min_relevance']:.3f} - {stats['max_relevance']:.3f}")
        
        print(f"\nCitation options:")
        print("1. Proceed with these citations")
        print("2. Adjust relevance threshold")
        print("3. Review individual citations")
        print("4. Go back to adjust document scores")
        
        # Add helpful suggestion for small citation sets
        if len(citations) <= 2:
            print(f"\n💡 Suggestion: You have {len(citations)} citation(s). For a more comprehensive report:")
            print("   • Choose option 2 to lower relevance threshold")
            print("   • Choose option 4 to lower document score threshold")
        
        return input("Choose option (1-4): ").strip()
    
    def show_detailed_citations(self, citations: List[Citation]) -> None:
        """Show detailed view of citations with pagination."""
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
    
    def get_relevance_threshold_adjustment(self, current_relevance: float) -> Optional[float]:
        """Get new relevance threshold from user."""
        while True:
            try:
                new_relevance = float(input(f"Enter new minimum relevance (current: {current_relevance}): "))
                if 0 <= new_relevance <= 1:
                    return new_relevance
                else:
                    print("❌ Relevance must be between 0 and 1")
            except ValueError:
                print("❌ Please enter a valid number")
    
    def handle_large_citation_set(self, citation_count: int) -> str:
        """Handle large citation sets with user options."""
        print(f"\n⚠️  You have {citation_count} citations. Large citation sets may:")
        print("• Take a long time to process (5-10 minutes)")
        print("• Cause timeouts with the AI model")
        print("• Produce less focused reports")
        
        print(f"\nOptions:")
        print("1. Proceed with all citations (may be slow)")
        print("2. Use only the top citations by relevance")
        print("3. Go back and increase citation thresholds")
        
        return input("Choose option (1-3): ").strip()
    
    def display_report(self, report: Report, reporting_agent=None) -> None:
        """Display the generated report."""
        print("\n" + "=" * 60)
        print("Step 6: Report Generation")
        print("=" * 60)
        
        print(f"\n✅ Report generated successfully!")
        print(f"   Evidence strength: {report.evidence_strength}")
        print(f"   Citations analyzed: {report.citation_count}")
        print(f"   Unique references: {report.unique_documents}")
        
        # Format the report using the agent instance or create a basic format
        if reporting_agent:
            formatted_report = reporting_agent.format_report_output(report)
        else:
            formatted_report = self._format_basic_report(report)
        
        print("\n" + "=" * 80)
        print("GENERATED RESEARCH REPORT")
        print("=" * 80)
        print(formatted_report)
        print("=" * 80)
    
    def get_save_report_choice(self) -> bool:
        """Get user choice for saving report."""
        while True:
            save_choice = input("\n💾 Save report as markdown file? (y/n): ").strip().lower()
            if save_choice in ['y', 'yes']:
                return True
            elif save_choice in ['n', 'no']:
                return False
            else:
                print("Please enter 'y' or 'n'.")
    
    def get_report_filename(self, question: str) -> str:
        """Get filename for saving report."""
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        question_slug = "".join(c if c.isalnum() or c in [' ', '-'] else '' for c in question)
        question_slug = "_".join(question_slug.split()[:5])  # First 5 words
        
        default_filename = f"bmlibrarian_report_{question_slug}_{timestamp}.md"
        
        print(f"\n💾 Save report as markdown file:")
        filename = input(f"Filename (default: {default_filename}): ").strip()
        
        if not filename:
            filename = default_filename
        
        if not filename.endswith('.md'):
            filename += '.md'
        
        return filename
    
    def show_file_saved(self, filename: str, file_size: int, content_preview: str) -> None:
        """Show confirmation of file save."""
        print(f"✅ Report saved as: {filename}")
        print(f"   File size: {file_size} bytes")
        
        # Show file preview
        print(f"\n📄 File preview (first 300 characters):")
        print("-" * 50)
        print(content_preview[:300] + ("..." if len(content_preview) > 300 else ""))
        print("-" * 50)
    
    def show_workflow_summary(self, question: str, documents_count: int, scored_count: int, 
                            citations_count: int, evidence_strength: str) -> None:
        """Show final workflow summary."""
        print(f"\n🎉 Research workflow completed successfully!")
        print(f"   Question: {question[:60]}...")
        print(f"   Documents found: {documents_count}")
        print(f"   Documents scored: {scored_count}")
        print(f"   Citations extracted: {citations_count}")
        print(f"   Evidence strength: {evidence_strength}")
    
    def show_documentation(self) -> None:
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
        print("7. **Export:** Save report as markdown file")
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
    
    def show_progress_message(self, message: str) -> None:
        """Show a progress message."""
        print(f"⏳ {message}")
    
    def show_success_message(self, message: str) -> None:
        """Show a success message."""
        print(f"✅ {message}")
    
    def show_error_message(self, message: str) -> None:
        """Show an error message."""
        print(f"❌ {message}")
    
    def show_warning_message(self, message: str) -> None:
        """Show a warning message."""
        print(f"⚠️  {message}")
    
    def show_info_message(self, message: str) -> None:
        """Show an info message."""
        print(f"ℹ️  {message}")
    
    def show_step_header(self, step_num: int, step_name: str) -> None:
        """Show a step header."""
        print("\n" + "=" * 60)
        print(f"Step {step_num}: {step_name}")
        print("=" * 60)
    
    def _calculate_citation_stats(self, citations: List[Citation]) -> Dict[str, Any]:
        """Calculate statistics for citations."""
        if not citations:
            return {
                'total_citations': 0,
                'unique_documents': 0,
                'average_relevance': 0.0,
                'min_relevance': 0.0,
                'max_relevance': 0.0
            }
        
        # Count unique documents
        unique_docs = set(citation.document_id for citation in citations)
        
        # Calculate relevance statistics
        relevance_scores = [citation.relevance_score for citation in citations]
        
        return {
            'total_citations': len(citations),
            'unique_documents': len(unique_docs),
            'average_relevance': sum(relevance_scores) / len(relevance_scores),
            'min_relevance': min(relevance_scores),
            'max_relevance': max(relevance_scores)
        }
    
    def _format_basic_report(self, report: Report) -> str:
        """Format a basic report when no reporting agent is available."""
        lines = []
        
        # Title
        lines.append(f"Research Question: {report.user_question}")
        lines.append("")
        
        # Evidence assessment
        lines.append(f"Evidence Strength: {report.evidence_strength}")
        lines.append(f"Citations Analyzed: {report.citation_count}")
        lines.append(f"Unique References: {report.unique_documents}")
        lines.append("")
        
        # Main findings
        lines.append("Findings:")
        lines.append("-" * 40)
        lines.append(report.synthesized_answer)
        lines.append("")
        
        # References
        if report.references:
            lines.append("References:")
            lines.append("-" * 40)
            for ref in report.references:
                lines.append(f"{ref.number}. {ref.title}")
                lines.append(f"   Authors: {', '.join(ref.authors)}")
                lines.append(f"   Date: {ref.publication_date}")
                lines.append("")
        
        return "\n".join(lines)