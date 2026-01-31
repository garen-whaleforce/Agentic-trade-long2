"""
Application configuration.

Loads settings from environment variables.
"""

from datetime import date
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Environment
    environment: str = "development"

    # Backend
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_debug: bool = True

    # Database
    database_url: str = "sqlite:///./data/rocket_screener.db"

    # External APIs
    earningscall_api_key: str = ""
    earningscall_api_url: str = "https://api.earningscall.com/v1"

    whaleforce_backtest_api_key: str = ""
    whaleforce_backtest_api_url: str = "https://api.whaleforce.com/v1"

    # LLM
    litellm_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    llm_batch_score_model: str = "gpt-4o-mini"
    llm_full_audit_model: str = "gpt-5-mini"
    llm_batch_score_max_cost: float = 0.01
    llm_full_audit_max_cost: float = 0.10
    llm_temperature: float = 0.0

    # Cache
    cache_dir: str = "./data/cache"

    # Strategy Configuration
    strategy_score_threshold: float = 0.70
    strategy_evidence_min_count: int = 2
    strategy_win_rate_target: float = 0.75

    # Walk-forward periods
    strategy_tune_start: str = "2017-01-01"
    strategy_tune_end: str = "2021-12-31"
    strategy_validate_start: str = "2022-01-01"
    strategy_validate_end: str = "2023-12-31"
    strategy_test_start: str = "2024-01-01"
    strategy_test_end: str = "2025-12-31"
    strategy_paper_start: str = "2026-01-01"

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def is_frozen(self) -> bool:
        """Check if we're in the frozen (paper trading) period."""
        from datetime import datetime

        freeze_date = datetime.strptime(self.strategy_paper_start, "%Y-%m-%d").date()
        return date.today() >= freeze_date


settings = Settings()
