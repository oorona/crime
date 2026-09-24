"""Metro station crime statistics (per physical station = name cluster)."""
from __future__ import annotations
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from services.coverage import coverage, ym, months_between
from services.filters import CASES_COLS, STATION_MV_COLS, CrimeFilter, crime_filter
from services.readiness import require_views

router = APIRouter(dependencies=[Depends(require_views)])

RADII = (300, 500)


def _radius(radius: int) -> int:
    if radius not in RADII:
        raise HTTPException(400, f"radius must be one of {RADII}")
    return radius


async def _window(pool, f: CrimeFilter) -> dict:
    """Effective (clamped) month window shared by crime counts and ridership, so
    a rate per million uses the same months on both sides."""
    cov = await coverage(pool)
    ym_from = max(ym(f.date_from) if f.date_from else 0, cov["ym_from"] or 0)
    ym_to = min(ym(f.date_to) if f.date_to else 999912, cov["ym_to"] or 999912)
    return {"ym_from": ym_from, "ym_to": ym_to, "months": max(0, months_between(ym_from, ym_to)),
            "from": (f.date_from or cov["date_from"]).isoformat() if (f.date_from or cov["date_from"]) else None,
            "to": (f.date_to or cov["date_to"]).isoformat() if (f.date_to or cov["date_to"]) else None}


async def station_table(pool, f: CrimeFilter, radius: int) -> tuple[list[dict], dict]:
    """All 163 stations with counts, entries and rate for the filter window."""
    win = await _window(pool, f)
    params: list = [radius]
    if f.unsupported(STATION_MV_COLS):
        w = f.where("c", params, CASES_COLS)
        crime_cte = f"""
            c AS (
                SELECT ms.station_key,
                       COUNT(c.id)::INT AS n,
                       COUNT(c.id) FILTER (WHERE c.is_transport_related)::INT AS nt
                FROM metro_stations ms
                LEFT JOIN crime_cases c
                  ON c.geom IS NOT NULL
                 AND ST_DWithin(ms.pts::geography, c.geom::geography, $1)
                 {('AND ' + w) if w else ''}
                GROUP BY 1
            )"""
    else:
        w = f.where("m", params, STATION_MV_COLS)
        crime_cte = f"""
            c AS (
                SELECT m.station_key,
                       SUM(m.n_cases)::INT AS n,
                       SUM(m.n_cases) FILTER (WHERE m.is_transport_related)::INT AS nt
                FROM mv_station_crime m
                WHERE m.radius_m = $1 {('AND ' + w) if w else ''}
                GROUP BY 1
            )"""
    params.extend([win["ym_from"], win["ym_to"]])
    p_from, p_to = f"${len(params)-1}", f"${len(params)}"
    rows = await pool.fetch(f"""
        WITH {crime_cte},
        r AS (
            SELECT station_key, SUM(entries)::BIGINT AS entries, SUM(days)::INT AS days
            FROM mv_station_ridership_monthly
            WHERE ym BETWEEN {p_from} AND {p_to}
            GROUP BY 1
        )
        SELECT ms.station_key, ms.station_name, ms.lines, ms.stop_ids,
               ST_X(ms.geom) AS lon, ST_Y(ms.geom) AS lat,
               COALESCE(c.n, 0) AS n_cases, COALESCE(c.nt, 0) AS n_transport,
               r.entries, r.days
        FROM metro_stations ms
        LEFT JOIN c USING (station_key)
        LEFT JOIN r USING (station_key)
        ORDER BY ms.station_name
    """, *params)
    out = []
    for r in rows:
        entries = int(r["entries"]) if r["entries"] else 0
        n, nt = int(r["n_cases"]), int(r["n_transport"])
        rate = round(n / (entries / 1e6), 2) if entries > 0 else None
        trate = round(nt / (entries / 1e6), 2) if entries > 0 else None
        out.append({
            "station_key": r["station_key"], "station_name": r["station_name"],
            "lines": list(r["lines"] or []), "lon": r["lon"], "lat": r["lat"],
            "n_cases": n, "n_transport": nt,
            "entries": entries or None, "days_with_data": int(r["days"]) if r["days"] else 0,
            "avg_daily_entries": round(entries / r["days"]) if r["days"] else None,
            "rate_per_million": rate, "transport_rate_per_million": trate,
        })
    return out, win


