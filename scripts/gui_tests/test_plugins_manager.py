#!/usr/bin/env python3
"""Test script for Plugins Manager plugin."""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
if src_path.exists():
    sys.path.insert(0, str(src_path))

from bmlibrarian.gui.qt.core.tab_registry import TabRegistry
from bmlibrarian.gui.qt.core.plugin_manager import PluginManager


def test_plugins_manager():
    """Test that the plugins_manager plugin can be discovered and loaded."""
    print("Testing Plugins Manager plugin...")

    # Create registry and manager
    registry = TabRegistry()
    plugin_manager = PluginManager(registry)

    # Discover plugins
    discovered = plugin_manager.discover_plugins()
    print(f"✓ Discovered {len(discovered)} plugins: {discovered}")

    # Check if plugins_manager is discovered
    if "plugins_manager" not in discovered:
        print("✗ ERROR: plugins_manager not discovered!")
        return False
    print("✓ plugins_manager plugin discovered")

    # Try to load the plugin
    try:
        plugin = plugin_manager.load_plugin("plugins_manager")
        if not plugin:
            print("✗ ERROR: Failed to load plugins_manager plugin")
            return False
        print("✓ plugins_manager plugin loaded successfully")

        # Check metadata
        metadata = plugin.get_metadata()
        print(f"  - Plugin ID: {metadata.plugin_id}")
        print(f"  - Display Name: {metadata.display_name}")
        print(f"  - Description: {metadata.description}")
        print(f"  - Version: {metadata.version}")
        print(f"  - Dependencies: {metadata.requires}")

        # Verify metadata
        assert metadata.plugin_id == "plugins_manager", "Plugin ID mismatch"
        assert metadata.display_name == "Plugins", "Display name mismatch"
        print("✓ Metadata validation passed")

        # Test cleanup
        plugin.cleanup()
        print("✓ Plugin cleanup successful")

        return True

    except Exception as e:
        print(f"✗ ERROR: Exception during plugin load: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_plugins_manager()
    if success:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Tests failed!")
        sys.exit(1)
