# ADR-004: Week 1 執行計劃 — ChatGPT Pro 分析結果

**日期**: 2026-02-02
**狀態**: 執行中
**ChatGPT Pro Task ID**: 9320
**處理時間**: 939 秒

## 背景

PR7 P0 缺口修復完成後，提交專案完整分析給 ChatGPT Pro，請求下一步建議。

## ChatGPT Pro 核心診斷

### 現狀判讀

> **Sharpe 卡住最常見的硬傷是：假陽性（value trap）造成尾部虧損**

- 工程地基已完成（PR1-7, 113 tests）
- 瓶頸不是工程，而是「信號品質 + 風控」
- Sharpe 0.84 → 2.0 需要 2.38 倍改善

### 績效缺口分析

| 指標 | 目前 | 目標 | 缺口 | 主要對策 |
|------|------|------|------|----------|
| CAGR | 19.33% | 35% | +15.67% | 提高每筆期望報酬 |
| Sharpe | 0.84 | 2.0 | +1.16 | **減少假陽性（頭號敵人）** |
| MDD | 30.19% | 25% | -5.19% | 減少尾部虧損 |

## 優化後的 4 週執行計劃

### 雙主線並行策略

```
主線 A：端到端可跑（paper 的工程與資料）
主線 B：信號品質可量化（golden set + eval harness + LLM 選型）
```

### Week 1：最短閉環

| 任務 | 主線 | 說明 | 驗收標準 |
|------|------|------|----------|
| A1. market_data_client MVP | A | get_close_price() 穩定可用 | 測試通過 + 可觀測 |
| A2. entry fill 串接 | A | pending → open 正確寫入 entry_price | PnL 計算正確 |
| B1. Eval Harness + 快取 | B | 可重複 eval CLI | 二次跑快取命中 |
| B2. Golden Set v0 (50份) | B | 驗證標註規範 | 明顯好球/壞球/灰色地帶 |

### Week 1 Go/No-Go 關卡

- [ ] eval harness 可穩定重跑，結果可複現
- [ ] 快取命中率在二次跑時明顯提升
- [ ] market_data_client 讓 paper 回放有 entry/exit price + PnL

### Week 2-4 概覽

| Week | 主線 A | 主線 B |
|------|--------|--------|
| W2 | PnL 完整計算 | Golden Set v1 (200份) + LLM 選型 |
| W3 | 損失歸因 → Gate 校準 | 策略層調整 |
| W4 | Shadow mode 驗證 | 正式 Paper Trading |

## 六題具體建議

### 1. 執行順序優化

**原提案**：W1 data → W2 LLM → W3 策略 → W4 paper（線性）

**ChatGPT Pro 建議**：W1 同時建立兩個閉環（並行）

**原因**：
- LLM 選型是績效關鍵路徑
- 晚一週開始量化 LLM 信號品質 → Sharpe 瓶頸晚一週被看見
- 沒有快取，W2-3 的 A/B 會非常慢且昂貴

### 2. Golden Set 策略

**結論**：兩個都要，分階段設計

| 階段 | 數量 | 目的 |
|------|------|------|
| v0 | 50 份 | 驗證標註規範 + 暴露系統性誤判 |
| v1 | 200 份 | 模型/提示的初步定奪 |
| v2 | 500+ | 回歸測試套件（如需要） |

**Golden Set 結構建議**：
```
每筆標註：
- guidance_cut / guidance_withdraw（是/否）
- margin_concern（是/否）
- balance_sheet_risk（是/否）
- one_off vs structural（one-off / structural / unclear）
```

### 3. 成本控制策略

**優先順序**：快取優先 → 路由（兩段式）→ 最後才降級

| 階段 | 策略 | 說明 |
|------|------|------|
| 研究期 | **快取** | 不犧牲品質，直接砍成本與時間 |
| 上線期 | **路由** | 便宜模型 screening → 強模型 audit |
| 例外 | 降級 | 預算/供應受限時才考慮 |

**快取 key**：`(model, prompt_hash, transcript_hash, params)`

### 4. Sharpe 瓶頸分析

**三大障礙**：

