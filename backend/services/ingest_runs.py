"""Idempotent bookkeeping for ingestion sources.

Each loader hashes its source file (or set of files) and records the result
in `data_ingest_runs`. On the next boot the loader can compare the new hash
to the recorded one and skip the work entirely if nothing changed.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Iterable


def hash_files(paths: Iterable[Path]) -> str:
    """SHA-256 over the concatenated bytes of the given files (in iteration order)."""
    h = hashlib.sha256()
    for p in paths:
        h.update(str(p).encode())
        h.update(b"\0")
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


async def already_ran(conn, source_name: str, content_hash: str) -> bool:
    row = await conn.fetchrow(
        "SELECT content_hash FROM data_ingest_runs WHERE source_name = $1",
        source_name,
    )
    return row is not None and row["content_hash"] == content_hash


async def record_run(conn, source_name: str, content_hash: str, row_count: int) -> None:
    await conn.execute(
        """
        INSERT INTO data_ingest_runs (source_name, content_hash, row_count, ran_at)
        VALUES ($1, $2, $3, now())
        ON CONFLICT (source_name) DO UPDATE
            SET content_hash = EXCLUDED.content_hash,
                row_count = EXCLUDED.row_count,
                ran_at = EXCLUDED.ran_at
        """,
        source_name,
        content_hash,
        row_count,
    )
