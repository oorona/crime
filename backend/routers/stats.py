"""Small-JSON statistics endpoints. Each doubles as an MCP tool payload for the
chat agent, so responses echo the window and filters and stay compact."""
from __future__ import annotations
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from services.coverage import coverage
from services.crime_parsing import MODE_LABELS
from services.filters import CASES_COLS, DAILY_COLS, CrimeFilter, crime_filter
from services.readiness import require_views
from .crime import hex_counts

router = APIRouter(dependencies=[Depends(require_views)])

CAVEATS = [
    "Los datos son carpetas de investigación (denuncias) de la FGJ CDMX, no incidencia real: la cifra negra "
    "(delitos no denunciados) es alta y varía por tipo de delito y zona.",
    "La ubicación es la del hecho según la carpeta; ~6% de las carpetas no tienen coordenadas (indeterminadas o "
    "fuera de CDMX) y no aparecen en mapas ni en estadísticas por estación/colonia.",
    "Las estadísticas por estación cuentan carpetas dentro de un radio (300 m por defecto) alrededor de todas las "
    "plataformas de la estación; los radios de estaciones vecinas se traslapan y una carpeta puede contar en dos.",
    "La tasa por millón usa las entradas al Metro de la estación en los mismos meses; estaciones sin afluencia no "
    "tienen tasa.",
    "La hora del hecho falta o es 00:00 (marcador) en una parte de las carpetas; los perfiles por hora solo usan "
    "carpetas con hora válida (ver hora_ok_share).",
    "'DELITO DE BAJO IMPACTO' agrupa la gran mayoría de las carpetas; 'HECHO NO DELICTIVO' se excluye por defecto.",
    "Víctimas y carpetas son tablas separadas sin identificador común; una carpeta puede tener varias víctimas.",
]


def _daily_or_live(f: CrimeFilter, params: list, alias_mv="m", alias_c="c") -> tuple[str, str, bool]:
    """Returns (FROM+WHERE sql, count expression, is_live)."""
    if f.unsupported(DAILY_COLS):
        w = f.where(alias_c, params, CASES_COLS)
        return f"FROM crime_cases {alias_c} {('WHERE ' + w) if w else ''}", "COUNT(*)", True
    w = f.where(alias_mv, params, DAILY_COLS)
    return f"FROM mv_crime_daily {alias_mv} {('WHERE ' + w) if w else ''}", f"SUM({alias_mv}.n_cases)", False


async def _window(pool, f: CrimeFilter) -> dict:
    cov = await coverage(pool)
    d_from = max(f.date_from, cov["date_from"]) if (f.date_from and cov["date_from"]) else (f.date_from or cov["date_from"])
    d_to = min(f.date_to, cov["date_to"]) if (f.date_to and cov["date_to"]) else (f.date_to or cov["date_to"])
    months = ((d_to.year - d_from.year) * 12 + d_to.month - d_from.month + 1) if (d_from and d_to) else 0
    return {"from": d_from.isoformat() if d_from else None, "to": d_to.isoformat() if d_to else None, "months": months}


@router.get("/stats/coverage")
async def stats_coverage(request: Request):
    pool = request.app.state.db
    r = await pool.fetchrow("SELECT * FROM v_coverage")
    return {
        "cases": {"rows": r["cases_rows"], "from": r["cases_from"].date().isoformat() if r["cases_from"] else None,
                  "to": r["cases_to"].date().isoformat() if r["cases_to"] else None,
                  "without_coordinates": r["cases_no_geom"],
                  "hora_ok_share": round(r["cases_hora_ok"] / r["cases_rows"], 3) if r["cases_rows"] else None},
        "victims": {"rows": r["victims_rows"], "from": r["victims_from"].date().isoformat() if r["victims_from"] else None,
                    "to": r["victims_to"].date().isoformat() if r["victims_to"] else None},
        "ridership": {"from": r["ridership_from"].isoformat() if r["ridership_from"] else None,
                      "to": r["ridership_to"].isoformat() if r["ridership_to"] else None},
        "stations": r["stations"], "colonias": r["colonias"],
        "ingested_at": r["ingested_at"].isoformat() if r["ingested_at"] else None,
        "default_station_radius_m": 300,
        "transport_modes": MODE_LABELS,
        "sources": {
            "carpetas": "FGJ CDMX, Carpetas de investigación (datos.cdmx.gob.mx, CC-BY-4.0)",
            "victimas": "FGJ CDMX, Víctimas en carpetas de investigación (datos.cdmx.gob.mx, CC-BY-4.0)",
            "afluencia": "SEMOVI / STC Metro, Afluencia diaria por estación (datos.cdmx.gob.mx, CC-BY-4.0)",
        },
        "caveats": CAVEATS,
    }


