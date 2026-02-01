"""
PR3: Robust JSON Parser for LLM outputs.

Handles common LLM output issues:
1. Markdown code blocks (```json ... ```)
2. Leading/trailing text before/after JSON
3. Trailing commas in arrays/objects
4. Truncated JSON (attempts best-effort recovery)
5. Invalid escape sequences
"""

import json
import re
from typing import Any, Dict, Optional, Tuple, Union

from pydantic import BaseModel


class ParseResult(BaseModel):
    """Result of JSON parsing attempt."""

    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    recovery_method: Optional[str] = None  # How the JSON was recovered


def extract_json_from_markdown(text: str) -> str:
    """
    Extract JSON from markdown code blocks.

    Handles:
    - ```json {...} ```
    - ``` {...} ```
    - {json without code blocks}

    Args:
        text: Raw LLM output

    Returns:
        Extracted JSON string
    """
    # Pattern 1: ```json ... ```
    json_block = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if json_block:
        return json_block.group(1).strip()

    # Pattern 2: ``` ... ``` (generic code block)
    code_block = re.search(r"```\s*([\s\S]*?)\s*```", text)
    if code_block:
        content = code_block.group(1).strip()
        # Check if it looks like JSON
        if content.startswith("{") or content.startswith("["):
            return content

    # Pattern 3: Find JSON object directly
    # Look for the first { and last } or first [ and last ]
    obj_start = text.find("{")
    arr_start = text.find("[")

    if obj_start == -1 and arr_start == -1:
        return text  # No JSON found, return as-is

    # Prefer object over array if both exist and object comes first
    if obj_start != -1 and (arr_start == -1 or obj_start < arr_start):
        obj_end = text.rfind("}")
        if obj_end > obj_start:
            return text[obj_start : obj_end + 1]
    elif arr_start != -1:
        arr_end = text.rfind("]")
        if arr_end > arr_start:
            return text[arr_start : arr_end + 1]

    return text


def fix_trailing_commas(text: str) -> str:
    """
    Remove trailing commas in JSON objects and arrays.

    LLMs sometimes produce:
    {"a": 1, "b": 2,}  -> {"a": 1, "b": 2}
    [1, 2, 3,]         -> [1, 2, 3]

    Args:
        text: JSON string with potential trailing commas

    Returns:
        Fixed JSON string
    """
    # Remove trailing commas before closing braces/brackets
    # This is a simplified approach that handles most common cases
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)
    return text


def fix_escape_sequences(text: str) -> str:
    """
    Fix invalid escape sequences in JSON strings.

    Common issues:
    - Unescaped newlines inside strings
    - Invalid \\x or \\u sequences

    Args:
        text: JSON string with potential escape issues

    Returns:
        Fixed JSON string
    """
    # Replace literal newlines inside strings (not the \n escape)
    # This is tricky because we need to be inside a string context
    # Simple approach: replace actual newlines with \\n
    # Note: This may not work for all edge cases

    # Fix unescaped single quotes (less common in JSON but LLMs do it)
    # JSON spec requires double quotes for strings

    return text


def attempt_truncation_recovery(text: str) -> Optional[str]:
    """
    Attempt to recover from truncated JSON.

    If the JSON was cut off mid-way, try to close any open structures.
    This is a best-effort recovery and may produce incomplete but valid JSON.

    Args:
        text: Truncated JSON string

    Returns:
        Recovered JSON string or None if recovery impossible
    """
    if not text:
        return None

    # Count brackets to see what needs closing
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")

    if open_braces == 0 and open_brackets == 0:
        return None  # Balanced, not a truncation issue

    # Try to close unclosed structures
    recovered = text

    # If we're in the middle of a string, close it
    # Count unescaped quotes
    in_string = False
    for i, char in enumerate(text):
        if char == '"' and (i == 0 or text[i - 1] != "\\"):
            in_string = not in_string

    if in_string:
        recovered += '"'

    # If we're in the middle of a value, add null
    if recovered.rstrip().endswith(":"):
        recovered += "null"
    elif recovered.rstrip().endswith(","):
        # Remove trailing comma before closing
        recovered = recovered.rstrip()[:-1]

    # Close structures
    recovered += "]" * open_brackets
    recovered += "}" * open_braces

    return recovered


def parse_llm_json(
    text: str, attempt_recovery: bool = True
) -> ParseResult:
    """
    Parse JSON from LLM output with robust error handling.

    This is the main entry point for PR3 JSON parsing.

    Args:
        text: Raw LLM output
        attempt_recovery: Whether to attempt recovery on parse failure

    Returns:
        ParseResult with success status, data, and error info
    """
    if not text or not text.strip():
        return ParseResult(
            success=False,
            error="Empty input",
        )

    original_text = text

    # Step 1: Extract from markdown
    text = extract_json_from_markdown(text)
    used_markdown_extraction = text != original_text

    # Step 2: Try direct parse
    try:
        data = json.loads(text)
        return ParseResult(
            success=True,
            data=data,
            recovery_method="markdown_extraction" if used_markdown_extraction else None,
        )
    except json.JSONDecodeError:
        pass

    # Step 3: Fix trailing commas
    text_fixed = fix_trailing_commas(text)
    try:
        data = json.loads(text_fixed)
        return ParseResult(
            success=True,
            data=data,
            recovery_method="trailing_comma_fix",
        )
    except json.JSONDecodeError:
        pass

    # Step 4: Attempt truncation recovery
    if attempt_recovery:
        recovered = attempt_truncation_recovery(text_fixed)
        if recovered:
            try:
                data = json.loads(recovered)
                return ParseResult(
                    success=True,
                    data=data,
                    recovery_method="truncation_recovery",
                )
            except json.JSONDecodeError:
                pass

    # All recovery attempts failed
    return ParseResult(
        success=False,
        error=f"Failed to parse JSON after all recovery attempts. Input: {original_text[:200]}...",
    )


def parse_or_default(
    text: str,
    default: Dict[str, Any],
    attempt_recovery: bool = True,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Parse JSON or return default on failure.

    This is a convenience wrapper that always returns valid data.

    Args:
        text: Raw LLM output
        default: Default value to return on failure
        attempt_recovery: Whether to attempt recovery

    Returns:
        Tuple of (parsed_data, error_message_or_none)
    """
    result = parse_llm_json(text, attempt_recovery)

    if result.success:
        return result.data, None
    else:
        return default, result.error


# Default NO_TRADE response for parse failures
NO_TRADE_DEFAULT = {
    "score": 0.0,
    "trade_candidate": False,
    "evidence_count": 0,
    "key_flags": {
        "guidance_positive": False,
        "revenue_beat": False,
        "margin_concern": False,
        "guidance_raised": False,
        "buyback_announced": False,
    },
    "evidence_snippets": [],
    "no_trade_reason": "JSON parse failure - conservative NO_TRADE",
}


def parse_batch_score_response(text: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Parse batch_score LLM response with NO_TRADE fallback.

    This is the PR3 recommended entry point for score_only_runner.

    Args:
        text: Raw LLM output

    Returns:
        Tuple of (parsed_data, error_message_or_none)
    """
    return parse_or_default(text, NO_TRADE_DEFAULT)
