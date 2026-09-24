#!/usr/bin/env bash
# ── CDMX Crime GIS — data fetch ──────────────────────────────────────────────
# Downloads the open-data inputs from datos.cdmx.gob.mx (CC-BY-4.0).
#
#   datos.cdmx.gob.mx and archivo.datos.cdmx.gob.mx GEO-BLOCK non-Mexican IPs.
#   Run this from a Mexican IP or through the Mexico VPN. A "connection
#   refused" or 403 on the first request means the block, not a bad URL.
#
# Idempotent: files that already exist and are non-empty are skipped; partial
# downloads resume with `curl -C -`. Pass --force to re-download everything.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

mkdir -p "$ROOT/data" "$ROOT/boundaries" "$ROOT/gtfs"

fetch() {
    local url=$1 out=$2
    if [[ $FORCE -eq 0 && -s "$out" ]]; then
        echo "  = $(basename "$out") (exists, skip)"
        return 0
    fi
    echo "  > $(basename "$out")"
    if ! curl -L --fail --retry 3 --retry-delay 5 -C - \
            -A "cdmx-crime-gis/1.0 (+https://github.com/iktdts)" \
            -o "$out.part" "$url"; then
        echo "  ! download failed for $url" >&2
        echo "    (refused / 403 = geo-block: connect to the Mexico VPN and retry)" >&2
        rm -f "$out.part"
        return 1
    fi
    mv "$out.part" "$out"
}

echo ""
echo "══════════════════════════════════════════════"
echo "  CDMX Crime GIS — fetching open data"
echo "══════════════════════════════════════════════"

# ── FGJ crime data (archivo host, plain CSV) ────────────────────────────────
fetch "https://archivo.datos.cdmx.gob.mx/FGJ/carpetas/carpetasFGJ_acumulado_2025_01.csv" \
      "$ROOT/data/carpetasFGJ_acumulado_2025_01.csv"
fetch "https://archivo.datos.cdmx.gob.mx/FGJ/victimas/victimasFGJ_acumulado_2024_09.csv" \
      "$ROOT/data/victimasFGJ_acumulado_2024_09.csv"

# ── Metro daily ridership per station (SEMOVI, "afluencia simple") ──────────
fetch "https://datos.cdmx.gob.mx/dataset/f2046fd5-51b5-4876-b008-bd65d95f9a02/resource/0e8ffe58-28bb-4dde-afcd-e5f5b4de4ccb/download/0e8ffe58-28bb-4dde-afcd-e5f5b4de4ccb.csv" \
      "$ROOT/data/afluencia_metro_simple.csv"

# ── Boundaries ───────────────────────────────────────────────────────────────
fetch "https://datos.cdmx.gob.mx/dataset/02c6ce99-dbd8-47d8-aee1-ae885a12bb2f/resource/026b42d3-a609-44c7-a83d-22b2150caffc/download/026b42d3-a609-44c7-a83d-22b2150caffc.json" \
      "$ROOT/boundaries/colonias.json"
fetch "https://datos.cdmx.gob.mx/dataset/bae265a8-d1f6-4614-b399-4184bc93e027/resource/deb5c583-84e2-4e07-a706-1b3a0dbc99b0/download/deb5c583-84e2-4e07-a706-1b3a0dbc99b0.json" \
      "$ROOT/boundaries/alcaldias.json"
# Optional context layer (not ingested in v1, kept for later joins by cve_col)
fetch "https://datos.cdmx.gob.mx/dataset/75fda961-2c64-4671-bdef-a61feb1ec1cb/resource/12d71b2e-1ae0-44e8-8ee8-7c5e3489adde/download/12d71b2e-1ae0-44e8-8ee8-7c5e3489adde.json" \
      "$ROOT/boundaries/marginalidad.json" || true

# ── Documentation only ───────────────────────────────────────────────────────
fetch "https://datos.cdmx.gob.mx/dataset/7593b324-6010-44f7-8132-cb8b2276c842/resource/10235569-f4a9-4876-9465-9780887df8e2/download/10235569-f4a9-4876-9465-9780887df8e2.xlsx" \
      "$ROOT/data/diccionario_victimas.xlsx" || true

# ── GTFS static: byte-identical to ../metro/gtfs (verified), prefer local ────
if [[ -s "$ROOT/../metro/gtfs/stops.txt" ]]; then
    cp -n "$ROOT/../metro/gtfs/"*.txt "$ROOT/gtfs/" 2>/dev/null || true
    echo "  = gtfs/*.txt copied from ../metro/gtfs"
elif [[ ! -s "$ROOT/gtfs/stops.txt" ]]; then
    fetch "https://datos.cdmx.gob.mx/dataset/75538d96-3ade-4bc5-ae7d-d85595e4522d/resource/32ed1b6b-41cd-49b3-b7f0-b57acb0eb819/download/32ed1b6b-41cd-49b3-b7f0-b57acb0eb819.zip" \
          "$ROOT/gtfs/gtfs.zip"
    (cd "$ROOT/gtfs" && unzip -oq gtfs.zip)
fi

# ── Sanity ───────────────────────────────────────────────────────────────────
echo ""
echo "  CSV headers:"
for f in "$ROOT"/data/*.csv; do printf "    %-40s %s\n" "$(basename "$f")" "$(head -c 400 "$f" | head -n 1 | cut -c1-90)"; done

python3 - "$ROOT/boundaries/colonias.json" <<'PY'
import json, sys
fc = json.load(open(sys.argv[1], encoding="utf-8"))
def first_coord(g):
    c = g["coordinates"]
    while isinstance(c[0], list): c = c[0]
    return c
lon, lat = first_coord(fc["features"][0]["geometry"])[:2]
assert -99.5 < lon < -98.8 and 19.0 < lat < 19.7, f"colonias.json is not WGS84 lon/lat: {lon},{lat}"
print(f"  colonias.json: {len(fc['features'])} features, WGS84 ok")
PY

(cd "$ROOT" && sha256sum data/*.csv boundaries/*.json > data/CHECKSUMS.txt)
echo ""
echo "  Done. Checksums in data/CHECKSUMS.txt"