@router.get("/stats/categories/list")
async def categories_list(request: Request, top_delitos: int = Query(60, ge=0, le=300)):
    pool = request.app.state.db
    cats = await pool.fetch("SELECT categoria_delito, COUNT(*)::INT AS n FROM crime_cases GROUP BY 1 ORDER BY 2 DESC")
    delitos = await pool.fetch("SELECT delito, categoria_delito, COUNT(*)::INT AS n FROM crime_cases GROUP BY 1, 2 ORDER BY 3 DESC LIMIT $1", top_delitos)
    modes = await pool.fetch("SELECT transport_mode, COUNT(*)::INT AS n FROM crime_cases WHERE is_transport_related GROUP BY 1 ORDER BY 2 DESC")
    return {
        "categories": [{"categoria": r["categoria_delito"], "n": r["n"]} for r in cats],
        "delitos": [{"delito": r["delito"], "categoria": r["categoria_delito"], "n": r["n"]} for r in delitos],
        "modes": [{"mode": r["transport_mode"], "label": MODE_LABELS.get(r["transport_mode"], r["transport_mode"]), "n": r["n"]} for r in modes],
    }


@router.get("/stats/summary")
async def stats_summary(request: Request, f: CrimeFilter = Depends(crime_filter)):
    pool = request.app.state.db
    await f.resolve(pool)
    win = await _window(pool, f)
    params: list = []
    src, cnt, live = _daily_or_live(f, params)
    tcol = "c.is_transport_related" if live else "m.is_transport_related"
    ccol = "c.categoria_delito" if live else "m.categoria_delito"
    tot = await pool.fetchrow(f"SELECT COALESCE({cnt},0)::BIGINT AS n, COALESCE({cnt.replace(')', ') FILTER (WHERE ' + tcol + ')') if live else 'SUM(m.n_cases) FILTER (WHERE m.is_transport_related)'},0)::BIGINT AS nt {src}", *params)
    cats = await pool.fetch(f"SELECT {ccol} AS categoria, {cnt}::BIGINT AS n {src} GROUP BY 1 ORDER BY 2 DESC LIMIT 8", *params)
    n = int(tot["n"])
    return {
        "window": win, "filters": f.active(),
        "n_cases": n, "n_transport": int(tot["nt"]),
        "transport_share": round(int(tot["nt"]) / n, 4) if n else None,
        "per_month": round(n / win["months"], 1) if win["months"] else None,
        "top_categories": [{"categoria": r["categoria"], "n": int(r["n"]), "share": round(int(r["n"]) / n, 4) if n else None} for r in cats],
    }


@router.get("/stats/trend")
async def stats_trend(
    request: Request,
    granularity: str = Query("month", pattern="^(day|week|month|quarter|year)$"),
    f: CrimeFilter = Depends(crime_filter),
):
    pool = request.app.state.db
    await f.resolve(pool)
    win = await _window(pool, f)
    params: list = []
    src, cnt, live = _daily_or_live(f, params)
    dcol = "c.fecha_hecho" if live else "m.day"
    rows = await pool.fetch(f"SELECT date_trunc('{granularity}', {dcol})::date AS period, {cnt}::INT AS n {src} GROUP BY 1 ORDER BY 1", *params)
    series = [{"period": r["period"].isoformat(), "n": int(r["n"])} for r in rows]
    first, last = (series[0]["n"], series[-1]["n"]) if len(series) >= 2 else (None, None)
    return {"granularity": granularity, "window": win, "filters": f.active(), "series": series,
            "first": first, "last": last,
            "change_pct": round((last - first) / first * 100, 1) if first else None}


