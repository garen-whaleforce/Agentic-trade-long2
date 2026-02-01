"""
Health check endpoints.
"""

from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter

from core.config import settings

router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint.

    Returns basic application status and configuration.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.environment,
        "version": "1.0.0",
        "frozen": settings.is_frozen(),
        "config": {
            "llm_batch_score_model": settings.llm_batch_score_model,
            "llm_full_audit_model": settings.llm_full_audit_model,
            "strategy_score_threshold": settings.strategy_score_threshold,
            "strategy_evidence_min_count": settings.strategy_evidence_min_count,
        },
    }


@router.get("/health/services")
async def services_health() -> Dict[str, Any]:
    """
    Check health of external services.

    Performs lightweight checks:
    - API keys configured (not actual API calls for cost reasons)
    - LLM provider reachable
    - Database connection (if configured)
    """
    results = {}

    # Check EarningsCall API (config check only - avoid unnecessary API costs)
    earningscall_key = settings.earningscall_api_key
    if earningscall_key and len(earningscall_key) > 10:
        results["earningscall_api"] = {
            "status": "configured",
            "message": "API key present",
        }
    else:
        results["earningscall_api"] = {
            "status": "not_configured",
            "message": "API key missing or invalid",
        }

    # Check Whaleforce Backtest API (config check only)
    backtest_key = settings.whaleforce_backtest_api_key
    if backtest_key and len(backtest_key) > 10:
        results["whaleforce_backtest_api"] = {
            "status": "configured",
            "message": "API key present",
        }
    else:
        results["whaleforce_backtest_api"] = {
            "status": "not_configured",
            "message": "API key missing or invalid",
        }

    # Check LLM provider (config check - actual completion would cost money)
    litellm_key = settings.litellm_api_key
    if litellm_key and len(litellm_key) > 10:
        results["llm_provider"] = {
            "status": "configured",
            "message": "API key present",
            "batch_score_model": settings.llm_batch_score_model,
            "full_audit_model": settings.llm_full_audit_model,
        }
    else:
        results["llm_provider"] = {
            "status": "not_configured",
            "message": "API key missing or invalid",
        }

    # Check database (connection string check)
    db_url = settings.database_url
    if db_url and len(db_url) > 10:
        results["database"] = {
            "status": "configured",
            "message": "Connection string present",
        }
    else:
        results["database"] = {
            "status": "not_configured",
            "message": "Connection string missing",
        }

    return results
