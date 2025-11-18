#!/usr/bin/env python3
"""
PICO Lab - Interactive GUI for PICO Component Extraction

This application provides an interactive interface for extracting PICO
(Population, Intervention, Comparison, Outcome) components from biomedical
research papers stored in the BMLibrarian database.

Usage:
    uv run python pico_lab.py
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from bmlibrarian.lab.pico_lab import run_pico_lab

if __name__ == '__main__':
    run_pico_lab()
