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

Enhanced Workflow (9 Steps):
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
8. Comprehensive Editing: EditorAgent creates balanced, structured report
   - Integrates original findings with contradictory evidence
   - Creates comprehensive markdown with tables and proper references
   - Provides evidence quality assessment and confidence grading
9. Export: Save comprehensive report as structured markdown file

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
- EditorAgent: Creates balanced, comprehensive reports combining original findings with contradictory evidence

Usage:
    python bmlibrarian_cli_refactored.py [options] [question]
    
    Options:
    --max-results N      Maximum search results (default: 100)
    --timeout M          Timeout in minutes (default: 5.0)
    --score-threshold S  Document score threshold (default: 2.5)
    --min-relevance R    Minimum citation relevance (default: 0.7)
    --quick             Quick testing mode (reduced limits)
    --auto              Automatic mode: run full workflow without interaction
    --verbose           Enable verbose output for debugging
    
    Auto Mode:
    python bmlibrarian_cli_refactored.py --auto "What are the benefits of exercise?"
    
    Runs the complete 9-step workflow including counterfactual analysis and comprehensive
    editing automatically without any user interaction. Saves the final comprehensive
    report as a structured markdown file.

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
from bmlibrarian.cli.logging_config import setup_logging


class MedicalResearchCLI:
    """Main CLI application class using modular architecture."""
    
    def __init__(self, config: CLIConfig, workflow_logger=None):
        """Initialize CLI with configuration."""
        self.config = config
        self.workflow_logger = workflow_logger
        
        # Log configuration
        if workflow_logger:
            workflow_logger.log_configuration(config.__dict__)
        
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
    
    def run(self, auto_question: str = None) -> None:
        """Run the main CLI application."""
        try:
            if self.config.auto_mode:
                # Run automatic workflow
                if not auto_question:
                    if self.workflow_logger:
                        self.workflow_logger.log_error("auto_mode_error", "Auto mode requires a research question")
                    self.ui.show_error_message("--auto mode requires a research question.")
                    sys.exit(1)
                
                if self.workflow_logger:
                    self.workflow_logger.log_user_interaction("auto_mode_start", f"Auto question: {auto_question}", auto_mode=True)
                
                self.ui.show_info_message(f"Running auto mode with question: {auto_question}")
                success = self.workflow.run_complete_workflow(auto_question)
                
                if success:
                    if self.workflow_logger:
                        self.workflow_logger.log_session_end(True, {"mode": "auto", "question": auto_question})
                    self.ui.show_success_message("Auto workflow completed successfully!")
                    sys.exit(0)
                else:
                    if self.workflow_logger:
                        self.workflow_logger.log_session_end(False, {"mode": "auto", "question": auto_question})
                    self.ui.show_error_message("Auto workflow failed.")
                    sys.exit(1)
            else:
                if self.workflow_logger:
                    self.workflow_logger.log_user_interaction("interactive_mode_start", "Starting interactive menu", auto_mode=False)
                self.show_main_menu()
                
        except KeyboardInterrupt:
            if self.workflow_logger:
                self.workflow_logger.log_session_end(False, {"interrupted_by": "user"})
            self.ui.show_info_message("Exiting BMLibrarian CLI...")
        except Exception as e:
            if self.workflow_logger:
                self.workflow_logger.log_error("cli_fatal_error", str(e), exception=e)
                self.workflow_logger.log_session_end(False, {"error_type": type(e).__name__, "error_message": str(e)})
            
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
    workflow_logger = None
    
    try:
        # Setup logging with timestamped files
        workflow_logger = setup_logging()
        print(f"📝 Logging to: {workflow_logger.log_file_path}")
        
        # Parse command line arguments
        args = parse_command_line_args()
        
        # Log command line arguments
        workflow_logger.logger.info(f"CLI started with args: {vars(args)}")
        
        # Validate auto mode requirements
        if args.auto and not args.question:
            error_msg = "Auto mode requires a research question as an argument."
            workflow_logger.log_error("argument_validation", error_msg, {
                'auto_mode': True,
                'question_provided': False
            })
            print("❌ Error: --auto mode requires a research question as an argument.")
            print("Usage: python bmlibrarian_cli_refactored.py --auto 'What are the benefits of exercise?'")
            sys.exit(1)
        
        # Create configuration from arguments
        config = create_config_from_args(args)
        
        # Create and run CLI
        cli = MedicalResearchCLI(config, workflow_logger)
        cli.run(auto_question=args.question)
        
    except KeyboardInterrupt:
        if workflow_logger:
            workflow_logger.log_session_end(False, {"interrupted_by": "keyboard_interrupt"})
        print(f"\n\n👋 Exiting BMLibrarian CLI...")
    except Exception as e:
        if workflow_logger:
            workflow_logger.log_error("main_fatal_error", str(e), exception=e)
            workflow_logger.log_session_end(False, {"error_type": type(e).__name__, "error_message": str(e)})
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()