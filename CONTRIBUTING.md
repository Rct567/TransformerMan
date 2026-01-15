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
├── __init__.py                     # Add-on entry point; handles Anki menu integration.
├── config.json                     # Default configuration for the add-on.
├── scripts/                        # Development and maintenance scripts.
│   └── test.py                     # Comprehensive test runner (ruff, pyright, mypy, pytest, etc.).
├── transformerman/
│   ├── lib/                        # Core business logic (UI-independent).
│   │   ├── addon_config.py         # Manages add-on settings, persistence, and LM client instantiation.
│   │   ├── collection_data.py      # Wrapper for Anki's collection with caching and helper methods.
│   │   ├── field_updates.py        # Defines the FieldUpdates data structure and logic for applying changes to notes.
│   │   ├── generate_operations.py  # Backend logic for generating new notes using LLMs.
│   │   ├── generation_prompt_builder.py # Specialized prompt construction for note generation tasks.
│   │   ├── http_utils.py           # Low-level HTTP communication and progress tracking for API requests.
│   │   ├── lm_clients.py           # Abstracted interface for various LLM providers (OpenAI, Anthropic, etc.).
│   │   ├── notes_batching.py       # Batching of notes to stay within (prompt size) limits.
│   │   ├── prompt_builder.py       # Base class for XML-based prompt construction and example note selection.
│   │   ├── response_middleware.py  # Extensible middleware for logging, caching, and intercepting LLM responses.
│   │   ├── selected_notes.py       # Data repository for managing the user-selected notes.
│   │   ├── transform_operations.py # Backend logic for transforming existing notes (e.g., filling empty fields).
│   │   ├── transform_prompt_builder.py # Specialized prompt construction for note transformation tasks.
│   │   ├── utilities.py            # Shared helper functions for data manipulation and sampling.
│   │   └── xml_parser.py           # Parsing and generation of the XML.
│   └── ui/                         # User Interface components (Qt-based).
│       ├── generate/               # Components for the "Generate Notes" feature.
│       │   ├── generate_notes_dialog.py # Main entry point for generating new notes from text.
│       │   ├── generated_notes_table.py # Interactive preview of notes.
│       │   └── generating_notes.py      # Orchestrates generating notes.
│       ├── transform/              # Components for the "Transform Notes" feature.
│       │   ├── transform_notes_dialog.py # Main entry point for batch-modifying existing notes.
│       │   ├── preview_table.py        # Side-by-side comparison of old vs. new field values.
│       │   ├── field_widgets.py        # Dynamic UI for selecting which fields to read from and write to.
│       │   └── transforming_notes.py   # Orchestrates the transformation process, managing progress.
│       ├── base_dialog.py          # Base class for all add-on dialogs.
│       ├── custom_widgets.py       # UI elements like specialized buttons or labels.
│       ├── progress_dialog.py      # Unified progress tracking for long-running LLM operations.
│       ├── prompt_preview_dialog.py # Allows users to preview the generated prompt before execution.
│       ├── settings_dialog.py      # Central configuration UI for API keys and add-on behavior.
│       ├── stats_widget.py         # Visual feedback on selection size and estimated API usage.
│       └── ui_utilities.py         # Helpers for Qt-specific tasks like layout management and icon handling.
└── tests/                          # Test suite (pytest-based).
```
