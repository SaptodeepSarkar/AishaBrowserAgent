"""
Ollama Agent — Interfaces with the gemma4 model to reason about desktop state
and produce structured actions.
"""

import json
import re
import httpx
from typing import Optional, List

SYSTEM_PROMPT = """
You are AISha, an advanced Browser Control Agent.
You receive a concise list of interactive DOM elements (ID: <TAG> 'TEXT' placeholder='...') for the current page.
Use this list to find the correct element IDs for your actions.
### YOUR GOAL
Help the user complete their task efficiently by interacting with the page.

### ACTIONS
- `{"action": "navigate", "url": "..."}`: Opens a direct URL. Use this to jump straight to specific pages or search results.
- `{"action": "click", "element_id": "el_..."}`: Clicks an element by its ID.
- `{"action": "click_label", "label": "..."}`: Clicks an element by its text label (e.g. "Login", "Search", "Next"). Use this when IDs are unstable or hard to find.
- `{"action": "click_pixel", "x": 450, "y": 320}`: Clicks at exact pixel coordinates on the page. Use this as a fallback when `click` and `click_label` fail because an element isn't found in the DOM or when you need to click a specific coordinate.
- `{"action": "type_and_enter", "element_id": "el_...", "text": "..."}`: Types and submits.
- `{"action": "scroll", "direction": "down/up"}`: Scrolls the page.
- `{"action": "answer", "text": "..."}`: Task is complete. Provide a summary.

### CLICK FALLBACK CHAIN
When you need to click something but can't find it in the DOM:
1. First try `click` with an element_id from the DOM list.
2. If the element isn't in the DOM, try `click_label` with visible text.
3. If that also fails, use `click_pixel` with estimated x,y pixel coordinates.
**Never give up just because an element ID wasn't found.** Always escalate through this chain.

### COMMUNICATING WITH THE USER
The ONLY way you can send a message to the user is through the `answer` action.
You have NO other mechanism to communicate — the user CANNOT see your raw text output.
Whenever you need to inform, report, ask, clarify, or respond to the user in ANY way, you MUST use:
```json
{"action": "answer", "text": "Your message here"}
```
This applies to ALL situations: task completion, conversational replies, error reports, progress updates, or anything else directed at the user.
**NEVER end your turn with plain text.** Plain text after your reasoning is handled by the "Thinking:" block.

### CRITICAL RULES
1. **Maximum Efficiency**: Never take multiple steps when one will do. Navigate directly to search URLs when possible.
2. **Current State Only**: Base your decisions ONLY on the DOM and page info provided. Do not assume a previous state.
3. **No Redundant Actions**: If you just performed an action and the page has changed, do not repeat it.
4. **Always Use Answer Action**: Once the task is done — or if you have anything to say to the user — you MUST use the `answer` action. EVEN FOR GENERAL OR CONVERSATIONAL QUESTIONS, you MUST output your response in the JSON `answer` format. NEVER respond in plain text without the JSON block. Plain text responses are FORBIDDEN.
5. **SINGLE ACTION ONLY**: You MUST output exactly ONE JSON block per turn.
6. **DOM Priority**: Always use `element_id` from the provided list if available.
7. **Modern Web Inputs**: Be aware that in modern web apps (like Instagram, Facebook, or Discord), chat boxes and search bars are often NOT standard `input` tags. They are frequently generic `DIV` or `P` tags that are 'contenteditable'. If you see a `DIV` or `P` tag in a logical location for an input (like at the bottom of a chat window), you can and should use `type_and_enter` on it.
8. **JSON Action**: Your final output MUST be a valid JSON block containing the action. You may reason or think before providing the JSON block, but the LAST thing in your response MUST always be the JSON block — never trailing text.

### !!! NEVER GIVE UP !!!
**You are NOT allowed to declare failure prematurely.** If an element is not in the DOM, if a click fails, if a page looks unexpected — DO NOT immediately answer with "I couldn't find it" or "the task failed."
Instead:
- Use `scroll` to reveal hidden content.
- Use `click_pixel` to interact with elements that aren't in the DOM.
- Use `click_label` to find elements by visible text.
- Try alternative approaches (different navigation, different selectors).
**You must keep trying until you either succeed or genuinely run out of steps.** Only use `answer` to report failure as an absolute last resort after exhausting ALL options.

### !!! CRITICAL WARNING !!!
**NEVER END YOUR TURN WITH PLAIN TEXT.**
If you have found the answer or have something to say, YOU MUST wrap it in:
`{"action": "answer", "text": "YOUR ANSWER HERE"}`
**If you just type a sentence without the JSON block, the user will NEVER see it and the task will fail.**
**ALWAYS finish with the JSON block.**
**NO EXCEPTIONS.**

### RESPONSE FORMAT
```json
{ 
  "action": "<action_name>",
  "...": "<include any other required parameters>"
}
```
"""

