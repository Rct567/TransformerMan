"""
Test that catches the real ModuleNotFoundError when Anki loads the addon.
This test directly checks the problematic imports in the actual codebase.
"""

from __future__ import annotations

from pathlib import Path

import re


def test_transformerman_imports() -> None:
    """
    Generic test that checks all Python files for problematic imports.

    This test scans the entire codebase and ensures no file uses absolute imports
    from the transformerman package, which would fail when Anki loads the addon.
    """

    # Find all Python files in the transformerman directory
    transformerman_dir = Path(__file__).parent.parent / "transformerman"
    python_files = list(transformerman_dir.rglob("*.py"))

    # Pattern to match absolute imports from transformerman package
    absolute_import_pattern = re.compile(r"^from transformerman\.")
    direct_aqt_import_pattern = re.compile(r"^from aqt import Q")

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

            error = ""

            if absolute_import_pattern.match(line.strip()):
                error = "Found problematic absolute imports that would fail in Anki"
            elif direct_aqt_import_pattern.match(line.strip()):
                error = "Direct imports from aqt are not allowed; use aqt.qt instead"

            if error:
                problematic_files.append({
                    "file": str(file_path.relative_to(Path(__file__).parent.parent)),
                    "line": line_num,
                    "content": line.strip(),
                    "error": error
                })

    # Fail if any problematic imports found
    if problematic_files:
        error_msg = "Found problematic imports:\n"
        for issue in problematic_files:
            error_msg += f"  {issue['file']}:{issue['line']} - {issue['content']}\n"
            error_msg += f"\nError: {issue['error']}\n\n"
        raise AssertionError(error_msg)
