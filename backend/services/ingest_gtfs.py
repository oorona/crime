"""GTFS static ingestion (crime-app subset).

Reads the on-disk GTFS feed into PostgreSQL with COPY, derives geometry
columns (`stops.geom`, `shape_lines.geom`), derives `stops.agency_id` /
`stops.line_code`, and builds `metro_stations` — one row per physical Metro
station (name cluster) with all its platforms as a MultiPoint.

Idempotent: hashes the source files and skips the run when the hash matches
the latest `data_ingest_runs` row for `gtfs:all`.
"""
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Iterable

import pandas as pd

from .ingest_runs import already_ran, hash_files, record_run
from .name_match import normalize

logger = logging.getLogger(__name__)

GTFS_DIR = Path(os.getenv("GTFS_DIR", "/app/gtfs"))
GTFS_FILES = ("agency.txt", "routes.txt", "stops.txt", "trips.txt", "stop_times.txt", "shapes.txt")


def _to_secs(t: str | None) -> int | None:
    """Parse 'HH:MM:SS' (allows H >= 24, GTFS overflow) into seconds-after-midnight."""
    if not t or t == "" or pd.isna(t):
        return None
    try:
        h, m, s = t.split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    except (ValueError, AttributeError):
        return None


def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(GTFS_DIR / name, dtype=str, keep_default_na=False)


async def _copy_records(conn, table: str, columns: list[str], records: Iterable[tuple]):
    await conn.copy_records_to_table(table, records=list(records), columns=columns)


def _int_or_none(v):
    try:
        return int(float(v)) if v not in ("", None) else None
    except (TypeError, ValueError):
        return None


def _float_or_none(v):
    try:
        return float(v) if v not in ("", None) else None
    except (TypeError, ValueError):
        return None


