"""station radius join on indexed UTM geometry

The 006 definition cast crime_cases.geom to geography inside ST_DWithin, which
cannot use the GiST index and made the refresh a parallel scan of 1.4M rows
per station; a parallel worker was OOM-killed on an 8 GB host. crime_cases
already carries an indexed `geom_utm` (EPSG:32614, meters); give
metro_stations the matching `pts_utm` and join in planar meters (the
difference from geodesic distance is negligible at 300–500 m).

Revision ID: 009
Revises: 008
"""
from typing import Sequence, Union
from alembic import op


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE metro_stations ADD COLUMN IF NOT EXISTS pts_utm geometry(MultiPoint, 32614)")
    op.execute("UPDATE metro_stations SET pts_utm = ST_Transform(pts, 32614) WHERE pts_utm IS NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_metro_stations_pts_utm ON metro_stations USING GIST(pts_utm)")

    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_station_crime")
    op.execute("""
        CREATE MATERIALIZED VIEW mv_station_crime AS
        WITH radii AS (SELECT unnest(ARRAY[300, 500]) AS radius_m)
        SELECT ms.station_key, r.radius_m, c.ym, c.categoria_delito,
               c.is_transport_related, COALESCE(c.transport_mode, '') AS transport_mode,
               COUNT(*)::INT AS n_cases
        FROM metro_stations ms
        CROSS JOIN radii r
        JOIN crime_cases c
          ON c.geom_utm IS NOT NULL
         AND ST_DWithin(c.geom_utm, ms.pts_utm, r.radius_m)
        GROUP BY 1, 2, 3, 4, 5, 6
        WITH NO DATA
    """)
    op.execute("""
        CREATE UNIQUE INDEX ux_mv_station_crime ON mv_station_crime
            (station_key, radius_m, ym, categoria_delito, is_transport_related, transport_mode)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_metro_stations_pts_utm")
    op.execute("ALTER TABLE metro_stations DROP COLUMN IF EXISTS pts_utm")
