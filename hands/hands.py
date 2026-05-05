# hands/hands.py
# Module 5: Hands — PyAutoGUI controller + AI-powered action planner

import logging
import time
import json
from typing import List, Optional
import pyautogui
from groq import Groq

from shared.types import ActionStep, HandsResult
from shared.config import (
    PYAUTOGUI_PAUSE, PYAUTOGUI_FAILSAFE,
    GROQ_API_KEY, MODEL_CHAT, ACTION_TIMEOUT
)

logger = logging.getLogger(__name__)

pyautogui.PAUSE = PYAUTOGUI_PAUSE
pyautogui.FAILSAFE = PYAUTOGUI_FAILSAFE

PLANNER_PROMPT = """You are an action planner for a computer control system.
Convert the user's instruction into a precise list of computer actions.

Available actions:
- navigate: open a URL in the default browser. target = full URL. Use for ALL websites.
- open: open a desktop application by name (e.g. Notepad, Spotify). NOT for websites.
- click_text: find text on screen using OCR and single-click it. target = exact visible text.
              Use for buttons, menu items, links, any visible text element.
- double_click_text: find text on screen and double-click it. Use to PLAY a song in Spotify or open a file.
- click: click at exact coordinates. target = "x,y". Only use when you know exact coords.
- type: type text. value = text. Handles Unicode, emoji, any language safely.
- hotkey: press key combination. target = e.g. "ctrl+c", "enter", "ctrl+v".
- scroll: scroll the page. target = "up" or "down". value = number of clicks.
- wait: pause. value = seconds (e.g. "3").
- double_click: double click. target = "x,y" or text.
- right_click: right click. target = "x,y".

Rules:
- Websites → navigate. Desktop apps → open. Visible UI elements → click_text.
- Always wait after navigate (at least 3s) so the page loads before clicking.
- For WhatsApp: use the search box to find contacts — don't assume they're visible.
- Keep steps minimal.

Examples:
"open youtube" → [{{"action": "navigate", "target": "https://youtube.com"}}]
"open notepad and type hello" → [{{"action": "open", "target": "notepad"}}, {{"action": "wait", "value": "1.5"}}, {{"action": "type", "value": "hello"}}]
"send hey to Miera on WhatsApp" → [
  {{"action": "navigate", "target": "https://web.whatsapp.com"}},
  {{"action": "wait", "value": "5"}},
  {{"action": "click_text", "target": "Search"}},
  {{"action": "type", "value": "Miera"}},
  {{"action": "wait", "value": "2"}},
  {{"action": "click_text", "target": "Miera"}},
  {{"action": "wait", "value": "1.5"}},
  {{"action": "click_text", "target": "Type a message"}},
  {{"action": "type", "value": "hey"}},
  {{"action": "hotkey", "target": "enter"}}
]
"click the submit button" → [{{"action": "click_text", "target": "Submit"}}]
"play Shape of You on Spotify" → [
  {{"action": "open", "target": "spotify:search:Shape%20of%20You"}},
  {{"action": "wait", "value": "3.5"}},
  {{"action": "double_click_text", "target": "Shape of You"}}
]

Return ONLY a valid JSON array of steps, no markdown, no explanation.

User instruction: {instruction}
Current screen context: {screen_context}
"""