@router.get("/stats/categories")
async def stats_categories(
    request: Request,
    by: str = Query("categoria", pattern="^(categoria|delito|mode)$"),
    limit: int = Query(20, ge=1, le=300),
    f: CrimeFilter = Depends(crime_filter),
):
    pool = request.app.state.db
    await f.resolve(pool)
    win = await _window(pool, f)
    params: list = []
    if by == "delito":
        w = f.where("c", params, CASES_COLS)
        rows = await pool.fetch(f"SELECT c.delito AS k, c.categoria_delito AS cat, COUNT(*)::INT AS n FROM crime_cases c {('WHERE ' + w) if w else ''} GROUP BY 1, 2 ORDER BY 3 DESC LIMIT {int(limit)}", *params)
        total = await pool.fetchval(f"SELECT COUNT(*) FROM crime_cases c {('WHERE ' + w) if w else ''}", *params)
    else:
        src, cnt, live = _daily_or_live(f, params)
        a = "c" if live else "m"
        col = f"{a}.categoria_delito" if by == "categoria" else f"NULLIF({a}.transport_mode, '')"
        extra = "" if by == "categoria" else f" AND {a}.is_transport_related" if "WHERE" in src else f" WHERE {a}.is_transport_related"
        rows = await pool.fetch(f"SELECT {col} AS k, NULL::TEXT AS cat, {cnt}::INT AS n {src}{extra} GROUP BY 1 ORDER BY 3 DESC LIMIT {int(limit)}", *params)
        total = await pool.fetchval(f"SELECT COALESCE({cnt},0) {src}", *params)
    total = int(total or 0)
    return {"by": by, "window": win, "filters": f.active(), "total": total,
            "items": [{"key": r["k"], "label": MODE_LABELS.get(r["k"], r["k"]) if by == "mode" else r["k"],
                       "categoria": r["cat"], "n": int(r["n"]), "share": round(int(r["n"]) / total, 4) if total else None}
                      for r in rows if r["k"] is not None]}


@router.get("/stats/profile")
async def stats_profile(
    request: Request,
    dim: str = Query("hour", pattern="^(hour|dow|hour_dow|month)$"),
    f: CrimeFilter = Depends(crime_filter),
):
    """Hour-of-day / weekday profiles run live on crime_cases (hour needs hora_ok)."""
    pool = request.app.state.db
    await f.resolve(pool)
    win = await _window(pool, f)
    params: list = []
    w = f.where("c", params, CASES_COLS)
    where = f"WHERE {w}" if w else ""
    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM crime_cases c {where}", *params) or 0)
    out = {"dim": dim, "window": win, "filters": f.active(), "n_cases": total}
    if dim in ("hour", "hour_dow"):
        hw = f"{where} AND c.hora_ok" if where else "WHERE c.hora_ok"
        if dim == "hour":
            rows = await pool.fetch(f"SELECT c.hour, COUNT(*)::INT AS n FROM crime_cases c {hw} GROUP BY 1", *params)
            prof = [0] * 24
            for r in rows: prof[int(r["hour"])] = int(r["n"])
            out["hour"] = prof
        else:
            rows = await pool.fetch(f"SELECT c.dow, c.hour, COUNT(*)::INT AS n FROM crime_cases c {hw} GROUP BY 1, 2", *params)
            grid = [[0] * 24 for _ in range(7)]
            for r in rows: grid[int(r["dow"]) - 1][int(r["hour"])] = int(r["n"])
            out["hour_dow"] = grid
        n_ok = sum(int(r["n"]) for r in rows)
        out["hora_ok_share"] = round(n_ok / total, 3) if total else None
        out["peak_hour"] = max(range(24), key=lambda h: (out.get("hour") or [sum(g[h] for g in out["hour_dow"]) for h in range(24)])[h]) if n_ok else None
    elif dim == "dow":
        rows = await pool.fetch(f"SELECT c.dow, COUNT(*)::INT AS n FROM crime_cases c {where} GROUP BY 1", *params)
        prof = [0] * 7
        for r in rows: prof[int(r["dow"]) - 1] = int(r["n"])
        out["dow"] = prof
        out["dow_labels"] = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    else:
        rows = await pool.fetch(f"SELECT c.month, COUNT(*)::INT AS n FROM crime_cases c {where} GROUP BY 1", *params)
        prof = [0] * 12
        for r in rows: prof[int(r["month"]) - 1] = int(r["n"])
        out["month"] = prof
    return out


