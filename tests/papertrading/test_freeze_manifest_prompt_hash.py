"""
Tests for PR2: Prompt SSOT + prompt_hash freezing.

Ensures that:
1. FreezeManifest includes prompt_id and prompt_hash fields
2. create_manifest() stores prompt_hash in manifest
3. validate_runtime() checks prompt_hash
4. compute_prompt_hash() is deterministic
"""

import pytest
import tempfile
import os
import sys
from pathlib import Path
from datetime import date
from unittest.mock import patch

# Direct import to avoid triggering papertrading/__init__.py import chain
# which has dependencies on pandas_market_calendars (Python 3.10+ only)
import importlib.util

_freeze_policy_path = Path(__file__).parent.parent.parent / "backend" / "papertrading" / "freeze_policy.py"
spec = importlib.util.spec_from_file_location("freeze_policy", _freeze_policy_path)
freeze_policy_module = importlib.util.module_from_spec(spec)

# Mock core.config.settings before loading the module
class MockSettings:
    pass

sys.modules["core.config"] = type(sys)("core.config")
sys.modules["core.config"].settings = MockSettings()

spec.loader.exec_module(freeze_policy_module)

FreezePolicy = freeze_policy_module.FreezePolicy
FreezeManifest = freeze_policy_module.FreezeManifest
FrozenConfig = freeze_policy_module.FrozenConfig
compute_prompt_hash = freeze_policy_module.compute_prompt_hash
validate_runtime = freeze_policy_module.validate_runtime
get_frozen_config = freeze_policy_module.get_frozen_config


class TestComputePromptHash:
    """Test the prompt hash computation."""

    def test_compute_prompt_hash_deterministic(self):
        """Same content should always produce same hash."""
        system = "You are a financial analyst."
        user = "Analyze this transcript: {transcript}"

        hash1 = compute_prompt_hash(system, user)
        hash2 = compute_prompt_hash(system, user)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest

    def test_compute_prompt_hash_different_content(self):
        """Different content should produce different hash."""
        system1 = "You are a financial analyst."
        system2 = "You are an expert financial analyst."
        user = "Analyze this transcript: {transcript}"

        hash1 = compute_prompt_hash(system1, user)
        hash2 = compute_prompt_hash(system2, user)

        assert hash1 != hash2

    def test_compute_prompt_hash_whitespace_matters(self):
        """Whitespace differences should produce different hash."""
        system = "You are a financial analyst."
        user1 = "Analyze this."
        user2 = "Analyze this. "  # Extra space

        hash1 = compute_prompt_hash(system, user1)
        hash2 = compute_prompt_hash(system, user2)

        assert hash1 != hash2


class TestFreezeManifestPromptHash:
    """Test FreezeManifest with prompt_hash fields."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temporary directory."""
        return tmp_path

    def test_manifest_includes_prompt_hash_fields(self, temp_dir):
        """Manifest should include prompt_id and prompt_hash."""
        policy = FreezePolicy(base_dir=str(temp_dir))

        manifest = policy.create_manifest(
            git_commit="abc123",
            batch_score_model="gpt-4o-mini",
            full_audit_model="claude-3.5-sonnet",
            batch_score_prompt_version="v1.0.0",
            full_audit_prompt_version="v1.0.0",
            score_threshold=0.70,
            evidence_min_count=2,
            batch_score_prompt_id="batch_score_v1",
            batch_score_prompt_hash="deadbeef" * 8,
            full_audit_prompt_id="full_audit_v1",
            full_audit_prompt_hash="cafebabe" * 8,
        )

        assert manifest.batch_score_prompt_id == "batch_score_v1"
        assert manifest.batch_score_prompt_hash == "deadbeef" * 8
        assert manifest.full_audit_prompt_id == "full_audit_v1"
        assert manifest.full_audit_prompt_hash == "cafebabe" * 8

    def test_manifest_hash_includes_prompt_hash(self, temp_dir):
        """Manifest hash should change when prompt_hash changes."""
        policy = FreezePolicy(base_dir=str(temp_dir))

        # Create manifest with one prompt hash
        manifest1 = policy.create_manifest(
            git_commit="abc123",
            batch_score_model="gpt-4o-mini",
            full_audit_model="claude-3.5-sonnet",
            batch_score_prompt_version="v1.0.0",
            full_audit_prompt_version="v1.0.0",
            score_threshold=0.70,
            evidence_min_count=2,
            batch_score_prompt_hash="aaaa" * 16,
        )

        # Create manifest with different prompt hash
        manifest2 = policy.create_manifest(
            git_commit="abc123",
            batch_score_model="gpt-4o-mini",
            full_audit_model="claude-3.5-sonnet",
            batch_score_prompt_version="v1.0.0",  # Same version
            full_audit_prompt_version="v1.0.0",
            score_threshold=0.70,
            evidence_min_count=2,
            batch_score_prompt_hash="bbbb" * 16,  # Different hash!
        )

        # Manifest hashes should be different
        assert manifest1.manifest_hash != manifest2.manifest_hash

    def test_manifest_persists_prompt_hash(self, temp_dir):
        """Prompt hash should be saved and loaded correctly."""
        policy = FreezePolicy(base_dir=str(temp_dir))

        prompt_hash = compute_prompt_hash(
            "You are a financial analyst.",
            "Analyze this: {transcript}"
        )

        # Create and save
        policy.create_manifest(
            git_commit="abc123",
            batch_score_model="gpt-4o-mini",
            full_audit_model="claude-3.5-sonnet",
            batch_score_prompt_version="v1.0.0",
            full_audit_prompt_version="v1.0.0",
            score_threshold=0.70,
            evidence_min_count=2,
            batch_score_prompt_id="batch_v1",
            batch_score_prompt_hash=prompt_hash,
        )

        # Load
        loaded = policy.load_manifest()

        assert loaded is not None
        assert loaded.batch_score_prompt_id == "batch_v1"
        assert loaded.batch_score_prompt_hash == prompt_hash


