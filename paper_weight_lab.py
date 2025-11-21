#!/usr/bin/env python3
"""
Paper Weight Assessment Laboratory - Entry Point

Battle testing interface for paper weight assessment with full
visual inspection of all assessment steps and audit trails.

This is a thin entry point that imports from the modular package
at bmlibrarian.lab.paper_weight_lab.

Usage:
    uv run python paper_weight_lab.py
"""

from bmlibrarian.lab.paper_weight_lab import main

if __name__ == '__main__':
    main()
