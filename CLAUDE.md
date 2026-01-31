# CLAUDE.md — Rocket Screener Agentic (Rewrite)

## 0) 絕對規則（Hard Rules）

1. **Skills-first**：任何非 trivial 變更前，必先閱讀 `.claude/skills/` 對應規範並照做。
2. **禁止瞎猜**：不得虛構 API、DB schema、檔案、回測結果、模型價格/表現。
3. **禁止偷看/禁止 leakage**：
   - 分析只能使用 <= T day 可得資料（earnings call 發佈日）。
   - 不得使用任何 future outcome（例如 T+30 價格）來調參或寫 prompt。
4. **禁止過擬合**：
   - 必須 walk-forward：2017–2021 tune；2022–2023 validate；2024–2025 final test。
   - final test 一旦跑完，不得用其結果改 threshold/prompt/model。
5. **Backtest SSOT**：
   - 所有 CAGR/Sharpe/win rate 只能來自 Whaleforce Backtest API。
   - 不准用本地自算績效來宣稱結果。

## 1) 策略定義（不可任意改）

- **Event day**: earnings call publish date = **T day**
- **Entry**: buy at **T+1 trading day close**
- **Exit**: sell at **T+30 trading day close**
- **Long only** (no short)
- **Win rate constraint**: P(T+30 close > T+1 close) >= 75%
- **Objectives (2017–2025)**:
  - CAGR > 35% (higher is better)
  - Sharpe > 2
  - Trades/year target ~100, but priority: **CAGR = Sharpe > trade count**

## 2) 2026-01-01 起 Paper Trading（Freeze Policy）

- 2026-01-01 and later are forward/paper-trading regime.
- Model routing + prompt version + thresholds must be **frozen**.
- Any change requires:
  - new version tag
  - full walk-forward rerun
  - explicit decision record in `docs/decisions/`

## 3) LLM 系統規範（品質/一致性優先）

- Default: `temperature=0`, structured JSON output.
- **Two-stage pipeline**:
  - `batch_score`: cheap + short output (cost target < $0.01 / event)
  - `full_audit`: only for high-score candidates or UI on-demand
- **Deterministic trade decision**:
  - `trade_long` is a deterministic gate from score + evidence + red flags
- **Consistency requirement**:
  - K=5 runs must not flip trade decision
  - If inconsistent: fallback or abstain (NO_TRADE)

## 4) 記錄與可追蹤性（必做）

- Every run must write artifacts:
  - `run_config.json` (models, prompt_version, thresholds, date range)
  - `signals.csv` / `trades.csv`
  - `backtest_request.json` + `backtest_result.json`
  - `llm_requests/` (prompt template id + rendered prompt hash)
  - `llm_responses/` (raw JSON)
- **No artifact => run is invalid.**

## 5) Claude Code Buddy (Optional but Recommended)

- If developer installs CCB MCP:
  - use `buddy-do` for structured tasks
  - use `buddy-remember` to recall decisions and previous resolutions
- NOTE: CCB is AGPL; do not embed/ship CCB code as part of product service.

## 6) 專案結構

```
/
├── CLAUDE.md                    # 本文件
├── .claude/
│   └── skills/                  # Claude skills 定義
├── backend/                     # FastAPI 後端
│   ├── api/                     # API endpoints
│   ├── core/                    # 核心邏輯（trading calendar, etc）
│   ├── data/                    # 資料取得與快取
│   ├── llm/                     # LLM 分析模組
│   ├── signals/                 # 交易訊號產生
│   ├── services/                # 外部服務整合
│   ├── backtest/                # 回測模組
│   ├── schemas/                 # Pydantic schemas
│   ├── guardrails/              # 規則引擎
│   ├── eval/                    # 模型評估
│   ├── research/                # 研究工具
│   └── papertrading/            # Paper trading
├── frontend/                    # Next.js 前端
├── runs/                        # 執行記錄（每個 run_id 一個目錄）
├── docs/
│   ├── decisions/               # ADR 決策記錄
│   └── RUNBOOK.md               # 操作手冊
└── tests/                       # 測試
```

## 7) 開發命令

```bash
# 後端
cd backend && pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 前端
cd frontend && npm install
npm run dev

# 測試
pytest tests/

# 回測
python -m backend.backtest.run_backtest --start 2017-01-01 --end 2025-12-31
```

## 8) 環境變數

見 `.env.example`，必須設定：
- `EARNINGSCALL_API_KEY`
- `WHALEFORCE_BACKTEST_API_KEY`
- `LITELLM_API_KEY`
- `DATABASE_URL`

## 9) Skills 清單

| Skill ID | 用途 |
|----------|------|
| `no-lookahead-guardrails` | 防止資料洩漏 |
| `backtest-ssot-whaleforce` | 回測唯一來源 |
| `run-artifacts-ledger` | 執行記錄規範 |
| `evidence-triangulation` | 證據三角驗證 |
| `earningcall-api-integration` | Earnings Call API 整合 |
| `whaleforce-backtest-api-integration` | 回測 API 整合 |
| `frontend-analysis-ui` | 前端 UI 規範 |
| `llm-routing-and-budget` | LLM 路由與預算 |
| `model-selection-harness` | 模型選擇測試 |
| `prompt-regression-suite` | Prompt 回歸測試 |
