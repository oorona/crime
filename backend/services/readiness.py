"""Readiness helpers: are the statistics views populated yet?"""
from __future__ import annotations
from fastapi import HTTPException, Request

_ready = False


async def views_populated(pool) -> bool:
    global _ready
    if _ready:
        return True
    ok = await pool.fetchval("SELECT relispopulated FROM pg_class WHERE relname = 'mv_station_crime'")
    _ready = bool(ok)
    return _ready


async def require_views(request: Request) -> None:
    """FastAPI dependency: 503 with the ingest state until the views exist."""
    if not await views_populated(request.app.state.db):
        raise HTTPException(503, {"error": "ingesting", "ingest": getattr(request.app.state, "ingest", None)})
