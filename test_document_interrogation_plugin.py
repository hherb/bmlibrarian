#!/usr/bin/env python3
"""
Test script for Document Interrogation plugin.

Verifies that the plugin can be loaded and initialized correctly.
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def test_plugin_discovery():
    """Test that the plugin can be discovered."""
    from bmlibrarian.gui.qt.core.plugin_manager import PluginManager
    from bmlibrarian.gui.qt.core.tab_registry import TabRegistry

    registry = TabRegistry()
    manager = PluginManager(registry)

    discovered = manager.discover_plugins()
    print(f"✓ Discovered {len(discovered)} plugins: {discovered}")

    assert "document_interrogation" in discovered, "document_interrogation plugin not discovered!"
    print("✓ document_interrogation plugin discovered")

    return manager, registry


def test_plugin_load(manager):
    """Test that the plugin can be loaded."""
    try:
        plugin = manager.load_plugin("document_interrogation")
        print("✓ document_interrogation plugin loaded successfully")

        # Check metadata
        metadata = plugin.get_metadata()
        print(f"  - Plugin ID: {metadata.plugin_id}")
        print(f"  - Display Name: {metadata.display_name}")
        print(f"  - Description: {metadata.description}")
        print(f"  - Version: {metadata.version}")
        print(f"  - Requires: {metadata.requires}")

        assert metadata.plugin_id == "document_interrogation"
        print("✓ Plugin metadata is correct")

        return plugin

    except Exception as e:
        print(f"✗ Failed to load plugin: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def test_widget_creation(plugin):
    """Test that the plugin can create its widget."""
    try:
        # Import PySide6 to create a QApplication
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        widget = plugin.create_widget()
        print("✓ Plugin widget created successfully")
        print(f"  - Widget type: {type(widget).__name__}")

        # Check that widget has expected components
        assert hasattr(widget, 'load_doc_btn'), "Missing load_doc_btn"
        assert hasattr(widget, 'model_combo'), "Missing model_combo"
        assert hasattr(widget, 'chat_scroll_area'), "Missing chat_scroll_area"
        assert hasattr(widget, 'message_input'), "Missing message_input"
        print("✓ Widget has expected components")

        return widget

    except Exception as e:
        print(f"✗ Failed to create widget: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Run all tests."""
    print("=" * 60)
    print("Document Interrogation Plugin Test Suite")
    print("=" * 60)
    print()

    print("1. Testing plugin discovery...")
    manager, registry = test_plugin_discovery()
    print()

    print("2. Testing plugin load...")
    plugin = test_plugin_load(manager)
    print()

    print("3. Testing widget creation...")
    widget = test_widget_creation(plugin)
    print()

    print("=" * 60)
    print("✓ All tests passed!")
    print("=" * 60)
    print()
    print("The Document Interrogation plugin is ready to use.")
    print("Launch the Qt GUI with: uv run python bmlibrarian_qt.py")


if __name__ == "__main__":
    main()
