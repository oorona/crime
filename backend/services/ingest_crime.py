"""FGJ crime ingestion: carpetas de investigación (cases) and víctimas (victims).

Both files are single accumulated snapshots with no stable case id, so each
load is a full TRUNCATE + reload. Rows stream through pandas in 200k-row
chunks into an UNLOGGED staging table via COPY; one SQL pass then builds the
final rows with geometry, derived time columns, and the spatial enrichments
(alcaldía, colonia, nearest Metro station, hex cell ids for three resolutions)
computed with LATERAL joins so the big table is written exactly once.

Idempotent via `data_ingest_runs` (SHA-256 of the file). Only rows with a
parseable `fecha_hecho` in [MIN_YEAR, MAX_YEAR] are kept.
"""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

from .crime_parsing import clean_text, parse_coords, parse_dt, parse_edad, transport_mode
from .ingest_runs import already_ran, hash_files, record_run

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
MIN_YEAR = int(os.getenv("CRIME_MIN_YEAR", "2019"))
MAX_YEAR = 2030
CHUNK = 200_000

COMMON_IN = [
    "fecha_hecho", "hora_hecho", "fecha_inicio", "hora_inicio", "delito", "categoria_delito",
    "competencia", "colonia_hecho", "colonia_catalogo", "alcaldia_hecho", "alcaldia_catalogo",
    "municipio_hecho", "latitud", "longitud",
]
COMMON_STAGE = [
    "fecha_hecho", "fecha_inicio", "hora_ok", "delito", "categoria_delito", "competencia",
    "colonia_hecho", "colonia_catalogo", "alcaldia_hecho", "alcaldia_catalogo", "municipio_hecho",
    "lat", "lon", "transport_mode", "source_row",
]


@dataclass
class Spec:
    source: str
    table: str
    glob: str
    extra_in: list[str]
    extra_stage: list[str]
    extra_stage_ddl: str
    extra_values: Callable[[object], tuple]
    counters: dict = field(default_factory=dict)


CASES = Spec(
    source="crime:cases", table="crime_cases", glob="carpetasFGJ_acumulado_*.csv",
    extra_in=["fiscalia", "agencia", "unidad_investigacion"],
    extra_stage=["fiscalia", "agencia", "unidad_investigacion"],
    extra_stage_ddl="fiscalia TEXT, agencia TEXT, unidad_investigacion TEXT",
    extra_values=lambda r: (clean_text(r.fiscalia), clean_text(r.agencia), clean_text(r.unidad_investigacion)),
)
VICTIMS = Spec(
    source="crime:victims", table="crime_victims", glob="victimasFGJ_acumulado_*.csv",
    extra_in=["sexo", "edad", "tipo_persona", "calidad_juridica"],
    extra_stage=["sexo", "edad", "tipo_persona", "calidad_juridica"],
    extra_stage_ddl="sexo TEXT, edad SMALLINT, tipo_persona TEXT, calidad_juridica TEXT",
    extra_values=lambda r: (clean_text(r.sexo), parse_edad(r.edad), clean_text(r.tipo_persona),
                            clean_text(r.calidad_juridica)),
)


def find_file(spec: Spec) -> Path | None:
    files = sorted(DATA_DIR.glob(spec.glob))
    return files[-1] if files else None


def _records(df: pd.DataFrame, spec: Spec, offset: int, counters: dict) -> list[tuple]:
    out = []
    for i, r in enumerate(df.itertuples(index=False)):
        counters["read"] += 1
        ts, hora_ok = parse_dt(r.fecha_hecho, r.hora_hecho)
        if ts is None:
            counters["dropped_no_date"] += 1
            continue
        if ts.year < MIN_YEAR or ts.year > MAX_YEAR:
            counters["dropped_out_of_range"] += 1
            continue
        delito = clean_text(r.delito)
        categoria = clean_text(r.categoria_delito)
        if not delito or not categoria:
            counters["dropped_no_delito"] += 1
            continue
        lat, lon = parse_coords(r.latitud, r.longitud)
        if lat is None:
            counters["no_geom"] += 1
        ts_inicio, _ = parse_dt(r.fecha_inicio, r.hora_inicio)
        out.append((
            ts, ts_inicio, hora_ok, delito, categoria, clean_text(r.competencia),
            clean_text(r.colonia_hecho), clean_text(r.colonia_catalogo),
            clean_text(r.alcaldia_hecho), clean_text(r.alcaldia_catalogo), clean_text(r.municipio_hecho),
            lat, lon, transport_mode(delito, categoria), offset + i,
        ) + spec.extra_values(r))
    return out


