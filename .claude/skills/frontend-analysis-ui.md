# Skill: frontend-analysis-ui

## 目的
規範前端 UI 的兩種查詢入口和分析結果顯示方式。

## 何時使用
- 建立前端 UI
- 顯示分析結果
- 展示 prompt 和 model 資訊

## 兩種入口模式

### 模式 1: 日期模式
1. 使用者選擇日期
2. 顯示當天所有 earnings calls 清單
3. 選擇一個 event 進行分析
4. 顯示分析結果

### 模式 2: 股票/季度模式
1. 使用者輸入股票代碼
2. 顯示該公司的 earnings call 歷史
3. 選擇年份和季度
4. 顯示分析結果

## UI 元件

### 1. DatePicker
```tsx
interface DatePickerProps {
  value: Date;
  onChange: (date: Date) => void;
  minDate?: Date;  // 2017-01-01
  maxDate?: Date;  // today
}
```

### 2. EarningsCallList
```tsx
interface EarningsCall {
  eventId: string;
  symbol: string;
  companyName: string;
  fiscalYear: number;
  fiscalQuarter: number;
  eventDate: string;
  transcriptAvailable: boolean;
}

interface EarningsCallListProps {
  calls: EarningsCall[];
  onSelect: (eventId: string) => void;
  loading: boolean;
}
```

### 3. SymbolSearch
```tsx
interface SymbolSearchProps {
  value: string;
  onChange: (symbol: string) => void;
  onSearch: () => void;
}
```

### 4. AnalysisResult
```tsx
interface AnalysisResult {
  eventId: string;
  symbol: string;
  score: number;
  tradeLong: boolean;
  confidence: number;
  evidence: Evidence[];
  modelInfo: ModelInfo;
  promptInfo: PromptInfo;
  rawOutput: object;
}
```

## 分析結果顯示

### 必須顯示的資訊

1. **基本資訊**
   - Symbol
   - Company name
   - Event date
   - Fiscal year/quarter

2. **分析結果**
   - Score (0-1)
   - Trade recommendation (Long/No Trade)
   - Confidence (經過校準的)
   - Key findings

3. **證據引用**
   - 每個 evidence 的原文引用
   - Speaker 和 section 資訊
   - 相關性說明

4. **Model 資訊**
   - Model ID (e.g., gpt-4o-mini)
   - Model routing (batch_score / full_audit)
   - Token usage
   - Cost
   - Latency

5. **Prompt 資訊**
   - Prompt template ID
   - Prompt version
   - Rendered prompt (可展開)
   - Prompt hash

## API Endpoints

### 1. 取得日期的 Earnings Calls
```
GET /api/earnings?date=YYYY-MM-DD
```

### 2. 取得公司的 Events
```
GET /api/company/{symbol}/events
```

### 3. 執行分析（batch_score）
```
POST /api/analyze
{
  "event_id": "evt_aapl_2024q1",
  "mode": "batch_score"
}
```

### 4. 執行分析（full_audit）
```
POST /api/analyze/full_audit
{
  "event_id": "evt_aapl_2024q1"
}
```

## UI 版面配置

```
┌─────────────────────────────────────────────────────────────┐
│  [Tab: By Date]  [Tab: By Symbol]                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐  ┌───────────────────────────────────┐│
│  │ Date Picker /   │  │ Earnings Calls List               ││
│  │ Symbol Search   │  │                                   ││
│  │                 │  │ ○ AAPL - Apple Inc. (Q1 2024)    ││
│  │ [2024-01-25]    │  │ ○ MSFT - Microsoft (Q2 2024)     ││
│  │                 │  │ ○ GOOGL - Alphabet (Q4 2023)     ││
│  └─────────────────┘  └───────────────────────────────────┘│
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Analysis Result                                            │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ AAPL - Apple Inc. - Q1 2024                             ││
│  │ Event Date: 2024-01-25                                  ││
│  │                                                         ││
│  │ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        ││
│  │ │ Score: 0.82 │ │ Long: ✓    │ │ Conf: 0.78  │        ││
│  │ └─────────────┘ └─────────────┘ └─────────────┘        ││
│  │                                                         ││
│  │ Key Findings:                                           ││
│  │ • Strong revenue guidance (+15-18%)                     ││
│  │ • Positive iPhone demand outlook                        ││
│  │                                                         ││
│  │ Evidence:                                               ││
│  │ ┌─────────────────────────────────────────────────────┐││
│  │ │ "We expect revenue growth of 15-18%..."              │││
│  │ │ — CFO, Prepared Remarks, ¶12                         │││
│  │ └─────────────────────────────────────────────────────┘││
│  │                                                         ││
│  │ [▶ Show Prompt]  [▶ Show Model Info]  [▶ Show Raw]     ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## 展開區塊

### Prompt Info（展開後）
```
Prompt Template: batch_score_v1.2.3
Prompt Hash: sha256:abc123...

--- Rendered Prompt ---
You are analyzing an earnings call transcript for AAPL (Apple Inc.)
for fiscal Q1 2024.

[Transcript snippets...]

Based on the above, provide:
- A score from 0 to 1
- Key evidence quotes
...
```

### Model Info（展開後）
```
Model: gpt-4o-mini
Mode: batch_score
Temperature: 0
Max Tokens: 500

Token Usage:
- Input: 1,200
- Output: 150
- Total: 1,350

Cost: $0.0027
Latency: 1,850ms
```

## 驗收標準

1. 兩種入口模式都可用
2. 分析結果顯示完整資訊
3. Prompt 可展開查看
4. Model 資訊可展開查看
5. Evidence 有引用位置
6. 響應式設計（mobile friendly）

## 驗收命令

```bash
# 啟動前端
cd frontend && npm run dev

# 執行 E2E 測試
npm run test:e2e
```
