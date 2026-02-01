# PR Checklist — P0 工程版落地

> 6 個 PR 的檔案級變更清單，按順序執行。
>
> **Merge 順序**：PR1 → PR2 → PR3 → PR4 → PR5 → PR6

---

## PR1 — Leakage Auditor 縮小掃描面 + Allowlist

### 目標
- `make leakage` 不再誤殺 `exit_price/entry_price/return_pct` 等結果欄位
- 但仍能抓到「在 signal 產生路徑使用未來資訊」的作弊模式

### 修改檔案

| 檔案 | 變更內容 |
|------|----------|
| `backend/guardrails/leakage_auditor.py` | 新增掃描設定（include_roots, exclude_globs, allowlist_file_globs, allowlist_regex）；修改 `full_audit()` 支援 config；新增 `_is_allowlisted()` helper |

### 新增檔案

| 檔案 | 說明 |
|------|------|
| `tests/guardrails/__init__.py` | Package init |
| `tests/guardrails/test_leakage_audit_scope_allowlist.py` | 測試：合法不報、非法必報 |
| `tests/guardrails/test_leakage_prompt_detection.py` | （可選）測試 prompt 內塞禁字 |

### 掃描設定

```python
# 只掃這些路徑（相對於 backend/）
SCAN_ROOTS = [
    "llm/",
    "signals/",
    "api/routes/analyze.py",
    "backtest/full_backtest_runner.py",
    "papertrading/runner.py",
]

# Allowlist（這些檔案可以出現 exit_price 等）
ALLOWLIST_FILES = [
    "services/whaleforce_backtest_client.py",
    "api/routes/backtest.py",
    "papertrading/order_book.py",
]
```

### Gate
- `make leakage`：必須能掃得到且抓到故意違規
- `tests/guardrails/test_leakage_audit_scope_allowlist.py`

### 依賴
無（可先做）

---

## PR2 — Prompt SSOT + prompt_hash 凍結

### 目標
- freeze 記 `prompt_hash`（system + user template hash），不只靠版本字串
- runtime validate 能抓到「版本字串沒變但 prompt 內容變了」

### 修改檔案

| 檔案 | 變更內容 |
|------|----------|
| `backend/llm/prompt_registry.py` | 加 `get_template_hash()`、`get_template_id()`；load 找不到時明確 fail |
| `backend/papertrading/freeze_policy.py` | FreezeManifest 加 `batch_score_prompt_id/hash`、`full_audit_prompt_id/hash`；`validate_runtime()` 驗 prompt_hash |
| `docs/decisions/ADR-001-production-config-freeze.md` | 更新：freeze 的 SSOT 是 prompt_hash |
| `docs/GO_NO_GO_CHECKLIST.md` | 增加勾選項 |

### 新增檔案

| 檔案 | 說明 |
|------|------|
| `tests/paper/test_freeze_manifest_includes_prompt_hash.py` | 斷言 `*_prompt_hash` 存在且非空 |
| `tests/paper/test_validate_runtime_checks_prompt_hash.py` | prompt_hash 改 1 字 → validate 必須 raise |
| `backend/llm/prompts/full_audit_v1.md` | 最小可解析 schema |

### FreezeManifest 擴充欄位

```python
class FreezeManifest(BaseModel):
    # 既有欄位...
    batch_score_prompt_id: str
    batch_score_prompt_hash: str
    full_audit_prompt_id: str
    full_audit_prompt_hash: str
```

### Gate
- `make gate-v20`：freeze manifest 必含 prompt_hash
- `tests/llm/test_prompt_hash_stability.py`

### 依賴
建議在 PR1 後做

---

## PR3 — JSON 輸出健壯化

### 目標
- 即使模型吐出前綴/後綴文字，也能可靠抽出 JSON
- 提升一致性與 schema pass rate

### 修改檔案

| 檔案 | 變更內容 |
|------|----------|
| `backend/llm/score_only_runner.py` | 改用 `extract_first_json_object()` |
| `backend/llm/routing.py` | 保證 response_format 與 runner 判斷一致 |

### 新增檔案

| 檔案 | 說明 |
|------|------|
| `backend/llm/json_utils.py` | `extract_first_json_object(text) -> dict` |
| `tests/llm/__init__.py` | Package init |
| `tests/llm/test_json_extractor.py` | 測試混入前後綴文字仍能 parse |
| `tests/llm/test_json_mode_param.py` | monkeypatch litellm 驗證參數 |

### JSON Extractor 規格

```python
def extract_first_json_object(text: str) -> dict:
    """
    支援：
    - 前後夾雜文字
    - code fence (```json ... ```)
    - 多段 JSON（取第一段完整 object）
    """
```

### Gate
- `make unit`（含 test_json_extractor）

### 依賴
PR2 之前/之後都可

---

## PR4 — Backtest/Paper 改用 `.run()` + Artifacts Schema 驗證

### 目標
- 所有產 signal 的流程都留下完整 `LLMRequest/LLMResponse`
- `validate_run` 驗欄位齊全可重建

### 修改檔案

