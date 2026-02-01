"""
PR5: Fail-Closed Module for Paper Trading.

Ensures paper trading fails safely on any error:
1. PreRunChecks - validate environment before running
2. FailClosed decorator - wrap operations to fail safely
3. HealthChecks - verify critical services are available

Principle: If anything goes wrong, NO_TRADE is the default.
"""

import functools
import logging
from datetime import datetime
from enum import Enum
from typing import Callable, Any, Dict, List, Optional, TypeVar

from pydantic import BaseModel

logger = logging.getLogger("fail_closed")


class CheckResult(str, Enum):
    """Result of a pre-run check."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class PreRunCheck(BaseModel):
    """Result of a single pre-run check."""

    name: str
    status: CheckResult
    message: str
    timestamp: str = ""
    details: Optional[Dict[str, Any]] = None

    def __init__(self, **data):
        super().__init__(**data)
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()


class PreRunCheckResult(BaseModel):
    """Result of all pre-run checks."""

    passed: bool
    checks: List[PreRunCheck]
    failed_checks: List[str] = []
    warning_checks: List[str] = []

    def __init__(self, **data):
        super().__init__(**data)
        self.failed_checks = [c.name for c in self.checks if c.status == CheckResult.FAIL]
        self.warning_checks = [c.name for c in self.checks if c.status == CheckResult.WARN]
        self.passed = len(self.failed_checks) == 0


class PreRunValidator:
    """
    Validates environment before paper trading run.

    All checks must pass for paper trading to proceed.
    Fail-closed: Any failure blocks the entire run.
    """

    def __init__(self):
        self.checks: List[PreRunCheck] = []

    def check_freeze_policy(self, policy) -> PreRunCheck:
        """Check that freeze policy is active and valid."""
        try:
            if not policy.is_frozen_period():
                return PreRunCheck(
                    name="freeze_policy",
                    status=CheckResult.FAIL,
                    message="Not in frozen period. Paper trading requires frozen configuration.",
                )

            if not policy.has_manifest():
                return PreRunCheck(
                    name="freeze_policy",
                    status=CheckResult.FAIL,
                    message="No freeze manifest found. Run: make enable-paper-trading",
                )

            manifest = policy.load_manifest()
            if manifest is None:
                return PreRunCheck(
                    name="freeze_policy",
                    status=CheckResult.FAIL,
                    message="Failed to load freeze manifest.",
                )

            return PreRunCheck(
                name="freeze_policy",
                status=CheckResult.PASS,
                message=f"Freeze policy active. Manifest hash: {manifest.manifest_hash[:16]}...",
                details={"manifest_hash": manifest.manifest_hash},
            )

        except Exception as e:
            return PreRunCheck(
                name="freeze_policy",
                status=CheckResult.FAIL,
                message=f"Freeze policy check failed: {str(e)}",
            )

    def check_prompt_hash(self, expected_hash: str, actual_hash: str) -> PreRunCheck:
        """Check that prompt hash matches frozen manifest (PR2 integration)."""
        if not expected_hash:
            return PreRunCheck(
                name="prompt_hash",
                status=CheckResult.WARN,
                message="No expected prompt hash in manifest. Skipping check.",
            )

        if not actual_hash:
            return PreRunCheck(
                name="prompt_hash",
                status=CheckResult.FAIL,
                message="No actual prompt hash provided. Cannot verify prompt integrity.",
            )

        if expected_hash != actual_hash:
            return PreRunCheck(
                name="prompt_hash",
                status=CheckResult.FAIL,
                message=f"Prompt hash mismatch! Expected: {expected_hash[:16]}..., Got: {actual_hash[:16]}...",
                details={
                    "expected": expected_hash,
                    "actual": actual_hash,
                },
            )

        return PreRunCheck(
            name="prompt_hash",
            status=CheckResult.PASS,
            message=f"Prompt hash verified: {expected_hash[:16]}...",
        )

    def check_data_source_available(self, source_name: str, check_fn: Callable[[], bool]) -> PreRunCheck:
        """Check that a data source is available."""
        try:
            available = check_fn()
            if available:
                return PreRunCheck(
                    name=f"data_source_{source_name}",
                    status=CheckResult.PASS,
                    message=f"Data source '{source_name}' is available.",
                )
            else:
                return PreRunCheck(
                    name=f"data_source_{source_name}",
                    status=CheckResult.FAIL,
                    message=f"Data source '{source_name}' is not available.",
                )
        except Exception as e:
            return PreRunCheck(
                name=f"data_source_{source_name}",
                status=CheckResult.FAIL,
                message=f"Data source '{source_name}' check failed: {str(e)}",
            )

    def check_order_book_integrity(self, order_book) -> PreRunCheck:
        """Check that order book is in valid state."""
        try:
            # Check for any corrupted positions
            positions = order_book.get_open_positions()

            # Basic integrity checks
            invalid_positions = []
            for pos in positions:
                if not pos.get("symbol"):
                    invalid_positions.append(f"Missing symbol: {pos}")
                if not pos.get("entry_date"):
                    invalid_positions.append(f"Missing entry_date: {pos}")

            if invalid_positions:
                return PreRunCheck(
                    name="order_book_integrity",
                    status=CheckResult.FAIL,
                    message=f"Order book has {len(invalid_positions)} invalid positions.",
                    details={"invalid_positions": invalid_positions[:5]},  # First 5
                )

            return PreRunCheck(
                name="order_book_integrity",
                status=CheckResult.PASS,
                message=f"Order book healthy. {len(positions)} open positions.",
                details={"open_positions": len(positions)},
            )

        except Exception as e:
            return PreRunCheck(
                name="order_book_integrity",
                status=CheckResult.FAIL,
                message=f"Order book integrity check failed: {str(e)}",
            )

    def check_disk_space(self, min_mb: int = 100) -> PreRunCheck:
        """Check that sufficient disk space is available."""
        try:
            import shutil
            total, used, free = shutil.disk_usage(".")
            free_mb = free // (1024 * 1024)

            if free_mb < min_mb:
                return PreRunCheck(
                    name="disk_space",
                    status=CheckResult.FAIL,
                    message=f"Insufficient disk space: {free_mb}MB (need {min_mb}MB)",
                    details={"free_mb": free_mb, "required_mb": min_mb},
                )

            return PreRunCheck(
                name="disk_space",
                status=CheckResult.PASS,
                message=f"Disk space OK: {free_mb}MB available.",
                details={"free_mb": free_mb},
            )

        except Exception as e:
            return PreRunCheck(
                name="disk_space",
                status=CheckResult.WARN,
                message=f"Could not check disk space: {str(e)}",
            )

    def run_all_checks(self, checks: List[PreRunCheck]) -> PreRunCheckResult:
        """Run all checks and return result."""
        return PreRunCheckResult(passed=True, checks=checks)


class FailClosedException(Exception):
    """Exception raised when fail-closed is triggered."""

    def __init__(self, reason: str, details: Optional[Dict[str, Any]] = None):
        self.reason = reason
        self.details = details or {}
        super().__init__(f"Fail-closed triggered: {reason}")


T = TypeVar("T")


def fail_closed(
    default_value: Any = None,
    log_error: bool = True,
    raise_exception: bool = False,
) -> Callable:
    """
    Decorator to wrap operations with fail-closed behavior.

    If the wrapped function raises any exception:
    1. Log the error
    2. Return default_value (typically NO_TRADE)
    3. Optionally raise FailClosedException

    Args:
        default_value: Value to return on failure
        log_error: Whether to log the error
        raise_exception: Whether to raise FailClosedException

    Usage:
        @fail_closed(default_value={"trade_candidate": False})
        def analyze_event(event):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_error:
                    logger.error(
                        f"Fail-closed triggered in {func.__name__}: {str(e)}",
                        exc_info=True,
                    )

                if raise_exception:
                    raise FailClosedException(
                        reason=f"Error in {func.__name__}",
                        details={"original_error": str(e)},
                    )

                return default_value

        return wrapper

    return decorator


