"""
Tests for Leakage Auditor scope and allowlist functionality.

PR1: Ensures that:
1. Result schema files (exit_price, entry_price, etc.) are not flagged as critical
2. Signal-generating paths ARE flagged when they use future data
3. Allowlist patterns work correctly
"""

import pytest
from pathlib import Path
import tempfile
import os

from backend.guardrails.leakage_auditor import (
    LeakageAuditor,
    LeakageAuditConfig,
    LeakageViolation,
    run_leakage_audit,
    DEFAULT_AUDIT_CONFIG,
    create_strict_config,
)


class TestLeakageAuditConfig:
    """Test LeakageAuditConfig defaults and customization."""

    def test_default_config_has_include_roots(self):
        """Default config should include signal-generating paths."""
        config = DEFAULT_AUDIT_CONFIG
        assert "llm/" in config.include_roots
        assert "signals/" in config.include_roots
        assert any("analyze" in r for r in config.include_roots)

    def test_default_config_has_allowlist(self):
        """Default config should have allowlist for result schema files."""
        config = DEFAULT_AUDIT_CONFIG
        assert any("backtest" in g for g in config.allowlist_file_globs)
        assert any("order_book" in g for g in config.allowlist_file_globs)

    def test_strict_config_scans_everything(self):
        """Strict config should scan all paths."""
        config = create_strict_config()
        assert "." in config.include_roots
        assert len(config.allowlist_file_globs) == 0


class TestAllowlistBehavior:
    """Test that allowlisted files don't trigger critical violations."""

    @pytest.fixture
    def temp_codebase(self, tmp_path):
        """Create a temporary codebase for testing."""
        # Create directory structure
        (tmp_path / "services").mkdir()
        (tmp_path / "signals").mkdir()
        (tmp_path / "llm").mkdir()
        (tmp_path / "api" / "routes").mkdir(parents=True)

        return tmp_path

    def test_allowlisted_file_not_critical(self, temp_codebase):
        """
        Files in allowlist (e.g., whaleforce_backtest_client.py)
        should NOT trigger critical violations for exit_price.
        """
        # Create an allowlisted file with exit_price
        allowlisted_file = temp_codebase / "services" / "whaleforce_backtest_client.py"
        allowlisted_file.write_text('''
"""Backtest client - result schema."""

class BacktestResult:
    exit_price: float
    entry_price: float
    return_pct: float

def get_result():
    return {"exit_price": 100.0, "entry_price": 95.0}
''')

        # Config that includes services/ but has allowlist
        config = LeakageAuditConfig(
            include_roots=["services/"],
            allowlist_file_globs=["**/services/whaleforce_backtest_client.py"],
            allowlist_variables=["exit_price", "entry_price", "return_pct"],
        )

        auditor = LeakageAuditor(config=config)
        result = auditor.full_audit(temp_codebase)

        # Should pass (no critical violations)
        assert result.passed, f"Should pass but got violations: {result.violations}"
        # Any violations should be info (allowlisted)
        for v in result.violations:
            assert v.severity != "critical", f"Unexpected critical: {v}"

    def test_signal_path_with_future_data_is_critical(self, temp_codebase):
        """
        Files in signal-generating paths (e.g., signals/generator.py)
        SHOULD trigger critical violations for exit_price.
        """
        # Create a signal generator with forbidden future data access
        signal_file = temp_codebase / "signals" / "generator.py"
        signal_file.write_text('''
"""Signal generator - should NOT access future data."""

def generate_signal(event):
    # BAD: Using exit_price to decide signal
    exit_price = get_future_price(event.date + 30)
    if exit_price > event.current_price:
        return "BUY"
    return "NO_TRADE"
''')

        config = LeakageAuditConfig(
            include_roots=["signals/"],
            allowlist_file_globs=[],  # No allowlist
        )

        auditor = LeakageAuditor(config=config)
        result = auditor.full_audit(temp_codebase)

        # Should fail (critical violation for exit_price in signal path)
        assert not result.passed, "Should fail but passed"
        assert result.critical_count > 0, "Should have critical violations"

        # Verify the violation is about exit_price
        critical_violations = [v for v in result.violations if v.severity == "critical"]
        assert any("exit_price" in v.description.lower() for v in critical_violations)

    def test_llm_path_with_t_plus_30_is_critical(self, temp_codebase):
        """
        LLM analysis code using T+30 price should be flagged as critical.
        """
        llm_file = temp_codebase / "llm" / "analyzer.py"
        llm_file.write_text('''
"""LLM analyzer."""

def analyze(event):
    # BAD: Using T+30 price in analysis
    future_price = get_price(event.date + timedelta(days=30))
    prompt = f"Price went to {future_price}"
    return call_llm(prompt)
''')

        config = LeakageAuditConfig(
            include_roots=["llm/"],
            allowlist_file_globs=[],
        )

        auditor = LeakageAuditor(config=config)
        result = auditor.full_audit(temp_codebase)

        # Should have warnings or critical for T+30 patterns
        assert result.violations_found > 0, "Should detect T+30 pattern"


