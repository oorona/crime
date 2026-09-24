"""Cached coverage window (min/max month of the crime data) for clamping."""
from __future__ import annotations
import time
from datetime import date

_cache: dict = {"at": 0.0, "row": None}
TTL = 60.0


async def coverage(pool) -> dict:
    """Returns {'ym_from', 'ym_to', 'date_from', 'date_to'} for crime_cases (or Nones)."""
    if _cache["row"] is not None and time.time() - _cache["at"] < TTL:
        return _cache["row"]
    r = await pool.fetchrow("SELECT MIN(ym) AS ym_from, MAX(ym) AS ym_to, "
                            "MIN(fecha_hecho)::date AS d_from, MAX(fecha_hecho)::date AS d_to FROM crime_cases")
    row = {"ym_from": r["ym_from"], "ym_to": r["ym_to"], "date_from": r["d_from"], "date_to": r["d_to"]}
    _cache.update(at=time.time(), row=row)
    return row


def ym(d: date) -> int:
    return d.year * 100 + d.month


def ym_to_date(v: int, end: bool = False) -> date:
    y, m = divmod(v, 100)
    if not end:
        return date(y, m, 1)
    return date(y + (m == 12), 1 if m == 12 else m + 1, 1).fromordinal(
        date(y + (m == 12), 1 if m == 12 else m + 1, 1).toordinal() - 1)


def months_between(ym_a: int, ym_b: int) -> int:
    ya, ma = divmod(ym_a, 100)
    yb, mb = divmod(ym_b, 100)
    return (yb - ya) * 12 + (mb - ma) + 1
