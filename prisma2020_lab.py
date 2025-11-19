#!/usr/bin/env python3
"""
PRISMA 2020 Lab - Interactive GUI for PRISMA 2020 Compliance Assessment

This application provides an interactive interface for assessing systematic reviews
against the PRISMA 2020 (Preferred Reporting Items for Systematic reviews and
Meta-Analyses) reporting guidelines.

Usage:
    uv run python prisma2020_lab.py
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from bmlibrarian.lab.prisma2020_lab import run_prisma2020_lab

if __name__ == '__main__':
    run_prisma2020_lab()
