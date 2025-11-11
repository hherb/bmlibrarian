"""
Command handlers for fact checker CLI.

Provides functions for loading input files, creating agents, and saving results.
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

from bmlibrarian.config import get_model, get_agent_config, BMLibrarianConfig
from ..agent.fact_checker_agent import FactCheckerAgent


def load_input_file(file_path: str) -> List[Dict[str, str]]:
    """
    Load statements from JSON input file.

    Args:
        file_path: Path to JSON input file

    Returns:
        List of statement dictionaries

    Raises:
        ValueError: If file format is invalid
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)

        # Validate format
        if not isinstance(data, list):
            raise ValueError("Input must be a JSON array of statement objects")

        for item in data:
            if not isinstance(item, dict):
                raise ValueError("Each item must be a dictionary")
            if 'statement' not in item:
                raise ValueError("Each item must have a 'statement' field")

        return data

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {e}")
    except Exception as e:
        raise ValueError(f"Error reading input file: {e}")


def save_output_file(results: List[Any], output_path: str, summary: Dict[str, Any]) -> None:
    """
    Save fact-check results to JSON output file.

    Args:
        results: List of FactCheckResult objects
        output_path: Path to output file
        summary: Summary statistics
    """
    output_data = {
        "results": [r.to_dict() for r in results],
        "summary": summary
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n✓ Results saved to: {output_path}")


def create_agent(args: argparse.Namespace) -> FactCheckerAgent:
    """
    Create and configure FactCheckerAgent.

    Args:
        args: Command-line arguments

    Returns:
        Configured FactCheckerAgent
    """
    # Get model and config from centralized configuration
    if args.model:
        model = args.model
    else:
        # Try to get fact_checker_agent model from config, fallback to query_agent
        config = BMLibrarianConfig()
        model = config.get_model('fact_checker_agent')
        if not model:
            model = config.get_model('query_agent')

    # Get agent configuration
    agent_config = get_agent_config('fact_checker') or {}

    # Override with command-line arguments
    if args.temperature is not None:
        agent_config['temperature'] = args.temperature
    if args.score_threshold is not None:
        score_threshold = args.score_threshold
    else:
        score_threshold = agent_config.get('score_threshold', 2.5)

    if args.max_search_results is not None:
        max_search_results = args.max_search_results
    else:
        max_search_results = agent_config.get('max_search_results', 50)

    if args.max_citations is not None:
        max_citations = args.max_citations
    else:
        max_citations = agent_config.get('max_citations', 10)

    # Progress callback
    def progress_callback(step: str, message: str):
        if args.verbose:
            print(f"  [{step}] {message}")

    # Determine database mode
    use_database = not args.json_only if hasattr(args, 'json_only') else True
    db_path = getattr(args, 'db_path', None)
    incremental = getattr(args, 'incremental', False)

    # Create agent
    agent = FactCheckerAgent(
        model=model,
        temperature=agent_config.get('temperature', 0.1),
        top_p=agent_config.get('top_p', 0.9),
        max_tokens=agent_config.get('max_tokens', 2000),
        callback=progress_callback if args.verbose else None,
        show_model_info=True,
        score_threshold=score_threshold,
        max_search_results=max_search_results,
        max_citations=max_citations,
        db_path=db_path,
        use_database=use_database,
        incremental=incremental
    )

    return agent
