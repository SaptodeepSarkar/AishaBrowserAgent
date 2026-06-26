"""
Prompt Builder — Stitches system prompt + last action steps + browser state
into a single compact prompt for Ollama.

Design philosophy:
  - Ollama has no memory: every message is a fresh start.
  - Sending raw chat history (last 12 messages) wastes tokens on irrelevant steps.
  - Instead, send the system prompt + only the last 2 steps with their
    thinking, action JSON, result, and the URL they ran on.
  - This gives the LLM enough context ("what I just did and what happened")
    while keeping the window small (~4096 tokens).
"""

import json


def build_prompt(
    system_prompt: str,
    browser_state: str,
    user_prompt: str,
    steps: list,
) -> str:
    """
    Build a single compact prompt string.

    Args:
        system_prompt: The rules / identity prompt (already stripped by caller).
        browser_state: Current page description (URL, title, page text, elements).
        user_prompt: The user's request (current iteration prompt).
        steps: List of step dicts, each with keys:
               "thinking"  — what the LLM was thinking before the action
               "action"    — the JSON action dict that was taken
               "result"    — the action_result string returned by content.js
               "url"       — the page URL at the time of the action

    Returns:
        A single string suitable for ``role: "user"`` in the Ollama API.
    """
    parts = []

    # ── 1. System identity + rules (reinforced every turn) ──
    parts.append(system_prompt.strip())

    # ── 2. Last 2 action steps (compact history) ──
    if steps:
        recent = steps[-2:] if len(steps) > 2 else steps
        lines = ["\n### Previous Actions"]
        for i, step in enumerate(recent):
            idx = len(steps) - len(recent) + i + 1
            lines.append(f"\n--- Step {idx} ---")
            url = step.get("url", "")
            if url:
                lines.append(f"📍 On: {url}")
            thinking = step.get("thinking", "").strip()
            if thinking:
                # Keep only the first ~250 chars of thinking to save context
                lines.append(f"💭 Thought: {thinking[:250]}")
            action = step.get("action", {})
            if action:
                lines.append(f"⚡ Action: {json.dumps(action)}")
            result = step.get("result", "")
            if result:
                lines.append(f"✅ Result: {result[:200]}")
        parts.append("\n".join(lines))

    # ── 3. Current browser state ──
    parts.append(f"\n### Current Page\n{browser_state}")

    # ── 4. The task (user request) ──
    parts.append(f"\n### Task\n{user_prompt}")

    # ── 5. Instruction ──
    parts.append("Please decide on the NEXT SINGLE STEP action.")

    return "\n\n".join(parts)
