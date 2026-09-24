"""Crime CDMX MCP server.

Wraps the /api/stats/* and /api/stations/* endpoints of the crime FastAPI
backend as MCP tools so the Gemini chat agent can answer questions about
crime patterns around Mexico City's public transport with real numbers.

Transport: streamable-http on CRIME_MCP_SERVER_PORT (default 6701).
Auth: clients must send X-API-Key header matching MCP_API_KEY.
Backend: CRIME_BACKEND_URL (default http://backend:8000).
"""
from __future__ import annotations

import logging
import os
from typing import Annotated, Any, Optional

import httpx
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
from pydantic import Field

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("crime-mcp-server")

MCP_API_KEY = os.getenv("MCP_API_KEY")
if not MCP_API_KEY:
    logger.error("MCP_API_KEY is required and not set.")
    raise ValueError("MCP_API_KEY is required")

BACKEND_URL = os.getenv("CRIME_BACKEND_URL", "http://backend:8000").rstrip("/")
SERVER_PORT = int(os.getenv("CRIME_MCP_SERVER_PORT", "6701"))
HTTP_TIMEOUT = float(os.getenv("CRIME_HTTP_TIMEOUT", "60"))

mcp = FastMCP(
    name="Crimen CDMX",
    instructions=(
        "Tools for analysing reported crime (FGJ CDMX carpetas de investigación, 2019 onward) "
        "around Mexico City's public transport. Call data_coverage first to learn the date window "
        "and caveats. Station tools work on physical Metro stations (station_key); resolve names "
        "with search_station. Every tool accepts the same optional filters (date_from, date_to, "
        "categories, transport_only, modes, alcaldia) so you can scope any question."
    ),
)

# ── shared filter plumbing ──────────────────────────────────────────────────
FilterDateFrom = Annotated[Optional[str], Field(description="Inclusive start date YYYY-MM-DD (fecha del hecho).")]
FilterDateTo = Annotated[Optional[str], Field(description="Inclusive end date YYYY-MM-DD.")]
FilterCategories = Annotated[Optional[list[str]], Field(description="Exact `categoria_delito` strings (see list_categories). Omit for all categories except HECHO NO DELICTIVO.")]
FilterTransportOnly = Annotated[bool, Field(description="Only crimes against public-transport passengers (robo a pasajero a bordo de Metro/Metrobús/microbús/taxi…).")]
FilterModes = Annotated[Optional[list[str]], Field(description="Transport modes to keep when transport_only: METRO, MB, TROLE, TL, SUB, RTP, MICRO, TAXI, TP.")]
FilterAlcaldia = Annotated[Optional[str], Field(description="Restrict to one alcaldía by name (accent-insensitive), e.g. 'Iztapalapa'.")]
FilterHours = Annotated[Optional[str], Field(description="Hour-of-day range 'H0-H1' inclusive, wraps midnight (e.g. '22-5'). Uses only rows with a valid time.")]
FilterDows = Annotated[Optional[list[int]], Field(description="ISO weekdays to keep, 1=Monday … 7=Sunday.")]


def _params(date_from=None, date_to=None, categories=None, transport_only=False, modes=None,
            alcaldia=None, hours=None, dows=None, **extra) -> dict[str, Any]:
    p: dict[str, Any] = {}
    if date_from: p["from"] = date_from
    if date_to: p["to"] = date_to
    if categories: p["categories"] = ",".join(categories)
    if transport_only: p["transport_only"] = "true"
    if modes: p["modes"] = ",".join(modes)
    if alcaldia: p["alcaldia"] = alcaldia
    if hours: p["hours"] = hours
    if dows: p["dows"] = ",".join(str(d) for d in dows)
    for k, v in extra.items():
        if v is not None:
            p[k] = v
    return p


def _check_auth() -> Optional[dict[str, Any]]:
    headers = get_http_headers()
    provided = headers.get("x-api-key") or headers.get("X-API-Key")
    if provided != MCP_API_KEY:
        return {"error": "unauthorized: missing or invalid X-API-Key"}
    return None


