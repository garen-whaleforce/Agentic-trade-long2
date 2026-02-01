# Engineering Roadmap — P0→P1 工程版落地清單

> 本文件定義工程版的「完成狀態」與具體實作清單。
>
> **原則**：先把 P0 做完（輸入/輸出/追蹤固定），再做 LLM/Prompt 選型。

---

## 一、工程版「完成定義」（硬狀態）

工程版不是「功能看起來有」，而是必須同時滿足：

### 1. 可執行閉環

| 階段 | 要求 |
|------|------|
| **analyze** | 事件→pack→LLM→gate→signal 能跑 |
| **backtest** | signals→Whaleforce API→metrics 能跑 |
| **paper** | daily job→order/position ledger→T+1/T+30 close 執行能跑（可先 fail-closed，不可瞎填價格） |

### 2. 可稽核 / 可回放（SSOT artifacts）

每筆 trade（或 no-trade）都能追溯：

- `transcript pack`（pack_hash）
- `prompt`（prompt_id/version 或 template_id + prompt_hash）
- `LLMRequest/LLMResponse` raw（含 token/cost/latency）
- `deterministic gate decision`（含原因）
- `backtest_id`（若回測）

### 3. 不偷看 / 不瞎猜 / 不過擬合（硬 gate 保障）

- leakage audit 不誤殺結果欄位，但能抓住「拿 outcome 當特徵」
- frozen period 任何 config 漂移必 fail-closed
- walk-forward 分段不跨期持有（final 不吃 2026 價格）

---

## 二、P0 必修優化（6 項）

### P0-1：Leakage Audit 誤殺問題

**現象**：`exit_price/entry_price/return_pct/timedelta(30)` 被掃描當作弊，導致 gate 假 fail。

**正解**：掃描聚焦「會產 signal 的路徑」，並 allowlist「結果/成交 schema」。

**要改什麼**：

調整 `guardrails/leakage_auditor.py`：

```python
# Scan roots（只掃這些）
SCAN_ROOTS = [
    "backend/llm/",
    "backend/signals/",
    "backend/api/routes/analyze.py",
    "backend/backtest/full_backtest_runner.py",
    "backend/papertrading/runner.py",
]

# Allowlist（這些檔案可以出現 exit_price 等）
ALLOWLIST_FILES = [
    "services/whaleforce_backtest_client.py",
    "api/routes/backtest.py",
    "papertrading/order_book.py",
]
```

**Rule refinement**：不要用 "看到 exit_price 就判作弊"，而是抓：
- 在 signal 生成路徑中出現 `T+30 price` 類語句
- 或引用 `backtest_result` / `trades` 欄位來決策

**對應 Gate**：

| Gate | 說明 |
|------|------|
| `make leakage` | 必須掃得到檔案、且能抓到故意放進 prompt 的 forbidden 字串 |
| `tests/guardrails/test_leakage_audit_scopes.py` | 合法不報、非法必報 |

---

### P0-2：Backtest/Paper 必須把 LLMRequest/LLMResponse 當 SSOT

**現象**：runner 仍用 `.analyze()` 回 dict，artifacts 記不全。

**正解**：所有會產生 signal 的路徑**一律改用 `ScoreOnlyRunner.run()`** 並落地完整 artifacts。

**要改什麼**：

```python
# backtest/full_backtest_runner.py
# 改前
analysis = await analyzer.analyze(...)

# 改後
(req, resp) = await analyzer.run(event_id, pack, ...)
score_output = resp.parsed_output
artifact_logger.log_llm_request(req.model_dump())
artifact_logger.log_llm_response(resp.model_dump())
```

**影響檔案**：
- `backtest/full_backtest_runner.py`
- `papertrading/runner.py`
- `signals/generator.py`
- `signals/artifact_logger.py`

**對應 Gate**：

| Gate | 說明 |
|------|------|
| `make validate-runs` | 升級成 schema 驗證 |
| `tests/artifacts/test_llm_request_response_schema.py` | 驗證 schema 完整性 |
| `tests/integration/test_backtest_runner_artifacts_smoke.py` | 可用 mock litellm |

---

### P0-3：Prompt SSOT 統一

