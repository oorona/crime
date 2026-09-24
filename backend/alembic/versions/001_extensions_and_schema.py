"""extensions and bookkeeping tables

Revision ID: 001
Revises:
"""
from typing import Sequence, Union
from alembic import op


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Defensive: extensions were already installed by db-setup.sh, but
    # `alembic upgrade head` may also be invoked against a fresh DB without it.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute("""
        CREATE TABLE IF NOT EXISTS data_ingest_runs (
            id SERIAL PRIMARY KEY,
            source_name TEXT UNIQUE NOT NULL,
            content_hash TEXT NOT NULL,
            row_count INTEGER NOT NULL DEFAULT 0,
            ran_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS data_ingest_runs")
