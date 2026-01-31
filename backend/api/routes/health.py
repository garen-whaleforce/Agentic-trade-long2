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
    """
    # TODO: Implement actual health checks for external services
    return {
        "earningscall_api": {"status": "unknown", "message": "Not implemented"},
        "whaleforce_backtest_api": {"status": "unknown", "message": "Not implemented"},
        "llm_provider": {"status": "unknown", "message": "Not implemented"},
        "database": {"status": "unknown", "message": "Not implemented"},
    }