**現象**：prompt 命名存在多套（`batch_score_v1.md`、`v1.0.0`），容易 fallback 到錯 prompt。

**正解**：prompt 的身份用**不可偽造的 prompt_hash** 做凍結條件。

**目錄結構**：

```
backend/llm/prompts/
├── batch_score/
│   ├── v1.0.0.md
│   └── v1.1.0.md
└── full_audit/
    └── v1.0.0.md
```

**PromptRegistry 介面**：

```python
class PromptRegistry:
    def get(self, prompt_id: str, version: str) -> PromptInfo:
        """
        Returns:
            system_prompt: str
            user_template: str
            prompt_hash: str = sha256(system + user)
        """
```

**FreezePolicy 凍結欄位**：

```yaml
freeze:
  prompt_id: batch_score
  prompt_version: v1.0.0
  prompt_hash: abc123...  # 必填！
```

**對應 Gate**：

| Gate | 說明 |
|------|------|
| `tests/llm/test_prompt_hash_stability.py` | 同 prompt 重跑→hash 不變；改 1 字→hash 必變 |
| `make gate-v20` | freeze manifest 必須包含 prompt_hash |

---

### P0-4：JSON 強制模式要真的生效

**現象**：`response_format` 命名不一致導致 litellm JSON mode 永遠沒開。

**正解**：規範化 `LLMConfig.response_format`，runner 依 provider 能力真正送出 JSON mode。

**要改什麼**：

```python
# LLMConfig
response_format: Literal["json", "text"] = "json"

# ScoreOnlyRunner
if config.response_format == "json":
    # 對支援的 provider
    response_format = {"type": "json_object"}
else:
    # 不支援的 provider：加 robust JSON extractor
    output = extract_first_json(raw_output)
```

**對應 Gate**：

| Gate | 說明 |
|------|------|
| `tests/llm/test_json_mode_param.py` | monkeypatch litellm 驗證參數 |
| `tests/llm/test_json_extractor.py` | 混入前後綴文字仍能抽出 JSON |

---

### P0-5：Paper Trading 必須 Fail-Closed

**現象**：order_book 有 `event_date=entry_date # Approximate`、沒有 market data 也可能 close。

**正解**：paper trading 在沒有 close price SSOT 時，**只能停在 pending**。

**要改什麼**：

```python
# order_book.py
def open_position(self, ...):
    # event_date 必須是 T day（earnings call publish date）
    assert event_date == earnings_call_date, "event_date must be T day"
    # metadata 必須由 runner 傳入
    assert model is not None
    assert prompt_version is not None
    assert run_id is not None

def close_due_positions(self, ...):
    # 沒有 exit_price → 不得 mark exited
    if exit_price is None:
        position.status = "exit_pending_no_price"
        return  # fail-closed
```

**對應 Gate**：

| Gate | 說明 |
|------|------|
| `tests/paper/test_orderbook_event_date.py` | event_date 必須正確 |
| `tests/paper/test_fail_closed_no_price.py` | 無價格時不產生假 fill |
| `make paper_dryrun_10days` | 模擬無價格時 fail-closed |

---

### P0-6：Docs/Skills 與實際 CLI/工具入口必須一致

**現象**：RUNBOOK/skills 指向不存在的 module/命令。

**正解**：新增 `backend/tools/` package（真正可執行的入口）。

**目錄結構**：

```
backend/tools/
├── __init__.py
├── validate_run.py      # python -m backend.tools.validate_run <run_id>
├── leakage_check.py     # python -m backend.tools.leakage_check
├── consistency_check.py # python -m backend.tools.consistency_check <run_id> --k=5
└── cost_report.py       # python -m backend.tools.cost_report <run_id>
```

**Makefile 更新**：

```makefile
leakage:
	python -m backend.tools.leakage_check

validate-run:
	python -m backend.tools.validate_run $(RUN_ID)

runbook-smoke:
	python -m backend.tools.leakage_check --smoke
	python -m backend.tools.validate_run --smoke
```

**對應 Gate**：

| Gate | 說明 |
|------|------|
| `make runbook-smoke` | 跑 3 個最重要的命令，任何 ImportError 直接 fail |

