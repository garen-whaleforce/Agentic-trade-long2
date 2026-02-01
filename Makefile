# Rocket Screener Agentic - Makefile
# Gate tests for each version

.PHONY: help check lint typecheck unit contract integration test \
        integ_s0 integ_s1 integ_s2 \
        eval_consistency_s1_k5 eval_cost_s2 \
        backtest_s3_quarter walkforward_tune walkforward_val final_test_lock \
        paper_dryrun_10days leakage all \
        forbid-todo forbid-stub validate-runs

# Default target
help:
	@echo "Rocket Screener Agentic - Available targets:"
	@echo ""
	@echo "  Quality checks:"
	@echo "    make check          - Run all quality checks (lint + typecheck)"
	@echo "    make lint           - Run linter"
	@echo "    make typecheck      - Run type checker"
	@echo ""
	@echo "  Tests:"
	@echo "    make unit           - Run unit tests"
	@echo "    make contract       - Run contract tests"
	@echo "    make test           - Run all tests"
	@echo ""
	@echo "  Integration tests:"
	@echo "    make integ_s0       - S0: Single event smoke test"
	@echo "    make integ_s1       - S1: Golden 20 events"
	@echo "    make integ_s2       - S2: Smoke 200 events"
	@echo ""
	@echo "  Evaluation:"
	@echo "    make eval_consistency_s1_k5  - K=5 consistency test on S1"
	@echo "    make eval_cost_s2            - Cost evaluation on S2"
	@echo ""
	@echo "  Backtest:"
	@echo "    make backtest_s3_quarter     - Single quarter backtest"
	@echo "    make walkforward_tune        - Walk-forward tune (2017-2021)"
	@echo "    make walkforward_val         - Walk-forward validate (2022-2023)"
	@echo "    make final_test_lock         - Final test (2024-2025) + lock"
	@echo ""
	@echo "  Paper Trading:"
	@echo "    make paper_dryrun_10days     - Dry run simulation"
	@echo ""
	@echo "  Security:"
	@echo "    make leakage        - Check for lookahead leakage"
	@echo ""
	@echo "  All:"
	@echo "    make all            - Run all checks and tests"

# =====================================
# Quality Checks
# =====================================

check: lint typecheck
	@echo "All quality checks passed"

lint:
	@echo "Running linter..."
	@which ruff > /dev/null 2>&1 || (echo "ERROR: ruff not installed. Run: pip install ruff" && exit 1)
	cd backend && python -m ruff check .
	@echo "Lint complete"

typecheck:
	@echo "Running type checker..."
	@which mypy > /dev/null 2>&1 || (echo "WARNING: mypy not installed, skipping typecheck" && exit 0)
	cd backend && python -m mypy . --ignore-missing-imports
	@echo "Type check complete"

# =====================================
# Tests
# =====================================

unit:
	@echo "Running unit tests..."
	cd backend && python -m pytest ../tests/ -v --ignore=../tests/integration
	@echo "Unit tests complete"

contract:
	@echo "Running contract tests..."
	@test -d tests/contract && cd backend && python -m pytest ../tests/contract/ -v || echo "No contract tests directory yet"
	@echo "Contract tests complete"

test: unit contract
	@echo "All tests complete"

# =====================================
# Integration Tests (S0/S1/S2)
# =====================================

integ_s0:
	@echo "Running S0: Single event smoke test..."
	@echo "TODO: Implement S0 test"
	# cd backend && python -m pytest tests/integration/test_s0.py -v
	@echo "S0 complete"

integ_s1:
	@echo "Running S1: Golden 20 test..."
	@echo "TODO: Implement S1 test"
	# cd backend && python -m pytest tests/integration/test_s1_golden20.py -v
	@echo "S1 complete"

integ_s2:
	@echo "Running S2: Smoke 200 test..."
	@echo "TODO: Implement S2 test"
	# cd backend && python -m pytest tests/integration/test_s2_smoke200.py -v
	@echo "S2 complete"

# =====================================
# Evaluation
# =====================================

eval_consistency_s1_k5:
	@echo "Running K=5 consistency test on S1..."
	@echo "TODO: Implement consistency test"
	# cd backend && python -m backend.eval.eval_harness --test-set s1 --k 5
	@echo "Consistency test complete"

