# vision/eyes.py
# Module 4: Eyes — screenshot + OCR (no external vision API required)

import logging
import os
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

import pyautogui
import pytesseract
from PIL import Image

from shared.types import ScreenResult
from shared.config import (
    SCREENSHOTS_DIR, SCREENSHOT_FORMAT, OCR_LANGUAGE,
    VISION_FALLBACK_THRESHOLD, TESSERACT_PATH
)

if TESSERACT_PATH and os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

logger = logging.getLogger(__name__)


class Eyes:
    def __init__(self):
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

    # ── Main Entry Point ──────────────────────────────────────────────────────

    def see(self, region: Optional[Tuple] = None, question: Optional[str] = None) -> ScreenResult:
        """Capture screen and run OCR. Returns a ScreenResult with extracted text."""
        path = self.capture(region)
        if not path:
            return ScreenResult(raw_text="", description=None, success=False, error="Screenshot failed")

        text, confidence = self.read_text(path)
        description = text if question else None

        return ScreenResult(
            raw_text=text,
            description=description,
            screenshot_path=str(path),
            success=True
        )

    def see_and_describe(self) -> str:
        """Convenience method — returns OCR text from the current screen."""
        result = self.see()
        return result.raw_text or "Nothing visible on screen."

    # ── Text Locator ──────────────────────────────────────────────────────────

    def find_text(self, text: str) -> Optional[Tuple[int, int]]:
        """
        Find text on the live screen using OCR.
        Returns (x, y) screen coordinates of the text centre, or None if not found.
        """
        try:
            from collections import defaultdict
            screenshot = pyautogui.screenshot()
            data = pytesseract.image_to_data(
                screenshot, lang=OCR_LANGUAGE, output_type=pytesseract.Output.DICT
            )
            search = text.lower().strip()
            n = len(data["text"])

            lines: dict = defaultdict(list)
            for i in range(n):
                word = data["text"][i].strip()
                if not word or int(data["conf"][i]) < 25:
                    continue
                key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                lines[key].append(i)

            for idxs in lines.values():
                line_text = " ".join(data["text"][i] for i in idxs).lower()
                if search in line_text:
                    lefts  = [data["left"][i]                    for i in idxs]
                    tops   = [data["top"][i]                     for i in idxs]
                    rights = [data["left"][i] + data["width"][i] for i in idxs]
                    bots   = [data["top"][i] + data["height"][i] for i in idxs]
                    x = (min(lefts) + max(rights)) // 2
                    y = (min(tops)  + max(bots))   // 2
                    logger.debug(f"find_text: '{text}' found at ({x}, {y})")
                    return (x, y)

            logger.warning(f"find_text: '{text}' not found on screen")
            return None
        except Exception as e:
            logger.error(f"find_text failed: {e}")
            return None


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    eyes = Eyes()
    result = eyes.see()
    print(f"OCR text (first 200 chars): {result.raw_text[:200]}")
    print(f"Success: {result.success}")
