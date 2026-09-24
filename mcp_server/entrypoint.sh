#!/bin/sh
set -e

# Docker secret: shared MCP API key. Required for the server to start.
MCP_KEY_FILE=/run/secrets/crime_mcp_api_key
if [ -f "$MCP_KEY_FILE" ]; then
    KEY=$(cat "$MCP_KEY_FILE")
    if [ -n "$KEY" ]; then
        export MCP_API_KEY="$KEY"
    fi
fi

if [ -z "$MCP_API_KEY" ]; then
    echo "FATAL: MCP_API_KEY is empty. Populate ./secrets/crime_mcp_api_key.txt with a random secret (e.g. openssl rand -hex 32) and recreate this container." >&2
    exit 1
fi

exec python server.py