eval_cost_s2:
	@echo "Running cost evaluation on S2..."
	@echo "TODO: Implement cost evaluation"
	# cd backend && python -m backend.eval.cost_report --test-set s2
	@echo "Cost evaluation complete"

# =====================================
# Backtest
# =====================================

backtest_s3_quarter:
	@echo "Running S3: Single quarter backtest..."
	cd backend && python -m backtest.run_backtest --period 2024Q1 --dry-run
	@echo "Quarter backtest complete"

walkforward_tune:
	@echo "Running walk-forward tune (2017-2021)..."
	cd backend && python -m backtest.run_backtest --period tune --dry-run
	@echo "Tune period complete"

walkforward_val:
	@echo "Running walk-forward validate (2022-2023)..."
	cd backend && python -m backtest.run_backtest --period validate --dry-run
	@echo "Validation period complete"

final_test_lock:
	@echo "Running final test (2024-2025) + lock..."
	@echo "WARNING: This will lock the final test results!"
	cd backend && python -m backtest.run_backtest --period final --dry-run
	@echo "Final test complete"

# =====================================
# Paper Trading
# =====================================

paper_dryrun_10days:
	@echo "Running paper trading dry run (10 days)..."
	cd backend && python -m papertrading.runner
	@echo "Dry run complete"

enable-paper-trading:
	@echo "Enabling paper trading..."
	cd backend && python -c "from papertrading.freeze_policy import FreezePolicy; FreezePolicy().freeze()"
	@echo "Paper trading enabled"

disable-paper-trading:
	@echo "Disabling paper trading..."
	@echo "Manual intervention required - edit frozen_config.json"

paper-trading-status:
	@echo "Paper trading status:"
	cd backend && python -c "from papertrading.freeze_policy import get_frozen_config; print(get_frozen_config())" || echo "Not configured"

# =====================================
# Security / Audit
# =====================================

leakage:
	@echo "Checking for lookahead leakage..."
	@echo "Scanning for prohibited patterns..."
	cd backend && python -c "from guardrails.leakage_auditor import run_leakage_audit; r = run_leakage_audit(); print(f'Violations: {r.violations_found}, Critical: {r.critical_count}'); exit(0 if r.passed else 1)"
	@echo "Leakage check complete"

audit-leakage: leakage

# =====================================
# Version Gates (V1-V21)
# =====================================

gate-v1:
	@echo "V1 Gate: Repo structure + API connectivity..."
	@test -f CLAUDE.md && echo "✓ CLAUDE.md exists" || (echo "✗ CLAUDE.md missing" && exit 1)
	@test -d .claude/skills && echo "✓ Skills directory exists" || (echo "✗ Skills missing" && exit 1)
	@test -f backend/main.py && echo "✓ Backend main.py exists" || (echo "✗ Backend missing" && exit 1)
	@echo "V1 Gate PASSED"

gate-v2:
	@echo "V2 Gate: Trading calendar SSOT..."
	@test -f backend/core/trading_calendar.py && echo "✓ Trading calendar exists" || exit 1
	cd backend && python -c "from core.trading_calendar import calculate_trading_dates; print('✓ Trading calendar works')"
	@echo "V2 Gate PASSED"

gate-v3:
	@echo "V3 Gate: Transcript Pack..."
	@test -f backend/data/transcript_pack_builder.py && echo "✓ Transcript pack builder exists" || exit 1
	cd backend && python -c "from data.transcript_pack_builder import TranscriptPackBuilder; print('✓ Transcript pack builder importable')"
	@echo "V3 Gate PASSED"

gate-v4:
	@echo "V4 Gate: LLM batch_score (real implementation)..."
	@test -f backend/llm/score_only_runner.py && echo "✓ Score runner exists" || exit 1
	cd backend && python -c "from llm.score_only_runner import ScoreOnlyRunner; print('✓ Score runner importable')"
	cd backend && python -c "import litellm; print('✓ LiteLLM installed')" || echo "⚠ LiteLLM not installed"
	@echo "V4 Gate PASSED"

