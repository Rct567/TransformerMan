#!/bin/bash

# Git pre-commit hook for TransformerMan
# Runs: pyright && mypy && ruff check && pytest
# Static analysis tools run on staged Python files only
# Pytest runs entire test suite

set -e  # Exit on error for pytest (stop on first error)

echo "Running TransformerMan pre-commit checks..."

# Get staged Python files
STAGED_PY_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true)

# Function to run command and exit on failure
run_check() {
    local cmd="$1"
    local description="$2"

    echo -n "Running $description... "
    if eval "$cmd"; then
        echo "✓"
    else
        echo "✗"
        echo "Error: $description failed"
        exit 1
    fi
}

# Run pyright on staged Python files (or skip if no Python files)
if [ -n "$STAGED_PY_FILES" ]; then
    echo "Checking ${#STAGED_PY_FILES[@]} staged Python file(s) with static analysis tools"

    # Run pyright on staged files
    if command -v pyright >/dev/null 2>&1; then
        run_check "pyright $STAGED_PY_FILES" "pyright"
    else
        echo "Warning: pyright not found, skipping"
    fi

    # Run mypy on staged files
    if command -v mypy >/dev/null 2>&1; then
        run_check "mypy $STAGED_PY_FILES" "mypy"
    else
        echo "Warning: mypy not found, skipping"
    fi

    # Run ruff check on staged files
    if command -v ruff >/dev/null 2>&1; then
        run_check "ruff check $STAGED_PY_FILES" "ruff check"
    else
        echo "Warning: ruff not found, skipping"
    fi
else
    echo "No staged Python files found, skipping static analysis"
fi

# Always run pytest on entire test suite
echo "Running full test suite with pytest..."
run_check "pytest tests/" "pytest"

echo "All pre-commit checks passed! ✓"
exit 0
