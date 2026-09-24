"""Shared crime filter: parsed once from query params, rendered to SQL for
whichever table backs an endpoint.

    f = Depends(crime_filter)
    await f.resolve(pool)                       # alcaldía name -> id
    sql, params = f.where("c", params, CASES_COLS)

Every value is bound as an asyncpg positional parameter; nothing is
interpolated. `unsupported(cols)` tells an endpoint whether a set filter
cannot be expressed on a pre-aggregated view, in which case it should fall
back to a live query on crime_cases.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from fastapi import HTTPException, Query

from .coverage import ym
from .name_match import normalize

NON_CRIMINAL = "HECHO NO DELICTIVO"

# Column sets of the tables an endpoint may filter.
CASES_COLS = {"date", "categoria_delito", "delito", "is_transport_related", "transport_mode",
              "alcaldia_id", "colonia_id", "hour", "dow"}
DAILY_COLS = {"day", "categoria_delito", "is_transport_related", "transport_mode", "alcaldia_id"}
STATION_MV_COLS = {"ym", "categoria_delito", "is_transport_related", "transport_mode"}
HEX_MV_COLS = {"ym", "categoria_delito", "is_transport_related"}
COLONIA_MV_COLS = {"ym", "categoria_delito", "is_transport_related", "colonia_id"}


def _csv(s: Optional[str]) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


@dataclass
class CrimeFilter:
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    categories: list[str] = field(default_factory=list)
    delitos: list[str] = field(default_factory=list)
    transport_only: bool = False
    modes: list[str] = field(default_factory=list)
    alcaldia: Optional[str] = None
    alcaldia_id: Optional[int] = None
    colonia_id: Optional[int] = None
    hours: Optional[tuple[int, int]] = None
    dows: list[int] = field(default_factory=list)
    include_non_criminal: bool = False

    # ── resolution ──────────────────────────────────────────────────────────
    async def resolve(self, pool) -> "CrimeFilter":
        if self.alcaldia and self.alcaldia_id is None:
            norm = normalize(self.alcaldia)
            row = await pool.fetchrow(
                "SELECT id, nomgeo FROM alcaldias WHERE nomgeo_norm = $1 "
                "OR similarity(nomgeo_norm, $1) > 0.4 ORDER BY (nomgeo_norm = $1) DESC, similarity(nomgeo_norm, $1) DESC LIMIT 1",
                norm)
            if not row:
                raise HTTPException(404, {"error": "alcaldia_not_found", "alcaldia": self.alcaldia})
            self.alcaldia_id = row["id"]
            self.alcaldia = row["nomgeo"]
        return self

    # ── introspection ───────────────────────────────────────────────────────
    def active(self) -> dict:
        d = {}
        if self.date_from: d["from"] = self.date_from.isoformat()
        if self.date_to: d["to"] = self.date_to.isoformat()
        if self.categories: d["categories"] = self.categories
        if self.delitos: d["delitos"] = self.delitos
        if self.transport_only: d["transport_only"] = True
        if self.modes: d["modes"] = self.modes
        if self.alcaldia: d["alcaldia"] = self.alcaldia
        if self.colonia_id is not None: d["colonia_id"] = self.colonia_id
        if self.hours: d["hours"] = f"{self.hours[0]}-{self.hours[1]}"
        if self.dows: d["dows"] = self.dows
        if self.include_non_criminal: d["include_non_criminal"] = True
        return d

    def unsupported(self, cols: set[str]) -> bool:
        """True when a set filter has no column on the target table."""
        need = set()
        if self.delitos: need.add("delito")
        if self.modes: need.add("transport_mode")
        if self.alcaldia_id is not None: need.add("alcaldia_id")
        if self.colonia_id is not None: need.add("colonia_id")
        if self.hours: need.add("hour")
        if self.dows: need.add("dow")
        return bool(need - cols)

    # ── SQL ─────────────────────────────────────────────────────────────────
    def where(self, alias: str, params: list, cols: set[str]) -> str:
        """Append bound values to `params`; return an AND-joined predicate
        (may be empty string). Callers prepend 'WHERE' / 'AND' as needed."""
        a = f"{alias}." if alias else ""
        preds: list[str] = []

        def bind(v) -> str:
            params.append(v)
            return f"${len(params)}"

        if "date" in cols:
            if self.date_from: preds.append(f"{a}fecha_hecho >= {bind(self.date_from)}::date")
            if self.date_to:   preds.append(f"{a}fecha_hecho < ({bind(self.date_to)}::date + 1)")
        elif "day" in cols:
            if self.date_from: preds.append(f"{a}day >= {bind(self.date_from)}::date")
            if self.date_to:   preds.append(f"{a}day <= {bind(self.date_to)}::date")
        elif "ym" in cols:
            if self.date_from: preds.append(f"{a}ym >= {bind(ym(self.date_from))}")
            if self.date_to:   preds.append(f"{a}ym <= {bind(ym(self.date_to))}")

        if "categoria_delito" in cols:
            if self.categories:
                preds.append(f"{a}categoria_delito = ANY({bind(self.categories)}::TEXT[])")
            elif not self.include_non_criminal:
                preds.append(f"{a}categoria_delito <> {bind(NON_CRIMINAL)}")
        if self.delitos and "delito" in cols:
            preds.append(f"{a}delito = ANY({bind(self.delitos)}::TEXT[])")
        if self.transport_only and "is_transport_related" in cols:
            preds.append(f"{a}is_transport_related")
        if self.modes and "transport_mode" in cols:
            preds.append(f"{a}transport_mode = ANY({bind(self.modes)}::TEXT[])")
        if self.alcaldia_id is not None and "alcaldia_id" in cols:
            preds.append(f"{a}alcaldia_id = {bind(self.alcaldia_id)}")
        if self.colonia_id is not None and "colonia_id" in cols:
            preds.append(f"{a}colonia_id = {bind(self.colonia_id)}")
        if self.hours and "hour" in cols:
            h0, h1 = self.hours
            if h0 <= h1:
                preds.append(f"{a}hour BETWEEN {bind(h0)} AND {bind(h1)}")
            else:
                preds.append(f"({a}hour >= {bind(h0)} OR {a}hour <= {bind(h1)})")
        if self.dows and "dow" in cols:
            preds.append(f"{a}dow = ANY({bind(self.dows)}::SMALLINT[])")
        return " AND ".join(preds)

    def where_clause(self, alias: str, params: list, cols: set[str], prefix: str = "WHERE") -> str:
        w = self.where(alias, params, cols)
        return f"{prefix} {w}" if w else ""


def _parse_hours(s: Optional[str]) -> Optional[tuple[int, int]]:
    if not s:
        return None
    try:
        h0, h1 = (int(x) for x in s.split("-"))
    except ValueError:
        raise HTTPException(400, "hours must be 'H0-H1' (0-23), e.g. 22-5")
    if not (0 <= h0 <= 23 and 0 <= h1 <= 23):
        raise HTTPException(400, "hours must be within 0-23")
    return (h0, h1)


def _parse_dows(s: Optional[str]) -> list[int]:
    out = []
    for x in _csv(s):
        try:
            v = int(x)
        except ValueError:
            raise HTTPException(400, "dows must be ISO weekday numbers 1-7 (1=Mon)")
        if not 1 <= v <= 7:
            raise HTTPException(400, "dows must be within 1-7")
        out.append(v)
    return out


def crime_filter(
    date_from: Optional[date] = Query(None, alias="from", description="Inclusive start date (fecha_hecho)"),
    date_to: Optional[date] = Query(None, alias="to", description="Inclusive end date"),
    categories: Optional[str] = Query(None, description="Comma-separated categoria_delito values (exact)"),
    delitos: Optional[str] = Query(None, description="Comma-separated delito values (exact)"),
    transport_only: bool = Query(False, description="Only crimes against public-transport passengers"),
    modes: Optional[str] = Query(None, description="Comma-separated transport modes: METRO,MB,TROLE,TL,SUB,RTP,MICRO,TAXI,TP"),
    alcaldia: Optional[str] = Query(None, description="Alcaldía name (accent-insensitive)"),
    colonia_id: Optional[int] = Query(None),
    hours: Optional[str] = Query(None, description="Hour range 'H0-H1' inclusive, wraps midnight (22-5)"),
    dows: Optional[str] = Query(None, description="Comma-separated ISO weekdays 1-7 (1=Mon)"),
    include_non_criminal: bool = Query(False, description="Include 'HECHO NO DELICTIVO' rows (excluded by default)"),
) -> CrimeFilter:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(400, "'from' must be <= 'to'")
    return CrimeFilter(
        date_from=date_from, date_to=date_to,
        categories=_csv(categories), delitos=_csv(delitos),
        transport_only=transport_only, modes=[m.upper() for m in _csv(modes)],
        alcaldia=alcaldia, colonia_id=colonia_id,
        hours=_parse_hours(hours), dows=_parse_dows(dows),
        include_non_criminal=include_non_criminal,
    )
