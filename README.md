# CDMX Crime GIS · Delitos y transporte público

Interactive web map of reported crime in Mexico City layered on the public
transport network, with per-station statistics normalized by Metro ridership
and a Gemini chat that answers pattern questions with numbers computed from
the data. Standalone sibling of [`../metro`](../metro) (same stack, same
shared postgres, same Traefik), built from CDMX open data.

**What you get**

- Heat map of FGJ *carpetas de investigación* (2019 → Nov 2024) as hexagonal density, over Metro / Metrobús / etc. lines and stations.
- 163 physical Metro stations as graduated circles: cases within 300 m or 500 m of every platform, and **cases per million entries** for the same months (raw counts mostly follow foot traffic).
- Colonia and alcaldía choropleths, individual cases at street zoom, click any station or area for a panel with monthly series, category mix, top delitos and an hour × weekday grid.
- Filters: period, category (16 official categories, "solo alto impacto" preset), crimes against public-transport passengers by mode, hour range and weekday, count vs rate, radius.
- Chat (`/chat` and the mini chat on the map): Gemini + 13 MCP tools (`rank_stations`, `station_crime_stats`, `compare_periods`, `hotspots`, `time_profile`, `area_summary`, `victim_profile`, …). Answers state the data window and caveats; results highlight on the map.

---

## Stack

| Layer | Tech |
|---|---|
| Database | **Shared** PostgreSQL 18 (container `postgres` at `/home/iktdts/apps/infra/database`) + PostGIS 3.6, unaccent, pg_trgm, btree_gist, pgcrypto. DB `cdmx_crime`, role + schema `crime_user`. |
| Backend | FastAPI · asyncpg · Alembic raw-SQL migrations · pandas (chunked ingest) |
| Frontend | React 18 · Vite 6 · MapLibre GL 4 (heatmap, choropleths, graduated circles; inline-SVG charts, no chart lib) |
| Chat | Gemini 2.5 Flash ReAct loop (`backend/services/chat_agent.py`) over a FastMCP server (`mcp_server/server.py`) |
| Data | datos.cdmx.gob.mx (CC-BY-4.0): FGJ carpetas + víctimas, STC Metro daily ridership, GTFS static, colonias + alcaldías |

---

## Data sources

All from the CDMX open-data portal (CKAN). **The portal geo-blocks non-Mexican IPs**: run `scripts/fetch_data.sh` from Mexico or on the Mexico VPN. A refused connection or 403 on the first request is the block, not a bad URL.

| Dataset | File | Coverage |
|---|---|---|
| FGJ carpetas de investigación (case-level, accumulated) | `data/carpetasFGJ_acumulado_2025_01.csv` (560 MB) | Jan 2016 → **Nov 2024** (rows before 2019 are dropped at ingest) |
| FGJ víctimas (victim-level, accumulated) | `data/victimasFGJ_acumulado_2024_09.csv` (373 MB) | Jan 2019 → ~May 2024 |
| STC Metro afluencia diaria por estación (simple) | `data/afluencia_metro_simple.csv` (60 MB) | 2010 → Jul 2026 (2019+ kept) |
| GTFS static | `gtfs/*.txt` | Oct 2022 feed, identical to `../metro/gtfs` |
| Catálogo de colonias, Límite de alcaldías | `boundaries/colonias.json`, `boundaries/alcaldias.json` | current |

Exact URLs live in `scripts/fetch_data.sh`. As of Sep 2026 the portal publishes no 2025/2026 crime file despite claiming monthly updates; when one appears, drop it in `data/` (the loaders glob `carpetasFGJ_acumulado_*.csv` and take the newest name) and re-run the ingest.

### Caveats baked into the app (and into the chat's system prompt)

- Cases are **reported** crimes (denuncias), not incidence: the cifra negra is large and uneven.
- ~6% of cases have no usable coordinates (indeterminate / outside CDMX) and are excluded from maps and station/colonia stats.
- Station stats count cases within a radius of *all* platforms of a physical station (Pantitlán = 4 GTFS stops = 1 station). Neighbouring radii overlap; one case can count for two stations. "Cerca de la estación", not "en la estación": only delitos named *A BORDO DE METRO* are explicitly inside the system.
- A time of exactly 00:00 is a placeholder → `hora_ok=false`; hour profiles use only rows with a valid time and report the share.
- `DELITO DE BAJO IMPACTO` is ~85% of everything; `HECHO NO DELICTIVO` is excluded unless `include_non_criminal=true`.
- Víctimas and carpetas are separate tables with no common id.

---

## Repository layout

