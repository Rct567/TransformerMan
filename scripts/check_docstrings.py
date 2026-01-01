#!/usr/bin/env python3
"""
Check for incorrect docstrings (parameters/returns that don't match code).
Ignores missing docstrings - only flags when documented items are wrong.

Usage: python check_docstrings.py [path ...]
"""

from __future__ import annotations

import ast
import sys
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import NoReturn

# Add the project root to Python path so we can import transformerman modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from transformerman.lib.utilities import override


@dataclass
class DocstringError:
    """Represents a docstring validation error."""

    filepath: Path
    line: int
    function_name: str
    message: str

    @override
    def __str__(self) -> str:
        return f"{self.filepath}:{self.line}: Function '{self.function_name}' {self.message}"


class DocstringChecker(ast.NodeVisitor):
    """AST visitor that validates docstrings against function signatures."""

    def __init__(self, filepath: Path) -> None:
        self.filepath = filepath
        self.errors: list[DocstringError] = []

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Visit function/method definitions."""
        if docstring := ast.get_docstring(node):
            self._validate_function_docstring(node, docstring)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def _validate_function_docstring(self, node: ast.FunctionDef | ast.AsyncFunctionDef, docstring: str) -> None:
        """Validate that docstring matches function signature."""
        actual_params = self._extract_parameters(node)
        has_return = self._has_return_value(node)

        doc_params = self._parse_documented_params(docstring)
        doc_has_return = self._documents_return(docstring)
        doc_has_args = self._documents_args_section(docstring)

        # Check for documented parameters that don't exist
        for param in doc_params - actual_params:
            self.errors.append(
                DocstringError(
                    filepath=self.filepath,
                    line=node.lineno,
                    function_name=node.name,
                    message=f"documents parameter '{param}' that doesn't exist",
                )
            )

        # Check for documented return when function doesn't return
        if doc_has_return and not has_return:
            self.errors.append(
                DocstringError(
                    filepath=self.filepath,
                    line=node.lineno,
                    function_name=node.name,
                    message="documents a return value but doesn't return anything",
                )
            )

        # Check for undocumented parameters when Args section is present
        if doc_has_args:
            undocumented_params = actual_params - doc_params
            undocumented_params -= {"self", "cls"}
            if undocumented_params:
                self.errors.append(
                    DocstringError(
                        filepath=self.filepath,
                        line=node.lineno,
                        function_name=node.name,
                        message=f"has undocumented parameter(s): {', '.join(sorted(undocumented_params))}",
                    )
                )

    def _extract_parameters(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        """Extract all parameter names from function signature."""
        params = {arg.arg for arg in node.args.args}
        params.update(arg.arg for arg in node.args.posonlyargs)
        params.update(arg.arg for arg in node.args.kwonlyargs)

        if node.args.vararg:
            params.add(node.args.vararg.arg)
        if node.args.kwarg:
            params.add(node.args.kwarg.arg)

        return params

    def _has_return_value(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Check if function returns a non-None value."""
        return any(isinstance(child, ast.Return) and child.value is not None for child in ast.walk(node))

    def _parse_documented_params(self, docstring: str) -> set[str]:
        """Extract parameter names mentioned in docstring."""
        params: set[str] = set()

        in_example_section = False

        for line in docstring.splitlines():
            stripped_line = line.strip()

            # Check if we're entering or exiting an example section
            if stripped_line.startswith("Example:") or stripped_line.startswith("Examples:"):
                in_example_section = True
                continue
            elif in_example_section and stripped_line and not line.startswith((" ", "\t")):
                # We've exited the example section (non-indented line)
                in_example_section = False

            # Skip example sections
            if in_example_section:
                continue

            # Sphinx style: :param param_name: description
            if ":param " in stripped_line:
                param: str = stripped_line.split(":param ")[1].split(":")[0].strip()
                params.add(param)
            # Google/Numpy style: param_name: description or param_name (type): description
            elif ":" in stripped_line and not stripped_line.startswith((
                "Returns",
                "Raises",
                "Yields",
                "Args",
                "Parameters",
                "Note",
                "Example",
            )):
                param = stripped_line.split(":")[0].strip().split("(")[0].strip()
                # Basic validation: looks like a parameter name
                if param and param[0].islower() and param.replace("_", "").isalnum():
                    params.add(param)

        return params

    def _documents_return(self, docstring: str) -> bool:
        """Check if docstring documents a return value."""
        lower = docstring.lower()
        return any(marker in lower for marker in ["returns:", "return:", ":returns:", ":return:"])

    def _documents_args_section(self, docstring: str) -> bool:
        """Check if docstring has an Args section."""
        lower = docstring.lower()
        return "args:" in lower


def get_python_files(search_path: Path) -> list[Path]:
    """Get Python files respecting .gitignore if in a git repo."""
    if search_path.is_file():
        return [search_path] if search_path.suffix == ".py" else []

    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
            cwd=search_path,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )

        files: list[Path] = [search_path / line for line in result.stdout.strip().splitlines() if line.strip()]
        return [f for f in files if f.exists()]

    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return _fallback_file_search(search_path)


def _fallback_file_search(search_path: Path) -> list[Path]:
    """Fallback file search when git is unavailable."""
    if search_path.is_file():
        return [search_path] if search_path.suffix == ".py" else []
    return list(search_path.rglob("*.py"))


def check_file(filepath: Path) -> list[DocstringError]:
    """Analyze a Python file for docstring inconsistencies."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))

        checker = DocstringChecker(filepath)
        checker.visit(tree)
        return checker.errors

    except SyntaxError:
        return [DocstringError(filepath, 0, "", "Syntax error, skipping")]
    except Exception as e:
        return [DocstringError(filepath, 0, "", f"Error processing: {e}")]


def main() -> NoReturn:
    """Main entry point."""
    paths: list[Path] = [Path(p) for p in sys.argv[1:]] if len(sys.argv) > 1 else [Path.cwd()]

    all_python_files: set[Path] = set()
    for path in paths:
        if not path.exists():
            print(f"❌ Error: Path '{path}' does not exist", file=sys.stderr)
            sys.exit(1)
        all_python_files.update(get_python_files(path))

    python_files = sorted(all_python_files)

    if not python_files:
        print("⚠ No Python files found", file=sys.stderr)
        sys.exit(0)

    all_errors: list[DocstringError] = [error for filepath in python_files for error in check_file(filepath)]

    if all_errors:
        for error in all_errors:
            print(error)
        sys.exit(1)

    print(f"✓ No incorrect docstrings found in {len(python_files)} files")
    sys.exit(0)


if __name__ == "__main__":
    main()
