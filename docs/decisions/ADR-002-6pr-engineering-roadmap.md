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

## References
- `docs/ENGINEERING_ROADMAP.md`
- `docs/PR_CHECKLIST.md`
- `docs/RUNBOOK.md`
