#!/usr/bin/env python3
"""
BMLibrarian Configuration Management Script

Utility script for managing BMLibrarian configuration settings.
"""

import sys
import os
import argparse

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bmlibrarian.config import get_config, reload_config

def show_config():
    """Show current configuration."""
    config = get_config()
    
    print("🔧 BMLibrarian Current Configuration")
    print("=" * 50)
    
    print("\n📋 Models:")
    models = config._config["models"]
    for agent_type, model in models.items():
        print(f"  {agent_type:<20}: {model}")
    
    print("\n🌐 Ollama:")
    ollama = config.get_ollama_config()
    for key, value in ollama.items():
        print(f"  {key:<20}: {value}")
    
    print("\n⚙️  Agent Settings:")
    agents = config._config["agents"]
    for agent_type, settings in agents.items():
        print(f"  {agent_type}:")
        for key, value in settings.items():
            print(f"    {key:<18}: {value}")

def create_config():
    """Create a sample configuration file."""
    config = get_config()
    config.create_sample_config()

def set_model(agent_type: str, model: str):
    """Set model for a specific agent type."""
    config = get_config()
    
    # Map common agent names to config keys
    agent_mapping = {
        "counterfactual": "counterfactual_agent",
        "query": "query_agent", 
        "scoring": "scoring_agent",
        "citation": "citation_agent",
        "reporting": "reporting_agent"
    }
    
    config_key = agent_mapping.get(agent_type, agent_type)
    
    if config_key not in config._config["models"]:
        print(f"❌ Unknown agent type: {agent_type}")
        print(f"Available types: {', '.join(agent_mapping.keys())}")
        return
    
    config.set(f"models.{config_key}", model)
    config.save_config()
    
    print(f"✅ Set {agent_type} model to: {model}")
    print("💾 Configuration saved")

def quick_switch(preset: str):
    """Quickly switch to a preset configuration."""
    config = get_config()
    
    presets = {
        "fast": "medgemma4B_it_q8:latest",
        "medical": "medgemma-27b-text-it-Q8_0:latest", 
        "complex": "gpt-oss:20b"
    }
    
    if preset not in presets:
        print(f"❌ Unknown preset: {preset}")
        print(f"Available presets: {', '.join(presets.keys())}")
        return
    
    model = presets[preset]
    
    # Set all agent models to the preset
    for agent_type in ["counterfactual_agent", "query_agent", "scoring_agent", "citation_agent"]:
        config.set(f"models.{agent_type}", model)
    
    # Keep reporting agent on complex model for better report generation
    if preset != "complex":
        config.set("models.reporting_agent", presets["complex"])
    
    config.save_config()
    
    print(f"✅ Switched to '{preset}' preset ({model})")
    print("💾 Configuration saved")

def test_models():
    """Test connection to all configured models."""
    config = get_config()
    
    print("🧪 Testing Model Connections")
    print("=" * 40)
    
    # Import here to avoid circular imports during config loading
    from bmlibrarian.agents import CounterfactualAgent
    
    models = config._config["models"]
    unique_models = set(models.values())
    
    for model in unique_models:
        print(f"\n🔍 Testing: {model}")
        try:
            agent = CounterfactualAgent(model=model)
            if agent.test_connection():
                print(f"  ✅ Connection successful")
            else:
                print(f"  ❌ Connection failed")
        except Exception as e:
            print(f"  ❌ Error: {e}")

def main():
    parser = argparse.ArgumentParser(description="BMLibrarian Configuration Manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Show config command
    subparsers.add_parser("show", help="Show current configuration")
    
    # Create config command  
    subparsers.add_parser("create", help="Create sample configuration file")
    
    # Set model command
    set_parser = subparsers.add_parser("set", help="Set model for an agent type")
    set_parser.add_argument("agent", help="Agent type (counterfactual, query, scoring, citation, reporting)")
    set_parser.add_argument("model", help="Model name")
    
    # Quick switch command
    switch_parser = subparsers.add_parser("switch", help="Quick switch to preset configuration")
    switch_parser.add_argument("preset", choices=["fast", "medical", "complex"], 
                              help="Preset configuration (fast, medical, complex)")
    
    # Test models command
    subparsers.add_parser("test", help="Test connection to all configured models")
    
    args = parser.parse_args()
    
    if args.command == "show":
        show_config()
    elif args.command == "create":
        create_config()
    elif args.command == "set":
        set_model(args.agent, args.model)
    elif args.command == "switch":
        quick_switch(args.preset)
    elif args.command == "test":
        test_models()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()