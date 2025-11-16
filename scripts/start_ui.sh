#!/bin/bash
# Quick start script for Deal Finder UI

echo "🚀 Starting Deal Finder UI Server..."
echo ""

# Check if uvicorn is installed
if ! command -v uvicorn &> /dev/null; then
    echo "❌ uvicorn not found. Installing dependencies..."
    pip install fastapi uvicorn[standard] websockets
fi

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "⚠️  Warning: OPENAI_API_KEY not set in environment"
    echo "   You can set it in the UI or export it before running"
fi

echo "✓ Starting server on http://localhost:8000"
echo "  Press Ctrl+C to stop"
echo ""

# Start the server
uvicorn ui_server:app --reload --port 8000
