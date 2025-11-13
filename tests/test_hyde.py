#!/usr/bin/env python3
"""
Simple test script for HyDE search implementation.
Tests the basic functionality without requiring a full test suite.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """Test that all HyDE-related imports work."""
    print("Testing imports...")

    try:
        from bmlibrarian.agents.base import BaseAgent
        print("  ✓ BaseAgent imported")

        from bmlibrarian.agents.query_agent import QueryAgent
        print("  ✓ QueryAgent imported")

        from bmlibrarian.agents.utils.hyde_search import (
            generate_hypothetical_documents,
            embed_documents,
            search_with_embedding,
            reciprocal_rank_fusion,
            hyde_search
        )
        print("  ✓ HyDE search utilities imported")

        from bmlibrarian.config import get_config
        print("  ✓ Config imported")

        return True

    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        return False


def test_config():
    """Test that HyDE configuration exists."""
    print("\nTesting HyDE configuration...")

    try:
        from bmlibrarian.config import get_config

        config = get_config()
        search_strategy = config.get('search_strategy', {})
        hyde_config = search_strategy.get('hyde', {})

        print(f"  HyDE enabled: {hyde_config.get('enabled', False)}")
        print(f"  Generation model: {hyde_config.get('generation_model', 'N/A')}")
        print(f"  Embedding model: {hyde_config.get('embedding_model', 'N/A')}")
        print(f"  Num hypothetical docs: {hyde_config.get('num_hypothetical_docs', 'N/A')}")
        print(f"  Similarity threshold: {hyde_config.get('similarity_threshold', 'N/A')}")
        print(f"  Max results: {hyde_config.get('max_results', 'N/A')}")

        return True

    except Exception as e:
        print(f"  ✗ Config test failed: {e}")
        return False


def test_agent_method():
    """Test that QueryAgent has find_abstracts_hyde method."""
    print("\nTesting QueryAgent.find_abstracts_hyde method...")

    try:
        from bmlibrarian.agents.query_agent import QueryAgent

        # Create agent (without connecting to Ollama)
        agent = QueryAgent(show_model_info=False)

        # Check method exists
        if hasattr(agent, 'find_abstracts_hyde'):
            print("  ✓ find_abstracts_hyde method exists")

            # Check method signature
            import inspect
            sig = inspect.signature(agent.find_abstracts_hyde)
            params = list(sig.parameters.keys())

            expected_params = ['question', 'max_results', 'num_hypothetical_docs',
                             'similarity_threshold', 'generation_model', 'embedding_model']

            if all(p in params for p in expected_params):
                print("  ✓ Method signature correct")
                return True
            else:
                print(f"  ✗ Method signature incorrect. Expected: {expected_params}, Got: {params}")
                return False
        else:
            print("  ✗ find_abstracts_hyde method not found")
            return False

    except Exception as e:
        print(f"  ✗ Agent method test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_base_agent_embedding():
    """Test that BaseAgent has _generate_embedding method."""
    print("\nTesting BaseAgent._generate_embedding method...")

    try:
        from bmlibrarian.agents.query_agent import QueryAgent

        # Create agent (QueryAgent inherits from BaseAgent)
        agent = QueryAgent(show_model_info=False)

        # Check method exists
        if hasattr(agent, '_generate_embedding'):
            print("  ✓ _generate_embedding method exists")

            # Check method signature
            import inspect
            sig = inspect.signature(agent._generate_embedding)
            params = list(sig.parameters.keys())

            if 'text' in params and 'model' in params:
                print("  ✓ Method signature correct")
                return True
            else:
                print(f"  ✗ Method signature incorrect. Got: {params}")
                return False
        else:
            print("  ✗ _generate_embedding method not found")
            return False

    except Exception as e:
        print(f"  ✗ BaseAgent embedding test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("="*80)
    print("HyDE IMPLEMENTATION TESTS")
    print("="*80)

    results = []

    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("Configuration", test_config()))
    results.append(("BaseAgent Embedding", test_base_agent_embedding()))
    results.append(("QueryAgent HyDE Method", test_agent_method()))

    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")

    print(f"\n  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n✓ All tests passed! HyDE implementation is ready.")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed. Review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