class Hands:
    def __init__(self):
        self.groq = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
        self._eyes = None  # lazy — loaded only when click_text is first used
        logger.info("Hands initialized")

    def _get_eyes(self):
        """Lazy-load Eyes to avoid circular import on startup."""
        if self._eyes is None:
            from vision.eyes import Eyes
            self._eyes = Eyes()
        return self._eyes

    # ── Action Planner ────────────────────────────────────────────────────────

    def plan(self, instruction: str, screen_context: str = "") -> List[ActionStep]:
        """Use AI to convert natural language instruction into action steps."""
        if not self.groq:
            logger.warning("No Groq API — cannot plan actions")
            return []
        try:
            prompt = PLANNER_PROMPT.format(
                instruction=instruction,
                screen_context=screen_context or "Unknown"
            )
            response = self.groq.chat.completions.create(
                model=MODEL_CHAT,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.choices[0].message.content.strip()
            # Strip markdown code fences if present
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start == -1 or end == 0:
                logger.error(f"No JSON array in planner response: {raw}")
                return []
            steps_data = json.loads(raw[start:end])
            steps = [ActionStep(
                action=s.get("action", ""),
                target=s.get("target"),
                value=s.get("value")
            ) for s in steps_data]
            logger.debug(f"Planned {len(steps)} steps for: {instruction}")
            return steps
        except Exception as e:
            logger.error(f"Action planning failed: {e}")
            return []

    # ── Executor ──────────────────────────────────────────────────────────────

    def execute_step(self, step: ActionStep) -> bool:
        """Execute a single action step. Returns True on success."""
        try:
            if step.action == "navigate":
                import webbrowser
                url = step.target or step.value or ""
                if not url.startswith("http"):
                    url = f"https://{url}"
                webbrowser.open(url)
                logger.debug(f"Navigated to: {url}")

            elif step.action == "open":
                import subprocess, sys
                target = step.target or ""
                if sys.platform == "win32":
                    subprocess.Popen(f'start "" "{target}"', shell=True)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", "-a", target])
                else:
                    subprocess.Popen(["xdg-open", target])
                logger.debug(f"Opened: {target}")

            elif step.action == "click_text":
                # OCR-based click: find text on screen then click its coordinates
                target_text = step.target or step.value or ""
                coords = self._get_eyes().find_text(target_text)
                if coords:
                    pyautogui.click(coords[0], coords[1])
                    logger.debug(f"click_text: '{target_text}' at {coords}")
                else:
                    logger.warning(f"click_text: '{target_text}' not found on screen")
                    return False

            elif step.action == "click":
                if step.target and "," in step.target:
                    x, y = map(int, step.target.split(","))
                    pyautogui.click(x, y)
                else:
                    # Fall back to click_text if target looks like a label
                    if step.target:
                        coords = self._get_eyes().find_text(step.target)
                        if coords:
                            pyautogui.click(coords[0], coords[1])
                        else:
                            return False
                logger.debug(f"Clicked: {step.target}")

            elif step.action == "type":
                text_to_type = step.value or ""
                # Use clipboard paste for reliable Unicode support (emoji, Malay, etc.)
                try:
                    import pyperclip
                    pyperclip.copy(text_to_type)
                    pyautogui.hotkey("ctrl", "v")
                except ImportError:
                    # pyperclip not installed — fall back to write() for ASCII
                    pyautogui.write(text_to_type, interval=0.03)
                logger.debug(f"Typed: {text_to_type}")

            elif step.action == "hotkey":
                keys = (step.target or "").split("+")
                pyautogui.hotkey(*keys)
                logger.debug(f"Hotkey: {step.target}")

            elif step.action == "scroll":
                amount = int(step.value or 3)
                direction = -amount if step.target == "down" else amount
                pyautogui.scroll(direction)
                logger.debug(f"Scrolled: {step.target}")

            elif step.action == "wait":
                secs = float(step.value or 1)
                time.sleep(min(secs, ACTION_TIMEOUT))
                logger.debug(f"Waited: {secs}s")

            elif step.action == "screenshot":
                pass  # eyes module handles this

            elif step.action == "move":
                if step.target and "," in step.target:
                    x, y = map(int, step.target.split(","))
                    pyautogui.moveTo(x, y, duration=0.3)
                logger.debug(f"Moved to: {step.target}")

            elif step.action == "double_click_text":
                target_text = step.target or step.value or ""
                coords = self._get_eyes().find_text(target_text)
                if coords:
                    pyautogui.doubleClick(coords[0], coords[1])
                    logger.debug(f"double_click_text: '{target_text}' at {coords}")
                else:
                    logger.warning(f"double_click_text: '{target_text}' not found on screen")
                    return False

            elif step.action == "double_click":
                if step.target and "," in step.target:
                    x, y = map(int, step.target.split(","))
                    pyautogui.doubleClick(x, y)
                else:
                    pyautogui.doubleClick()
                logger.debug(f"Double clicked: {step.target}")

            elif step.action == "right_click":
                if step.target and "," in step.target:
                    x, y = map(int, step.target.split(","))
                    pyautogui.rightClick(x, y)
                logger.debug(f"Right clicked: {step.target}")

            else:
                logger.warning(f"Unknown action: {step.action}")
                return False

            return True

        except Exception as e:
            logger.error(f"Step execution failed ({step.action}): {e}")
            return False

    # ── Main Entry Point ──────────────────────────────────────────────────────

    def do(self, instruction: str, screen_context: str = "") -> HandsResult:
        """
        Full pipeline: plan actions from instruction → execute each step.
        Returns HandsResult with all steps and overall success.
        """
        steps = self.plan(instruction, screen_context)
        if not steps:
            return HandsResult(steps_executed=[], success=False, error="Could not plan actions")

        executed = []
        for step in steps:
            success = self.execute_step(step)
            executed.append(step)
            if not success:
                return HandsResult(steps_executed=executed, success=False,
                                   error=f"Failed at step: {step.action} {step.target}")
            time.sleep(PYAUTOGUI_PAUSE)

        logger.info(f"Completed {len(executed)} steps for: {instruction}")
        return HandsResult(steps_executed=executed, success=True)

    # ── Direct controls (bypass planner for simple commands) ──────────────────

    def click_at(self, x: int, y: int) -> bool:
        try:
            pyautogui.click(x, y)
            return True
        except Exception as e:
            logger.error(f"click_at failed: {e}")
            return False

    def type_text(self, text: str) -> bool:
        try:
            pyautogui.write(text, interval=0.03)
            return True
        except Exception as e:
            logger.error(f"type_text failed: {e}")
            return False

    def press(self, *keys) -> bool:
        try:
            pyautogui.hotkey(*keys)
            return True
        except Exception as e:
            logger.error(f"press failed: {e}")
            return False


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.DEBUG)
    hands = Hands()
    print("=== Test 1: Open YouTube ===")
    for s in hands.plan("open youtube"):
        print(f"  {s.action}: target={s.target}, value={s.value}")
    print()
    print("=== Test 2: WhatsApp message ===")
    for s in hands.plan('send "Hey, are you free?" to Miera on WhatsApp'):
        print(f"  {s.action}: target={s.target}, value={s.value}")