@router.get("/stats/area")
async def stats_area(
    request: Request,
    alcaldia: str | None = Query(None), colonia_id: int | None = Query(None), colonia: str | None = Query(None),
    f: CrimeFilter = Depends(crime_filter),
):
    """Summary for one alcaldía or colonia: totals, monthly trend, top categories,
    rank among peers, Metro stations inside."""
    pool = request.app.state.db
    if alcaldia: f.alcaldia = alcaldia
    if colonia and colonia_id is None:
        from services.name_match import normalize
        row = await pool.fetchrow(
            "SELECT id, colonia, alc FROM colonias WHERE colonia_norm = $1 OR similarity(colonia_norm, $1) > 0.5 "
            "ORDER BY (colonia_norm = $1) DESC, similarity(colonia_norm, $1) DESC LIMIT 1", normalize(colonia))
        if not row:
            raise HTTPException(404, {"error": "colonia_not_found", "colonia": colonia})
        colonia_id = row["id"]
    if colonia_id is not None:
        f.colonia_id = colonia_id
    await f.resolve(pool)
    if f.alcaldia_id is None and f.colonia_id is None:
        raise HTTPException(400, "pass alcaldia or colonia / colonia_id")
    win = await _window(pool, f)

    params: list = []
    w = f.where("c", params, CASES_COLS)
    where = f"WHERE {w}" if w else ""
    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM crime_cases c {where}", *params) or 0)
    nt = int(await pool.fetchval(f"SELECT COUNT(*) FROM crime_cases c {where} {'AND' if where else 'WHERE'} c.is_transport_related", *params) or 0)
    monthly = await pool.fetch(f"SELECT c.ym, COUNT(*)::INT AS n FROM crime_cases c {where} GROUP BY 1 ORDER BY 1", *params)
    cats = await pool.fetch(f"SELECT c.categoria_delito, COUNT(*)::INT AS n FROM crime_cases c {where} GROUP BY 1 ORDER BY 2 DESC LIMIT 8", *params)
    delitos = await pool.fetch(f"SELECT c.delito, COUNT(*)::INT AS n FROM crime_cases c {where} GROUP BY 1 ORDER BY 2 DESC LIMIT 8", *params)

    # Peer ranking (same filter minus the area) by count and per km².
    peer = CrimeFilter(**{**f.__dict__, "alcaldia": None, "alcaldia_id": None, "colonia_id": None})
    if f.colonia_id is not None:
        area = await pool.fetchrow("SELECT id, colonia AS name, alc AS parent, area_km2, ST_AsGeoJSON(ST_Centroid(geom)) AS c FROM colonias WHERE id = $1", f.colonia_id)
        pp: list = []
        pw = peer.where("c", pp, CASES_COLS)
        peers = await pool.fetch(f"""
            WITH agg AS (SELECT c.colonia_id, COUNT(*)::INT AS n FROM crime_cases c WHERE c.colonia_id IS NOT NULL {('AND ' + pw) if pw else ''} GROUP BY 1)
            SELECT k.id, COALESCE(agg.n,0) AS n, CASE WHEN k.area_km2>0 THEN COALESCE(agg.n,0)/k.area_km2 END AS d
            FROM colonias k LEFT JOIN agg ON agg.colonia_id = k.id""", *pp)
        kind = "colonia"
    else:
        area = await pool.fetchrow("SELECT id, nomgeo AS name, NULL::TEXT AS parent, area_km2, ST_AsGeoJSON(ST_Centroid(geom)) AS c FROM alcaldias WHERE id = $1", f.alcaldia_id)
        pp = []
        pw = peer.where("c", pp, CASES_COLS)
        peers = await pool.fetch(f"""
            WITH agg AS (SELECT c.alcaldia_id, COUNT(*)::INT AS n FROM crime_cases c WHERE c.alcaldia_id IS NOT NULL {('AND ' + pw) if pw else ''} GROUP BY 1)
            SELECT a.id, COALESCE(agg.n,0) AS n, CASE WHEN a.area_km2>0 THEN COALESCE(agg.n,0)/a.area_km2 END AS d
            FROM alcaldias a LEFT JOIN agg ON agg.alcaldia_id = a.id""", *pp)
        kind = "alcaldia"
    by_n = sorted(peers, key=lambda r: r["n"], reverse=True)
    by_d = sorted((r for r in peers if r["d"] is not None), key=lambda r: r["d"], reverse=True)
    rank_n = next((i + 1 for i, r in enumerate(by_n) if r["id"] == area["id"]), None)
    rank_d = next((i + 1 for i, r in enumerate(by_d) if r["id"] == area["id"]), None)

    stations = await pool.fetch(f"""
        SELECT ms.station_key, ms.station_name, ms.lines
        FROM metro_stations ms JOIN {'colonias' if kind == 'colonia' else 'alcaldias'} g ON g.id = $1
        WHERE ST_DWithin(g.geom::geography, ms.geom::geography, 300)
        ORDER BY ms.station_name""", area["id"])
    import json as _json
    return {
        "area": {"kind": kind, "id": area["id"], "name": area["name"], "parent": area["parent"],
                 "area_km2": round(area["area_km2"], 3) if area["area_km2"] else None,
                 "centroid": _json.loads(area["c"])},
        "window": win, "filters": f.active(),
        "n_cases": total, "n_transport": nt, "per_month": round(total / win["months"], 1) if win["months"] else None,
        "per_km2": round(total / area["area_km2"], 1) if area["area_km2"] else None,
        "rank_by_count": rank_n, "rank_by_density": rank_d, "n_peers": len(peers),
        "monthly": [{"ym": r["ym"], "n": int(r["n"])} for r in monthly],
        "top_categories": [{"categoria": r["categoria_delito"], "n": int(r["n"])} for r in cats],
        "top_delitos": [{"delito": r["delito"], "n": int(r["n"])} for r in delitos],
        "metro_stations": [{"station_key": r["station_key"], "station_name": r["station_name"], "lines": list(r["lines"] or [])} for r in stations],
    }


