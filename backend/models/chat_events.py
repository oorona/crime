"""Pydantic event types for the chat ReAct loop SSE stream.

Modeled on reactreel-web/backend's event taxonomy. Each event is emitted
as a single ``data: {json}\\n\\n`` line. The frontend reducer dispatches
on the ``type`` field.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class BaseEvent(BaseModel):
    type: str
    ts: float = Field(0.0, description="Server epoch seconds when the event was emitted.")


class LoopStarted(BaseEvent):
    type: Literal["loop.started"] = "loop.started"
    conversation_id: str
    user_message_id: str
    user_message: str


class IterStarted(BaseEvent):
    type: Literal["iter.started"] = "iter.started"
    iter: int


class ModelToken(BaseEvent):
    """Streamed token of assistant prose (partial text delta)."""
    type: Literal["model.token"] = "model.token"
    iter: int
    text: str


class ModelThinking(BaseEvent):
    """Streamed token of the model's internal chain-of-thought (thought summary)."""
    type: Literal["model.thinking"] = "model.thinking"
    iter: int
    text: str


class ModelAction(BaseEvent):
    """Model decided to call a tool."""
    type: Literal["model.action"] = "model.action"
    iter: int
    call_id: str
    tool: str
    args: dict[str, Any]


class ToolStarted(BaseEvent):
    type: Literal["tool.started"] = "tool.started"
    iter: int
    call_id: str
    tool: str


class ToolCompleted(BaseEvent):
    type: Literal["tool.completed"] = "tool.completed"
    iter: int
    call_id: str
    tool: str
    result: Any
    duration_ms: int


class IterFinished(BaseEvent):
    type: Literal["iter.finished"] = "iter.finished"
    iter: int


class LoopFinished(BaseEvent):
    type: Literal["loop.finished"] = "loop.finished"
    iter_count: int
    assistant_text: str
    assistant_message_id: str


class LoopErrored(BaseEvent):
    type: Literal["loop.errored"] = "loop.errored"
    message: str
    iter: Optional[int] = None