_INSERT_SQL = """
    INSERT INTO {table} (
        fecha_hecho, fecha_inicio, hora_ok, delito, categoria_delito, competencia,
        colonia_hecho, colonia_catalogo, alcaldia_hecho, alcaldia_catalogo, municipio_hecho,
        lat, lon, geom, geom_utm, year, month, ym, dow, hour,
        is_transport_related, transport_mode, alcaldia_id, colonia_id,
        nearest_station_key, nearest_station_m,
        hex250_i, hex250_j, hex500_i, hex500_j, hex1000_i, hex1000_j,
        source_row, {extra_cols}
    )
    SELECT
        s.fecha_hecho, s.fecha_inicio, s.hora_ok, s.delito, s.categoria_delito, s.competencia,
        s.colonia_hecho, s.colonia_catalogo, s.alcaldia_hecho, s.alcaldia_catalogo, s.municipio_hecho,
        s.lat, s.lon, p.geom,
        CASE WHEN p.geom IS NOT NULL THEN ST_Transform(p.geom, 32614) END,
        EXTRACT(YEAR  FROM s.fecha_hecho)::SMALLINT,
        EXTRACT(MONTH FROM s.fecha_hecho)::SMALLINT,
        (EXTRACT(YEAR FROM s.fecha_hecho) * 100 + EXTRACT(MONTH FROM s.fecha_hecho))::INT,
        EXTRACT(ISODOW FROM s.fecha_hecho)::SMALLINT,
        CASE WHEN s.hora_ok THEN EXTRACT(HOUR FROM s.fecha_hecho)::SMALLINT END,
        s.transport_mode IS NOT NULL, s.transport_mode,
        a.id, k.id, ns.station_key, ns.d,
        h250.i, h250.j, h500.i, h500.j, h1000.i, h1000.j,
        s.source_row, {extra_sel}
    FROM {stage} s
    CROSS JOIN LATERAL (
        SELECT CASE WHEN s.lat IS NOT NULL THEN ST_SetSRID(ST_MakePoint(s.lon, s.lat), 4326) END AS geom
    ) p
    LEFT JOIN LATERAL (
        SELECT a.id FROM alcaldias a WHERE p.geom IS NOT NULL AND ST_Contains(a.geom, p.geom) LIMIT 1
    ) a ON TRUE
    LEFT JOIN LATERAL (
        SELECT k.id FROM colonias k WHERE p.geom IS NOT NULL AND ST_Contains(k.geom, p.geom) LIMIT 1
    ) k ON TRUE
    LEFT JOIN LATERAL (
        SELECT ms.station_key, ST_Distance(ms.pts::geography, p.geom::geography)::REAL AS d
        FROM metro_stations ms
        WHERE p.geom IS NOT NULL
        ORDER BY ms.geom <-> p.geom
        LIMIT 1
    ) ns ON TRUE
    LEFT JOIN LATERAL (
        SELECT h.i, h.j FROM mv_hex_cells h
        WHERE h.res_m = 250 AND p.geom IS NOT NULL AND ST_Intersects(h.geom, p.geom) LIMIT 1
    ) h250 ON TRUE
    LEFT JOIN LATERAL (
        SELECT h.i, h.j FROM mv_hex_cells h
        WHERE h.res_m = 500 AND p.geom IS NOT NULL AND ST_Intersects(h.geom, p.geom) LIMIT 1
    ) h500 ON TRUE
    LEFT JOIN LATERAL (
        SELECT h.i, h.j FROM mv_hex_cells h
        WHERE h.res_m = 1000 AND p.geom IS NOT NULL AND ST_Intersects(h.geom, p.geom) LIMIT 1
    ) h1000 ON TRUE
"""


async def _load(conn, spec: Spec, path: Path, progress: Callable[[dict], None] | None = None) -> dict:
    counters = {k: 0 for k in ("read", "kept", "dropped_no_date", "dropped_out_of_range",
                               "dropped_no_delito", "no_geom")}
    stage = f"_stage_{spec.table}"
    stage_cols = COMMON_STAGE + spec.extra_stage

    await conn.execute(f"DROP TABLE IF EXISTS {stage}")
    await conn.execute(f"""
        CREATE UNLOGGED TABLE {stage} (
            fecha_hecho TIMESTAMP, fecha_inicio TIMESTAMP, hora_ok BOOLEAN,
            delito TEXT, categoria_delito TEXT, competencia TEXT,
            colonia_hecho TEXT, colonia_catalogo TEXT, alcaldia_hecho TEXT, alcaldia_catalogo TEXT,
            municipio_hecho TEXT, lat DOUBLE PRECISION, lon DOUBLE PRECISION,
            transport_mode TEXT, source_row BIGINT, {spec.extra_stage_ddl}
        )
    """)
    try:
        usecols = COMMON_IN + spec.extra_in
        reader = pd.read_csv(
            path, usecols=lambda c: c in usecols, dtype=str, keep_default_na=False,
            chunksize=CHUNK, encoding="utf-8", encoding_errors="replace", on_bad_lines="warn",
        )
        offset = 0
        for chunk in reader:
            for c in usecols:
                if c not in chunk.columns:
                    chunk[c] = ""
            recs = _records(chunk, spec, offset, counters)
            offset += len(chunk)
            if recs:
                await conn.copy_records_to_table(stage, records=recs, columns=stage_cols)
                counters["kept"] += len(recs)
            if progress:
                progress(dict(counters))
            logger.info("%s: staged %s / read %s", spec.source, counters["kept"], counters["read"])

        async with conn.transaction():
            await conn.execute(f"TRUNCATE {spec.table}")
            await conn.execute(_INSERT_SQL.format(
                table=spec.table, stage=stage,
                extra_cols=", ".join(spec.extra_stage),
                extra_sel=", ".join(f"s.{c}" for c in spec.extra_stage),
            ))
        await conn.execute(f"ANALYZE {spec.table}")
    finally:
        await conn.execute(f"DROP TABLE IF EXISTS {stage}")
    return counters


async def run_one(conn, spec: Spec, force: bool = False, progress=None) -> dict | None:
    path = find_file(spec)
    if path is None:
        logger.warning("No %s in %s — skipping %s", spec.glob, DATA_DIR, spec.source)
        return None
    src_hash = hash_files([path])
    if not force and await already_ran(conn, spec.source, src_hash):
        logger.info("%s skipped — hash unchanged", spec.source)
        return None
    logger.info("%s: loading %s (%.0f MB)…", spec.source, path.name, path.stat().st_size / 1e6)
    counters = await _load(conn, spec, path, progress)
    await record_run(conn, spec.source, src_hash, counters["kept"])
    logger.info("%s complete: %s", spec.source, counters)
    return counters
