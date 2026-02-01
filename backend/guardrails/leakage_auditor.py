"""
Leakage Auditor.

Audits code and data flows to prevent lookahead bias.

Types of leakage to detect:
1. Future price data in analysis
2. Post-event information in prompts
3. Outcome-based parameter tuning
4. Data from after T day

PR1 Update:
- Added LeakageAuditConfig for scoped scanning
- Added allowlist support for result schema files
- Only scan signal-generating paths by default
"""

import ast
import fnmatch
import os
import re
from datetime import date
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

from pydantic import BaseModel, Field


class LeakageAuditConfig(BaseModel):
    """Configuration for leakage audit scope and allowlist."""

    # Only scan these paths (relative to codebase root)
    include_roots: List[str] = Field(
        default=[
            "llm/",
            "signals/",
            "api/routes/analyze.py",
            "backtest/full_backtest_runner.py",
            "papertrading/runner.py",
        ],
        description="Paths to scan for leakage (relative to codebase)"
    )

    # Exclude these patterns (glob)
    exclude_globs: List[str] = Field(
        default=[
            "**/venv/**",
            "**/.git/**",
            "**/__pycache__/**",
            "**/node_modules/**",
            "**/.pytest_cache/**",
            "**/migrations/**",
        ],
        description="Glob patterns to exclude from scanning"
    )

    # Files where result schema variables are allowed (glob patterns)
    allowlist_file_globs: List[str] = Field(
        default=[
            "**/services/whaleforce_backtest_client.py",
            "**/api/routes/backtest.py",
            "**/papertrading/order_book.py",
            "**/schemas/*.py",
            "**/tests/**/*.py",
        ],
        description="Files where exit_price/entry_price etc are allowed"
    )

    # Regex patterns to allowlist (e.g., in comments or docstrings)
    allowlist_patterns: List[str] = Field(
        default=[
            r"#.*exit_price",  # Comments about exit_price
            r'""".*exit_price.*"""',  # Docstrings
            r"'exit_price'",  # String literals (schema definitions)
            r'"exit_price"',  # String literals
        ],
        description="Regex patterns to allowlist"
    )

    # Variables that are allowed in allowlisted files
    allowlist_variables: List[str] = Field(
        default=[
            "exit_price",
            "entry_price",
            "return_pct",
            "actual_return",
            "realized_return",
        ],
        description="Variables allowed in allowlisted files"
    )


# Default config for signal-generating path scanning
DEFAULT_AUDIT_CONFIG = LeakageAuditConfig()


class LeakageViolation(BaseModel):
    """A detected leakage violation."""

    violation_type: str
    severity: str  # "critical", "warning", "info"
    file_path: str
    line_number: Optional[int] = None
    description: str
    recommendation: str


class LeakageAuditResult(BaseModel):
    """Result of leakage audit."""

    total_files_scanned: int
    violations_found: int
    critical_count: int
    warning_count: int
    info_count: int
    violations: List[LeakageViolation]
    passed: bool


class LeakagePatterns:
    """Patterns that indicate potential leakage."""

    # Code patterns that might indicate future data access
    SUSPICIOUS_CODE_PATTERNS = [
        # Price data access
        (r"get_price.*T\+", "Accessing price data after T day"),
        (r"price.*exit", "Accessing exit price in analysis"),
        (r"future.*price", "Reference to future price"),
        (r"return.*T\+30", "Return calculation in analysis code"),

        # Date manipulation
        (r"event_date\s*\+", "Adding days to event date"),
        (r"timedelta.*days.*[3-9]\d", "Large timedelta (possible future)"),

        # Outcome access
        (r"actual.*return", "Accessing actual returns"),
        (r"realized.*pnl", "Accessing realized P&L"),
        (r"win.*loss.*ratio", "Win/loss calculation"),
    ]

    # Prompt patterns that might leak future info
    SUSPICIOUS_PROMPT_PATTERNS = [
        (r"stock.*went.*up", "Reference to stock movement"),
        (r"stock.*went.*down", "Reference to stock movement"),
        (r"turned out", "Reference to outcome"),
        (r"actually.*happened", "Reference to actual outcome"),
        (r"in hindsight", "Hindsight reference"),
        (r"we now know", "Post-event knowledge"),
    ]

    # Variable names that might indicate leakage
    SUSPICIOUS_VARIABLES = [
        "future_price",
        "exit_price",
        "actual_return",
        "realized_return",
        "outcome",
        "result_price",
        "t_plus_30_price",
    ]


