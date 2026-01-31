# Skill: evidence-triangulation

## 目的
確保每個關鍵結論至少有 2 個不同來源的 transcript 引用支持，避免單一證據偏誤。

## 何時使用
- LLM 分析 earnings call transcript
- 產生交易訊號
- 評估 confidence

## 規則

### 1. 證據三角驗證原則
- **每個關鍵判斷至少 2 個引用**
- **引用必須來自不同來源**（不同 speaker 或不同段落）
- **引用必須可追溯**（包含位置資訊）

### 2. 引用來源類型
```python
class EvidenceSource(Enum):
    CEO = "ceo"           # CEO 發言
    CFO = "cfo"           # CFO 發言
    ANALYST = "analyst"   # 分析師提問
    PREPARED = "prepared" # Prepared remarks
    QA = "qa"             # Q&A session
```

### 3. 有效的證據組合
```python
# 有效：不同 speaker
evidence_1 = {"speaker": "CEO", "section": "prepared"}
evidence_2 = {"speaker": "CFO", "section": "prepared"}

# 有效：不同 section
evidence_1 = {"speaker": "CEO", "section": "prepared"}
evidence_2 = {"speaker": "CEO", "section": "qa"}

# 無效：同一 speaker 同一 section
evidence_1 = {"speaker": "CEO", "section": "prepared", "paragraph": 3}
evidence_2 = {"speaker": "CEO", "section": "prepared", "paragraph": 4}
```

### 4. Evidence Schema
```python
class Evidence(BaseModel):
    quote: str                    # 原文引用
    speaker: str                  # 發言者
    section: Literal["prepared", "qa"]  # 段落類型
    paragraph_index: int          # 段落索引
    relevance: str               # 相關性說明
    supports: str                # 支持的結論
```

### 5. 降權規則
如果證據不足：
```python
def apply_evidence_penalty(score: float, evidence_count: int) -> float:
    """根據證據數量調整分數"""
    if evidence_count >= 3:
        return score  # 充足證據，不調整
    elif evidence_count == 2:
        return score * 0.95  # 輕微降權
    elif evidence_count == 1:
        return score * 0.7   # 嚴重降權
    else:
        return 0.0  # 無證據，不交易
```

### 6. NO_TRADE 觸發條件
- 證據數量 < 2
- 所有證據來自同一來源
- 關鍵欄位（guidance、outlook）無引用支持

## Prompt 整合
```markdown
## Evidence Requirements

For each key finding, you MUST provide at least 2 supporting quotes:
- Quotes must be from DIFFERENT speakers OR different sections
- Include exact location (speaker name, section, paragraph)
- If insufficient evidence exists, set `trade_candidate: false`

Example:
{
  "key_finding": "Strong revenue guidance",
  "evidence": [
    {
      "quote": "We expect revenue growth of 15-18% next quarter",
      "speaker": "CFO",
      "section": "prepared",
      "paragraph_index": 12
    },
    {
      "quote": "Our pipeline is stronger than ever",
      "speaker": "CEO",
      "section": "qa",
      "paragraph_index": 45
    }
  ]
}
```

## 產出 Artifacts
- 每個 LLM response 的 `evidence` 欄位
- `evidence_audit.json`: 證據品質統計

## 驗收命令
```bash
# 驗證證據完整性
pytest tests/guardrails/test_evidence_triangulation.py -v

# 檢查證據覆蓋率
python -m backend.tools.audit_evidence --run-id <run_id>
```

## 統計報告
```json
{
  "total_events": 1000,
  "events_with_2plus_evidence": 850,
  "events_with_1_evidence": 100,
  "events_with_0_evidence": 50,
  "evidence_coverage_rate": 0.85,
  "unique_speaker_pairs": {
    "CEO-CFO": 450,
    "CEO-Analyst": 200,
    "CFO-Analyst": 150,
    "Other": 50
  }
}
```
