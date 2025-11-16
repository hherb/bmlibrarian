#!/usr/bin/env python3
"""Headless test for Phase 1 implementation.

This script tests the core components without importing GUI dependencies.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_imports():
    """Test that all modules can be imported (except GUI-dependent ones)."""
    print("\n=== Testing Module Imports ===")

    try:
        # Test non-GUI imports
        from bmlibrarian.gui.qt.core.tab_registry import TabRegistry, DependencyError
        print("✓ TabRegistry imported")

        from bmlibrarian.gui.qt.core.config_manager import GUIConfigManager
        print("✓ GUIConfigManager imported")

        # EventBus uses QObject from PySide6, so it will fail in headless mode
        # from bmlibrarian.gui.qt.core.event_bus import EventBus
        # print("✓ EventBus imported")

        from bmlibrarian.gui.qt.plugins.base_tab import TabPluginMetadata
        print("✓ TabPluginMetadata imported")

        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tab_registry():
    """Test tab registry without plugins."""
    print("\n=== Testing Tab Registry ===")

    try:
        from bmlibrarian.gui.qt.core.tab_registry import TabRegistry

        registry = TabRegistry()
        print("✓ TabRegistry instantiated")

        # Test empty registry
        plugins = registry.list_plugins()
        if len(plugins) == 0:
            print("✓ Empty registry works")
        else:
            print(f"✗ Expected empty registry, got {plugins}")
            return False

        # Test statistics
        stats = registry.get_registry_stats()
        print(f"✓ Registry stats: {stats}")

        return True
    except Exception as e:
        print(f"✗ TabRegistry test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_manager():
    """Test configuration manager."""
    print("\n=== Testing Configuration Manager ===")

    try:
        from bmlibrarian.gui.qt.core.config_manager import GUIConfigManager

        # Create config in temp location to avoid modifying user config
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.json"

            config_manager = GUIConfigManager(config_path)
            print("✓ Configuration manager initialized")

            # Get config
            config = config_manager.get_config()
            print(f"✓ Configuration loaded: {len(config)} top-level keys")

            # Test default values
            theme = config_manager.get_theme()
            print(f"✓ Default theme: {theme}")

            # Test window config
            window_config = config_manager.get_window_config()
            print(f"✓ Window config: {window_config.get('width')}x{window_config.get('height')}")

            # Test enabled plugins
            enabled = config_manager.get_enabled_plugins()
            print(f"✓ Enabled plugins: {enabled}")

            # Test tab order
            tab_order = config_manager.get_tab_order()
            print(f"✓ Tab order: {tab_order}")

            # Test save/load
            config_manager.set_theme("dark")
            config_manager.save_config()

            # Reload
            config_manager2 = GUIConfigManager(config_path)
            if config_manager2.get_theme() == "dark":
                print("✓ Save/load works")
            else:
                print("✗ Save/load failed")
                return False

        return True
    except Exception as e:
        print(f"✗ Config manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_plugin_structure():
    """Test that plugin structure is correct."""
    print("\n=== Testing Plugin Structure ===")

    try:
        # Check example plugin file exists
        example_plugin = Path("src/bmlibrarian/gui/qt/plugins/example/plugin.py")
        if not example_plugin.exists():
            print(f"✗ Example plugin not found: {example_plugin}")
            return False

        print(f"✓ Example plugin exists: {example_plugin}")

        # Check it has the required function
        with open(example_plugin) as f:
            content = f.read()
            if "def create_plugin()" in content:
                print("✓ create_plugin() function found")
            else:
                print("✗ create_plugin() function not found")
                return False

            if "class ExamplePlugin" in content:
                print("✓ ExamplePlugin class found")
            else:
                print("✗ ExamplePlugin class not found")
                return False

        return True
    except Exception as e:
        print(f"✗ Plugin structure test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_file_structure():
    """Test that all required files exist."""
    print("\n=== Testing File Structure ===")

    required_files = [
        "src/bmlibrarian/gui/qt/__init__.py",
        "src/bmlibrarian/gui/qt/core/__init__.py",
        "src/bmlibrarian/gui/qt/core/application.py",
        "src/bmlibrarian/gui/qt/core/main_window.py",
        "src/bmlibrarian/gui/qt/core/plugin_manager.py",
        "src/bmlibrarian/gui/qt/core/tab_registry.py",
        "src/bmlibrarian/gui/qt/core/config_manager.py",
        "src/bmlibrarian/gui/qt/core/event_bus.py",
        "src/bmlibrarian/gui/qt/plugins/__init__.py",
        "src/bmlibrarian/gui/qt/plugins/base_tab.py",
        "src/bmlibrarian/gui/qt/plugins/example/plugin.py",
        "src/bmlibrarian/gui/qt/resources/styles/default.qss",
        "src/bmlibrarian/gui/qt/resources/styles/dark.qss",
        "bmlibrarian_qt.py",
    ]

    all_exist = True
    for file_path in required_files:
        path = Path(file_path)
        if path.exists():
            print(f"✓ {file_path}")
        else:
            print(f"✗ Missing: {file_path}")
            all_exist = False

    return all_exist


def test_syntax():
    """Test that all Python files have valid syntax."""
    print("\n=== Testing Python Syntax ===")

    python_files = [
        "src/bmlibrarian/gui/qt/core/application.py",
        "src/bmlibrarian/gui/qt/core/main_window.py",
        "src/bmlibrarian/gui/qt/core/plugin_manager.py",
        "src/bmlibrarian/gui/qt/core/tab_registry.py",
        "src/bmlibrarian/gui/qt/core/config_manager.py",
        "src/bmlibrarian/gui/qt/core/event_bus.py",
        "src/bmlibrarian/gui/qt/plugins/base_tab.py",
        "src/bmlibrarian/gui/qt/plugins/example/plugin.py",
    ]

    all_valid = True
    for file_path in python_files:
        try:
            with open(file_path) as f:
                compile(f.read(), file_path, 'exec')
            print(f"✓ {file_path}")
        except SyntaxError as e:
            print(f"✗ Syntax error in {file_path}: {e}")
            all_valid = False

    return all_valid


def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 1 Implementation Test Suite (Headless)")
    print("=" * 60)

    tests = [
        ("File Structure", test_file_structure),
        ("Python Syntax", test_syntax),
        ("Module Imports", test_imports),
        ("Tab Registry", test_tab_registry),
        ("Configuration Manager", test_config_manager),
        ("Plugin Structure", test_plugin_structure),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ Test '{name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = 0
    failed = 0

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\nTotal: {passed} passed, {failed} failed out of {len(results)} tests")

    if failed == 0:
        print("\n🎉 All tests passed! Phase 1 implementation is structurally correct.")
        print("\nNote: Full GUI testing requires a display environment.")
        print("To test the GUI: uv run python bmlibrarian_qt.py")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed. Review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
