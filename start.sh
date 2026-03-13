#!/bin/bash

# Guardrail Engine - Quick Start Script
# This script helps you quickly set up and run the Guardrail Engine

set -e

echo "======================================"
echo "Guardrail Engine - Quick Start"
echo "======================================"
echo ""

# Check Python version
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python -m venv venv
    echo "✓ Virtual environment created"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate || . venv/Scripts/activate 2>/dev/null
echo "✓ Virtual environment activated"

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✓ Dependencies installed"

echo ""
echo "======================================"
echo "Setup complete!"
echo "======================================"
echo ""
echo "Available commands:"
echo ""
echo "  1. Run demo scenarios:"
echo "     python demo.py"
echo ""
echo "  2. Launch web editor:"
echo "     python web_editor.py"
echo "     (Opens at http://localhost:5000)"
echo ""
echo "======================================"
echo ""

# Ask user what to run
read -p "What would you like to run? (1: Demo, 2: Web Editor, q: Quit): " choice

case $choice in
    1)
        echo ""
        echo "Running demo scenarios..."
        python demo.py
        ;;
    2)
        echo ""
        echo "Starting web editor..."
        echo "Open http://localhost:5000 in your browser"
        python web_editor.py
        ;;
    q|Q)
        echo "Goodbye!"
        exit 0
        ;;
    *)
        echo "Invalid choice. Run 'python demo.py' or 'python web_editor.py' manually."
        ;;
esac
