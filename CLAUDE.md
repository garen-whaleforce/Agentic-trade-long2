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

## 9) Skills 清單（本地 Skills）

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

---

## 10) 外部服務 Skills（~/.claude/skills/）

### 資料來源

#### PostgreSQL Database（股價、Earnings Call、公司資訊）

| Item | Value |
|------|-------|
| **Host** | `172.23.22.100` |
| **Port** | `5432` |
| **User** | `whaleforce` |
| **Password** | (empty string) |
| **Database** | `pead_reversal` |

**主要資料表**：

| 資料表 | 說明 | 資料範圍 |
|--------|------|----------|
| `historical_prices` | 股價 OHLCV | 2015-01 ~ today, 1,098,150 筆 |
| `companies` | 公司基本資料 | S&P 500, 504 家 |
| `earnings_surprises` | EPS Surprise | 2015 ~ today, 262,559 筆 |
| `transcript_content` | Earnings Call 逐字稿 | 2015 Q1 ~ today, 16,953 筆 |

```python
import psycopg2
import pandas as pd

conn = psycopg2.connect(
    host="172.23.22.100", port=5432,
    user="whaleforce", password="", database="pead_reversal"
)
df = pd.read_sql("SELECT * FROM historical_prices WHERE symbol='AAPL' LIMIT 10", conn)
```

#### MinIO Storage（13F 機構持股 + 資料儲存）

| Item | Value |
|------|-------|
| **API Endpoint** | `https://minio.api.gpu5090.whaleforce.dev` |
| **Web UI** | `https://minio.gpu5090.whaleforce.dev` |
| **Account** | `whaleforce` |
| **Password** | `whaleforce.ai` |
| **Default Bucket** | `13f` |
| **資料範圍** | 2020 ~ 2025, ~23 GB |

**可用 Bucket**：

| Bucket | 用途 |
|--------|------|
| `13f` | 13F 機構持股資料 |
| `rocket-screener` | 本專案回測結果、信號、artifacts |

```python
import boto3
from botocore.client import Config
import json

s3 = boto3.client(
    "s3",
    endpoint_url="https://minio.api.gpu5090.whaleforce.dev",
    aws_access_key_id="whaleforce",
    aws_secret_access_key="whaleforce.ai",
    config=Config(signature_version="s3v4"),
    verify=False
)

# ===== 讀取資料 =====

# List 13F files
response = s3.list_objects_v2(Bucket="13f", Prefix="2024/")
for obj in response.get("Contents", [])[:5]:
    print(obj['Key'])

# Download file to local
s3.download_file(Bucket="13f", Key="2024/0001067983/filing.json", Filename="local_filing.json")

# Read file to memory
response = s3.get_object(Bucket="13f", Key="2024/0001067983/filing.json")
content = json.loads(response["Body"].read())

# ===== 儲存資料 =====

# Upload JSON data
data = {"run_id": "abc123", "signals": [...], "metrics": {...}}
s3.put_object(
    Bucket="rocket-screener",
    Key="runs/2026-02-01/run_config.json",
    Body=json.dumps(data, indent=2),
    ContentType="application/json"
)

# Upload local file
s3.upload_file(
    Filename="local_signals.csv",
    Bucket="rocket-screener",
    Key="runs/2026-02-01/signals.csv"
)

# Upload DataFrame as CSV
import pandas as pd
from io import StringIO

df = pd.DataFrame({"symbol": ["AAPL", "MSFT"], "score": [0.85, 0.72]})
csv_buffer = StringIO()
df.to_csv(csv_buffer, index=False)
s3.put_object(
    Bucket="rocket-screener",
    Key="runs/2026-02-01/signals.csv",
    Body=csv_buffer.getvalue(),
    ContentType="text/csv"
)

# Upload DataFrame as Parquet
from io import BytesIO

parquet_buffer = BytesIO()
df.to_parquet(parquet_buffer, index=False)
s3.put_object(
    Bucket="rocket-screener",
    Key="runs/2026-02-01/signals.parquet",
    Body=parquet_buffer.getvalue(),
    ContentType="application/octet-stream"
)
```