---

## 三、P1 強化優化（3 項）

### P1-1：Evidence Quote 必須存在於 Pack（防 Hallucination）

- `pack_builder` 輸出 `source_map`
- `EvidenceQuoteVerifier` 做 fuzzy match（lower/strip/punct tolerant）
- 不存在 → NO_TRADE + violation 記錄

**Gate**：`tests/guardrails/test_evidence_quote_must_exist.py`

---

### P1-2：跨期持有防漏看（Final 不得吃 2026 價格）

- 在產 signals 前 filter：`exit_date <= period_end`
- 最好在 dataset manifest 就剔除尾端事件

**Gate**：`tests/backtest/test_exclude_cross_period_holds.py`

---

### P1-3：成本表單一來源

- `config/model_pricing.yaml`（或由 litellm 計費注入）
- run_config 記錄 `pricing_version/hash`

**Gate**：`tests/eval/test_pricing_single_source.py`

---

## 四、Sprint 計劃

### Sprint 0：P0 必修（可稽核可回放）

| PR | 內容 | Gate |
|----|------|------|
| PR1 | Leakage auditor scope/allowlist + tests | `make leakage` |
| PR2 | Prompt SSOT + prompt_hash + registry | `test_prompt_hash_stability` |
| PR3 | JSON mode + extractor + tests | `test_json_mode_param` |
| PR4 | BacktestRunner/PaperRunner 改用 `.run()` + artifacts | `make validate-runs` |
| PR5 | Paper fail-closed + event_date 正確 | `test_fail_closed_no_price` |
| PR6 | tools/CLI 補齊 + runbook-smoke | `make runbook-smoke` |

**Exit Criteria**：
- `make leakage` 真掃得到且能抓到故意違規
- 跑一次 S0 replay：`validate_run` PASS

---

### Sprint 1：LLM 選型 + Prompt 優化

- 固定 S1 Golden20 / S2 Smoke200 manifests
- K=5 consistency（只對候選事件或臨界分）
- scoreboard（quality = consistency > cost > latency）

**Exit Criteria**：
- winner pipeline：Golden20 K=5 不翻單
- 平均成本 < $0.01/event

---

### Sprint 2：Walk-Forward 回測 + Freeze

| 階段 | 期間 | 用途 |
|------|------|------|
| Tune | 2017-2021 | 低自由度調參 |
| Validate | 2022-2023 | 不調參驗證 |
| Final | 2024-2025 | 一次跑 + lock |

**產出**：freeze manifest（prompt_hash + model routing hash + thresholds）

---

## 五、PR 對應表

| PR | 改動檔案 | 新增測試 | Make Target |
|----|----------|----------|-------------|
| PR1 | `guardrails/leakage_auditor.py` | `test_leakage_audit_scopes.py` | `make leakage` |
| PR2 | `llm/prompt_registry.py`, `llm/prompts/` | `test_prompt_hash_stability.py` | - |
| PR3 | `llm/score_only_runner.py`, `llm/json_extractor.py` | `test_json_mode_param.py`, `test_json_extractor.py` | - |
| PR4 | `backtest/full_backtest_runner.py`, `papertrading/runner.py`, `signals/artifact_logger.py` | `test_llm_request_response_schema.py`, `test_backtest_runner_artifacts_smoke.py` | `make validate-runs` |
| PR5 | `papertrading/order_book.py`, `papertrading/runner.py` | `test_orderbook_event_date.py`, `test_fail_closed_no_price.py` | `make paper_dryrun_10days` |
| PR6 | `tools/*.py`, `Makefile`, `docs/RUNBOOK.md` | - | `make runbook-smoke` |

---

## 六、Gate 總表

```makefile
# Makefile - gate-all target
gate-all: leakage validate-runs runbook-smoke test
	@echo "All gates passed!"

leakage:
	python -m backend.tools.leakage_check

validate-runs:
	python -m backend.tools.validate_run --smoke

runbook-smoke:
	python -m backend.tools.leakage_check --smoke
	python -m backend.tools.validate_run --smoke
	python -m backend.tools.consistency_check --smoke
```
