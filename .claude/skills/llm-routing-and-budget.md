# Skill: llm-routing-and-budget

## 目的
定義 LLM 的兩種模式（batch_score / full_audit）、成本控制與 token 上限。

## 何時使用
- 設計 LLM pipeline
- 控制成本
- 選擇使用哪個模式

## 兩種模式

### 1. batch_score（批量分數模式）

**用途**：回測批量掃描、每日掃描
**成本目標**：< $0.01 / event
**輸出**：極簡 JSON（200-400 tokens）

```json
{
  "score": 0.82,
  "trade_candidate": true,
  "evidence_count": 3,
  "key_flags": {
    "guidance_positive": true,
    "revenue_beat": true,
    "margin_concern": false
  },
  "evidence_snippets": [
    {
      "quote": "We expect 15-18% growth",
      "speaker": "CFO",
      "section": "prepared"
    }
  ],
  "prompt_version": "v1.2.3",
  "no_trade_reason": null
}
```

**模型選擇**：
- Primary: `gpt-4o-mini`
- Fallback: `claude-3-haiku`

### 2. full_audit（完整審計模式）

**用途**：UI 互動查看、高分候選確認
**成本限制**：無硬性上限，但只對少數 event 觸發
**輸出**：完整多代理分析

```json
{
  "score": 0.82,
  "score_breakdown": {
    "guidance_score": 0.9,
    "sentiment_score": 0.75,
    "financial_score": 0.8
  },
  "trade_long_final": true,
  "confidence_raw": 0.78,
  "confidence_calibrated": 0.74,
  "key_findings": [
    {
      "finding": "Strong revenue guidance",
      "importance": "high",
      "evidence": [...]
    }
  ],
  "risk_factors": [
    {
      "factor": "Supply chain concerns mentioned",
      "severity": "low",
      "evidence": [...]
    }
  ],
  "multi_agent_analysis": {
    "analyst_1": {...},
    "analyst_2": {...},
    "synthesizer": {...}
  },
  "prompt_info": {
    "template_id": "full_audit_v1.1.0",
    "rendered_prompt": "...",
    "prompt_hash": "sha256:..."
  }
}
```

**模型選擇**：
- Primary: `gpt-5-mini` 或 `claude-sonnet`
- 可用較昂貴模型因為只對少數 event 觸發

## Token 預算

### batch_score
| 項目 | 上限 |
|------|------|
| Input (transcript pack) | 3,000 tokens |
| Output | 500 tokens |
| Total | 3,500 tokens |

### full_audit
| 項目 | 上限 |
|------|------|
| Input (transcript pack + context) | 8,000 tokens |
| Output | 2,000 tokens |
| Total | 10,000 tokens |

## 成本計算

### batch_score（以 gpt-4o-mini 為例）
```
Input: 3,000 tokens × $0.00015/1K = $0.00045
Output: 500 tokens × $0.0006/1K = $0.0003
Total: ~$0.00075 per event ✓ (< $0.01)
```

### full_audit（以 gpt-5-mini 為例）
```
Input: 8,000 tokens × $0.0003/1K = $0.0024
Output: 2,000 tokens × $0.0012/1K = $0.0024
Total: ~$0.0048 per event
```

## 路由邏輯

```python
def route_llm_call(event: Event, mode: str, score: float = None) -> LLMConfig:
    """決定使用哪個 LLM 配置"""

    if mode == "batch_score":
        return LLMConfig(
            model="gpt-4o-mini",
            max_input_tokens=3000,
            max_output_tokens=500,
            temperature=0,
            response_format="json"
        )

    elif mode == "full_audit":
        # 只對高分或 UI 請求觸發
        return LLMConfig(
            model="gpt-5-mini",
            max_input_tokens=8000,
            max_output_tokens=2000,
            temperature=0,
            response_format="json"
        )

    else:
        raise ValueError(f"Unknown mode: {mode}")
```

## 觸發 full_audit 的條件

```python
def should_trigger_full_audit(score: float, mode: str, is_ui_request: bool) -> bool:
    """決定是否觸發 full_audit"""

    # UI 請求直接觸發
    if is_ui_request:
        return True

    # 高分候選（臨界區域）
    if 0.65 <= score <= 0.85:
        return True

    # 非常高分（確認用）
    if score > 0.85:
        return True

    return False
```

## Deterministic 設定

**必須設定**：
- `temperature=0`
- `top_p=1`（或不設定）
- `response_format="json"` 或 JSON schema
- `seed=42`（如果 API 支援）

## 錯誤處理

```python
class LLMBudgetExceededError(Exception):
    """超出 token/成本預算"""
    pass

def validate_budget(tokens: int, cost: float, mode: str) -> None:
    if mode == "batch_score":
        if tokens > 3500:
            raise LLMBudgetExceededError(f"Tokens {tokens} > 3500")
        if cost > 0.01:
            raise LLMBudgetExceededError(f"Cost ${cost} > $0.01")
```

## 產出 Artifacts

每次 LLM 呼叫記錄：
```json
{
  "event_id": "evt_001",
  "mode": "batch_score",
  "model": "gpt-4o-mini",
  "input_tokens": 2500,
  "output_tokens": 350,
  "cost_usd": 0.00058,
  "latency_ms": 1200,
  "within_budget": true
}
```

## 驗收命令

```bash
# 驗證成本控制
pytest tests/llm/test_budget.py -v

# 檢查 batch_score 平均成本
python -m backend.tools.cost_report --run-id <run_id>
```