async def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    if (err := _check_auth()):
        return err
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(f"{BACKEND_URL}{path}", params=params)
            if r.status_code == 503:
                return {"error": "data is still being ingested; try again in a few minutes", "detail": r.text[:300]}
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        logger.error("backend error %s %s: %s", path, e.response.status_code, e.response.text[:300])
        return {"error": f"backend {e.response.status_code}: {e.response.text[:300]}"}
    except Exception as e:  # noqa: BLE001
        logger.exception("%s failed", path)
        return {"error": f"unexpected: {e}"}


# ── tools ───────────────────────────────────────────────────────────────────
@mcp.tool()
async def data_coverage() -> dict[str, Any]:
    """Date windows, row counts, sources and caveats of the data. CALL THIS FIRST
    in a conversation and state the coverage (e.g. 'carpetas 2019-01 a 2024-11')
    and that these are reported cases, not true incidence, before giving numbers."""
    return await _get("/api/stats/coverage")


@mcp.tool()
async def list_categories(
    top_delitos: Annotated[int, Field(description="How many of the most frequent detailed `delito` names to include.", ge=0, le=300)] = 60,
) -> dict[str, Any]:
    """The exact `categoria_delito` strings (16 values, with counts), the most
    frequent detailed `delito` names, and the transport-mode codes. Use these
    exact strings for the `categories` filter; never invent category names."""
    return await _get("/api/stats/categories/list", {"top_delitos": top_delitos})


@mcp.tool()
async def search_station(
    query: Annotated[str, Field(description="Metro station name, accents/case ignored, e.g. 'Pantitlan', 'Hidalgo', 'Bellas Artes'.")],
    limit: Annotated[int, Field(ge=1, le=30)] = 6,
) -> dict[str, Any]:
    """Resolve a station name to `station_key` values (physical Metro stations;
    transfer stations are ONE station with several lines). Returns matches with
    station_key, station_name and lines."""
    rows = await _get("/api/stops/search", {"q": query, "agency_id": "METRO", "limit": 60, "match": "auto"})
    if isinstance(rows, dict) and rows.get("error"):
        return rows
    seen: dict[str, dict] = {}
    for r in rows:
        key = _norm(r["stop_name"])
        st = seen.setdefault(key, {"station_key": key, "station_name": r["stop_name"], "lines": []})
        if r.get("line_code") and r["line_code"] not in st["lines"]:
            st["lines"].append(r["line_code"])
    matches = list(seen.values())[:limit]
    return {"matches": matches, "count": len(matches)}


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.lower().strip().split())


@mcp.tool()
async def station_crime_stats(
    station_key: Annotated[str, Field(description="station_key from search_station (e.g. 'pantitlan').")],
    radius_m: Annotated[int, Field(description="Radius around the station's platforms: 300 (default) or 500.")] = 300,
    include_profiles: Annotated[bool, Field(description="Also return hour-of-day and weekday profiles (24 + 7 counts).")] = False,
    date_from: FilterDateFrom = None, date_to: FilterDateTo = None,
    categories: FilterCategories = None, transport_only: FilterTransportOnly = False,
    modes: FilterModes = None, hours: FilterHours = None, dows: FilterDows = None,
) -> dict[str, Any]:
    """Crime report for one Metro station: totals within the radius, rate per
    million entries, rank among all stations (by count and by rate), monthly
    series, category and detailed-delito breakdown, transport-mode split, and
    optional hour/weekday profiles. Always quote the radius and the window."""
    p = _params(date_from, date_to, categories, transport_only, modes, None, hours, dows,
                radius=radius_m, include_profiles="true" if include_profiles else "false")
    r = await _get(f"/api/stations/{station_key}/report", p)
    if isinstance(r, dict) and not r.get("error") and not include_profiles:
        r.pop("profiles", None)
    if isinstance(r, dict) and not r.get("error"):
        r["monthly"] = r.get("monthly", [])[-24:]  # keep payload small: last 24 months
    return r


