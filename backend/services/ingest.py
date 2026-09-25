"""Ingest orchestrator.

    gtfs -> boundaries -> hex cells -> ridership -> crime cases -> crime victims -> refresh views

Runs as a background task from the FastAPI lifespan (see main.py) so the API
answers immediately, and as a CLI for re-runs:

    docker compose exec crime-backend python -m services.ingest [--only crime_cases,crime_victims] [--force]

A Postgres advisory lock makes the run single-flight across processes.
`state` (a plain dict on app.state) is what /health reports.
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import time
from typing import Iterable

from . import ingest_boundaries, ingest_crime, ingest_gtfs, ingest_ridership

logger = logging.getLogger(__name__)

LOCK_KEY = "crime_ingest"
STEPS = ("gtfs", "boundaries", "hex_cells", "ridership", "crime_cases", "crime_victims", "refresh_views")

# Refresh order respects dependencies (station crime needs metro_stations + cases, etc.).
MATERIALIZED_VIEWS = (
    "mv_station_ridership_monthly",
    "mv_station_crime",
    "mv_hex_crime",
    "mv_colonia_crime_monthly",
    "mv_crime_daily",
)


def new_state() -> dict:
    return {"status": "idle", "started_at": None, "finished_at": None, "error": None,
            "steps": {s: {"status": "pending"} for s in STEPS}}


async def _refresh_mv(conn, name: str) -> None:
    populated = await conn.fetchval("SELECT relispopulated FROM pg_class WHERE relname = $1", name)
    if populated:
        await conn.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {name}")
    else:
        await conn.execute(f"REFRESH MATERIALIZED VIEW {name}")
    logger.info("refreshed %s", name)


async def refresh_views(conn, names: Iterable[str] = MATERIALIZED_VIEWS) -> None:
    # The shared postgres runs on an 8 GB host next to other apps: keep each
    # refresh single-process and index-driven rather than a parallel scan
    # (a parallel worker was OOM-killed refreshing mv_station_crime once).
    await conn.execute("SET max_parallel_workers_per_gather = 0")
    await conn.execute("SET work_mem = '64MB'")
    try:
        for name in names:
            await _refresh_mv(conn, name)
        await conn.execute("ANALYZE")
    finally:
        await conn.execute("RESET max_parallel_workers_per_gather")
        await conn.execute("RESET work_mem")


async def ensure_hex_cells(conn) -> None:
    """The hex grid is static; populate it once (crime ingest needs it)."""
    populated = await conn.fetchval("SELECT relispopulated FROM pg_class WHERE relname = 'mv_hex_cells'")
    if not populated:
        await conn.execute("REFRESH MATERIALIZED VIEW mv_hex_cells")
        logger.info("populated mv_hex_cells: %s cells", await conn.fetchval("SELECT COUNT(*) FROM mv_hex_cells"))


async def run_all(pool, state: dict, only: set[str] | None = None, force: bool = False) -> dict:
    state.update(status="running", started_at=time.time(), finished_at=None, error=None)
    for s in STEPS:
        state["steps"][s] = {"status": "pending"}

    async with pool.acquire() as conn:
        locked = await conn.fetchval("SELECT pg_try_advisory_lock(hashtext($1))", LOCK_KEY)
        if not locked:
            logger.warning("ingest already running elsewhere — skipping")
            state.update(status="skipped", finished_at=time.time())
            return state
        try:
            changed_any = False

            async def step(name, coro_factory):
                nonlocal changed_any
                if only and name not in only:
                    state["steps"][name] = {"status": "skipped"}
                    return None
                st = state["steps"][name] = {"status": "running", "started_at": time.time()}
                try:
                    result = await coro_factory()
                except Exception as exc:  # noqa: BLE001
                    st.update(status="error", error=f"{type(exc).__name__}: {exc}",
                              seconds=round(time.time() - st["started_at"], 1))
                    logger.exception("ingest step %s failed", name)
                    raise
                st.update(status="done", seconds=round(time.time() - st["started_at"], 1))
                # None / {} / 0 mean "nothing loaded" (hash unchanged or file absent);
                # only a real load should trigger the view refresh.
                if result not in (None, {}, 0):
                    st["result"] = result if isinstance(result, (int, dict)) else str(result)
                    changed_any = True
                return result

            await step("gtfs", lambda: ingest_gtfs.run(conn, force=force))
            await step("boundaries", lambda: ingest_boundaries.run(conn, force=force))
            await step("hex_cells", lambda: ensure_hex_cells(conn))
            await step("ridership", lambda: ingest_ridership.run(conn, force=force))

            def _progress_for(name):
                def cb(counters):
                    state["steps"][name]["progress"] = counters
                return cb

            await step("crime_cases", lambda: ingest_crime.run_one(
                conn, ingest_crime.CASES, force=force, progress=_progress_for("crime_cases")))
            await step("crime_victims", lambda: ingest_crime.run_one(
                conn, ingest_crime.VICTIMS, force=force, progress=_progress_for("crime_victims")))

            populated = await conn.fetchval(
                "SELECT relispopulated FROM pg_class WHERE relname = 'mv_station_crime'")
            if changed_any or force or not populated:
                await step("refresh_views", lambda: refresh_views(conn))
            else:
                state["steps"]["refresh_views"] = {"status": "skipped", "reason": "no source changed"}

            state.update(status="done", finished_at=time.time())
        except Exception as exc:  # noqa: BLE001
            state.update(status="error", finished_at=time.time(), error=f"{type(exc).__name__}: {exc}")
        finally:
            await conn.execute("SELECT pg_advisory_unlock(hashtext($1))", LOCK_KEY)
    logger.info("ingest finished: %s", state["status"])
    return state


async def _main_cli(args) -> int:
    from db import create_pool  # local import: CLI runs with backend/ as cwd
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO)
    pool = await create_pool()
    try:
        only = set(args.only.split(",")) if args.only else None
        if args.force and only:
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM data_ingest_runs WHERE source_name = ANY($1::TEXT[])",
                                   [_source_for(s) for s in only])
        state = await run_all(pool, new_state(), only=only, force=args.force)
    finally:
        await pool.close()
    for name, st in state["steps"].items():
        print(f"{name:14s} {st.get('status'):8s} {st.get('seconds', '')} {st.get('result', st.get('error', ''))}")
    return 0 if state["status"] == "done" else 1


def _source_for(step: str) -> str:
    return {"gtfs": "gtfs:all", "ridership": "ridership:metro_simple",
            "crime_cases": "crime:cases", "crime_victims": "crime:victims"}.get(step, step)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Run the crime GIS ingest pipeline.")
    ap.add_argument("--only", help="comma-separated subset of steps: " + ",".join(STEPS))
    ap.add_argument("--force", action="store_true", help="ignore the data_ingest_runs hash bookkeeping")
    raise SystemExit(asyncio.run(_main_cli(ap.parse_args())))
