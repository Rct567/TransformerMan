# Contributing to TransformerMan

Thank you for your interest in contributing to TransformerMan! This document provides guidelines and instructions for developers.

## Development Setup

### Prerequisites
- Python 3.9 or higher
- Git
- Anki (for testing the addon)

### Installation for Development

1. Clone the repository:
   ```bash
   git clone https://github.com/Rct567/TransformerMan.git
   cd TransformerMan
   ```

2. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

## Development Workflow

### Running checks and tests

```bash
ruff check && pyright && mypy && pytest
```

### Pre-commit Hook

A git pre-commit hook is included to automatically run code quality checks before committing.

#### Installation

You have two options to install the pre-commit hook:

**Option 1: Manual installation (using bash script)**
```bash
# Copy the hook to the git hooks directory
cp scripts/pre-commit-hook.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```
*Note: This requires bash to be available on your system.*

**Option 2: Using pre-commit framework (recommended, cross-platform)**
The project includes a `.pre-commit-config.yaml` file. Install the `pre-commit` tool and then:
```bash
# Install pre-commit globally
pip install pre-commit

# Install the git hooks
pre-commit install
```

The pre-commit framework will automatically manage the hook installation and runs the Python command directly for cross-platform compatibility.

#### What the hook runs:
The pre-commit hook runs `scripts/test.py --pytest --staged` which executes:
1. **ruff check** - Linting on staged Python files only (faster)
2. **pyright** - Type checking on staged Python files only (faster)
3. **mypy** - Static type checking on staged Python files only (faster)
4. **pytest** - Full test suite (always runs)

Note: With the `--staged` flag, static analysis tools only check staged Python files, making the pre-commit hook much faster while still ensuring code quality for the files being committed.

#### Usage

```bash
# To temporarily bypass the hook:
git commit --no-verify -m "Your message"

# To remove the hook:
rm .git/hooks/pre-commit
```

#### Features
- Runs comprehensive test suite via `scripts/test.py --pytest --staged`
- Includes ruff, pyright, mypy (on staged files only), and pytest checks
- Stops the commit if any check fails
- Optimized for speed by only checking staged files with static analysis tools

## Project Structure

```
TransformerMan/
├── __init__.py                     # Plugin entry point
├── config.json                     # Default configuration
├── transformerman/
│   ├── lib/                        # Core library
│   │   ├── lm_client.py            # LM client abstraction
│   │   ├── prompt_builder.py       # Prompt construction
│   │   ├── xml_parser.py           # XML parsing
│   │   ├── selected_notes.py       # Note management
│   │   ├── settings_manager.py     # Settings management
│   │   └── transform_operations.py # Batch processing
│   └── ui/                         # User interface
│       ├── main_dialog.py          # Main dialog
│       └── settings_dialog.py      # Settings dialog
└── tests/                          # Test suite
```


## Getting Help

If you need help or have questions:
- Ask questions in pull requests or issues

Thank you for contributing to TransformerMan!
