"""
AISha Desktop Agent — Main FastAPI Server.
Orchestrates: Desktop Control (PyAutoGUI) ↔ Ollama Agent ↔ Memory ↔ Chat History.
Exposes REST + WebSocket endpoints for the React frontend.
"""

import asyncio
import json
import os
import re
import traceback
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from desktop_agent import DesktopAgent
from ollama_agent import OllamaAgent, SYSTEM_PROMPT
from chat_manager import ChatManager


# ── Security: allowed origins for CORS ──────────────────────────────────
# In production, replace with the actual frontend URL.
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://localhost:8763",
]


# ── Input validation helpers ────────────────────────────────────────────
def sanitize_prompt(text: str, max_length: int = 2000) -> str:
    """Sanitize user prompt strings: trim, escape, limit length."""
    text = (text or "").strip()
    # Remove null bytes and control characters (except newlines/tabs)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    if len(text) > max_length:
        text = text[:max_length]
    return text


# ── Globals & App Initialization ──────────────────────────────────────────
browser = DesktopAgent()
ollama = OllamaAgent()
chats = ChatManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Starts the Desktop Agent on startup."""
    await browser.start()
    yield
    await browser.stop()

app = FastAPI(lifespan=lifespan)

# CORS Setup - restricted to known origins for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)

class BridgeManager:
    def __init__(self):
        self.latest_dom = None
        self.latest_action_result = "None"
        self.extension_ws = None
        self.dom_event = asyncio.Event()
        self.last_url = None # Track the URL of the last processed DOM

    def set_dom(self, dom_data):
        """Called when extension pushes a dom_update."""
        new_url = dom_data.get("url")
        
        # If we are waiting for a fresh DOM after a clear, and this update
        # comes from the exact same URL as before, it MIGHT be a stale update
        # from a dying page (especially during navigation).
        # However, for non-navigational actions (like click), the URL stays the same.
        # So we only reject if the event was cleared.
        
        self.latest_dom = dom_data
        self.last_url = new_url
        self.dom_event.set()

    def clear_dom(self):
        """Clear DOM and reset the event so we can wait for the next one."""
        self.latest_dom = None
        self.dom_event.clear()

    async def wait_for_dom(self, timeout: float = 10.0, expect_new_url: bool = False) -> bool:
        """
        Block until extension pushes a fresh dom_update, or timeout.
        If expect_new_url is True, it will ignore updates from the old URL.
        """
        start_time = asyncio.get_event_loop().time()
        old_url = self.last_url
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                await asyncio.wait_for(self.dom_event.wait(), timeout=timeout - (asyncio.get_event_loop().time() - start_time))
                
                if expect_new_url and self.latest_dom and self.latest_dom.get("url") == old_url:
                    # Received an update, but it's still the old URL. 
                    # Clear the event and keep waiting.
                    self.dom_event.clear()
                    continue
                
                return True
            except (asyncio.TimeoutError, asyncio.CancelledError):
                break
        return False

bridge = BridgeManager()

# ── Globals ──
connected_clients = set()


def _log_dom(content: dict):
    """Pretty-print a DOM update to the server console for human readability."""
    url = content.get("url", "—")
    title = content.get("title", "—")
    page_text = (content.get("pageText") or "")[:200]
    elements = content.get("elements", [])

    sep = "─" * 80
    print(f"\n[LLM DOM] {sep}")
    print(f"[LLM DOM]  🌐  URL   : {url}")
    print(f"[LLM DOM]  📄  Title : {title}")
    if page_text:
        print(f"[LLM DOM]  📝  Summary: {page_text}{'…' if len(content.get('pageText', '')) > 200 else ''}")
    print(f"[LLM DOM]  🔢  Elements: {len(elements)} pruned")
    print(f"[LLM DOM] {sep}")

    if elements:
        # Column widths
        id_w, tag_w, text_w, ph_w = 12, 10, 40, 25
        header = f"  {'ID':<{id_w}}  {'TAG':<{tag_w}}  {'TEXT':<{text_w}}  {'PLACEHOLDER':<{ph_w}}"
        print(f"[LLM DOM] {header}")
        print(f"[LLM DOM]  {'─'*id_w}  {'─'*tag_w}  {'─'*text_w}  {'─'*ph_w}")

        for el in elements:
            el_id = str(el.get("id", ""))[:id_w]
            is_editable = el.get("isContentEditable") or el.get("role") == "textbox"
            tag_suffix = "+" if is_editable else ""
            tag = f"{el.get('tag', '')}{tag_suffix}"[:tag_w]
            text = (el.get("text") or "")[:text_w]
            placeholder = (el.get("placeholder") or "")[:ph_w]
            
            # Show all elements that have a tag or ID, even if text/placeholder are empty
            if not el_id and not tag:
                continue
                
            print(f"[LLM DOM]   {el_id:<{id_w}}  {tag:<{tag_w}}  {text:<{text_w}}  {placeholder:<{ph_w}}")

    print(f"[LLM DOM] {sep}\n")


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
                bridge.set_dom(data["content"])
                # Broadcast URL to all frontend clients
                url = data["content"].get("url", "")
                title = data["content"].get("title", "")
                for client in connected_clients:
                    try:
                        await client.send_json({"type": "dom_update", "url": url, "title": title})
                    except:
                        pass
            elif data["type"] == "action_result":
                bridge.latest_action_result = data["content"]
    except Exception:
        bridge.extension_ws = None
        print("[Bridge] Extension disconnected")

MAX_AGENT_STEPS = 15  # Safety limit on action loop

# ── Models ───────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    chat_id: Optional[str] = None

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        return sanitize_prompt(v)

# ── REST Endpoints ────────────────────────────────────────────────────────
@app.get("/api/chats")
async def list_chats():
    return chats.list_chats()

@app.get("/api/chats/{chat_id}")
async def get_chat_details(chat_id: str):
    return chats.get_chat(chat_id)

@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str):
    success = chats.delete_chat(chat_id)
    return {"success": success}

@app.get("/api/agent/state")
async def get_agent_state():
    return {"todo": "Work in progress", "plan": []}


# ── External Query API ────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    chat_id: Optional[str] = None

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        return sanitize_prompt(v, max_length=4000)

class QueryResponse(BaseModel):
    answer: str
    chat_id: str
    steps_taken: int

@app.post("/api/query", response_model=QueryResponse)
async def external_query(req: QueryRequest):
    """
    Headless agent API endpoint.
    Accepts a prompt, runs the full browser agent loop internally,
    saves the chat, and returns only the final answer.

    Example:
        POST /api/query
        { "prompt": "Search YouTube for lo-fi music and tell me the top result" }

    Returns:
        { "answer": "...", "chat_id": "...", "steps_taken": 5 }
    """
    prompt = req.prompt
    chat_id = req.chat_id

    # Create or reuse a chat
    if not chat_id:
        new_chat = chats.create_chat(title=prompt[:40])
        chat_id = new_chat["id"]
    
    chats.add_message(chat_id, "user", prompt)

    # Load history
    chat = chats.get_chat(chat_id)
    history = []
    if chat and "messages" in chat:
        history = chat["messages"][:-1] if len(chat["messages"]) > 1 else []

    step_count = 0
    session_steps = []
    current_prompt = prompt
    final_answer = "Agent did not produce an answer within the step limit."

    # Lock the browser tab immediately
    if bridge.extension_ws:
        try:
            await bridge.extension_ws.send_json({"type": "action", "content": {"action": "lock"}})
        except:
            pass

    try:
        # Request initial DOM
        bridge.clear_dom()
        if bridge.extension_ws:
            try:
                await bridge.extension_ws.send_json({"type": "action", "content": {"action": "get_dom"}})
            except Exception as e:
                print(f"[API Query] Error requesting initial DOM: {e}")
        await bridge.wait_for_dom(timeout=10.0)

        while step_count < MAX_AGENT_STEPS:
            print(f"\n[API Query] ─── Step {step_count + 1} ───")

            # Re-lock on every step (handles page reloads)
            if bridge.extension_ws:
                try:
                    await bridge.extension_ws.send_json({"type": "action", "content": {"action": "lock"}})
                except:
                    pass

            # Build browser state from current DOM (with empty-DOM retry)
            MAX_DOM_RETRIES = 5
            dom_retries = 0
            dom_ready = False
            
            while dom_retries < MAX_DOM_RETRIES and not dom_ready:
                dom_retries += 1

                # Backoff delay on retries: first check instant, then 500ms, 1s, 1.5s, 2s
                if dom_retries > 1:
                    backoff = 0.5 * (dom_retries - 1)
                    print(f"[API Query] Waiting {backoff:.1f}s before DOM retry {dom_retries}...")
                    await asyncio.sleep(backoff)

                if bridge.latest_dom and bridge.latest_dom.get("elements"):
                    elements = bridge.latest_dom.get("elements", [])
                    pruned = [
                        el for el in elements 
                        if el.get("text") or el.get("placeholder") or 
                           el.get("tag") in ["input", "textarea", "button", "select", "a"] or
                           el.get("role") == "textbox" or el.get("isContentEditable")
                    ][:500]
                    
                    if len(pruned) > 0:
                        # We have usable elements — build state and proceed
                        dom_lines = []
                        for el in pruned:
                            text_part = f" '{el['text']}'" if el.get('text') else ""
                            placeholder_part = f" placeholder='{el['placeholder']}'" if el.get('placeholder') else ""
                            href_part = f" href='{el['href']}'" if el.get('href') else ""
                            editable_part = " [editable]" if el.get("isContentEditable") or el.get("role") == "textbox" else ""
                            dom_lines.append(f"{el['id']}: <{el['tag']}>{text_part}{href_part}{placeholder_part}{editable_part}")
                        dom_text = "\n".join(dom_lines) if dom_lines else "No interactive elements found."
                        page_summary = bridge.latest_dom.get("pageText", "No summary available.")
                        browser_state = f"URL: {bridge.latest_dom['url']}\nTitle: {bridge.latest_dom['title']}\n\nPage Summary: {page_summary}\n\nInteractive Elements:\n{dom_text}"
                        print(f"[API Query] Page: {bridge.latest_dom['title']}")
                        print(f"[API Query] Elements: {len(elements)} raw → {len(pruned)} pruned")
                        _log_dom({**bridge.latest_dom, "elements": pruned})
                        dom_ready = True
                        break
                    else:
                        # DOM is present but no pruned elements — retry
                        if dom_retries < MAX_DOM_RETRIES:
                            print(f"[API Query] ⚠ DOM has 0 interactive elements (attempt {dom_retries}/{MAX_DOM_RETRIES}). Retrying...")
                            bridge.clear_dom()
                            if bridge.extension_ws:
                                try:
                                    await bridge.extension_ws.send_json({"type": "action", "content": {"action": "get_dom"}})
                                except: pass
                            await bridge.wait_for_dom(timeout=5.0)
                else:
                    # No DOM at all
                    if dom_retries < MAX_DOM_RETRIES:
                        print(f"[API Query] ⚠ No DOM available (attempt {dom_retries}/{MAX_DOM_RETRIES}). Retrying...")
                        bridge.clear_dom()
                        if bridge.extension_ws:
                            try:
                                await bridge.extension_ws.send_json({"type": "action", "content": {"action": "get_dom"}})
                            except: pass
                        await bridge.wait_for_dom(timeout=5.0)
            
            # If DOM is still empty/absent after retries, bail out
            if not dom_ready:
                final_answer = "Error: The page did not load any interactive elements. Cannot proceed with this task."
                print(f"[API Query] ✋ {final_answer}")
                chats.add_message(chat_id, "assistant", final_answer, metadata={"steps": session_steps})
                step_count = MAX_AGENT_STEPS  # force exit of while loop
                break

            # Trim history
            trimmed_steps = session_steps[-3:] if len(session_steps) > 3 else session_steps
            session_history = history + [{"role": "assistant", "content": f"**Thinking:** {s['thinking']}\n```json\n{json.dumps(s['action'])}\n```"} for s in trimmed_steps]

            # Run the LLM
            thinking_buffer = ""
            async for token in ollama.stream_think(current_prompt, browser_state, history=session_history, system_prompt=SYSTEM_PROMPT):
                thinking_buffer += token
                print(token, end="", flush=True)
            print()

            # Parse action
            parsed = ollama._parse_response(thinking_buffer)
            action = parsed.get("action")

            if not action:
                print("[API Query] No action parsed. Retrying...")
                continue

            print(f"[API Query] Action: {action.get('action')}")

            # Handle answer — return immediately
            if action.get("action") == "answer":
                final_answer = action.get("text", "Task completed.")
                session_steps.append({"thinking": thinking_buffer, "action": action})
                chats.add_message(chat_id, "assistant", final_answer, metadata={"steps": session_steps})
                break

            # Execute action
            session_steps.append({"thinking": thinking_buffer, "action": action})

            if bridge.extension_ws:
                ext_action = action.copy()
                if ext_action["action"] == "type_and_enter":
                    ext_action["action"] = "type"
                    ext_action["press_enter"] = True
                
                # Clear DOM BEFORE sending action to wait for fresh one
                bridge.clear_dom()
                bridge.latest_action_result = None
                
                await bridge.extension_ws.send_json({"type": "action", "content": ext_action})
                
                # Wait for action_result (max 4s)
                idle_wait = 0
                while bridge.latest_action_result is None and idle_wait < 40:
                    await asyncio.sleep(0.1)
                    idle_wait += 1
                action_result = bridge.latest_action_result or "Action timed out."
                print(f"[API Query] Action executed in ~{idle_wait * 100}ms")
                
                # Wait for fresh DOM from extension
                is_navigation = ext_action.get("action") in ["navigate", "type"] and (ext_action.get("press_enter") or ext_action.get("action") == "navigate")
                dom_timeout = 10.0 if is_navigation else 5.0
                
                print(f"[API Query] Waiting for fresh DOM (timeout: {dom_timeout}s)...")
                got_fresh_dom = await bridge.wait_for_dom(timeout=dom_timeout, expect_new_url=is_navigation)
                
                if got_fresh_dom:
                    print(f"[API Query] ✓ Fresh DOM received from: {bridge.latest_dom.get('url', 'unknown')}")
                else:
                    print(f"[API Query] ⚠ DOM timeout. Requesting explicitly...")
                    bridge.clear_dom()
                    if bridge.extension_ws:
                        try:
                            await bridge.extension_ws.send_json({"type": "action", "content": {"action": "get_dom"}})
                        except:
                            pass
                        await bridge.wait_for_dom(timeout=5.0)
            else:
                action_result = "Extension not available."

            step_count += 1
            current_prompt = f"Original task: {prompt}\n\nLast action result: {action_result}\n\nContinue."

    finally:
        # Always unlock when done
        if bridge.extension_ws:
            try:
                await bridge.extension_ws.send_json({"type": "action", "content": {"action": "unlock"}})
            except:
                pass

    return QueryResponse(answer=final_answer, chat_id=chat_id, steps_taken=step_count)


# ── WebSocket Handler ─────────────────────────────────────────────────────
@app.websocket("/ws/agent")
async def agent_websocket(ws: WebSocket):
    await ws.accept()
    connected_clients.add(ws)
    print("[WS] Client connected")
    
    # Use a lock to prevent concurrent writes to the same websocket
    ws_lock = asyncio.Lock()
    agent_running = False
    
    try:
        while True:
            data = await ws.receive_json()
            if data["type"] == "user_message":
                if agent_running:
                    async with ws_lock:
                        await ws.send_json({"type": "status", "content": "Already processing a task..."})
                    continue
                
                # Validate and sanitize input
                prompt_raw = data.get("content", "")
                if not isinstance(prompt_raw, str) or not prompt_raw.strip():
                    async with ws_lock:
                        await ws.send_json({"type": "error", "content": "Empty prompt received."})
                    continue
                prompt = sanitize_prompt(prompt_raw, max_length=4000)
                if not prompt:
                    async with ws_lock:
                        await ws.send_json({"type": "error", "content": "Prompt is empty after sanitization."})
                    continue
                    
                agent_running = True
                try:
                    chat_id = data.get("chat_id")
                    
                    is_new_chat = False
                    if not chat_id:
                        is_new_chat = True
                        new_chat = chats.create_chat(title="Loading...")
                        chat_id = new_chat["id"]
                        async with ws_lock:
                            try:
                                await ws.send_json({"type": "chat_created", "chat": {"id": chat_id}})
                            except: pass
                    else:
                        # Check if it was previously loading (interrupted or failed generation)
                        chat = chats.get_chat(chat_id)
                        if chat and chat["title"] in ["New Chat", "Loading..."]:
                            is_new_chat = True

                    # Save user message
                    chats.add_message(chat_id, "user", prompt)

                    # Load Chat History for Context
                    chat = chats.get_chat(chat_id)
                    # Only pass history IF it's not the very first message in a NEW chat
                    history = []
                    if chat and "messages" in chat:
                        # If this is the only message (the one we just added), don't pass it as "history" yet
                        # Otherwise, pass previous messages
                        history = chat["messages"][:-1] if len(chat["messages"]) > 1 else []

                    # Agent Loop Setup
                    step_count = 0
                    session_steps = []
                    current_prompt = prompt

                    # Initial Lock: Start the pink glow immediately
                    if bridge.extension_ws:
                        try:
                            await bridge.extension_ws.send_json({"type": "action", "content": {"action": "lock"}})
                        except: pass

                    # === BROWSER AGENT PHASE ===
                    # Pipeline: Wait for DOM → Agent decides → Execute → Wait for fresh DOM → Repeat
                    
                    # Step 0: Request initial DOM from extension
                    bridge.clear_dom()
                    if bridge.extension_ws:
                        try:
                            await bridge.extension_ws.send_json({"type": "action", "content": {"action": "get_dom"}})
                        except Exception as e:
                            print(f"[Bridge] Error requesting initial DOM: {e}")
                    
                    # Wait for the first DOM to arrive
                    got_dom = await bridge.wait_for_dom(timeout=10.0)
                    if not got_dom:
                        print("[Agent] Warning: No initial DOM received from extension.")
                    
                    while step_count < MAX_AGENT_STEPS:
                        print(f"\n[Agent] ─── Step {step_count + 1} ───")
                        async with ws_lock:
                            try:
                                await ws.send_json({"type": "status", "content": "Exploring page..."})
                            except: pass
                        
                        # Ensure the tab is locked/glowing at every step (handles page loads)
                        if bridge.extension_ws:
                            try:
                                await bridge.extension_ws.send_json({"type": "action", "content": {"action": "lock"}})
                            except:
                                pass
                        
                        # ── 1. BUILD BROWSER STATE FROM CURRENT DOM (with empty-DOM retry) ──
                        MAX_DOM_RETRIES = 5
                        dom_retries = 0
                        dom_ready = False
                        
                        while dom_retries < MAX_DOM_RETRIES and not dom_ready:
                            dom_retries += 1

                            # Backoff delay on retries: first check instant, then 500ms, 1s, 1.5s, 2s
                            if dom_retries > 1:
                                backoff = 0.5 * (dom_retries - 1)
                                print(f"[Agent] Waiting {backoff:.1f}s before DOM retry {dom_retries}...")
                                await asyncio.sleep(backoff)

                            if bridge.latest_dom and bridge.latest_dom.get("elements"):
                                elements = bridge.latest_dom.get("elements", [])
                                
                                # Inclusive pruning: keep text, placeholders, interactive tags, OR editable elements.
                                pruned = [
                                    el for el in elements
                                    if el.get("text") or el.get("placeholder") or 
                                       el.get("tag") in ["input", "textarea", "button", "select", "a"] or
                                       el.get("role") == "textbox" or el.get("isContentEditable")
                                ][:500]
                                
                                if len(pruned) > 0:
                                    # We have usable elements — build state and proceed
                                    dom_lines = []
                                    for el in pruned:
                                        text_part = f" '{el['text']}'" if el.get('text') else ""
                                        placeholder_part = f" placeholder='{el['placeholder']}'" if el.get('placeholder') else ""
                                        href_part = f" href='{el['href']}'" if el.get('href') else ""
                                        editable_part = " [editable]" if el.get("isContentEditable") or el.get("role") == "textbox" else ""
                                        dom_lines.append(f"{el['id']}: <{el['tag']}>{text_part}{href_part}{placeholder_part}{editable_part}")
                                    
                                    dom_text = "\n".join(dom_lines) if dom_lines else "No interactive elements found."
                                    page_summary = bridge.latest_dom.get("pageText", "No summary available.")
                                    browser_state = f"URL: {bridge.latest_dom['url']}\nTitle: {bridge.latest_dom['title']}\n\nPage Summary: {page_summary}\n\nInteractive Elements:\n{dom_text}"
                                    print(f"[Agent] Page: {bridge.latest_dom['title']}")
                                    print(f"[Agent] Elements: {len(elements)} raw → {len(pruned)} pruned")
                                    _log_dom({**bridge.latest_dom, "elements": pruned})
                                    dom_ready = True
                                    break
                                else:
                                    # DOM is present but no pruned elements — retry
                                    if dom_retries < MAX_DOM_RETRIES:
                                        print(f"[Agent] ⚠ DOM has 0 interactive elements (attempt {dom_retries}/{MAX_DOM_RETRIES}). Retrying...")
                                        async with ws_lock:
                                            try:
                                                await ws.send_json({"type": "status", "content": f"Waiting for page to load ({dom_retries}/{MAX_DOM_RETRIES})..."})
                                            except: pass
                                        bridge.clear_dom()
                                        if bridge.extension_ws:
                                            try:
                                                await bridge.extension_ws.send_json({"type": "action", "content": {"action": "get_dom"}})
                                            except: pass
                                        await bridge.wait_for_dom(timeout=5.0)
                            else:
                                # No DOM at all
                                if dom_retries < MAX_DOM_RETRIES:
                                    print(f"[Agent] ⚠ No DOM available (attempt {dom_retries}/{MAX_DOM_RETRIES}). Retrying...")
                                    async with ws_lock:
                                        try:
                                            await ws.send_json({"type": "status", "content": f"Waiting for page to load ({dom_retries}/{MAX_DOM_RETRIES})..."})
                                        except: pass
                                    bridge.clear_dom()
                                    if bridge.extension_ws:
                                        try:
                                            await bridge.extension_ws.send_json({"type": "action", "content": {"action": "get_dom"}})
                                        except: pass
                                    await bridge.wait_for_dom(timeout=5.0)
                        
                        # If DOM is still empty/absent after retries, report error and abort
                        if not dom_ready:
                            error_msg = "The page is not responding or has loaded without interactive elements. Cannot proceed with this task."
                            print(f"[Agent] ✋ {error_msg}")
                            if bridge.extension_ws:
                                try:
                                    await bridge.extension_ws.send_json({"type": "action", "content": {"action": "unlock"}})
                                except: pass
                            final_answer_text = f"I encountered an error: {error_msg}"
                            session_steps.append({"thinking": "", "action": {"action": "answer", "text": final_answer_text}})
                            if is_new_chat:
                                async with ws_lock:
                                    await ws.send_json({"type": "status", "content": "Naming chat..."})
                                new_title = await ollama.generate_title(prompt)
                                chats.update_title(chat_id, new_title)
                            chats.add_message(chat_id, "assistant", final_answer_text, metadata={"steps": session_steps})
                            async with ws_lock:
                                try:
                                    await ws.send_json({"type": "answer", "text": final_answer_text, "metadata": {"steps": session_steps}})
                                    await ws.send_json({"type": "task_complete"})
                                except: pass
                            break  # exit the main agent loop
                        
                        # Build history: system + chat history + last 3 session steps
                        trimmed_steps = session_steps[-3:] if len(session_steps) > 3 else session_steps
                        session_history = history + [{"role": "assistant", "content": f"**Thinking:** {s['thinking']}\n```json\n{json.dumps(s['action'])}\n```"} for s in trimmed_steps]

                        # ── 2. ASK THE AGENT ──
                        print(f"[Agent] Calling Ollama (DOM-only)")
                        thinking_buffer = ""
                        first_token = True
                        token_count = 0
                        async for token in ollama.stream_think(current_prompt, browser_state, history=session_history, system_prompt=SYSTEM_PROMPT):
                            if first_token:
                                async with ws_lock:
                                    try:
                                        await ws.send_json({"type": "status", "content": f"Step {step_count + 1}"})
                                    except: pass
                                first_token = False
                            thinking_buffer += token
                            token_count += 1
                            async with ws_lock:
                                try:
                                    await ws.send_json({"type": "thinking", "content": token})
                                except: pass
                            print(token, end="", flush=True)
                        
                        print()
                        print(f"[Agent] Thinking complete. {token_count} tokens, {len(thinking_buffer)} chars.")

                        # ── 3. PARSE THE ACTION ──
                        parsed = ollama._parse_response(thinking_buffer)
                        action = parsed.get("action")
                        
                        if not action:
                            print("[Agent] No action parsed. Retrying...")
                            async with ws_lock:
                                try:
                                    await ws.send_json({"type": "status", "content": "No action decided. Retrying..."})
                                except: pass
                            continue

                        print(f"[Agent] Decided action: {action.get('action')}")

                        # Handle "answer" — task complete
                        if action.get("action") == "answer":
                            if bridge.extension_ws:
                                try:
                                    await bridge.extension_ws.send_json({"type": "action", "content": {"action": "unlock"}})
                                except: pass
                            
                            answer_text = action.get("text", "Task completed.")
                            session_steps.append({"thinking": thinking_buffer, "action": action})
                            
                            # Generate AI title if this was a new chat
                            if is_new_chat:
                                async with ws_lock:
                                    await ws.send_json({"type": "status", "content": "Naming chat..."})
                                new_title = await ollama.generate_title(prompt)
                                chats.update_title(chat_id, new_title)
                            
                            chats.add_message(chat_id, "assistant", answer_text, metadata={"steps": session_steps})
                            async with ws_lock:
                                try:
                                    await ws.send_json({"type": "answer", "text": answer_text, "metadata": {"steps": session_steps}})
                                    await ws.send_json({"type": "task_complete"})
                                except: pass
                            break

                        # ── 4. EXECUTE THE ACTION ──
                        session_steps.append({"thinking": thinking_buffer, "action": action})
                        async with ws_lock:
                            try:
                                await ws.send_json({"type": "action", "content": action})
                                await ws.send_json({"type": "status", "content": f"Executing {action.get('action')}..."})
                            except: pass
                        
                        bridge.latest_action_result = None
                        
                        if bridge.extension_ws:
                            ext_action = action.copy()
                            if ext_action["action"] == "type_and_enter":
                                ext_action["action"] = "type"
                                ext_action["press_enter"] = True
                                
                            # ★ CRITICAL: Clear DOM BEFORE sending the action.
                            # This ensures we wait for a FRESH dom_update from the NEW page state.
                            bridge.clear_dom()
                                
                            try:
                                await bridge.extension_ws.send_json({"type": "action", "content": ext_action})
                            except: pass
                            
                            # Wait for action_result from extension (max 4s)
                            idle_wait = 0
                            while bridge.latest_action_result is None and idle_wait < 40:
                                await asyncio.sleep(0.1)
                                idle_wait += 1
                            
                            action_result = bridge.latest_action_result or "Action timed out."
                            print(f"[Agent] Action executed in ~{idle_wait * 100}ms")
                            
                            # ★ CRITICAL: Now WAIT for the extension to push fresh DOM.
                            is_navigation = ext_action.get("action") in ["navigate", "type"] and (ext_action.get("press_enter") or ext_action.get("action") == "navigate")
                            dom_timeout = 10.0 if is_navigation else 5.0
                            
                            print(f"[Agent] Waiting for fresh DOM from extension (timeout: {dom_timeout}s)...")
                            got_fresh_dom = await bridge.wait_for_dom(timeout=dom_timeout, expect_new_url=is_navigation)
                            
                            if got_fresh_dom:
                                print(f"[Agent] ✓ Fresh DOM received from: {bridge.latest_dom.get('url', 'unknown')}")
                            else:
                                print(f"[Agent] ⚠ DOM timeout. Requesting explicitly...")
                                # Fallback: explicitly ask for DOM
                                bridge.clear_dom()
                                if bridge.extension_ws:
                                    try:
                                        await bridge.extension_ws.send_json({"type": "action", "content": {"action": "get_dom"}})
                                    except:
                                        pass
                                    await bridge.wait_for_dom(timeout=5.0)
                        else:
                            action_result = "Extension not available for control."
                        
                        step_count += 1
                        current_prompt = f"Original task: {prompt}\n\nLast action result: {action_result}\n\nContinue."
                        
                        async with ws_lock:
                            try:
                                await ws.send_json({"type": "step_complete", "content": {"thinking": thinking_buffer, "action": action}})
                            except: pass
                            
                    # If we exceeded MAX_AGENT_STEPS without answering
                    else:
                        if bridge.extension_ws:
                            try:
                                await bridge.extension_ws.send_json({"type": "action", "content": {"action": "unlock"}})
                            except:
                                pass
                        
                        # Generate AI title if this was a new chat
                        if is_new_chat:
                            async with ws_lock:
                                await ws.send_json({"type": "status", "content": "Naming chat..."})
                            new_title = await ollama.generate_title(prompt)
                            chats.update_title(chat_id, new_title)
                            
                        timeout_msg = f"I ran out of steps ({MAX_AGENT_STEPS}) before completing the task. Here's what I managed to do so far."
                        chats.add_message(chat_id, "assistant", timeout_msg, metadata={"steps": session_steps})
                        async with ws_lock:
                            try:
                                await ws.send_json({"type": "answer", "text": timeout_msg})
                            except: pass
                        async with ws_lock:
                            try:
                                await ws.send_json({"type": "task_complete"})
                            except: pass
                finally:
                    agent_running = False

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Error: {e}")
        traceback.print_exc()
    finally:
        connected_clients.remove(ws)
        # Final Unlock: Ensure the page is freed when the task ends or crashes
        if bridge.extension_ws:
            try:
                await bridge.extension_ws.send_json({"type": "action", "content": {"action": "unlock"}})
            except:
                pass
        
        try:
            await ws.close()
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8763, reload=False)
