# ADR-002: 6-PR Engineering Roadmap Completion

## Status
**COMPLETED** - 2026-02-01

## Context
Paper trading 需要穩健的工程基礎設施：leakage 防護、prompt 版本控制、JSON 解析容錯、artifacts 標準化、fail-closed 機制、CLI 操作介面。

## Decision
實作 6 個 PR 建立完整的 paper trading 工程基礎：

### PR Summary

| PR | 功能 | 測試數 | 關鍵檔案 |
|---|---|---|---|
| PR1 | Leakage Auditor Allowlist | 7 | `backend/guardrails/leakage_auditor.py` |
| PR2 | Prompt SSOT + prompt_hash | 11 | `backend/papertrading/freeze_policy.py` |
| PR3 | JSON 輸出健壯化 | 30 | `backend/llm/json_parser.py` |
| PR4 | Artifacts Schema | 17 | `backend/schemas/artifacts.py` |
| PR5 | Fail-Closed 機制 | 25 | `backend/papertrading/fail_closed.py` |
| PR6 | CLI 入口 + RUNBOOK | 16 | `backend/papertrading/cli.py` |

**總計：113 測試全數通過**

### PR1: Leakage Auditor Allowlist

**問題**：Result schema 變數（如 `return_pct`, `win_rate`）在合法檔案中被誤報為 leakage。

**解法**：
- `ALLOWLIST_PATTERNS`: 允許特定變數出現在指定檔案
- `include_patterns`: 縮小掃描範圍

```python
ALLOWLIST_PATTERNS = {
    "return_pct": ["backend/schemas/*", "tests/*"],
    "win_rate": ["backend/schemas/*", "tests/*"],
}
```

### PR2: Prompt SSOT + prompt_hash

**問題**：Prompt 變更後無法追蹤，可能導致 paper trading 結果不可重現。

**解法**：
- `compute_prompt_hash()`: SHA256(system_prompt + user_template)
- `FreezeManifest.prompt_hash`: 凍結時記錄 hash
- `validate_runtime()`: 執行時驗證一致性

```python
def compute_prompt_hash(system_prompt: str, user_template: str) -> str:
    combined = f"{system_prompt}\n---\n{user_template}"
    return hashlib.sha256(combined.encode()).hexdigest()
```

### PR3: JSON 輸出健壯化

**問題**：LLM 輸出的 JSON 常有格式問題（markdown 包裹、trailing comma、截斷）。

**解法**：
- `extract_json_from_markdown()`: 處理 ```json 包裹
- `fix_trailing_commas()`: 修復常見錯誤
- `attempt_truncation_recovery()`: 嘗試修復截斷
- `NO_TRADE_DEFAULT`: 解析失敗時的保守預設

```python
NO_TRADE_DEFAULT = {
    "score": 0.0,
    "trade_candidate": False,
    "no_trade_reason": "JSON parse failure - conservative NO_TRADE",
}
```

### PR4: Artifacts Schema

**問題**：回測/paper trading 產出格式不一致，難以追蹤和比較。

**解法**：Pydantic schema 標準化所有產出物

- `RunManifest`: 執行配置（model, prompt, threshold）
- `SignalArtifact`: 個別信號（score, evidence, flags）
- `PositionArtifact`: 部位（entry/exit date, weight）
- `PerformanceArtifact`: 績效（**必須來自 Whaleforce API**）

### PR5: Fail-Closed 機制

**問題**：任何錯誤可能導致意外交易。

**解法**：Fail-closed 原則 - 有任何問題就 NO_TRADE

- `PreRunValidator`: 執行前檢查（freeze_policy, prompt_hash, disk_space）
- `@fail_closed`: 裝飾器，錯誤時返回 NO_TRADE
- `HealthChecker`: 服務可用性檢查

```python
@fail_closed(default_value=NO_TRADE_RESPONSE)
def analyze_event(event):
    # 任何錯誤都會返回 NO_TRADE
    ...
