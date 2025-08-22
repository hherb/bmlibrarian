#!/usr/bin/env python3
"""
BMLibrarian Configuration GUI

A graphical user interface for configuring BMLibrarian agents and settings.
Built with Flet for cross-platform compatibility.

Usage:
    python bmlibrarian_config_gui.py

Features:
- Tabbed interface with separate configuration for each agent
- Model selection with live refresh from Ollama
- Parameter adjustment with sliders and input fields
- Configuration save/load functionality
- Connection testing
- Reset to defaults
"""

import argparse
import sys
from pathlib import Path

# Add the src directory to the path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

try:
    import flet as ft
except ImportError:
    print("❌ Flet library not found. Please install it with:")
    print("   uv add flet")
    sys.exit(1)

try:
    from bmlibrarian.gui.config_app import BMLibrarianConfigApp
except ImportError as e:
    print(f"❌ Failed to import BMLibrarian GUI components: {e}")
    print("Make sure you're running from the project root directory.")
    sys.exit(1)


def main():
    """Main entry point for the configuration GUI."""
    parser = argparse.ArgumentParser(
        description="BMLibrarian Configuration GUI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bmlibrarian_config_gui.py                # Launch desktop GUI
  python bmlibrarian_config_gui.py --view web     # Launch in web browser
  python bmlibrarian_config_gui.py --view web --port 8080  # Web with custom port
        """
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=0,
        help='Port for web interface (0 = auto-assign, only used with --view web)'
    )
    
    parser.add_argument(
        '--view',
        choices=['web', 'desktop'],
        default='desktop',
        help='View mode: web browser or desktop app (default: desktop)'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    
    args = parser.parse_args()
    
    print("🚀 Starting BMLibrarian Configuration GUI...")
    print(f"   View mode: {args.view}")
    if args.port:
        print(f"   Port: {args.port}")
    
    try:
        app = BMLibrarianConfigApp()
        
        # Configure Flet view
        if args.view == 'desktop':
            view = ft.FLET_APP  # Native desktop application
        else:
            view = ft.WEB_BROWSER
        
        # Run the application
        if args.view == 'desktop':
            ft.app(
                target=app.main,
                view=view
            )
        else:
            ft.app(
                target=app.main,
                view=view,
                port=args.port if args.port else 0,
                web_renderer=ft.WebRenderer.HTML
            )
        
    except KeyboardInterrupt:
        print("\n👋 Configuration GUI stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Failed to start GUI: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()