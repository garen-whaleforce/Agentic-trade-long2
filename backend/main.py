"""
Rocket Screener Agentic - Backend API

Main entry point for the FastAPI backend.
"""

import os
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.routes import earnings, analyze, company, backtest, health, runs
from core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print(f"Starting Rocket Screener Agentic API...")
    print(f"Environment: {settings.environment}")
    yield
    # Shutdown
    print("Shutting down...")


app = FastAPI(
    title="Rocket Screener Agentic API",
    description="""
    Earnings Call Analysis API for quantitative trading.

    ## Features
    - Earnings call calendar and transcript retrieval
    - LLM-powered analysis (batch_score / full_audit)
    - Trade signal generation
    - Backtest integration (via Whaleforce API)

    ## Important Rules
    - All backtest metrics come from Whaleforce API (SSOT)
    - No lookahead bias - analysis uses only T-day data
    - Deterministic LLM outputs (temperature=0)
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(earnings.router, prefix="/api", tags=["Earnings"])
app.include_router(company.router, prefix="/api", tags=["Company"])
app.include_router(analyze.router, prefix="/api", tags=["Analyze"])
app.include_router(backtest.router, prefix="/api", tags=["Backtest"])
app.include_router(runs.router, prefix="/api", tags=["Runs"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=settings.backend_debug,
    )
