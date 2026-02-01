"""
Tests for PR5: Fail-Closed Module.

Tests the fail-safe mechanisms for paper trading.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch
from datetime import date

import sys
import os

# Direct import to avoid triggering papertrading/__init__.py import chain
import importlib.util

_fail_closed_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "backend", "papertrading", "fail_closed.py"
)
spec = importlib.util.spec_from_file_location("fail_closed", _fail_closed_path)
fail_closed_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fail_closed_module)

CheckResult = fail_closed_module.CheckResult
PreRunCheck = fail_closed_module.PreRunCheck
PreRunCheckResult = fail_closed_module.PreRunCheckResult
PreRunValidator = fail_closed_module.PreRunValidator
FailClosedException = fail_closed_module.FailClosedException
fail_closed = fail_closed_module.fail_closed
fail_closed_async = fail_closed_module.fail_closed_async
NO_TRADE_RESPONSE = fail_closed_module.NO_TRADE_RESPONSE
HealthChecker = fail_closed_module.HealthChecker
validate_pre_run = fail_closed_module.validate_pre_run


class TestPreRunCheck:
    """Test PreRunCheck model."""

    def test_create_passing_check(self):
        """Should create a passing check."""
        check = PreRunCheck(
            name="test_check",
            status=CheckResult.PASS,
            message="All good",
        )

        assert check.name == "test_check"
        assert check.status == CheckResult.PASS
        assert check.timestamp != ""

    def test_create_failing_check(self):
        """Should create a failing check."""
        check = PreRunCheck(
            name="test_check",
            status=CheckResult.FAIL,
            message="Something went wrong",
            details={"error": "details"},
        )

        assert check.status == CheckResult.FAIL
        assert check.details == {"error": "details"}


class TestPreRunCheckResult:
    """Test PreRunCheckResult aggregation."""

    def test_all_pass(self):
        """Should pass when all checks pass."""
        checks = [
            PreRunCheck(name="check1", status=CheckResult.PASS, message="OK"),
            PreRunCheck(name="check2", status=CheckResult.PASS, message="OK"),
        ]

        result = PreRunCheckResult(passed=True, checks=checks)

        assert result.passed is True
        assert len(result.failed_checks) == 0

    def test_one_fail(self):
        """Should fail when any check fails."""
        checks = [
            PreRunCheck(name="check1", status=CheckResult.PASS, message="OK"),
            PreRunCheck(name="check2", status=CheckResult.FAIL, message="Bad"),
        ]

        result = PreRunCheckResult(passed=True, checks=checks)

        assert result.passed is False
        assert "check2" in result.failed_checks

    def test_warns_dont_fail(self):
        """Warnings should not cause failure."""
        checks = [
            PreRunCheck(name="check1", status=CheckResult.PASS, message="OK"),
            PreRunCheck(name="check2", status=CheckResult.WARN, message="Warning"),
        ]

        result = PreRunCheckResult(passed=True, checks=checks)

        assert result.passed is True
        assert "check2" in result.warning_checks


class TestPreRunValidator:
    """Test PreRunValidator checks."""

    def test_check_freeze_policy_not_frozen(self):
        """Should fail if not in frozen period."""
        mock_policy = MagicMock()
        mock_policy.is_frozen_period.return_value = False

        validator = PreRunValidator()
        check = validator.check_freeze_policy(mock_policy)

        assert check.status == CheckResult.FAIL
        assert "frozen period" in check.message.lower()

    def test_check_freeze_policy_no_manifest(self):
        """Should fail if no manifest exists."""
        mock_policy = MagicMock()
        mock_policy.is_frozen_period.return_value = True
        mock_policy.has_manifest.return_value = False

        validator = PreRunValidator()
        check = validator.check_freeze_policy(mock_policy)

        assert check.status == CheckResult.FAIL
        assert "manifest" in check.message.lower()

    def test_check_freeze_policy_success(self):
        """Should pass with valid frozen policy."""
        mock_manifest = MagicMock()
        mock_manifest.manifest_hash = "abc123def456"

        mock_policy = MagicMock()
        mock_policy.is_frozen_period.return_value = True
        mock_policy.has_manifest.return_value = True
        mock_policy.load_manifest.return_value = mock_manifest

        validator = PreRunValidator()
        check = validator.check_freeze_policy(mock_policy)

        assert check.status == CheckResult.PASS

    def test_check_prompt_hash_match(self):
        """Should pass when prompt hashes match."""
        validator = PreRunValidator()
        check = validator.check_prompt_hash(
            expected_hash="abc123",
            actual_hash="abc123",
        )

        assert check.status == CheckResult.PASS

    def test_check_prompt_hash_mismatch(self):
        """Should fail when prompt hashes don't match."""
        validator = PreRunValidator()
        check = validator.check_prompt_hash(
            expected_hash="abc123",
            actual_hash="xyz789",
        )

        assert check.status == CheckResult.FAIL
        assert "mismatch" in check.message.lower()

    def test_check_prompt_hash_missing_expected(self):
        """Should warn when no expected hash."""
        validator = PreRunValidator()
        check = validator.check_prompt_hash(
            expected_hash="",
            actual_hash="abc123",
        )

        assert check.status == CheckResult.WARN

    def test_check_order_book_integrity_success(self):
        """Should pass with valid order book."""
        mock_order_book = MagicMock()
        mock_order_book.get_open_positions.return_value = [
            {"symbol": "AAPL", "entry_date": "2024-01-15"},
            {"symbol": "MSFT", "entry_date": "2024-01-16"},
        ]

        validator = PreRunValidator()
        check = validator.check_order_book_integrity(mock_order_book)

        assert check.status == CheckResult.PASS
        assert check.details["open_positions"] == 2

    def test_check_order_book_integrity_invalid(self):
        """Should fail with invalid positions."""
        mock_order_book = MagicMock()
        mock_order_book.get_open_positions.return_value = [
            {"symbol": "AAPL", "entry_date": "2024-01-15"},
            {"symbol": "", "entry_date": "2024-01-16"},  # Missing symbol
        ]

        validator = PreRunValidator()
        check = validator.check_order_book_integrity(mock_order_book)

        assert check.status == CheckResult.FAIL


