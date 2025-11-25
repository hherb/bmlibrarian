#!/usr/bin/env python3
"""
Study Assessment Lab - Interactive GUI for Study Quality Assessment

This application provides an interactive interface for assessing the quality,
design, and trustworthiness of biomedical research papers stored in the
BMLibrarian database.

Usage:
    uv run python study_assessment_lab.py
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from bmlibrarian.lab.study_assessment_lab import run_study_assessment_lab

if __name__ == '__main__':
    run_study_assessment_lab()