| 檔案 | 變更內容 |
|------|----------|
| `backend/backtest/full_backtest_runner.py` | 改用 `.run()` 拿 `(req, resp)`；落 artifacts |
| `backend/papertrading/runner.py` | 同樣改用 `.run()` |
| `backend/api/routes/analyze.py` | 新增 `run_id` 概念；回傳帶 `run_id` |
| `backend/guardrails/validate_run.py` | 升級為 schema 驗證 |
| `backend/signals/artifact_logger.py` | 新增 `log_gate_decision()` |

### 新增檔案

| 檔案 | 說明 |
|------|------|
| `tests/artifacts/__init__.py` | Package init |
| `tests/artifacts/test_validate_run_schema.py` | 驗證 schema |
| `tests/integration/test_backtest_runner_logs_llm_artifacts.py` | 端到端測試 |

### LLMRequest 必含欄位

```python
{
    "event_id": str,
    "timestamp": datetime,
    "model": str,
    "prompt_template_id": str,
    "prompt_hash": str,
    "rendered_prompt": str,
    "parameters": dict
}
```

### LLMResponse 必含欄位

```python
{
    "raw_output": str,
    "token_usage": {
        "total": int,
        "prompt": int,
        "completion": int
    },
    "cost_usd": float,
    "latency_ms": int
}
```

### Gate
- `make validate-runs`
- `make gate-v20`（擴充）

### 依賴
PR2 + PR3 完成後再做

---

## PR5 — Paper Trading Fail-Closed

### 目標
- paper trading 不允許用假價成交/平倉
- `event_date` 必須是 T day
- 無價格時停在 pending，不瞎填

### 修改檔案

| 檔案 | 變更內容 |
|------|----------|
| `backend/papertrading/order_book.py` | `open_position()` 強制傳 `event_date`；`close_due_positions()` 移除 placeholder；新增 `mark_entered()`、`mark_exited()` |
| `backend/papertrading/runner.py` | 傳入正確 `event_date=T`；metadata 用 frozen config 傳入 |
| `backend/papertrading/scheduler.py` | 抓不到價格 → skip（fail-closed） |

### 新增檔案

| 檔案 | 說明 |
|------|------|
| `backend/papertrading/price_provider.py` | `get_close(symbol, date) -> Optional[float]` |
| `tests/paper/__init__.py` | Package init |
| `tests/paper/test_orderbook_event_date_required.py` | event_date 必須正確 |
| `tests/paper/test_close_due_positions_no_placeholder.py` | 無 placeholder |
| `tests/paper/test_scheduler_fail_closed_no_price.py` | mock 回 None |

### Gate
- `make paper_dryrun_10days`
- `forbid-stub` 額外 grep：禁止 `"placeholder"` 出現在 `backend/papertrading/`

### 依賴
PR4（因為 paper runner 要落 artifacts）

---

## PR6 — CLI 入口 + RUNBOOK 對齊

### 目標
- 文件/skills 不再指向不存在命令
- Makefile 只呼叫工具入口

### 新增檔案

| 檔案 | 說明 |
|------|------|
| `backend/tools/__init__.py` | Package init |
| `backend/tools/validate_run.py` | 轉呼叫 `guardrails.validate_run` |
| `backend/tools/leakage_check.py` | 轉呼叫 `guardrails.leakage_auditor` |
| `backend/tools/consistency_check.py` | 轉呼叫 `eval/consistency_checker.py` |
| `backend/tools/cost_report.py` | 彙總 `cost_usd` |
| `tests/test_runbook_smoke.py` | subprocess 跑 `--help` 應 exit 0 |

### 修改檔案

| 檔案 | 變更內容 |
|------|----------|
| `Makefile` | `validate-runs`、`leakage` 改用 `python -m tools.*`；新增 `runbook-smoke` |
| `docs/RUNBOOK.md` | 全面改為 `python -m tools.*` |
| `.claude/skills/run-artifacts-ledger.md` | 更新命令/路徑 |
| `.claude/skills/prompt-regression-suite.md` | 更新命令/路徑 |
| `.claude/skills/model-selection-harness.md` | 更新命令/路徑 |

### Makefile runbook-smoke

```makefile
runbook-smoke:
	cd backend && python -m tools.validate_run --help
	cd backend && python -m tools.leakage_check --help
	cd backend && python -m tools.cost_report --help
```

### Gate
- `make runbook-smoke`

### 依賴
PR4 後做

---

## Gate 總表

| PR | Gate Target | 驗收條件 |
|----|-------------|----------|
| PR1 | `make leakage` | 掃得到且能抓到故意違規 |
| PR2 | `make gate-v20` | freeze manifest 含 prompt_hash |
| PR3 | `make unit` | JSON extractor 測試通過 |
| PR4 | `make validate-runs` | schema 驗證通過 |
| PR5 | `make paper_dryrun_10days` | 無假價成交 |
| PR6 | `make runbook-smoke` | CLI 入口可執行 |

---

## 完整 gate-all

```makefile
gate-all: leakage validate-runs runbook-smoke unit
	@echo "All P0 gates passed!"
```
