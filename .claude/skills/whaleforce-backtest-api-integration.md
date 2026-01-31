# Skill: whaleforce-backtest-api-integration

## 目的
規範與 Whaleforce Backtest API 的整合方式，這是績效計算的唯一來源（SSOT）。

## 何時使用
- 執行回測
- 取得績效指標（CAGR、Sharpe、win rate 等）
- 取得交易明細

## API Endpoints

### 1. 執行回測
```
POST /api/v1/backtest
```

Request:
```json
{
  "strategy_id": "earnings_momentum_v1",
  "positions": [
    {
      "symbol": "AAPL",
      "entry_date": "2024-01-26",
      "exit_date": "2024-03-08",
      "direction": "long",
      "sizing": "equal_weight"
    }
  ],
  "config": {
    "start_date": "2017-01-01",
    "end_date": "2025-12-31",
    "initial_capital": 1000000,
    "commission_rate": 0.001,
    "slippage_model": "fixed_bps",
    "slippage_bps": 5
  }
}
```

Response:
```json
{
  "backtest_id": "bt_20260131_abc123",
  "strategy_id": "earnings_momentum_v1",
  "status": "completed",
  "performance": {
    "cagr": 0.385,
    "sharpe_ratio": 2.15,
    "sortino_ratio": 2.85,
    "max_drawdown": -0.153,
    "win_rate": 0.782,
    "profit_factor": 2.34,
    "total_return": 12.45,
    "annualized_volatility": 0.18
  },
  "trade_stats": {
    "total_trades": 847,
    "winning_trades": 662,
    "losing_trades": 185,
    "avg_win": 0.082,
    "avg_loss": -0.045,
    "avg_holding_days": 30,
    "trades_per_year": 94
  },
  "yearly_returns": {
    "2017": 0.42,
    "2018": 0.28,
    "2019": 0.51,
    "2020": 0.38,
    "2021": 0.45,
    "2022": 0.22,
    "2023": 0.35,
    "2024": 0.41,
    "2025": 0.33
  },
  "trades": [
    {
      "trade_id": "t_001",
      "symbol": "AAPL",
      "entry_date": "2024-01-26",
      "entry_price": 192.45,
      "exit_date": "2024-03-08",
      "exit_price": 215.30,
      "return": 0.1187,
      "pnl": 22850
    }
  ]
}
```

### 2. 取得 Trading Calendar
```
GET /api/v1/trading-calendar?start=YYYY-MM-DD&end=YYYY-MM-DD
```

Response:
```json
{
  "trading_days": [
    "2024-01-02",
    "2024-01-03",
    "2024-01-04"
  ],
  "holidays": [
    {
      "date": "2024-01-01",
      "name": "New Year's Day"
    }
  ]
}
```

## Backend Client

```python
# backend/services/whaleforce_backtest_client.py

class WhaleforceBacktestClient:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url

    async def run_backtest(
        self,
        strategy_id: str,
        positions: List[Position],
        config: BacktestConfig
    ) -> BacktestResult:
        """執行回測，返回績效指標"""
        pass

    async def get_trading_calendar(
        self,
        start_date: date,
        end_date: date
    ) -> TradingCalendar:
        """取得交易日曆"""
        pass

    def is_trading_day(self, d: date) -> bool:
        """檢查是否為交易日"""
        pass

    def next_trading_day(self, d: date) -> date:
        """取得下一個交易日"""
        pass

    def add_trading_days(self, d: date, n: int) -> date:
        """加 N 個交易日"""
        pass
```

## Position Schema

```python
class Position(BaseModel):
    symbol: str
    entry_date: date           # T+1 close
    exit_date: date            # T+30 close
    direction: Literal["long"] # 只做多
    sizing: Literal["equal_weight", "score_weighted"] = "equal_weight"
    signal_id: str             # 對應的 signal ID
    score: float               # LLM score
```

## 禁止的操作

```python
# 禁止：本地計算 CAGR
def calculate_cagr_locally(returns):  # 不要這樣做！
    pass

# 禁止：本地計算 Sharpe
def calculate_sharpe_locally(returns):  # 不要這樣做！
    pass

# 正確：只使用 API 返回值
result = await client.run_backtest(...)
cagr = result.performance.cagr  # 來自 API
sharpe = result.performance.sharpe_ratio  # 來自 API
```

## 錯誤處理

```python
class BacktestAPIError(Exception):
    pass

class InvalidPositionError(BacktestAPIError):
    """無效的 position（如日期錯誤）"""
    pass

class InsufficientDataError(BacktestAPIError):
    """缺少價格資料"""
    pass
```

## 產出 Artifacts

每次回測必須保存：
```
runs/<run_id>/
├── backtest_request.json   # 完整的 API 請求
├── backtest_result.json    # 完整的 API 回應
└── report.md               # 格式化報告
```

## 驗收命令

```bash
# 測試 API 連通性
python -m backend.services.whaleforce_backtest_client --test

# 執行整合測試
pytest tests/integration/test_whaleforce_backtest.py -v

# 確認沒有本地績效計算
grep -r "calculate_cagr\|calculate_sharpe\|calculate_return" backend/ && exit 1 || echo "OK"
```

## 注意事項

1. **所有績效數字只能來自 API**
2. **保存完整的請求與回應**
3. **不要快取績效結果**（每次都要重跑以確保一致性）
4. **Trading calendar 可以快取**（不常變動）
