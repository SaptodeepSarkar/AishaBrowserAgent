# AISha: Headless Browser & Desktop Automation Agent

This document serves as the primary context file for other AIs or developers working on the AISha project. It explains the core architecture, the agent execution loop, and the design philosophy.

## Overview
AISha is an advanced, locally-hosted browser control and desktop automation agent. It uses a local LLM (specifically **gemma4** via Ollama) to autonomously navigate the web, interact with web pages, and accomplish user tasks based on natural language prompts.

The system is designed with a **Single-Agent Architecture**. We recently deprecated a dual-agent (Planner + Executor) system in favor of a single, highly streamlined execution agent to maximize speed, reduce latency, and prevent conflicts between static plans and dynamic web environments.

## Core Components

### 1. The Execution Agent (`backend/ollama_agent.py`)
This is the "brain" of the operation. It receives the user's prompt and a structured representation of the current screen/browser state.
- **Streaming Reasoning:** The agent streams its response token-by-token (using `aiohttp` for unbuffered delivery) directly to the frontend so the user can read its `**Thinking:**` process in real-time.
- **JSON Actions:** After reasoning, the agent MUST output exactly one JSON block containing the specific action it wants to execute.
- **No Static Planning:** The agent does not use or edit static `todo.md` or `plan.md` files. It evaluates the DOM state at every step and decides the absolute best *next single action*.

### 2. The Orchestrator (`backend/server.py`)
A FastAPI backend that bridges the LLM, the desktop environment, the browser extension, and the user interface.
- **WebSocket Loop:** It maintains an execution loop (`while step_count < MAX_AGENT_STEPS:`) that continually fetches the latest DOM, passes it to the agent, parses the resulting JSON action, and routes that action to the executor.
- **History Management:** Uses `chat_manager.py` to persist all chats to local JSON files (`backend/data/chats/`). Every single reasoning step and executed action is saved in the `metadata.steps` array of the final answer message.

### 3. The Vision/Execution Bridge (`backend/desktop_agent.py` & Browser Extension)
- **DOM Extraction:** A browser extension continually scans the active webpage, extracting all interactive elements (buttons, links, inputs) and assigning them unique IDs (`el_1`, `el_2`, etc.).
- **State Formatting:** The backend formats these elements into a highly dense, token-efficient string: `el_ID: <TAG> 'TEXT' placeholder='...'` and feeds this to the agent.
- **Execution:** Actions like `click` or `type_and_enter` are mapped to the provided `el_ID` and executed natively on the desktop or injected via the extension.
- **Label-Based Interaction:** The agent can also use the `click_label` tool to interact with elements by their visible text, providing a robust fallback when IDs are unstable or missing.
- **Activity Indicator:** While the agent is active, the target browser tab displays a pulsing pink border glow, indicating that AISha is currently controlling the page. This lock starts from the user prompt and persists until the task is complete.

### 4. The Frontend (`frontend/src/`)
A React + Vite dashboard that provides a futuristic, live view of the agent at work.
- **Real-Time Feed:** Shows the agent's token-by-token thinking process (`ChatPanel.jsx`).
- **Browser View:** Displays the live URL and agent status (`BrowserView.jsx`).
- **Historical Steps:** The step history is natively embedded directly inside each chat message. If you look at a past chat, the complete execution path is rendered above the final answer, completely expanded by default.

## Agent Action Schema
The agent is restricted to the following JSON output actions (do not include a "reason" key, as reasoning is handled by the "Thinking:" block):
- `navigate`: Opens a direct URL. `{"action": "navigate", "url": "https://..."}`
- `click`: Clicks an element by ID. `{"action": "click", "element_id": "el_5"}`
- `click_label`: Clicks an element by its text label. `{"action": "click_label", "label": "Login"}`
- `click_pixel`: Clicks at exact pixel coordinates. `{"action": "click_pixel", "x": 450, "y": 320}`
- `type_and_enter`: Types text and submits (includes a robust form-submission fallback). `{"action": "type_and_enter", "element_id": "el_12", "text": "..."}`
- `scroll`: Scrolls the page. `{"action": "scroll", "direction": "down"}`
- `answer`: Completes the task. `{"action": "answer", "text": "..."}`

### Resilient Behavior
The agent is instructed to **never give up prematurely**. If DOM elements aren't found, the agent follows a fallback chain: `click` → `click_label` → `click_pixel`. It must exhaust all options before reporting failure via `answer`.

## Development Guidelines for AIs
1. **Maintain the Single-Agent Flow:** Do not attempt to re-introduce external Planner agents or markdown-based Todo lists. The system is intentionally designed to react dynamically to the DOM step-by-step.
2. **UI Component Integrity & Visibility:** The frontend is strictly designed so that the agent's step-by-step reasoning is ALWAYS visible by default. 
   - When modifying `ChatPanel.jsx`, ensure the historical `MessageSteps` component remains embedded *above* the final message text (`.message-text`). 
   - Never hide steps behind a "Show/Hide" toggle button or accordion. Transparency is key.
3. **Token Efficiency:** The prompt formatting in `server.py` is highly tuned to keep context windows small. Do not bloat the DOM representation.
4. **Strict Synchronization:** The server must explicitly clear `latest_dom` and send a `get_dom` command to the extension at the start of every step. Never proceed with reasoning until a fresh DOM update has been received for the current step.
5. **UI Compactness:** Reasoning steps in `ChatPanel.jsx` are constrained to a max-height with a scrollbar to prevent long summaries from overwhelming the screen.
6. **State Consistency:** All agent steps must be rigorously pushed to the `session_steps` array and saved to the JSON chat files so the frontend can retrieve them on reload.