class CodeLeakageScanner:
    """Scans code for potential leakage patterns."""

    def __init__(self, patterns: LeakagePatterns = None):
        """
        Initialize scanner.

        Args:
            patterns: Leakage patterns to check
        """
        self.patterns = patterns or LeakagePatterns()

    def scan_file(self, file_path: Path) -> List[LeakageViolation]:
        """
        Scan a single file for leakage.

        Args:
            file_path: Path to file

        Returns:
            List of violations found
        """
        violations = []

        try:
            with open(file_path, "r") as f:
                content = f.read()
                lines = content.split("\n")
        except Exception:
            return violations

        # Check code patterns
        for line_num, line in enumerate(lines, 1):
            for pattern, description in self.patterns.SUSPICIOUS_CODE_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    violations.append(
                        LeakageViolation(
                            violation_type="code_pattern",
                            severity="warning",
                            file_path=str(file_path),
                            line_number=line_num,
                            description=f"Suspicious pattern: {description}",
                            recommendation="Review to ensure no future data is used",
                        )
                    )

        # Check variable names in Python files
        if file_path.suffix == ".py":
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name):
                        if node.id.lower() in [
                            v.lower() for v in self.patterns.SUSPICIOUS_VARIABLES
                        ]:
                            violations.append(
                                LeakageViolation(
                                    violation_type="suspicious_variable",
                                    severity="critical",
                                    file_path=str(file_path),
                                    line_number=getattr(node, "lineno", None),
                                    description=f"Suspicious variable name: {node.id}",
                                    recommendation="Variable name suggests future data access",
                                )
                            )
            except SyntaxError:
                pass

        return violations

    def scan_directory(
        self,
        directory: Path,
        extensions: Set[str] = {".py", ".md"},
    ) -> List[LeakageViolation]:
        """
        Scan a directory for leakage.

        Args:
            directory: Directory to scan
            extensions: File extensions to check

        Returns:
            List of violations found
        """
        violations = []

        for root, dirs, files in os.walk(directory):
            # Skip certain directories
            dirs[:] = [d for d in dirs if d not in {"venv", ".git", "__pycache__", "node_modules"}]

            for file in files:
                if Path(file).suffix in extensions:
                    file_path = Path(root) / file
                    violations.extend(self.scan_file(file_path))

        return violations


class PromptLeakageScanner:
    """Scans prompts for leakage patterns."""

    def __init__(self, patterns: LeakagePatterns = None):
        """
        Initialize scanner.

        Args:
            patterns: Leakage patterns to check
        """
        self.patterns = patterns or LeakagePatterns()

    def scan_prompt(
        self,
        prompt_content: str,
        prompt_id: str,
    ) -> List[LeakageViolation]:
        """
        Scan a prompt for leakage.

        Args:
            prompt_content: Prompt text
            prompt_id: Identifier for the prompt

        Returns:
            List of violations found
        """
        violations = []

        for pattern, description in self.patterns.SUSPICIOUS_PROMPT_PATTERNS:
            if re.search(pattern, prompt_content, re.IGNORECASE):
                violations.append(
                    LeakageViolation(
                        violation_type="prompt_pattern",
                        severity="critical",
                        file_path=prompt_id,
                        description=f"Prompt contains: {description}",
                        recommendation="Remove reference to future/outcome information",
                    )
                )

        return violations


class DataFlowAuditor:
    """Audits data flow to ensure no future data in analysis."""

    def audit_analysis_input(
        self,
        event_date: date,
        data_sources: Dict[str, Any],
    ) -> List[LeakageViolation]:
        """
        Audit data sources for an analysis.

        Args:
            event_date: The T day (event date)
            data_sources: Dict of data source name to metadata

        Returns:
            List of violations found
        """
        violations = []

        for source_name, metadata in data_sources.items():
            source_date = metadata.get("as_of_date")
            if source_date and source_date > event_date:
                violations.append(
                    LeakageViolation(
                        violation_type="future_data",
                        severity="critical",
                        file_path=source_name,
                        description=f"Data source {source_name} has date {source_date} > event date {event_date}",
                        recommendation="Use only data available on or before event date",
                    )
                )

        return violations


