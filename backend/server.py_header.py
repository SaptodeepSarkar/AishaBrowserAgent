"""
AISha Desktop Agent — Main FastAPI Server.
Orchestrates: Desktop Control (PyAutoGUI) ↔ Ollama Agent ↔ Memory ↔ Chat History.
Exposes REST + WebSocket endpoints for the React frontend.
"""

import asyncio
import json
import os
import traceback
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from desktop_agent import DesktopAgent
from ollama_agent import OllamaAgent
# from memory_manager import MemoryManager
from chat_manager import ChatManager


# ── Globals & App Initialization ──────────────────────────────────────────
browser = DesktopAgent()
ollama = OllamaAgent(model="gemma4:26b")
# memory = MemoryManager()
chats = ChatManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Starts the Desktop Agent on startup."""
    await browser.start()
    yield
    await browser.stop()

app = FastAPI(lifespan=lifespan)

# CORS Setup - MUST BE AT TOP
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class BridgeManager:
    def __init__(self):
        self.latest_dom = None
        self.extension_ws = None

bridge = BridgeManager()

# ── Extension WebSocket ───────────────────────────────────────────────────
@app.websocket("/ws/extension")
async def extension_websocket(ws: WebSocket):
    await ws.accept()
    bridge.extension_ws = ws
    print("[Bridge] Extension connected")
    try:
        while True:
            data = await ws.receive_json()
            if data["type"] == "dom_update":
                bridge.latest_dom = data["content"]
    except Exception:
        bridge.extension_ws = None
        print("[Bridge] Extension disconnected")

MAX_AGENT_STEPS = 15  # Safety limit on action loop

# ── Models ───────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    prompt: str
    chat_id: Optional[str] = None
