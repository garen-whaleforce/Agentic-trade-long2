# Skill: backtest-ssot-whaleforce

## 目的
確保所有回測績效指標（CAGR、Sharpe、win rate 等）只來自 Whaleforce Backtest API，禁止本地自算。

## 何時使用
- 執行回測
- 評估策略績效
- 比較不同版本的策略
- 產生績效報告

## 規則

### 1. 唯一績效來源
- **SSOT（Single Source of Truth）**: Whaleforce Backtest API
- **本地只能做**:
  - 準備 signals/positions 清單
  - 格式化 API 請求
  - 解析 API 回應
- **禁止本地計算**:
  - CAGR
  - Sharpe ratio
  - Win rate
  - Maximum drawdown
  - 任何基於價格的績效指標

### 2. API 呼叫流程
```python
# Step 1: 準備 signals
signals = generate_signals(events, llm_scores)

# Step 2: 轉換成 API 格式
positions = signals_to_positions(signals)

# Step 3: 呼叫 Backtest API
result = whaleforce_backtest_client.run_backtest(
    positions=positions,
    start_date="2017-01-01",
    end_date="2025-12-31",
    strategy_id="earnings_momentum_v1"
)

# Step 4: 直接使用 API 返回的績效指標
cagr = result.cagr  # 來自 API
sharpe = result.sharpe_ratio  # 來自 API
win_rate = result.win_rate  # 來自 API
```

### 3. 禁止的操作
```python
# 禁止：自己算 CAGR
def calculate_cagr(returns):  # 不要這樣做
    pass

# 禁止：自己算 Sharpe
def calculate_sharpe(returns, risk_free_rate):  # 不要這樣做
    pass
```

### 4. 必須記錄
- `backtest_request.json`: 送出的請求（含 positions）
- `backtest_result.json`: API 返回的原始結果
- `report.md`: 格式化的績效報告

## 產出 Artifacts
```
runs/<run_id>/
├── backtest_request.json
├── backtest_result.json
└── report.md
```

## 驗收命令
```bash
# 確認 backtest 結果來自 API
pytest tests/backtest/test_whaleforce_integration.py -v

# 確認沒有本地績效計算
grep -r "calculate_cagr\|calculate_sharpe" backend/ && exit 1 || echo "OK"
```

## 報告格式
```markdown
# Backtest Report

## Run Info
- Run ID: {run_id}
- Date Range: 2017-01-01 to 2025-12-31
- Strategy: earnings_momentum_v1
- Prompt Version: v1.2.3

## Performance (from Whaleforce API)
| Metric | Value |
|--------|-------|
| CAGR | 38.5% |
| Sharpe | 2.15 |
| Win Rate | 78.2% |
| Max Drawdown | -15.3% |
| Total Trades | 847 |
| Trades/Year | 94 |

## Data Source
- API Endpoint: whaleforce.com/api/v1/backtest
- Request ID: {api_request_id}
- Timestamp: {timestamp}
```
