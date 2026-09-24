"""administrative boundaries: alcaldías (INEGI) + colonias (catálogo de datos abiertos)

Revision ID: 003
Revises: 002
"""
from typing import Sequence, Union
from alembic import op


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE alcaldias (
            id           SERIAL PRIMARY KEY,
            cvegeo       TEXT UNIQUE,
            cve_mun      TEXT,
            nomgeo       TEXT NOT NULL,
            nomgeo_norm  TEXT NOT NULL,
            geom         geometry(MultiPolygon, 4326) NOT NULL,
            area_km2     DOUBLE PRECISION
        )
    """)
    op.execute("CREATE INDEX idx_alcaldias_geom ON alcaldias USING GIST(geom)")
    op.execute("CREATE INDEX idx_alcaldias_norm ON alcaldias(nomgeo_norm)")

    # cve_col is NOT unique in the catalog (repeated codes across alcaldías),
    # so `id` is the FK target and (alc_norm, colonia_norm) the lookup key.
    op.execute("""
        CREATE TABLE colonias (
            id            SERIAL PRIMARY KEY,
            cve_col       TEXT,
            colonia       TEXT NOT NULL,
            colonia_norm  TEXT NOT NULL,
            cve_alc       TEXT,
            alc           TEXT,
            alc_norm      TEXT,
            clasif        TEXT,
            geom          geometry(MultiPolygon, 4326) NOT NULL,
            area_km2      DOUBLE PRECISION
        )
    """)
    op.execute("CREATE INDEX idx_colonias_geom ON colonias USING GIST(geom)")
    op.execute("CREATE INDEX idx_colonias_norm ON colonias(alc_norm, colonia_norm)")
    op.execute("CREATE INDEX idx_colonias_trgm ON colonias USING GIN (colonia_norm gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS colonias")
    op.execute("DROP TABLE IF EXISTS alcaldias")
