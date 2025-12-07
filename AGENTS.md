# TransformerMan Project Rules


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
- Private methods/attributes: `__double_leading_underscore`
- Boolean variables: prefer `is_`, `has_`, `should_` prefixes
- Use `is_too_large` not `is_large` for threshold checks

### Code Organization
- Extract magic numbers into named constants
- Keep methods focused (single responsibility)
- Extract complex logic into private helper methods
- Class constants should be defined right after class declaration
- Import statements should be located at the top of the file

## Testing Requirements

### Test Coverage
- Test files go in `tests/` directory
- Test filename format: `test_<module_name>.py`
- Test class format: `class Test<ModuleName>:`
- Use descriptive test method names: `test_<what>_<scenario>`

### Test Structure
- One test file per module being tested
- Use pytest fixtures, but try to use the real thing where possible (it often is)
- Don't test implementation details, instead focus on behavior, usage/consumption and edge cases

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
5. **Check code**: `ruff check && mypy && pyright`
6. **Verify** all checks pass before considering task complete

Note: `ruff check`, `mypy`, `pyright` and `pytest` should **ALWAYS** be run before ending a task!