class LeakageAuditor:
    """
    Main auditor that combines all leakage checks.

    Run this as part of CI/CD and before production deployment.

    PR1 Update:
    - Added config parameter for scoped scanning
    - Added allowlist support
    - Only scans signal-generating paths by default
    """

    def __init__(self, config: Optional[LeakageAuditConfig] = None):
        """
        Initialize auditor.

        Args:
            config: Audit configuration (defaults to DEFAULT_AUDIT_CONFIG)
        """
        self.config = config or DEFAULT_AUDIT_CONFIG
        self.code_scanner = CodeLeakageScanner()
        self.prompt_scanner = PromptLeakageScanner()
        self.data_auditor = DataFlowAuditor()

    def _is_path_included(
        self,
        file_path: Path,
        codebase_path: Path,
        config: Optional[LeakageAuditConfig] = None,
    ) -> bool:
        """
        Check if a file path should be included in scanning.

        Args:
            file_path: Absolute path to file
            codebase_path: Base path of codebase
            config: Config to use (defaults to self.config)

        Returns:
            True if file should be scanned
        """
        audit_config = config or self.config

        try:
            relative_path = file_path.relative_to(codebase_path)
        except ValueError:
            return False

        rel_str = str(relative_path)

        # Check exclude globs first
        for exclude_glob in audit_config.exclude_globs:
            if fnmatch.fnmatch(rel_str, exclude_glob):
                return False

        # Check if in include_roots
        for include_root in audit_config.include_roots:
            # Handle both directory patterns (ends with /) and file patterns
            if include_root.endswith("/"):
                # Match "llm/" against "llm/something.py"
                include_dir = include_root.rstrip("/")
                if rel_str.startswith(include_root) or rel_str.startswith(include_dir + os.sep):
                    return True
            else:
                # Exact file match or directory prefix
                if rel_str == include_root or rel_str.startswith(include_root + os.sep):
                    return True

        return False

    def _is_allowlisted(
        self,
        file_path: Path,
        violation: LeakageViolation,
        config: Optional[LeakageAuditConfig] = None,
    ) -> bool:
        """
        Check if a violation should be allowlisted.

        Args:
            file_path: Path to the file
            violation: The detected violation
            config: Config to use (defaults to self.config)

        Returns:
            True if violation should be allowlisted (downgraded/ignored)
        """
        audit_config = config or self.config
        file_str = str(file_path)

        # Check if file matches allowlist globs
        for allowlist_glob in audit_config.allowlist_file_globs:
            if fnmatch.fnmatch(file_str, allowlist_glob):
                # Check if violation is about an allowlisted variable
                if violation.violation_type == "suspicious_variable":
                    for allowed_var in audit_config.allowlist_variables:
                        if allowed_var.lower() in violation.description.lower():
                            return True

        # Check if the violation matches allowlist patterns
        if violation.line_number and file_path.exists():
            try:
                lines = file_path.read_text().split("\n")
                if 0 < violation.line_number <= len(lines):
                    line = lines[violation.line_number - 1]
                    for pattern in audit_config.allowlist_patterns:
                        if re.search(pattern, line, re.IGNORECASE):
                            return True
            except Exception:
                pass

        return False

    def full_audit(
        self,
        codebase_path: Path,
        prompts_path: Optional[Path] = None,
        config: Optional[LeakageAuditConfig] = None,
    ) -> LeakageAuditResult:
        """
        Run full leakage audit.

        Args:
            codebase_path: Path to codebase
            prompts_path: Path to prompts directory
            config: Override audit config for this run

        Returns:
            LeakageAuditResult
        """
        audit_config = config or self.config
        violations = []
        files_scanned = 0
        allowlisted_count = 0

        # Scan code - only in include_roots
        for root, dirs, files in os.walk(codebase_path):
            # Filter out excluded directories by name
            excluded_dir_names = {"venv", ".git", "__pycache__", "node_modules", ".pytest_cache", "migrations"}
            dirs[:] = [d for d in dirs if d not in excluded_dir_names]

            for file in files:
                if file.endswith(".py"):
                    file_path = Path(root) / file

                    # Check if path should be scanned
                    if not self._is_path_included(file_path, codebase_path, audit_config):
                        continue

                    files_scanned += 1
                    file_violations = self.code_scanner.scan_file(file_path)

                    # Filter out allowlisted violations
                    for v in file_violations:
                        if self._is_allowlisted(file_path, v, audit_config):
                            allowlisted_count += 1
                            # Downgrade to info instead of critical/warning
                            v.severity = "info"
                            v.description = f"[ALLOWLISTED] {v.description}"
                        violations.append(v)

        # Scan prompts (always scan all prompts)
        if prompts_path and prompts_path.exists():
            for prompt_file in prompts_path.glob("**/*.md"):
                files_scanned += 1
                content = prompt_file.read_text()
                violations.extend(
                    self.prompt_scanner.scan_prompt(content, str(prompt_file))
                )

        # Categorize violations (after allowlist processing)
        critical = sum(1 for v in violations if v.severity == "critical")
        warning = sum(1 for v in violations if v.severity == "warning")
        info = sum(1 for v in violations if v.severity == "info")

        return LeakageAuditResult(
            total_files_scanned=files_scanned,
            violations_found=len(violations),
            critical_count=critical,
            warning_count=warning,
            info_count=info,
            violations=violations,
            passed=critical == 0,
        )


