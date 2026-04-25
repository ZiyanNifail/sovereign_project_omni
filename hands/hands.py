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
- navigate: open a URL in the default browser. Use this for ANY website request. target = full URL.
- open: open a desktop application by name (e.g. Notepad, Calculator, Spotify). NOT for websites.
- click: click at coordinates "x,y"
- type: type text (value = text to type)
- hotkey: press key combination e.g. "ctrl+c"
- scroll: scroll "up" or "down"
- wait: wait N seconds (value = seconds)
- double_click: double click at coordinates
- right_click: right click at coordinates

Rules:
- For websites and URLs, ALWAYS use navigate, never open.
- For desktop apps, use open.
- Keep steps minimal and direct.

Examples:
"open youtube" → [{{"action": "navigate", "target": "https://youtube.com"}}]
"open notepad" → [{{"action": "open", "target": "notepad"}}]
"open notepad and type hello" → [{{"action": "open", "target": "notepad"}}, {{"action": "wait", "value": "1.5"}}, {{"action": "type", "value": "hello"}}]

Return ONLY a valid JSON array of steps, no markdown, no explanation.

User instruction: {instruction}
Current screen context: {screen_context}
"""


class Hands:
    def __init__(self):
        self.groq = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
        logger.info("Hands initialized")

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

            elif step.action == "click":
                if step.target and "," in step.target:
                    x, y = map(int, step.target.split(","))
                    pyautogui.click(x, y)
                else:
                    # Try to find text on screen and click it
                    pyautogui.click()
                logger.debug(f"Clicked: {step.target}")

            elif step.action == "type":
                pyautogui.write(step.value or "", interval=0.03)
                logger.debug(f"Typed: {step.value}")

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
    logging.basicConfig(level=logging.DEBUG)
    hands = Hands()
    # Test planning only (no execution in test)
    steps = hands.plan("Open Notepad and type Hello World")
    for s in steps:
        print(f"  {s.action}: target={s.target}, value={s.value}")
