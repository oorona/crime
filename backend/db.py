"""asyncpg pool factory.

Mirrors the latent pattern: a single pool stored on `app.state.db`, with a
`init` callback that sets `search_path` to the app schema on each connection.
"""
from __future__ import annotations
import os

import asyncpg


def _password() -> str | None:
    """POSTGRES_PASSWORD is exported by entrypoint.sh; a `docker compose exec`
    shell does not inherit it, so fall back to the Docker secret file."""
    pw = os.getenv("POSTGRES_PASSWORD")
    if pw:
        return pw
    try:
        return open("/run/secrets/db_password").read().strip()
    except FileNotFoundError:
        return None


async def create_pool() -> asyncpg.Pool:
    pg_user = os.getenv("POSTGRES_USER", "postgres")
    pg_schema = os.getenv("POSTGRES_SCHEMA", pg_user)

    async def _init_conn(conn):
        await conn.execute(f"SET search_path TO {pg_schema}, public")

    return await asyncpg.create_pool(
        user=pg_user,
        password=_password(),
        database=os.getenv("POSTGRES_DB", "cdmx_crime"),
        host=os.getenv("POSTGRES_HOST", "postgres"),
        init=_init_conn,
        min_size=1,
        max_size=10,
    )
