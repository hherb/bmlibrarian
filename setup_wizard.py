#!/usr/bin/env python3
"""
BMLibrarian Setup Wizard

A graphical wizard for initial setup and configuration of BMLibrarian.

This wizard guides you through:
1. PostgreSQL database configuration
2. Database schema initialization
3. Optional data import from PubMed and medRxiv

Usage:
    uv run python setup_wizard.py
    uv run python setup_wizard.py --help

Requirements:
    - PySide6
    - PostgreSQL server running
    - pgvector and plpython3u extensions available
"""

import sys
import argparse
import logging
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging for the setup wizard.

    Args:
        verbose: If True, enable debug logging
    """
    level = logging.DEBUG if verbose else logging.INFO

    # Create log directory
    log_dir = Path.home() / ".bmlibrarian"
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "setup_wizard.log"),
        ],
    )

    # Suppress noisy loggers
    logging.getLogger("PySide6").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> int:
    """
    Main entry point for the setup wizard.

    Returns:
        int: Exit code (0 for success)
    """
    parser = argparse.ArgumentParser(
        description="BMLibrarian Setup Wizard - Configure your biomedical literature database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (debug) logging",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="BMLibrarian Setup Wizard 1.0.0",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("Starting BMLibrarian Setup Wizard")

    try:
        # Import Qt components
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt

        # Create application
        app = QApplication(sys.argv)
        app.setApplicationName("BMLibrarian Setup Wizard")
        app.setOrganizationName("BMLibrarian")
        app.setApplicationVersion("1.0.0")

        # Import and create wizard
        from bmlibrarian.gui.qt.setup_wizard import SetupWizard

        wizard = SetupWizard()
        wizard.show()

        # Run event loop
        result = app.exec()

        if wizard.result() == wizard.DialogCode.Accepted:
            logger.info("Setup wizard completed successfully")
            print("\nSetup completed successfully!")
            print("You can now run BMLibrarian using:")
            print("  uv run python bmlibrarian_cli.py")
            print("  uv run python bmlibrarian_research_gui.py")
        else:
            logger.info("Setup wizard was cancelled")
            print("\nSetup was cancelled.")

        return result

    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        print(f"\nError: Failed to import required modules: {e}")
        print("\nPlease ensure PySide6 is installed:")
        print("  uv add pyside6")
        return 1

    except Exception as e:
        logger.error(f"Setup wizard failed: {e}", exc_info=True)
        print(f"\nError: Setup wizard failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
