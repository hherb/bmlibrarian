#!/usr/bin/env python3
"""
BMLibrarian Lite - Lightweight version without PostgreSQL dependency.

A simplified interface for:
- Systematic literature review (search, score, extract, report)
- Document interrogation (Q&A with loaded documents)

Features:
- ChromaDB for vector storage (embedded, no PostgreSQL)
- SQLite for metadata (embedded)
- FastEmbed for local embeddings (CPU-optimized, no PyTorch)
- Anthropic Claude for LLM inference (online)
- NCBI E-utilities for PubMed search (online)

Usage:
    # Launch GUI (default)
    python bmlibrarian_lite.py

    # Show storage statistics
    python bmlibrarian_lite.py stats

    # Validate configuration
    python bmlibrarian_lite.py validate

    # Show version
    python bmlibrarian_lite.py --version

Requirements:
    - Python 3.12+
    - Anthropic API key (set ANTHROPIC_API_KEY or configure in Settings)
    - Internet connection for PubMed search and Claude API

First-time setup:
    1. Run the application
    2. Go to Settings
    3. Enter your Anthropic API key
    4. Optionally enter your email for PubMed (recommended)
"""

import argparse
import json
import os
import sys
import logging
from pathlib import Path

# Suppress tokenizers parallelism warning when forking for Qt threads
# This must be set before importing any HuggingFace/FastEmbed modules
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Add src to path if running from source
src_path = Path(__file__).parent / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

__version__ = "0.1.0"


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging based on verbosity level.

    Args:
        verbose: If True, set DEBUG level; otherwise INFO
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def cmd_gui(args: argparse.Namespace) -> int:
    """
    Launch the GUI application.

    Args:
        args: Parsed command line arguments

    Returns:
        Application exit code
    """
    from bmlibrarian_lite.gui.app import run_lite_app
    return run_lite_app()


def cmd_stats(args: argparse.Namespace) -> int:
    """
    Show storage statistics.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success)
    """
    from bmlibrarian_lite import LiteConfig, LiteStorage

    config = LiteConfig.load()
    storage = LiteStorage(config)
    stats = storage.get_statistics()

    print("=== BMLibrarian Lite Storage Statistics ===")
    print(f"\nData directory: {stats['data_dir']}")
    print(f"\nDocuments:        {stats['documents']:,}")
    print(f"Chunks:           {stats['chunks']:,}")
    print(f"Search sessions:  {stats['search_sessions']:,}")
    print(f"Checkpoints:      {stats['checkpoints']:,}")

    if args.json:
        print(f"\n{json.dumps(stats, indent=2)}")

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """
    Validate configuration.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 if valid, 1 if invalid)
    """
    from bmlibrarian_lite import LiteConfig

    config = LiteConfig.load()
    errors = config.validate()

    if errors:
        print("Configuration validation FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    else:
        print("Configuration is valid.")

        if args.verbose:
            print("\nConfiguration details:")
            print(f"  LLM Provider: {config.llm.provider}")
            print(f"  LLM Model: {config.llm.model}")
            print(f"  Temperature: {config.llm.temperature}")
            print(f"  Embedding Model: {config.embeddings.model}")
            print(f"  Data Directory: {config.storage.data_dir}")
            print(f"  PubMed Email: {config.pubmed.email or '(not set)'}")

        return 0


def cmd_clear(args: argparse.Namespace) -> int:
    """
    Clear all stored data.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success)
    """
    from bmlibrarian_lite import LiteConfig, LiteStorage

    if not args.force:
        confirm = input("This will DELETE ALL stored data. Type 'yes' to confirm: ")
        if confirm.lower() != "yes":
            print("Aborted.")
            return 1

    config = LiteConfig.load()
    storage = LiteStorage(config)
    storage.clear_all(confirm=True)

    print("All data has been cleared.")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """
    Show or export configuration.

    Args:
        args: Parsed command line arguments

    Returns:
        Exit code (0 for success)
    """
    from bmlibrarian_lite import LiteConfig

    config = LiteConfig.load()

    if args.json:
        print(json.dumps(config.to_dict(), indent=2))
    else:
        print("=== BMLibrarian Lite Configuration ===")
        print(f"\nConfig file: {config.storage.data_dir / 'config.json'}")
        print(f"\n[LLM]")
        print(f"  Provider: {config.llm.provider}")
        print(f"  Model: {config.llm.model}")
        print(f"  Temperature: {config.llm.temperature}")
        print(f"  Max tokens: {config.llm.max_tokens}")
        print(f"\n[Embeddings]")
        print(f"  Model: {config.embeddings.model}")
        print(f"  Cache dir: {config.embeddings.cache_dir or '(auto)'}")
        print(f"\n[PubMed]")
        print(f"  Email: {config.pubmed.email or '(not set)'}")
        print(f"  API key: {'*****' if config.pubmed.api_key else '(not set)'}")
        print(f"\n[Search]")
        print(f"  Chunk size: {config.search.chunk_size}")
        print(f"  Chunk overlap: {config.search.chunk_overlap}")
        print(f"  Similarity threshold: {config.search.similarity_threshold}")
        print(f"  Max results: {config.search.max_results}")
        print(f"\n[Storage]")
        print(f"  Data directory: {config.storage.data_dir}")

    return 0


def create_parser() -> argparse.ArgumentParser:
    """
    Create the argument parser.

    Returns:
        Configured ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="bmlibrarian_lite",
        description="BMLibrarian Lite - Lightweight biomedical literature research tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Launch the GUI
    python bmlibrarian_lite.py

    # Show storage statistics
    python bmlibrarian_lite.py stats

    # Validate configuration
    python bmlibrarian_lite.py validate --verbose

    # Show configuration
    python bmlibrarian_lite.py config --json

    # Clear all data (with confirmation)
    python bmlibrarian_lite.py clear
""",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        help="Available commands",
    )

    # GUI command (default)
    gui_parser = subparsers.add_parser(
        "gui",
        help="Launch the graphical user interface (default)",
    )
    gui_parser.set_defaults(func=cmd_gui)

    # Stats command
    stats_parser = subparsers.add_parser(
        "stats",
        help="Show storage statistics",
    )
    stats_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    stats_parser.set_defaults(func=cmd_stats)

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate configuration",
    )
    validate_parser.set_defaults(func=cmd_validate)

    # Clear command
    clear_parser = subparsers.add_parser(
        "clear",
        help="Clear all stored data (requires confirmation)",
    )
    clear_parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )
    clear_parser.set_defaults(func=cmd_clear)

    # Config command
    config_parser = subparsers.add_parser(
        "config",
        help="Show current configuration",
    )
    config_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    config_parser.set_defaults(func=cmd_config)

    return parser


def main() -> int:
    """
    Main entry point for BMLibrarian Lite.

    Returns:
        Application exit code
    """
    parser = create_parser()
    args = parser.parse_args()

    # Set up logging
    setup_logging(getattr(args, "verbose", False))

    # Default to GUI if no command specified
    if args.command is None:
        args.func = cmd_gui

    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130
    except Exception as e:
        logging.error(f"Error: {e}")
        if getattr(args, "verbose", False):
            logging.exception("Full traceback:")
        return 1


if __name__ == "__main__":
    sys.exit(main())
