# Skill: prompt-regression-suite

## 目的
管理 prompt 版本化，確保任何 prompt 改動都經過回歸測試。

## 何時使用
- 修改 prompt
- 發布新 prompt 版本
- 比較不同 prompt 版本的效果
- 確保 prompt 改動不會破壞既有功能

## Prompt 版本化

### 版本命名
```
{mode}_v{major}.{minor}.{patch}

例如：
- batch_score_v1.0.0
- batch_score_v1.1.0
- full_audit_v1.0.0
```

### 版本規則
- **Major**: 重大結構改變（輸出 schema 變更）
- **Minor**: 新增指令或調整邏輯
- **Patch**: 措辭修正或 bug fix

## Prompt 儲存結構

```
backend/llm/prompts/
├── batch_score/
│   ├── v1.0.0.md
│   ├── v1.1.0.md
│   └── v1.2.0.md
├── full_audit/
│   ├── v1.0.0.md
│   └── v1.1.0.md
└── registry.yaml
```

### registry.yaml
```yaml
prompts:
  batch_score:
    current: v1.2.0
    versions:
      - version: v1.2.0
        hash: sha256:abc123...
        date: 2026-01-30
        author: dev@company.com
        changes: "Add evidence triangulation requirement"
      - version: v1.1.0
        hash: sha256:def456...
        date: 2026-01-15
        author: dev@company.com
        changes: "Improve guidance extraction"

  full_audit:
    current: v1.1.0
    versions:
      - version: v1.1.0
        hash: sha256:ghi789...
        date: 2026-01-20
```

## Prompt Template 格式

```markdown
# batch_score_v1.2.0

## Metadata
- Version: 1.2.0
- Mode: batch_score
- Max Output Tokens: 500
- Output Schema: batch_score_output_v1

## System Prompt
You are a financial analyst specializing in earnings call analysis.
Your task is to evaluate whether an earnings call indicates a potential long opportunity.

## Rules
1. Only use information available on or before the event date
2. Provide at least 2 evidence quotes from different speakers/sections
3. If insufficient evidence, set trade_candidate to false
4. Be conservative - when in doubt, do not trade

## Output Format
Respond with a JSON object matching this schema:
```json
{
  "score": <float 0-1>,
  "trade_candidate": <boolean>,
  "evidence_count": <int>,
  "key_flags": {
    "guidance_positive": <boolean>,
    "revenue_beat": <boolean>,
    "margin_concern": <boolean>
  },
  "evidence_snippets": [
    {
      "quote": <string>,
      "speaker": <string>,
      "section": <string>
    }
  ],
  "no_trade_reason": <string or null>
}
```

## User Prompt Template
```
Analyze the following earnings call for {symbol} ({company_name}).
Fiscal Period: Q{quarter} {year}
Event Date: {event_date}

--- TRANSCRIPT ---
{transcript_pack}
--- END TRANSCRIPT ---

Based on the transcript above, provide your analysis.
```
```

## Prompt Hash 計算

```python
import hashlib

def calculate_prompt_hash(prompt_content: str) -> str:
    """計算 prompt 的 SHA-256 hash"""
    # 標準化：移除多餘空白
    normalized = " ".join(prompt_content.split())
    return "sha256:" + hashlib.sha256(normalized.encode()).hexdigest()[:16]
```

## 回歸測試流程

### 1. 修改 prompt 前
```bash
# 記錄當前版本的 baseline
python -m backend.eval.prompt_baseline \
  --prompt-id batch_score \
  --version v1.1.0 \
  --test-events data/regression_events.json \
  --output eval/baselines/batch_score_v1.1.0.json
```

### 2. 建立新版本
```bash
# 建立新 prompt 檔案
cp backend/llm/prompts/batch_score/v1.1.0.md \
   backend/llm/prompts/batch_score/v1.2.0.md

# 編輯新版本...

# 更新 registry
python -m backend.llm.prompts.register \
  --prompt-id batch_score \
  --version v1.2.0 \
  --file backend/llm/prompts/batch_score/v1.2.0.md
```

### 3. 執行回歸測試
```bash
python -m backend.eval.prompt_regression \
  --prompt-id batch_score \
  --old-version v1.1.0 \
  --new-version v1.2.0 \
  --test-events data/regression_events.json \
  --k 3 \
  --output eval/regressions/batch_score_v1.1.0_to_v1.2.0.json
```

### 4. 檢查回歸報告
```markdown
# Prompt Regression Report

## Comparison
- Old: batch_score_v1.1.0
- New: batch_score_v1.2.0
- Test Events: 100
- K (consistency): 3

## Results

| Metric | v1.1.0 | v1.2.0 | Change |
|--------|--------|--------|--------|
| JSON Valid | 99.6% | 99.8% | +0.2% |
| Flip Rate | 0.8% | 0.4% | -0.4% ✓ |
| Score Std | 0.022 | 0.018 | -0.004 ✓ |
| Evidence Compliance | 92% | 96% | +4% ✓ |
| Avg Cost | $0.0007 | $0.0008 | +$0.0001 |

## Decision Comparison

| Event | v1.1.0 trade | v1.2.0 trade | Agreement |
|-------|--------------|--------------|-----------|
| evt_001 | true | true | ✓ |
| evt_002 | false | false | ✓ |
| evt_003 | true | false | ⚠️ |

## Recommendation
- **Approve**: New version improves consistency and evidence compliance
- **Note**: 1 decision changed (evt_003) - verify manually
```

## 重要規則

### 1. 不能在 production 直接改 prompt
```python
# 錯誤：直接修改 current version
edit backend/llm/prompts/batch_score/v1.2.0.md  # 不要這樣！

# 正確：建立新版本
cp v1.2.0.md v1.2.1.md
edit v1.2.1.md
# 跑回歸測試
# 更新 registry
```

### 2. 每次改動必須
- 建立新版本號
- 計算新 hash
- 跑回歸測試
- 更新 registry
- 記錄 ADR（如果是重大改動）

### 3. Freeze 期間（2026-01-01 起）
- 不能修改 production prompt
- 任何改動需要：
  - 新版本 tag
  - 完整 walk-forward 重跑
  - ADR 記錄

## 產出 Artifacts

```
eval/
├── baselines/
│   ├── batch_score_v1.1.0.json
│   └── batch_score_v1.2.0.json
├── regressions/
│   └── batch_score_v1.1.0_to_v1.2.0.json
```

## 驗收命令

```bash
# 驗證 prompt registry
python -m backend.llm.prompts.validate

# 檢查所有 prompt 都有 hash
python -m backend.llm.prompts.audit

# 執行回歸測試
pytest tests/llm/test_prompt_regression.py -v
```