@mcp.tool()
async def rank_stations(
    metric: Annotated[str, Field(description="'rate' (cases per million Metro entries, default), 'count', 'transport_rate', 'transport_count'.")] = "rate",
    limit: Annotated[int, Field(ge=1, le=163)] = 15,
    radius_m: Annotated[int, Field(description="300 (default) or 500.")] = 300,
    date_from: FilterDateFrom = None, date_to: FilterDateTo = None,
    categories: FilterCategories = None, transport_only: FilterTransportOnly = False,
    modes: FilterModes = None, alcaldia: FilterAlcaldia = None,
    hours: FilterHours = None, dows: FilterDows = None,
) -> dict[str, Any]:
    """Rank Metro stations by crime within the radius. Prefer `rate` when the
    user asks which station is 'most dangerous' (raw counts mostly follow foot
    traffic), and mention the leader by `count` too. Stations without ridership
    data have no rate."""
    p = _params(date_from, date_to, categories, transport_only, modes, alcaldia, hours, dows,
                metric=metric, limit=limit, radius=radius_m)
    r = await _get("/api/stations/rank", p)
    if isinstance(r, dict) and not r.get("error"):
        for s in r.get("stations", []):
            s.pop("stop_ids", None)
    return r


@mcp.tool()
async def crime_trend(
    granularity: Annotated[str, Field(description="'month' (default), 'week', 'quarter' or 'year'.")] = "month",
    date_from: FilterDateFrom = None, date_to: FilterDateTo = None,
    categories: FilterCategories = None, transport_only: FilterTransportOnly = False,
    modes: FilterModes = None, alcaldia: FilterAlcaldia = None,
    hours: FilterHours = None, dows: FilterDows = None,
) -> dict[str, Any]:
    """Time series of reported cases for the filter, plus first/last values and
    percent change. Use month for trends over 1-3 years, year for the whole window."""
    p = _params(date_from, date_to, categories, transport_only, modes, alcaldia, hours, dows, granularity=granularity)
    return await _get("/api/stats/trend", p)


@mcp.tool()
async def category_breakdown(
    by: Annotated[str, Field(description="'categoria' (16 official categories, default), 'delito' (detailed names), or 'mode' (transport mode of passenger robberies).")] = "categoria",
    limit: Annotated[int, Field(ge=1, le=100)] = 15,
    date_from: FilterDateFrom = None, date_to: FilterDateTo = None,
    categories: FilterCategories = None, transport_only: FilterTransportOnly = False,
    modes: FilterModes = None, alcaldia: FilterAlcaldia = None,
    hours: FilterHours = None, dows: FilterDows = None,
) -> dict[str, Any]:
    """What kinds of crime make up the filtered set, with counts and shares."""
    p = _params(date_from, date_to, categories, transport_only, modes, alcaldia, hours, dows, by=by, limit=limit)
    return await _get("/api/stats/categories", p)


@mcp.tool()
async def time_profile(
    dim: Annotated[str, Field(description="'hour' (24 counts), 'dow' (7 counts, Monday first), 'hour_dow' (7x24 grid) or 'month' (12 counts, seasonality).")] = "hour",
    date_from: FilterDateFrom = None, date_to: FilterDateTo = None,
    categories: FilterCategories = None, transport_only: FilterTransportOnly = False,
    modes: FilterModes = None, alcaldia: FilterAlcaldia = None,
) -> dict[str, Any]:
    """When crimes happen. Hour profiles only use rows with a valid time-of-day;
    report `hora_ok_share` so the user knows the base."""
    p = _params(date_from, date_to, categories, transport_only, modes, alcaldia, dim=dim)
    return await _get("/api/stats/profile", p)


@mcp.tool()
async def area_summary(
    alcaldia: Annotated[Optional[str], Field(description="Alcaldía name, e.g. 'Cuauhtémoc'. Pass this OR colonia.")] = None,
    colonia: Annotated[Optional[str], Field(description="Colonia name, e.g. 'Roma Norte', 'Centro', 'Doctores'.")] = None,
    date_from: FilterDateFrom = None, date_to: FilterDateTo = None,
    categories: FilterCategories = None, transport_only: FilterTransportOnly = False,
    modes: FilterModes = None, hours: FilterHours = None, dows: FilterDows = None,
) -> dict[str, Any]:
    """Totals, per-month and per-km² figures, rank among peer areas (16 alcaldías
    or ~1,800 colonias), monthly series, top categories/delitos and the Metro
    stations inside the area."""
    if not alcaldia and not colonia:
        return {"error": "pass alcaldia or colonia"}
    p = _params(date_from, date_to, categories, transport_only, modes, None, hours, dows,
                alcaldia=alcaldia, colonia=colonia)
    r = await _get("/api/stats/area", p)
    if isinstance(r, dict) and not r.get("error"):
        r["monthly"] = r.get("monthly", [])[-24:]
    return r


