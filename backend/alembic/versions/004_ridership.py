"""Metro daily ridership per station (SEMOVI "afluencia simple")

Revision ID: 004
Revises: 003
"""
from typing import Sequence, Union
from alembic import op


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE ridership_metro_station_daily (
            date                DATE NOT NULL,
            line                TEXT NOT NULL,
            station_name        TEXT NOT NULL,
            station_name_norm   TEXT NOT NULL,
            count               INTEGER NOT NULL,
            stop_id             TEXT,
            PRIMARY KEY (date, line, station_name)
        )
    """)
    op.execute("CREATE INDEX idx_rmsd_stop_date ON ridership_metro_station_daily(stop_id, date)")
    op.execute("CREATE INDEX idx_rmsd_norm_date ON ridership_metro_station_daily(station_name_norm, date)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ridership_metro_station_daily")
