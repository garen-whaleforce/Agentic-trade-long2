"""
No-Stub Detection Test.

Ensures that production API endpoints don't contain stub responses.
This test scans for patterns that indicate unimplemented code.
"""

import re
from pathlib import Path
from typing import List, Tuple

import pytest


# Directories to scan for stubs
PRODUCTION_DIRS = [
    "backend/api/routes",
    "backend/papertrading",
    "backend/backtest",
]

# Patterns that indicate stub/unimplemented code
STUB_PATTERNS = [
    (r"#\s*TODO:\s*Implement", "TODO: Implement comment"),
    (r"#\s*This is a stub", "Stub comment"),
    (r"stub response", "Stub response text"),
    (r"stub_", "Stub variable/function name"),
    (r"NotImplementedError", "NotImplementedError (may be intentional)"),
    (r'return\s+\{\s*["\']stub', "Stub response dict"),
]

# Allowed exceptions (files that are OK to have stubs)
ALLOWED_EXCEPTIONS = [
    "tests/",  # Tests can have stub patterns
    "__pycache__",  # Ignore bytecode
]


def find_stub_patterns(file_path: Path) -> List[Tuple[int, str, str]]:
    """
    Find stub patterns in a file.

    Returns:
        List of (line_number, pattern_name, line_content) tuples
    """
    violations = []

    try:
        content = file_path.read_text()
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            for pattern, name in STUB_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    violations.append((line_num, name, line.strip()[:80]))

    except Exception as e:
        # Skip files that can't be read
        pass

    return violations


def scan_directory(directory: str) -> List[Tuple[str, int, str, str]]:
    """
    Scan a directory for stub patterns.

    Returns:
        List of (filepath, line_number, pattern_name, line_content) tuples
    """
    all_violations = []
    base_path = Path(directory)

    if not base_path.exists():
        return []

    for file_path in base_path.rglob("*.py"):
        # Skip allowed exceptions
        if any(exc in str(file_path) for exc in ALLOWED_EXCEPTIONS):
            continue

        violations = find_stub_patterns(file_path)
        for line_num, pattern_name, line_content in violations:
            all_violations.append((str(file_path), line_num, pattern_name, line_content))

    return all_violations


class TestNoStubs:
    """Test that production code has no stubs."""

    def test_api_routes_no_stubs(self):
        """API routes should not contain stub responses."""
        violations = scan_directory("backend/api/routes")

        if violations:
            msg = "Found stub patterns in API routes:\n"
            for filepath, line_num, pattern, content in violations:
                msg += f"  {filepath}:{line_num} [{pattern}]: {content}\n"
            pytest.fail(msg)

    def test_papertrading_no_stubs(self):
        """Paper trading code should not contain stubs."""
        violations = scan_directory("backend/papertrading")

        # Filter out allowed stubs (e.g., dry run mode stubs)
        filtered = [v for v in violations if "dry_run" not in v[3].lower()]

        if filtered:
            msg = "Found stub patterns in paper trading:\n"
            for filepath, line_num, pattern, content in filtered:
                msg += f"  {filepath}:{line_num} [{pattern}]: {content}\n"
            pytest.fail(msg)

    def test_backtest_no_stubs(self):
        """Backtest code should not contain stubs."""
        violations = scan_directory("backend/backtest")

        # Filter out allowed stubs (e.g., dry run mode)
        filtered = [v for v in violations if "dry_run" not in v[3].lower()]

        if filtered:
            msg = "Found stub patterns in backtest:\n"
            for filepath, line_num, pattern, content in filtered:
                msg += f"  {filepath}:{line_num} [{pattern}]: {content}\n"
            pytest.fail(msg)


def test_no_todo_implement_in_production():
    """Ensure no TODO: Implement comments in production code."""
    all_violations = []

    for directory in PRODUCTION_DIRS:
        violations = scan_directory(directory)
        todo_violations = [v for v in violations if "TODO" in v[2]]
        all_violations.extend(todo_violations)

    if all_violations:
        msg = "Found TODO: Implement patterns in production code:\n"
        for filepath, line_num, pattern, content in all_violations:
            msg += f"  {filepath}:{line_num}: {content}\n"
        pytest.fail(msg)


def test_all_api_endpoints_implemented():
    """Verify all API endpoints are implemented (no stub returns)."""
    violations = []
    api_dir = Path("backend/api/routes")

    if not api_dir.exists():
        pytest.skip("API routes directory not found")

    for file_path in api_dir.glob("*.py"):
        if file_path.name.startswith("_"):
            continue

        content = file_path.read_text()

        # Check for stub response patterns
        stub_return_pattern = r'return\s+\w+Response\([^)]*backtest_id="bt_\d+_stub'
        if re.search(stub_return_pattern, content):
            violations.append(str(file_path))

    if violations:
        msg = f"Found stub returns in API endpoints: {', '.join(violations)}"
        pytest.fail(msg)


if __name__ == "__main__":
    # Run as script for quick check
    print("Scanning for stub patterns...")

    total_violations = 0
    for directory in PRODUCTION_DIRS:
        violations = scan_directory(directory)
        if violations:
            print(f"\n{directory}:")
            for filepath, line_num, pattern, content in violations:
                print(f"  {filepath}:{line_num} [{pattern}]: {content}")
            total_violations += len(violations)

    if total_violations == 0:
        print("\nNo stub patterns found!")
    else:
        print(f"\nTotal violations: {total_violations}")
