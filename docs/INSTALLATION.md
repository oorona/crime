# Installation

## Prerequisites

Docker Compose v2; the shared `postgres` container (PostgreSQL 18 + PostGIS,
from `infra/database`) up on `dbnet`; the external networks `internet`,
`intranet` and `dbnet` created; a Mexico VPN for the data download. The
portal geo-blocks non-Mexican IPs: a refused connection or a 403 on the
first request is the block, not a bad URL.

## Quick start

```sh
cp .env.example .env                      # local dev values are already right
./scripts/db-setup.sh                     # creates cdmx_crime + crime_user, writes secrets/db_password.txt
cp ../metro/secrets/gemini_api_key.txt secrets/   # or paste your own key
openssl rand -hex 32 > secrets/crime_mcp_api_key.txt
./scripts/fetch_data.sh                   # ~1 GB; needs the Mexico VPN
docker compose up -d --build
docker logs -f cdmx-crime-backend         # watch the ingest
```

`secrets/` holds `db_password.txt`, `gemini_api_key.txt` and
`crime_mcp_api_key.txt`, mounted as Docker secrets. Empty key files are
allowed: `/api/chat/stream` then returns 503 and everything else works.
`APP_UID` / `APP_GID` in `.env` must match the owner of `secrets/*.txt`.

First boot ingests in the background: GTFS about 10 s, boundaries 5 s,
ridership 1 min, cases 5 to 10 min, víctimas 5 min, view refresh 2 min. The
API is up immediately; `/health` shows the step in progress and
`views_populated`; the crime endpoints answer 503 `{"error":"ingesting"}`
until the views exist, and the frontend shows a banner. Re-runs are
idempotent (SHA-256 of each input in `data_ingest_runs`).

Open <http://localhost:5174>. The gitignored `docker-compose.override.yml`
publishes the frontend on 5174 and the backend on 8001; the base compose
file exposes nothing on the host, Traefik reaches the containers over the
docker networks.

## Environment

`.env.example` documents every key: container names (unique on the shared
intranet), Traefik hosts and cert resolver, database name, role, host and
schema, `ALLOWED_ORIGINS`, `INGEST_ON_BOOT` (1 runs the idempotent ingest on
every boot, 0 never), `CRIME_GEMINI_MODEL`, the internal MCP and backend
URLs, and `MCP_LOG_LEVEL`.

## Data

`scripts/fetch_data.sh` downloads all inputs and writes
`data/CHECKSUMS.txt`. `data/` and `boundaries/` are gitignored; `gtfs/*.txt`
is tracked.

| Dataset | File | Coverage |
|---|---|---|
| FGJ carpetas de investigación | `data/carpetasFGJ_acumulado_2025_01.csv` (560 MB) | Jan 2016 to Nov 2024; rows before 2019 dropped at ingest |
| FGJ víctimas | `data/victimasFGJ_acumulado_2024_09.csv` (373 MB) | Jan 2019 to about May 2024 |
| STC Metro afluencia diaria | `data/afluencia_metro_simple.csv` (60 MB) | 2010 to Jul 2026; 2019 on kept |
| GTFS static | `gtfs/*.txt` | Oct 2022 feed, identical to metro's |
| Colonias, alcaldías | `boundaries/colonias.json`, `boundaries/alcaldias.json` | current |

As of Sep 2026 the portal publishes no 2025 or 2026 crime file despite
claiming monthly updates. When one appears, drop it in `data/` (the loaders
glob `carpetasFGJ_acumulado_*.csv` and take the newest name), run
`./scripts/fetch_data.sh --force`, and restart the backend: the hash
changes, so the loader re-runs and refreshes the views.

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

## Tests

```sh
docker compose exec backend python -m pytest -q -p no:cacheprovider tests
```

The root filesystem is read-only, hence no cache. 50 tests cover the parsing
helpers and the filter layer.

## Day to day

```sh
docker logs -f cdmx-crime-backend
docker compose up -d --build backend                    # after editing backend code
docker compose exec backend python -m services.ingest --only crime_cases --force   # reload one source
docker compose exec backend python -m services.ingest --force                      # reload everything
docker exec postgres psql -U postgres -d cdmx_crime -c "TRUNCATE crime_user.data_ingest_runs;"  # forget hashes
```

## Deploy (test and prod)

Same convention as metro: `.env.test` and `.env.prod` carry unique
container names (`cdmx-crime-test-*`), hosts (`crime.home.iktdts.com`,
`crimemcp.home.iktdts.com`) and Traefik router names (`crime-frontend`,
`crimemcp`); `secrets.test/` and `secrets.prod/` are renamed to `secrets/`
on the target by the infra deploy scripts. The data directories are not
synced by git: run `scripts/fetch_data.sh` on the target (VPN) or rsync
`data/` and `boundaries/`.
