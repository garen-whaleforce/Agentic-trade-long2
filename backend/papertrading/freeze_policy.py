"""
Freeze Policy for Paper Trading.

Ensures model, prompt, and threshold versions are locked
during forward/paper trading period (2026-01-01 onwards).
"""

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Dict, Any

from pydantic import BaseModel

from core.config import settings


class FreezeManifest(BaseModel):
    """
    Manifest of frozen configuration for paper trading.

    Once frozen, these cannot be changed without explicit unlock.
    """

    frozen_at: str
    freeze_boundary: str  # 2026-01-01
    git_commit: str

    # Model routing
    batch_score_model: str
    full_audit_model: str

    # Prompt versions
    batch_score_prompt_version: str
    full_audit_prompt_version: str

    # Thresholds
    score_threshold: float
    evidence_min_count: int
    block_on_margin_concern: bool

    # Universe
    universe_filter: Optional[str] = None

    # Hash of entire manifest
    manifest_hash: str


class FreezePolicy:
    """
    Manages freeze policy for paper trading.

    Rules:
    1. After freeze boundary (2026-01-01), config is locked
    2. Any change requires explicit unlock + ADR documentation
    3. Unlock creates new version, requires full walk-forward rerun
    """

    MANIFEST_FILE = "papertrading_freeze_manifest.json"

    def __init__(
        self,
        base_dir: str = ".",
        freeze_boundary: Optional[date] = None,
    ):
        """
        Initialize freeze policy.

        Args:
            base_dir: Base directory for manifest file
            freeze_boundary: Date after which config is frozen
        """
        self.base_dir = Path(base_dir)
        self.freeze_boundary = freeze_boundary or date(2026, 1, 1)

    def is_frozen_period(self) -> bool:
        """Check if we're in the frozen period."""
        return date.today() >= self.freeze_boundary

    def get_manifest_path(self) -> Path:
        """Get path to manifest file."""
        return self.base_dir / self.MANIFEST_FILE

    def has_manifest(self) -> bool:
        """Check if freeze manifest exists."""
        return self.get_manifest_path().exists()

    def load_manifest(self) -> Optional[FreezeManifest]:
        """Load freeze manifest."""
        path = self.get_manifest_path()
        if not path.exists():
            return None

        with open(path, "r") as f:
            data = json.load(f)
            return FreezeManifest(**data)

    def save_manifest(self, manifest: FreezeManifest) -> None:
        """Save freeze manifest."""
        path = self.get_manifest_path()
        with open(path, "w") as f:
            json.dump(manifest.model_dump(), f, indent=2)

    def create_manifest(
        self,
        git_commit: str,
        batch_score_model: str,
        full_audit_model: str,
        batch_score_prompt_version: str,
        full_audit_prompt_version: str,
        score_threshold: float,
        evidence_min_count: int,
        block_on_margin_concern: bool = True,
        universe_filter: Optional[str] = None,
    ) -> FreezeManifest:
        """
        Create a new freeze manifest.

        Args:
            Various configuration parameters

        Returns:
            FreezeManifest
        """
        # Calculate hash
        content = json.dumps(
            {
                "git_commit": git_commit,
                "batch_score_model": batch_score_model,
                "full_audit_model": full_audit_model,
                "batch_score_prompt_version": batch_score_prompt_version,
                "full_audit_prompt_version": full_audit_prompt_version,
                "score_threshold": score_threshold,
                "evidence_min_count": evidence_min_count,
                "block_on_margin_concern": block_on_margin_concern,
                "universe_filter": universe_filter,
            },
            sort_keys=True,
        )
        manifest_hash = hashlib.sha256(content.encode()).hexdigest()

        manifest = FreezeManifest(
            frozen_at=datetime.utcnow().isoformat(),
            freeze_boundary=self.freeze_boundary.isoformat(),
            git_commit=git_commit,
            batch_score_model=batch_score_model,
            full_audit_model=full_audit_model,
            batch_score_prompt_version=batch_score_prompt_version,
            full_audit_prompt_version=full_audit_prompt_version,
            score_threshold=score_threshold,
            evidence_min_count=evidence_min_count,
            block_on_margin_concern=block_on_margin_concern,
            universe_filter=universe_filter,
            manifest_hash=manifest_hash,
        )

        self.save_manifest(manifest)
        return manifest

    def validate_config(
        self,
        batch_score_model: str,
        full_audit_model: str,
        batch_score_prompt_version: str,
        score_threshold: float,
        evidence_min_count: int,
    ) -> bool:
        """
        Validate that current config matches frozen manifest.

        Args:
            Configuration parameters to validate

        Returns:
            True if config matches manifest

        Raises:
            ValueError if config doesn't match and we're in frozen period
        """
        if not self.is_frozen_period():
            return True

        manifest = self.load_manifest()
        if manifest is None:
            raise ValueError(
                "In frozen period but no manifest exists. "
                "Create manifest with freeze_policy.create_manifest()"
            )

        mismatches = []

        if batch_score_model != manifest.batch_score_model:
            mismatches.append(
                f"batch_score_model: {batch_score_model} != {manifest.batch_score_model}"
            )

        if full_audit_model != manifest.full_audit_model:
            mismatches.append(
                f"full_audit_model: {full_audit_model} != {manifest.full_audit_model}"
            )

        if batch_score_prompt_version != manifest.batch_score_prompt_version:
            mismatches.append(
                f"prompt_version: {batch_score_prompt_version} != {manifest.batch_score_prompt_version}"
            )

        if score_threshold != manifest.score_threshold:
            mismatches.append(
                f"score_threshold: {score_threshold} != {manifest.score_threshold}"
            )

        if evidence_min_count != manifest.evidence_min_count:
            mismatches.append(
                f"evidence_min_count: {evidence_min_count} != {manifest.evidence_min_count}"
            )

        if mismatches:
            raise ValueError(
                f"Configuration mismatch in frozen period. "
                f"Mismatches: {'; '.join(mismatches)}. "
                f"To change, delete manifest, document in ADR, and rerun walk-forward."
            )

        return True

    def freeze(
        self,
        git_commit: str = "HEAD",
        batch_score_model: str = "gpt-4o-mini",
        full_audit_model: str = "claude-3.5-sonnet",
        batch_score_prompt_version: str = "v1.0.0",
        full_audit_prompt_version: str = "v1.0.0",
        score_threshold: float = 0.70,
        evidence_min_count: int = 2,
        block_on_margin_concern: bool = True,
    ) -> FreezeManifest:
        """
        Create and save a freeze manifest with default or custom settings.

        This is a convenience method for enabling paper trading.
        """
        return self.create_manifest(
            git_commit=git_commit,
            batch_score_model=batch_score_model,
            full_audit_model=full_audit_model,
            batch_score_prompt_version=batch_score_prompt_version,
            full_audit_prompt_version=full_audit_prompt_version,
            score_threshold=score_threshold,
            evidence_min_count=evidence_min_count,
            block_on_margin_concern=block_on_margin_concern,
        )

    def is_frozen(self) -> bool:
        """Check if we're in frozen period with a valid manifest."""
        return self.has_manifest() and self.is_frozen_period()


