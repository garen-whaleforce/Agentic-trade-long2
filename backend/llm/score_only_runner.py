"""
Score-Only Runner.

Runs batch_score analysis with minimal output tokens for cost efficiency.
"""

import hashlib
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any, Union

from pydantic import BaseModel, ValidationError

from core.config import settings
from data.transcript_pack_builder import TranscriptPack
from schemas.llm_output import BatchScoreOutput, Evidence, KeyFlags
from .routing import LLMRouter, LLMConfig, get_llm_router


class LLMRequest(BaseModel):
    """Record of an LLM request."""

    event_id: str
    timestamp: str
    model: str
    prompt_template_id: str
    prompt_hash: str
    rendered_prompt: str
    parameters: Dict[str, Any]


class LLMResponse(BaseModel):
    """Record of an LLM response."""

    event_id: str
    timestamp: str
    model: str
    raw_response: Dict[str, Any]
    parsed_output: Optional[BatchScoreOutput] = None
    parse_error: Optional[str] = None
    token_usage: Dict[str, int]
    cost_usd: float
    latency_ms: int


class ScoreOnlyRunner:
    """
    Runs batch_score analysis.

    Features:
    - Low cost (< $0.01/event target)
    - Strict JSON schema enforcement
    - Deterministic (temperature=0)
    - Evidence triangulation enforcement
    """

    PROMPT_TEMPLATE = """Analyze the following earnings call transcript for {symbol} ({company_name}).
Fiscal Period: Q{quarter} {year}
Event Date: {event_date}

{transcript_content}

Based on the transcript above, provide your analysis in the specified JSON format.
Remember:
- At least 2 evidence quotes from different speakers/sections
- If insufficient evidence, set trade_candidate to false
- Keep response under 300 tokens"""

    SYSTEM_PROMPT = """You are a financial analyst specializing in earnings call analysis for quantitative trading.
Your task is to evaluate whether an earnings call transcript indicates a potential LONG opportunity.

CRITICAL RULES:
1. NO LOOKAHEAD: Only use information available on or before the event date.
2. EVIDENCE REQUIRED: Every key finding needs at least 2 supporting quotes from DIFFERENT speakers OR sections.
3. CONSERVATIVE BIAS: When in doubt, do NOT recommend trading.
4. NO FABRICATION: Never invent facts.
5. OUTPUT JSON ONLY: Respond with valid JSON matching the schema. No other text.

JSON Schema:
{
  "score": <float 0.0-1.0>,
  "trade_candidate": <boolean>,
  "evidence_count": <integer>,
  "key_flags": {
    "guidance_positive": <boolean>,
    "revenue_beat": <boolean>,
    "margin_concern": <boolean>,
    "guidance_raised": <boolean>,
    "buyback_announced": <boolean>
  },
  "evidence_snippets": [{"quote": "<string>", "speaker": "<string>", "section": "<prepared|qa>"}],
  "no_trade_reason": "<string or null>"
}"""

    def __init__(
        self,
        model: Optional[str] = None,
        router: Optional[LLMRouter] = None,
        prompt_version: str = "v1.0.0",
    ):
        """
        Initialize the runner.

        Args:
            model: Override model (optional, uses router default if not set)
            router: LLM router instance
            prompt_version: Version of the prompt
        """
        self.router = router or get_llm_router()
        self.prompt_version = prompt_version
        self._model_override = model

    def _render_prompt(self, pack: TranscriptPack) -> str:
        """Render the user prompt with transcript pack."""
        return self.PROMPT_TEMPLATE.format(
            symbol=pack.symbol,
            company_name=pack.company_name,
            quarter=pack.fiscal_quarter,
            year=pack.fiscal_year,
            event_date=pack.event_date,
            transcript_content=pack.to_llm_context(),
        )

    def _calculate_prompt_hash(self, prompt: str) -> str:
        """Calculate hash of the rendered prompt."""
        return "sha256:" + hashlib.sha256(prompt.encode()).hexdigest()[:16]

    def _parse_response(self, raw_response: str) -> BatchScoreOutput:
        """
        Parse and validate LLM response.

        Args:
            raw_response: Raw JSON string from LLM

        Returns:
            Validated BatchScoreOutput

        Raises:
            ValueError: If response is invalid
        """
        try:
            # Parse JSON
            data = json.loads(raw_response)

            # Validate with Pydantic
            output = BatchScoreOutput(
                score=data.get("score", 0),
                trade_candidate=data.get("trade_candidate", False),
                evidence_count=data.get("evidence_count", 0),
                key_flags=KeyFlags(**data.get("key_flags", {})),
                evidence_snippets=[
                    Evidence(**e) for e in data.get("evidence_snippets", [])
                ],
                no_trade_reason=data.get("no_trade_reason"),
            )

            return output

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {str(e)}")
        except ValidationError as e:
            raise ValueError(f"Schema validation failed: {str(e)}")

    async def run(
        self,
        event_id: str,
        pack: TranscriptPack,
        use_cache: bool = True,
    ) -> tuple[LLMRequest, LLMResponse]:
        """
        Run batch_score analysis.

        Args:
            event_id: Event identifier
            pack: Transcript pack
            use_cache: Whether to use cached results

        Returns:
            Tuple of (LLMRequest, LLMResponse)
        """
        config = self.router.get_config("batch_score", self.prompt_version)

        # Override model if specified
        if self._model_override:
            config = LLMConfig(
                model=self._model_override,
                temperature=config.temperature,
                max_input_tokens=config.max_input_tokens,
                max_output_tokens=config.max_output_tokens,
                cost_per_1k_input=config.cost_per_1k_input,
                cost_per_1k_output=config.cost_per_1k_output,
                response_format=config.response_format,
            )

        # Render prompt
        user_prompt = self._render_prompt(pack)
        prompt_hash = self._calculate_prompt_hash(user_prompt)

        # Create request record
        request = LLMRequest(
            event_id=event_id,
            timestamp=datetime.utcnow().isoformat(),
            model=config.model,
            prompt_template_id=f"batch_score_{self.prompt_version}",
            prompt_hash=prompt_hash,
            rendered_prompt=user_prompt,
            parameters={
                "temperature": config.temperature,
                "max_tokens": config.max_output_tokens,
                "response_format": config.response_format,
            },
        )

        # Call LLM via litellm
        start_time = time.time()

        try:
            import litellm

            # Configure litellm
            litellm.drop_params = True  # Drop unsupported params gracefully

            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

            # Make actual API call
            llm_response = await litellm.acompletion(
                model=config.model,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_output_tokens,
                response_format={"type": "json_object"} if config.response_format == "json_object" else None,
                timeout=30,
            )

            # Extract response content
            raw_text = llm_response.choices[0].message.content
            raw_output = json.loads(raw_text)

            # Get actual token usage
            input_tokens = llm_response.usage.prompt_tokens
            output_tokens = llm_response.usage.completion_tokens

        except ImportError:
            # Fallback if litellm not installed - use stub for testing
            raw_output = {
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
                "no_trade_reason": "LiteLLM not installed - stub response",
            }
            input_tokens = len(user_prompt) // 4
            output_tokens = 100

        except Exception as e:
            # On any LLM error, return conservative NO_TRADE
            raw_output = {
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
                "no_trade_reason": f"LLM error: {str(e)}",
            }
            input_tokens = len(user_prompt) // 4
            output_tokens = 50

        latency_ms = int((time.time() - start_time) * 1000)

        # Parse response
        try:
            parsed_output = self._parse_response(json.dumps(raw_output))
            parse_error = None
        except ValueError as e:
            parsed_output = None
            parse_error = str(e)

        # Use actual token counts from LLM response (already set above)
        # Only fallback to estimation if tokens weren't set by the LLM call
        cost = self.router.calculate_cost(config, input_tokens, output_tokens)

        # Create response record
        response = LLMResponse(
            event_id=event_id,
            timestamp=datetime.utcnow().isoformat(),
            model=config.model,
            raw_response=raw_output,
            parsed_output=parsed_output,
            parse_error=parse_error,
            token_usage={
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
            },
            cost_usd=cost,
            latency_ms=latency_ms,
        )

        return request, response


    async def analyze(
        self,
        event_id: str,
        transcript: Any,
        mode: str = "batch_score",
    ) -> Dict[str, Any]:
        """
        Analyze an earnings call transcript.

        This is the unified interface for all callers.

        Args:
            event_id: Event identifier
            transcript: TranscriptResponse or TranscriptPack
            mode: Analysis mode (batch_score or full_audit)

        Returns:
            Dict with score, trade_candidate, evidence, etc.
        """
        from data.transcript_pack_builder import TranscriptPackBuilder, TranscriptPack

        # Convert transcript to pack if needed
        if isinstance(transcript, TranscriptPack):
            pack = transcript
        else:
            # Build pack from transcript response
            builder = TranscriptPackBuilder()
            pack = builder.build(transcript)

        # Run analysis
        request, response = await self.run(event_id, pack)

        # Return dict format for compatibility
        result = {
            "event_id": event_id,
            "score": response.parsed_output.score if response.parsed_output else 0.0,
            "trade_candidate": response.parsed_output.trade_candidate if response.parsed_output else False,
            "evidence_count": response.parsed_output.evidence_count if response.parsed_output else 0,
            "key_flags": response.parsed_output.key_flags.model_dump() if response.parsed_output else {},
            "evidence_snippets": [e.model_dump() for e in response.parsed_output.evidence_snippets] if response.parsed_output else [],
            "no_trade_reason": response.parsed_output.no_trade_reason if response.parsed_output else response.parse_error,
            "cost_usd": response.cost_usd,
            "latency_ms": response.latency_ms,
            "model": response.model,
            "prompt_version": self.prompt_version,
        }

        return result


async def run_batch_score(
    event_id: str,
    pack: TranscriptPack,
) -> tuple[LLMRequest, LLMResponse]:
    """Convenience function to run batch_score analysis."""
    runner = ScoreOnlyRunner()
    return await runner.run(event_id, pack)
