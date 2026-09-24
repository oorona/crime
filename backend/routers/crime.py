"""Crime geodata: points, hex heat, colonia and alcaldía choropleths."""
from __future__ import annotations
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from services.filters import (CASES_COLS, COLONIA_MV_COLS, DAILY_COLS, HEX_MV_COLS,
                              CrimeFilter, crime_filter)
from services.readiness import require_views

router = APIRouter(dependencies=[Depends(require_views)])

RES = (250, 500, 1000)


def _bbox(bbox: Optional[str]) -> Optional[tuple[float, float, float, float]]:
    if not bbox:
        return None
    try:
        minx, miny, maxx, maxy = (float(x) for x in bbox.split(","))
    except ValueError:
        raise HTTPException(400, "bbox must be 'minx,miny,maxx,maxy' (lon/lat)")
    return minx, miny, maxx, maxy


@router.get("/crime/points")
async def crime_points(
    request: Request,
    bbox: Optional[str] = Query(None, description="minx,miny,maxx,maxy (lon/lat)"),
    limit: int = Query(5000, ge=1, le=20000),
    f: CrimeFilter = Depends(crime_filter),
):
    """Individual cases (newest first), capped. `truncated` says whether more exist."""
    pool = request.app.state.db
    await f.resolve(pool)
    params: list = []
    preds = ["c.geom IS NOT NULL"]
    b = _bbox(bbox)
    if b:
        params.extend(b)
        preds.append(f"c.geom && ST_MakeEnvelope(${len(params)-3}, ${len(params)-2}, ${len(params)-1}, ${len(params)}, 4326)")
    w = f.where("c", params, CASES_COLS)
    if w:
        preds.append(w)
    params.append(limit + 1)
    rows = await pool.fetch(f"""
        SELECT c.id, c.delito, c.categoria_delito, c.fecha_hecho, c.hora_ok, c.transport_mode,
               c.colonia_catalogo, c.alcaldia_catalogo, c.nearest_station_key, c.nearest_station_m,
               ST_X(c.geom) AS lon, ST_Y(c.geom) AS lat
        FROM crime_cases c
        WHERE {' AND '.join(preds)}
        ORDER BY c.fecha_hecho DESC
        LIMIT ${len(params)}
    """, *params)
    truncated = len(rows) > limit
    rows = rows[:limit]
    return {
        "type": "FeatureCollection", "truncated": truncated, "count": len(rows), "filters": f.active(),
        "features": [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
             "properties": {
                 "id": r["id"], "delito": r["delito"], "categoria": r["categoria_delito"],
                 "fecha": r["fecha_hecho"].isoformat(sep=" ", timespec="minutes"), "hora_ok": r["hora_ok"],
                 "mode": r["transport_mode"], "colonia": r["colonia_catalogo"], "alcaldia": r["alcaldia_catalogo"],
                 "station": r["nearest_station_key"],
                 "station_m": round(r["nearest_station_m"]) if r["nearest_station_m"] is not None else None,
             }}
            for r in rows
        ],
    }


async def hex_counts(pool, f: CrimeFilter, res: int, bbox=None) -> list:
    """(i, j, n, geom/centroid) per cell for the filter. Uses the MV when the
    filter is expressible on it, otherwise groups live rows by their cell ids."""
    params: list = [res]
    if f.unsupported(HEX_MV_COLS):
        w = f.where("c", params, CASES_COLS)
        col = f"hex{res}"
        agg = f"""
            SELECT c.{col}_i AS i, c.{col}_j AS j, COUNT(*)::INT AS n
            FROM crime_cases c
            WHERE c.{col}_i IS NOT NULL {('AND ' + w) if w else ''}
            GROUP BY 1, 2"""
    else:
        w = f.where("m", params, HEX_MV_COLS)
        agg = f"""
            SELECT m.i, m.j, SUM(m.n_cases)::INT AS n
            FROM mv_hex_crime m
            WHERE m.res_m = $1 {('AND ' + w) if w else ''}
            GROUP BY 1, 2"""
    bpred = ""
    if bbox:
        params.extend(bbox)
        bpred = f"AND h.geom && ST_MakeEnvelope(${len(params)-3}, ${len(params)-2}, ${len(params)-1}, ${len(params)}, 4326)"
    return await pool.fetch(f"""
        WITH agg AS ({agg})
        SELECT agg.i, agg.j, agg.n,
               ST_AsGeoJSON(h.geom) AS hex_json, ST_X(h.centroid) AS lon, ST_Y(h.centroid) AS lat
        FROM agg
        JOIN mv_hex_cells h ON h.res_m = $1 AND h.i = agg.i AND h.j = agg.j
        WHERE TRUE {bpred}
    """, *params)