def get_freeze_policy() -> FreezePolicy:
    """Get freeze policy instance."""
    return FreezePolicy()


class FrozenConfig(BaseModel):
    """Simplified frozen config for runtime use."""

    model: str = "gpt-4o-mini"
    prompt_version: str = "v1.0.0"
    score_threshold: float = 0.70
    evidence_min_count: int = 2
    block_on_margin_concern: bool = True
    is_frozen: bool = False


# Global frozen config
_frozen_config: Optional[FrozenConfig] = None


def get_frozen_config() -> FrozenConfig:
    """
    Get the frozen configuration.

    Returns:
        FrozenConfig with current frozen settings
    """
    global _frozen_config

    if _frozen_config is not None:
        return _frozen_config

    policy = get_freeze_policy()
    manifest = policy.load_manifest()

    if manifest is not None:
        _frozen_config = FrozenConfig(
            model=manifest.batch_score_model,
            prompt_version=manifest.batch_score_prompt_version,
            score_threshold=manifest.score_threshold,
            evidence_min_count=manifest.evidence_min_count,
            block_on_margin_concern=manifest.block_on_margin_concern,
            is_frozen=True,
        )
    else:
        # Default config if no manifest
        _frozen_config = FrozenConfig()

    return _frozen_config


def validate_runtime(
    batch_score_model: Optional[str] = None,
    full_audit_model: Optional[str] = None,
    prompt_version: Optional[str] = None,
    score_threshold: Optional[float] = None,
    evidence_min_count: Optional[int] = None,
) -> bool:
    """
    Validate runtime configuration against freeze policy.

    This is the SSOT check that should be called at the start of any
    paper trading or production run.

    Raises:
        ValueError: If config doesn't match frozen manifest in frozen period.

    Returns:
        True if validation passes.
    """
    policy = get_freeze_policy()

    # If not in frozen period, allow any config
    if not policy.is_frozen_period():
        return True

    # Get frozen config
    frozen = get_frozen_config()
    if not frozen.is_frozen:
        raise ValueError(
            "In frozen period but no freeze manifest exists. "
            "Run: make enable-paper-trading"
        )

    mismatches = []

    if batch_score_model and batch_score_model != frozen.model:
        mismatches.append(f"batch_score_model: {batch_score_model} != {frozen.model}")

    if prompt_version and prompt_version != frozen.prompt_version:
        mismatches.append(f"prompt_version: {prompt_version} != {frozen.prompt_version}")

    if score_threshold is not None and score_threshold != frozen.score_threshold:
        mismatches.append(f"score_threshold: {score_threshold} != {frozen.score_threshold}")

    if evidence_min_count is not None and evidence_min_count != frozen.evidence_min_count:
        mismatches.append(f"evidence_min_count: {evidence_min_count} != {frozen.evidence_min_count}")

    if mismatches:
        raise ValueError(
            f"Configuration mismatch in frozen period. "
            f"Mismatches: {'; '.join(mismatches)}. "
            f"To change, delete manifest, document in ADR, and rerun walk-forward."
        )

    return True


def require_frozen() -> FrozenConfig:
    """
    Ensure we're in frozen period with valid config.

    This is the recommended way to get frozen config in paper trading.
    It will raise if not properly frozen.

    Returns:
        FrozenConfig that is guaranteed to be frozen.

    Raises:
        ValueError: If not in frozen period or manifest is missing.
    """
    policy = get_freeze_policy()

    if not policy.is_frozen_period():
        raise ValueError(
            f"Not in frozen period. Paper trading requires date >= {policy.freeze_boundary}"
        )

    frozen = get_frozen_config()
    if not frozen.is_frozen:
        raise ValueError(
            "In frozen period but no freeze manifest exists. "
            "Run: make enable-paper-trading"
        )

    return frozen
