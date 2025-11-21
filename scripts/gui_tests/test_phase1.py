#!/usr/bin/env python3
"""Test Phase 1 implementation of PySide6 migration.

This script tests the core components without launching the GUI:
- Plugin discovery
- Plugin loading
- TabRegistry
- EventBus
- Configuration management
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from bmlibrarian.gui.qt.core import (
    PluginManager,
    TabRegistry,
    GUIConfigManager,
    EventBus
)


def test_plugin_discovery():
    """Test plugin discovery."""
    print("\n=== Testing Plugin Discovery ===")

    registry = TabRegistry()
    manager = PluginManager(registry)

    discovered = manager.discover_plugins()
    print(f"✓ Discovered {len(discovered)} plugins: {discovered}")

    return len(discovered) > 0


def test_plugin_loading():
    """Test plugin loading."""
    print("\n=== Testing Plugin Loading ===")

    registry = TabRegistry()
    manager = PluginManager(registry)

    # Try to load example plugin
    try:
        plugin = manager.load_plugin("example")
        if plugin:
            metadata = plugin.get_metadata()
            print(f"✓ Loaded plugin '{metadata.plugin_id}'")
            print(f"  Display name: {metadata.display_name}")
            print(f"  Version: {metadata.version}")
            print(f"  Description: {metadata.description}")
            return True
        else:
            print("✗ Failed to load example plugin")
            return False
    except Exception as e:
        print(f"✗ Error loading plugin: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tab_registry():
    """Test tab registry functionality."""
    print("\n=== Testing Tab Registry ===")

    registry = TabRegistry()
    manager = PluginManager(registry)

    # Load example plugin
    plugin = manager.load_plugin("example")
    if not plugin:
        print("✗ Cannot test registry without loaded plugin")
        return False

    metadata = plugin.get_metadata()

    # Test registry functions
    plugin_list = registry.list_plugins()
    print(f"✓ Registered plugins: {plugin_list}")

    retrieved = registry.get_plugin("example")
    if retrieved == plugin:
        print("✓ Plugin retrieval works")
    else:
        print("✗ Plugin retrieval failed")
        return False

    metadata_retrieved = registry.get_metadata("example")
    if metadata_retrieved.plugin_id == metadata.plugin_id:
        print("✓ Metadata retrieval works")
    else:
        print("✗ Metadata retrieval failed")
        return False

    # Test dependency validation
    deps_ok = registry.validate_dependencies("example")
    print(f"✓ Dependency validation: {deps_ok}")

    return True


def test_event_bus():
    """Test event bus."""
    print("\n=== Testing Event Bus ===")

    event_bus = EventBus()

    # Register a plugin
    event_bus.register_plugin("test_plugin")
    print("✓ Plugin registered with EventBus")

    # Subscribe to events
    event_bus.subscribe_to_event("test_plugin", "test_event")
    print("✓ Subscribed to event")

    # Check subscribers
    subscribers = event_bus.get_subscribers("test_event")
    if "test_plugin" in subscribers:
        print(f"✓ Subscription confirmed: {subscribers}")
    else:
        print("✗ Subscription failed")
        return False

    # Get statistics
    stats = event_bus.get_statistics()
    print(f"✓ EventBus stats: {stats}")

    # Cleanup
    event_bus.unregister_plugin("test_plugin")
    print("✓ Plugin unregistered")

    return True


def test_config_manager():
    """Test configuration manager."""
    print("\n=== Testing Configuration Manager ===")

    # Create config manager (will create default config if needed)
    config_manager = GUIConfigManager()
    print("✓ Configuration manager initialized")

    # Get config
    config = config_manager.get_config()
    print(f"✓ Configuration loaded: {len(config)} top-level keys")

    # Test plugin config
    plugin_config = config_manager.get_plugin_config("example")
    print(f"✓ Example plugin config: {plugin_config}")

    # Test window config
    window_config = config_manager.get_window_config()
    print(f"✓ Window config: {window_config.get('width')}x{window_config.get('height')}")

    # Test enabled plugins
    enabled = config_manager.get_enabled_plugins()
    print(f"✓ Enabled plugins: {enabled}")

    return True


def test_plugin_cleanup():
    """Test plugin cleanup."""
    print("\n=== Testing Plugin Cleanup ===")

    registry = TabRegistry()
    manager = PluginManager(registry)

    # Load plugin
    plugin = manager.load_plugin("example")
    if not plugin:
        print("✗ Cannot test cleanup without loaded plugin")
        return False

    print("✓ Plugin loaded")

    # Call cleanup
    try:
        plugin.cleanup()
        print("✓ Plugin cleanup successful")
        return True
    except Exception as e:
        print(f"✗ Plugin cleanup failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 1 Implementation Test Suite")
    print("=" * 60)

    tests = [
        ("Plugin Discovery", test_plugin_discovery),
        ("Plugin Loading", test_plugin_loading),
        ("Tab Registry", test_tab_registry),
        ("Event Bus", test_event_bus),
        ("Configuration Manager", test_config_manager),
        ("Plugin Cleanup", test_plugin_cleanup),
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
        print("\n🎉 All tests passed! Phase 1 implementation is working.")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed. Review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