def _rank(rows: list[dict], metric: str) -> list[dict]:
    key = {"count": "n_cases", "rate": "rate_per_million",
           "transport_count": "n_transport", "transport_rate": "transport_rate_per_million"}[metric]
    ranked = sorted((r for r in rows if r[key] is not None), key=lambda r: r[key], reverse=True)
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


@router.get("/stations")
async def stations_geojson(
    request: Request,
    radius: int = Query(300), normalize: str = Query("count", pattern="^(count|rate)$"),
    f: CrimeFilter = Depends(crime_filter),
):
    """All Metro stations as GeoJSON points with crime counts within `radius` m
    and the rate per million entries for the same months."""
    pool = request.app.state.db
    await f.resolve(pool)
    rows, win = await station_table(pool, f, _radius(radius))
    metric = "rate" if normalize == "rate" else "count"
    _rank(rows, metric)
    return {
        "type": "FeatureCollection",
        "window": win, "filters": f.active(), "radius_m": radius, "metric": metric,
        "features": [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
             "properties": {k: v for k, v in r.items() if k not in ("lon", "lat")}}
            for r in rows
        ],
    }


@router.get("/stations/rank")
async def stations_rank(
    request: Request,
    metric: str = Query("rate", pattern="^(count|rate|transport_count|transport_rate)$"),
    limit: int = Query(15, ge=1, le=163),
    radius: int = Query(300),
    f: CrimeFilter = Depends(crime_filter),
):
    """Stations ranked by the chosen metric. `rate` metrics are per million
    Metro entries over the same months (stations without ridership data are
    omitted from rate rankings)."""
    pool = request.app.state.db
    await f.resolve(pool)
    rows, win = await station_table(pool, f, _radius(radius))
    ranked = _rank(rows, metric)
    total = sum(r["n_cases"] for r in rows)
    return {
        "metric": metric, "radius_m": radius, "window": win, "filters": f.active(),
        "n_stations": len(rows), "n_stations_ranked": len(ranked), "total_cases_all_stations": total,
        "stations": ranked[:limit],
    }


