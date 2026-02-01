"""
Tests for PR3: Robust JSON Parser.

Tests the json_parser module's ability to handle common LLM output issues.
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from llm.json_parser import (
    extract_json_from_markdown,
    fix_trailing_commas,
    attempt_truncation_recovery,
    parse_llm_json,
    parse_or_default,
    parse_batch_score_response,
    NO_TRADE_DEFAULT,
)


class TestExtractJsonFromMarkdown:
    """Test markdown extraction functionality."""

    def test_json_code_block(self):
        """Should extract JSON from ```json code block."""
        text = '''Here is the analysis:
```json
{"score": 0.8, "trade_candidate": true}
```
That's the result.'''

        result = extract_json_from_markdown(text)
        assert result == '{"score": 0.8, "trade_candidate": true}'

    def test_generic_code_block(self):
        """Should extract JSON from generic ``` code block."""
        text = '''Analysis:
```
{"score": 0.5}
```'''

        result = extract_json_from_markdown(text)
        assert result == '{"score": 0.5}'

    def test_bare_json(self):
        """Should extract JSON without code blocks."""
        text = 'Some text {"score": 0.7} more text'

        result = extract_json_from_markdown(text)
        assert result == '{"score": 0.7}'

    def test_json_array(self):
        """Should extract JSON arrays."""
        text = 'The results are: [1, 2, 3] end'

        result = extract_json_from_markdown(text)
        assert result == '[1, 2, 3]'

    def test_no_json(self):
        """Should return original text if no JSON found."""
        text = "No JSON here at all"

        result = extract_json_from_markdown(text)
        assert result == text


class TestFixTrailingCommas:
    """Test trailing comma fixing."""

    def test_trailing_comma_in_object(self):
        """Should remove trailing comma in object."""
        text = '{"a": 1, "b": 2,}'

        result = fix_trailing_commas(text)
        assert result == '{"a": 1, "b": 2}'

    def test_trailing_comma_in_array(self):
        """Should remove trailing comma in array."""
        text = '[1, 2, 3,]'

        result = fix_trailing_commas(text)
        assert result == '[1, 2, 3]'

    def test_nested_trailing_commas(self):
        """Should handle nested trailing commas."""
        text = '{"items": [1, 2,], "nested": {"a": 1,},}'

        result = fix_trailing_commas(text)
        assert result == '{"items": [1, 2], "nested": {"a": 1}}'

    def test_no_trailing_commas(self):
        """Should not modify valid JSON."""
        text = '{"a": 1, "b": 2}'

        result = fix_trailing_commas(text)
        assert result == text


class TestTruncationRecovery:
    """Test truncation recovery functionality."""

    def test_missing_closing_brace(self):
        """Should close unclosed braces."""
        text = '{"score": 0.8'

        result = attempt_truncation_recovery(text)
        assert result is not None
        assert result.endswith("}")

    def test_missing_closing_bracket(self):
        """Should close unclosed brackets."""
        text = '{"items": [1, 2, 3'

        result = attempt_truncation_recovery(text)
        assert result is not None
        assert "]" in result
        assert "}" in result

    def test_balanced_json(self):
        """Should return None for balanced JSON."""
        text = '{"score": 0.8}'

        result = attempt_truncation_recovery(text)
        assert result is None

    def test_truncated_in_string(self):
        """Should close unclosed string."""
        text = '{"name": "test'

        result = attempt_truncation_recovery(text)
        assert result is not None
        # Should have an extra quote to close the string
        assert result.count('"') >= text.count('"')


class TestParseLlmJson:
    """Test the main parsing function."""

    def test_valid_json(self):
        """Should parse valid JSON."""
        text = '{"score": 0.8, "trade_candidate": true}'

        result = parse_llm_json(text)

        assert result.success is True
        assert result.data == {"score": 0.8, "trade_candidate": True}
        assert result.error is None

    def test_json_in_markdown(self):
        """Should parse JSON from markdown."""
        text = '''
```json
{"score": 0.7}
```
'''

        result = parse_llm_json(text)

        assert result.success is True
        assert result.data == {"score": 0.7}
        assert result.recovery_method == "markdown_extraction"

    def test_json_with_trailing_comma(self):
        """Should fix trailing comma."""
        text = '{"score": 0.6, "items": [1, 2,],}'

        result = parse_llm_json(text)

        assert result.success is True
        assert result.data["score"] == 0.6
        assert result.recovery_method == "trailing_comma_fix"

    def test_truncated_json_recovery(self):
        """Should recover truncated JSON."""
        text = '{"score": 0.5, "items": [1, 2'

        result = parse_llm_json(text)

        assert result.success is True
        assert result.data["score"] == 0.5
        assert result.recovery_method == "truncation_recovery"

    def test_completely_invalid(self):
        """Should fail gracefully on completely invalid input."""
        text = "This is not JSON at all, just random text"

        result = parse_llm_json(text)

        assert result.success is False
        assert result.error is not None

    def test_empty_input(self):
        """Should handle empty input."""
        result = parse_llm_json("")

        assert result.success is False
        assert "Empty" in result.error

    def test_real_llm_response_format(self):
        """Should parse realistic LLM batch_score response."""
        text = '''Based on the transcript analysis, here is my assessment:

```json
{
  "score": 0.82,
  "trade_candidate": true,
  "evidence_count": 3,
  "key_flags": {
    "guidance_positive": true,
    "revenue_beat": true,
    "margin_concern": false,
    "guidance_raised": false,
    "buyback_announced": true
  },
  "evidence_snippets": [
    {"quote": "Revenue grew 15%", "speaker": "CEO", "section": "prepared"},
    {"quote": "Raising guidance", "speaker": "CFO", "section": "qa"}
  ],
  "no_trade_reason": null
}
```

This indicates a strong buy signal.'''

        result = parse_llm_json(text)

        assert result.success is True
        assert result.data["score"] == 0.82
        assert result.data["trade_candidate"] is True
        assert len(result.data["evidence_snippets"]) == 2


class TestParseOrDefault:
    """Test the convenience wrapper function."""

    def test_success_returns_data(self):
        """Should return parsed data on success."""
        text = '{"score": 0.8}'
        default = {"score": 0.0}

        data, error = parse_or_default(text, default)

        assert data == {"score": 0.8}
        assert error is None

    def test_failure_returns_default(self):
        """Should return default on failure."""
        text = "invalid json"
        default = {"score": 0.0, "fallback": True}

        data, error = parse_or_default(text, default)

        assert data == default
        assert error is not None


class TestParseBatchScoreResponse:
    """Test the batch_score specific parser."""

    def test_valid_batch_score(self):
        """Should parse valid batch_score response."""
        text = '''{"score": 0.75, "trade_candidate": true, "evidence_count": 2}'''

        data, error = parse_batch_score_response(text)

        assert data["score"] == 0.75
        assert data["trade_candidate"] is True
        assert error is None

    def test_failure_returns_no_trade(self):
        """Should return NO_TRADE default on failure."""
        text = "completely invalid"

        data, error = parse_batch_score_response(text)

        assert data["score"] == 0.0
        assert data["trade_candidate"] is False
        assert "no_trade_reason" in data
        assert error is not None

    def test_no_trade_default_is_safe(self):
        """NO_TRADE_DEFAULT should be a safe conservative response."""
        assert NO_TRADE_DEFAULT["score"] == 0.0
        assert NO_TRADE_DEFAULT["trade_candidate"] is False
        assert NO_TRADE_DEFAULT["evidence_count"] == 0
        assert NO_TRADE_DEFAULT["key_flags"]["guidance_positive"] is False
        assert NO_TRADE_DEFAULT["key_flags"]["margin_concern"] is False


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_unicode_content(self):
        """Should handle unicode content."""
        text = '{"name": "测试", "symbol": "AAPL"}'

        result = parse_llm_json(text)

        assert result.success is True
        assert result.data["name"] == "测试"

    def test_nested_quotes(self):
        """Should handle nested quotes in strings."""
        text = '{"quote": "He said \\"buy\\" strongly"}'

        result = parse_llm_json(text)

        assert result.success is True
        assert "buy" in result.data["quote"]

    def test_large_numbers(self):
        """Should handle large numbers."""
        text = '{"revenue": 123456789012345}'

        result = parse_llm_json(text)

        assert result.success is True
        assert result.data["revenue"] == 123456789012345

    def test_boolean_values(self):
        """Should handle boolean values correctly."""
        text = '{"positive": true, "negative": false}'

        result = parse_llm_json(text)

        assert result.success is True
        assert result.data["positive"] is True
        assert result.data["negative"] is False

    def test_null_values(self):
        """Should handle null values."""
        text = '{"reason": null}'

        result = parse_llm_json(text)

        assert result.success is True
        assert result.data["reason"] is None