| 障礙 | 說明 | 對策 |
|------|------|------|
| A. 假陽性 | 把 structural 誤判成 one-off | 最大虧損歸因 → hard block |
| B. 風控沒針對尾部 | 好球被 stop、壞球 stop 不夠快 | 兩段式進場 + 波動度調整 |
| C. 評估指標沒對齊 | 只看分類準確不看交易結果 | 用高分段 precision 當 proxy |

### 5. 依賴關係

**結論**：不要選一個先做；用「最小可用 data + 立即開始 LLM eval」的並行策略

- LLM 選型**不依賴** market_data_client
- Paper trading 結算**依賴** market_data_client

### 6. Paper Trading 前置條件

**必要前置（沒有就不該上線）**：
- [ ] entry/exit 價格鏈完整
- [ ] 資料一致性定義（adjusted vs raw close）
- [ ] LLM freeze + 版本鎖定
- [ ] 成本/預算與降級策略
- [ ] 監控與告警可用
- [ ] Idempotency（同一事件重跑不重複下單）

**建議前置**：
- [ ] 交易層風控（單筆曝險上限）
- [ ] Shadow mode 先跑一段時間

## 風險與緩解

| 風險 | 會怎麼壞 | 緩解措施 |
|------|----------|----------|
| Golden Set 標註不一致 | 模型比較結果失真 | 先做 50 份校準；明確定義每個 flag |
| 沒快取就進入 A/B | 成本失控、迭代變慢 | W1 就上快取 |
| Sharpe 改善靠調參硬拉 | 可能只在特定期間有效 | 先做損失歸因 |
| market data 不穩 | PnL 不可信 | 多資料源備援 + fail-closed |
| 把 backfill 當 forward | 誤判績效 | 區分 replay vs forward |

## 關鍵成功因素

1. 用 Golden Set 把「假陽性」當頭號敵人
2. 把評估指標對齊交易（高分段 precision）
3. 快取 + 可重放 artifacts
4. **先做損失歸因，再做策略調參**
5. Freeze boundary 定義乾淨

## Week 1 執行任務

### PR8: market_data_client + entry fill

```python
# 目標 API
class MarketDataClient:
    async def get_close_price(symbol: str, date: date) -> Optional[float]
    async def get_ohlcv(symbol: str, start: date, end: date) -> DataFrame
```

### PR9: Eval Harness + 快取

```python
# 目標 CLI
aegis eval --model gpt-4o-mini --prompt v1.0.0 --golden-set golden_v0.json

# 輸出
- trade_candidate precision/recall
- key_flags 準確率
- 成本（$/event）
- latency（P95）
```

### PR10: Golden Set v0

```
50 份，分層抽樣：
- 明顯好球（一次性利空但體質好）
- 明顯壞球（結構性惡化）
- 灰色地帶（容易誤判）
```

## Week 1 執行進度

### 2026-02-02 更新

| 任務 | 狀態 | 說明 |
|------|------|------|
| **A1. market_data_client** | ✅ 完成 | PostgreSQL 客戶端，fail-closed 設計，11 單元測試 |
| **A2. entry fill** | ✅ 完成 | PENDING → OPEN 轉換邏輯，整合到 runner.py |
| **B1. LLM 快取** | ✅ 完成 | Cache key = (model, prompt_hash, transcript_hash)，10 單元測試 |
| **B2. Golden Set** | ✅ Framework | Schema + 評估 metrics，11 單元測試。待填入 50 份資料 |

**測試結果**: 150 passed, 3 skipped (integration tests)

**提交紀錄**:
- `31e6ae5`: PR8: LLM response cache for fast iteration
- `34e6710`: PR8: Golden Set framework for LLM evaluation

### Go/No-Go 關卡狀態

- [x] eval harness 可穩定重跑，結果可複現（快取機制完成）
- [x] market_data_client 穩定可用
- [ ] Golden Set v0 填入 50 份標註資料
- [ ] 端到端 paper trading 驗證

## 參考資料

- ChatGPT Pro Task ID: 9320
- 上傳檔案: rocket_screener_analysis.zip
- 相關 ADR: ADR-003-chatgpt-pro-iteration.md