class TestFailClosedDecorator:
    """Test the fail_closed decorator."""

    def test_normal_execution(self):
        """Should return normal result when no error."""

        @fail_closed(default_value="default")
        def success_func():
            return "success"

        result = success_func()
        assert result == "success"

    def test_returns_default_on_error(self):
        """Should return default value on error."""

        @fail_closed(default_value="default")
        def error_func():
            raise ValueError("Something went wrong")

        result = error_func()
        assert result == "default"

    def test_returns_no_trade_response(self):
        """Should return NO_TRADE response as default."""

        @fail_closed(default_value=NO_TRADE_RESPONSE)
        def analysis_func():
            raise Exception("LLM error")

        result = analysis_func()

        assert result["score"] == 0.0
        assert result["trade_candidate"] is False
        assert "Fail-closed" in result["no_trade_reason"]

    def test_raises_exception_when_configured(self):
        """Should raise FailClosedException when configured."""

        @fail_closed(default_value="default", raise_exception=True)
        def error_func():
            raise ValueError("Something went wrong")

        with pytest.raises(FailClosedException):
            error_func()


class TestFailClosedAsync:
    """Test the async fail_closed decorator."""

    @pytest.mark.asyncio
    async def test_normal_async_execution(self):
        """Should return normal result for async function."""

        @fail_closed_async(default_value="default")
        async def async_success():
            return "success"

        result = await async_success()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_returns_default_on_async_error(self):
        """Should return default on async error."""

        @fail_closed_async(default_value="default")
        async def async_error():
            raise ValueError("Async error")

        result = await async_error()
        assert result == "default"


class TestNoTradeResponse:
    """Test NO_TRADE_RESPONSE default."""

    def test_no_trade_is_conservative(self):
        """NO_TRADE response should be conservative."""
        assert NO_TRADE_RESPONSE["score"] == 0.0
        assert NO_TRADE_RESPONSE["trade_candidate"] is False
        assert NO_TRADE_RESPONSE["evidence_count"] == 0
        assert NO_TRADE_RESPONSE["key_flags"]["guidance_positive"] is False
        assert NO_TRADE_RESPONSE["key_flags"]["margin_concern"] is False


class TestHealthChecker:
    """Test HealthChecker."""

    def test_check_earnings_api_success(self):
        """Should pass when earnings API has correct interface."""
        mock_client = MagicMock()
        mock_client.get_events_in_range = MagicMock()

        checker = HealthChecker()
        result = checker.check_earnings_api(mock_client)

        assert result is True

    def test_check_llm_service_success(self):
        """Should pass when LLM runner has correct interface."""
        mock_runner = MagicMock()
        mock_runner.analyze = MagicMock()

        checker = HealthChecker()
        result = checker.check_llm_service(mock_runner)

        assert result is True

    def test_check_all(self):
        """Should check all services."""
        mock_client = MagicMock()
        mock_client.get_events_in_range = MagicMock()

        mock_runner = MagicMock()
        mock_runner.analyze = MagicMock()

        checker = HealthChecker()
        results = checker.check_all(mock_client, mock_runner)

        assert results["earnings_api"] is True
        assert results["llm_service"] is True
        assert checker.last_result is True


class TestValidatePreRun:
    """Test the validate_pre_run convenience function."""

    def test_validate_pre_run_all_pass(self):
        """Should pass when all checks pass."""
        mock_manifest = MagicMock()
        mock_manifest.manifest_hash = "abc123"

        mock_policy = MagicMock()
        mock_policy.is_frozen_period.return_value = True
        mock_policy.has_manifest.return_value = True
        mock_policy.load_manifest.return_value = mock_manifest

        mock_order_book = MagicMock()
        mock_order_book.get_open_positions.return_value = []

        result = validate_pre_run(mock_policy, mock_order_book)

        assert result.passed is True

    def test_validate_pre_run_with_prompt_hash(self):
        """Should include prompt hash check when provided."""
        mock_manifest = MagicMock()
        mock_manifest.manifest_hash = "abc123"

        mock_policy = MagicMock()
        mock_policy.is_frozen_period.return_value = True
        mock_policy.has_manifest.return_value = True
        mock_policy.load_manifest.return_value = mock_manifest

        mock_order_book = MagicMock()
        mock_order_book.get_open_positions.return_value = []

        result = validate_pre_run(
            mock_policy,
            mock_order_book,
            expected_prompt_hash="abc123",
            actual_prompt_hash="abc123",
        )

        assert result.passed is True
        check_names = [c.name for c in result.checks]
        assert "prompt_hash" in check_names
