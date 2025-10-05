"""
User Interface Module

Handles all user interaction, display functions, and input validation for the CLI.
"""

from typing import List, Dict, Any, Tuple, Optional
from bmlibrarian.agents import Citation, Report, CounterfactualAnalysis


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
        if self.config.auto_mode:
            # In auto mode, we need a default research question or should be provided externally
            return None
        
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
        if self.config.auto_mode:
            print(f"\n📋 Generated PostgreSQL Query: {current_query}")
            return "1"  # Auto-accept the query
        
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
        if self.config.auto_mode:
            print(f"\n📄 Found {len(documents)} documents - auto-proceeding...")
            return "1"  # Auto-proceed
        
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
        if self.config.auto_mode:
            high_scoring = len([doc for doc, score in scored_docs if score.get('score', 0) > score_threshold])
            print(f"\n📊 Scored {len(scored_docs)} documents, {high_scoring} above threshold {score_threshold} - auto-proceeding...")
            return "1"  # Auto-proceed
        
        print("\n" + "=" * 60)
        print("Step 4: Document Relevance Scoring")
        print("=" * 60)
        
        print(f"\n✅ Successfully scored {len(scored_docs)} documents")

        # Separate documents by threshold
        high_scoring_docs = [(doc, score) for doc, score in scored_docs if score.get('score', 0) > score_threshold]
        low_scoring_docs = [(doc, score) for doc, score in scored_docs if score.get('score', 0) <= score_threshold]

        # Display scoring results
        print("\n📊 Document Scores (1-5 scale, 5=most relevant):")
        print("=" * 80)

        # Show high-scoring documents first
        if high_scoring_docs:
            print(f"\n🎯 HIGH-SCORING DOCUMENTS (Above threshold {score_threshold}): {len(high_scoring_docs)}")
            print("=" * 80)
            for i, (doc, score_result) in enumerate(high_scoring_docs, 1):
                score = score_result.get('score', 0)
                reasoning = score_result.get('reasoning', 'No reasoning provided')

                # Color coding for scores
                if score >= 4:
                    score_display = f"🟢 {score}/5"
                elif score >= 3:
                    score_display = f"🟡 {score}/5"
                else:
                    score_display = f"🟠 {score}/5"

                print(f"\n{i}. {score_display} - {doc.get('title', 'No title')[:60]}")
                print(f"   ID: {doc.get('id')}")
                print(f"   Reasoning: {reasoning}")
                print("-" * 80)

        # Show low-scoring documents
        if low_scoring_docs:
            print(f"\n📉 LOW-SCORING DOCUMENTS (At or below threshold {score_threshold}): {len(low_scoring_docs)}")
            print("=" * 80)
            for i, (doc, score_result) in enumerate(low_scoring_docs, 1):
                score = score_result.get('score', 0)
                reasoning = score_result.get('reasoning', 'No reasoning provided')

                # Color coding for scores
                if score >= 2:
                    score_display = f"🟠 {score}/5"
                else:
                    score_display = f"🔴 {score}/5"

                print(f"\n{i}. {score_display} - {doc.get('title', 'No title')[:60]}")
                print(f"   ID: {doc.get('id')}")
                print(f"   Reasoning: {reasoning}")
                print("-" * 80)

        # Show score distribution
        self._show_score_distribution(scored_docs)

        # Ask about score threshold
        high_scoring = len(high_scoring_docs)
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
        if self.config.auto_mode:
            stats = self._calculate_citation_stats(citations)
            print(f"\n📝 Extracted {len(citations)} citations (avg relevance: {stats['average_relevance']:.3f}) - auto-proceeding...")
            return "1"  # Auto-proceed
        
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
        if self.config.auto_mode:
            # In auto mode, automatically use top citations by relevance for performance
            print(f"\n⚠️  Auto-mode: {citation_count} citations detected. Using top 15 citations by relevance for optimal performance.")
            return "2"  # Use only the top citations by relevance
        
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
    
    def display_comprehensive_report(self, comprehensive_report, editor_agent=None, methodology_metadata=None) -> None:
        """Display the comprehensive edited report."""
        print("\n" + "=" * 60)
        print("Step 8: Comprehensive Report Generation")
        print("=" * 60)
        
        print(f"\n✅ Comprehensive report generated successfully!")
        print(f"   Evidence Confidence: {comprehensive_report.confidence_assessment}")
        print(f"   Word Count: {comprehensive_report.word_count}")
        print(f"   References: {len(comprehensive_report.references)}")
        
        if comprehensive_report.contradictory_evidence_section:
            print(f"   Includes contradictory evidence analysis")
        
        # Format the report using the agent instance or create a basic format
        if editor_agent:
            # Use template-based formatting to ensure programmatic references and methodology
            formatted_report = editor_agent.format_comprehensive_markdown_template(
                comprehensive_report, 
                methodology_metadata=methodology_metadata
            )
        else:
            formatted_report = self._format_basic_comprehensive_report(comprehensive_report)
        
        print("\n" + "=" * 80)
        print("COMPREHENSIVE RESEARCH REPORT")
        print("=" * 80)
        print(formatted_report[:2000])  # Show first 2000 characters
        if len(formatted_report) > 2000:
            print("\n[... Report truncated for display. Full report will be saved to file ...]\n")
        print("=" * 80)
    
    def _format_basic_comprehensive_report(self, comprehensive_report) -> str:
        """Format a basic comprehensive report when no editor agent is available."""
        lines = []
        
        # Title and metadata
        lines.append(f"# {comprehensive_report.title}")
        lines.append("")
        lines.append(f"**Evidence Confidence:** {comprehensive_report.confidence_assessment}")
        lines.append(f"**Word Count:** {comprehensive_report.word_count}")
        lines.append("")
        
        # Executive Summary
        lines.append("## Executive Summary")
        lines.append(comprehensive_report.executive_summary)
        lines.append("")
        
        # Main sections
        if comprehensive_report.findings_section:
            lines.append("## Findings")
            lines.append(comprehensive_report.findings_section)
            lines.append("")
        
        if comprehensive_report.contradictory_evidence_section:
            lines.append("## Contradictory Evidence")
            lines.append(comprehensive_report.contradictory_evidence_section)
            lines.append("")
        
        if comprehensive_report.limitations_section:
            lines.append("## Limitations")
            lines.append(comprehensive_report.limitations_section)
            lines.append("")
        
        if comprehensive_report.conclusions_section:
            lines.append("## Conclusions")
            lines.append(comprehensive_report.conclusions_section)
            lines.append("")
        
        return "\n".join(lines)
    
    def get_save_report_choice(self) -> bool:
        """Get user choice for saving report."""
        if self.config.auto_mode:
            print("\n💾 Auto-mode: Saving report as markdown file...")
            return True  # Auto-save report
        
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
        
        if self.config.auto_mode:
            print(f"\n💾 Auto-generated filename: {default_filename}")
            return default_filename
        
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
                            citations_count: int, evidence_strength: str, counterfactual_analysis: Optional[CounterfactualAnalysis] = None) -> None:
        """Show final workflow summary."""
        print(f"\n🎉 Research workflow completed successfully!")
        print(f"   Question: {question[:60]}...")
        print(f"   Documents found: {documents_count}")
        print(f"   Documents scored: {scored_count}")
        print(f"   Citations extracted: {citations_count}")
        print(f"   Evidence strength: {evidence_strength}")
        if counterfactual_analysis:
            print(f"   Counterfactual analysis: {len(counterfactual_analysis.counterfactual_questions)} questions generated")
            print(f"   Original confidence: {counterfactual_analysis.confidence_level}")
    
    def get_counterfactual_analysis_choice(self) -> bool:
        """Ask user if they want to perform counterfactual analysis."""
        if self.config.auto_mode:
            print("\n🔍 Auto-mode: Performing counterfactual analysis...")
            return True  # Auto-perform counterfactual analysis
        
        while True:
            choice = input("\n🔍 Perform counterfactual analysis to find contradictory evidence? (y/n): ").strip().lower()
            if choice in ['y', 'yes']:
                return True
            elif choice in ['n', 'no']:
                self.show_info_message("Skipping counterfactual analysis.")
                return False
            else:
                print("Please enter 'y' or 'n'.")
    
    def display_counterfactual_analysis(self, analysis: CounterfactualAnalysis) -> None:
        """Display results of counterfactual analysis."""
        self.show_step_header(7, "Counterfactual Analysis Results")
        
        self.show_success_message("Counterfactual analysis completed!")
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
    
    def get_contradictory_evidence_search_choice(self) -> bool:
        """Ask user if they want to search for contradictory evidence."""
        if self.config.auto_mode:
            print("\n🔍 Auto-mode: Searching for contradictory evidence...")
            return True  # Auto-search for contradictory evidence
        
        while True:
            choice = input("\n🔍 Search database for contradictory evidence? (y/n): ").strip().lower()
            if choice in ['y', 'yes']:
                return True
            elif choice in ['n', 'no']:
                self.show_info_message("Skipping contradictory evidence search.")
                return False
            else:
                print("Please enter 'y' or 'n'.")
    
    def display_contradictory_evidence_results(self, contradictory_results: Dict[str, Any]) -> None:
        """Display results of contradictory evidence search."""
        print("\n" + "=" * 80)
        print("Contradictory Evidence Search Results")
        print("=" * 80)

        if contradictory_results.get('contradictory_evidence'):
            self.show_success_message(f"Found {len(contradictory_results.get('contradictory_evidence', []))} contradictory documents")

            # Display validated contradictory citations
            if contradictory_results.get('contradictory_citations'):
                self.show_success_message(f"✓ Extracted {len(contradictory_results.get('contradictory_citations', []))} VALIDATED contradictory citations")

                # Display key contradictory citations
                for i, cit_info in enumerate(contradictory_results.get('contradictory_citations', [])[:2], 1):
                    citation = cit_info['citation']
                    print(f"\n{i}. Citation:")
                    print(f"   Document: {citation.document_title}")
                    print(f"   Relevance: {citation.relevance_score:.3f}")
                    print(f"   Passage: \"{citation.passage[:150]}...\"")
                    print(f"   Contradicts: {cit_info['original_claim']}")

            # Display rejected citations with reasoning and allow user override
            rejected = contradictory_results.get('rejected_citations', [])
            if rejected:
                print(f"\n⚠️  {len(rejected)} citations were REJECTED during validation:")
                print("=" * 80)

                # Initialize skip flag
                self._skip_remaining_overrides = False

                for i, rejected_info in enumerate(rejected, 1):
                    citation = rejected_info['citation']
                    doc = rejected_info['document']

                    print(f"\n{'─' * 80}")
                    print(f"REJECTED CITATION #{i}")
                    print(f"{'─' * 80}")
                    print(f"📄 Document: {doc.get('title', 'No title')}")
                    print(f"👥 Authors: {', '.join(doc.get('authors', [])[:3])}")
                    print(f"📅 Year: {doc.get('publication_year', 'Unknown')}")
                    print(f"⭐ Relevance Score: {rejected_info['document_score']}/5")

                    print(f"\n🎯 Target Claim: {rejected_info['original_claim']}")
                    print(f"🔄 Counterfactual: {rejected_info['counterfactual_statement']}")

                    print(f"\n📝 Extracted Passage:")
                    print(f"   \"{citation.passage}\"")

                    print(f"\n❌ AI Rejection Reasoning:")
                    print(f"   {rejected_info['rejection_reasoning']}")

                    # Show full abstract for user judgment
                    abstract = doc.get('abstract', '')
                    if abstract:
                        print(f"\n📋 Full Abstract (for your judgment):")
                        print(f"   {abstract}")

                    print(f"\n💭 AI Scoring Reasoning:")
                    print(f"   {rejected_info['score_reasoning']}")

                    # Allow user override (skip if in auto mode or user chose to skip)
                    if not self._skip_remaining_overrides:
                        print(f"\n❓ Do you disagree with the AI's rejection?")
                        override_choice = self._get_user_override_for_rejected_citation(i, len(rejected))
                        if override_choice:
                            override_reasoning = self._get_user_override_reasoning()
                            # Mark this citation for inclusion with user override
                            rejected_info['user_override'] = True
                            rejected_info['user_reasoning'] = override_reasoning
                            # Move to contradictory_citations list
                            if 'contradictory_citations' not in contradictory_results:
                                contradictory_results['contradictory_citations'] = []
                            contradictory_results['contradictory_citations'].append(rejected_info)
                            self.show_success_message(f"✓ Citation #{i} ACCEPTED by user override")
                        else:
                            if not self._skip_remaining_overrides:
                                self.show_info_message(f"Citation #{i} remains rejected")

            # Display documents where no citation could be extracted
            no_citation = contradictory_results.get('no_citation_extracted', [])
            if no_citation:
                print(f"\n📭 {len(no_citation)} documents found but NO citation could be extracted:")
                print("=" * 80)

                for i, doc_info in enumerate(no_citation, 1):
                    doc = doc_info['document']
                    print(f"\n{i}. Document: {doc.get('title', 'No title')}")
                    print(f"   Authors: {', '.join(doc.get('authors', [])[:3])}")
                    print(f"   Year: {doc.get('publication_year', 'Unknown')}")
                    print(f"   Relevance Score: {doc_info['document_score']}/5")
                    print(f"   Target Claim: {doc_info['original_claim']}")

                    # Show abstract
                    abstract = doc.get('abstract', '')
                    if abstract:
                        print(f"   Abstract: {abstract[:300]}{'...' if len(abstract) > 300 else ''}")

            # Update analysis summary
            summary = contradictory_results.get('summary', {})
            if summary.get('contradictory_citations_extracted', 0) > 0:
                print(f"\n⚠️  RECOMMENDATION: Consider revising confidence level to {summary.get('revised_confidence', 'MEDIUM')}")
                print("   Contradictory evidence was found that may challenge some claims.")
            else:
                self.show_success_message("No strong contradictory evidence found.")
                print("   Original report confidence level appears justified.")
        else:
            self.show_success_message("No contradictory evidence found in the database.")
            print("   This supports the confidence in the original report.")
    
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

    def _get_user_override_for_rejected_citation(self, citation_num: int, total_rejected: int) -> bool:
        """Ask user if they want to override the AI's rejection of a citation."""
        while True:
            try:
                response = input(f"   Accept this citation anyway? (y/n/skip remaining): ").strip().lower()
                if response in ['y', 'yes']:
                    return True
                elif response in ['n', 'no']:
                    return False
                elif response in ['skip', 's', 'skip remaining']:
                    # Set a flag to skip all remaining rejections
                    self._skip_remaining_overrides = True
                    return False
                else:
                    print("   Please enter 'y', 'n', or 'skip remaining'.")
            except (KeyboardInterrupt, EOFError):
                print("\n   Skipping override prompt")
                return False

    def _get_user_override_reasoning(self) -> str:
        """Get user's reasoning for overriding the AI's rejection."""
        print("\n📝 Please provide your reasoning for accepting this citation:")
        print("   (Press Enter twice to finish, or Ctrl+D to skip)")
        lines = []
        try:
            while True:
                line = input("   ")
                if not line and lines:  # Empty line after some input
                    break
                if line:  # Non-empty line
                    lines.append(line)
        except (KeyboardInterrupt, EOFError):
            print("\n   Using default reasoning")
            return "User expert judgment - citation deemed relevant despite AI rejection"

        reasoning = " ".join(lines).strip()
        return reasoning if reasoning else "User expert judgment - citation deemed relevant despite AI rejection"

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