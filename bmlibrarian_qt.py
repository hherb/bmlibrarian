#!/usr/bin/env python3
"""Entry point for BMLibrarian Qt GUI application.

This script launches the PySide6-based graphical user interface for BMLibrarian.
It provides a modern, plugin-based tabbed interface for biomedical literature research.

Usage:
    python bmlibrarian_qt.py
    python bmlibrarian_qt.py --user herb --env .debug_env
    # Or make executable and run directly:
    chmod +x bmlibrarian_qt.py
    ./bmlibrarian_qt.py

The application will:
1. Load environment from --env file if specified (BEFORE any other initialization)
2. Load configuration from ~/.bmlibrarian/gui_config.json
3. Discover and load enabled plugins
4. Create tabs for each plugin
5. Show the main window

Command-line options:
    --env FILE    Load environment variables from specified file instead of .env
    --user NAME   Auto-login as specified user (testing mode)
"""

import os
import sys
from pathlib import Path


def _load_env_file_early(env_path: Path) -> bool:
    """Load environment variables from specified file before any other initialization.

    This function is called BEFORE importing bmlibrarian modules to ensure
    environment variables are set before any module initialization occurs.

    Args:
        env_path: Path to environment file to load.

    Returns:
        True if file was loaded successfully, False otherwise.
    """
    if not env_path.exists():
        print(f"Error: Environment file not found: {env_path}", file=sys.stderr)
        return False

    try:
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and value:
                        os.environ[key] = value
        print(f"Loaded environment from: {env_path}")
        return True
    except Exception as e:
        print(f"Error loading environment file {env_path}: {e}", file=sys.stderr)
        return False


def _parse_env_arg_early() -> tuple[Path | None, list[str]]:
    """Parse --env argument before any other processing.

    This extracts the --env argument from sys.argv early, before
    argparse or any other module has a chance to process arguments.
    The --env file must be loaded before importing bmlibrarian modules.

    Returns:
        Tuple of (env_path or None, remaining argv without --env args).
    """
    argv = sys.argv[:]
    env_path = None
    filtered_argv = [argv[0]]  # Keep program name

    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == '--env':
            if i + 1 < len(argv):
                env_path = Path(argv[i + 1])
                i += 2  # Skip both --env and its value
                continue
            else:
                print("Error: --env requires a file path argument", file=sys.stderr)
                sys.exit(1)
        elif arg.startswith('--env='):
            env_path = Path(arg.split('=', 1)[1])
            i += 1
            continue
        else:
            filtered_argv.append(arg)
            i += 1

    return env_path, filtered_argv


# Parse and load --env BEFORE importing any bmlibrarian modules
# This ensures environment variables are set before any module initialization
_env_path, _filtered_argv = _parse_env_arg_early()

if _env_path is not None:
    # Load the specified env file
    if not _load_env_file_early(_env_path):
        sys.exit(1)
    # Store the env path for later reference by the application
    os.environ['BMLIBRARIAN_ENV_FILE'] = str(_env_path.resolve())
    # Update sys.argv to remove --env args so downstream parsers don't see them
    sys.argv = _filtered_argv

# Now safe to add src to path and import bmlibrarian modules
src_path = Path(__file__).parent / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

from bmlibrarian.gui.qt import main

if __name__ == "__main__":
    sys.exit(main())
