#!/usr/bin/env bash
# ── CDMX Crime GIS — Database Setup ──────────────────────────────────────
# Creates the cdmx_crime database, the crime_user app role, the crime_user
# schema, and the GIS extensions on top of the SHARED PostgreSQL container at
# /home/iktdts/apps/infra/database (container name: `postgres`).
#
# Inputs:
#   - SUPERUSER password    /home/iktdts/apps/infra/database/secrets/postgres_password.txt
#   - APP-USER password     ./secrets/db_password.txt   (generated here if absent)
#
# Idempotent: re-running the script re-syncs the role password and re-issues
# CREATE EXTENSION IF NOT EXISTS for every required extension.
#
# Prerequisite: the shared postgres image must already include PostGIS
# (rebuilt via /home/iktdts/apps/infra/database/Dockerfile + a
# `docker compose build postgres` + restart). If it doesn't, this script
# fails at the CREATE EXTENSION step with a pointer to that Dockerfile.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Constants ────────────────────────────────────────────────────────────────
DB_NAME="cdmx_crime"
APP_USER="crime_user"
APP_SCHEMA="crime_user"
PG_CONTAINER="postgres"
PG_ADMIN="postgres"
INFRA_SECRET="/home/iktdts/apps/infra/database/secrets/postgres_password.txt"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_SECRETS_DIR="$PROJECT_DIR/secrets"
APP_PASS_FILE="$APP_SECRETS_DIR/db_password.txt"

info()  { echo "  ▸ $*"; }
ok()    { echo "  ✓ $*"; }
warn()  { echo "  ⚠  $*" >&2; }
die()   { echo "  ✗ $*" >&2; exit 1; }

echo ""
echo "══════════════════════════════════════════════"
echo "  CDMX Crime GIS — DB Setup (shared)"
echo "══════════════════════════════════════════════"
echo "  Target container : $PG_CONTAINER"
echo "  Database         : $DB_NAME"
echo "  App role         : $APP_USER  (schema: $APP_SCHEMA)"
echo "══════════════════════════════════════════════"
echo ""

# ── Verify the shared postgres container is running ─────────────────────────
if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    die "container '$PG_CONTAINER' is not running. Start it first:
        cd /home/iktdts/apps/infra/database && docker compose up -d"
fi

# ── Read the SUPERUSER password from the shared infra secret ────────────────
if [[ ! -r "$INFRA_SECRET" ]]; then
    die "cannot read shared superuser secret at $INFRA_SECRET
        (expected to be readable by your user; chmod 600 owner=you)"
fi
SUPER_PASS="$(cat "$INFRA_SECRET")"

# ── Sanity-check connectivity (peer/exec, no password needed inside container) ─
if ! docker exec "$PG_CONTAINER" pg_isready -U "$PG_ADMIN" >/dev/null 2>&1; then
    die "pg_isready failed inside '$PG_CONTAINER' — is postgres still booting?"
fi
ok "Shared postgres is up"

# Helper: run psql inside the container with PGPASSWORD set
psql_admin() {
    docker exec -i -e PGPASSWORD="$SUPER_PASS" "$PG_CONTAINER" \
        psql -U "$PG_ADMIN" -v ON_ERROR_STOP=1 "$@"
}

# ── Ensure the APP-USER password file exists (mode 600) ─────────────────────
mkdir -p "$APP_SECRETS_DIR"
chmod 700 "$APP_SECRETS_DIR"
if [[ -f "$APP_PASS_FILE" && -s "$APP_PASS_FILE" ]]; then
    info "Reusing existing app password from $APP_PASS_FILE"
else
    APP_PASS=$(openssl rand -base64 32 | tr -d '/+=\n' | head -c 32)
    printf '%s' "$APP_PASS" > "$APP_PASS_FILE"
    chmod 600 "$APP_PASS_FILE"
    ok "Generated new app password → $APP_PASS_FILE (mode 600)"
fi
APP_PASS="$(cat "$APP_PASS_FILE")"

# ── Create database ──────────────────────────────────────────────────────────
info "Ensuring database '$DB_NAME' exists..."
psql_admin -d postgres <<SQL
SELECT 'CREATE DATABASE "$DB_NAME"'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')
\gexec
SQL
ok "Database '$DB_NAME' ready"

# ── Create / sync the app role ──────────────────────────────────────────────
info "Ensuring role '$APP_USER' exists and password is in sync..."
psql_admin -d postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$APP_USER') THEN
    CREATE ROLE "$APP_USER" LOGIN PASSWORD '$APP_PASS';
    RAISE NOTICE 'Role $APP_USER created.';
  ELSE
    ALTER ROLE "$APP_USER" LOGIN PASSWORD '$APP_PASS';
    RAISE NOTICE 'Role $APP_USER exists — password synced.';
  END IF;
END;
\$\$;

GRANT ALL PRIVILEGES ON DATABASE "$DB_NAME" TO "$APP_USER";
SQL
ok "Role '$APP_USER' ready"

# ── Extensions on the cdmx_crime database (superuser only) ────────────────
info "Enabling extensions on '$DB_NAME'..."
if ! psql_admin -d "$DB_NAME" <<'EXTSQL'
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gist;
EXTSQL
then
    die "extension install failed.
        The shared image does not provide one of: postgis.
        Rebuild it from /home/iktdts/apps/infra/database/Dockerfile
        (it should apt-install postgresql-18-postgis-3
        + postgresql-18-pgvector) then restart the postgres container."
fi
ok "Extensions installed on '$DB_NAME'"

# ── App schema (owned by app user, not public) ──────────────────────────────
info "Creating schema '$APP_SCHEMA' owned by '$APP_USER'..."
psql_admin -d "$DB_NAME" <<SQL
CREATE SCHEMA IF NOT EXISTS "$APP_SCHEMA" AUTHORIZATION "$APP_USER";
GRANT ALL ON SCHEMA "$APP_SCHEMA" TO "$APP_USER";
GRANT USAGE ON SCHEMA public TO "$APP_USER";
ALTER ROLE "$APP_USER" SET search_path TO "$APP_SCHEMA", public;
SQL
ok "Schema '$APP_SCHEMA' ready (search_path set)"

# ── Verify ───────────────────────────────────────────────────────────────────
echo ""
echo "  Extensions registered on '$DB_NAME':"
psql_admin -d "$DB_NAME" -c \
    "SELECT extname, extversion FROM pg_extension
     WHERE extname IN ('postgis','unaccent','pg_trgm','btree_gist','pgcrypto','vector','pg_textsearch')
     ORDER BY extname;" \
    2>/dev/null || true

echo ""
echo "══════════════════════════════════════════════"
echo "  Setup complete."
echo "══════════════════════════════════════════════"
echo "  Container : $PG_CONTAINER  (shared infra)"
echo "  Database  : $DB_NAME"
echo "  Schema    : $APP_SCHEMA"
echo "  App pass  : $APP_PASS_FILE"
echo ""
echo "  Now fetch the data (on the Mexico VPN) and bring up the crime stack:"
echo "    cd $PROJECT_DIR && ./scripts/fetch_data.sh && docker compose up -d --build"
echo ""
exit 0
