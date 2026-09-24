# Architecture

```
 datos.cdmx.gob.mx ─► scripts/fetch_data.sh ─► data/ gtfs/ boundaries/ (read-only mounts)
                                                       │
                                        backend ingest (background task, hashed, idempotent)
                                                       │
                              PostgreSQL 18 + PostGIS  ─  schema crime_user  ─  materialized views
                                                       │
            ┌──────────────────────────────────────────┼──────────────────────────────┐
     frontend (React + MapLibre)              REST /api/*                      mcp_server (FastMCP, 13 tools)
     map · panels · filters · chat UI  ◄── SSE /api/chat/stream ◄── chat_agent (Gemini ReAct) ──► MCP tools ──► /api/stats/*
```

Three containers on the shared `intranet` and `dbnet` networks, all with
read-only root filesystems: `backend` (FastAPI), `mcp_server` (FastMCP) and
`frontend` (static Vite build). The database is the shared `postgres`
container from `infra/database`; this app owns database `cdmx_crime`, role
and schema `crime_user`.

## Repository layout

```
crime/
├── docker-compose.yml           backend + mcp_server + frontend on the shared networks
├── .env.example                 every setting, documented
├── scripts/
│   ├── db-setup.sh              bootstrap cdmx_crime + crime_user + extensions on the shared postgres
│   ├── enable_extensions.sh     idempotent extension verifier
│   └── fetch_data.sh            download all inputs (VPN), idempotent, writes data/CHECKSUMS.txt
├── gtfs/  data/  boundaries/    inputs (read-only mounts; data/ and boundaries/ are gitignored)
├── secrets/                     db_password.txt · gemini_api_key.txt · crime_mcp_api_key.txt (gitignored)
├── backend/
│   ├── main.py                  FastAPI app; ingest runs as a background task; /health reports it
│   ├── alembic/versions/        001 extensions · 002 GTFS · 003 boundaries · 004 ridership
│   │                            005 crime tables · 006 stats views · 007 chat
│   ├── routers/                 stops · routes · stations · crime · stats · chat
│   ├── services/
│   │   ├── ingest.py            orchestrator + CLI (python -m services.ingest)
│   │   ├── ingest_gtfs.py       GTFS to stops/shapes + metro_stations (name clusters)
│   │   ├── ingest_boundaries.py GeoJSON to alcaldias / colonias
│   │   ├── ingest_ridership.py  afluencia CSV to ridership_metro_station_daily
│   │   ├── ingest_crime.py      chunked FGJ CSV to crime_cases / crime_victims (+ spatial enrichment)
│   │   ├── crime_parsing.py     pure parsing helpers (dates, coords, transport mode), unit-tested
│   │   ├── filters.py           CrimeFilter: query params to bound SQL predicates for any table or view
│   │   └── chat_agent.py · mcp_client.py   Gemini ReAct loop (shared design with metro)
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

## Ingest

`main.py` starts the ingest orchestrator as a background task on boot when
`INGEST_ON_BOOT=1`, and `/health` reports the step in progress. Each loader
hashes its input (SHA-256 recorded in `data_ingest_runs`) and skips when the
hash is unchanged, so restarts are free and a new accumulated file from the
portal triggers a reload by itself. Order: GTFS (stops, shapes, and
`metro_stations`, which clusters the GTFS stops of one physical station by
name so Pantitlán's four platforms are one station), boundaries (alcaldías
and colonias GeoJSON), ridership (daily entries per station), then the two
FGJ files read in pandas chunks into `crime_cases` and `crime_victims` with
spatial enrichment (geometry, colonia, alcaldía, transport mode, `hora_ok`
for a placeholder 00:00 time, `is_transport_related`). The views refresh
last. `python -m services.ingest --only <source> --force` reloads one
source by hand.

## Schema and views

Migrations are raw SQL under Alembic: extensions, GTFS tables, boundaries,
ridership, crime tables, stats views, chat conversations. Pre-aggregated
materialized views serve month-granular filters:

| view | grain |
|---|---|
| `mv_station_crime` | station, radius (300 or 500 m), year-month, category |
| `mv_hex_crime` | hex cell at 250, 500 and 1000 m, year-month, category |
| `mv_colonia_crime_monthly` | colonia, year-month, category |
| `mv_crime_daily` | day, category |
| `mv_station_ridership_monthly` | station, year-month entries, for the per-million rate |

When a filter needs a column the views lack (hours, weekdays, exact delitos,
transport modes on the hex view) the endpoint falls back to a live query on
`crime_cases`: slower (1 to 3 s) but exact. `services/filters.py` turns the
shared query parameters into bound SQL predicates for any table or view, so
every crime endpoint accepts the same filter set.

## API (all under `/api`)

Shared filter query: `from`, `to`, `categories`, `delitos` (exact strings),
`transport_only`, `modes`, `alcaldia`, `colonia_id`, `hours` (`22-5` wraps
midnight), `dows` (`6,7`, 1 = Monday), `include_non_criminal`. Responses echo
`window` and `filters`.

| Endpoint | Purpose |
|---|---|
| `GET /stations?radius&normalize` · `/stations/rank?metric&limit` · `/stations/{key}/report` | station circles, rankings, full report |
| `GET /crime/points?bbox&limit` · `/crime/heat?res&geom` · `/crime/colonias?normalize` · `/crime/alcaldias` | geodata for the map |
| `GET /stats/coverage` · `/stats/categories/list` · `/stats/summary` · `/stats/trend?granularity` · `/stats/categories?by` · `/stats/profile?dim` · `/stats/area?alcaldia|colonia` · `/stats/compare?a_from…` · `/stats/hotspots?res&top` · `/stats/victims?group_by` | small JSON; these are the MCP tool payloads |
| `GET /agencies` · `/stops` · `/stops/search` · `/shapes` · `/lines/stops` | transit network (from metro) |
| `POST /chat/stream` (SSE) · `/chat/conversations…` | chat |

Until the views exist the crime endpoints answer 503 `{"error":"ingesting"}`.

## Chat

`services/chat_agent.py` runs a ReAct loop on Gemini 2.5 Flash with a
thinking budget large enough that the model emits a reasoning summary on
every step, including the final answer. Each iteration streams the model's
thoughts and function calls to the client over SSE (`model.thinking`, tool
call and result events, final text), so the frontend's trace panel shows
the reasoning as it happens. Tool calls go through `mcp_client.py` to the
`mcp_server` container, which exposes 13 read-only FastMCP tools
(`rank_stations`, `station_crime_stats`, `compare_periods`, `hotspots`,
`time_profile`, `area_summary`, `victim_profile` and others) that proxy the
`/api/stats/*` and `/api/stations/*` endpoints and are guarded by the MCP
shared key. The system prompt in `backend/prompts/` carries the data window
and the caveats, so every answer states them. Conversations persist in the
chat tables; results carry station keys and geometries the map highlights.

## Frontend

React 18 with Vite, MapLibre GL for the heatmap, choropleths, graduated
circles and point layer, and inline-SVG charts (sparkline, bars, hour by
weekday grid) with no chart library. `MapApp.jsx` holds the filter state and
serializes it into the URL so every view is a deep link; `App.jsx` shows the
ingest banner while `/health` reports `views_populated: false`. The mini
chat lives on the map; `/chat` is the full page with the trace panel.
