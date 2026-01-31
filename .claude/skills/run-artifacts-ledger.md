# Skill: run-artifacts-ledger

## 目的
規範每次執行（run）必須產出的 artifacts，確保完整可追蹤性。

## 何時使用
- 批量分析執行
- 回測執行
- 模型評估
- Paper trading 執行

## 規則

### 1. Run ID 命名
```
run_<timestamp>_<purpose>
例如：run_20260131_153022_backtest_2017_2025
```

### 2. 必備 Artifacts（缺一不可）

```
runs/<run_id>/
├── run_config.json          # 執行配置
├── signals.csv              # 產生的交易訊號
├── trades.csv               # 交易記錄（含 entry/exit）
├── backtest_request.json    # 送出的回測請求
├── backtest_result.json     # 回測 API 返回結果
├── llm_requests/            # LLM 請求記錄
│   ├── {event_id}_request.json
│   └── ...
├── llm_responses/           # LLM 回應記錄
│   ├── {event_id}_response.json
│   └── ...
├── summary.json             # 執行摘要
└── report.md                # 可讀報告
```

### 3. run_config.json 格式
```json
{
  "run_id": "run_20260131_153022_backtest_2017_2025",
  "timestamp": "2026-01-31T15:30:22Z",
  "purpose": "backtest",
  "date_range": {
    "start": "2017-01-01",
    "end": "2025-12-31"
  },
  "models": {
    "batch_score": "gpt-4o-mini",
    "full_audit": "gpt-5-mini"
  },
  "prompt_versions": {
    "batch_score": "v1.2.3",
    "full_audit": "v1.1.0"
  },
  "thresholds": {
    "score_threshold": 0.7,
    "evidence_min_count": 2
  },
  "git_commit": "abc123def",
  "frozen": false
}
```

### 4. signals.csv 格式
```csv
event_id,symbol,event_date,entry_date,exit_date,score,trade_long,confidence,evidence_count,model,prompt_version
evt_001,AAPL,2024-01-25,2024-01-26,2024-03-08,0.82,true,0.78,3,gpt-4o-mini,v1.2.3
evt_002,MSFT,2024-01-30,2024-01-31,2024-03-14,0.45,false,0.42,1,gpt-4o-mini,v1.2.3
```

### 5. LLM Request/Response 格式
```json
// llm_requests/{event_id}_request.json
{
  "event_id": "evt_001",
  "timestamp": "2026-01-31T15:31:00Z",
  "model": "gpt-4o-mini",
  "prompt_template_id": "batch_score_v1.2.3",
  "prompt_hash": "sha256:abc123...",
  "rendered_prompt": "...",
  "parameters": {
    "temperature": 0,
    "max_tokens": 500
  }
}

// llm_responses/{event_id}_response.json
{
  "event_id": "evt_001",
  "timestamp": "2026-01-31T15:31:05Z",
  "model": "gpt-4o-mini",
  "raw_response": {...},
  "parsed_output": {
    "score": 0.82,
    "trade_candidate": true,
    "evidence": [...]
  },
  "token_usage": {
    "input": 1200,
    "output": 150,
    "total": 1350
  },
  "cost_usd": 0.0027,
  "latency_ms": 1850
}
```

### 6. 驗證規則
- 所有必備檔案都必須存在
- JSON 必須可解析
- CSV 必須符合 schema
- 缺少任何 artifact => run 無效

## 產出 Artifacts
見上述目錄結構

## 驗收命令
```bash
# 驗證 run artifacts 完整性
python -m backend.tools.validate_run --run-id <run_id>
```

## ADR 決策記錄
任何策略/模型/prompt 改動必須寫入 `docs/decisions/ADR-xxxx.md`：
```markdown
# ADR-0001: 提高 score threshold 從 0.7 到 0.75

## 日期
2026-01-31

## 狀態
Accepted

## 背景
Walk-forward 驗證顯示 threshold 0.7 的 win rate 只有 72%，未達 75% 目標。

## 決策
將 score threshold 從 0.7 提高到 0.75。

## 影響
- 預期 win rate 提升到 76%
- 預期 trades/year 從 100 降到 85
- 需要重跑 2024-2025 final test

## 相關 Run
- Baseline: run_20260130_backtest_baseline
- New: run_20260131_backtest_threshold_075
```
