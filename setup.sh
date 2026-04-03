#!/bin/bash
# Setup script for Cycle Tracker
# Run once on a new machine: ./setup.sh

set -e

echo "=== Cycle Tracker Setup ==="

# Check for Homebrew
if ! command -v brew &>/dev/null; then
    echo "Error: Homebrew not found. Install it from https://brew.sh"
    exit 1
fi

# Install Python 3.12 + Tkinter via Homebrew
echo "Installing Python 3.12 and Tkinter..."
brew install python@3.12 python-tk@3.12

# Find the installed python3.12
PYTHON=$(brew --prefix python@3.12)/bin/python3.12
if [ ! -f "$PYTHON" ]; then
    PYTHON=$(which python3.12)
fi

if [ ! -f "$PYTHON" ]; then
    echo "Error: python3.12 not found after install"
    exit 1
fi

echo "Using Python: $PYTHON"

# Create virtual environment
echo "Creating virtual environment..."
$PYTHON -m venv venv

# Install dependencies
echo "Installing dependencies..."
venv/bin/pip install -r requirements.txt

echo ""
echo "=== Setup complete! ==="
echo "To run:  venv/bin/python3 gui.py"
echo ""
echo "Next steps:"
echo "  1. Place your credentials.json in this folder"
echo "  2. Double-click the Cycle Tracker app, or run: venv/bin/python3 gui.py"
