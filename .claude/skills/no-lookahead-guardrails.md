# Skill: no-lookahead-guardrails

## 目的
防止資料洩漏（lookahead bias），確保分析只使用 T day（earnings call 發佈日）及之前可得的資料。

## 何時使用
- 任何涉及時間序列資料的操作
- 特徵工程
- 模型訓練與評估
- 回測執行

## 規則

### 1. 時間點定義
- **T day**: earnings call 發佈日（event date）
- **可用資料**: 只能使用 <= T day 的資料
- **禁止使用**: T+1 及之後的任何資料（價格、新聞、其他 earnings call）

### 2. 資料查詢必須帶 as_of
```python
# 正確
def get_transcript(symbol: str, event_date: date) -> str:
    # 只取得 event_date 當天發佈的 transcript
    pass

# 錯誤 - 沒有時間限制
def get_transcript(symbol: str) -> str:
    # 可能取得未來的資料
    pass
```

### 3. 禁止的操作
- 使用 T+30 價格來調整 threshold
- 使用未來的 earnings call 結果來訓練模型
- 在 prompt 中加入任何 T 日之後的資訊
- 使用跨時間的統計量（如：全時間範圍的平均值）

### 4. 驗證檢查
```python
def validate_no_lookahead(data_date: date, analysis_date: date) -> bool:
    """確保資料日期 <= 分析日期"""
    return data_date <= analysis_date
```

## 產出 Artifacts
- `guardrails/lookahead_check.log`: 每次檢查的記錄
- `guardrails/violations.json`: 違規記錄（如有）

## 驗收命令
```bash
pytest tests/guardrails/test_no_lookahead.py -v
```

## 違規處理
- 任何 lookahead 違規必須立即停止執行
- 記錄違規詳情到 `violations.json`
- 相關的 run 結果視為無效
