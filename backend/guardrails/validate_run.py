"""
Run Validation Tool.

Validates that a run has all required artifacts for compliance
and reproducibility.

Required artifacts:
- run_config.json: Run configuration
- signals.csv: All signals generated
- summary.json: Run summary
- llm_requests/: LLM request logs (at least one)
- llm_responses/: LLM response logs (at least one)
- backtest_request.json: Backtest submission (for non-dry runs)
- backtest_result.json: Backtest results from Whaleforce API
"""

import json
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from pydantic import BaseModel


class ValidationResult(BaseModel):
    """Result of run validation."""

    run_id: str
    valid: bool
    errors: List[str]
    warnings: List[str]
    artifacts_found: List[str]
    artifacts_missing: List[str]
    timestamp: str


# Required artifacts for different run types
REQUIRED_ARTIFACTS = {
    "minimal": [
        "run_config.json",
    ],
    "analysis": [
        "run_config.json",
        "signals.csv",
        "summary.json",
    ],
    "full": [
        "run_config.json",
        "signals.csv",
        "summary.json",
        "backtest_request.json",
        "backtest_result.json",
        "report.md",
    ],
}


def validate_run(
    run_dir: Path,
    validation_level: str = "full",
    require_llm_logs: bool = True,
) -> ValidationResult:
    """
    Validate a run directory for completeness.

    Args:
        run_dir: Path to run directory
        validation_level: "minimal", "analysis", or "full"
        require_llm_logs: Whether to require LLM logs

    Returns:
        ValidationResult
    """
    run_id = run_dir.name
    errors = []
    warnings = []
    found = []
    missing = []

    if not run_dir.exists():
        return ValidationResult(
            run_id=run_id,
            valid=False,
            errors=[f"Run directory does not exist: {run_dir}"],
            warnings=[],
            artifacts_found=[],
            artifacts_missing=["run_config.json"],
            timestamp=datetime.utcnow().isoformat(),
        )

    required = REQUIRED_ARTIFACTS.get(validation_level, REQUIRED_ARTIFACTS["full"])

    # Check required artifacts
    for artifact in required:
        artifact_path = run_dir / artifact
        if artifact_path.exists():
            found.append(artifact)
        else:
            missing.append(artifact)
            errors.append(f"Missing required artifact: {artifact}")

    # Check LLM logs if required
    if require_llm_logs:
        llm_requests_dir = run_dir / "llm_requests"
        llm_responses_dir = run_dir / "llm_responses"

        if llm_requests_dir.exists():
            request_files = list(llm_requests_dir.glob("*.json"))
            if request_files:
                found.append(f"llm_requests/ ({len(request_files)} files)")
            else:
                warnings.append("llm_requests/ directory exists but is empty")
        else:
            missing.append("llm_requests/")
            errors.append("Missing LLM request logs")

        if llm_responses_dir.exists():
            response_files = list(llm_responses_dir.glob("*.json"))
            if response_files:
                found.append(f"llm_responses/ ({len(response_files)} files)")
            else:
                warnings.append("llm_responses/ directory exists but is empty")
        else:
            missing.append("llm_responses/")
            errors.append("Missing LLM response logs")

    # Validate run_config.json content
    config_path = run_dir / "run_config.json"
    if config_path.exists():
        config_errors = _validate_config(config_path)
        errors.extend(config_errors)

    # Validate signals.csv content
    signals_path = run_dir / "signals.csv"
    if signals_path.exists():
        signals_warnings = _validate_signals(signals_path)
        warnings.extend(signals_warnings)

    # Validate backtest_result.json content (SSOT check)
    backtest_path = run_dir / "backtest_result.json"
    if backtest_path.exists():
        backtest_errors = _validate_backtest_result(backtest_path)
        errors.extend(backtest_errors)

    valid = len(errors) == 0

    return ValidationResult(
        run_id=run_id,
        valid=valid,
        errors=errors,
        warnings=warnings,
        artifacts_found=found,
        artifacts_missing=missing,
        timestamp=datetime.utcnow().isoformat(),
    )


