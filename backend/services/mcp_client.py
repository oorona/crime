"""Thin wrapper around fastmcp.Client for the metro MCP server.

Used by the chat agent to discover tools and dispatch calls. Each
session opens a streamable-HTTP connection to the MCP server with the
shared API key in the X-API-Key header. Use as an async context manager
so the underlying connection is cleaned up when the request ends.
"""
from __future__ import annotations

import logging
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

logger = logging.getLogger("metro.mcp_client")


def _normalize_mcp_url(url: str) -> str:
    """Ensure the URL ends with the streamable-http MCP endpoint path
    (`/mcp/`) regardless of how the operator wrote it in env."""
    u = url.rstrip("/")
    if u.endswith("/mcp"):
        return u + "/"
    if "/mcp/" in u + "/":
        return u + "/" if not u.endswith("/") else u
    return u + "/mcp/"


class MetroMCPSession:
    def __init__(self, url: str, api_key: str):
        transport = StreamableHttpTransport(
            url=_normalize_mcp_url(url),
            headers={"X-API-Key": api_key},
        )
        self._client = Client(transport)

    async def __aenter__(self) -> "MetroMCPSession":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._client.__aexit__(exc_type, exc, tb)

    async def list_tools(self) -> list[Any]:
        return await self._client.list_tools()

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        return await self._client.call_tool(name, args)


_GEMINI_SCALAR_KEYS = {
    "type", "description", "enum", "format", "nullable",
    "minimum", "maximum", "minLength", "maxLength",
    "minItems", "maxItems", "pattern",
}


def to_gemini_schema(schema: Any) -> Any:
    """Convert a JSON Schema (as emitted by pydantic via fastmcp) into the
    restricted subset that Gemini's FunctionDeclaration accepts. Specifically:

    - Flatten ``anyOf: [{type:T}, {type:"null"}]`` (i.e. Optional[T]) into
      ``{type:T, nullable:true}``.
    - Drop unsupported keywords like ``title``, ``default``, ``$defs``,
      ``additionalProperties``, ``$ref``.
    """
    if not isinstance(schema, dict):
        return schema

    if "anyOf" in schema:
        non_null = [s for s in schema["anyOf"] if not (isinstance(s, dict) and s.get("type") == "null")]
        if len(non_null) == 1:
            base = to_gemini_schema(non_null[0])
            if isinstance(base, dict):
                base["nullable"] = True
                if "description" in schema and "description" not in base:
                    base["description"] = schema["description"]
                return base

    out: dict[str, Any] = {}
    for k, v in schema.items():
        if k == "properties":
            out[k] = {pk: to_gemini_schema(pv) for pk, pv in (v or {}).items()}
        elif k == "items":
            out[k] = to_gemini_schema(v)
        elif k == "required":
            out[k] = list(v)
        elif k in _GEMINI_SCALAR_KEYS:
            out[k] = v
    if out.get("type") == "object" and "properties" not in out:
        out["properties"] = {}
    return out


def mcp_tools_to_gemini(mcp_tools: list[Any]) -> list[dict[str, Any]]:
    """Convert fastmcp Tool objects to Gemini function declarations."""
    decls: list[dict[str, Any]] = []
    for t in mcp_tools:
        params = getattr(t, "inputSchema", None) or {"type": "object", "properties": {}}
        decls.append({
            "name": t.name,
            "description": (t.description or "").strip(),
            "parameters": to_gemini_schema(params),
        })
    return decls


def extract_tool_result(result: Any) -> Any:
    """fastmcp Client.call_tool returns a CallToolResult; extract a JSON-able payload."""
    structured = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if structured is not None:
        return structured
    data = getattr(result, "data", None)
    if data is not None:
        return data
    content = getattr(result, "content", None) or []
    out: list[Any] = []
    for item in content:
        text = getattr(item, "text", None)
        if text is not None:
            out.append(text)
    if len(out) == 1:
        return out[0]
    if out:
        return out
    return {"raw": str(result)}
