"""
Test that catches the real ModuleNotFoundError when Anki loads the addon.
This test directly checks the problematic imports in the actual codebase.
"""

from __future__ import annotations

from pathlib import Path

import re
import importlib.util


def test_no_absolute_transformerman_imports() -> None:
    """
    Generic test that checks all Python files for problematic absolute imports.

    This test scans the entire codebase and ensures no file uses absolute imports
    from the transformerman package, which would fail when Anki loads the addon.
    """

    # Find all Python files in the transformerman directory
    transformerman_dir = Path(__file__).parent.parent / "transformerman"
    python_files = list(transformerman_dir.rglob("*.py"))

    # Pattern to match absolute imports from transformerman package
    absolute_import_pattern = re.compile(r"^from transformerman\.")

    problematic_files = []

    for file_path in python_files:
        # Skip __init__.py files and test files
        if file_path.name == "__init__.py" or "test_" in file_path.name:
            continue

        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        for line_num, line in enumerate(lines, 1):
            # Skip comments and docstrings
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue

            if absolute_import_pattern.match(line.strip()):
                problematic_files.append({
                    "file": str(file_path.relative_to(Path(__file__).parent.parent)),
                    "line": line_num,
                    "content": line.strip(),
                })

    # Fail if any problematic imports found
    if problematic_files:
        error_msg = "Found problematic absolute imports that would fail in Anki:\n"
        for issue in problematic_files:
            error_msg += f"  {issue['file']}:{issue['line']} - {issue['content']}\n"
        error_msg += "\nThese should be changed to relative imports (e.g., 'from .lib.module import')"
        raise AssertionError(error_msg)
