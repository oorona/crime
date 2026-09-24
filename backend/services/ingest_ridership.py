"""Metro ridership ingestion ("afluencia simple": one row per day × line × station).

Reuses metro's mojibake repair and station-name resolver. Only rows from
2019 onward are kept (the crime window); the file itself starts in 2010.
"""
from __future__ import annotations
import logging
import os
from datetime import date as _date
from pathlib import Path

import pandas as pd

from .ingest_runs import already_ran, hash_files, record_run
from .name_match import MetroStopResolver, fix_mojibake, normalize, parse_metro_line

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
RIDERSHIP_GLOB = "afluencia_metro_simple*.csv"
MIN_DATE = _date(2019, 1, 1)


def _to_date(s: str | None):
    if not s:
        return None
    try:
        return _date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _to_count(s) -> int:
    if s is None or s == "":
        return 0
    try:
        return int(round(float(s)))
    except (TypeError, ValueError):
        return 0


def _read_metro_csv(path: Path) -> pd.DataFrame:
    """The Metro CSV is double-encoded mojibake; read as UTF-8 then unmangle in-Python."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for col in ("linea", "estacion", "mes"):
        if col in df.columns:
            df[col] = df[col].apply(fix_mojibake)
    return df


def find_file() -> Path | None:
    files = sorted(DATA_DIR.glob(RIDERSHIP_GLOB))
    return files[-1] if files else None


async def _load_metro(conn, path: Path) -> int:
    df = _read_metro_csv(path)
    df = df[df["fecha"] >= MIN_DATE.isoformat()]
    resolver = MetroStopResolver(conn)

    name_to_stop: dict[tuple[str, str], str | None] = {}
    unresolved: list[tuple[str, str]] = []
    for line, station in df[["linea", "estacion"]].drop_duplicates().itertuples(index=False):
        sid = await resolver.resolve(line, station)
        name_to_stop[(line, station)] = sid
        if sid is None:
            unresolved.append((line, station))
    if unresolved:
        logger.warning("ridership: %d (line, station) pairs did not resolve to a stop_id: %s",
                       len(unresolved), unresolved[:15])

    records = []
    for r in df.itertuples(index=False):
        d = _to_date(r.fecha)
        if d is None:
            continue
        records.append((d, parse_metro_line(r.linea) or "", r.estacion, normalize(r.estacion),
                        _to_count(r.afluencia), name_to_stop.get((r.linea, r.estacion))))

    async with conn.transaction():
        await conn.execute("""
            CREATE TEMP TABLE _stage_metro (
                date DATE, line TEXT, station_name TEXT, station_name_norm TEXT, count INTEGER, stop_id TEXT
            ) ON COMMIT DROP
        """)
        await conn.copy_records_to_table(
            "_stage_metro", records=records,
            columns=["date", "line", "station_name", "station_name_norm", "count", "stop_id"])
        await conn.execute("""
            INSERT INTO ridership_metro_station_daily
                (date, line, station_name, station_name_norm, count, stop_id)
            SELECT date, line, station_name, station_name_norm, SUM(count)::INT, MAX(stop_id)
            FROM _stage_metro
            GROUP BY date, line, station_name, station_name_norm
            ON CONFLICT (date, line, station_name) DO UPDATE
                SET count = EXCLUDED.count,
                    stop_id = COALESCE(EXCLUDED.stop_id, ridership_metro_station_daily.stop_id),
                    station_name_norm = EXCLUDED.station_name_norm
        """)
    return len(records)


async def run(conn, force: bool = False) -> int | None:
    path = find_file()
    if path is None:
        logger.warning("No %s in %s — skipping ridership ingest", RIDERSHIP_GLOB, DATA_DIR)
        return None
    src_hash = hash_files([path])
    if not force and await already_ran(conn, "ridership:metro_simple", src_hash):
        logger.info("Ridership ingest skipped — hash unchanged")
        return None
    n = await _load_metro(conn, path)
    await record_run(conn, "ridership:metro_simple", src_hash, n)
    logger.info("Ridership loaded from %s: %s rows", path.name, n)
    return n
