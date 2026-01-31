# Rocket Screener Runbook

## Overview

This runbook covers operational procedures for the Rocket Screener paper trading system.

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Deployment](#deployment)
3. [Monitoring](#monitoring)
4. [Troubleshooting](#troubleshooting)
5. [Emergency Procedures](#emergency-procedures)
6. [Configuration Management](#configuration-management)

---

## Daily Operations

### Morning Routine (Before Market Open)

1. **Check system health**
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8000/health/services
   ```

2. **Verify freeze manifest**
   ```bash
   cat papertrading_freeze_manifest.json
   # Verify hash matches expected
   ```

3. **Check pending orders**
   ```bash
   python -m backend.papertrading.cli check-orders
   ```

### Daily Pipeline (After Market Close)

1. **Run daily job** (automated via cron/scheduler)
   ```bash
   python -m backend.papertrading.scheduler run-daily
   ```

2. **Review results**
   ```bash
   python -m backend.papertrading.cli daily-report --date TODAY
   ```

3. **Check for errors**
   ```bash
   tail -100 logs/papertrading.log | grep ERROR
   ```

### Weekly Review

1. **Generate performance report**
   ```bash
   python -m backend.papertrading.cli weekly-report
   ```

2. **Verify consistency**
   ```bash
   python -m backend.eval.consistency_check --k 5 --sample 20
   ```

3. **Check cost trends**
   ```bash
   python -m backend.tools.cost_report --period 7d
   ```

---

## Deployment

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 15+ (or SQLite for development)

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env
# Edit .env with your credentials
```

### Frontend Setup

```bash
cd frontend
npm install
```

### Start Services

```bash
# Backend
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm run dev
```

### Production Deployment

1. Set `ENVIRONMENT=production` in `.env`
2. Use gunicorn with uvicorn workers:
   ```bash
   gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
   ```
3. Use nginx as reverse proxy
4. Enable SSL/TLS

---

## Monitoring

### Key Metrics to Watch

| Metric | Normal Range | Alert Threshold |
|--------|--------------|-----------------|
| Daily job success rate | 100% | < 95% |
| LLM API latency (p95) | < 5s | > 10s |
| Cost per event | < $0.01 | > $0.02 |
| Schema validation rate | > 99% | < 95% |
| Paper win rate (30d) | > 70% | < 60% |

### Log Locations

- Backend logs: `logs/backend.log`
- Paper trading logs: `logs/papertrading.log`
- LLM request logs: `runs/*/llm_requests/`
- LLM response logs: `runs/*/llm_responses/`

### Health Check Endpoints

- `/health` - Basic health check
- `/health/services` - External service connectivity

---

## Troubleshooting

### Common Issues

#### 1. LLM API Timeout

**Symptoms**: Analysis jobs timing out, high latency

**Solution**:
```bash
# Check API status
curl -X POST https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"test"}]}'

# If API is down, switch to fallback model
# Edit .env: LLM_BATCH_SCORE_MODEL=claude-3-haiku
```

#### 2. Earnings Call API Errors

**Symptoms**: Empty calendar, missing transcripts

**Solution**:
```bash
# Check API connectivity
python -m backend.services.earningscall_client --test

# Clear cache and retry
rm -rf data/cache/earningscall/*
```

#### 3. Backtest API Failures

**Symptoms**: Backtest results not returning

**Solution**:
```bash
# Check API status
python -m backend.services.whaleforce_backtest_client --test

# Review request payload
cat runs/<run_id>/backtest_request.json
```

#### 4. Freeze Policy Violation

**Symptoms**: "Configuration mismatch in frozen period" error

**Solution**:
1. Do NOT change the configuration directly
2. If change is required:
   - Create ADR documenting the reason
   - Delete `papertrading_freeze_manifest.json`
   - Rerun full walk-forward validation
   - Create new freeze manifest

---

## Emergency Procedures

### Stop All Trading

```bash
# Immediate stop
python -m backend.papertrading.cli emergency-stop

# This will:
# 1. Cancel all pending orders
# 2. Disable the daily scheduler
# 3. Send alert notification
```

### Rollback to Previous Version

```bash
# Check current version
cat papertrading_freeze_manifest.json | jq .git_commit

# Rollback
git checkout <previous_commit>

# Restart services
systemctl restart rocket-screener-backend
```

### Data Recovery

```bash
# All run data is in runs/ directory
# Backtest results are in runs/*/backtest_result.json
# Orders are in papertrading/orders.json

# To replay a day:
python -m backend.papertrading.scheduler run-daily --date 2026-01-15 --dry-run
```

---

## Configuration Management

### Freeze Policy

After 2026-01-01, the following are FROZEN:

- Model routing (`batch_score_model`, `full_audit_model`)
- Prompt versions
- Score threshold
- Evidence minimum count
- Universe filter

**To change frozen configuration:**

1. Document reason in `docs/decisions/ADR-XXXX.md`
2. Delete `papertrading_freeze_manifest.json`
3. Rerun walk-forward:
   ```bash
   make walkforward_tune
   make walkforward_val
   make final_test_lock
   ```
4. Create new freeze manifest:
   ```bash
   python -m backend.papertrading.freeze_policy create-manifest
   ```
5. Get approval from team lead

### Environment Variables

See `.env.example` for all configuration options.

**Critical variables:**
- `OPENAI_API_KEY` - LLM access
- `EARNINGSCALL_API_KEY` - Data access
- `WHALEFORCE_BACKTEST_API_KEY` - Backtest access

---

## Contacts

- **On-call**: [Your team's on-call rotation]
- **Escalation**: [Manager/Lead contact]
- **External APIs**:
  - OpenAI support: support@openai.com
  - EarningsCall support: support@earningscall.com
  - Whaleforce support: support@whaleforce.com