@mcp.tool()
async def hotspots(
    res_m: Annotated[int, Field(description="Hex cell size: 250, 500 (default) or 1000 meters.")] = 500,
    top: Annotated[int, Field(ge=1, le=50)] = 12,
    date_from: FilterDateFrom = None, date_to: FilterDateTo = None,
    categories: FilterCategories = None, transport_only: FilterTransportOnly = False,
    modes: FilterModes = None, alcaldia: FilterAlcaldia = None,
    hours: FilterHours = None, dows: FilterDows = None,
) -> dict[str, Any]:
    """Where crimes concentrate: the top hexagonal cells by count with their
    colonia, alcaldía and nearest Metro station. Describe them by colonia and
    station, not by coordinates."""
    p = _params(date_from, date_to, categories, transport_only, modes, alcaldia, hours, dows, res=res_m, top=top)
    return await _get("/api/stats/hotspots", p)


@mcp.tool()
async def compare_periods(
    a_from: Annotated[str, Field(description="Period A start YYYY-MM-DD.")],
    a_to: Annotated[str, Field(description="Period A end YYYY-MM-DD.")],
    b_from: Annotated[str, Field(description="Period B start YYYY-MM-DD.")],
    b_to: Annotated[str, Field(description="Period B end YYYY-MM-DD.")],
    categories: FilterCategories = None, transport_only: FilterTransportOnly = False,
    modes: FilterModes = None, alcaldia: FilterAlcaldia = None,
    hours: FilterHours = None, dows: FilterDows = None,
) -> dict[str, Any]:
    """Two periods side by side per category, with per-month averages so unequal
    windows compare fairly. Quote per-month figures and the percent change."""
    p = _params(None, None, categories, transport_only, modes, alcaldia, hours, dows,
                a_from=a_from, a_to=a_to, b_from=b_from, b_to=b_to)
    return await _get("/api/stats/compare", p)


@mcp.tool()
async def victim_profile(
    group_by: Annotated[str, Field(description="'sexo', 'edad_band' (10-year bands), 'calidad_juridica', 'tipo_persona' (FISICA/MORAL) or 'categoria'.")] = "sexo",
    date_from: FilterDateFrom = None, date_to: FilterDateTo = None,
    categories: FilterCategories = None, transport_only: FilterTransportOnly = False,
    modes: FilterModes = None, alcaldia: FilterAlcaldia = None,
) -> dict[str, Any]:
    """Who the victims are (separate FGJ víctimas file, one row per victim,
    ends around May 2024). Mention its own coverage window."""
    p = _params(date_from, date_to, categories, transport_only, modes, alcaldia, group_by=group_by)
    return await _get("/api/stats/victims", p)


@mcp.tool()
async def crime_summary(
    date_from: FilterDateFrom = None, date_to: FilterDateTo = None,
    categories: FilterCategories = None, transport_only: FilterTransportOnly = False,
    modes: FilterModes = None, alcaldia: FilterAlcaldia = None,
    hours: FilterHours = None, dows: FilterDows = None,
) -> dict[str, Any]:
    """Headline totals for any filter: cases, per month, transport share, top categories."""
    p = _params(date_from, date_to, categories, transport_only, modes, alcaldia, hours, dows)
    return await _get("/api/stats/summary", p)


def main() -> None:
    logger.info("Starting Crime MCP server on port %s (backend=%s)", SERVER_PORT, BACKEND_URL)
    mcp.run(transport="streamable-http", host="0.0.0.0", port=SERVER_PORT, log_level=LOG_LEVEL.lower())


if __name__ == "__main__":
    main()
