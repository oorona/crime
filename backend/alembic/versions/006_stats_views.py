"""statistics materialized views

Every MV is created WITH NO DATA and gets a UNIQUE index so it can be
refreshed CONCURRENTLY after the first population (services.ingest.refresh_views
probes pg_class.relispopulated to pick the right variant).

Revision ID: 006
Revises: 005
"""
from typing import Sequence, Union
from alembic import op


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# CDMX extent used for the hex grids (lon/lat, WGS84).
CDMX_BBOX = (-99.37, 19.05, -98.94, 19.60)


def upgrade() -> None:
    # ── Hex cells: static grid over the CDMX extent, built in UTM 14N so the
    # cell size is true meters, then stored in both SRIDs. Refreshed once
    # (before crime ingest, which assigns each case its cell ids).
    op.execute(f"""
        CREATE MATERIALIZED VIEW mv_hex_cells AS
        WITH ext AS (
            SELECT ST_Transform(ST_SetSRID(ST_MakeEnvelope({CDMX_BBOX[0]}, {CDMX_BBOX[1]},
                                                         {CDMX_BBOX[2]}, {CDMX_BBOX[3]}), 4326), 32614) AS g
        ),
        res AS (SELECT unnest(ARRAY[250, 500, 1000]) AS res_m)
        SELECT res.res_m, h.i, h.j,
               h.geom                                   AS geom_utm,
               ST_Transform(h.geom, 4326)               AS geom,
               ST_Transform(ST_Centroid(h.geom), 4326)  AS centroid
        FROM res, ext, LATERAL ST_HexagonGrid(res.res_m, ext.g) AS h
        WITH NO DATA
    """)
    op.execute("CREATE UNIQUE INDEX ux_mv_hex_cells ON mv_hex_cells (res_m, i, j)")
    op.execute("CREATE INDEX idx_mv_hex_cells_geom ON mv_hex_cells USING GIST(geom)")

    # ── Cases per hex cell / month / category (all three resolutions).
    op.execute("""
        CREATE MATERIALIZED VIEW mv_hex_crime AS
        SELECT 250 AS res_m, hex250_i AS i, hex250_j AS j, ym, categoria_delito, is_transport_related,
               COUNT(*)::INT AS n_cases
        FROM crime_cases WHERE hex250_i IS NOT NULL
        GROUP BY 2, 3, 4, 5, 6
        UNION ALL
        SELECT 500, hex500_i, hex500_j, ym, categoria_delito, is_transport_related, COUNT(*)::INT
        FROM crime_cases WHERE hex500_i IS NOT NULL
        GROUP BY 2, 3, 4, 5, 6
        UNION ALL
        SELECT 1000, hex1000_i, hex1000_j, ym, categoria_delito, is_transport_related, COUNT(*)::INT
        FROM crime_cases WHERE hex1000_i IS NOT NULL
        GROUP BY 2, 3, 4, 5, 6
        WITH NO DATA
    """)
    op.execute("CREATE UNIQUE INDEX ux_mv_hex_crime ON mv_hex_crime (res_m, i, j, ym, categoria_delito, is_transport_related)")
    op.execute("CREATE INDEX idx_mv_hex_crime_res_ym ON mv_hex_crime (res_m, ym)")

    # ── Station radius join. One row per station cluster × radius × month ×
    # category. ST_DWithin against the MultiPoint of all platforms counts a
    # case once per station. Radii of neighbouring stations overlap (Hidalgo /
    # Bellas Artes) — by design; data_coverage states it as a caveat.
    op.execute("""
        CREATE MATERIALIZED VIEW mv_station_crime AS
        WITH radii AS (SELECT unnest(ARRAY[300, 500]) AS radius_m)
        SELECT ms.station_key, r.radius_m, c.ym, c.categoria_delito,
               c.is_transport_related, COALESCE(c.transport_mode, '') AS transport_mode,
               COUNT(*)::INT AS n_cases
        FROM metro_stations ms
        CROSS JOIN radii r
        JOIN crime_cases c
          ON c.geom IS NOT NULL
         AND ST_DWithin(ms.pts::geography, c.geom::geography, r.radius_m)
        GROUP BY 1, 2, 3, 4, 5, 6
        WITH NO DATA
    """)
    op.execute("""
        CREATE UNIQUE INDEX ux_mv_station_crime ON mv_station_crime
            (station_key, radius_m, ym, categoria_delito, is_transport_related, transport_mode)
    """)

    # ── Monthly entries per station cluster (sums every platform of a station).
    op.execute("""
        CREATE MATERIALIZED VIEW mv_station_ridership_monthly AS
        SELECT ms.station_key,
               (EXTRACT(YEAR FROM r.date) * 100 + EXTRACT(MONTH FROM r.date))::INT AS ym,
               SUM(r.count)::BIGINT AS entries,
               COUNT(DISTINCT r.date)::INT AS days
        FROM ridership_metro_station_daily r
        JOIN stops s ON s.stop_id = r.stop_id
        JOIN metro_stations ms ON ms.station_key = s.stop_name_norm
        GROUP BY 1, 2
        WITH NO DATA
    """)
    op.execute("CREATE UNIQUE INDEX ux_mv_station_ridership ON mv_station_ridership_monthly (station_key, ym)")

    # ── Colonia × month × category.
    op.execute("""
        CREATE MATERIALIZED VIEW mv_colonia_crime_monthly AS
        SELECT colonia_id, ym, categoria_delito, is_transport_related, COUNT(*)::INT AS n_cases
        FROM crime_cases
        WHERE colonia_id IS NOT NULL
        GROUP BY 1, 2, 3, 4
        WITH NO DATA
    """)
    op.execute("CREATE UNIQUE INDEX ux_mv_colonia_crime ON mv_colonia_crime_monthly (colonia_id, ym, categoria_delito, is_transport_related)")

    # ── Daily cube for trends, summaries, alcaldía comparisons. Hour/weekday
    # profiles run live on crime_cases (they need hora_ok and station radii).
    op.execute("""
        CREATE MATERIALIZED VIEW mv_crime_daily AS
        SELECT fecha_hecho::date AS day, alcaldia_id, categoria_delito,
               is_transport_related, COALESCE(transport_mode, '') AS transport_mode,
               COUNT(*)::INT AS n_cases
        FROM crime_cases
        GROUP BY 1, 2, 3, 4, 5
        WITH NO DATA
    """)
    op.execute("CREATE UNIQUE INDEX ux_mv_crime_daily ON mv_crime_daily (day, COALESCE(alcaldia_id, 0), categoria_delito, is_transport_related, transport_mode)")
    op.execute("CREATE INDEX idx_mv_crime_daily_day ON mv_crime_daily (day)")

    # ── Coverage summary for the UI banner and the LLM's data_coverage tool.
    op.execute("""
        CREATE OR REPLACE VIEW v_coverage AS
        SELECT
            (SELECT COUNT(*)            FROM crime_cases)                        AS cases_rows,
            (SELECT MIN(fecha_hecho)    FROM crime_cases)                        AS cases_from,
            (SELECT MAX(fecha_hecho)    FROM crime_cases)                        AS cases_to,
            (SELECT COUNT(*)            FROM crime_cases WHERE geom IS NULL)     AS cases_no_geom,
            (SELECT COUNT(*)            FROM crime_cases WHERE hora_ok)          AS cases_hora_ok,
            (SELECT COUNT(*)            FROM crime_victims)                      AS victims_rows,
            (SELECT MIN(fecha_hecho)    FROM crime_victims)                      AS victims_from,
            (SELECT MAX(fecha_hecho)    FROM crime_victims)                      AS victims_to,
            (SELECT MIN(date)           FROM ridership_metro_station_daily)      AS ridership_from,
            (SELECT MAX(date)           FROM ridership_metro_station_daily)      AS ridership_to,
            (SELECT COUNT(*)            FROM metro_stations)                     AS stations,
            (SELECT COUNT(*)            FROM colonias)                           AS colonias,
            (SELECT MAX(ran_at)         FROM data_ingest_runs)                   AS ingested_at
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_coverage")
    for mv in ("mv_crime_daily", "mv_colonia_crime_monthly", "mv_station_ridership_monthly",
               "mv_station_crime", "mv_hex_crime", "mv_hex_cells"):
        op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {mv}")
