"""Chat endpoints: streaming ReAct loop + conversation history."""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.chat_agent import history_to_gemini_contents

logger = logging.getLogger("routers.chat")
router = APIRouter()


class MapContext(BaseModel):
    """What the map is currently filtered to; the agent uses it as defaults."""
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    categories: Optional[list[str]] = None
    transport_only: Optional[bool] = None
    modes: Optional[list[str]] = None
    alcaldia: Optional[str] = None
    station_key: Optional[str] = None


class ChatStreamRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[str] = None
    map_context: Optional[MapContext] = None
    # Set by the English entry point (/en); pins the reply language.
    lang: Optional[Literal["es", "en"]] = None


def _summarize(text: str, limit: int = 60) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def _ensure_conversation(pool, conversation_id: Optional[str], first_message: str) -> str:
    """Return an existing conversation_id or create a new one."""
    if conversation_id:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM chat_conversations WHERE id = $1", uuid.UUID(conversation_id)
            )
            if row:
                return str(row["id"])
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO chat_conversations (title) VALUES ($1) RETURNING id",
            _summarize(first_message),
        )
        return str(row["id"])


async def _insert_message(pool, conversation_id: str, role: str, content: dict[str, Any]) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO chat_messages (conversation_id, role, content)
            VALUES ($1, $2, $3::jsonb)
            RETURNING id
            """,
            uuid.UUID(conversation_id),
            role,
            json.dumps(content),
        )
        await conn.execute(
            "UPDATE chat_conversations SET updated_at = now() WHERE id = $1",
            uuid.UUID(conversation_id),
        )
        return str(row["id"])


async def _load_history_rows(pool, conversation_id: str) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content
            FROM chat_messages
            WHERE conversation_id = $1
            ORDER BY created_at ASC, id ASC
            """,
            uuid.UUID(conversation_id),
        )
    return [
        {"role": r["role"], "content": json.loads(r["content"]) if isinstance(r["content"], str) else r["content"]}
        for r in rows
    ]


@router.post("/chat/stream")
async def chat_stream(req: ChatStreamRequest, request: Request):
    agent = getattr(request.app.state, "chat_agent", None)
    if agent is None:
        raise HTTPException(503, {"error": "chat_agent_unavailable",
                                  "detail": "GEMINI_API_KEY or CRIME_MCP_API_KEY not configured"})
    pool = request.app.state.db

    conversation_id = await _ensure_conversation(pool, req.conversation_id, req.message)
    history_rows = await _load_history_rows(pool, conversation_id)
    history_contents = history_to_gemini_contents(history_rows)
    user_message_id = await _insert_message(
        pool, conversation_id, "user", {"text": req.message}
    )

    # Build the message the agent actually sees. Persisted history keeps just
    # the original user text; the model sees a transient preamble with the
    # map's current filters so "here" / "this period" resolve to something.
    augmented_message = req.message
    if req.map_context is not None:
        ctx = {k: v for k, v in req.map_context.model_dump().items() if v not in (None, [], "")}
        if ctx:
            augmented_message = (
                "[user_context]\n"
                f"map_filters: {json.dumps(ctx, ensure_ascii=False)}\n"
                "(The user is looking at the map filtered like this. Use these values as defaults "
                "for date_from/date_to/categories/transport_only/alcaldia when the question does not "
                "state its own, and say which window you used. Reply in the language of the message "
                "below, not of these values.)\n"
                "[/user_context]\n\n"
                f"{req.message}"
            )

    async def on_assistant_iteration(payload: dict[str, Any]) -> None:
        await _insert_message(pool, conversation_id, "assistant", {
            "iter": payload.get("iter"),
            "text": payload.get("text") or "",
            "tool_calls": payload.get("tool_calls") or [],
        })

    async def on_tool_message(payload: dict[str, Any]) -> None:
        await _insert_message(pool, conversation_id, "tool", {
            "tool": payload.get("tool"),
            "args": payload.get("args"),
            "result": payload.get("result"),
        })

    async def generate():
        # Initial hello so the browser knows the connection is live.
        yield ":hello\n\n"
        try:
            async for event in agent.run(
                conversation_id=conversation_id,
                user_message=augmented_message,
                user_message_id=user_message_id,
                history=history_contents,
                lang=req.lang,
                on_assistant_iteration=on_assistant_iteration,
                on_tool_message=on_tool_message,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            logger.exception("chat.stream errored mid-stream")
            err = {
                "type": "loop.errored",
                "ts": time.time(),
                "message": str(exc),
                "exception_type": type(exc).__name__,
            }
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/chat/conversations")
async def list_conversations(request: Request, limit: int = 50):
    pool = request.app.state.db
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM chat_messages m WHERE m.conversation_id = c.id) AS msg_count
            FROM chat_conversations c
            ORDER BY c.updated_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            "msg_count": int(r["msg_count"]),
        }
        for r in rows
    ]


@router.get("/chat/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str, request: Request):
    pool = request.app.state.db
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(400, "invalid conversation_id")
    async with pool.acquire() as conn:
        head = await conn.fetchrow(
            "SELECT id, title, created_at, updated_at FROM chat_conversations WHERE id = $1", cid
        )
        if not head:
            raise HTTPException(404, "conversation not found")
        rows = await conn.fetch(
            """
            SELECT id, role, content, created_at
            FROM chat_messages
            WHERE conversation_id = $1
            ORDER BY created_at ASC, id ASC
            """,
            cid,
        )
    return {
        "id": str(head["id"]),
        "title": head["title"],
        "created_at": head["created_at"].isoformat() if head["created_at"] else None,
        "messages": [
            {
                "id": str(r["id"]),
                "role": r["role"],
                "content": json.loads(r["content"]) if isinstance(r["content"], str) else r["content"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ],
    }


@router.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request):
    pool = request.app.state.db
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(400, "invalid conversation_id")
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM chat_conversations WHERE id = $1", cid)
    return {"deleted": result.endswith(" 1")}
