"""The CRM assistant: a tool-calling loop over read-only CRM readers.

    agent -> (tool calls?) -> tools -> agent -> ... -> END

This is the one graph in the package that reaches data, and it is also the one that must not be
able to reach the *wrong* data. It resolves that by never holding a database client: the caller
constructs each :class:`CrmTool` around a reader that is already bound to the requesting user's
RLS-scoped connection (see ``apps/api/app/services/ai/assistant_tools.py``). Postgres then decides
what the model can see, exactly as it does for every screen in the product. There is no
``organization_id`` in this file, because there is nothing here that could use one correctly.

That design also disposes of the prompt-injection question for tenancy. A user -- or a malicious
note inside a CRM record -- can ask the model to look at another organization's leads all it
likes; the query still executes as the requesting user, and returns nothing.

Streaming: the final answer is streamed token by token through an ``asyncio.Queue`` that the agent
node writes to, so the graph stays the orchestrator rather than being bypassed for the one path
users actually watch.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from ..client import get_openai_client
from ..config import ai_settings
from ..errors import AiUpstreamError
from ..prompts import ASSISTANT
from ..usage import UsageRecord

logger = logging.getLogger(__name__)

#: How many times the model may call tools before it must answer. Each round trip is a model call
#: plus a query; without a ceiling a confused model can loop until the request times out.
MAX_TOOL_ROUNDS = 5

#: Cap on one tool result, in characters. A reader that returns 500 leads would otherwise blow the
#: context window and push the user's actual question out of it.
MAX_TOOL_RESULT_CHARS = 8_000

ToolFn = Callable[[dict[str, Any]], Awaitable[Any]]


@dataclass(slots=True)
class CrmTool:
    """One read-only reader the assistant may call.

    ``fn`` must already be bound to the requesting user's scoped database client. This package
    does not check that -- it cannot -- so the binding is the caller's contract to keep.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    fn: ToolFn

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class AssistantState(TypedDict, total=False):
    messages: list[dict[str, Any]]
    tools: dict[str, CrmTool]
    rounds: int
    usage: UsageRecord
    queue: asyncio.Queue


_SENTINEL = object()


async def _agent(state: AssistantState) -> AssistantState:
    """One model turn. Streams assistant text to the queue as it arrives."""
    client = get_openai_client()
    tools = state["tools"]
    # Once the round limit is reached, drop the tools entirely: telling the model it may not call
    # them is more reliable than asking it politely to stop.
    schemas = [t.to_schema() for t in tools.values()] if state["rounds"] < MAX_TOOL_ROUNDS else None

    try:
        stream = await client.chat.completions.create(
            model=ai_settings.openai_chat_model,
            messages=state["messages"],
            tools=schemas,
            temperature=0.2,
            stream=True,
            stream_options={"include_usage": True},
        )
    except Exception as exc:
        logger.exception("assistant_model_call_failed")
        raise AiUpstreamError("The assistant could not reach the model provider") from exc

    content_parts: list[str] = []
    # Tool calls arrive in fragments across deltas, keyed by index; reassemble before use.
    tool_calls: dict[int, dict[str, Any]] = {}
    queue: asyncio.Queue = state["queue"]

    async for chunk in stream:
        if chunk.usage is not None:
            state["usage"].add(chunk.usage)
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        if delta.content:
            content_parts.append(delta.content)
            await queue.put(delta.content)

        for fragment in delta.tool_calls or []:
            call = tool_calls.setdefault(
                fragment.index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
            )
            if fragment.id:
                call["id"] = fragment.id
            if fragment.function and fragment.function.name:
                call["function"]["name"] = fragment.function.name
            if fragment.function and fragment.function.arguments:
                call["function"]["arguments"] += fragment.function.arguments

    message: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts) or None}
    if tool_calls:
        message["tool_calls"] = [tool_calls[i] for i in sorted(tool_calls)]

    return {"messages": state["messages"] + [message], "rounds": state["rounds"] + 1}


async def _tools(state: AssistantState) -> AssistantState:
    """Execute every tool the model asked for, concurrently."""
    last = state["messages"][-1]
    registry = state["tools"]

    async def run_one(call: dict[str, Any]) -> dict[str, Any]:
        name = call["function"]["name"]
        raw_args = call["function"]["arguments"] or "{}"
        try:
            arguments = json.loads(raw_args)
        except json.JSONDecodeError:
            logger.warning("assistant_tool_bad_arguments tool=%s", name)
            result: Any = {"error": "arguments were not valid JSON"}
        else:
            tool = registry.get(name)
            if tool is None:
                # The model hallucinated a tool. Say so plainly rather than failing the turn --
                # it will usually recover on the next round.
                logger.warning("assistant_tool_unknown tool=%s", name)
                result = {"error": f"Unknown tool: {name}"}
            else:
                try:
                    result = await tool.fn(arguments)
                except Exception as exc:
                    logger.exception("assistant_tool_failed tool=%s", name)
                    result = {"error": f"{name} failed: {exc.__class__.__name__}"}

        serialised = json.dumps(result, default=str)
        if len(serialised) > MAX_TOOL_RESULT_CHARS:
            serialised = serialised[:MAX_TOOL_RESULT_CHARS] + '... "(truncated)"'
        return {"role": "tool", "tool_call_id": call["id"], "content": serialised}

    results = await asyncio.gather(*(run_one(c) for c in last.get("tool_calls", [])))
    return {"messages": state["messages"] + list(results)}


def _route(state: AssistantState) -> Literal["tools", "__end__"]:
    last = state["messages"][-1]
    if last.get("role") == "assistant" and last.get("tool_calls"):
        return "tools"
    return END


def build_graph():
    graph = StateGraph(AssistantState)
    graph.add_node("agent", _agent)
    graph.add_node("tools", _tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", _route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def _sanitise(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only the fields we put there ourselves.

    The message list originates in a browser. Letting arbitrary keys (or a second ``system``
    message) through would hand the caller partial control of the prompt, which is precisely what
    the old client-supplied-``context`` design got wrong.
    """
    cleaned: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        cleaned.append({"role": role, "content": content})
    return cleaned


async def run_stream(
    *,
    messages: list[dict[str, Any]],
    tools: list[CrmTool],
    usage: UsageRecord | None = None,
) -> AsyncIterator[str]:
    """Stream the assistant's answer.

    ``tools`` must already be bound to the requesting user's scoped database client.
    """
    history = _sanitise(messages)
    if not history:
        raise ValueError("at least one user message is required")

    usage = usage or UsageRecord(feature="assistant", model=ai_settings.openai_chat_model)
    queue: asyncio.Queue = asyncio.Queue()

    state: AssistantState = {
        "messages": [{"role": "system", "content": ASSISTANT}, *history],
        "tools": {t.name: t for t in tools},
        "rounds": 0,
        "usage": usage,
        "queue": queue,
    }

    async def drive() -> None:
        try:
            await _graph().ainvoke(state, {"recursion_limit": MAX_TOOL_ROUNDS * 2 + 4})
        finally:
            await queue.put(_SENTINEL)

    task = asyncio.create_task(drive())
    try:
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            yield item
        # Surface a failure that happened after the last token was emitted.
        await task
    finally:
        if not task.done():
            task.cancel()
