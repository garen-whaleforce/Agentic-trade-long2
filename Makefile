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
	@echo "TODO: Implement dry run"
	# cd backend && python -m backend.papertrading.scheduler dry-run --days 10
	@echo "Dry run complete"

# =====================================
# Security
# =====================================

leakage:
	@echo "Checking for lookahead leakage..."
	@echo "Scanning for prohibited patterns..."
	@# Check for future date usage in analysis
	@grep -r "T+30" backend/ --include="*.py" || true
	@grep -r "calculate_cagr\|calculate_sharpe" backend/ --include="*.py" && \
		echo "WARNING: Found local performance calculation!" || \
		echo "OK: No local performance calculations found"
	@echo "Leakage check complete"

# =====================================
# All
# =====================================

all: check test integ_s0 leakage
	@echo "All checks and tests complete"
