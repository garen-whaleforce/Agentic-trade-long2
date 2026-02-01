"""
Leakage Auditor.

Audits code and data flows to prevent lookahead bias.

Types of leakage to detect:
1. Future price data in analysis
2. Post-event information in prompts
3. Outcome-based parameter tuning
4. Data from after T day
"""

import ast
import os
import re
from datetime import date
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

from pydantic import BaseModel


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
    """

    def __init__(self):
        """Initialize auditor."""
        self.code_scanner = CodeLeakageScanner()
        self.prompt_scanner = PromptLeakageScanner()
        self.data_auditor = DataFlowAuditor()

    def full_audit(
        self,
        codebase_path: Path,
        prompts_path: Optional[Path] = None,
    ) -> LeakageAuditResult:
        """
        Run full leakage audit.

        Args:
            codebase_path: Path to codebase
            prompts_path: Path to prompts directory

        Returns:
            LeakageAuditResult
        """
        violations = []
        files_scanned = 0

        # Scan code
        for root, dirs, files in os.walk(codebase_path):
            dirs[:] = [d for d in dirs if d not in {"venv", ".git", "__pycache__", "node_modules"}]
            for file in files:
                if file.endswith(".py"):
                    files_scanned += 1
                    file_path = Path(root) / file
                    violations.extend(self.code_scanner.scan_file(file_path))

        # Scan prompts
        if prompts_path and prompts_path.exists():
            for prompt_file in prompts_path.glob("**/*.md"):
                files_scanned += 1
                content = prompt_file.read_text()
                violations.extend(
                    self.prompt_scanner.scan_prompt(content, str(prompt_file))
                )

        # Categorize violations
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
) -> LeakageAuditResult:
    """
    Convenience function to run leakage audit.

    NOTE: Default paths are relative to current working directory.
    When running from Makefile (cd backend && ...), use defaults.
    When running from project root, pass "backend" and "backend/llm/prompts".

    Args:
        codebase_path: Path to codebase (default "." for running from backend/)
        prompts_path: Path to prompts (default "llm/prompts" for running from backend/)

    Returns:
        LeakageAuditResult
    """
    codebase = Path(codebase_path)
    prompts = Path(prompts_path)

    # Validate paths exist
    if not codebase.exists():
        raise ValueError(f"Codebase path does not exist: {codebase_path}")

    auditor = LeakageAuditor()
    return auditor.full_audit(
        codebase_path=codebase,
        prompts_path=prompts if prompts.exists() else None,
    )