@router.get("/stats/compare")
async def stats_compare(
    request: Request,
    a_from: date = Query(...), a_to: date = Query(...), b_from: date = Query(...), b_to: date = Query(...),
    limit: int = Query(15, ge=1, le=100),
    f: CrimeFilter = Depends(crime_filter),
):
    """Two periods side by side, per category, with per-month averages so
    unequal windows compare fairly. The filter's own from/to are ignored."""
    pool = request.app.state.db
    await f.resolve(pool)

    async def period(d0: date, d1: date):
        g = CrimeFilter(**{**f.__dict__, "date_from": d0, "date_to": d1})
        params: list = []
        src, cnt, live = _daily_or_live(g, params)
        a = "c" if live else "m"
        rows = await pool.fetch(f"SELECT {a}.categoria_delito AS k, {cnt}::INT AS n {src} GROUP BY 1", *params)
        months = (d1.year - d0.year) * 12 + d1.month - d0.month + 1
        return {r["k"]: int(r["n"]) for r in rows}, months

    A, ma = await period(a_from, a_to)
    B, mb = await period(b_from, b_to)
    keys = sorted(set(A) | set(B), key=lambda k: -(A.get(k, 0) + B.get(k, 0)))
    items = []
    for k in keys[:limit]:
        na, nb = A.get(k, 0), B.get(k, 0)
        pma, pmb = na / ma, nb / mb
        items.append({"categoria": k, "n_a": na, "n_b": nb, "per_month_a": round(pma, 1), "per_month_b": round(pmb, 1),
                      "delta_per_month": round(pmb - pma, 1),
                      "change_pct": round((pmb - pma) / pma * 100, 1) if pma else None})
    ta, tb = sum(A.values()), sum(B.values())
    return {"a": {"from": a_from.isoformat(), "to": a_to.isoformat(), "months": ma, "n": ta, "per_month": round(ta / ma, 1)},
            "b": {"from": b_from.isoformat(), "to": b_to.isoformat(), "months": mb, "n": tb, "per_month": round(tb / mb, 1)},
            "total_change_pct": round((tb / mb - ta / ma) / (ta / ma) * 100, 1) if ta else None,
            "filters": f.active(), "items": items}


