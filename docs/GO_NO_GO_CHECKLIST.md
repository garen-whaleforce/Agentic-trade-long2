# Go/No-Go Checklist for Paper Trading

## Overview
This checklist must be completed before enabling paper trading (2026-01-01+).
All items must be checked and approved before proceeding.

## 1. Walk-Forward Validation ✓

### Tune Period (2017-2021)
- [ ] Backtest completed with Whaleforce API
- [ ] CAGR > 35% achieved
- [ ] Sharpe > 2 achieved
- [ ] Win rate > 75% achieved
- [ ] Results logged to `runs/tune_YYYYMMDD_HHMMSS/`

### Validation Period (2022-2023)
- [ ] Backtest completed with Whaleforce API
- [ ] CAGR within 80% of tune period
- [ ] Sharpe within 80% of tune period
- [ ] No significant degradation pattern
- [ ] Results logged to `runs/validate_YYYYMMDD_HHMMSS/`

### Final Test Period (2024-2025)
- [ ] Backtest completed with Whaleforce API
- [ ] Results meet minimum thresholds
- [ ] NO parameter changes after this
- [ ] Results logged to `runs/final_YYYYMMDD_HHMMSS/`

## 2. Configuration Freeze ✓

- [ ] ADR-001 approved and signed
- [ ] Frozen parameters documented:
  - [ ] score_threshold
  - [ ] evidence_min_count
  - [ ] block_on_margin_concern
  - [ ] model routing
  - [ ] prompt version
- [ ] Configuration stored in `backend/papertrading/frozen_config.json`

## 3. Quality Checks ✓

### Consistency
- [ ] K=5 flip rate < 1%
- [ ] Consistency test passed on regression fixtures
- [ ] `make test-consistency` passes

### Cost
- [ ] Average cost per event < $0.01
- [ ] Cost optimizer configured
- [ ] `make test-cost` passes

### Leakage
- [ ] Leakage audit passed
- [ ] No critical violations
- [ ] `make audit-leakage` passes

## 4. Infrastructure ✓

### APIs
- [ ] Earnings Call API connected and tested
- [ ] Whaleforce Backtest API connected and tested
- [ ] LLM API (LiteLLM) connected and tested
- [ ] All API keys set in environment

### Monitoring
- [ ] Metrics collection enabled
- [ ] Alert manager configured
- [ ] Health checks registered
- [ ] Daily report generation tested

### Artifacts
- [ ] Artifact logging enabled
- [ ] Run directories created
- [ ] Report generation tested

## 5. Testing ✓

- [ ] `make test-unit` passes
- [ ] `make test-integration` passes
- [ ] `make test-regression` passes
- [ ] `make gate-v10` passes

## 6. Documentation ✓

- [ ] CLAUDE.md up to date
- [ ] RUNBOOK.md complete
- [ ] ADRs documented
- [ ] Skills documentation complete

## 7. Operational Readiness ✓

- [ ] On-call schedule defined
- [ ] Escalation path documented
- [ ] Rollback procedure tested
- [ ] Emergency stop mechanism tested

## 8. Final Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Tech Lead | | | |
| Data Scientist | | | |
| Ops | | | |

## Approval

- [ ] All items checked
- [ ] All stakeholders signed
- [ ] Paper trading approved to begin

---

## Post-Approval Actions

After approval, execute:

```bash
# Enable paper trading
make enable-paper-trading

# Verify status
make paper-trading-status
```

## Rollback

If issues are discovered:

```bash
# Disable paper trading
make disable-paper-trading

# Review logs
make review-paper-trading-logs
```