```

### PR6: CLI Entry Point

**問題**：缺乏操作介面，難以日常運維。

**解法**：對齊 RUNBOOK.md 的 CLI 命令

```bash
python -m backend.papertrading.cli check-orders      # 檢查訂單
python -m backend.papertrading.cli daily-report      # 每日報告
python -m backend.papertrading.cli weekly-report     # 每週報告
python -m backend.papertrading.cli emergency-stop    # 緊急停止
python -m backend.papertrading.cli status            # 系統狀態
python -m backend.papertrading.cli validate          # 配置驗證
```

## Consequences

### Positive
- 完整的 leakage 防護機制
- Prompt 版本可追蹤、可驗證
- LLM JSON 輸出容錯處理
- 標準化的 artifacts 格式
- Fail-closed 確保安全
- CLI 方便日常操作

### Negative
- 增加程式碼複雜度
- 新的測試維護負擔

## Test Execution

```bash
# 執行所有 113 個測試
python3 -m pytest tests/guardrails/ tests/llm/ tests/papertrading/ tests/schemas/ -v
```

## Test Results (113 PASSED)

### PR1: Leakage Auditor (14 tests) ✅

| Test | Status |
|------|--------|
| `test_default_config_has_include_roots` | ✅ PASSED |
| `test_default_config_has_allowlist` | ✅ PASSED |
| `test_strict_config_scans_everything` | ✅ PASSED |
| `test_allowlisted_file_not_critical` | ✅ PASSED |
| `test_signal_path_with_future_data_is_critical` | ✅ PASSED |
| `test_llm_path_with_t_plus_30_is_critical` | ✅ PASSED |
| `test_only_included_paths_scanned` | ✅ PASSED |
| `test_file_pattern_inclusion` | ✅ PASSED |
| `test_prompts_always_scanned` | ✅ PASSED |
| `test_run_with_default_config` | ✅ PASSED |
| `test_run_with_custom_config` | ✅ PASSED |
| `test_empty_codebase` | ✅ PASSED |
| `test_nonexistent_include_root` | ✅ PASSED |
| `test_malformed_python_file` | ✅ PASSED |

### PR2: Prompt SSOT (11 tests) ✅

| Test | Status |
|------|--------|
| `test_compute_prompt_hash_deterministic` | ✅ PASSED |
| `test_compute_prompt_hash_different_content` | ✅ PASSED |
| `test_compute_prompt_hash_whitespace_matters` | ✅ PASSED |
| `test_manifest_includes_prompt_hash_fields` | ✅ PASSED |
| `test_manifest_hash_includes_prompt_hash` | ✅ PASSED |
| `test_manifest_persists_prompt_hash` | ✅ PASSED |
| `test_validate_runtime_passes_with_matching_hash` | ✅ PASSED |
| `test_validate_runtime_fails_with_mismatched_hash` | ✅ PASSED |
| `test_frozen_config_has_prompt_hash_fields` | ✅ PASSED |
| `test_frozen_config_defaults_to_none` | ✅ PASSED |
| `test_freeze_accepts_prompt_hash` | ✅ PASSED |

### PR3: JSON Parser (30 tests) ✅

| Test | Status |
|------|--------|
| `test_json_code_block` | ✅ PASSED |
| `test_generic_code_block` | ✅ PASSED |
| `test_bare_json` | ✅ PASSED |
| `test_json_array` | ✅ PASSED |
| `test_no_json` | ✅ PASSED |
| `test_trailing_comma_in_object` | ✅ PASSED |
| `test_trailing_comma_in_array` | ✅ PASSED |
| `test_nested_trailing_commas` | ✅ PASSED |
| `test_no_trailing_commas` | ✅ PASSED |
| `test_missing_closing_brace` | ✅ PASSED |
| `test_missing_closing_bracket` | ✅ PASSED |
| `test_balanced_json` | ✅ PASSED |
| `test_truncated_in_string` | ✅ PASSED |
| `test_valid_json` | ✅ PASSED |
| `test_json_in_markdown` | ✅ PASSED |
| `test_json_with_trailing_comma` | ✅ PASSED |
| `test_truncated_json_recovery` | ✅ PASSED |
| `test_completely_invalid` | ✅ PASSED |
| `test_empty_input` | ✅ PASSED |
| `test_real_llm_response_format` | ✅ PASSED |
| `test_success_returns_data` | ✅ PASSED |
| `test_failure_returns_default` | ✅ PASSED |
| `test_valid_batch_score` | ✅ PASSED |
| `test_failure_returns_no_trade` | ✅ PASSED |
| `test_no_trade_default_is_safe` | ✅ PASSED |
| `test_unicode_content` | ✅ PASSED |
| `test_nested_quotes` | ✅ PASSED |
| `test_large_numbers` | ✅ PASSED |
| `test_boolean_values` | ✅ PASSED |
| `test_null_values` | ✅ PASSED |

### PR4: Artifacts Schema (17 tests) ✅

| Test | Status |
|------|--------|
| `test_create_manifest_basic` | ✅ PASSED |
| `test_manifest_hash_deterministic` | ✅ PASSED |
| `test_manifest_hash_changes_with_config` | ✅ PASSED |
| `test_manifest_includes_prompt_hash` | ✅ PASSED |
| `test_create_signal` | ✅ PASSED |
| `test_signal_with_no_trade` | ✅ PASSED |
| `test_create_position` | ✅ PASSED |
| `test_position_with_prices` | ✅ PASSED |
| `test_create_performance` | ✅ PASSED |
| `test_performance_requires_api_source` | ✅ PASSED |
| `test_create_run_artifacts` | ✅ PASSED |
| `test_add_signals_and_positions` | ✅ PASSED |
| `test_add_checkpoint` | ✅ PASSED |
| `test_save_and_load` | ✅ PASSED |
| `test_all_run_types` | ✅ PASSED |
| `test_create_summary` | ✅ PASSED |
| `test_summary_with_performance` | ✅ PASSED |

### PR5: Fail-Closed (25 tests) ✅

| Test | Status |
|------|--------|
| `test_create_passing_check` | ✅ PASSED |
| `test_create_failing_check` | ✅ PASSED |
| `test_all_pass` | ✅ PASSED |
| `test_one_fail` | ✅ PASSED |
| `test_warns_dont_fail` | ✅ PASSED |
| `test_check_freeze_policy_not_frozen` | ✅ PASSED |
| `test_check_freeze_policy_no_manifest` | ✅ PASSED |
| `test_check_freeze_policy_success` | ✅ PASSED |
| `test_check_prompt_hash_match` | ✅ PASSED |
| `test_check_prompt_hash_mismatch` | ✅ PASSED |
| `test_check_prompt_hash_missing_expected` | ✅ PASSED |
| `test_check_order_book_integrity_success` | ✅ PASSED |
| `test_check_order_book_integrity_invalid` | ✅ PASSED |
| `test_normal_execution` | ✅ PASSED |
| `test_returns_default_on_error` | ✅ PASSED |
| `test_returns_no_trade_response` | ✅ PASSED |
| `test_raises_exception_when_configured` | ✅ PASSED |
| `test_normal_async_execution` | ✅ PASSED |
| `test_returns_default_on_async_error` | ✅ PASSED |
| `test_no_trade_is_conservative` | ✅ PASSED |
| `test_check_earnings_api_success` | ✅ PASSED |
| `test_check_llm_service_success` | ✅ PASSED |
| `test_check_all` | ✅ PASSED |
| `test_validate_pre_run_all_pass` | ✅ PASSED |
| `test_validate_pre_run_with_prompt_hash` | ✅ PASSED |

### PR6: CLI Entry Point (16 tests) ✅

| Test | Status |
|------|--------|
| `test_default_config` | ✅ PASSED |
| `test_custom_config` | ✅ PASSED |
| `test_create_order_status` | ✅ PASSED |
| `test_create_daily_report` | ✅ PASSED |
| `test_cli_initialization` | ✅ PASSED |
| `test_cli_custom_config` | ✅ PASSED |
| `test_check_orders_empty` | ✅ PASSED |
| `test_daily_report_with_data` | ✅ PASSED |
| `test_daily_report_today` | ✅ PASSED |
| `test_daily_report_no_data` | ✅ PASSED |
| `test_weekly_report_aggregation` | ✅ PASSED |
| `test_emergency_stop_returns_result` | ✅ PASSED |
| `test_status_returns_dict` | ✅ PASSED |
| `test_validate_returns_result` | ✅ PASSED |
| `test_cli_module_importable` | ✅ PASSED |
| `test_models_serializable` | ✅ PASSED |

## File Mapping

| PR | 實作檔案 | 測試檔案 |
|---|---|---|
| PR1 | `backend/guardrails/leakage_auditor.py` | `tests/guardrails/test_leakage_audit_scope_allowlist.py` |
| PR2 | `backend/papertrading/freeze_policy.py` | `tests/papertrading/test_freeze_manifest_prompt_hash.py` |
| PR3 | `backend/llm/json_parser.py` | `tests/llm/test_json_parser.py` |
| PR4 | `backend/schemas/artifacts.py` | `tests/schemas/test_artifacts.py` |
| PR5 | `backend/papertrading/fail_closed.py` | `tests/papertrading/test_fail_closed.py` |
| PR6 | `backend/papertrading/cli.py` | `tests/papertrading/test_cli.py` |

## Notes & Caveats

### Python 3.9 相容性
- **問題**：`pandas_market_calendars` 使用 Python 3.10+ 的 `X | None` 語法
- **解法**：測試使用 `importlib.util` 直接載入模組，避免觸發 `papertrading/__init__.py` 的 import chain
- **影響檔案**：所有 `tests/papertrading/test_*.py`

### Pydantic v2 注意
- 使用 `model_config = {"populate_by_name": True}` 取代舊的 `class Config:`
- `model_dump()` 取代 `dict()`
- `model_dump_json()` 取代 `json()`

### 測試 Mock 策略
- `freeze_policy.py` 的模組依賴需要在測試中 mock：
  ```python
  sys.modules["backend.papertrading.order_book"] = MagicMock()
  sys.modules["backend.papertrading.freeze_policy"] = MagicMock()
  ```
- CLI 的 `validate()` 方法將 import 移到 try block 內，讓 ImportError 被正確捕獲

### Fail-Closed 原則
- 任何錯誤都返回 `NO_TRADE_DEFAULT`
- 不使用 `ParamSpec`（Python 3.9 不支援）
- Decorator 簡化為基本的 `Callable` 型別

### JSON Parser 容錯順序
1. 嘗試直接解析
2. 移除 markdown code block
3. 修復 trailing comma
4. 嘗試截斷修復（補上缺少的 `}` 或 `]`）
5. 全部失敗 → 返回 `NO_TRADE_DEFAULT`

## References
- `docs/ENGINEERING_ROADMAP.md`
- `docs/PR_CHECKLIST.md`
- `docs/RUNBOOK.md`