class TestPathInclusion:
    """Test that path inclusion logic works correctly."""

    @pytest.fixture
    def temp_codebase(self, tmp_path):
        """Create a temporary codebase with multiple directories."""
        for d in ["llm", "signals", "services", "api/routes", "tests", "utils"]:
            (tmp_path / d).mkdir(parents=True, exist_ok=True)
        return tmp_path

    def test_only_included_paths_scanned(self, temp_codebase):
        """Only files in include_roots should be scanned."""
        # Create files in multiple directories
        (temp_codebase / "llm" / "runner.py").write_text("exit_price = 100")
        (temp_codebase / "utils" / "helper.py").write_text("exit_price = 100")

        config = LeakageAuditConfig(
            include_roots=["llm/"],
            allowlist_file_globs=[],
        )

        auditor = LeakageAuditor(config=config)
        result = auditor.full_audit(temp_codebase)

        # Should only scan 1 file (llm/runner.py)
        assert result.total_files_scanned == 1

    def test_file_pattern_inclusion(self, temp_codebase):
        """Specific file patterns should be included."""
        # Create the specific file
        analyze_file = temp_codebase / "api" / "routes" / "analyze.py"
        analyze_file.write_text("future_price = get_price()")

        config = LeakageAuditConfig(
            include_roots=["api/routes/analyze.py"],
            allowlist_file_globs=[],
        )

        auditor = LeakageAuditor(config=config)
        result = auditor.full_audit(temp_codebase)

        # Should scan exactly that file
        assert result.total_files_scanned == 1


class TestPromptScanning:
    """Test that prompts are always scanned regardless of include_roots."""

    def test_prompts_always_scanned(self, tmp_path):
        """Prompts should be scanned even if not in include_roots."""
        # Create prompt with forbidden content
        prompts_dir = tmp_path / "llm" / "prompts"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "bad_prompt.md").write_text("""
# Bad Prompt
The stock went up after earnings. We now know it was a good investment.
""")

        config = LeakageAuditConfig(
            include_roots=["signals/"],  # Not llm/prompts
        )

        auditor = LeakageAuditor(config=config)
        result = auditor.full_audit(
            codebase_path=tmp_path,
            prompts_path=prompts_dir,
        )

        # Should detect prompt violations
        prompt_violations = [v for v in result.violations if v.violation_type == "prompt_pattern"]
        assert len(prompt_violations) > 0, "Should detect prompt violations"


class TestRunLeakageAuditFunction:
    """Test the convenience function."""

    def test_run_with_default_config(self, tmp_path):
        """run_leakage_audit should work with defaults."""
        # Create minimal structure
        (tmp_path / "llm").mkdir()
        (tmp_path / "signals").mkdir()
        (tmp_path / "llm" / "prompts").mkdir()

        result = run_leakage_audit(
            codebase_path=str(tmp_path),
            prompts_path=str(tmp_path / "llm" / "prompts"),
        )

        assert result is not None
        assert isinstance(result.passed, bool)

    def test_run_with_custom_config(self, tmp_path):
        """run_leakage_audit should accept custom config."""
        (tmp_path / "custom").mkdir()
        (tmp_path / "custom" / "test.py").write_text("exit_price = 100")

        config = LeakageAuditConfig(
            include_roots=["custom/"],
            allowlist_file_globs=[],
        )

        result = run_leakage_audit(
            codebase_path=str(tmp_path),
            config=config,
        )

        assert result.total_files_scanned >= 1  # At least the test.py file
        assert result.critical_count > 0  # exit_price not allowlisted


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_codebase(self, tmp_path):
        """Should handle empty codebase gracefully."""
        auditor = LeakageAuditor()
        result = auditor.full_audit(tmp_path)

        assert result.total_files_scanned == 0
        assert result.passed

    def test_nonexistent_include_root(self, tmp_path):
        """Should handle nonexistent include roots gracefully."""
        config = LeakageAuditConfig(
            include_roots=["nonexistent/"],
        )

        auditor = LeakageAuditor(config=config)
        result = auditor.full_audit(tmp_path)

        assert result.total_files_scanned == 0
        assert result.passed

    def test_malformed_python_file(self, tmp_path):
        """Should handle malformed Python files gracefully."""
        (tmp_path / "llm").mkdir()
        (tmp_path / "llm" / "bad.py").write_text("def broken(:\n    pass")

        config = LeakageAuditConfig(include_roots=["llm/"])
        auditor = LeakageAuditor(config=config)
        result = auditor.full_audit(tmp_path)

        # Should not crash
        assert result is not None