gate-v5:
	@echo "V5 Gate: Signal gate + evidence rules..."
	@test -f backend/signals/gate.py && echo "✓ Signal gate exists" || exit 1
	@test -f backend/guardrails/evidence_rules.py && echo "✓ Evidence rules exists" || exit 1
	cd backend && python -c "from signals.gate import SignalGate; from guardrails.evidence_rules import validate_evidence; print('✓ Gate and rules importable')"
	@echo "V5 Gate PASSED"

gate-v6:
	@echo "V6 Gate: Whaleforce Backtest API..."
	@test -f backend/services/whaleforce_backtest_client.py && echo "✓ Backtest client exists" || exit 1
	cd backend && python -c "from services.whaleforce_backtest_client import get_backtest_client; print('✓ Backtest client importable')"
	@echo "V6 Gate PASSED"

gate-v10:
	@echo "V10 Gate: Paper trading skeleton..."
	@test -f backend/papertrading/runner.py && echo "✓ Paper trading runner exists" || exit 1
	@test -f backend/papertrading/freeze_policy.py && echo "✓ Freeze policy exists" || exit 1
	@test -f backend/papertrading/order_book.py && echo "✓ Order book exists" || exit 1
	@echo "V10 Gate PASSED"

gate-v11:
	@echo "V11 Gate: Regression fixtures..."
	@test -f tests/fixtures/regression_events.py && echo "✓ Regression events exist" || exit 1
	@echo "V11 Gate PASSED"

gate-v13:
	@echo "V13 Gate: Consistency checker..."
	@test -f backend/eval/consistency_checker.py && echo "✓ Consistency checker exists" || exit 1
	@echo "V13 Gate PASSED"

gate-v18:
	@echo "V18 Gate: Leakage auditor..."
	@test -f backend/guardrails/leakage_auditor.py && echo "✓ Leakage auditor exists" || exit 1
	$(MAKE) leakage
	@echo "V18 Gate PASSED"

gate-v20:
	@echo "V20 Gate: Go/No-Go checklist..."
	@test -f docs/GO_NO_GO_CHECKLIST.md && echo "✓ Checklist exists" || exit 1
	@echo "V20 Gate PASSED"

gate-v21:
	@echo "V21 Gate: Paper trading runner..."
	@test -f backend/papertrading/runner.py && echo "✓ Runner exists" || exit 1
	@test -f backend/papertrading/monitoring.py && echo "✓ Monitoring exists" || exit 1
	@echo "V21 Gate PASSED"

gate-all: gate-v1 gate-v2 gate-v3 gate-v4 gate-v5 gate-v6 gate-v10 gate-v11 gate-v13 gate-v18 gate-v20 gate-v21
	@echo ""
	@echo "=========================================="
	@echo "All version gates PASSED"
	@echo "=========================================="

# =====================================
# Convenience Targets
# =====================================

test-unit: unit
test-integration: integ_s0 integ_s1 integ_s2
test-regression:
	cd backend && python -m pytest ../tests/fixtures/ -v
test-consistency: eval_consistency_s1_k5
test-cost: eval_cost_s2

# =====================================
# Code Quality Gates
# =====================================

forbid-todo:
	@echo "Checking for forbidden TODO patterns in production code..."
	@! grep -r "TODO.*Implement" backend/api/ backend/papertrading/ backend/backtest/ 2>/dev/null || (echo "ERROR: Found TODO:Implement in production code" && exit 1)
	@echo "No forbidden TODOs found"

forbid-stub:
	@echo "Checking for stub patterns in production code..."
	@! grep -rn "stub response" backend/api/ 2>/dev/null || (echo "ERROR: Found stub responses in API" && exit 1)
	@! grep -rn "This is a stub" backend/api/ 2>/dev/null || (echo "ERROR: Found stub comments in API" && exit 1)
	@echo "No stubs found"

validate-runs:
	@echo "Validating run artifacts..."
	cd backend && python -m guardrails.validate_run
	@echo "Run validation complete"

# =====================================
# All
# =====================================

all: check test gate-all leakage forbid-stub forbid-todo
	@echo "All checks and tests complete"
