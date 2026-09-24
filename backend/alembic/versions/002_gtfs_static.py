"""GTFS static tables (subset: no calendar / frequencies — the crime app only
needs geometry, names, and the stop→line mapping)

Revision ID: 002
Revises: 001
"""
from typing import Sequence, Union
from alembic import op


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE agencies (
            agency_id        TEXT PRIMARY KEY,
            agency_name      TEXT NOT NULL,
            agency_url       TEXT,
            agency_timezone  TEXT,
            agency_lang      TEXT
        )
    """)

    op.execute("""
        CREATE TABLE routes (
            route_id          TEXT PRIMARY KEY,
            agency_id         TEXT REFERENCES agencies(agency_id),
            route_short_name  TEXT,
            route_long_name   TEXT,
            route_type        INTEGER,
            route_color       TEXT,
            route_text_color  TEXT
        )
    """)
    op.execute("CREATE INDEX idx_routes_agency ON routes(agency_id)")

    op.execute("""
        CREATE TABLE stops (
            stop_id              TEXT PRIMARY KEY,
            stop_name            TEXT NOT NULL,
            stop_lat             DOUBLE PRECISION NOT NULL,
            stop_lon             DOUBLE PRECISION NOT NULL,
            zone_id              TEXT,
            wheelchair_boarding  SMALLINT,
            agency_id            TEXT,
            line_code            TEXT,
            geom                 geometry(Point, 4326),
            stop_name_norm       TEXT
        )
    """)
    op.execute("CREATE INDEX idx_stops_geom ON stops USING GIST(geom)")
    op.execute("CREATE INDEX idx_stops_agency ON stops(agency_id)")
    op.execute("CREATE INDEX idx_stops_line ON stops(agency_id, line_code)")
    op.execute("CREATE INDEX idx_stops_name_trgm ON stops USING GIN (stop_name_norm gin_trgm_ops)")

    op.execute("""
        CREATE TABLE trips (
            trip_id          TEXT PRIMARY KEY,
            route_id         TEXT REFERENCES routes(route_id),
            service_id       TEXT,
            shape_id         TEXT,
            trip_headsign    TEXT,
            trip_short_name  TEXT,
            direction_id     SMALLINT
        )
    """)
    op.execute("CREATE INDEX idx_trips_route ON trips(route_id)")
    op.execute("CREATE INDEX idx_trips_shape ON trips(shape_id)")

    # Needed for the stops.agency_id/line_code derivation and /api/lines/stops.
    op.execute("""
        CREATE TABLE stop_times (
            trip_id         TEXT NOT NULL,
            timepoint       SMALLINT,
            stop_id         TEXT NOT NULL,
            stop_sequence   INTEGER NOT NULL,
            arrival_time    TEXT,
            departure_time  TEXT,
            arrival_secs    INTEGER,
            departure_secs  INTEGER,
            PRIMARY KEY (trip_id, stop_sequence)
        )
    """)
    op.execute("CREATE INDEX idx_stop_times_stop ON stop_times(stop_id)")
    op.execute("CREATE INDEX idx_stop_times_trip ON stop_times(trip_id, stop_sequence)")

    op.execute("""
        CREATE TABLE shape_points (
            shape_id              TEXT NOT NULL,
            shape_pt_sequence     INTEGER NOT NULL,
            shape_pt_lat          DOUBLE PRECISION NOT NULL,
            shape_pt_lon          DOUBLE PRECISION NOT NULL,
            shape_dist_traveled   DOUBLE PRECISION,
            PRIMARY KEY (shape_id, shape_pt_sequence)
        )
    """)

    op.execute("""
        CREATE TABLE shape_lines (
            shape_id   TEXT PRIMARY KEY,
            route_id   TEXT,
            agency_id  TEXT,
            geom       geometry(LineString, 4326)
        )
    """)
    op.execute("CREATE INDEX idx_shape_lines_geom ON shape_lines USING GIST(geom)")
    op.execute("CREATE INDEX idx_shape_lines_route ON shape_lines(route_id)")
    op.execute("CREATE INDEX idx_shape_lines_agency ON shape_lines(agency_id)")


def downgrade() -> None:
    for tbl in ("shape_lines", "shape_points", "stop_times", "trips", "stops", "routes", "agencies"):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
