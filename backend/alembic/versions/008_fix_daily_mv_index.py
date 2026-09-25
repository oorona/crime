"""mv_crime_daily: unique index on plain columns so REFRESH CONCURRENTLY works

The 006 index used COALESCE(alcaldia_id, 0), which Postgres rejects for
concurrent refresh ("unique index with no WHERE clause on one or more
columns"). Rebuild the view with a NOT NULL `alc_key` column instead.

Revision ID: 008
Revises: 007
"""
from typing import Sequence, Union
from alembic import op


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_crime_daily")
    op.execute("""
        CREATE MATERIALIZED VIEW mv_crime_daily AS
        SELECT fecha_hecho::date AS day,
               alcaldia_id,
               COALESCE(alcaldia_id, 0) AS alc_key,
               categoria_delito,
               is_transport_related,
               COALESCE(transport_mode, '') AS transport_mode,
               COUNT(*)::INT AS n_cases
        FROM crime_cases
        GROUP BY 1, 2, 3, 4, 5, 6
        WITH NO DATA
    """)
    op.execute("CREATE UNIQUE INDEX ux_mv_crime_daily ON mv_crime_daily (day, alc_key, categoria_delito, is_transport_related, transport_mode)")
    op.execute("CREATE INDEX idx_mv_crime_daily_day ON mv_crime_daily (day)")
    op.execute("CREATE INDEX idx_mv_crime_daily_alc ON mv_crime_daily (alcaldia_id, day)")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_crime_daily")
