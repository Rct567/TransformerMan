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

A git pre-commit hook is included to automatically run code quality checks before committing. The hook script is located at `scripts/pre-commit-hook.sh`.

#### Installation

```bash
# Copy the hook to the git hooks directory
cp scripts/pre-commit-hook.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

#### What the hook runs:
1. **pyright** - Type checking on staged Python files
2. **mypy** - Static type checking on staged Python files
3. **ruff check** - Linting on staged Python files
4. **pytest** - Full test suite (always runs)

#### Usage

```bash
# To temporarily bypass the hook:
git commit --no-verify -m "Your message"

# To remove the hook:
rm .git/hooks/pre-commit
```

#### Features
- Runs static analysis (pyright, mypy, ruff) only on staged Python files
- Always runs the full pytest test suite
- Stops the commit if any check fails

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
