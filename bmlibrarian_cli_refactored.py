#!/usr/bin/env python3
"""
BMLibrarian CLI - Interactive Medical Literature Research Tool

A comprehensive command-line interface for conducting evidence-based medical literature research
using the full BMLibrarian multi-agent workflow with human-in-the-loop interaction.

This refactored version uses a modular architecture for better maintainability:
- config: Configuration management and command-line parsing
- ui: User interface components and display functions
- query_processing: Query validation, editing, and search orchestration
- formatting: Report formatting and export utilities
- workflow: Main research workflow orchestration

Features:
- Interactive query generation and editing
- Database search with real-time results
- Document relevance scoring with user review
- Citation extraction from high-scoring documents
- Medical publication-style report generation
- Counterfactual analysis for finding contradictory evidence
- Enhanced markdown report export with counterfactual analysis

Enhanced Workflow (8 Steps):
1. Research Question: Enter your medical research question
2. Query Generation: AI generates PostgreSQL to_tsquery with human editing
3. Document Search: Execute database search and review results
4. Relevance Scoring: AI scores documents (1-5) for relevance
5. Citation Extraction: Extract relevant passages from high-scoring documents
6. Report Generation: Create medical publication-style report
7. Counterfactual Analysis: (Optional) Analyze report for contradictory evidence
   - Identifies main claims in the generated report
   - Generates research questions to find contradictory evidence
   - Optionally searches database for opposing studies
   - Provides confidence level recommendations
8. Export: Save report as markdown file with optional counterfactual analysis

Modular Architecture:
- bmlibrarian.cli.config: Configuration management, command-line parsing
- bmlibrarian.cli.ui: User interface, display functions, user interaction
- bmlibrarian.cli.query_processing: Query editing, database search coordination
- bmlibrarian.cli.formatting: Report formatting, markdown generation, file export
- bmlibrarian.cli.workflow: Multi-agent workflow orchestration, state management

Agent Integration:
- QueryAgent: Natural language to PostgreSQL query conversion
- DocumentScoringAgent: Document relevance scoring for user questions
- CitationFinderAgent: Extracts relevant passages from high-scoring documents
- ReportingAgent: Synthesizes citations into medical publication-style reports
- CounterfactualAgent: Analyzes reports to generate contradictory evidence questions

Usage:
    python bmlibrarian_cli_refactored.py [options]
    
    Options:
    --max-results N      Maximum search results (default: 100)
    --timeout M          Timeout in minutes (default: 5.0)
    --score-threshold S  Document score threshold (default: 2.5)
    --min-relevance R    Minimum citation relevance (default: 0.7)
    --quick             Quick testing mode (reduced limits)

Requirements:
- PostgreSQL database with biomedical literature and pgvector extension
- Ollama service running locally (http://localhost:11434)
- Required models: gpt-oss:20b, medgemma4B_it_q8:latest
- BMLibrarian agents properly configured
"""

import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.cli import (
    CLIConfig, UserInterface, QueryProcessor, 
    ReportFormatter, WorkflowOrchestrator
)
from bmlibrarian.cli.config import (
    parse_command_line_args, create_config_from_args, 
    show_config_summary, ConfigurationManager
)


class MedicalResearchCLI:
    """Main CLI application class using modular architecture."""
    
    def __init__(self, config: CLIConfig):
        """Initialize CLI with configuration."""
        self.config = config
        
        # Initialize modules
        self.ui = UserInterface(config)
        self.query_processor = QueryProcessor(config, self.ui)
        self.formatter = ReportFormatter(config, self.ui)
        self.workflow = WorkflowOrchestrator(config, self.ui, self.query_processor, self.formatter)
        self.config_manager = ConfigurationManager(config)
        
        # Show header
        self.ui.show_header()
        
        # Show configuration if non-default
        if self._has_non_default_config():
            show_config_summary(config)
    
    def _has_non_default_config(self) -> bool:
        """Check if configuration has non-default values."""
        default_config = CLIConfig()
        
        return (
            self.config.max_search_results != default_config.max_search_results or
            self.config.timeout_minutes != default_config.timeout_minutes or
            self.config.default_score_threshold != default_config.default_score_threshold or
            self.config.default_min_relevance != default_config.default_min_relevance or
            self.config.max_documents_display != default_config.max_documents_display or
            self.config.max_workers != default_config.max_workers or
            self.config.verbose
        )
    
    def run(self) -> None:
        """Run the main CLI application."""
        try:
            self.show_main_menu()
        except KeyboardInterrupt:
            self.ui.show_info_message("Exiting BMLibrarian CLI...")
        except Exception as e:
            self.ui.show_error_message(f"Fatal error: {e}")
            if self.config.verbose:
                import traceback
                traceback.print_exc()
    
    def show_main_menu(self) -> None:
        """Display main menu and handle user choices."""
        while True:
            choice = self.ui.show_main_menu()
            
            if choice == '1':
                # Start new research workflow
                success = self.workflow.run_complete_workflow()
                if success:
                    self.ui.show_success_message("Research workflow completed successfully!")
            
            elif choice == '2':
                # Resume previous session (placeholder)
                self.ui.show_error_message("Session resume not implemented yet.")
                self._show_resume_placeholder()
            
            elif choice == '3':
                # Test system connections
                self.workflow.setup_agents()
            
            elif choice == '4':
                # Configuration settings
                self.config_manager.show_configuration_menu()
            
            elif choice == '5':
                # View documentation
                self.ui.show_documentation()
            
            elif choice == '6':
                # Exit
                print("👋 Goodbye!")
                break
            
            else:
                self.ui.show_error_message("Invalid option. Please choose 1-6.")
    
    def _show_resume_placeholder(self) -> None:
        """Show placeholder information for session resume feature."""
        print("\n📋 Session Resume Feature (Future Implementation)")
        print("=" * 50)
        print("This feature will allow you to:")
        print("• Save workflow state at any step")
        print("• Resume interrupted research sessions")
        print("• Reload previous configurations")
        print("• Continue from citation extraction or report generation")
        print()
        
        # Show current state if any
        state = self.workflow.get_workflow_state()
        if state['current_question']:
            print("Current session state:")
            print(f"• Question: {state['current_question']}")
            print(f"• Search results: {state['search_results_count']} documents")
            print(f"• Scored documents: {state['scored_documents_count']}")
            print(f"• Extracted citations: {state['extracted_citations_count']}")
            print(f"• Final report: {'✅' if state['has_final_report'] else '❌'}")
        else:
            print("No active session to resume.")
        
        input("\nPress Enter to continue...")


def main():
    """Main entry point for the CLI application."""
    try:
        # Parse command line arguments
        args = parse_command_line_args()
        
        # Create configuration from arguments
        config = create_config_from_args(args)
        
        # Create and run CLI
        cli = MedicalResearchCLI(config)
        cli.run()
        
    except KeyboardInterrupt:
        print(f"\n\n👋 Exiting BMLibrarian CLI...")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()