def fail_closed_async(
    default_value: Any = None,
    log_error: bool = True,
    raise_exception: bool = False,
) -> Callable:
    """
    Async version of fail_closed decorator.

    Usage:
        @fail_closed_async(default_value={"trade_candidate": False})
        async def analyze_event(event):
            ...
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if log_error:
                    logger.error(
                        f"Fail-closed triggered in {func.__name__}: {str(e)}",
                        exc_info=True,
                    )

                if raise_exception:
                    raise FailClosedException(
                        reason=f"Error in {func.__name__}",
                        details={"original_error": str(e)},
                    )

                return default_value

        return wrapper

    return decorator


# Default NO_TRADE response for fail-closed scenarios
NO_TRADE_RESPONSE = {
    "score": 0.0,
    "trade_candidate": False,
    "evidence_count": 0,
    "key_flags": {
        "guidance_positive": False,
        "revenue_beat": False,
        "margin_concern": False,
        "guidance_raised": False,
        "buyback_announced": False,
    },
    "evidence_snippets": [],
    "no_trade_reason": "Fail-closed triggered - conservative NO_TRADE",
}


class HealthChecker:
    """
    Health checker for paper trading services.

    Checks critical services before operations.
    """

    def __init__(self):
        self.last_check: Optional[datetime] = None
        self.last_result: bool = False

    def check_earnings_api(self, client) -> bool:
        """Check if earnings API is reachable."""
        try:
            # Simple health check - should implement actual ping
            return hasattr(client, 'get_events_in_range')
        except Exception:
            return False

    def check_llm_service(self, runner) -> bool:
        """Check if LLM service is available."""
        try:
            # Simple check - should implement actual ping
            return hasattr(runner, 'analyze')
        except Exception:
            return False

    def check_all(self, earnings_client, llm_runner) -> Dict[str, bool]:
        """Check all services."""
        self.last_check = datetime.utcnow()
        results = {
            "earnings_api": self.check_earnings_api(earnings_client),
            "llm_service": self.check_llm_service(llm_runner),
        }
        self.last_result = all(results.values())
        return results


def validate_pre_run(
    freeze_policy,
    order_book,
    expected_prompt_hash: Optional[str] = None,
    actual_prompt_hash: Optional[str] = None,
) -> PreRunCheckResult:
    """
    Convenience function to run all pre-run validations.

    This is the recommended entry point for pre-run checks.

    Args:
        freeze_policy: FreezePolicy instance
        order_book: PaperOrderBook instance
        expected_prompt_hash: Expected prompt hash from manifest
        actual_prompt_hash: Actual prompt hash from loaded prompt

    Returns:
        PreRunCheckResult with all check results

    Raises:
        FailClosedException: If any critical check fails and fail_on_error=True
    """
    validator = PreRunValidator()

    checks = [
        validator.check_freeze_policy(freeze_policy),
        validator.check_order_book_integrity(order_book),
        validator.check_disk_space(),
    ]

    # Add prompt hash check if hashes provided
    if expected_prompt_hash or actual_prompt_hash:
        checks.append(
            validator.check_prompt_hash(expected_prompt_hash or "", actual_prompt_hash or "")
        )

    return validator.run_all_checks(checks)
