"""Pure parsing helpers for the FGJ carpetas / víctimas CSVs. No I/O, unit-tested.

Quirks handled (all observed in the published files):
  * `fecha_hecho` is either 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'; when the
    date has no time, `hora_hecho` ('HH:MM:SS') may carry it.
  * A time of exactly 00:00:00 is overwhelmingly a placeholder, so it is kept
    on the timestamp but flagged `hora_ok=False` and excluded from hour profiles.
  * `anio_hecho` can be a float string ('2015.0'); literal 'NA' everywhere.
  * Coordinates are 'NA' for indeterminate rows and occasionally outside CDMX.
  * `delito` names the transport mode in free text ("ROBO A PASAJERO A BORDO
    DE METROBUS SIN VIOLENCIA"); `categoria_delito` names it for a few
    categories only.
"""
from __future__ import annotations
import re
from datetime import datetime
from typing import Optional

from .name_match import normalize

NA_VALUES = {"", "NA", "N/A", "NAN", "NULL", "NONE", "-"}

# CDMX bounding box (lon, lat), generous enough for Milpa Alta and Cuajimalpa.
CDMX_LON = (-99.37, -98.94)
CDMX_LAT = (19.05, 19.60)

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")

# Ordered: more specific patterns first (METROBUS before METRO).
_MODE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("MB",    re.compile(r"\bMETROBUS\b")),
    ("METRO", re.compile(r"\bMETRO\b")),
    ("TROLE", re.compile(r"\bTROLEBUS\b")),
    ("TL",    re.compile(r"\bTREN LIGERO\b")),
    ("SUB",   re.compile(r"\bSUBURBANO\b")),
    ("RTP",   re.compile(r"\bRTP\b")),
    ("MICRO", re.compile(r"\b(PESERO|COLECTIVO|MICROBUS|COMBI)\b")),
    ("TAXI",  re.compile(r"\bTAXI\b")),
    ("TP",    re.compile(r"\bTRANSPORTE PUBLICO\b")),
]

# Fallback when `delito` is generic but the category is explicit.
_CATEGORY_MODES = [
    ("MB",    re.compile(r"\bMETROBUS\b")),
    ("METRO", re.compile(r"\bMETRO\b")),
    ("MICRO", re.compile(r"\bMICROBUS\b")),
    ("TAXI",  re.compile(r"\bTAXI\b")),
]

MODE_LABELS = {
    "METRO": "Metro", "MB": "Metrobús", "TROLE": "Trolebús", "TL": "Tren Ligero",
    "SUB": "Tren Suburbano", "RTP": "RTP", "MICRO": "Microbús / pesero", "TAXI": "Taxi",
    "TP": "Transporte público (genérico)",
}


def is_na(s: Optional[str]) -> bool:
    return s is None or s.strip().upper() in NA_VALUES


def parse_dt(fecha: Optional[str], hora: Optional[str]) -> tuple[Optional[datetime], bool]:
    """Return (timestamp, hora_ok). hora_ok is True only when a real, non-midnight
    time was present in either the date string or the separate hour field."""
    if is_na(fecha):
        return None, False
    f = fecha.strip()
    try:
        d = datetime.strptime(f[:10], "%Y-%m-%d")
    except ValueError:
        return None, False

    hh = mm = ss = None
    tail = f[10:].strip()
    if tail:
        m = _TIME_RE.match(tail[:8].strip()) or _TIME_RE.match(tail)
        if m:
            hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if hh is None and not is_na(hora):
        m = _TIME_RE.match(hora.strip())
        if m:
            hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if hh is None or not (0 <= hh < 24 and 0 <= mm < 60 and 0 <= ss < 60):
        return d, False
    ts = d.replace(hour=hh, minute=mm, second=ss)
    hora_ok = not (hh == 0 and mm == 0 and ss == 0)
    return ts, hora_ok


def parse_year(s: Optional[str]) -> Optional[int]:
    if is_na(s):
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def parse_float(s: Optional[str]) -> Optional[float]:
    if is_na(s):
        return None
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v if v == v else None  # NaN guard


def in_cdmx_bbox(lat: Optional[float], lon: Optional[float]) -> bool:
    if lat is None or lon is None:
        return False
    return CDMX_LON[0] <= lon <= CDMX_LON[1] and CDMX_LAT[0] <= lat <= CDMX_LAT[1]


def parse_coords(lat_s: Optional[str], lon_s: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    """Coordinates only when both parse AND fall inside CDMX; else (None, None)."""
    lat, lon = parse_float(lat_s), parse_float(lon_s)
    if in_cdmx_bbox(lat, lon):
        return lat, lon
    return None, None


def transport_mode(delito: Optional[str], categoria: Optional[str] = None) -> Optional[str]:
    """Extract the transport mode a `delito` refers to, or None when the crime is
    not about public-transport passengers. Freight ('TRANSPORTISTA', 'REPARTIDOR')
    and private vehicles are intentionally not transport-related."""
    text = normalize(delito or "").upper()
    if text:
        for code, rx in _MODE_PATTERNS:
            if rx.search(text):
                return code
    cat = normalize(categoria or "").upper()
    if cat and "PASAJERO" in cat:
        for code, rx in _CATEGORY_MODES:
            if rx.search(cat):
                return code
    return None


def parse_edad(s: Optional[str]) -> Optional[int]:
    v = parse_float(s)
    if v is None:
        return None
    v = int(v)
    return v if 0 <= v <= 120 else None


def clean_text(s: Optional[str]) -> Optional[str]:
    """Strip; map NA-like tokens to None; keep original casing/accents."""
    if is_na(s):
        return None
    return " ".join(s.split())