```
crime/
├── docker-compose.yml           backend + mcp_server + frontend on the shared networks
├── .env.example / .env / .env.test / .env.prod
├── scripts/
│   ├── db-setup.sh              bootstrap cdmx_crime + crime_user + extensions on the shared postgres
│   ├── enable_extensions.sh     idempotent extension verifier
│   └── fetch_data.sh            download all inputs (VPN!), idempotent, writes data/CHECKSUMS.txt
├── gtfs/  data/  boundaries/    inputs (read-only mounts; data/ and boundaries/ are gitignored)
├── secrets/                     db_password.txt · gemini_api_key.txt · crime_mcp_api_key.txt
├── backend/
│   ├── main.py                  FastAPI app; ingest runs as a background task; /health reports it
│   ├── alembic/versions/        001 extensions · 002 GTFS · 003 boundaries · 004 ridership
│   │                            005 crime tables · 006 stats views · 007 chat
│   ├── routers/                 stops · routes · stations · crime · stats · chat
│   ├── services/
│   │   ├── ingest.py            orchestrator + CLI (python -m services.ingest)
│   │   ├── ingest_gtfs.py       GTFS → stops/shapes + metro_stations (name clusters)
│   │   ├── ingest_boundaries.py GeoJSON → alcaldias / colonias
│   │   ├── ingest_ridership.py  afluencia CSV → ridership_metro_station_daily
│   │   ├── ingest_crime.py      chunked FGJ CSV → crime_cases / crime_victims (+ spatial enrichment)
│   │   ├── crime_parsing.py     pure parsing helpers (dates, coords, transport mode) — unit-tested
│   │   ├── filters.py           CrimeFilter: query params → bound SQL predicates for any table/view
│   │   ├── chat_agent.py · mcp_client.py   Gemini ReAct loop (from ../metro)
│   ├── prompts/chat_system_prompt.txt
│   └── tests/                   pytest (parsing, filters)
├── mcp_server/server.py         FastMCP, 13 tools proxying /api/stats/* and /api/stations/*
└── frontend/src/
    ├── MapApp.jsx · App.jsx     filter state, deep links, ingest banner
    ├── components/Map.jsx       heat · points · colonias · alcaldías · station circles · highlights
    ├── components/FilterPanel.jsx · LayerPanel.jsx · StationCrimePanel.jsx · AreaPanel.jsx · Legend.jsx
    ├── components/charts/       Sparkline · Bars · HourDowGrid (inline SVG)
    └── components/MiniChat.jsx · ChatInterface.jsx · TracePanel.jsx
```

---

## Quick start

Prerequisites: Docker Compose v2, the shared `postgres` container up on `dbnet`, the external networks `internet`/`intranet`/`dbnet` created, a Mexico VPN for the download.

```sh
cp .env.example .env                      # local dev values are already right
./scripts/db-setup.sh                     # creates cdmx_crime + crime_user, writes secrets/db_password.txt
cp ../metro/secrets/gemini_api_key.txt secrets/   # or paste your own key
openssl rand -hex 32 > secrets/crime_mcp_api_key.txt
./scripts/fetch_data.sh                   # ~1 GB; needs the Mexico VPN
docker compose up -d --build
docker logs -f cdmx-crime-backend         # watch the ingest
```

**First boot ingests in the background** (GTFS ~10 s, boundaries ~5 s, ridership ~1 min, cases ~5–10 min, víctimas ~5 min, view refresh ~2 min). The API is up immediately; `/health` shows the step in progress and `views_populated`; the crime endpoints answer 503 `{"error":"ingesting"}` until the views exist, and the frontend shows a banner. Re-runs are idempotent (SHA-256 of each input in `data_ingest_runs`).

Open <http://localhost:5174> (the gitignored `docker-compose.override.yml` publishes the frontend on 5174 and the backend on 8001; the base compose file exposes nothing on the host, Traefik reaches the containers over the docker networks).

---

## Smoke checks

```sh
B=http://localhost:8001   # via docker-compose.override.yml
curl -s $B/health | jq '.ingest.status, .views_populated'
curl -s $B/api/stats/coverage | jq '.cases, .ridership'
curl -s "$B/api/stations/rank?metric=rate&limit=5&from=2023-01-01&to=2023-12-31" | jq '.stations[] | {station_name, n_cases, rate_per_million}'
curl -s "$B/api/stations/pantitlan/report?radius=300" | jq '.totals'
curl -s "$B/api/crime/heat?res=500&from=2024-01-01" | jq '.count, .max_n'
curl -s "$B/api/crime/points?bbox=-99.15,19.42,-99.13,19.44&limit=100" | jq '.count, .truncated'
curl -s "$B/api/stats/profile?dim=hour&transport_only=true" | jq '.peak_hour, .hora_ok_share'
curl -s "$B/api/stats/compare?a_from=2019-01-01&a_to=2019-12-31&b_from=2023-01-01&b_to=2023-12-31" | jq '.total_change_pct'
```