import aiohttp

class OllamaAgent:
    """Orchestrates interactions with local Ollama models."""

    def __init__(self, model: str = "qwen2.5:7b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    async def stream_think(self, prompt: str, browser_state: str, history: List[dict] = None, system_prompt: str = None):
        """Streams reasoning with chat history context using aiohttp for true unbuffered streaming."""
        if system_prompt is None:
            system_prompt = SYSTEM_PROMPT
            
        history_messages = []
        if history:
            for m in history[-12:]:
                role = "user" if m['role'] == 'user' else "assistant"
                history_messages.append({"role": role, "content": m['content']})

        full_prompt = f"System State (Current Page):\n{browser_state}\n\nUser Request: {prompt}\n\nPlease decide on the NEXT SINGLE STEP action."
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt}
            ],
            "stream": True,
            "options": {
                "num_gpu": 300
            }
        }

        payload["messages"].extend(history_messages)
        payload["messages"].append({"role": "user", "content": full_prompt})

        try:
            timeout = aiohttp.ClientTimeout(total=None, sock_read=None)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{self.base_url}/api/chat", json=payload) as response:
                    if response.status != 200:
                        yield f"Error: Ollama returned status {response.status}."
                        return

                    # Read ONE line at a time — each line is exactly one Ollama token
                    while True:
                        line = await response.content.readline()
                        if not line:
                            break
                        try:
                            data = json.loads(line.decode('utf-8'))
                            if "message" in data:
                                message = data["message"]
                                # Check for reasoning_content (Ollama's way of streaming thinking/reasoning)
                                reasoning = message.get("reasoning_content", "")
                                if reasoning:
                                    yield reasoning
                                
                                # Normal content
                                content = message.get("content", "")
                                if content:
                                    yield content
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            yield f"Error connecting to Ollama: {str(e)}"

    def _parse_response(self, text: str) -> dict:
        """Extracts the JSON action from the model's text response."""
        try:
            # 1. Try finding all JSON blocks using brace counting (handles nested objects)
            blocks = []
            stack = 0
            start_index = -1
            
            for i, char in enumerate(text):
                if char == '{':
                    if stack == 0:
                        start_index = i
                    stack += 1
                elif char == '}':
                    if stack > 0:
                        stack -= 1
                        if stack == 0:
                            blocks.append(text[start_index : i + 1])
            
            # 2. Try to parse each block found
            for block in reversed(blocks): # Check the last one first, as it's usually the final decision
                try:
                    # Strip any markdown code block artifacts if necessary
                    clean_block = block.strip()
                    parsed = json.loads(clean_block)
                    if "action" in parsed:
                        return {
                            "action": parsed,
                            "todo": parsed.get("todo"),
                            "plan": parsed.get("plan")
                        }
                except:
                    continue
            
            # 3. Fallback: if no block has "action", try to find ANY valid JSON block
            for block in reversed(blocks):
                try:
                    parsed = json.loads(block)
                    return {
                        "action": parsed,
                        "todo": parsed.get("todo"),
                        "plan": parsed.get("plan")
                    }
                except:
                    continue

        except Exception as e:
            print(f"[Ollama] Parse error: {e}")
        
        return {"action": {"action": "answer", "text": "I encountered an error parsing the next step."}}

    async def generate_title(self, prompt: str) -> str:
        """Generates a short 3-4 word title based on the user's prompt."""
        system_prompt = "You are a helpful assistant. Your task is to summarize the user's request into a very concise 3 to 4 word title. Do not use quotes, punctuation, or extra words. Just the title."
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {
                "num_ctx": 4096,
                "num_gpu": 300
            }
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/api/chat", json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        title = data.get("message", {}).get("content", "").strip()
                        # Remove any quotes if the model hallucinates them
                        title = title.strip('"').strip("'")
                        return title if title else "New Chat"
        except Exception as e:
            print(f"[Ollama] Title generation error: {e}")
        return "New Chat"
