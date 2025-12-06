#!/bin/bash

# Git pre-commit hook for TransformerMan
# Runs: scripts/test.py --pytest --staged
# This runs ruff, pyright, mypy (on staged files only), and pytest in one command

set -e  # Exit on error

echo "Running TransformerMan pre-commit checks..."

# Run the test script with --pytest and --staged flags
echo "Running comprehensive test suite with scripts/test.py --pytest --staged..."
python scripts/test.py --pytest --staged

echo "All pre-commit checks passed! ✓"
exit 0