**mc CLI 快速操作**：

```bash
# 設定 alias（一次性）
mc alias set wf https://minio.api.gpu5090.whaleforce.dev whaleforce whaleforce.ai

# 上傳檔案
mc cp local_file.json wf/rocket-screener/runs/2026-02-01/

# 上傳整個目錄
mc mirror ./runs/abc123/ wf/rocket-screener/runs/abc123/

# 下載檔案
mc cp wf/13f/2024/0001067983/filing.json ./

# 列出檔案
mc ls wf/rocket-screener/runs/

# 建立 bucket
mc mb wf/new-bucket-name
```

---

### LLM 服務

#### LiteLLM（統一 LLM 代理）

| Item | Value |
|------|-------|
| **Base URL** | `https://litellm.whaleforce.dev` |
| **API Key** | 聯繫管理員取得 |

**可用模型**：

| 模型 | Provider | 用途 |
|------|----------|------|
| `gpt-4o-mini` | Azure | 快速評分（batch_score） |
| `gpt-5` | Azure | 深度分析 |
| `o3` | Azure | 推理任務 |
| `claude-opus-4.5` | Open Router | 高品質分析 |

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-xxxxxxxx",
    base_url="https://litellm.whaleforce.dev"
)

resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "分析 AAPL 最新財報"}],
)
print(resp.choices[0].message.content)
```

---

### 回測服務

#### Backtester API（SSOT 績效計算）

| Item | Value |
|------|-------|
| **API URL** | `https://backtest.api.whaleforce.dev` |
| **Frontend** | `https://backtest.whaleforce.dev` |

**重要**：所有 CAGR、Sharpe、MDD 必須從此 API 取得，禁止自行計算！

```python
import requests

BASE_URL = "https://backtest.api.whaleforce.dev"

# 提交回測
response = requests.post(f"{BASE_URL}/backtest/run", json={
    "start_date": "2024-01-01T00:00:00Z",
    "end_date": "2024-12-31T00:00:00Z",
    "interval": "1d",
    "initial_capital": 100000,
    "base_currency": "USD",
    "strategy_name": "weighted_rebalance",
    "initial_portfolio": [
        {"ticker": "AAPL", "weight": 0.5},
        {"ticker": "MSFT", "weight": 0.5}
    ]
}, verify=False)

backtest_id = response.json()["backtest_id"]

# 取得結果
result = requests.get(f"{BASE_URL}/backtest/result/{backtest_id}", verify=False).json()
print(f"CAGR: {result['summary_metrics']['annualized_return_pct']:.2f}%")
print(f"Sharpe: {result['summary_metrics']['sharpe_ratio']:.2f}")
print(f"MDD: {result['summary_metrics']['max_drawdown_pct']:.2f}%")
```

---

### 迭代與 Review 服務

#### ChatGPT Pro API（深度分析與策略迭代）

| Item | Value |
|------|-------|
| **API URL** | `https://chatgpt-pro.gpu5090.whaleforce.dev` |
| **用途** | 策略迭代、深度 Review、複雜分析 |

```python
import requests

API_URL = "https://chatgpt-pro.gpu5090.whaleforce.dev"

# 提交分析任務
response = requests.post(f"{API_URL}/chat", json={
    "prompt": "Review 此策略的回測結果，找出潛在問題並建議改進方案",
    "project": "rocket-screener"
})
task_id = response.json()["task_id"]

# 等待結果（最多 60 秒）
result = requests.get(f"{API_URL}/task/{task_id}?wait=60").json()
if result["status"] == "completed":
    print(result["answer"])
```

---

### Earnings Call API

| Item | Value |
|------|-------|
| **API URL** | `https://earningcall.gpu5090.whaleforce.dev` |
| **API Docs** | `https://earningcall.gpu5090.whaleforce.dev/docs` |

