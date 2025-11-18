#!/usr/bin/env python3
"""Simple test script for Plugins Manager plugin (no Qt GUI)."""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))


def test_plugin_structure():
    """Test that the plugins_manager plugin structure is correct."""
    print("Testing Plugins Manager plugin structure...")

    # Check files exist
    plugin_dir = Path("src/bmlibrarian/gui/qt/plugins/plugins_manager")
    if not plugin_dir.exists():
        print(f"✗ ERROR: Plugin directory not found: {plugin_dir}")
        return False
    print(f"✓ Plugin directory exists: {plugin_dir}")

    # Check required files
    required_files = ["__init__.py", "plugin.py", "plugins_manager_tab.py"]
    for filename in required_files:
        filepath = plugin_dir / filename
        if not filepath.exists():
            print(f"✗ ERROR: Required file not found: {filepath}")
            return False
        print(f"✓ File exists: {filename}")

    # Try to import the plugin module
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "plugins_manager_plugin",
            plugin_dir / "plugin.py"
        )
        if spec is None or spec.loader is None:
            print("✗ ERROR: Failed to create module spec")
            return False

        module = importlib.util.module_from_spec(spec)
        # Don't execute the module (to avoid Qt imports)
        print("✓ Plugin module can be loaded")

        # Check that create_plugin function would exist
        with open(plugin_dir / "plugin.py", 'r') as f:
            content = f.read()
            if "def create_plugin()" not in content:
                print("✗ ERROR: create_plugin() function not found")
                return False
            if "class PluginsManagerPlugin" not in content:
                print("✗ ERROR: PluginsManagerPlugin class not found")
                return False
            print("✓ Required functions and classes found")

        # Check metadata values in the source
        if '"plugins_manager"' not in content:
            print("✗ ERROR: Plugin ID not found")
            return False
        if '"Plugins"' not in content:
            print("✗ ERROR: Display name not found")
            return False
        print("✓ Metadata values present")

        return True

    except Exception as e:
        print(f"✗ ERROR: Exception during import: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_plugin_structure()
    if success:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Tests failed!")
        sys.exit(1)
