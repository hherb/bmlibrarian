"""
Configuration Management Module

Handles CLI configuration, command-line argument parsing, and settings validation.
"""

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any


@dataclass
class CLIConfig:
    """Configuration settings for the BMLibrarian CLI."""
    
    # Search settings - defaults will be loaded from global config
    max_search_results: int = 100  # Will be updated from search config
    max_documents_display: int = 10
    
    # Scoring and filtering thresholds - defaults will be loaded from global config
    default_score_threshold: float = 2.5  # Will be updated from search config
    default_min_relevance: float = 0.7
    
    # Processing settings
    timeout_minutes: float = 5.0
    max_workers: int = 4
    polling_interval: float = 0.5
    
    # Display settings
    show_progress: bool = True
    verbose: bool = False
    
    # Automation settings
    auto_mode: bool = False
    
    # Model configuration
    model_config: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        self._load_search_defaults()
        self.validate()
    
    def _load_search_defaults(self):
        """Load default values from global search configuration."""
        try:
            from ..config import get_search_config
            search_config = get_search_config()
            
            # Update defaults from search configuration if not already set by CLI args
            if hasattr(self, '_from_defaults'):
                self.max_search_results = search_config.get('max_results', 100)
                self.default_score_threshold = search_config.get('score_threshold', 2.5)
        except Exception:
            # If config loading fails, keep hardcoded defaults
            pass
    
    def validate(self) -> None:
        """Validate configuration values."""
        if not (1 <= self.max_search_results <= 1000):
            raise ValueError("max_search_results must be between 1 and 1000")
        
        if not (1 <= self.max_documents_display <= 50):
            raise ValueError("max_documents_display must be between 1 and 50")
        
        if not (0 <= self.default_score_threshold <= 5):
            raise ValueError("default_score_threshold must be between 0 and 5")
        
        if not (0 <= self.default_min_relevance <= 1):
            raise ValueError("default_min_relevance must be between 0 and 1")
        
        if not (0.5 <= self.timeout_minutes <= 30):
            raise ValueError("timeout_minutes must be between 0.5 and 30")
        
        if not (1 <= self.max_workers <= 16):
            raise ValueError("max_workers must be between 1 and 16")
    
    def apply_quick_mode(self) -> None:
        """Apply quick testing mode settings."""
        self.max_search_results = 20
        self.timeout_minutes = 2.0
        self.default_score_threshold = 2.0
        self.default_min_relevance = 0.6
        self.max_documents_display = 5
    
    def update_from_dict(self, settings: dict) -> None:
        """Update configuration from a dictionary."""
        for key, value in settings.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.validate()