@router.get("/stats/hotspots")
async def stats_hotspots(
    request: Request,
    res: int = Query(500), top: int = Query(15, ge=1, le=100),
    f: CrimeFilter = Depends(crime_filter),
):
    """Top hex cells by count, with the colonia / alcaldía they fall in and the nearest Metro station."""
    if res not in (250, 500, 1000):
        raise HTTPException(400, "res must be 250, 500 or 1000")
    pool = request.app.state.db
    await f.resolve(pool)
    win = await _window(pool, f)
    rows = await hex_counts(pool, f, res)
    rows = sorted(rows, key=lambda r: int(r["n"]), reverse=True)[:top]
    total = sum(int(r["n"]) for r in rows)
    out = []
    for r in rows:
        ctx = await pool.fetchrow("""
            SELECT (SELECT colonia FROM colonias k WHERE ST_Contains(k.geom, p.g) LIMIT 1) AS colonia,
                   (SELECT nomgeo FROM alcaldias a WHERE ST_Contains(a.geom, p.g) LIMIT 1) AS alcaldia,
                   ns.station_name, ns.d
            FROM (SELECT ST_SetSRID(ST_MakePoint($1, $2), 4326) AS g) p
            LEFT JOIN LATERAL (SELECT station_name, ST_Distance(pts::geography, p.g::geography) AS d
                               FROM metro_stations ORDER BY geom <-> p.g LIMIT 1) ns ON TRUE""", r["lon"], r["lat"])
        out.append({"i": r["i"], "j": r["j"], "n": int(r["n"]), "lon": round(r["lon"], 5), "lat": round(r["lat"], 5),
                    "colonia": ctx["colonia"], "alcaldia": ctx["alcaldia"],
                    "nearest_station": ctx["station_name"], "nearest_station_m": round(ctx["d"]) if ctx["d"] is not None else None})
    return {"res_m": res, "window": win, "filters": f.active(), "top": top, "cells": out}


@router.get("/stats/victims")
async def stats_victims(
    request: Request,
    group_by: str = Query("sexo", pattern="^(sexo|edad_band|calidad_juridica|tipo_persona|categoria)$"),
    limit: int = Query(20, ge=1, le=100),
    f: CrimeFilter = Depends(crime_filter),
):
    """Victim-level breakdown (separate FGJ file; ends ~May 2024)."""
    pool = request.app.state.db
    await f.resolve(pool)
    params: list = []
    w = f.where("v", params, CASES_COLS)
    where = f"WHERE {w}" if w else ""
    col = {"sexo": "v.sexo", "edad_band": "CASE WHEN v.edad IS NULL THEN NULL ELSE (LEAST(v.edad, 89) / 10 * 10)::TEXT || '-' || (LEAST(v.edad, 89) / 10 * 10 + 9)::TEXT END",
           "calidad_juridica": "v.calidad_juridica", "tipo_persona": "v.tipo_persona", "categoria": "v.categoria_delito"}[group_by]
    rows = await pool.fetch(f"SELECT {col} AS k, COUNT(*)::INT AS n FROM crime_victims v {where} GROUP BY 1 ORDER BY 2 DESC LIMIT {int(limit)}", *params)
    total = int(await pool.fetchval(f"SELECT COUNT(*) FROM crime_victims v {where}", *params) or 0)
    cov = await pool.fetchrow("SELECT MIN(fecha_hecho)::date AS d0, MAX(fecha_hecho)::date AS d1 FROM crime_victims")
    return {"group_by": group_by, "filters": f.active(), "total": total,
            "coverage": {"from": cov["d0"].isoformat() if cov["d0"] else None, "to": cov["d1"].isoformat() if cov["d1"] else None},
            "items": [{"key": r["k"] if r["k"] is not None else "(sin dato)", "n": int(r["n"]),
                       "share": round(int(r["n"]) / total, 4) if total else None} for r in rows]}
