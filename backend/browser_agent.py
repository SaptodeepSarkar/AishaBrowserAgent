"""
Browser Agent — Playwright-based headless browser controller.
Provides full browser control: navigate, click, type, scroll, DOM reading.
"""

import asyncio
import os
import base64
import json
import re
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class BrowserAgent:
    """Controls a headless Chromium browser via Playwright."""

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._is_running = False

    async def start(self):
        """Launch the Firefox browser for better audio support."""
        if self._is_running:
            return
        
        # Using Firefox as requested by user - often better audio on Windows
        base_dir = os.path.dirname(__file__)
        user_data_dir = os.path.join(base_dir, "data", "firefox_profile")
        os.makedirs(user_data_dir, exist_ok=True)
        
        self._playwright = await async_playwright().start()
        
        try:
            print(f"[Browser] Launching Firefox Profile: {user_data_dir}")
            # Launch Firefox with persistent context
            self._context = await self._playwright.firefox.launch_persistent_context(
                user_data_dir,
                headless=False,
                viewport={"width": 1280, "height": 900},
                ignore_https_errors=True,
                # Firefox specific preferences for audio and stability
                args=[],
            )
            
            # Firefox Audio Preferences
            # Note: Playwright doesn't allow 'prefs' in launch_persistent_context easily, 
            # but standard settings usually work better in FF
            
            self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
            self._page.set_default_timeout(30000)
            
            self._is_running = True
            print(f"[Browser] AISha Firefox Started!")
            
            # Simple wake-up
            try:
                await self._page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(1)
                await self._page.mouse.click(10, 10)
            except: pass

        except Exception as e:
            print(f"[Browser] Failed to launch Firefox: {e}")
            # Fallback
            self._browser = await self._playwright.firefox.launch(headless=False)
            self._context = await self._browser.new_context()
            self._page = await self._context.new_page()
            self._is_running = True
            print("[Browser] Launched Clean Fallback Firefox")
        # Grant audio/media permissions
        await self._context.grant_permissions(["notifications", "microphone", "camera"])
        self._page = await self._context.new_page()
        self._page.set_default_timeout(15000)
        
        # Audio Hack: Clicking the page wakes up the audio engine in some cases
        await self._page.goto("https://www.google.com", wait_until="domcontentloaded")
        await asyncio.sleep(1)
        await self._page.mouse.click(0, 0) 
        
        self._is_running = True
        print("[Browser] Browser started with System Chrome & Enhanced Audio")

    async def stop(self):
        """Shut down the browser."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    # ── Actions ──────────────────────────────────────────────────────────

    async def navigate(self, url: str) -> dict:
        """Navigate to a URL."""
        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return {"success": True, "url": self._page.url, "title": await self._page.title()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def click(self, selector: str) -> dict:
        """Click an element by CSS selector with resilient fallbacks."""
        try:
            # Try a standard click first
            await self._page.click(selector, timeout=5000)
            await self._page.wait_for_load_state("domcontentloaded", timeout=10000)
            return {"success": True, "selector": selector}
        except Exception as e:
            try:
                # Fallback 1: Force click (bypasses hit-test)
                await self._page.click(selector, force=True, timeout=2000)
                return {"success": True, "selector": selector, "method": "force"}
            except Exception:
                try:
                    # Fallback 2: JS-based click (most resilient)
                    await self._page.eval_on_selector(selector, "el => el.click()")
                    return {"success": True, "selector": selector, "method": "js"}
                except Exception as e3:
                    return {"success": False, "error": f"All click methods failed: {str(e3)}"}

    async def click_text(self, text: str) -> dict:
        """Click an element containing specific text."""
        try:
            await self._page.get_by_text(text, exact=False).first.click(timeout=5000)
            await self._page.wait_for_load_state("domcontentloaded", timeout=10000)
            return {"success": True, "text": text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def type_text(self, selector: str, text: str, press_enter: bool = False) -> dict:
        """Type text into an input field (more robust than fill)."""
        try:
            # Focus and click first to trigger any focus events
            await self._page.click(selector, timeout=5000)
            
            # Clear the field first (select all + backspace)
            await self._page.focus(selector)
            await self._page.keyboard.press("Control+A")
            await self._page.keyboard.press("Backspace")
            
            # Type sequentially to trigger keyboard events (input, keydown, keyup)
            # This is crucial for search bars that show dropdowns
            await self._page.type(selector, text, delay=50) 
            
            if press_enter:
                await self._page.keyboard.press("Enter")
                await self._page.wait_for_load_state("domcontentloaded", timeout=5000)

            # Small wait for any UI to react
            await asyncio.sleep(1)
            return {"success": True, "selector": selector, "text": text, "pressed_enter": press_enter}
        except Exception as e:
            # Fallback to simple fill if complex typing fails
            try:
                await self._page.fill(selector, text, timeout=2000)
                if press_enter:
                    await self._page.keyboard.press("Enter")
                return {"success": True, "selector": selector, "text": text, "fallback": "fill", "pressed_enter": press_enter}
            except Exception as e2:
                return {"success": False, "error": f"Type failed: {str(e)}. Fallback fill failed: {str(e2)}"}

    async def press_key(self, key: str) -> dict:
        """Press a keyboard key (Enter, Tab, etc.)."""
        try:
            await self._page.keyboard.press(key)
            await asyncio.sleep(1)
            await self._page.wait_for_load_state("domcontentloaded", timeout=10000)
            return {"success": True, "key": key}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def scroll(self, direction: str = "down", amount: int = 500) -> dict:
        """Scroll the page."""
        try:
            delta = amount if direction == "down" else -amount
            await self._page.mouse.wheel(0, delta)
            await asyncio.sleep(0.5)
            return {"success": True, "direction": direction, "amount": amount}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def go_back(self) -> dict:
        """Navigate back."""
        try:
            await self._page.go_back(wait_until="domcontentloaded", timeout=10000)
            return {"success": True, "url": self._page.url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def go_forward(self) -> dict:
        """Navigate forward."""
        try:
            await self._page.go_forward(wait_until="domcontentloaded", timeout=10000)
            return {"success": True, "url": self._page.url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def wait(self, seconds: float = 2) -> dict:
        """Wait for a specified number of seconds."""
        await asyncio.sleep(min(seconds, 10))
        return {"success": True, "waited": seconds}

    # ── State Observation ────────────────────────────────────────────────

    async def get_page_info(self) -> dict:
        """Get current page URL and title."""
        try:
            return {
                "url": self._page.url,
                "title": await self._page.title(),
            }
        except Exception:
            return {"url": "", "title": ""}

    async def get_dom_summary(self) -> str:
        """Get a simplified DOM summary with interactive elements."""
        try:
            dom = await self._page.evaluate("""() => {
                function getInteractiveElements() {
                    const elements = [];
                    const interactiveSelectors = [
                        'a[href]', 'button', 'input', 'textarea', 'select',
                        '[role="button"]', '[role="link"]', '[role="textbox"]',
                        '[onclick]', '[tabindex]'
                    ];
                    const allElements = document.querySelectorAll(interactiveSelectors.join(','));
                    
                    let idx = 0;
                    allElements.forEach(el => {
                        if (el.offsetParent === null && el.tagName !== 'INPUT') return; // skip hidden
                        
                        const tag = el.tagName.toLowerCase();
                        const text = (el.textContent || '').trim().substring(0, 80);
                        const type = el.type || '';
                        const href = el.href || '';
                        const placeholder = el.placeholder || '';
                        const ariaLabel = el.getAttribute('aria-label') || '';
                        const name = el.name || '';
                        const id = el.id || '';
                        const value = el.value || '';
                        const role = el.getAttribute('role') || '';
                        
                        let selector = '';
                        if (id) selector = `#${id}`;
                        else if (name) selector = `${tag}[name="${name}"]`;
                        else if (ariaLabel) selector = `${tag}[aria-label="${ariaLabel}"]`;
                        else if (placeholder) selector = `${tag}[placeholder="${placeholder}"]`;
                        else {
                            selector = `${tag}:nth-of-type(${idx + 1})`;
                        }
                        
                        elements.push({
                            idx: idx,
                            tag: tag,
                            type: type,
                            text: text,
                            href: href ? href.substring(0, 100) : '',
                            placeholder: placeholder,
                            ariaLabel: ariaLabel,
                            selector: selector,
                            role: role,
                            value: value.substring(0, 50)
                        });
                        idx++;
                    });
                    return elements;
                }
                
                // Get page text content (trimmed)
                const bodyText = document.body ? document.body.innerText.substring(0, 2000) : '';
                
                return {
                    title: document.title,
                    url: window.location.href,
                    interactive_elements: getInteractiveElements(),
                    page_text: bodyText
                };
            }""")
            
            # Format into a readable summary
            lines = []
            lines.append(f"Page: {dom['title']}")
            lines.append(f"URL: {dom['url']}")
            lines.append("")
            lines.append("--- Interactive Elements ---")
            
            for el in dom.get("interactive_elements", [])[:50]:
                parts = [f"[{el['idx']}]", f"<{el['tag']}>"]
                if el.get("type"):
                    parts.append(f"type={el['type']}")
                if el.get("text"):
                    parts.append(f'"{el["text"]}"')
                if el.get("href"):
                    parts.append(f"href={el['href']}")
                if el.get("placeholder"):
                    parts.append(f'placeholder="{el["placeholder"]}"')
                if el.get("ariaLabel"):
                    parts.append(f'aria-label="{el["ariaLabel"]}"')
                if el.get("selector"):
                    parts.append(f"selector=\"{el['selector']}\"")
                lines.append(" ".join(parts))
            
            lines.append("")
            lines.append("--- Page Text (truncated) ---")
            lines.append(dom.get("page_text", "")[:1500])
            
            return "\n".join(lines)
        except Exception as e:
            return f"Error reading DOM: {e}"

    async def click_at(self, x: int, y: int) -> dict:
        """Click at specific coordinates."""
        try:
            await self._page.mouse.click(x, y)
            return {"success": True, "x": x, "y": y}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def execute_action(self, action: dict) -> dict:
        """Execute a parsed action from the Ollama agent."""
        action_type = action.get("action", "").lower()
        
        action_map = {
            "navigate": lambda: self.navigate(action.get("url", "")),
            "click": lambda: self.click(action.get("selector", "")),
            "click_at": lambda: self.click_at(action.get("x", 0), action.get("y", 0)),
            "click_text": lambda: self.click_text(action.get("text", "")),
            "type": lambda: self.type_text(action.get("selector", ""), action.get("text", ""), action.get("press_enter", False)),
            "press_key": lambda: self.press_key(action.get("key", "Enter")),
            "scroll": lambda: self.scroll(action.get("direction", "down"), action.get("amount", 500)),
            "go_back": lambda: self.go_back(),
            "go_forward": lambda: self.go_forward(),
            "wait": lambda: self.wait(action.get("seconds", 2)),
        }
        
        handler = action_map.get(action_type)
        if handler:
            result = await handler()
            return result
        else:
            return {"success": False, "error": f"Unknown action: {action_type}"}