def parse_command_line_args() -> argparse.Namespace:
    """Parse command line arguments for the CLI."""
    parser = argparse.ArgumentParser(
        description="BMLibrarian Interactive Medical Literature Research CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bmlibrarian_cli.py                    # Default settings
  python bmlibrarian_cli.py --max-results 50  # Limit search to 50 documents  
  python bmlibrarian_cli.py --timeout 10      # Set 10-minute timeout
  python bmlibrarian_cli.py --quick           # Quick testing mode (20 results, 2 min timeout)
        """
    )
    
    parser.add_argument(
        '--max-results', 
        type=int, 
        default=100,
        metavar='N',
        help='Maximum number of search results to retrieve (default: 100)'
    )
    
    parser.add_argument(
        '--timeout',
        type=float,
        default=5.0,
        metavar='M',
        help='Timeout duration in minutes for report generation (default: 5.0)'
    )
    
    parser.add_argument(
        '--score-threshold',
        type=float,
        default=2.5,
        metavar='S',
        help='Default document score threshold (default: 2.5)'
    )
    
    parser.add_argument(
        '--min-relevance',
        type=float,
        default=0.7,
        metavar='R',
        help='Default minimum citation relevance (default: 0.7)'
    )
    
    parser.add_argument(
        '--display-limit',
        type=int,
        default=10,
        metavar='D',
        help='Maximum documents to display at once (default: 10)'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=4,
        metavar='W',
        help='Number of worker threads for processing (default: 4)'
    )
    
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Quick testing mode (20 results, 2-minute timeout, lower thresholds)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output for debugging'
    )
    
    parser.add_argument(
        '--auto',
        action='store_true',
        help='Automatic mode: run full workflow including counterfactual analysis without user interaction'
    )
    
    parser.add_argument(
        'question',
        nargs='?',
        help='Research question (required for --auto mode)'
    )

    # Add authentication arguments
    from .auth_helper import add_auth_arguments, add_config_sync_arguments
    add_auth_arguments(parser)
    add_config_sync_arguments(parser)

    return parser.parse_args()


def create_config_from_args(args: argparse.Namespace) -> CLIConfig:
    """Create a CLIConfig instance from parsed command line arguments."""
    config = CLIConfig(
        max_search_results=args.max_results,
        timeout_minutes=args.timeout,
        default_score_threshold=args.score_threshold,
        default_min_relevance=args.min_relevance,
        max_documents_display=args.display_limit,
        max_workers=args.workers,
        verbose=args.verbose,
        auto_mode=args.auto
    )
    
    if args.quick:
        config.apply_quick_mode()
    
    return config


def show_config_summary(config: CLIConfig, show_non_default_only: bool = True) -> None:
    """Display current configuration settings."""
    default_config = CLIConfig()
    
    print("⚙️  Configuration:")
    
    settings = [
        ("Max search results", config.max_search_results, default_config.max_search_results),
        ("Timeout", f"{config.timeout_minutes} minutes", f"{default_config.timeout_minutes} minutes"),
        ("Score threshold", config.default_score_threshold, default_config.default_score_threshold),
        ("Min relevance", config.default_min_relevance, default_config.default_min_relevance),
        ("Display limit", config.max_documents_display, default_config.max_documents_display),
        ("Workers", config.max_workers, default_config.max_workers),
    ]
    
    for name, current, default in settings:
        if not show_non_default_only or current != default:
            print(f"   {name}: {current}")


class ConfigurationManager:
    """Manages CLI configuration with user interaction for runtime changes."""
    
    def __init__(self, config: CLIConfig):
        self.config = config
    
    def show_configuration_menu(self) -> None:
        """Show interactive configuration menu."""
        while True:
            print(f"\n⚙️  Configuration Settings")
            print("=" * 40)
            print(f"1. Max search results: {self.config.max_search_results}")
            print(f"2. Timeout duration: {self.config.timeout_minutes} minutes")
            print(f"3. Score threshold: {self.config.default_score_threshold}")
            print(f"4. Min relevance: {self.config.default_min_relevance}")
            print(f"5. Documents display limit: {self.config.max_documents_display}")
            print(f"6. Worker threads: {self.config.max_workers}")
            print("7. Reset to defaults")
            print("8. Back to main menu")
            
            choice = input("\nChoose option (1-8): ").strip()
            
            if choice == '1':
                self._update_max_search_results()
            elif choice == '2':
                self._update_timeout()
            elif choice == '3':
                self._update_score_threshold()
            elif choice == '4':
                self._update_min_relevance()
            elif choice == '5':
                self._update_display_limit()
            elif choice == '6':
                self._update_workers()
            elif choice == '7':
                self._reset_to_defaults()
            elif choice == '8':
                break
            else:
                print("❌ Invalid option. Please choose 1-8.")
    
    def _update_max_search_results(self) -> None:
        """Update max search results setting."""
        try:
            new_max = int(input(f"Enter max search results (current: {self.config.max_search_results}): "))
            if 1 <= new_max <= 1000:
                self.config.max_search_results = new_max
                print(f"✅ Max search results set to {new_max}")
            else:
                print("❌ Please enter a number between 1 and 1000")
        except ValueError:
            print("❌ Please enter a valid number")
    
    def _update_timeout(self) -> None:
        """Update timeout setting."""
        try:
            new_timeout = float(input(f"Enter timeout in minutes (current: {self.config.timeout_minutes}): "))
            if 0.5 <= new_timeout <= 30:
                self.config.timeout_minutes = new_timeout
                print(f"✅ Timeout set to {new_timeout} minutes")
            else:
                print("❌ Please enter a number between 0.5 and 30 minutes")
        except ValueError:
            print("❌ Please enter a valid number")
    
    def _update_score_threshold(self) -> None:
        """Update score threshold setting."""
        try:
            new_threshold = float(input(f"Enter score threshold (current: {self.config.default_score_threshold}): "))
            if 0 <= new_threshold <= 5:
                self.config.default_score_threshold = new_threshold
                print(f"✅ Score threshold set to {new_threshold}")
            else:
                print("❌ Please enter a number between 0 and 5")
        except ValueError:
            print("❌ Please enter a valid number")
    
    def _update_min_relevance(self) -> None:
        """Update minimum relevance setting."""
        try:
            new_relevance = float(input(f"Enter min relevance (current: {self.config.default_min_relevance}): "))
            if 0 <= new_relevance <= 1:
                self.config.default_min_relevance = new_relevance
                print(f"✅ Min relevance set to {new_relevance}")
            else:
                print("❌ Please enter a number between 0 and 1")
        except ValueError:
            print("❌ Please enter a valid number")
    
    def _update_display_limit(self) -> None:
        """Update display limit setting."""
        try:
            new_display = int(input(f"Enter documents display limit (current: {self.config.max_documents_display}): "))
            if 1 <= new_display <= 50:
                self.config.max_documents_display = new_display
                print(f"✅ Documents display limit set to {new_display}")
            else:
                print("❌ Please enter a number between 1 and 50")
        except ValueError:
            print("❌ Please enter a valid number")
    
    def _update_workers(self) -> None:
        """Update worker threads setting."""
        try:
            new_workers = int(input(f"Enter number of worker threads (current: {self.config.max_workers}): "))
            if 1 <= new_workers <= 16:
                self.config.max_workers = new_workers
                print(f"✅ Worker threads set to {new_workers}")
            else:
                print("❌ Please enter a number between 1 and 16")
        except ValueError:
            print("❌ Please enter a valid number")
    
    def _reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        default_config = CLIConfig()
        self.config.max_search_results = default_config.max_search_results
        self.config.timeout_minutes = default_config.timeout_minutes
        self.config.default_score_threshold = default_config.default_score_threshold
        self.config.default_min_relevance = default_config.default_min_relevance
        self.config.max_documents_display = default_config.max_documents_display
        self.config.max_workers = default_config.max_workers
        print("✅ All settings reset to defaults")


def load_bmlibrarian_config(config_path: str = None) -> Dict[str, Any]:
    """
    Load BMLibrarian configuration from JSON file.

    Args:
        config_path: Path to config file. If None, searches for bmlibrarian_config.json
                    in current directory and parent directories.

    Returns:
        Configuration dictionary
    """
    from bmlibrarian.utils.config_loader import load_config_with_fallback, load_json_config

    if config_path is None:
        # Use utility to find config in standard locations
        config = load_config_with_fallback()
        if config is None:
            print("⚠️  Warning: bmlibrarian_config.json not found, using default settings")
            return {}
        return config
    else:
        # Load from specific path
        try:
            config = load_json_config(Path(config_path))
            print(f"✅ Loaded configuration from {config_path}")
            return config
        except Exception as e:
            print(f"⚠️  Warning: Failed to load config from {config_path}: {e}")
            return {}


def create_config_with_models(args: argparse.Namespace, config_path: str = None) -> CLIConfig:
    """
    Create a CLIConfig instance with model configuration loaded from JSON.
    
    Args:
        args: Parsed command line arguments
        config_path: Optional path to configuration file
        
    Returns:
        CLIConfig instance with model configuration
    """
    # Load JSON configuration
    model_config = load_bmlibrarian_config(config_path)
    
    # Create base config from args
    config = create_config_from_args(args)
    
    # Add model configuration
    config.model_config = model_config
    
    return config