"""crime tables: metro_stations (name clusters), crime_cases, crime_victims

Revision ID: 005
Revises: 004
"""
from typing import Sequence, Union
from alembic import op


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Columns shared by crime_cases and crime_victims. Times are naive local
# CDMX wall-clock (the FGJ files carry no offset); hour-of-day analysis must
# see local hours, and a TIMESTAMPTZ would be shifted to UTC by asyncpg.
_COMMON_COLS = """
    id                    BIGSERIAL PRIMARY KEY,
    fecha_hecho           TIMESTAMP NOT NULL,
    fecha_inicio          TIMESTAMP,
    hora_ok               BOOLEAN NOT NULL DEFAULT false,
    delito                TEXT NOT NULL,
    categoria_delito      TEXT NOT NULL,
    competencia           TEXT,
    colonia_hecho         TEXT,
    colonia_catalogo      TEXT,
    alcaldia_hecho        TEXT,
    alcaldia_catalogo     TEXT,
    municipio_hecho       TEXT,
    lat                   DOUBLE PRECISION,
    lon                   DOUBLE PRECISION,
    geom                  geometry(Point, 4326),
    geom_utm              geometry(Point, 32614),
    year                  SMALLINT NOT NULL,
    month                 SMALLINT NOT NULL,
    ym                    INTEGER  NOT NULL,      -- year*100+month, for cheap range filters
    dow                   SMALLINT NOT NULL,      -- ISO: 1=Mon … 7=Sun
    hour                  SMALLINT,               -- NULL unless hora_ok
    is_transport_related  BOOLEAN NOT NULL DEFAULT false,
    transport_mode        TEXT,
    alcaldia_id           INTEGER REFERENCES alcaldias(id),
    colonia_id            INTEGER REFERENCES colonias(id),
    nearest_station_key   TEXT,
    nearest_station_m     REAL,
    hex250_i INTEGER, hex250_j INTEGER,
    hex500_i INTEGER, hex500_j INTEGER,
    hex1000_i INTEGER, hex1000_j INTEGER,
    source_row            BIGINT NOT NULL
"""


def _indexes(tbl: str) -> list[str]:
    p = tbl.replace("crime_", "c")  # ccases / cvictims
    return [
        f"CREATE INDEX idx_{p}_geom ON {tbl} USING GIST(geom)",
        f"CREATE INDEX idx_{p}_geom_utm ON {tbl} USING GIST(geom_utm)",
        f"CREATE INDEX idx_{p}_fecha ON {tbl} (fecha_hecho)",
        f"CREATE INDEX idx_{p}_ym ON {tbl} (ym)",
        f"CREATE INDEX idx_{p}_cat ON {tbl} (categoria_delito)",
        f"CREATE INDEX idx_{p}_alc ON {tbl} (alcaldia_id)",
        f"CREATE INDEX idx_{p}_col ON {tbl} (colonia_id)",
        f"CREATE INDEX idx_{p}_station ON {tbl} (nearest_station_key)",
        f"CREATE INDEX idx_{p}_transport ON {tbl} (transport_mode) WHERE is_transport_related",
    ]


def upgrade() -> None:
    # One row per PHYSICAL Metro station. GTFS models each line's platform as
    # its own stop_id (Pantitlán = 4 stops up to ~300 m apart); grouping by
    # the normalized name gives 163 stations. `pts` keeps every platform so a
    # radius query counts a crime once per station, whichever platform is
    # closest; `geom` is the centroid used for map circles.
    op.execute("""
        CREATE TABLE metro_stations (
            station_key   TEXT PRIMARY KEY,
            station_name  TEXT NOT NULL,
            stop_ids      TEXT[] NOT NULL,
            lines         TEXT[] NOT NULL,
            geom          geometry(Point, 4326) NOT NULL,
            pts           geometry(MultiPoint, 4326) NOT NULL
        )
    """)
    op.execute("CREATE INDEX idx_metro_stations_geom ON metro_stations USING GIST(geom)")
    op.execute("CREATE INDEX idx_metro_stations_pts ON metro_stations USING GIST(pts)")

    op.execute(f"""
        CREATE TABLE crime_cases (
            {_COMMON_COLS},
            fiscalia              TEXT,
            agencia               TEXT,
            unidad_investigacion  TEXT
        )
    """)
    for sql in _indexes("crime_cases"):
        op.execute(sql)

    op.execute(f"""
        CREATE TABLE crime_victims (
            {_COMMON_COLS},
            sexo              TEXT,
            edad              SMALLINT,
            tipo_persona      TEXT,
            calidad_juridica  TEXT
        )
    """)
    for sql in _indexes("crime_victims"):
        op.execute(sql)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS crime_victims")
    op.execute("DROP TABLE IF EXISTS crime_cases")
    op.execute("DROP TABLE IF EXISTS metro_stations")
