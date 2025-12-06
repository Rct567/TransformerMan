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

### Code Style & Standards

Please follow the project's coding standards outlined in `AGENTS.md`. Key points:

- Use `pathlib.Path` for all file system operations (never `os.path`)
- All function signatures must have type hints
- Use modern type hint syntax: `list[str]` not `List[str]`
- Use descriptive variable names with appropriate prefixes (`is_`, `has_`, `should_`)
- Extract magic numbers into named constants

### Running Tests

```bash
# Run all tests
pytest tests -v

# Run specific test file
pytest tests/test_lm_client.py -v

# Run with coverage
pytest tests --cov=transformerman --cov-report=html

# Run tests in parallel
pytest tests -n auto
```

### Type Checking

```bash
mypy transformerman tests
```

### Linting

```bash
ruff check transformerman tests

# Auto-fix linting issues where possible
ruff check --fix transformerman tests
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
- Provides clear success/failure messages

## Project Structure

```
TransformerMan/
├── __init__.py                      # Plugin entry point
├── config.json                      # Default configuration
├── transformerman/
│   ├── lib/                        # Core library
│   │   ├── lm_client.py           # LM client abstraction
│   │   ├── prompt_builder.py      # Prompt construction
│   │   ├── xml_parser.py          # XML parsing
│   │   ├── selected_notes.py      # Note management
│   │   ├── settings_manager.py    # Settings management
│   │   └── transform_operations.py # Batch processing
│   └── ui/                         # User interface
│       ├── main_dialog.py         # Main dialog
│       └── settings_dialog.py     # Settings dialog
└── tests/                          # Test suite
```

## Current Implementation Status

The plugin currently uses a `DummyLMClient` that returns mock responses for testing. To integrate with a real LM service:

1. Create a new class extending `LMClient` in `transformerman/lib/lm_client.py`
2. Implement the `transform(prompt: str) -> str` method
3. Update `__init__.py` to use your client

## Pull Request Process

1. Ensure your code follows the project's style guidelines
2. Run all tests and ensure they pass
3. Update documentation if needed
4. Create a descriptive pull request with:
   - Summary of changes
   - Motivation for the changes
   - Any breaking changes or migration steps

## Code Review Guidelines

- Reviewers should check for:
  - Adherence to coding standards
  - Test coverage for new functionality
  - Documentation updates
  - Performance considerations
  - Security implications

## Getting Help

If you need help or have questions:
- Check the existing issues and discussions
- Review the AGENTS.md file for project-specific guidelines
- Ask questions in pull requests or issues

Thank you for contributing to TransformerMan!