```sql
-- docker exec -it postgres psql -U postgres -d cdmx_crime
SET search_path TO crime_user, public;
SELECT count(*), min(fecha_hecho), max(fecha_hecho), count(*) FILTER (WHERE geom IS NULL) FROM crime_cases;
SELECT count(*) FROM metro_stations;                                       -- 163
SELECT categoria_delito, count(*) FROM crime_cases WHERE year = 2024 GROUP BY 1 ORDER BY 2 DESC LIMIT 5;
SELECT transport_mode, count(*) FROM crime_cases WHERE is_transport_related GROUP BY 1 ORDER BY 2 DESC;
-- MV vs live agreement for one station:
SELECT sum(n_cases) FROM mv_station_crime WHERE station_key = 'pantitlan' AND radius_m = 300 AND ym BETWEEN 202301 AND 202312;
SELECT count(*) FROM metro_stations ms JOIN crime_cases c ON ST_DWithin(ms.pts::geography, c.geom::geography, 300)
 WHERE ms.station_key = 'pantitlan' AND c.ym BETWEEN 202301 AND 202312;
```

Tests: `docker compose exec backend python -m pytest -q -p no:cacheprovider tests` (the rootfs is read-only, hence no cache).

---

## Day-to-day

```sh
docker logs -f cdmx-crime-backend
docker compose up -d --build backend                    # after editing backend code
docker compose exec backend python -m services.ingest --only crime_cases --force   # reload one source
docker compose exec backend python -m services.ingest --force                      # reload everything
docker exec postgres psql -U postgres -d cdmx_crime -c "TRUNCATE crime_user.data_ingest_runs;"  # forget hashes
INGEST_ON_BOOT=0                                        # in .env: never ingest on boot
```

When a new accumulated file appears on the portal: `./scripts/fetch_data.sh --force`, then restart the backend (the hash changes, so the loader re-runs and refreshes the views).

---

## API (all under `/api`)

Every crime endpoint accepts the same filter query: `from`, `to` (dates), `categories`, `delitos` (comma-separated exact strings), `transport_only`, `modes`, `alcaldia`, `colonia_id`, `hours` (`22-5`, wraps midnight), `dows` (`6,7`, 1 = Mon), `include_non_criminal`. Responses echo `window` and `filters`.

| Endpoint | Purpose |
|---|---|
| `GET /stations?radius&normalize` · `/stations/rank?metric&limit` · `/stations/{key}/report` | station circles, rankings, full report |
| `GET /crime/points?bbox&limit` · `/crime/heat?res&geom` · `/crime/colonias?normalize` · `/crime/alcaldias` | geodata for the map |
| `GET /stats/coverage` · `/stats/categories/list` · `/stats/summary` · `/stats/trend?granularity` · `/stats/categories?by` · `/stats/profile?dim` · `/stats/area?alcaldia|colonia` · `/stats/compare?a_from…` · `/stats/hotspots?res&top` · `/stats/victims?group_by` | small JSON; these are the MCP tool payloads |
| `GET /agencies` · `/stops` · `/stops/search` · `/shapes` · `/lines/stops` | transit network (from metro) |
| `POST /chat/stream` (SSE) · `/chat/conversations…` | chat |

Pre-aggregated materialized views (`mv_station_crime`, `mv_hex_crime`, `mv_colonia_crime_monthly`, `mv_crime_daily`, `mv_station_ridership_monthly`) serve month-granular filters; when a filter needs a column they lack (hours, weekdays, delitos, modes on the hex view) the endpoint falls back to a live query on `crime_cases`, which is slower (1–3 s) but exact.

---

## Deploy (test / prod)

Same convention as metro: `.env.test` / `.env.prod` carry unique container names (`cdmx-crime-test-*`), hosts (`crime.home.iktdts.com`, `crimemcp.home.iktdts.com`) and Traefik router names (`crime-frontend`, `crimemcp`); `secrets.test/` and `secrets.prod/` are renamed to `secrets/` on the target by the infra deploy scripts. The data directories are not synced by git: run `scripts/fetch_data.sh` on the target (VPN) or rsync `data/` and `boundaries/`.

---

## License & attribution

Crime and ridership data: Gobierno de la Ciudad de México, Portal de Datos Abiertos (CC-BY-4.0) — FGJ CDMX, SEMOVI / STC Metro, ADIP, INEGI. Basemap tiles: OpenStreetMap (ODbL) and ESRI World Imagery.
