"""Boundary ingestion: alcaldías (INEGI 2020) and colonias (catálogo de datos abiertos).

Both files are GeoJSON FeatureCollections in WGS84. Geometry is passed to
PostGIS as GeoJSON text and normalized with ST_MakeValid + ST_Multi so every
row is a MultiPolygon. Names are normalized (unaccent + lower) for joins.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path

from .ingest_runs import already_ran, hash_files, record_run
from .name_match import normalize

logger = logging.getLogger(__name__)

BOUNDARIES_DIR = Path(os.getenv("BOUNDARIES_DIR", "/app/boundaries"))


def _features(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        fc = json.load(f)
    return [ft for ft in fc.get("features", []) if ft.get("geometry")]


async def _load_alcaldias(conn, path: Path) -> int:
    feats = _features(path)
    records = []
    for ft in feats:
        p = ft.get("properties") or {}
        name = (p.get("NOMGEO") or p.get("nomgeo") or "").strip()
        if not name:
            continue
        records.append((p.get("CVEGEO") or p.get("cvegeo"), p.get("CVE_MUN") or p.get("cve_mun"),
                        name, normalize(name), json.dumps(ft["geometry"])))
    async with conn.transaction():
        await conn.execute("TRUNCATE alcaldias CASCADE")
        await conn.execute("""
            CREATE TEMP TABLE _stage_alc (cvegeo TEXT, cve_mun TEXT, nomgeo TEXT, nomgeo_norm TEXT, gj TEXT)
            ON COMMIT DROP
        """)
        await conn.copy_records_to_table("_stage_alc", records=records,
                                         columns=["cvegeo", "cve_mun", "nomgeo", "nomgeo_norm", "gj"])
        await conn.execute("""
            INSERT INTO alcaldias (cvegeo, cve_mun, nomgeo, nomgeo_norm, geom, area_km2)
            SELECT cvegeo, cve_mun, nomgeo, nomgeo_norm, g.geom, ST_Area(g.geom::geography) / 1e6
            FROM _stage_alc s
            CROSS JOIN LATERAL (
                SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(s.gj), 4326)), 3)) AS geom
            ) g
            WHERE NOT ST_IsEmpty(g.geom)
        """)
    return len(records)


async def _load_colonias(conn, path: Path) -> int:
    feats = _features(path)
    records = []
    for ft in feats:
        p = ft.get("properties") or {}
        name = (p.get("colonia") or "").strip()
        if not name:
            continue
        alc = (p.get("alc") or "").strip()
        records.append((p.get("cve_col"), name, normalize(name), p.get("cve_alc"), alc, normalize(alc),
                        p.get("clasif"), json.dumps(ft["geometry"])))
    async with conn.transaction():
        await conn.execute("TRUNCATE colonias CASCADE")
        await conn.execute("""
            CREATE TEMP TABLE _stage_col (cve_col TEXT, colonia TEXT, colonia_norm TEXT, cve_alc TEXT,
                                          alc TEXT, alc_norm TEXT, clasif TEXT, gj TEXT)
            ON COMMIT DROP
        """)
        await conn.copy_records_to_table(
            "_stage_col", records=records,
            columns=["cve_col", "colonia", "colonia_norm", "cve_alc", "alc", "alc_norm", "clasif", "gj"])
        await conn.execute("""
            INSERT INTO colonias (cve_col, colonia, colonia_norm, cve_alc, alc, alc_norm, clasif, geom, area_km2)
            SELECT cve_col, colonia, colonia_norm, cve_alc, alc, alc_norm, clasif, g.geom,
                   ST_Area(g.geom::geography) / 1e6
            FROM _stage_col s
            CROSS JOIN LATERAL (
                SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(s.gj), 4326)), 3)) AS geom
            ) g
            WHERE NOT ST_IsEmpty(g.geom)
        """)
    return len(records)


async def run(conn, force: bool = False) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source, fname, loader in (
        ("boundaries:alcaldias", "alcaldias.json", _load_alcaldias),
        ("boundaries:colonias", "colonias.json", _load_colonias),
    ):
        path = BOUNDARIES_DIR / fname
        if not path.exists():
            logger.warning("Boundary file not found: %s — skipping %s", path, source)
            continue
        src_hash = hash_files([path])
        if not force and await already_ran(conn, source, src_hash):
            logger.info("%s skipped — hash unchanged", source)
            continue
        n = await loader(conn, path)
        await record_run(conn, source, src_hash, n)
        counts[source] = n
        logger.info("%s loaded: %s features", source, n)
    return counts
