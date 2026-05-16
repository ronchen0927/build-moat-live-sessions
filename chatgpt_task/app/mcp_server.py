"""
MCP stdio server for the task scheduler.

Tool registry uses a decorator pattern — adding a new tool requires only
decorating a function; the router never needs to change.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Callable

import mcp.server.stdio
from mcp.server import Server
from mcp.types import TextContent, Tool

from . import db, scheduler
from .watcher import watch_loop
from .worker import work_loop

db.init_db()

server = Server("task-scheduler")
_queue: asyncio.Queue = asyncio.Queue()

# Registry: tool_name -> (Tool metadata, handler callable)
TOOL_REGISTRY: dict[str, tuple[Tool, Callable[..., Any]]] = {}


def tool(name: str, description: str, input_schema: dict) -> Callable:
    """Decorator that registers a function as an MCP tool handler."""
    def decorator(fn: Callable) -> Callable:
        TOOL_REGISTRY[name] = (
            Tool(name=name, description=description, inputSchema=input_schema),
            fn,
        )
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@tool(
    name="task.create",
    description="Schedule a new task for future execution.",
    input_schema={
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "What the task should do",
            },
            "scheduled_at": {
                "type": "string",
                "description": "ISO 8601 datetime when the task should run (e.g. 2026-05-16T10:00:00)",
            },
        },
        "required": ["description", "scheduled_at"],
    },
)
def _task_create(description: str, scheduled_at: str) -> dict:
    dt = datetime.fromisoformat(scheduled_at)
    job = scheduler.create_job(description, dt)
    return {
        "job_id": job.id,
        "status": job.status,
        "description": job.description,
        "scheduled_at": job.scheduled_at.isoformat(),
        "hour_bucket": job.hour_bucket,
    }


@tool(
    name="task.list",
    description="List all scheduled tasks.",
    input_schema={"type": "object", "properties": {}},
)
def _task_list() -> list:
    return [
        {
            "job_id": j.id,
            "description": j.description,
            "status": j.status,
            "scheduled_at": j.scheduled_at.isoformat(),
            "hour_bucket": j.hour_bucket,
        }
        for j in scheduler.list_jobs()
    ]


@tool(
    name="task.status",
    description="Get the current status of a specific task.",
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {"type": "integer", "description": "ID of the job to check"},
        },
        "required": ["job_id"],
    },
)
def _task_status(job_id: int) -> dict:
    job = scheduler.get_job(job_id)
    if not job:
        return {"error": f"Job {job_id} not found"}
    return {
        "job_id": job.id,
        "description": job.description,
        "status": job.status,
        "scheduled_at": job.scheduled_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@tool(
    name="task.cancel",
    description="Cancel a pending or queued task.",
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {"type": "integer", "description": "ID of the job to cancel"},
        },
        "required": ["job_id"],
    },
)
def _task_cancel(job_id: int) -> dict:
    job = scheduler.cancel_job(job_id)
    if not job:
        return {"error": f"Job {job_id} not found"}
    return {"job_id": job.id, "status": job.status}


# ---------------------------------------------------------------------------
# MCP server hooks
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [meta for meta, _ in TOOL_REGISTRY.values()]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: {name}")
    _, handler = TOOL_REGISTRY[name]
    result = handler(**(arguments or {}))
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        asyncio.create_task(watch_loop(_queue))
        asyncio.create_task(work_loop(_queue))
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