@router.get("/stations/{station_key}/report")
async def station_report(
    station_key: str, request: Request,
    radius: int = Query(300), include_profiles: bool = Query(True),
    f: CrimeFilter = Depends(crime_filter),
):
    pool = request.app.state.db
    await f.resolve(pool)
    radius = _radius(radius)
    head = await pool.fetchrow(
        "SELECT station_key, station_name, lines, stop_ids, ST_AsGeoJSON(geom) AS g FROM metro_stations WHERE station_key = $1",
        station_key)
    if not head:
        # tolerate un-normalized keys ("Pantitlán")
        from services.name_match import normalize
        head = await pool.fetchrow(
            "SELECT station_key, station_name, lines, stop_ids, ST_AsGeoJSON(geom) AS g FROM metro_stations WHERE station_key = $1",
            normalize(station_key))
        if not head:
            raise HTTPException(404, {"error": "station_not_found", "station_key": station_key})
        station_key = head["station_key"]

    rows, win = await station_table(pool, f, radius)
    me = next(r for r in rows if r["station_key"] == station_key)
    _rank(rows, "count"); me_count_rank = me.get("rank")
    _rank(rows, "rate");  me_rate_rank = me.get("rank")

    # Monthly series + category breakdown (MV when possible, else live).
    params: list = [station_key, radius]
    if f.unsupported(STATION_MV_COLS):
        w = f.where("c", params, CASES_COLS)
        base = f"""
            FROM metro_stations ms
            JOIN crime_cases c ON c.geom IS NOT NULL
             AND ST_DWithin(ms.pts::geography, c.geom::geography, $2)
            WHERE ms.station_key = $1 {('AND ' + w) if w else ''}"""
        monthly = await pool.fetch(f"SELECT c.ym, COUNT(*)::INT AS n {base} GROUP BY 1 ORDER BY 1", *params)
        bycat = await pool.fetch(f"SELECT c.categoria_delito AS categoria, COUNT(*)::INT AS n {base} GROUP BY 1 ORDER BY 2 DESC", *params)
        bymode = await pool.fetch(f"SELECT c.transport_mode AS mode, COUNT(*)::INT AS n {base} AND c.is_transport_related GROUP BY 1 ORDER BY 2 DESC", *params)
    else:
        w = f.where("m", params, STATION_MV_COLS)
        base = f"FROM mv_station_crime m WHERE m.station_key = $1 AND m.radius_m = $2 {('AND ' + w) if w else ''}"
        monthly = await pool.fetch(f"SELECT m.ym, SUM(m.n_cases)::INT AS n {base} GROUP BY 1 ORDER BY 1", *params)
        bycat = await pool.fetch(f"SELECT m.categoria_delito AS categoria, SUM(m.n_cases)::INT AS n {base} GROUP BY 1 ORDER BY 2 DESC", *params)
        bymode = await pool.fetch(f"SELECT NULLIF(m.transport_mode,'') AS mode, SUM(m.n_cases)::INT AS n {base} AND m.is_transport_related GROUP BY 1 ORDER BY 2 DESC", *params)

    entries = await pool.fetch(
        "SELECT ym, entries, days FROM mv_station_ridership_monthly WHERE station_key = $1 AND ym BETWEEN $2 AND $3 ORDER BY ym",
        station_key, win["ym_from"], win["ym_to"])
    entries_by_ym = {r["ym"]: (int(r["entries"]), int(r["days"])) for r in entries}
    months = sorted(set(entries_by_ym) | {r["ym"] for r in monthly})
    n_by_ym = {r["ym"]: int(r["n"]) for r in monthly}

    # Live: top delitos + hour/dow profiles for this station.
    lp: list = [station_key, radius]
    lw = f.where("c", lp, CASES_COLS)
    live_base = f"""
        FROM metro_stations ms
        JOIN crime_cases c ON c.geom IS NOT NULL
         AND ST_DWithin(ms.pts::geography, c.geom::geography, $2)
        WHERE ms.station_key = $1 {('AND ' + lw) if lw else ''}"""
    top_delitos = await pool.fetch(f"SELECT c.delito, COUNT(*)::INT AS n {live_base} GROUP BY 1 ORDER BY 2 DESC LIMIT 10", *lp)
    profiles = None
    if include_profiles:
        hours = await pool.fetch(f"SELECT c.hour, COUNT(*)::INT AS n {live_base} AND c.hora_ok GROUP BY 1", *lp)
        dows = await pool.fetch(f"SELECT c.dow, COUNT(*)::INT AS n {live_base} GROUP BY 1", *lp)
        hd = await pool.fetch(f"SELECT c.dow, c.hour, COUNT(*)::INT AS n {live_base} AND c.hora_ok GROUP BY 1, 2", *lp)
        hora_ok_n = sum(int(r["n"]) for r in hours)
        grid = [[0] * 24 for _ in range(7)]
        for r in hd:
            grid[int(r["dow"]) - 1][int(r["hour"])] = int(r["n"])
        profiles = {
            "hour": [0] * 24, "dow": [0] * 7, "hour_dow": grid,
            "hora_ok_share": round(hora_ok_n / me["n_cases"], 3) if me["n_cases"] else None,
        }
        for r in hours: profiles["hour"][int(r["hour"])] = int(r["n"])
        for r in dows:  profiles["dow"][int(r["dow"]) - 1] = int(r["n"])

    return {
        "station": {"station_key": head["station_key"], "station_name": head["station_name"],
                    "lines": list(head["lines"] or []), "stop_ids": list(head["stop_ids"] or []),
                    "geometry": json.loads(head["g"])},
        "radius_m": radius, "window": win, "filters": f.active(),
        "totals": {"n_cases": me["n_cases"], "n_transport": me["n_transport"], "entries": me["entries"],
                   "avg_daily_entries": me["avg_daily_entries"],
                   "rate_per_million": me["rate_per_million"],
                   "transport_rate_per_million": me["transport_rate_per_million"],
                   "rank_by_count": me_count_rank, "rank_by_rate": me_rate_rank, "n_stations": len(rows),
                   "transport_share": round(me["n_transport"] / me["n_cases"], 3) if me["n_cases"] else None},
        "monthly": [{"ym": m, "n": n_by_ym.get(m, 0), "entries": entries_by_ym.get(m, (None, None))[0],
                     "days": entries_by_ym.get(m, (None, None))[1]} for m in months],
        "by_category": [{"categoria": r["categoria"], "n": int(r["n"])} for r in bycat],
        "by_mode": [{"mode": r["mode"], "n": int(r["n"])} for r in bymode if r["mode"]],
        "top_delitos": [{"delito": r["delito"], "n": int(r["n"])} for r in top_delitos],
        "profiles": profiles,
    }
