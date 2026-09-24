"""Gemini-backed ReAct loop for the metro chat assistant.

Connects to the metro MCP server via fastmcp Client, discovers tools, and
runs a tool-use loop calling Gemini with streaming. Yields typed events
for each step (`loop.started`, `model.token`, `model.action`,
`tool.completed`, ...) so the FastAPI route can serialize them as SSE.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator

from google import genai
from google.genai import types as genai_types

from .mcp_client import (
    MetroMCPSession,
    extract_tool_result,
    mcp_tools_to_gemini,
)

logger = logging.getLogger("metro.chat_agent")

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "chat_system_prompt.txt"
MAX_ITERATIONS = 8
TOOL_TIMEOUT_SECONDS = 30


def _now() -> float:
    return time.time()


def _load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _summarize_user_message(text: str, limit: int = 60) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return str(value)


class ChatAgent:
    """Stateful per-process agent. Holds the Gemini client and config; each
    `run()` opens a fresh MCP session for the duration of one user turn.
    """

    def __init__(
        self,
        *,
        gemini_api_key: str,
        model: str,
        mcp_url: str,
        mcp_api_key: str,
    ):
        self._model = model
        self._mcp_url = mcp_url
        self._mcp_api_key = mcp_api_key
        self._client = genai.Client(api_key=gemini_api_key)
        self._system_prompt = _load_system_prompt()

    async def run(
        self,
        *,
        conversation_id: str,
        user_message: str,
        user_message_id: str,
        history: list[genai_types.Content],
        on_assistant_iteration: Any = None,
        on_tool_message: Any = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Drive the ReAct loop for one user turn. Yields event dicts ready to
        be JSON-serialized into SSE frames. ``history`` is the prior
        conversation as Gemini Content objects (not including the new user
        message). The optional callbacks fire in chronological order so the
        router can persist rows:

        - ``on_assistant_iteration({iter, text, tool_calls})`` — called at the
          end of each iteration where the model produced output (text and/or
          tool calls). Skipped if the iteration produced nothing.
        - ``on_tool_message({tool, args, result})`` — called once per tool
          call after it has completed.
        """
        yield {
            "type": "loop.started",
            "ts": _now(),
            "conversation_id": conversation_id,
            "user_message_id": user_message_id,
            "user_message": user_message,
        }

        contents: list[genai_types.Content] = list(history) + [
            genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_text(text=user_message)],
            )
        ]

        assistant_text_parts: list[str] = []
        assistant_message_id = str(uuid.uuid4())
        iter_count = 0

        async with MetroMCPSession(self._mcp_url, self._mcp_api_key) as mcp:
            mcp_tools = await mcp.list_tools()
            function_decls = mcp_tools_to_gemini(mcp_tools)
            tool_config = genai_types.Tool(function_declarations=function_decls)

            for iteration in range(1, MAX_ITERATIONS + 1):
                iter_count = iteration
                yield {"type": "iter.started", "ts": _now(), "iter": iteration}

                response_stream = await asyncio.to_thread(
                    self._client.models.generate_content_stream,
                    model=self._model,
                    contents=contents,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=self._system_prompt,
                        tools=[tool_config],
                        thinking_config=genai_types.ThinkingConfig(
                            include_thoughts=True,
                            # Generous budget so the model emits a reasoning
                            # summary on every step, including the final
                            # answer iteration. Lower values caused Gemini
                            # to skip thinking once it had a tool result.
                            thinking_budget=4096,
                        ),
                    ),
                )

                iter_function_calls: list[genai_types.FunctionCall] = []
                iter_text_parts: list[str] = []

                def _drain_stream():
                    chunks: list[genai_types.GenerateContentResponse] = []
                    for chunk in response_stream:
                        chunks.append(chunk)
                    return chunks

                chunks = await asyncio.to_thread(_drain_stream)

                for chunk in chunks:
                    candidates = getattr(chunk, "candidates", None) or []
                    for cand in candidates:
                        content = getattr(cand, "content", None)
                        if not content:
                            continue
                        for part in (getattr(content, "parts", None) or []):
                            text = getattr(part, "text", None)
                            is_thought = bool(getattr(part, "thought", False))
                            if text:
                                if is_thought:
                                    yield {
                                        "type": "model.thinking",
                                        "ts": _now(),
                                        "iter": iteration,
                                        "text": text,
                                    }
                                else:
                                    iter_text_parts.append(text)
                                    yield {
                                        "type": "model.token",
                                        "ts": _now(),
                                        "iter": iteration,
                                        "text": text,
                                    }
                            fc = getattr(part, "function_call", None)
                            if fc and getattr(fc, "name", None):
                                iter_function_calls.append(fc)

                if iter_text_parts:
                    assistant_text_parts.extend(iter_text_parts)

                if not iter_function_calls:
                    if iter_text_parts and on_assistant_iteration is not None:
                        await on_assistant_iteration({
                            "iter": iteration,
                            "text": "".join(iter_text_parts),
                            "tool_calls": [],
                        })
                    yield {"type": "iter.finished", "ts": _now(), "iter": iteration}
                    break

                model_parts: list[genai_types.Part] = []
                if iter_text_parts:
                    model_parts.append(
                        genai_types.Part.from_text(text="".join(iter_text_parts))
                    )
                for fc in iter_function_calls:
                    model_parts.append(genai_types.Part(function_call=fc))
                contents.append(genai_types.Content(role="model", parts=model_parts))

                if on_assistant_iteration is not None:
                    await on_assistant_iteration({
                        "iter": iteration,
                        "text": "".join(iter_text_parts),
                        "tool_calls": [
                            {"tool": fc.name, "args": _to_jsonable(dict(fc.args or {}))}
                            for fc in iter_function_calls
                        ],
                    })

                tool_response_parts: list[genai_types.Part] = []
                for fc in iter_function_calls:
                    call_id = str(uuid.uuid4())
                    args = dict(fc.args or {})
                    yield {
                        "type": "model.action",
                        "ts": _now(),
                        "iter": iteration,
                        "call_id": call_id,
                        "tool": fc.name,
                        "args": _to_jsonable(args),
                    }
                    yield {
                        "type": "tool.started",
                        "ts": _now(),
                        "iter": iteration,
                        "call_id": call_id,
                        "tool": fc.name,
                    }
                    started = _now()
                    try:
                        raw = await asyncio.wait_for(
                            mcp.call_tool(fc.name, args),
                            timeout=TOOL_TIMEOUT_SECONDS,
                        )
                        result_payload = extract_tool_result(raw)
                    except asyncio.TimeoutError:
                        result_payload = {"error": f"tool_timeout_{TOOL_TIMEOUT_SECONDS}s"}
                    except Exception as e:
                        logger.exception(f"tool {fc.name} failed")
                        result_payload = {"error": f"tool_exception: {e}"}
                    duration_ms = int((_now() - started) * 1000)
                    payload_jsonable = _to_jsonable(result_payload)
                    yield {
                        "type": "tool.completed",
                        "ts": _now(),
                        "iter": iteration,
                        "call_id": call_id,
                        "tool": fc.name,
                        "result": payload_jsonable,
                        "duration_ms": duration_ms,
                    }
                    if on_tool_message is not None:
                        await on_tool_message({
                            "tool": fc.name,
                            "args": _to_jsonable(args),
                            "result": payload_jsonable,
                        })
                    response_value = (
                        payload_jsonable if isinstance(payload_jsonable, dict)
                        else {"result": payload_jsonable}
                    )
                    tool_response_parts.append(
                        genai_types.Part.from_function_response(
                            name=fc.name,
                            response=response_value,
                        )
                    )

                contents.append(
                    genai_types.Content(role="user", parts=tool_response_parts)
                )
                yield {"type": "iter.finished", "ts": _now(), "iter": iteration}

        assistant_text = "".join(assistant_text_parts).strip()
        yield {
            "type": "loop.finished",
            "ts": _now(),
            "iter_count": iter_count,
            "assistant_text": assistant_text,
            "assistant_message_id": assistant_message_id,
        }


