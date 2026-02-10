"""
Tests for LLM Response Cache.

Verifies:
1. Cache key computation is deterministic
2. Cache hit/miss behavior
3. Cache stats tracking
4. Cache clear functionality
"""

import pytest
import tempfile
from pathlib import Path

from backend.llm.cache import LLMCache, get_llm_cache, reset_llm_cache


class TestLLMCacheUnit:
    """Unit tests for LLM cache."""

    def setup_method(self):
        """Reset global cache before each test."""
        reset_llm_cache()

    def test_compute_cache_key_deterministic(self):
        """Same inputs should produce same cache key."""
        key1 = LLMCache.compute_cache_key(
            model="gpt-4o-mini",
            prompt_hash="abc123",
            transcript_hash="def456",
        )
        key2 = LLMCache.compute_cache_key(
            model="gpt-4o-mini",
            prompt_hash="abc123",
            transcript_hash="def456",
        )
        assert key1 == key2

    def test_compute_cache_key_different_for_different_inputs(self):
        """Different inputs should produce different cache keys."""
        key1 = LLMCache.compute_cache_key(
            model="gpt-4o-mini",
            prompt_hash="abc123",
            transcript_hash="def456",
        )
        key2 = LLMCache.compute_cache_key(
            model="gpt-4o",  # Different model
            prompt_hash="abc123",
            transcript_hash="def456",
        )
        key3 = LLMCache.compute_cache_key(
            model="gpt-4o-mini",
            prompt_hash="xyz789",  # Different prompt
            transcript_hash="def456",
        )
        assert key1 != key2
        assert key1 != key3

    def test_compute_transcript_hash(self):
        """Transcript hash should be deterministic."""
        hash1 = LLMCache.compute_transcript_hash("Hello world")
        hash2 = LLMCache.compute_transcript_hash("Hello world")
        hash3 = LLMCache.compute_transcript_hash("Different text")

        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 16  # First 16 chars of SHA256

    def test_cache_set_and_get(self):
        """Test basic set and get operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = LLMCache(cache_dir=tmpdir, enabled=True)

            # Set a value
            cache.set(
                model="gpt-4o-mini",
                prompt_hash="abc123",
                transcript_hash="def456",
                rendered_prompt="Test prompt",
                parameters={"temperature": 0},
                raw_output={"score": 0.5, "trade_candidate": True},
                token_usage={"prompt": 100, "completion": 50, "total": 150},
                cost_usd=0.001,
                latency_ms=500,
            )

            # Get the value back
            entry = cache.get(
                model="gpt-4o-mini",
                prompt_hash="abc123",
                transcript_hash="def456",
            )

            assert entry is not None
            assert entry.model == "gpt-4o-mini"
            assert entry.raw_output == {"score": 0.5, "trade_candidate": True}
            assert entry.cost_usd == 0.001

    def test_cache_miss(self):
        """Test cache miss returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = LLMCache(cache_dir=tmpdir, enabled=True)

            entry = cache.get(
                model="nonexistent",
                prompt_hash="abc",
                transcript_hash="def",
            )

            assert entry is None

    def test_cache_stats(self):
        """Test cache statistics tracking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = LLMCache(cache_dir=tmpdir, enabled=True)

            # Initial stats
            stats = cache.get_stats()
            assert stats["hits"] == 0
            assert stats["misses"] == 0

            # Cache miss
            cache.get(model="m1", prompt_hash="p1", transcript_hash="t1")
            stats = cache.get_stats()
            assert stats["misses"] == 1

            # Set value
            cache.set(
                model="m1",
                prompt_hash="p1",
                transcript_hash="t1",
                rendered_prompt="Test",
                parameters={},
                raw_output={},
                token_usage={"prompt": 0, "completion": 0, "total": 0},
                cost_usd=0,
                latency_ms=0,
            )
            stats = cache.get_stats()
            assert stats["writes"] == 1

            # Cache hit
            cache.get(model="m1", prompt_hash="p1", transcript_hash="t1")
            stats = cache.get_stats()
            assert stats["hits"] == 1
            assert stats["hit_rate"] == 0.5  # 1 hit, 1 miss

    def test_cache_disabled(self):
        """Test cache operations when disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = LLMCache(cache_dir=tmpdir, enabled=False)

            # Set should be no-op
            key = cache.set(
                model="m1",
                prompt_hash="p1",
                transcript_hash="t1",
                rendered_prompt="Test",
                parameters={},
                raw_output={},
                token_usage={"prompt": 0, "completion": 0, "total": 0},
                cost_usd=0,
                latency_ms=0,
            )
            assert key == ""

            # Get should return None
            entry = cache.get(model="m1", prompt_hash="p1", transcript_hash="t1")
            assert entry is None

    def test_cache_clear(self):
        """Test cache clear functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = LLMCache(cache_dir=tmpdir, enabled=True)

            # Add some entries
            for i in range(5):
                cache.set(
                    model="m1",
                    prompt_hash=f"p{i}",
                    transcript_hash=f"t{i}",
                    rendered_prompt="Test",
                    parameters={},
                    raw_output={},
                    token_usage={"prompt": 0, "completion": 0, "total": 0},
                    cost_usd=0,
                    latency_ms=0,
                )

            # Verify entries exist
            entry = cache.get(model="m1", prompt_hash="p0", transcript_hash="t0")
            assert entry is not None

            # Clear cache
            cleared = cache.clear()
            assert cleared == 5

            # Verify entries are gone
            entry = cache.get(model="m1", prompt_hash="p0", transcript_hash="t0")
            assert entry is None

    def test_global_cache_singleton(self):
        """Test that get_llm_cache returns singleton."""
        reset_llm_cache()

        cache1 = get_llm_cache()
        cache2 = get_llm_cache()

        assert cache1 is cache2

    def test_reset_cache(self):
        """Test that reset_llm_cache clears singleton."""
        cache1 = get_llm_cache()
        reset_llm_cache()
        cache2 = get_llm_cache()

        assert cache1 is not cache2
