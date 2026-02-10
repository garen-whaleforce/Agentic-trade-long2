"""
LLM Response Cache.

Caches LLM responses to avoid redundant API calls during evaluation and development.

Cache key: (model, prompt_hash, transcript_hash)
This ensures:
- Same model + same prompt + same transcript = cache hit
- Changing any component = cache miss (correct behavior)

Per ChatGPT Pro recommendation:
- Cache is critical for fast iteration during LLM selection
- Second run should have >90% cache hit rate
"""

import hashlib
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from pydantic import BaseModel

from core.config import settings


logger = logging.getLogger("llm_cache")


class CacheEntry(BaseModel):
    """A cached LLM response."""

    cache_key: str
    model: str
    prompt_hash: str
    transcript_hash: str
    created_at: str

    # Request
    rendered_prompt: str
    parameters: Dict[str, Any]

    # Response
    raw_output: Dict[str, Any]
    token_usage: Dict[str, int]
    cost_usd: float
    latency_ms: int


class LLMCache:
    """
    File-based cache for LLM responses.

    Structure:
    cache_dir/
        {cache_key[:2]}/  # First 2 chars for sharding
            {cache_key}.json
    """

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        enabled: bool = True,
    ):
        """
        Initialize the cache.

        Args:
            cache_dir: Directory for cache files (default from settings)
            enabled: Whether caching is enabled
        """
        self.cache_dir = Path(cache_dir or settings.cache_dir) / "llm_cache"
        self.enabled = enabled
        self._stats = {
            "hits": 0,
            "misses": 0,
            "writes": 0,
        }

        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"LLM cache initialized at {self.cache_dir}")

    @staticmethod
    def compute_cache_key(
        model: str,
        prompt_hash: str,
        transcript_hash: str,
    ) -> str:
        """
        Compute cache key from components.

        Args:
            model: Model name (e.g., "gpt-4o-mini")
            prompt_hash: Hash of prompt template content
            transcript_hash: Hash of transcript content

        Returns:
            Cache key (SHA256 of combined components)
        """
        content = f"{model}|{prompt_hash}|{transcript_hash}"
        return hashlib.sha256(content.encode()).hexdigest()

    @staticmethod
    def compute_transcript_hash(transcript_text: str) -> str:
        """
        Compute hash of transcript content.

        Args:
            transcript_text: Full transcript text

        Returns:
            SHA256 hash (first 16 chars)
        """
        return hashlib.sha256(transcript_text.encode()).hexdigest()[:16]

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key."""
        shard = cache_key[:2]
        return self.cache_dir / shard / f"{cache_key}.json"

    def get(
        self,
        model: str,
        prompt_hash: str,
        transcript_hash: str,
    ) -> Optional[CacheEntry]:
        """
        Get cached response if exists.

        Args:
            model: Model name
            prompt_hash: Hash of prompt template
            transcript_hash: Hash of transcript

        Returns:
            CacheEntry if found, None otherwise
        """
        if not self.enabled:
            return None

        cache_key = self.compute_cache_key(model, prompt_hash, transcript_hash)
        cache_path = self._get_cache_path(cache_key)

        if cache_path.exists():
            try:
                with open(cache_path, "r") as f:
                    data = json.load(f)
                    entry = CacheEntry(**data)
                    self._stats["hits"] += 1
                    logger.debug(f"Cache hit: {cache_key[:8]}...")
                    return entry
            except Exception as e:
                logger.warning(f"Cache read error for {cache_key[:8]}: {e}")

        self._stats["misses"] += 1
        logger.debug(f"Cache miss: {cache_key[:8]}...")
        return None

    def set(
        self,
        model: str,
        prompt_hash: str,
        transcript_hash: str,
        rendered_prompt: str,
        parameters: Dict[str, Any],
        raw_output: Dict[str, Any],
        token_usage: Dict[str, int],
        cost_usd: float,
        latency_ms: int,
    ) -> str:
        """
        Store response in cache.

        Args:
            model: Model name
            prompt_hash: Hash of prompt template
            transcript_hash: Hash of transcript
            rendered_prompt: Full rendered prompt
            parameters: LLM call parameters
            raw_output: Raw LLM response
            token_usage: Token usage stats
            cost_usd: Cost in USD
            latency_ms: Latency in milliseconds

        Returns:
            Cache key
        """
        if not self.enabled:
            return ""

        cache_key = self.compute_cache_key(model, prompt_hash, transcript_hash)
        cache_path = self._get_cache_path(cache_key)

        entry = CacheEntry(
            cache_key=cache_key,
            model=model,
            prompt_hash=prompt_hash,
            transcript_hash=transcript_hash,
            created_at=datetime.utcnow().isoformat(),
            rendered_prompt=rendered_prompt,
            parameters=parameters,
            raw_output=raw_output,
            token_usage=token_usage,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )

        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w") as f:
                json.dump(entry.model_dump(), f, indent=2)
            self._stats["writes"] += 1
            logger.debug(f"Cache write: {cache_key[:8]}...")
        except Exception as e:
            logger.warning(f"Cache write error for {cache_key[:8]}: {e}")

        return cache_key

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0

        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "writes": self._stats["writes"],
            "hit_rate": hit_rate,
            "total_requests": total,
        }

    def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        if not self.enabled or not self.cache_dir.exists():
            return 0

        count = 0
        for shard_dir in self.cache_dir.iterdir():
            if shard_dir.is_dir():
                for cache_file in shard_dir.glob("*.json"):
                    cache_file.unlink()
                    count += 1
                # Remove empty shard directory
                if not any(shard_dir.iterdir()):
                    shard_dir.rmdir()

        logger.info(f"Cleared {count} cache entries")
        return count


# Global cache instance
_cache: Optional[LLMCache] = None


def get_llm_cache() -> LLMCache:
    """Get the global LLM cache instance."""
    global _cache
    if _cache is None:
        _cache = LLMCache()
    return _cache


def reset_llm_cache() -> None:
    """Reset the global cache (for testing)."""
    global _cache
    _cache = None
