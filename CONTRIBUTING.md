# Contributing to TransformerMan

Thank you for your interest in contributing to TransformerMan! This document provides guidelines and instructions for developers.

## Development Setup

### Prerequisites
- Python 3.9 or higher
- Git
- Anki (for testing the addon)

### Installation for Development


1. Go to the Anki plugin folder, such as `C:\Users\%USERNAME%\AppData\Roaming\Anki2\addons21`.
2. Create a new folder with the name `TransformerMan`.
3. Make sure you are still in the directory `addons21`.
4. Run: `git clone https://github.com/Rct567/TransformerMan.git TransformerMan`
5. Start Anki.

#### Install development dependencies

```bash
pip install -r requirements-dev.txt
```

###

## Development Workflow

### Running checks and tests

```bash
python ./scripts/test.py
```

### Pre-commit Hook

A git pre-commit hook is included to automatically run code quality checks before committing.

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
1. **ruff check** - Linting on staged Python files only
2. **pyright** - Type checking on staged Python files only
3. **mypy** - Static type checking on staged Python files only
4. **pytest** - Full test suite (always runs)


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

## Project Structure

```
TransformerMan/
├── __init__.py                     # Plugin entry point
├── config.json                     # Default add-on configuration
├── scripts/                        # Utility scripts
│   └── test.py                     # Test runner
├── transformerman/
│   ├── lib/
│   │   ├── addon_config.py         # Addon configuration
│   │   ├── http_utils.py           # HTTP utilities
│   │   ├── lm_clients.py           # Language model clients
│   │   ├── notes_batching.py       # Note batching logic
│   │   ├── prompt_builder.py       # Prompt construction
│   │   ├── selected_notes.py       # Data repository representing the notes selected by the user
│   │   ├── response_middleware.py  # Response middleware (used for logging and caching LM responses)
│   │   ├── transform_operations.py # Batch processing (where FieldUpdates are created from the LM responses)
│   │   ├── field_updates.py        # Field update logic
│   │   ├── utilities.py            # Utility functions
│   │   └── xml_parser.py           # XML parsing utilities
│   └── ui/
│       ├── main_window.py          # Main window
│       ├── settings_dialog.py      # Settings dialog
│       ├── base_dialog.py          # Base dialog
│       ├── preview_table.py        # Preview table
│       └── ...                     # Other UI components
└── tests/                          # Test suite
```
