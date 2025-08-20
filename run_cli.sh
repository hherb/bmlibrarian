#!/bin/bash

# BMLibrarian CLI Launcher Script
# 
# This script provides an easy way to launch the BMLibrarian interactive CLI
# with proper environment setup and dependency management.

echo "🏥 BMLibrarian CLI Launcher"
echo "=========================="

# Check if we're in the right directory
if [ ! -f "bmlibrarian_cli.py" ]; then
    echo "❌ Error: bmlibrarian_cli.py not found in current directory"
    echo "Please run this script from the bmlibrarian project root directory"
    exit 1
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ Error: uv package manager not found"
    echo "Please install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found"
    echo "Please create .env file with database configuration:"
    echo "  POSTGRES_DB=knowledgebase"
    echo "  POSTGRES_USER=your_username"
    echo "  POSTGRES_PASSWORD=your_password"
    echo "  POSTGRES_HOST=localhost"
    echo "  POSTGRES_PORT=5432"
    echo ""
    read -p "Continue anyway? (y/n): " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check if Ollama is running
echo "🔍 Checking Ollama service..."
if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "   ✅ Ollama service is running"
else
    echo "   ❌ Ollama service not accessible"
    echo "   Please start Ollama: ollama serve"
    echo ""
    read -p "Continue anyway? (y/n): " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check for required models
echo "🤖 Checking Ollama models..."
if ollama list | grep -q "gpt-oss:20b"; then
    echo "   ✅ gpt-oss:20b model found"
else
    echo "   ⚠️  gpt-oss:20b model not found"
    echo "   Install with: ollama pull gpt-oss:20b"
fi

if ollama list | grep -q "medgemma4B_it_q8:latest"; then
    echo "   ✅ medgemma4B_it_q8:latest model found"
else
    echo "   ⚠️  medgemma4B_it_q8:latest model not found"
    echo "   Install with: ollama pull medgemma4B_it_q8:latest"
fi

# Sync dependencies
echo ""
echo "📦 Syncing dependencies..."
if ! uv sync; then
    echo "❌ Failed to sync dependencies"
    exit 1
fi

echo ""
echo "🚀 Starting BMLibrarian CLI..."
echo "   Use Ctrl+C to exit at any time"
echo ""

# Launch the CLI
exec uv run python bmlibrarian_cli.py