def run_leakage_audit(
    codebase_path: str = ".",
    prompts_path: str = "llm/prompts",
    config: Optional[LeakageAuditConfig] = None,
    verbose: bool = False,
) -> LeakageAuditResult:
    """
    Convenience function to run leakage audit.

    NOTE: Default paths are relative to current working directory.
    When running from Makefile (cd backend && ...), use defaults.
    When running from project root, pass "backend" and "backend/llm/prompts".

    PR1 Update:
    - Uses scoped scanning by default (only signal-generating paths)
    - Supports allowlist for result schema files
    - Added verbose option for debugging

    Args:
        codebase_path: Path to codebase (default "." for running from backend/)
        prompts_path: Path to prompts (default "llm/prompts" for running from backend/)
        config: Audit configuration (defaults to DEFAULT_AUDIT_CONFIG)
        verbose: Print verbose output

    Returns:
        LeakageAuditResult
    """
    codebase = Path(codebase_path)
    prompts = Path(prompts_path)

    # Validate paths exist
    if not codebase.exists():
        raise ValueError(f"Codebase path does not exist: {codebase_path}")

    audit_config = config or DEFAULT_AUDIT_CONFIG

    if verbose:
        print(f"Leakage Audit Configuration:")
        print(f"  Codebase: {codebase.absolute()}")
        print(f"  Prompts: {prompts.absolute() if prompts.exists() else 'N/A'}")
        print(f"  Include roots: {audit_config.include_roots}")
        print(f"  Allowlist files: {audit_config.allowlist_file_globs}")

    auditor = LeakageAuditor(config=audit_config)
    result = auditor.full_audit(
        codebase_path=codebase,
        prompts_path=prompts if prompts.exists() else None,
    )

    if verbose:
        print(f"\nAudit Result:")
        print(f"  Files scanned: {result.total_files_scanned}")
        print(f"  Violations: {result.violations_found}")
        print(f"  Critical: {result.critical_count}")
        print(f"  Warning: {result.warning_count}")
        print(f"  Info: {result.info_count}")
        print(f"  Passed: {result.passed}")

    return result


def create_strict_config() -> LeakageAuditConfig:
    """
    Create a strict config that scans all paths (for comprehensive audits).

    Returns:
        LeakageAuditConfig with all paths included
    """
    return LeakageAuditConfig(
        include_roots=["."],  # Scan everything
        exclude_globs=[
            "**/venv/**",
            "**/.git/**",
            "**/__pycache__/**",
            "**/node_modules/**",
        ],
        allowlist_file_globs=[],  # No allowlist
        allowlist_patterns=[],
    )


def create_signal_path_config() -> LeakageAuditConfig:
    """
    Create config that only scans signal-generating paths (default).

    This is the recommended config for CI/CD to avoid false positives
    on result schema files.

    Returns:
        LeakageAuditConfig for signal paths only
    """
    return DEFAULT_AUDIT_CONFIG