def _validate_config(config_path: Path) -> List[str]:
    """Validate run config content."""
    errors = []

    try:
        with open(config_path, "r") as f:
            config = json.load(f)

        required_fields = ["run_id", "timestamp", "purpose", "date_range", "models", "thresholds"]
        for field in required_fields:
            if field not in config:
                errors.append(f"run_config.json missing required field: {field}")

        # Check date_range
        date_range = config.get("date_range", {})
        if "start" not in date_range:
            errors.append("run_config.json date_range missing 'start'")
        if "end" not in date_range:
            errors.append("run_config.json date_range missing 'end'")

        # Check thresholds
        thresholds = config.get("thresholds", {})
        if "score_threshold" not in thresholds:
            errors.append("run_config.json thresholds missing 'score_threshold'")

    except json.JSONDecodeError as e:
        errors.append(f"run_config.json is not valid JSON: {e}")

    return errors


def _validate_signals(signals_path: Path) -> List[str]:
    """Validate signals.csv content."""
    warnings = []

    try:
        with open(signals_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

            if not rows:
                warnings.append("signals.csv is empty")
            else:
                # Check required columns
                required_cols = ["event_id", "symbol", "score", "trade_long"]
                for col in required_cols:
                    if col not in reader.fieldnames:
                        warnings.append(f"signals.csv missing column: {col}")

    except Exception as e:
        warnings.append(f"Could not read signals.csv: {e}")

    return warnings


def _validate_backtest_result(backtest_path: Path) -> List[str]:
    """Validate backtest result - ensure it came from Whaleforce API."""
    errors = []

    try:
        with open(backtest_path, "r") as f:
            result = json.load(f)

        # Check for required API response fields
        if "backtest_id" not in result:
            errors.append("backtest_result.json missing 'backtest_id' - may not be from Whaleforce API")

        if "performance" not in result:
            errors.append("backtest_result.json missing 'performance' metrics")
        else:
            perf = result["performance"]
            required_metrics = ["cagr", "sharpe_ratio", "win_rate"]
            for metric in required_metrics:
                if metric not in perf:
                    errors.append(f"backtest_result.json performance missing '{metric}'")

    except json.JSONDecodeError as e:
        errors.append(f"backtest_result.json is not valid JSON: {e}")

    return errors


def validate_all_runs(
    runs_dir: Path = Path("runs"),
    validation_level: str = "full",
) -> Dict[str, ValidationResult]:
    """
    Validate all runs in the runs directory.

    Args:
        runs_dir: Base runs directory
        validation_level: Validation level

    Returns:
        Dict of run_id -> ValidationResult
    """
    results = {}

    if not runs_dir.exists():
        return results

    for run_dir in runs_dir.iterdir():
        if run_dir.is_dir():
            result = validate_run(run_dir, validation_level)
            results[run_dir.name] = result

    return results


def print_validation_report(results: Dict[str, ValidationResult]) -> None:
    """Print validation report to stdout."""
    valid_count = sum(1 for r in results.values() if r.valid)
    invalid_count = len(results) - valid_count

    print("=" * 60)
    print("RUN VALIDATION REPORT")
    print("=" * 60)
    print(f"Total runs: {len(results)}")
    print(f"Valid: {valid_count}")
    print(f"Invalid: {invalid_count}")
    print()

    if invalid_count > 0:
        print("INVALID RUNS:")
        print("-" * 40)
        for run_id, result in results.items():
            if not result.valid:
                print(f"\n{run_id}:")
                for error in result.errors:
                    print(f"  ERROR: {error}")
                for warning in result.warnings:
                    print(f"  WARNING: {warning}")

    print()
    print("=" * 60)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        run_path = Path(sys.argv[1])
        if run_path.is_dir():
            result = validate_run(run_path)
            if result.valid:
                print(f"✓ Run {result.run_id} is valid")
                sys.exit(0)
            else:
                print(f"✗ Run {result.run_id} is INVALID")
                for error in result.errors:
                    print(f"  ERROR: {error}")
                sys.exit(1)
        else:
            print(f"Not a directory: {run_path}")
            sys.exit(1)
    else:
        # Validate all runs
        results = validate_all_runs()
        print_validation_report(results)

        # Exit with error if any run is invalid
        if any(not r.valid for r in results.values()):
            sys.exit(1)
