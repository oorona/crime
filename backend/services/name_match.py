"""Station-name resolution for the Metro ridership CSV.

The ridership CSV is encoded with mojibake (`LÃ­nea` rather than `Línea`).
We unmojibake, then normalize (strip accents, lowercase) and compare against
`stops.stop_name_norm`. An exact match wins; otherwise we fall back to
`pg_trgm.similarity` with a sane threshold.
"""
from __future__ import annotations
import re
import unicodedata
from typing import Optional


_LINE_RE = re.compile(r"L[ií]nea\s+(\d+[A-Z]?)", re.IGNORECASE)


def fix_mojibake(s: str) -> str:
    """Repair UTF-8-encoded latin1-mojibake (`LÃ­nea` -> `Línea`)."""
    if not s or "Ã" not in s:
        return s
    try:
        return s.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def normalize(s: str) -> str:
    """Lowercase + strip accents + collapse whitespace."""
    if not s:
        return ""
    s = fix_mojibake(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.lower().strip().split())


def parse_metro_line(linea_text: str) -> Optional[str]:
    """`Línea 1` (or any mojibake variant) → `L1`. Special-case `LíneaA` → `LA`."""
    if not linea_text:
        return None
    txt = fix_mojibake(linea_text)
    m = _LINE_RE.search(txt)
    if m:
        return f"L{m.group(1)}"
    # Línea A / Línea B
    m = re.search(r"L[ií]nea\s+([A-Za-z])\b", txt)
    if m:
        return f"L{m.group(1).upper()}"
    return None


# Ridership names that differ from the GTFS stop names (renamed stations).
# Keys and values are normalized (see normalize()).
STATION_ALIASES = {
    "zocalo/tenochtitlan": "zocalo",
    "zocalo tenochtitlan": "zocalo",
    "ninos heroes": "ninos heroes y poder judicial cdmx",
    "ninos heroes/poder judicial cdmx": "ninos heroes y poder judicial cdmx",
}


class MetroStopResolver:
    """Per-run cache for resolving (line, station_name) → stop_id.

    We assume Metro stops have either:
      - a `route_short_name` from `routes` joined via stop_times → trips,
      - or a recognizable line in their `line_code` populated at ingest time.
    """

    def __init__(self, conn):
        self.conn = conn
        self.cache: dict[tuple[str, str], Optional[str]] = {}
        # Lazy: load all Metro stops once into memory for very fast exact lookup.
        self._index: dict[tuple[str, str], str] | None = None

    async def _load_index(self):
        rows = await self.conn.fetch(
            """
            SELECT s.stop_id,
                   s.stop_name_norm,
                   COALESCE(s.line_code, '') AS line_code
            FROM stops s
            WHERE s.agency_id = 'METRO'
            """
        )
        idx: dict[tuple[str, str], str] = {}
        for r in rows:
            key = (r["line_code"], r["stop_name_norm"])
            # First write wins; transfer stations show up under multiple lines
            # but the per-line key disambiguates.
            idx.setdefault(key, r["stop_id"])
            # Also index without line for trigram fallback parity
            idx.setdefault(("", r["stop_name_norm"]), r["stop_id"])
        self._index = idx

    async def resolve(self, line_text: str, station_name: str) -> Optional[str]:
        key = (line_text or "", station_name or "")
        if key in self.cache:
            return self.cache[key]

        if self._index is None:
            await self._load_index()

        line_code = parse_metro_line(line_text) or ""
        name_norm = normalize(station_name)
        name_norm = STATION_ALIASES.get(name_norm, name_norm)

        stop_id = self._index.get((line_code, name_norm)) if self._index else None
        if not stop_id and self._index:
            stop_id = self._index.get(("", name_norm))
        if not stop_id and self._index and "/" in name_norm:
            # "zocalo/tenochtitlan" style renames: try the part before the slash.
            head = name_norm.split("/")[0].strip()
            stop_id = self._index.get((line_code, head)) or self._index.get(("", head))
        if not stop_id:
            # Renamed with a suffix ("ninos heroes" -> "ninos heroes y poder judicial cdmx").
            row = await self.conn.fetchrow(
                "SELECT stop_id FROM stops WHERE agency_id = 'METRO' AND stop_name_norm LIKE $1 || ' %' "
                "ORDER BY (line_code = $2) DESC, stop_id LIMIT 1",
                name_norm, line_code,
            )
            if row:
                stop_id = row["stop_id"]

        if not stop_id:
            # Trigram fallback against the full Metro stop set.
            row = await self.conn.fetchrow(
                """
                SELECT stop_id
                FROM stops
                WHERE agency_id = 'METRO'
                  AND similarity(stop_name_norm, $1) > 0.6
                ORDER BY similarity(stop_name_norm, $1) DESC
                LIMIT 1
                """,
                name_norm,
            )
            if row:
                stop_id = row["stop_id"]

        self.cache[key] = stop_id
        return stop_id
