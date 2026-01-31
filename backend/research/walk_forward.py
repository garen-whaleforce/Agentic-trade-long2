"""
Walk-Forward Framework.

Implements walk-forward validation to prevent overfitting.

Split definitions (FIXED, DO NOT CHANGE):
- Tune:     2017-01-01 to 2021-12-31 (parameter tuning)
- Validate: 2022-01-01 to 2023-12-31 (model/parameter selection)
- Final:    2024-01-01 to 2025-12-31 (one-time final test)
- Paper:    2026-01-01 onwards (forward trading, frozen)

CRITICAL:
- Final period results CANNOT be used to adjust parameters
- Once final test is run, results are LOCKED
- Any change requires full walk-forward rerun
"""

from datetime import date
from enum import Enum
from typing import Dict, Any, Optional, List
from pathlib import Path
import json

from pydantic import BaseModel

from core.config import settings


class Period(str, Enum):
    """Walk-forward periods."""

    TUNE = "tune"
    VALIDATE = "validate"
    FINAL = "final"
    PAPER = "paper"


class PeriodConfig(BaseModel):
    """Configuration for a period."""

    name: Period
    start_date: date
    end_date: date
    allow_tuning: bool
    allow_validation: bool
    is_locked: bool = False


# Fixed period definitions
PERIOD_CONFIGS = {
    Period.TUNE: PeriodConfig(
        name=Period.TUNE,
        start_date=date(2017, 1, 1),
        end_date=date(2021, 12, 31),
        allow_tuning=True,
        allow_validation=False,
    ),
    Period.VALIDATE: PeriodConfig(
        name=Period.VALIDATE,
        start_date=date(2022, 1, 1),
        end_date=date(2023, 12, 31),
        allow_tuning=False,
        allow_validation=True,
    ),
    Period.FINAL: PeriodConfig(
        name=Period.FINAL,
        start_date=date(2024, 1, 1),
        end_date=date(2025, 12, 31),
        allow_tuning=False,
        allow_validation=False,
    ),
    Period.PAPER: PeriodConfig(
        name=Period.PAPER,
        start_date=date(2026, 1, 1),
        end_date=date(2099, 12, 31),  # Ongoing
        allow_tuning=False,
        allow_validation=False,
    ),
}


class WalkForwardConfig(BaseModel):
    """Configuration for walk-forward analysis."""

    strategy_id: str
    model_routing_version: str
    prompt_version: str
    thresholds: Dict[str, float]


class PeriodResult(BaseModel):
    """Result for a single period."""

    period: Period
    start_date: str
    end_date: str
    total_events: int
    total_signals: int
    trade_signals: int
    backtest_id: Optional[str] = None
    performance: Optional[Dict[str, float]] = None
    trade_stats: Optional[Dict[str, Any]] = None


class WalkForwardResult(BaseModel):
    """Result from walk-forward analysis."""

    config: WalkForwardConfig
    tune_result: Optional[PeriodResult] = None
    validate_result: Optional[PeriodResult] = None
    final_result: Optional[PeriodResult] = None
    is_locked: bool = False
    lock_hash: Optional[str] = None


class FinalLock(BaseModel):
    """Lock file for final test results."""

    locked_at: str
    git_commit: str
    config: WalkForwardConfig
    final_result: PeriodResult
    lock_hash: str


class WalkForwardRunner:
    """
    Runs walk-forward validation.

    Enforces:
    1. Tune period for parameter tuning only
    2. Validate period for model selection only
    3. Final period is one-time only
    4. Paper period is frozen
    """

    LOCK_FILE = "final_lock.json"

    def __init__(
        self,
        base_dir: str = "runs",
    ):
        """
        Initialize the runner.

        Args:
            base_dir: Base directory for artifacts
        """
        self.base_dir = Path(base_dir)
        self._lock: Optional[FinalLock] = None

    def get_period_config(self, period: Period) -> PeriodConfig:
        """Get configuration for a period."""
        return PERIOD_CONFIGS[period]

    def is_final_locked(self) -> bool:
        """Check if final period is locked."""
        lock_path = self.base_dir / self.LOCK_FILE
        return lock_path.exists()

    def load_lock(self) -> Optional[FinalLock]:
        """Load the final lock file."""
        lock_path = self.base_dir / self.LOCK_FILE
        if not lock_path.exists():
            return None

        with open(lock_path, "r") as f:
            data = json.load(f)
            return FinalLock(**data)

    def save_lock(self, lock: FinalLock) -> None:
        """Save the final lock file."""
        lock_path = self.base_dir / self.LOCK_FILE
        self.base_dir.mkdir(parents=True, exist_ok=True)

        with open(lock_path, "w") as f:
            json.dump(lock.model_dump(), f, indent=2)

    def validate_period_access(
        self,
        period: Period,
        purpose: str,
    ) -> None:
        """
        Validate access to a period.

        Args:
            period: Period to access
            purpose: Purpose of access (tune/validate/test)

        Raises:
            ValueError: If access is not allowed
        """
        config = self.get_period_config(period)

        if period == Period.FINAL:
            if self.is_final_locked():
                raise ValueError(
                    "Final period is LOCKED. Cannot modify or rerun. "
                    "To unlock, manually delete final_lock.json and document in ADR."
                )

        if period == Period.PAPER:
            raise ValueError(
                "Paper period cannot be backtested. "
                "Use paper trading pipeline instead."
            )

        if purpose == "tune" and not config.allow_tuning:
            raise ValueError(
                f"Tuning not allowed in {period.value} period. "
                f"Only tune period (2017-2021) allows parameter tuning."
            )

        if purpose == "validate" and period == Period.TUNE:
            raise ValueError(
                "Validation should use validate period (2022-2023), "
                "not tune period."
            )

    def get_date_range(self, period: Period) -> tuple[date, date]:
        """Get date range for a period."""
        config = self.get_period_config(period)
        return config.start_date, config.end_date

    def create_period_result(
        self,
        period: Period,
        total_events: int,
        total_signals: int,
        trade_signals: int,
        backtest_id: Optional[str] = None,
        performance: Optional[Dict[str, float]] = None,
        trade_stats: Optional[Dict[str, Any]] = None,
    ) -> PeriodResult:
        """Create a period result."""
        config = self.get_period_config(period)

        return PeriodResult(
            period=period,
            start_date=config.start_date.isoformat(),
            end_date=config.end_date.isoformat(),
            total_events=total_events,
            total_signals=total_signals,
            trade_signals=trade_signals,
            backtest_id=backtest_id,
            performance=performance,
            trade_stats=trade_stats,
        )

    def lock_final(
        self,
        config: WalkForwardConfig,
        final_result: PeriodResult,
        git_commit: str,
    ) -> FinalLock:
        """
        Lock the final period results.

        Once locked, final cannot be rerun without manual intervention.

        Args:
            config: Walk-forward configuration
            final_result: Final period result
            git_commit: Current git commit hash

        Returns:
            FinalLock object
        """
        import hashlib
        from datetime import datetime

        # Calculate lock hash
        lock_content = json.dumps(
            {
                "config": config.model_dump(),
                "final_result": final_result.model_dump(),
                "git_commit": git_commit,
            },
            sort_keys=True,
        )
        lock_hash = hashlib.sha256(lock_content.encode()).hexdigest()

        lock = FinalLock(
            locked_at=datetime.utcnow().isoformat(),
            git_commit=git_commit,
            config=config,
            final_result=final_result,
            lock_hash=lock_hash,
        )

        self.save_lock(lock)
        return lock


def get_walk_forward_runner() -> WalkForwardRunner:
    """Get a walk-forward runner instance."""
    return WalkForwardRunner()