class TestValidateRuntimePromptHash:
    """Test validate_runtime() with prompt_hash checking."""

    @pytest.fixture
    def frozen_env(self, tmp_path):
        """Create a frozen environment with manifest."""
        policy = FreezePolicy(
            base_dir=str(tmp_path),
            freeze_boundary=date(2020, 1, 1),  # In the past = frozen
        )

        manifest = policy.create_manifest(
            git_commit="abc123",
            batch_score_model="gpt-4o-mini",
            full_audit_model="claude-3.5-sonnet",
            batch_score_prompt_version="v1.0.0",
            full_audit_prompt_version="v1.0.0",
            score_threshold=0.70,
            evidence_min_count=2,
            batch_score_prompt_id="batch_v1",
            batch_score_prompt_hash="correct_hash_" + "a" * 52,
        )

        return policy, manifest

    def test_validate_runtime_passes_with_matching_hash(self, frozen_env, tmp_path):
        """validate_runtime should pass when prompt_hash matches."""
        policy, manifest = frozen_env

        # Patch the locally imported module instead of the full path
        with patch.object(freeze_policy_module, 'get_freeze_policy', return_value=policy):
            # Reset global config
            freeze_policy_module._frozen_config = None

            # Should not raise
            result = validate_runtime(
                batch_score_model="gpt-4o-mini",
                prompt_hash="correct_hash_" + "a" * 52,
            )

            assert result is True

    def test_validate_runtime_fails_with_mismatched_hash(self, frozen_env, tmp_path):
        """validate_runtime should fail when prompt_hash doesn't match."""
        policy, manifest = frozen_env

        with patch.object(freeze_policy_module, 'get_freeze_policy', return_value=policy):
            # Reset global config
            freeze_policy_module._frozen_config = None

            # Should raise due to hash mismatch
            with pytest.raises(ValueError) as exc_info:
                validate_runtime(
                    batch_score_model="gpt-4o-mini",
                    prompt_hash="wrong_hash_" + "b" * 55,
                )

            assert "prompt_hash" in str(exc_info.value)
            assert "prompt content changed" in str(exc_info.value)


class TestFrozenConfigPromptHash:
    """Test FrozenConfig includes prompt_hash."""

    def test_frozen_config_has_prompt_hash_fields(self):
        """FrozenConfig should have prompt_id and prompt_hash fields."""
        config = FrozenConfig(
            model="gpt-4o-mini",
            prompt_version="v1.0.0",
            prompt_id="batch_v1",
            prompt_hash="test_hash",
        )

        assert config.prompt_id == "batch_v1"
        assert config.prompt_hash == "test_hash"

    def test_frozen_config_defaults_to_none(self):
        """Prompt fields should default to None."""
        config = FrozenConfig()

        assert config.prompt_id is None
        assert config.prompt_hash is None


class TestFreezeMethodPromptHash:
    """Test freeze() method with prompt_hash."""

    def test_freeze_accepts_prompt_hash(self, tmp_path):
        """freeze() should accept and store prompt_hash."""
        policy = FreezePolicy(base_dir=str(tmp_path))

        manifest = policy.freeze(
            git_commit="HEAD",
            batch_score_prompt_id="batch_v1",
            batch_score_prompt_hash="test_hash_" + "x" * 54,
            full_audit_prompt_id="audit_v1",
            full_audit_prompt_hash="audit_hash_" + "y" * 53,
        )

        assert manifest.batch_score_prompt_id == "batch_v1"
        assert manifest.batch_score_prompt_hash == "test_hash_" + "x" * 54
        assert manifest.full_audit_prompt_id == "audit_v1"
        assert manifest.full_audit_prompt_hash == "audit_hash_" + "y" * 53