```python
import requests

BASE_URL = "https://earningcall.gpu5090.whaleforce.dev"

# 取得逐字稿
resp = requests.get(f"{BASE_URL}/api/company/AAPL/transcript", params={
    "year": 2024, "quarter": 4, "level": 2
})
transcript = resp.json()
```

---

## 11) 資料流與服務對應

```
┌─────────────────────────────────────────────────────────────────┐
│                        資料來源（讀取）                           │
├─────────────────────────────────────────────────────────────────┤
│  PostgreSQL (172.23.22.100:5432)                                │
│  ├── historical_prices → 股價 OHLCV                             │
│  ├── companies → 公司基本資料                                    │
│  ├── earnings_surprises → EPS Surprise                          │
│  └── transcript_content → Earnings Call 逐字稿                  │
│                                                                 │
│  MinIO (minio.api.gpu5090.whaleforce.dev)                       │
│  └── 13f/ → 機構持股 13F 資料                                    │
│                                                                 │
│  Earnings Call API (earningcall.gpu5090.whaleforce.dev)         │
│  └── /api/company/{symbol}/transcript → 即時逐字稿               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        LLM 分析                                  │
├─────────────────────────────────────────────────────────────────┤
│  LiteLLM (litellm.whaleforce.dev)                               │
│  ├── batch_score (gpt-4o-mini) → 快速評分 < $0.01/event         │
│  └── full_audit (gpt-5) → 深度分析                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        回測驗證                                  │
├─────────────────────────────────────────────────────────────────┤
│  Backtester API (backtest.api.whaleforce.dev)                   │
│  └── SSOT: CAGR, Sharpe, MDD, Win Rate                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        策略迭代                                  │
├─────────────────────────────────────────────────────────────────┤
│  ChatGPT Pro API (chatgpt-pro.gpu5090.whaleforce.dev)           │
│  └── 深度 Review、策略改進建議、複雜分析                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        資料儲存（寫入）                           │
├─────────────────────────────────────────────────────────────────┤
│  MinIO (minio.api.gpu5090.whaleforce.dev)                       │
│  └── rocket-screener/                                           │
│      ├── runs/{run_id}/                                         │
│      │   ├── run_config.json    → 執行配置                       │
│      │   ├── signals.csv        → 交易信號                       │
│      │   ├── trades.csv         → 交易記錄                       │
│      │   ├── backtest_result.json → 回測結果                     │
│      │   └── llm_responses/     → LLM 回應記錄                   │
│      ├── models/                → 訓練好的模型                    │
│      └── artifacts/             → 其他產出物                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 12) 專案進度與決策記錄

### 記錄規則（Claude 必讀）

**何時記錄？**
- 完成重要功能或里程碑時
- 做出架構/設計決策時
- 變更 frozen parameters 時
- 發現重要問題或 bug 時

**如何記錄？**
1. 建立 ADR 文件：`docs/decisions/ADR-{編號}-{簡短標題}.md`
2. 更新下方進度表格（加在最上面）
3. Commit 並 push

**ADR 格式**：
```markdown
# ADR-XXX: 標題
## Status: PROPOSED / APPROVED / COMPLETED / SUPERSEDED
## Context: 為什麼需要這個決策
## Decision: 決定了什麼
## Consequences: 正面/負面影響
```

**如何查詢過去記錄？**
```bash
# 列出所有 ADR
ls docs/decisions/

# 搜尋特定關鍵字
grep -r "關鍵字" docs/decisions/

# 查看 git 歷史
git log --oneline docs/decisions/
```

### 進度摘要

| 日期 | 里程碑 | ADR |
|------|--------|-----|
| 2026-02-01 | 6-PR 工程路線圖完成（113 測試） | [ADR-002](docs/decisions/ADR-002-6pr-engineering-roadmap.md) |
| 2026-01-31 | Production Config Freeze | [ADR-001](docs/decisions/ADR-001-production-config-freeze.md) |

### 目前狀態

- **Paper Trading 基礎設施**：✅ 完成（PR1-6）
- **測試覆蓋**：113 個測試通過
- **CLI 可用**：`python -m backend.papertrading.cli --help`
