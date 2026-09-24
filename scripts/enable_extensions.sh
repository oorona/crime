#!/usr/bin/env bash
# enable_extensions.sh — Idempotent verifier/installer of the GIS extensions on
# the shared PostgreSQL container's `cdmx_crime` database. Useful after a
# DB restore or when pointing this app at a fresh shared instance.
#
# REQUIRED: postgis                          (hard-fail if missing)
# OPTIONAL: unaccent, pg_trgm, btree_gist, pgcrypto (warn if missing)
#
# Prerequisite: the shared image at /home/iktdts/apps/infra/database/Dockerfile
# must already provide PostGIS + pgRouting at the OS level. If a CREATE
# EXTENSION fails because the .so isn't on disk, rebuild that image and
# restart the postgres container.
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-postgres}"
ADMIN_USER="${ADMIN_USER:-postgres}"
TARGET_DB="${TARGET_DB:-cdmx_crime}"
INFRA_SECRET="${INFRA_SECRET:-/home/iktdts/apps/infra/database/secrets/postgres_password.txt}"

REQUIRED_EXTENSIONS=(postgis)
OPTIONAL_EXTENSIONS=(unaccent pg_trgm btree_gist pgcrypto)

if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    echo "ERROR: container '$PG_CONTAINER' is not running" >&2
    echo "Start it: cd /home/iktdts/apps/infra/database && docker compose up -d" >&2
    exit 1
fi

if [[ ! -r "$INFRA_SECRET" ]]; then
    echo "ERROR: cannot read superuser secret at $INFRA_SECRET" >&2
    exit 1
fi
SUPER_PASS="$(cat "$INFRA_SECRET")"

psql_admin() {
    docker exec -i -e PGPASSWORD="$SUPER_PASS" "$PG_CONTAINER" \
        psql -U "$ADMIN_USER" "$@"
}

echo "==> Ensuring required extensions on '$TARGET_DB'…"
for ext in "${REQUIRED_EXTENSIONS[@]}"; do
    echo "  CREATE EXTENSION IF NOT EXISTS $ext"
    if ! psql_admin -v ON_ERROR_STOP=1 -d "$TARGET_DB" \
            -c "CREATE EXTENSION IF NOT EXISTS $ext;"; then
        echo "" >&2
        echo "ERROR: required extension '$ext' is not available in the image." >&2
        echo "       Rebuild /home/iktdts/apps/infra/database/Dockerfile so it" >&2
        echo "       apt-installs postgresql-18-postgis-3," >&2
        echo "       then 'docker compose build postgres && docker compose up -d'." >&2
        exit 1
    fi
done

echo "==> Ensuring optional extensions (logged but never block)…"
for ext in "${OPTIONAL_EXTENSIONS[@]}"; do
    echo "  CREATE EXTENSION IF NOT EXISTS $ext (optional)"
    psql_admin -d "$TARGET_DB" <<SQL
DO \$\$
BEGIN
  CREATE EXTENSION IF NOT EXISTS $ext;
  RAISE NOTICE '$ext enabled.';
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE '$ext not available (skipped).';
END;
\$\$;
SQL
done

echo "==> Currently registered extensions on '$TARGET_DB':"
psql_admin -d "$TARGET_DB" <<SQL
SELECT e.extname, n.nspname AS schema, e.extversion
FROM pg_extension e JOIN pg_namespace n ON e.extnamespace = n.oid
WHERE e.extname IN ('postgis','pg_trgm','unaccent','btree_gist','pgcrypto','vector','pg_textsearch')
ORDER BY e.extname;
SQL

required_count=${#REQUIRED_EXTENSIONS[@]}
in_clause=$(printf "'%s'," "${REQUIRED_EXTENSIONS[@]}" | sed 's/,$//')
found=$(docker exec -i -e PGPASSWORD="$SUPER_PASS" "$PG_CONTAINER" \
        psql -tA -U "$ADMIN_USER" -d "$TARGET_DB" \
        -c "SELECT count(*) FROM pg_extension WHERE extname IN ($in_clause);")

if [ "$found" != "$required_count" ]; then
    echo "ERROR: expected $required_count required extensions registered, found $found" >&2
    exit 1
fi

echo "==> All required extensions present on '$TARGET_DB'."