async def run(conn, force: bool = False) -> int | None:
    """Run the full GTFS ingest unless source hash is unchanged. Returns row count or None if skipped."""
    if not GTFS_DIR.is_dir():
        logger.warning("GTFS dir %s not found — skipping ingest", GTFS_DIR)
        return None

    paths = [GTFS_DIR / f for f in GTFS_FILES if (GTFS_DIR / f).exists()]
    if len(paths) < len(GTFS_FILES):
        logger.warning("GTFS dir %s is missing files (have %s) — skipping ingest", GTFS_DIR, [p.name for p in paths])
        return None
    src_hash = hash_files(paths)
    if not force and await already_ran(conn, "gtfs:all", src_hash):
        logger.info("GTFS ingest skipped — hash unchanged")
        return None

    logger.info("GTFS ingest starting (%d files)…", len(paths))
    await conn.execute(
        "TRUNCATE shape_lines, shape_points, stop_times, trips, routes, stops, agencies RESTART IDENTITY CASCADE"
    )

    # ── agencies ──────────────────────────────────────────────────────────────
    df = _read("agency.txt")
    await _copy_records(
        conn, "agencies",
        ["agency_id", "agency_name", "agency_url", "agency_timezone", "agency_lang"],
        ((r.agency_id, r.agency_name, r.agency_url, r.agency_timezone, r.agency_lang) for r in df.itertuples()),
    )

    # ── routes (auto-create any agency_id referenced but missing) ────────────
    df = _read("routes.txt")
    seen = {r["agency_id"] for r in await conn.fetch("SELECT agency_id FROM agencies")}
    for ag in sorted(set(df["agency_id"].unique()) - seen):
        await conn.execute(
            "INSERT INTO agencies (agency_id, agency_name) VALUES ($1, $1) ON CONFLICT DO NOTHING", ag
        )
    await _copy_records(
        conn, "routes",
        ["route_id", "agency_id", "route_short_name", "route_long_name",
         "route_type", "route_color", "route_text_color"],
        ((r.route_id, r.agency_id, r.route_short_name, r.route_long_name,
          _int_or_none(r.route_type), r.route_color, r.route_text_color)
         for r in df.itertuples()),
    )

    # ── stops ────────────────────────────────────────────────────────────────
    df = _read("stops.txt")
    df["stop_lat"] = df["stop_lat"].astype(float)
    df["stop_lon"] = df["stop_lon"].astype(float)
    df["stop_name_norm"] = df["stop_name"].apply(normalize)
    wcb = df.get("wheelchair_boarding", pd.Series([""] * len(df)))
    df["wheelchair_boarding"] = pd.to_numeric(wcb, errors="coerce").fillna(0).astype(int)
    await _copy_records(
        conn, "stops",
        ["stop_id", "stop_name", "stop_lat", "stop_lon", "zone_id", "wheelchair_boarding", "stop_name_norm"],
        ((r.stop_id, r.stop_name, r.stop_lat, r.stop_lon, r.zone_id, int(r.wheelchair_boarding), r.stop_name_norm)
         for r in df.itertuples()),
    )
    await conn.execute("UPDATE stops SET geom = ST_SetSRID(ST_MakePoint(stop_lon, stop_lat), 4326)")

    # ── trips ─────────────────────────────────────────────────────────────────
    df = _read("trips.txt")
    await _copy_records(
        conn, "trips",
        ["trip_id", "route_id", "service_id", "shape_id", "trip_headsign", "trip_short_name", "direction_id"],
        ((r.trip_id, r.route_id, r.service_id, r.shape_id, r.trip_headsign, r.trip_short_name,
          _int_or_none(r.direction_id)) for r in df.itertuples()),
    )

    # ── stop_times ────────────────────────────────────────────────────────────
    df = _read("stop_times.txt")
    await _copy_records(
        conn, "stop_times",
        ["trip_id", "timepoint", "stop_id", "stop_sequence", "arrival_time", "departure_time",
         "arrival_secs", "departure_secs"],
        ((r.trip_id, _int_or_none(r.timepoint), r.stop_id, int(r.stop_sequence),
          r.arrival_time, r.departure_time, _to_secs(r.arrival_time), _to_secs(r.departure_time))
         for r in df.itertuples()),
    )

    # ── shape_points + shape_lines ───────────────────────────────────────────
    df = _read("shapes.txt")
    df["shape_pt_lat"] = df["shape_pt_lat"].astype(float)
    df["shape_pt_lon"] = df["shape_pt_lon"].astype(float)
    await _copy_records(
        conn, "shape_points",
        ["shape_id", "shape_pt_sequence", "shape_pt_lat", "shape_pt_lon", "shape_dist_traveled"],
        ((r.shape_id, int(r.shape_pt_sequence), r.shape_pt_lat, r.shape_pt_lon, _float_or_none(r.shape_dist_traveled))
         for r in df.itertuples()),
    )
    await conn.execute("""
        INSERT INTO shape_lines (shape_id, route_id, agency_id, geom)
        SELECT sp.shape_id,
               first_route.route_id,
               first_route.agency_id,
               ST_MakeLine(ST_SetSRID(ST_MakePoint(sp.shape_pt_lon, sp.shape_pt_lat), 4326)
                           ORDER BY sp.shape_pt_sequence)
        FROM shape_points sp
        LEFT JOIN LATERAL (
            SELECT t.route_id, r.agency_id
            FROM trips t
            JOIN routes r ON r.route_id = t.route_id
            WHERE t.shape_id = sp.shape_id
            ORDER BY t.trip_id
            LIMIT 1
        ) first_route ON TRUE
        GROUP BY sp.shape_id, first_route.route_id, first_route.agency_id
    """)

    # ── derive stop.agency_id and stop.line_code from the GTFS ref graph ─────
    # A stop can serve multiple agencies (transfer stations); pick the most
    # frequent. line_code is normalized to L1 / LA form.
    await conn.execute("""
        WITH stop_agency AS (
            SELECT st.stop_id, r.agency_id, r.route_short_name AS line_code, COUNT(*) AS n
            FROM stop_times st
            JOIN trips t ON t.trip_id = st.trip_id
            JOIN routes r ON r.route_id = t.route_id
            GROUP BY st.stop_id, r.agency_id, r.route_short_name
        ),
        ranked AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY stop_id ORDER BY n DESC) AS rk
            FROM stop_agency
        )
        UPDATE stops s
        SET agency_id = r.agency_id,
            line_code = CASE WHEN r.line_code ~ '^L?\\d+[A-Z]?$' OR r.line_code ~ '^L?[A-Z]$' THEN
                              CASE WHEN r.line_code LIKE 'L%' THEN r.line_code ELSE 'L' || r.line_code END
                         ELSE r.line_code
                         END
        FROM ranked r
        WHERE r.stop_id = s.stop_id AND r.rk = 1
    """)

    # ── metro_stations: one row per physical station (name cluster) ────────
    await conn.execute("TRUNCATE metro_stations")
    await conn.execute("""
        INSERT INTO metro_stations (station_key, station_name, stop_ids, lines, geom, pts, pts_utm)
        SELECT stop_name_norm,
               MIN(stop_name),
               array_agg(stop_id ORDER BY stop_id),
               array_agg(DISTINCT line_code ORDER BY line_code),
               ST_Centroid(ST_Collect(geom)),
               ST_Multi(ST_Collect(geom)),
               ST_Transform(ST_Multi(ST_Collect(geom)), 32614)
        FROM stops
        WHERE agency_id = 'METRO' AND geom IS NOT NULL AND stop_name_norm <> ''
        GROUP BY stop_name_norm
    """)
    wide = await conn.fetch("""
        SELECT station_key, ST_MaxDistance(pts, pts) AS spread_deg
        FROM metro_stations WHERE ST_MaxDistance(pts, pts) > 0.006
    """)
    for w in wide:
        logger.warning("metro_stations cluster %s spans %.4f deg (~%.0f m) — check name collision",
                       w["station_key"], w["spread_deg"], w["spread_deg"] * 111_000)

    await conn.execute("ANALYZE")
    n = await conn.fetchval("SELECT (SELECT COUNT(*) FROM stops) + (SELECT COUNT(*) FROM stop_times)")
    await record_run(conn, "gtfs:all", src_hash, int(n))
    logger.info(
        "GTFS ingest complete: stops=%s routes=%s trips=%s stop_times=%s metro_stations=%s",
        await conn.fetchval("SELECT COUNT(*) FROM stops"),
        await conn.fetchval("SELECT COUNT(*) FROM routes"),
        await conn.fetchval("SELECT COUNT(*) FROM trips"),
        await conn.fetchval("SELECT COUNT(*) FROM stop_times"),
        await conn.fetchval("SELECT COUNT(*) FROM metro_stations"),
    )
    return int(n)
