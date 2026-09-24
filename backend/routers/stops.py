"""Stop / agency endpoints."""
from __future__ import annotations
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter()


@router.get("/stops/search")
async def search_stops(
    request: Request,
    q: str = Query(..., min_length=1, max_length=80),
    limit: int = Query(15, ge=1, le=500),
    agency_id: Optional[str] = Query(None),
    line_code: Optional[str] = Query(None),
    match: str = Query("auto", pattern="^(auto|prefix|contains|exact)$"),
):
    """Query the stop catalog. Three modes:
      - auto (default): substring match + pg_trgm similarity, prefix-ranked.
        Best for typeahead and best-guess natural-language queries.
      - prefix: rows whose normalized name starts with q. Use for "stations
        starting with R", alphabetical browse, etc.
      - contains: rows whose normalized name contains q anywhere.
      - exact: rows whose normalized name equals q (after unaccent + lower).

    Filters: optional `agency_id` and `line_code`. `limit` caps the result
    size (up to 500) so the agent can fetch enough rows to count/filter
    client-side without a dedicated counting endpoint.
    """
    pool = request.app.state.db
    norm = q.strip().lower()
    if match == "prefix":
        where_q = "s.stop_name_norm LIKE $1 || '%'"
        order = "s.stop_name_norm"
    elif match == "contains":
        where_q = "s.stop_name_norm LIKE '%' || $1 || '%'"
        order = "s.stop_name_norm"
    elif match == "exact":
        where_q = "s.stop_name_norm = $1"
        order = "s.stop_name_norm"
    else:  # auto
        where_q = "(s.stop_name_norm LIKE '%' || $1 || '%' OR similarity(s.stop_name_norm, $1) > 0.3)"
        order = "(s.stop_name_norm LIKE $1 || '%') DESC, similarity(s.stop_name_norm, $1) DESC"
    rows = await pool.fetch(
        f"""
        SELECT s.stop_id, s.stop_name, s.agency_id, s.line_code,
               ST_X(s.geom) AS lon, ST_Y(s.geom) AS lat
        FROM stops s
        WHERE s.geom IS NOT NULL
          AND ($3::TEXT IS NULL OR s.agency_id = $3)
          AND ($4::TEXT IS NULL OR s.line_code = $4)
          AND {where_q}
        ORDER BY {order}
        LIMIT $2
        """,
        norm, limit, agency_id, line_code,
    )
    return [
        {
            "stop_id": r["stop_id"],
            "stop_name": r["stop_name"],
            "agency_id": r["agency_id"],
            "line_code": r["line_code"],
            "lon": r["lon"],
            "lat": r["lat"],
        }
        for r in rows
    ]


@router.get("/agencies")
async def list_agencies(request: Request):
    pool = request.app.state.db
    rows = await pool.fetch(
        """
        SELECT a.agency_id,
               a.agency_name,
               COALESCE(rcount.n_routes, 0) AS n_routes,
               COALESCE(scount.n_stops,  0) AS n_stops
        FROM agencies a
        LEFT JOIN (
            SELECT agency_id, COUNT(*) AS n_routes
            FROM routes GROUP BY agency_id
        ) rcount USING (agency_id)
        LEFT JOIN (
            SELECT agency_id, COUNT(*) AS n_stops
            FROM stops WHERE agency_id IS NOT NULL GROUP BY agency_id
        ) scount USING (agency_id)
        ORDER BY n_stops DESC NULLS LAST, agency_id
        """
    )
    return [
        {
            "agency_id": r["agency_id"],
            "agency_name": r["agency_name"],
            "n_routes": int(r["n_routes"]),
            "n_stops":  int(r["n_stops"]),
        }
        for r in rows
    ]


@router.get("/stops")
async def list_stops(
    request: Request,
    agency_id: Optional[str] = Query(None),
    bbox: Optional[str] = Query(None, description="minx,miny,maxx,maxy in EPSG:4326"),
):
    pool = request.app.state.db
    where = []
    params: list = []
    if agency_id:
        params.append(agency_id)
        where.append(f"s.agency_id = ${len(params)}")
    if bbox:
        try:
            minx, miny, maxx, maxy = (float(x) for x in bbox.split(","))
        except ValueError:
            raise HTTPException(400, "bbox must be 'minx,miny,maxx,maxy'")
        params.extend([minx, miny, maxx, maxy])
        where.append(
            f"ST_MakeEnvelope(${len(params)-3},${len(params)-2},${len(params)-1},${len(params)},4326) && s.geom"
        )
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows = await pool.fetch(
        f"""
        SELECT s.stop_id, s.stop_name, s.agency_id, s.line_code,
               s.wheelchair_boarding,
               ST_AsGeoJSON(s.geom) AS geom_json
        FROM stops s
        {where_sql}
        """,
        *params,
    )
    features = [
        {
            "type": "Feature",
            "geometry": json.loads(r["geom_json"]) if r["geom_json"] else None,
            "properties": {
                "stop_id": r["stop_id"],
                "stop_name": r["stop_name"],
                "agency_id": r["agency_id"],
                "line_code": r["line_code"],
                "wheelchair_boarding": r["wheelchair_boarding"],
            },
        }
        for r in rows
    ]
    return {"type": "FeatureCollection", "features": features}