@router.get("/crime/heat")
async def crime_heat(
    request: Request,
    res: int = Query(500, description="Hex cell size in meters: 250, 500 or 1000"),
    geom: str = Query("centroid", pattern="^(centroid|hex)$"),
    bbox: Optional[str] = Query(None),
    f: CrimeFilter = Depends(crime_filter),
):
    """Aggregated cases per hex cell. `n_norm` is n / max(n) for heatmap weights."""
    if res not in RES:
        raise HTTPException(400, f"res must be one of {RES}")
    pool = request.app.state.db
    await f.resolve(pool)
    rows = await hex_counts(pool, f, res, _bbox(bbox))
    mx = max((int(r["n"]) for r in rows), default=0) or 1
    feats = []
    for r in rows:
        n = int(r["n"])
        g = json.loads(r["hex_json"]) if geom == "hex" else {"type": "Point", "coordinates": [r["lon"], r["lat"]]}
        feats.append({"type": "Feature", "geometry": g,
                      "properties": {"i": r["i"], "j": r["j"], "n": n, "n_norm": round(n / mx, 4)}})
    return {"type": "FeatureCollection", "res_m": res, "max_n": mx, "count": len(feats),
            "filters": f.active(), "features": feats}


@router.get("/crime/colonias")
async def crime_colonias(
    request: Request,
    normalize: str = Query("count", pattern="^(count|per_km2)$"),
    simplify: float = Query(0.0001, ge=0, le=0.01, description="ST_SimplifyPreserveTopology tolerance (deg)"),
    f: CrimeFilter = Depends(crime_filter),
):
    pool = request.app.state.db
    await f.resolve(pool)
    params: list = []
    if f.unsupported(COLONIA_MV_COLS):
        w = f.where("c", params, CASES_COLS)
        agg = f"SELECT c.colonia_id, COUNT(*)::INT AS n FROM crime_cases c WHERE c.colonia_id IS NOT NULL {('AND ' + w) if w else ''} GROUP BY 1"
    else:
        w = f.where("m", params, COLONIA_MV_COLS)
        agg = f"SELECT m.colonia_id, SUM(m.n_cases)::INT AS n FROM mv_colonia_crime_monthly m {('WHERE ' + w) if w else ''} GROUP BY 1"
    params.append(simplify)
    metric = "n" if normalize == "count" else "per_km2"
    rows = await pool.fetch(f"""
        WITH agg AS ({agg}),
        j AS (
            SELECT k.id, k.colonia, k.alc, k.cve_col, k.area_km2,
                   COALESCE(agg.n, 0) AS n,
                   CASE WHEN k.area_km2 > 0 THEN COALESCE(agg.n, 0) / k.area_km2 END AS per_km2,
                   ST_AsGeoJSON(ST_SimplifyPreserveTopology(k.geom, ${len(params)})) AS gj
            FROM colonias k LEFT JOIN agg ON agg.colonia_id = k.id
        )
        SELECT j.*, CASE WHEN j.n > 0 THEN ntile(5) OVER (PARTITION BY (j.n > 0) ORDER BY j.{metric}) ELSE 0 END AS quantile
        FROM j
    """, *params)
    return {
        "type": "FeatureCollection", "metric": metric, "filters": f.active(), "count": len(rows),
        "features": [
            {"type": "Feature", "geometry": json.loads(r["gj"]),
             "properties": {"id": r["id"], "colonia": r["colonia"], "alcaldia": r["alc"], "cve_col": r["cve_col"],
                            "area_km2": round(r["area_km2"], 3) if r["area_km2"] else None,
                            "n": int(r["n"]), "per_km2": round(r["per_km2"], 1) if r["per_km2"] is not None else None,
                            "quantile": int(r["quantile"])}}
            for r in rows
        ],
    }


@router.get("/crime/alcaldias")
async def crime_alcaldias(
    request: Request,
    simplify: float = Query(0.0005, ge=0, le=0.01),
    f: CrimeFilter = Depends(crime_filter),
):
    pool = request.app.state.db
    await f.resolve(pool)
    params: list = []
    if f.unsupported(DAILY_COLS):
        w = f.where("c", params, CASES_COLS)
        agg = f"SELECT c.alcaldia_id, COUNT(*)::INT AS n FROM crime_cases c WHERE c.alcaldia_id IS NOT NULL {('AND ' + w) if w else ''} GROUP BY 1"
    else:
        w = f.where("m", params, DAILY_COLS)
        agg = f"SELECT m.alcaldia_id, SUM(m.n_cases)::INT AS n FROM mv_crime_daily m WHERE m.alcaldia_id IS NOT NULL {('AND ' + w) if w else ''} GROUP BY 1"
    params.append(simplify)
    rows = await pool.fetch(f"""
        WITH agg AS ({agg})
        SELECT a.id, a.nomgeo, a.cvegeo, a.area_km2, COALESCE(agg.n, 0) AS n,
               CASE WHEN a.area_km2 > 0 THEN COALESCE(agg.n, 0) / a.area_km2 END AS per_km2,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(a.geom, ${len(params)})) AS gj
        FROM alcaldias a LEFT JOIN agg ON agg.alcaldia_id = a.id
        ORDER BY n DESC
    """, *params)
    return {
        "type": "FeatureCollection", "filters": f.active(),
        "features": [
            {"type": "Feature", "geometry": json.loads(r["gj"]),
             "properties": {"id": r["id"], "alcaldia": r["nomgeo"], "cvegeo": r["cvegeo"],
                            "area_km2": round(r["area_km2"], 2) if r["area_km2"] else None,
                            "n": int(r["n"]), "per_km2": round(r["per_km2"], 1) if r["per_km2"] is not None else None,
                            "rank": i + 1}}
            for i, r in enumerate(rows)
        ],
    }
