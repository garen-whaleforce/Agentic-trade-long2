"""
PR4: Artifacts Schema for Backtest/Paper Trading.

Defines standardized artifact format for run outputs.
Ensures reproducibility and traceability across backtest and paper trading.
"""

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, Field


class RunType(str, Enum):
    """Type of run."""
    BACKTEST_TUNE = "backtest_tune"
    BACKTEST_VALIDATE = "backtest_validate"
    BACKTEST_FINAL = "backtest_final"
    PAPER_TRADING = "paper_trading"
    SMOKE_TEST = "smoke_test"


class RunStatus(str, Enum):
    """Status of a run."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PromptArtifact(BaseModel):
    """Prompt configuration artifact (PR2 integration)."""

    prompt_id: str
    prompt_version: str
    prompt_hash: str  # SHA256 of system_prompt + user_template
    system_prompt_preview: Optional[str] = None  # First 200 chars
    user_template_preview: Optional[str] = None  # First 200 chars


class ModelArtifact(BaseModel):
    """Model configuration artifact."""

    model_id: str
    model_provider: str = "litellm"
    temperature: float = 0.0
    max_output_tokens: int = 400


class ThresholdArtifact(BaseModel):
    """Threshold configuration artifact."""

    score_threshold: float
    evidence_min_count: int
    block_on_margin_concern: bool = True


class RunManifest(BaseModel):
    """
    Manifest for a run.

    This is the SSOT for run configuration.
    Any change to configuration should result in a different manifest_hash.
    """

    run_id: str
    run_type: RunType
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    status: RunStatus = RunStatus.INITIALIZING

    # Version control
    git_commit: Optional[str] = None
    git_branch: Optional[str] = None
    git_dirty: bool = False

    # Date range
    start_date: str
    end_date: str

    # Configuration
    model_config_: ModelArtifact = Field(alias="model_config")
    prompt_config: PromptArtifact
    threshold_config: ThresholdArtifact

    # Freeze policy (PR2 integration)
    frozen: bool = False
    freeze_manifest_hash: Optional[str] = None

    # Computed hash of entire manifest
    manifest_hash: str = ""

    def compute_hash(self) -> str:
        """Compute hash of manifest content."""
        content = json.dumps(
            {
                "run_id": self.run_id,
                "run_type": self.run_type.value,
                "start_date": self.start_date,
                "end_date": self.end_date,
                "git_commit": self.git_commit,
                "model_config": self.model_config_.model_dump(),
                "prompt_config": self.prompt_config.model_dump(),
                "threshold_config": self.threshold_config.model_dump(),
            },
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()

    def finalize(self) -> "RunManifest":
        """Finalize manifest by computing hash."""
        self.manifest_hash = self.compute_hash()
        return self

    model_config = {"populate_by_name": True}


class SignalArtifact(BaseModel):
    """Individual signal artifact."""

    event_id: str
    symbol: str
    event_date: str
    signal_date: str  # Date signal was generated

    # LLM output
    score: float
    trade_candidate: bool
    evidence_count: int
    key_flags: Dict[str, bool]
    no_trade_reason: Optional[str] = None

    # Trading dates (calculated from No-Peek rules)
    entry_date: Optional[str] = None
    exit_date: Optional[str] = None

    # Cost tracking
    cost_usd: float = 0.0
    latency_ms: int = 0

    # Validation
    passed_gate: bool = False
    gate_reason: Optional[str] = None


class PositionArtifact(BaseModel):
    """Position artifact for backtest/paper trading."""

    symbol: str
    direction: str = "long"
    entry_date: str
    exit_date: str
    signal_id: str
    score: float
    weight: float = 1.0  # Portfolio weight

    # Filled by backtest API
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    return_pct: Optional[float] = None


class PerformanceArtifact(BaseModel):
    """
    Performance metrics artifact.

    IMPORTANT: These come from Whaleforce Backtest API.
    Do NOT calculate locally.
    """

    # Core metrics
    cagr: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    win_rate: Optional[float] = None
    total_return: Optional[float] = None

    # Trade stats
    total_trades: int = 0
    trades_per_year: float = 0.0
    avg_holding_days: float = 0.0

    # Cost tracking
    total_cost_usd: float = 0.0

    # Source validation
    source: str = "whaleforce_api"  # Must be whaleforce_api
    backtest_id: Optional[str] = None


class RunSummary(BaseModel):
    """Summary of a run."""

    run_id: str
    run_type: RunType
    status: RunStatus

    # Counts
    total_events: int = 0
    processed_events: int = 0
    trade_signals: int = 0
    no_trade_signals: int = 0
    errors: int = 0

    # Cost
    total_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0

    # Performance (from API)
    performance: Optional[PerformanceArtifact] = None

    # Timing
    started_at: str = ""
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None


class RunArtifacts(BaseModel):
    """
    Complete artifacts for a run.

    This is the top-level artifact structure that contains all
    outputs from a backtest or paper trading run.
    """

    manifest: RunManifest
    summary: Optional[RunSummary] = None
    signals: List[SignalArtifact] = []
    positions: List[PositionArtifact] = []
    performance: Optional[PerformanceArtifact] = None

    # Validation checkpoints
    checkpoints: Dict[str, Any] = {}

    def add_checkpoint(self, name: str, data: Any) -> None:
        """Add a validation checkpoint."""
        self.checkpoints[name] = {
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
        }

    def to_json(self) -> str:
        """Serialize to JSON."""
        return self.model_dump_json(indent=2)

    def save(self, path: str) -> None:
        """Save artifacts to file."""
        with open(path, "w") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "RunArtifacts":
        """Load artifacts from file."""
        with open(path, "r") as f:
            data = json.load(f)
        return cls(**data)


def create_run_manifest(
    run_id: str,
    run_type: RunType,
    start_date: str,
    end_date: str,
    model_id: str = "gpt-4o-mini",
    prompt_id: str = "batch_score_v1",
    prompt_version: str = "v1.0.0",
    prompt_hash: str = "",
    score_threshold: float = 0.70,
    evidence_min_count: int = 2,
    git_commit: Optional[str] = None,
    frozen: bool = False,
) -> RunManifest:
    """
    Create a new run manifest.

    This is the recommended factory function for creating manifests.
    """
    manifest = RunManifest(
        run_id=run_id,
        run_type=run_type,
        start_date=start_date,
        end_date=end_date,
        git_commit=git_commit,
        model_config=ModelArtifact(
            model_id=model_id,
        ),
        prompt_config=PromptArtifact(
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
        ),
        threshold_config=ThresholdArtifact(
            score_threshold=score_threshold,
            evidence_min_count=evidence_min_count,
        ),
        frozen=frozen,
    )

    return manifest.finalize()