def history_to_gemini_contents(rows: list[dict[str, Any]]) -> list[genai_types.Content]:
    """Reconstruct Gemini Content sequence from chat_messages rows ordered by created_at.

    Each row has ``role`` and JSON ``content``. We reconstruct user/model/tool
    parts so that the model sees previous tool calls and their results.
    """
    contents: list[genai_types.Content] = []
    for row in rows:
        role = row["role"]
        content = row["content"]
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                content = {"text": content}
        if role == "user":
            text = content.get("text") if isinstance(content, dict) else str(content)
            if text:
                contents.append(genai_types.Content(
                    role="user",
                    parts=[genai_types.Part.from_text(text=text)],
                ))
        elif role == "assistant":
            parts: list[genai_types.Part] = []
            text = content.get("text") if isinstance(content, dict) else None
            if text:
                parts.append(genai_types.Part.from_text(text=text))
            for tc in (content.get("tool_calls") or []) if isinstance(content, dict) else []:
                parts.append(genai_types.Part(
                    function_call=genai_types.FunctionCall(
                        name=tc.get("tool"),
                        args=tc.get("args") or {},
                    ),
                ))
            if parts:
                contents.append(genai_types.Content(role="model", parts=parts))
        elif role == "tool":
            response_value = content.get("result") if isinstance(content, dict) else content
            if not isinstance(response_value, dict):
                response_value = {"result": response_value}
            contents.append(genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_function_response(
                    name=content.get("tool", "tool") if isinstance(content, dict) else "tool",
                    response=response_value,
                )],
            ))
    return contents
