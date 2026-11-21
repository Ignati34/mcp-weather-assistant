from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from agent import WeatherAgent
from mcp_client import MCPError, WeatherMCPClient

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def configured_agent() -> WeatherAgent:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    client_args: dict[str, object] = {
        "api_key": key or "missing-key",
        "base_url": base_url or "https://api.openai.com/v1",
        "timeout": float(os.getenv("OPENAI_TIMEOUT_SECONDS", "45")),
        "max_retries": 0,
    }
    return WeatherAgent(
        mcp=WeatherMCPClient(os.getenv("WEATHER_MCP_URL", "https://weather.chukai.io/mcp"), float(os.getenv("MCP_TIMEOUT_SECONDS", "20"))),
        client=AsyncOpenAI(**client_args),
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        max_tool_calls=int(os.getenv("MAX_TOOL_CALLS", "5")),
    )


agent = configured_agent()


class ChatRequest(BaseModel):
    session_id: UUID
    message: str = Field(min_length=1, max_length=4000)


class ResetRequest(BaseModel):
    session_id: UUID


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await agent.client.close()


app = FastAPI(title="AI-помощник по погоде", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Введите сообщение.")
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return {"reply": "Добавьте OPENAI_API_KEY в файл .env и перезапустите приложение, чтобы включить ответы AI.", "tool_calls": [], "weather_card": None}
    try:
        return await agent.reply(str(request.session_id), message)
    except Exception:
        # В журнал/ответ не включаем возможные заголовки, окружение или ключи.
        return {"reply": "Внутренняя ошибка обработки запроса. Проверьте настройки и журнал приложения.", "tool_calls": [], "weather_card": None}


@app.post("/api/new-chat")
async def new_chat(request: ResetRequest) -> dict[str, bool]:
    agent.reset(str(request.session_id))
    return {"ok": True}


@app.get("/api/health")
async def health() -> dict:
    try:
        tools = await agent.mcp.list_tools()
        return {"app": "ok", "mcp": "available", "transport_configured": "Streamable HTTP", "url": agent.mcp.url, "tools": [{"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]} for t in tools]}
    except MCPError as exc:
        return {"app": "ok", "mcp": "unavailable", "transport_configured": "Streamable HTTP", "url": agent.mcp.url, "error": str(exc), "tools": []}
