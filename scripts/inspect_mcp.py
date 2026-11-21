"""Выполняет настоящий MCP initialize + tools/list и печатает серверные схемы."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import timedelta

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main() -> None:
    load_dotenv()
    url = os.getenv("WEATHER_MCP_URL", "https://weather.chukai.io/mcp")
    timeout = float(os.getenv("MCP_TIMEOUT_SECONDS", "20"))
    async with asyncio.timeout(timeout):
        async with streamablehttp_client(url, timeout=timedelta(seconds=timeout)) as (read_stream, write_stream, get_session_id):
            async with ClientSession(read_stream, write_stream) as session:
                initialized = await session.initialize()
                listed = await session.list_tools()
                print(f"URL: {url}")
                print(f"Transport: Streamable HTTP (проверяется этим запуском; сам факт поддержки подтвердит только успешный handshake)")
                print(f"Protocol: {initialized.protocolVersion}")
                print(f"Server: {initialized.serverInfo.name} {initialized.serverInfo.version}")
                print(f"Session ID: {get_session_id()}")
                print("Tools:")
                for tool in listed.tools:
                    schema = tool.inputSchema.model_dump(mode="json") if hasattr(tool.inputSchema, "model_dump") else tool.inputSchema
                    print(json.dumps({"name": tool.name, "description": tool.description, "inputSchema": schema}, ensure_ascii=False, indent=2))
                if not listed.tools:
                    print("Сервер не опубликовал инструменты.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"MCP check failed: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
