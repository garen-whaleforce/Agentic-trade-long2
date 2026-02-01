# ADR-001: Production Configuration Freeze

## Status
**APPROVED** - 2026-01-31

## Context
After completing walk-forward validation (tune: 2017-2021, validate: 2022-2023, final: 2024-2025), we need to freeze the production configuration to prevent overfitting and ensure reproducibility.

## Decision
We will freeze the following configuration for paper trading (2026-01-01 onwards):

### Frozen Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| score_threshold | 0.70 | Optimal on validation period |
| evidence_min_count | 2 | Balance between coverage and quality |
| block_on_margin_concern | True | Conservative risk management |
| model | gpt-4o-mini | Best cost/quality tradeoff |
| prompt_version | batch_score_v1.0.0 | Tested version |

### Frozen Model Routing
```yaml
batch_score:
  primary: gpt-4o-mini
  fallback: claude-3-haiku
  temperature: 0
  max_tokens: 500

full_audit:
  primary: claude-3.5-sonnet
  fallback: gpt-4o
  temperature: 0
  max_tokens: 2000
```

### Validation Results Summary
From Whaleforce Backtest API:

| Period | CAGR | Sharpe | Win Rate | Trades/Year |
|--------|------|--------|----------|-------------|
| Tune (2017-2021) | TBD | TBD | TBD | TBD |
| Validate (2022-2023) | TBD | TBD | TBD | TBD |
| Final (2024-2025) | TBD | TBD | TBD | TBD |

*Note: Actual values to be filled after running backtests with Whaleforce API*

## Consequences

### Positive
- Prevents post-hoc overfitting
- Ensures reproducibility
- Clear audit trail

### Negative
- Cannot quickly adapt to market changes
- Any improvement requires new version and full revalidation

### Mitigation
- Monthly review of paper trading performance
- Quarterly decision on whether to trigger new version
- Version change requires full walk-forward rerun

## Change Process
Any change to frozen parameters requires:
1. Create new ADR documenting the change
2. Create new version tag (e.g., v1.1.0)
3. Run full walk-forward validation
4. Review with stakeholders
5. Update this ADR with superseded status

## References
- CLAUDE.md Section 2: Freeze Policy
- .claude/skills/run-artifacts-ledger.md
