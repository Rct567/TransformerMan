# TransformerMan Project Rules

## Philosophy

This codebase will outlive you. Every shortcut becomes someone else's burden. Every hack compounds into technical debt that slows the whole team down.
You are not just writing code. You are shaping the future of this project. The patterns you establish will be copied. The corners you cut will be cut again.
Fight entropy. Leave the codebase better than you found it.

## Codebase Overview

### Main Directories

- **`transformerman/`** - Core addon code (card ranking, targets, language processing)
  - `transformerman/lib/` - Utility modules (config, logging, caching, database)
  - `transformerman/ui/` - Qt-based UI components (main window, tabs, dialogs)
- **`tests/`** - Test suite with `test_*.py` files matching source modules
- **`user_files/`** - User-generated data and logs (blocked by .gitignore)

### Key Files

- `__init__.py` - Main addon entry point (loaded by Anki)
- `config.json` - Default addon configuration
- `pyproject.toml` - Project dependencies and configuration
- `pytest.ini` - Pytest configuration

## Code Style & Standards

### File System Operations
- **ALWAYS use `pathlib.Path`** for all file system operations
- Never use `os.path` - prefer Path methods
- Type hints should use `Path` from `pathlib`
- Example: `def process_file(file_path: Path) -> None:`

### Type Hints
- All function signatures must have type hints
- Avoid `Any` unless absolutely necessary (it rarely is)
- Use modern syntax: `list[str]` not `List[str]`, `set[str]` not `Set[str]`
- Use `Optional[]` for variables that can be `None`
- Use `Sequence` instead of `list` for non-mutable sequences
- Use `from typing import` only for: `Callable`, `Optional`, `TypeVar`, etc.
- Use `from collections.abc import` for: `Generator`, `Iterator`, `Sequence` etc.
- Always include return type hints (use `-> None` when appropriate)
- `from __future__ import annotations` should be at the top of every file (to prevent evaluating type hints at runtime).

### Naming Conventions
- Use descriptive variable names
- Constants at class/module level: `UPPER_SNAKE_CASE`
- Private methods/attributes: `_leading_underscore`
- Boolean variables: prefer `is_`, `has_`, `should_` prefixes
- Use `is_too_large` not `is_large` for threshold checks

### Code Organization
- Extract magic numbers into named constants
- Keep methods focused (single responsibility)
- Extract complex logic into private helper methods
- Class constants should be defined right after class declaration
- Import statements should ALWAYS be located at the top of the file

## Testing

### Test Coverage Requirements
- Test files go in `tests/` directory
- Test filename format: `test_<module_name>.py`
- Test class format: `class Test<ModuleName>:`
- Use descriptive test method names: `test_<what>_<scenario>`
- One test file per module being tested

### Best practices
- Use pytest fixtures, but try to use the real thing where possible (avoid mocking if possible).
- Don't test implementation details, instead focus on behavior, usage/consumption and edge cases.
- Don't test private methods/attributes, instead test public APIs.

### Test Collections

- **TestCollection is a real Anki collection**: The `TestCollection` class in `tests/tools.py` inherits from `anki.collection.Collection` and provides real (temporary) collection instances for testing.
- **Available collections**: See `tests/data/collections/test_collections.md` for details on available test collections (e.g., `empty_collection`, `two_deck_collection`).

#### When to Use Which Collection

- **If a test needs notes to exist**: Use `two_deck_collection`. It has 16 notes with stable IDs. Update existing notes via API (e.g., `note['Front'] = 'new value'`).
- **If a test does not require notes at all**: Use `empty_collection`, but keep in mind: Creating new notes here gives them random IDs every test run, which can be problematic.

## Root Directory Structure

### Main Code
- `transformerman/` - Main addon code
- `transformerman/lib/` - Utility libraries
- `transformerman/ui/` - UI components

### Entry Point & Configuration
- `__init__.py` - Main addon entry point, loaded by Anki
- `config.json` - Default addon configuration
- `manifest.json` - Addon metadata for Anki
- `pytest.ini` - Pytest configuration
- `pyproject.toml` - Project configuration and dependencies


### Data Directories
- `user_files/` - User-generated data and logs

### Tests
- `tests/` - All test files
- `tests/ui/` - UI tests

## Common Patterns

### Context Managers
- Use context managers for resource management
- Example: `with file_path.open('r', encoding='utf-8') as file:`
- Always specify encoding for text files

### Error Handling
- Use specific exceptions, not bare `except:`
- Provide helpful error messages

## Documentation

### Docstrings
- Keep simple methods self-documenting through clear names
- Format: `"""Brief description."""` for one-liners
- Skip docstrings for simple methods if other methods in the same (already existing) class are without docstrings
- Skip docstrings for function if other functions in the same (already existing) file are without docstrings

### Comments
- Explain WHY, not WHAT
- Keep comments up-to-date with code changes
- Prefer self-documenting code over comments

## Anki-Specific Guidelines

### Compatibility
- Ensure compatibility with Anki's Qt framework
- Use PyQt6 imports from `aqt.qt`
- Ensure compatibility with Python 3.9

#### PyQt6
- Ensure PyQt6 compatibility
- Qt6 requires enums to be prefixed with their type name. For example:
 `self.setWizardStyle(QWizard.ClassicStyle)` becomes `self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)` and `f.setStyleHint(QFont.Monospace)` becomes `f.setStyleHint(QFont.StyleHint.Monospace)`.

## Workflow Summary

1. **Create code** following style guidelines
2. **Write or update tests** if appropriate
3. **Run tests**: `pytest -vv --full-trace --showlocals --maxfail=3`
4. **Fix issues** if tests fail and run tests again
5. **Check code**: `ruff check && pyright` (and `pytest` if appropriate)
6. **Verify** all checks pass before considering task complete

Note: `ruff check`, `pyright` and `pytest` should **ALWAYS** be run before ending a task!
