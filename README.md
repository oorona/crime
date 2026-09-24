# CDMX Crime GIS · Delitos y transporte público

Interactive web map of reported crime in Mexico City layered on the public
transport network, with per-station statistics normalized by Metro ridership
and a Gemini chat that answers pattern questions with numbers computed from
the data. Built entirely from CDMX open data; a standalone sibling of the
[metro](https://github.com/oorona/metro) transit GIS (same stack, same
shared PostGIS, same Traefik).

- Setup, data download and deployment: [docs/INSTALLATION.md](docs/INSTALLATION.md)
- Components, schema, API and data flow: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## The problem

Raw crime counts around a Metro station mostly measure foot traffic:
Pantitlán tops every list because it moves the most people. The question
worth asking is which stations have more reported crime *per rider*, how
that changed between years, and at what hours. The city publishes the
case-level prosecutor's files, the daily ridership per station and the GTFS
network, but as separate CSVs with no common key. This app joins them
spatially and lets a person, or a language model, ask the question directly.

## What you get

- **Heat map** of FGJ *carpetas de investigación* (2019 to Nov 2024) as
  hexagonal density at 250, 500 or 1000 m, over Metro, Metrobús, Tren Ligero,
  Cablebús, Trolebús and RTP lines and stations.
- **163 physical Metro stations** as graduated circles: cases within 300 m or
  500 m of every platform of the station, and **cases per million entries**
  over the same months. Pantitlán's four GTFS stops count as one station.
- **Colonia and alcaldía choropleths**, individual cases at street zoom, and
  a panel for any station or area with monthly series, category mix, top
  delitos and an hour by weekday grid.
- **Filters:** period, 16 official categories with a "solo alto impacto"
  preset, crimes against public-transport passengers by mode, hour range
  that wraps midnight, weekday, count versus rate, radius. Every filter is
  a deep link.
- **Chat** (a full page and a mini chat on the map): Gemini 2.5 Flash in a
  ReAct loop over 13 MCP tools such as `rank_stations`,
  `station_crime_stats`, `compare_periods`, `hotspots`, `time_profile`,
  `area_summary` and `victim_profile`. Answers state the data window and
  the caveats, show their reasoning trace, and highlight their results on
  the map.
- **Idempotent ingest** that runs in the background on first boot, hashes
  each input, and refreshes materialized views; the API answers 503
  "ingesting" and the frontend shows a banner until the views exist.

## Caveats the app carries into every answer

- Cases are **reported** crimes (denuncias), not incidence; the cifra negra
  is large and uneven across the city.
- About 6% of cases have no usable coordinates and are excluded from maps
  and station or colonia statistics.
- Station statistics count cases within a radius of all platforms of a
  station; neighbouring radii overlap, so one case can count for two
  stations. "Near the station", not "in the station": only delitos named
  *A BORDO DE METRO* are explicitly inside the system.
- A time of exactly 00:00 is a placeholder; hour profiles use only rows
  with a valid time and report the share they cover.
- *Delito de bajo impacto* is about 85% of everything; *hecho no delictivo*
  is excluded unless asked for.
- Víctimas and carpetas are separate tables with no common id.

## Data

All from the CDMX open-data portal (CC-BY-4.0): FGJ carpetas de
investigación (case level, Jan 2016 to Nov 2024, rows before 2019 dropped)
and víctimas (victim level, 2019 to mid 2024), STC Metro daily ridership per
station (2010 to 2026), the Oct 2022 GTFS static feed, and the colonias and
alcaldías boundaries. The 1 GB of inputs stay out of the repo; the portal
geo-blocks non-Mexican addresses, so the fetch script runs from Mexico or
over a Mexico VPN.

## Tech stack

| Layer | Tech |
|---|---|
| Database | Shared PostgreSQL 18 with PostGIS 3.6, unaccent, pg_trgm, btree_gist, pgcrypto; own database, role and schema |
| Backend | FastAPI, asyncpg, Alembic raw-SQL migrations, pandas chunked ingest, pre-aggregated materialized views with live-query fallback |
| Frontend | React 18, Vite 6, MapLibre GL 4 (heatmap, choropleths, graduated circles), inline-SVG charts, no chart library |
| Chat and AI | Gemini 2.5 Flash ReAct loop with thinking summaries, over a FastMCP server exposing 13 read-only tools that proxy the stats API |
| Deploy | Docker Compose, Traefik, read-only root filesystems, Docker secrets for the database password, the Gemini key and the MCP key |
| Tests | pytest on the pure parsing helpers (dates, coordinates, transport mode) and on the filter-to-SQL layer |

## License and attribution

Crime and ridership data: Gobierno de la Ciudad de México, Portal de Datos
Abiertos (CC-BY-4.0), FGJ CDMX, SEMOVI / STC Metro, ADIP, INEGI. Basemap
tiles: OpenStreetMap (ODbL) and ESRI World Imagery.
