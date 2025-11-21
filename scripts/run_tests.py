#!/usr/bin/env python3
"""Test runner script for bmlibrarian."""

import subprocess
import sys
from pathlib import Path


def run_tests():
    """Run the test suite with coverage reporting."""
    project_root = Path(__file__).parent
    
    # Change to project directory
    import os
    os.chdir(project_root)
    
    print("Running bmlibrarian test suite...")
    print("-" * 50)
    
    # Run pytest with coverage
    cmd = [
        "uv", "run", "pytest", 
        "tests/",
        "--cov=src/bmlibrarian",
        "--cov-report=term-missing",
        "--cov-report=html",
        "--verbose"
    ]
    
    try:
        result = subprocess.run(cmd, check=True)
        print("\n" + "=" * 50)
        print("✅ All tests passed successfully!")
        print("📊 Coverage report generated in htmlcov/")
        return 0
    except subprocess.CalledProcessError as e:
        print("\n" + "=" * 50)
        print("❌ Tests failed!")
        return e.returncode


if __name__ == "__main__":
    sys.exit(run_tests())