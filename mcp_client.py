"""Клиент для подключаемых MCP-серверов. На этапе 1 используется HTTP.

Здесь намеренно нет собственного MCP-сервера и прямых погодных API.
Отдельные подключения на запрос упрощают восстановление после обрыва сети.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


class MCPError(RuntimeError):
    """Ошибка соединения или выполнения операции MCP."""


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if hasattr(value, "dict"):
        return value.dict(exclude_none=True)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class WeatherMCPClient:
    def __init__(self, url: str, timeout_seconds: float = 20) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds

    @asynccontextmanager
    async def connected(self) -> AsyncIterator[ClientSession]:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with streamablehttp_client(
                    self.url,
                    timeout=timedelta(seconds=self.timeout_seconds),
                    sse_read_timeout=timedelta(seconds=self.timeout_seconds),
                ) as (read_stream, write_stream, _get_session_id):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        yield session
        except TimeoutError as exc:
            raise MCPError(f"Истекло время ожидания MCP-сервера ({self.timeout_seconds:g} с).") from exc
        except MCPError:
            raise
        except Exception as exc:
            raise MCPError(f"Не удалось выполнить запрос к MCP-серверу: {type(exc).__name__}: {exc}") from exc

    async def list_tools(self) -> list[dict[str, Any]]:
        async with self.connected() as session:
            try:
                result = await session.list_tools()
            except Exception as exc:
                raise MCPError(f"Ошибка tools/list: {type(exc).__name__}: {exc}") from exc
            return [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": _jsonable(tool.inputSchema),
                }
                for tool in result.tools
            ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async with self.connected() as session:
            try:
                result = await session.call_tool(name, arguments=arguments)
            except Exception as exc:
                raise MCPError(f"Ошибка tools/call ({name}): {type(exc).__name__}: {exc}") from exc
            return {
                "isError": bool(result.isError),
                "content": [_jsonable(item) for item in result.content],
                "structuredContent": _jsonable(getattr(result, "structuredContent", None)),
            }


def to_openai_tools(mcp_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Преобразует опубликованные сервером схемы в формат Chat Completions."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description") or f"Инструмент MCP: {tool['name']}",
                "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
            },
        }
        for tool in mcp_tools
    ]


def format_tool_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
