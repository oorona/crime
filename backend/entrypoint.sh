#!/bin/sh
set -e

# Docker secret: DB password
DB_PASS_FILE=/run/secrets/db_password
if [ -f "$DB_PASS_FILE" ]; then
    export POSTGRES_PASSWORD=$(cat "$DB_PASS_FILE")
fi

# Docker secret: Gemini API key (chat agent). Optional — chat is disabled if absent.
GEMINI_KEY_FILE=/run/secrets/gemini_api_key
if [ -f "$GEMINI_KEY_FILE" ]; then
    KEY=$(cat "$GEMINI_KEY_FILE")
    [ -n "$KEY" ] && export GEMINI_API_KEY="$KEY"
fi

# Docker secret: shared MCP API key (chat agent ↔ mcp_server).
MCP_KEY_FILE=/run/secrets/crime_mcp_api_key
if [ -f "$MCP_KEY_FILE" ]; then
    KEY=$(cat "$MCP_KEY_FILE")
    [ -n "$KEY" ] && export CRIME_MCP_API_KEY="$KEY"
fi

echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete."

exec uvicorn main:app --host 0.0.0.0 --port 8000
