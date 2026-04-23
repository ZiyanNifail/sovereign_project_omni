# vision/eyes.py
# Module 4: Eyes — screenshot + OCR + vision AI fallback

import logging
import base64
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

import pyautogui
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
from PIL import Image
import anthropic

from shared.types import ScreenResult
from shared.config import (
    SCREENSHOTS_DIR, SCREENSHOT_FORMAT, OCR_LANGUAGE,
    VISION_FALLBACK_THRESHOLD, ANTHROPIC_API_KEY, MODEL_COMPLEX
)

logger = logging.getLogger(__name__)


class Eyes:
    def __init__(self):
        self.claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
        pyautogui.FAILSAFE = True
        logger.info("Eyes initialized")

    # ── Screenshot ────────────────────────────────────────────────────────────

    def capture(self, region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Path]:
        """Take a screenshot. region = (x, y, width, height) or None for full screen."""
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = SCREENSHOTS_DIR / f"screen_{ts}.png"
            if region:
                screenshot = pyautogui.screenshot(region=region)
            else:
                screenshot = pyautogui.screenshot()
            screenshot.save(str(path))
            logger.debug(f"Screenshot saved: {path}")
            return path
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return None

    # ── OCR ───────────────────────────────────────────────────────────────────

    def read_text(self, image_path: Path) -> Tuple[str, float]:
        """Extract text from image. Returns (text, confidence 0-1)."""
        try:
            img = Image.open(image_path)
            data = pytesseract.image_to_data(img, lang=OCR_LANGUAGE, output_type=pytesseract.Output.DICT)
            texts = [data["text"][i] for i in range(len(data["text"]))
                     if int(data["conf"][i]) > 30]
            confidences = [int(data["conf"][i]) for i in range(len(data["conf"]))
                           if int(data["conf"][i]) > 30]
            text = " ".join(texts).strip()
            avg_conf = (sum(confidences) / len(confidences) / 100) if confidences else 0.0
            return text, avg_conf
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return "", 0.0

    # ── Vision AI ─────────────────────────────────────────────────────────────

    def describe_visually(self, image_path: Path, question: str = "What do you see on this screen?") -> str:
        """Send screenshot to Claude vision when OCR isn't enough."""
        if not self.claude:
            return "Vision AI unavailable — no API key."
        try:
            with open(image_path, "rb") as f:
                img_data = base64.standard_b64encode(f.read()).decode("utf-8")
            response = self.claude.messages.create(
                model=MODEL_COMPLEX,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_data}},
                        {"type": "text", "text": question}
                    ]
                }]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Vision AI failed: {e}")
            return f"Could not analyze screen: {e}"

    # ── Main Entry Point ──────────────────────────────────────────────────────

    def see(self, region: Optional[Tuple] = None, question: Optional[str] = None) -> ScreenResult:
        """
        Full pipeline: capture → OCR → vision AI fallback if needed.
        Returns a ScreenResult with text and optional visual description.
        """
        path = self.capture(region)
        if not path:
            return ScreenResult(raw_text="", description=None, success=False, error="Screenshot failed")

        text, confidence = self.read_text(path)
        description = None

        # If OCR confidence is low or question requires visual understanding
        if confidence < VISION_FALLBACK_THRESHOLD or question:
            q = question or "Describe what is visible on this screen in detail."
            description = self.describe_visually(path, q)
            logger.debug("Used vision AI fallback")

        return ScreenResult(
            raw_text=text,
            description=description,
            screenshot_path=str(path),
            success=True
        )

    def see_and_describe(self) -> str:
        """Convenience method — returns a single string summary of the screen."""
        result = self.see()
        if result.description:
            return result.description
        return result.raw_text or "Nothing visible on screen."


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    eyes = Eyes()
    result = eyes.see()
    print(f"OCR text (first 200 chars): {result.raw_text[:200]}")
    print(f"Description: {result.description}")
    print(f"Success: {result.success}")
