"""Route + shape (line corridor) endpoints."""
from __future__ import annotations
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter()


def _normalize_line(line: str) -> list[str]:
    """Return a list of variants to try when matching against
    `routes.route_short_name`, which can be e.g. '5' for Metro L5 or 'A' for
    Metro Línea A. Users may type '5', 'L5', or 'línea 5'."""
    s = line.strip()
    variants = {s, s.upper(), s.lower()}
    # Strip a leading 'L' if it precedes alphanumerics ('L5' → '5', 'LA' → 'A').
    upper = s.upper()
    if len(upper) > 1 and upper.startswith("L") and upper[1:].isalnum():
        variants.add(upper[1:])
        variants.add(upper[1:].lower())
    return list(variants)


@router.get("/lines/stops")
async def line_stops(
    request: Request,
    agency_id: str = Query(..., description="Agency code, e.g. METRO, MB, TROLE."),
    line: str = Query(..., description="Line identifier as the user would say it (e.g. '5', 'L5', 'A')."),
):
    """Return the ordered stops on a line, picking the trip with the most stops
    on that route (typically the full-line run, not a short-turn). Useful for
    questions like 'how many stations on L5?' or 'list the stops on Línea 2'.
    """
    pool = request.app.state.db
    variants = _normalize_line(line)
    async with pool.acquire() as conn:
        route = await conn.fetchrow(
            """
            SELECT route_id, route_short_name, route_long_name, route_color, agency_id
            FROM routes
            WHERE agency_id = $1
              AND route_short_name = ANY($2::TEXT[])
            ORDER BY route_short_name
            LIMIT 1
            """,
            agency_id, variants,
        )
        if not route:
            raise HTTPException(404, {"error": "line_not_found",
                                      "agency_id": agency_id, "line": line})
        rows = await conn.fetch(
            """
            WITH chosen_trip AS (
                SELECT t.trip_id, COUNT(*) AS n
                FROM trips t
                JOIN stop_times st ON st.trip_id = t.trip_id
                WHERE t.route_id = $1
                GROUP BY t.trip_id
                ORDER BY n DESC, t.trip_id
                LIMIT 1
            )
            SELECT s.stop_id, s.stop_name, s.agency_id, s.line_code,
                   st.stop_sequence,
                   ST_X(s.geom) AS lon, ST_Y(s.geom) AS lat
            FROM chosen_trip ct
            JOIN stop_times st ON st.trip_id = ct.trip_id
            JOIN stops s ON s.stop_id = st.stop_id
            ORDER BY st.stop_sequence
            """,
            route["route_id"],
        )
    return {
        "route_id": route["route_id"],
        "agency_id": route["agency_id"],
        "route_short_name": route["route_short_name"],
        "route_long_name": route["route_long_name"],
        "route_color": route["route_color"],
        "n_stops": len(rows),
        "stops": [
            {
                "stop_id": r["stop_id"],
                "stop_name": r["stop_name"],
                "agency_id": r["agency_id"],
                "line_code": r["line_code"],
                "stop_sequence": int(r["stop_sequence"]),
                "lon": r["lon"],
                "lat": r["lat"],
            }
            for r in rows
        ],
    }


@router.get("/routes")
async def list_routes(request: Request, agency_id: Optional[str] = Query(None)):
    pool = request.app.state.db
    if agency_id:
        rows = await pool.fetch(
            "SELECT route_id, agency_id, route_short_name, route_long_name, "
            "route_type, route_color, route_text_color FROM routes WHERE agency_id = $1 "
            "ORDER BY route_short_name",
            agency_id,
        )
    else:
        rows = await pool.fetch(
            "SELECT route_id, agency_id, route_short_name, route_long_name, "
            "route_type, route_color, route_text_color FROM routes ORDER BY agency_id, route_short_name"
        )
    return [dict(r) for r in rows]


@router.get("/shapes")
async def shapes(request: Request, agency_id: Optional[str] = Query(None)):
    pool = request.app.state.db
    where, params = "", []
    if agency_id:
        params.append(agency_id)
        where = "WHERE sl.agency_id = $1"
    rows = await pool.fetch(
        f"""
        SELECT sl.shape_id, sl.route_id, sl.agency_id,
               r.route_short_name, r.route_long_name,
               r.route_color, r.route_text_color, r.route_type,
               ST_AsGeoJSON(sl.geom) AS geom_json
        FROM shape_lines sl
        LEFT JOIN routes r ON r.route_id = sl.route_id
        {where}
        """,
        *params,
    )
    features = [
        {
            "type": "Feature",
            "geometry": json.loads(r["geom_json"]) if r["geom_json"] else None,
            "properties": {
                "shape_id": r["shape_id"],
                "route_id": r["route_id"],
                "agency_id": r["agency_id"],
                "route_short_name": r["route_short_name"],
                "route_long_name": r["route_long_name"],
                "route_color": r["route_color"],
                "route_text_color": r["route_text_color"],
                "route_type": r["route_type"],
            },
        }
        for r in rows
    ]
    return {"type": "FeatureCollection", "features": features}
