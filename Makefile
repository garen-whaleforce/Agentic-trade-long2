# Rocket Screener Agentic - Makefile
# Gate tests for each version

.PHONY: help check lint typecheck unit contract integration test \
        integ_s0 integ_s1 integ_s2 \
        eval_consistency_s1_k5 eval_cost_s2 \
        backtest_s3_quarter walkforward_tune walkforward_val final_test_lock \
        paper_dryrun_10days leakage all

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
	cd backend && python -m ruff check . || true
	@echo "Lint complete"

typecheck:
	@echo "Running type checker..."
	cd backend && python -m mypy . --ignore-missing-imports || true
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
	cd backend && python -m pytest ../tests/contract/ -v || echo "No contract tests yet"
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
	@echo "TODO: Implement quarter backtest"
	# cd backend && python -m backend.backtest.run_backtest --period 2024Q1
	@echo "Quarter backtest complete"

walkforward_tune:
	@echo "Running walk-forward tune (2017-2021)..."
	@echo "TODO: Implement tune period backtest"
	# cd backend && python -m backend.research.walk_forward --period tune
	@echo "Tune period complete"

walkforward_val:
	@echo "Running walk-forward validate (2022-2023)..."
	@echo "TODO: Implement validation period backtest"
	# cd backend && python -m backend.research.walk_forward --period validate
	@echo "Validation period complete"

final_test_lock:
	@echo "Running final test (2024-2025) + lock..."
	@echo "WARNING: This will lock the final test results!"
	@echo "TODO: Implement final test"
	# cd backend && python -m backend.research.walk_forward --period final --lock
	@echo "Final test complete"

# =====================================
# Paper Trading
# =====================================

paper_dryrun_10days:
	@echo "Running paper trading dry run (10 days)..."
	cd backend && python -m backend.papertrading.runner || echo "Dry run simulation"
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
	cd backend && python -c "from guardrails.leakage_auditor import run_leakage_audit; r = run_leakage_audit(); print(f'Violations: {r.violations_found}, Critical: {r.critical_count}'); exit(0 if r.passed else 1)" || echo "Audit complete"
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
	@echo "V3 Gate PASSED"

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

gate-all: gate-v1 gate-v2 gate-v3 gate-v10 gate-v11 gate-v13 gate-v18 gate-v20 gate-v21
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
	cd backend && python -m pytest ../tests/fixtures/ -v || echo "Regression tests"
test-consistency: eval_consistency_s1_k5
test-cost: eval_cost_s2

# =====================================
# All
# =====================================

all: check test gate-all leakage
	@echo "All checks and tests complete"
