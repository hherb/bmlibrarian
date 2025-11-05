#!/usr/bin/env python3
"""
BMLibrarian Research GUI - Interactive Medical Literature Research Desktop App

A comprehensive Flet-based desktop application for conducting evidence-based medical
literature research using the full BMLibrarian multi-agent workflow.

Features:
- Multi-line text input for medical research questions
- Human-in-the-loop toggle for automated vs interactive workflows
- Real-time progress tracking with foldable step cards
- Markdown-enabled report display with save functionality
- Integration with BMLibrarian's complete multi-agent architecture

Workflow Integration:
- QueryAgent: Natural language to PostgreSQL query conversion
- DocumentScoringAgent: Document relevance scoring
- CitationFinderAgent: Extract relevant passages from documents
- ReportingAgent: Generate medical publication-style reports
- CounterfactualAgent: Analyze for contradictory evidence
- EditorAgent: Create balanced comprehensive reports

Usage:
    python bmlibrarian_research_gui.py [--web] [--port 8080] [--debug]
"""

import sys
from pathlib import Path
import flet as ft

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.gui.research_app import ResearchGUI
from bmlibrarian.gui.workflow import initialize_agents_in_main_thread, cleanup_agents
import atexit


def main():
    """Main entry point for the research GUI."""
    import argparse
    
    parser = argparse.ArgumentParser(description='BMLibrarian Research GUI')
    parser.add_argument('--web', action='store_true', help='Run as web application')
    parser.add_argument('--port', type=int, default=8080, help='Port for web mode')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--max-results', type=int, help='Maximum search results')
    parser.add_argument('--timeout', type=float, help='Timeout in minutes')
    parser.add_argument('--score-threshold', type=float, help='Document score threshold')
    parser.add_argument('--min-relevance', type=float, help='Minimum citation relevance')
    parser.add_argument('--quick', action='store_true', help='Quick testing mode')
    parser.add_argument('--auto', type=str, help='Automatic mode with research question')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('question', nargs='*', help='Research question (alternative to --auto)')
    
    args = parser.parse_args()
    
    # Handle auto mode or question arguments
    auto_question = None
    if args.auto:
        auto_question = args.auto
    elif args.question:
        auto_question = ' '.join(args.question)
    
    # Initialize agents in main thread before starting GUI
    agents = initialize_agents_in_main_thread()

    # Register cleanup function to return audit connection on exit
    atexit.register(cleanup_agents, agents)

    # Create GUI app with pre-initialized agents
    app = ResearchGUI(agents=agents)
    
    # Set configuration options
    app.config_overrides = getattr(app, 'config_overrides', {})
    
    # Basic configuration
    if args.max_results:
        app.config_overrides['max_results'] = args.max_results
    
    # Only apply limits in quick mode - otherwise process ALL documents
    if args.quick:
        app.config_overrides['max_documents_to_score'] = 20  # Quick mode: limit docs
        app.config_overrides['max_documents_for_citations'] = 15
        app.config_overrides['quick_mode'] = True
    # In normal mode, process ALL documents (no artificial limits)
        
    if args.timeout:
        app.config_overrides['timeout'] = args.timeout
    if args.score_threshold:
        app.config_overrides['score_threshold'] = args.score_threshold
    if args.verbose:
        app.config_overrides['verbose'] = True
    
    # Set auto question if provided
    if auto_question:
        app.auto_question = auto_question
        app.human_in_loop = False  # Auto mode implies non-interactive
    
    if args.web:
        ft.app(target=app.main, view=ft.WEB_BROWSER, port=args.port)
    else:
        ft.app(target=app.main, view=ft.FLET_APP)


if __name__ == '__main__':
    main()