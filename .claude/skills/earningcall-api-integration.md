# Skill: earningcall-api-integration

## 目的
規範與 Earnings Call API 的整合方式，取得 calendar、company events、transcript。

## 何時使用
- 取得特定日期的 earnings calls 清單
- 取得特定公司的 earnings call 歷史
- 取得 transcript 內容

## API Endpoints

**Note:** Paths are relative to `EARNINGSCALL_API_URL` base URL.

### 1. 取得日期的 Earnings Calls
```
GET /calendar?date=YYYY-MM-DD
```

Response:
```json
{
  "date": "2024-01-25",
  "events": [
    {
      "event_id": "evt_aapl_2024q1",
      "symbol": "AAPL",
      "company_name": "Apple Inc.",
      "fiscal_year": 2024,
      "fiscal_quarter": 1,
      "event_time": "2024-01-25T16:30:00Z",
      "transcript_available": true
    }
  ]
}
```

### 2. 取得公司的 Earnings Call 歷史
```
GET /company/{symbol}/events?start=YYYY-MM-DD&end=YYYY-MM-DD
```

Response:
```json
{
  "symbol": "AAPL",
  "company_name": "Apple Inc.",
  "events": [
    {
      "event_id": "evt_aapl_2024q1",
      "fiscal_year": 2024,
      "fiscal_quarter": 1,
      "event_date": "2024-01-25",
      "transcript_available": true
    }
  ]
}
```

### 3. 取得 Transcript
```
GET /transcript/{event_id}
```

Response:
```json
{
  "event_id": "evt_aapl_2024q1",
  "symbol": "AAPL",
  "fiscal_year": 2024,
  "fiscal_quarter": 1,
  "event_date": "2024-01-25",
  "sections": {
    "prepared_remarks": {
      "speakers": [
        {
          "name": "Tim Cook",
          "role": "CEO",
          "paragraphs": [
            {"index": 0, "text": "Good afternoon everyone..."},
            {"index": 1, "text": "We're pleased to report..."}
          ]
        },
        {
          "name": "Luca Maestri",
          "role": "CFO",
          "paragraphs": [
            {"index": 0, "text": "Thank you Tim..."}
          ]
        }
      ]
    },
    "qa_session": {
      "exchanges": [
        {
          "analyst": "John Doe",
          "firm": "Goldman Sachs",
          "question": "Can you elaborate on...",
          "answers": [
            {"speaker": "Tim Cook", "text": "..."}
          ]
        }
      ]
    }
  },
  "metadata": {
    "word_count": 12500,
    "duration_minutes": 60
  }
}
```

## Backend Client

```python
# backend/services/earningscall_client.py

class EarningsCallClient:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url

    async def get_calendar(self, date: date) -> CalendarResponse:
        """取得特定日期的 earnings calls"""
        pass

    async def get_company_events(
        self,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> CompanyEventsResponse:
        """取得公司的 earnings call 歷史"""
        pass

    async def get_transcript(self, event_id: str) -> TranscriptResponse:
        """取得 transcript"""
        pass
```

## Contract Tests

```python
# tests/integration/test_earningscall_api.py

def test_calendar_response_schema():
    """驗證 calendar API 回應格式"""
    response = client.get_calendar(date(2024, 1, 25))
    assert "date" in response
    assert "events" in response
    assert isinstance(response["events"], list)

def test_transcript_response_schema():
    """驗證 transcript API 回應格式"""
    response = client.get_transcript("evt_aapl_2024q1")
    assert "event_id" in response
    assert "sections" in response
    assert "prepared_remarks" in response["sections"]
```

## 錯誤處理

```python
class EarningsCallAPIError(Exception):
    pass

class TranscriptNotAvailableError(EarningsCallAPIError):
    """Transcript 尚未公開"""
    pass

class EventNotFoundError(EarningsCallAPIError):
    """找不到指定的 event"""
    pass
```

## 快取策略

- Calendar data: 快取 24 小時
- Company events: 快取 1 小時
- Transcript: 永久快取（transcript 內容不會改變）

## 產出 Artifacts

- `data/cache/calendar/YYYY-MM-DD.json`
- `data/cache/transcripts/{event_id}.json`

## 驗收命令

```bash
# 測試 API 連通性
python -m backend.services.earningscall_client --test

# 執行 contract tests
pytest tests/integration/test_earningscall_api.py -v
```
