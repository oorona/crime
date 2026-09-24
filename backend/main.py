"""CDMX Crime GIS — FastAPI app.

Lifespan:
  1. Build asyncpg pool (search_path set per-connection).
  2. Build the Gemini chat agent (disabled when keys are absent).
  3. Start the idempotent ingest as a BACKGROUND task (INGEST_ON_BOOT=1) so
     the API is reachable immediately; /health reports its progress and the
     stats endpoints answer 503 until the views are populated.
"""
from __future__ import annotations
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import create_pool
from services import ingest
from services.readiness import views_populated

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await create_pool()
    app.state.chat_agent = _build_chat_agent()
    app.state.ingest = ingest.new_state()
    app.state.ingest_task = None
    if os.getenv("INGEST_ON_BOOT", "1") == "1":
        app.state.ingest_task = asyncio.create_task(ingest.run_all(app.state.db, app.state.ingest))
    else:
        app.state.ingest["status"] = "disabled"
    try:
        yield
    finally:
        task = app.state.ingest_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await app.state.db.close()


def _build_chat_agent():
    """Construct the chat agent if all required env is present, else return None."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    mcp_url = os.getenv("CRIME_MCP_URL")
    mcp_key = os.getenv("CRIME_MCP_API_KEY")
    if not (gemini_key and mcp_url and mcp_key):
        logger.warning("chat agent disabled: missing GEMINI_API_KEY, CRIME_MCP_URL, or CRIME_MCP_API_KEY")
        return None
    from services.chat_agent import ChatAgent
    return ChatAgent(
        gemini_api_key=gemini_key,
        model=os.getenv("CRIME_GEMINI_MODEL", "gemini-2.5-flash"),
        mcp_url=mcp_url,
        mcp_api_key=mcp_key,
    )


app = FastAPI(title="CDMX Crime GIS", lifespan=lifespan)

origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    state = app.state.ingest
    return {
        "ok": True,
        "ingest": {k: state.get(k) for k in ("status", "started_at", "finished_at", "error")},
        "steps": state.get("steps", {}),
        "views_populated": await views_populated(app.state.db),
        "chat_enabled": app.state.chat_agent is not None,
    }


# Routers — registered after app+lifespan so they can pick up app.state.db
from routers import stops, routes, stations, crime, stats, chat  # noqa: E402

app.include_router(stops.router,    prefix="/api", tags=["stops"])
app.include_router(routes.router,   prefix="/api", tags=["routes"])
app.include_router(stations.router, prefix="/api", tags=["stations"])
app.include_router(crime.router,    prefix="/api", tags=["crime"])
app.include_router(stats.router,    prefix="/api", tags=["stats"])
app.include_router(chat.router,     prefix="/api", tags=["chat"])
