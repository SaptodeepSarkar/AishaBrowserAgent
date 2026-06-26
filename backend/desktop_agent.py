import os
import time
import pyautogui

class DesktopAgent:
    """Controls the Windows desktop directly via PyAutoGUI and MSS."""
    
    def __init__(self):
        self._is_running = False
        self.screen_width, self.screen_height = pyautogui.size()
        # Set a small safety delay
        pyautogui.PAUSE = 0.5
        
    async def start(self):
        """Initialize the agent."""
        if self._is_running:
            return
            
        self._is_running = True
        print("[Desktop] Desktop Agent Active")

    async def stop(self):
        self._is_running = False

    async def execute_action(self, action):
        """Translate agent actions to PyAutoGUI commands."""
        name = action.get("action")
        
        try:
            if name == "click":
                # Convert percentage coordinates to pixels
                x_pct = float(action.get("x", 50))
                y_pct = float(action.get("y", 50))
                x = int((x_pct / 100) * self.screen_width)
                y = int((y_pct / 100) * self.screen_height)
                pyautogui.click(x, y)
                return f"Clicked at {x_pct}%, {y_pct}% ({x}, {y})"

            elif name == "type":
                text = action.get("text", "")
                press_enter = action.get("press_enter", False)
                pyautogui.write(text, interval=0.05)
                if press_enter:
                    pyautogui.press('enter')
                return f"Typed: {text}"

            elif name == "scroll":
                direction = action.get("direction", "down")
                amount = -500 if direction == "down" else 500
                pyautogui.scroll(amount)
                return f"Scrolled {direction}"

            elif name == "navigate":
                # We can't navigate via API, so we use the URL bar
                # Default Chrome URL bar shortcut is Ctrl+L
                pyautogui.hotkey('ctrl', 'l')
                time.sleep(0.2)
                pyautogui.write(action.get("url", ""), interval=0.05)
                pyautogui.press('enter')
                return f"Navigated to {action.get('url')}"

            elif name == "key":
                key = action.get("key", "enter")
                pyautogui.press(key)
                return f"Pressed key: {key}"

        except Exception as e:
            return f"Error executing {name}: {str(e)}"

        return "Unknown action"
