# integrations/web.py
# Module 6: Integrations — WhatsApp Web, LMS, DuckDuckGo search, Instagram

import logging
import asyncio
from pathlib import Path
from typing import Optional

from shared.types import IntegrationResult
from shared.config import DATA_DIR

logger = logging.getLogger(__name__)

WHATSAPP_SESSION_DIR = DATA_DIR / "whatsapp_session"
WHATSAPP_SESSION_DIR.mkdir(parents=True, exist_ok=True)


class Integrations:
    def __init__(self):
        self._browser = None
        self._playwright = None
        logger.info("Integrations initialized")

    # ── Internal browser helper ───────────────────────────────────────────────

    def _run(self, coro):
        """Run async playwright code synchronously."""
        return asyncio.run(coro)

    async def _get_browser(self, playwright):
        """Get persistent browser context (saves WhatsApp session between runs)."""
        from playwright.async_api import async_playwright
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(WHATSAPP_SESSION_DIR),
            headless=False,  # Must be visible for QR scan and active interaction
            args=["--no-sandbox"]
        )
        return context

    # ── WhatsApp ──────────────────────────────────────────────────────────────

    def read_whatsapp(self, contact: Optional[str] = None, limit: int = 20) -> IntegrationResult:
        """
        Open WhatsApp Web and read recent messages.
        First run: shows QR code, user scans once. Session saved after.
        contact: filter to specific contact name (None = read all recent)
        """
        async def _read():
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                try:
                    context = await self._get_browser(p)
                    page = await context.new_page()
                    await page.goto("https://web.whatsapp.com", timeout=60000)

                    # Wait for app to load (either QR or chat list)
                    await page.wait_for_selector('[data-testid="chat-list"], canvas', timeout=60000)

                    # Check if QR code is showing (first run)
                    qr = await page.query_selector('canvas')
                    if qr:
                        logger.info("WhatsApp QR code visible — waiting for user to scan (60s)...")
                        await page.wait_for_selector('[data-testid="chat-list"]', timeout=120000)

                    messages = []

                    if contact:
                        # Search for specific contact
                        search = await page.query_selector('[data-testid="chat-list-search"]')
                        if search:
                            await search.click()
                            await search.fill(contact)
                            await page.wait_for_timeout(1500)
                            first_result = await page.query_selector('[data-testid="cell-frame-container"]')
                            if first_result:
                                await first_result.click()
                                await page.wait_for_timeout(1000)

                    # Read messages from current chat
                    msg_elements = await page.query_selector_all('[data-testid="msg-container"]')
                    for el in msg_elements[-limit:]:
                        try:
                            text_el = await el.query_selector('[data-testid="msg-text"], span.selectable-text')
                            sender_el = await el.query_selector('[data-testid="msg-meta"] span, .copyable-text span')
                            if text_el:
                                text = await text_el.inner_text()
                                sender = await sender_el.inner_text() if sender_el else "unknown"
                                messages.append(f"{sender}: {text.strip()}")
                        except Exception:
                            continue

                    await context.close()

                    if not messages:
                        return IntegrationResult(
                            source="whatsapp",
                            content="No messages found or chat not loaded.",
                            success=False
                        )

                    content = "\n".join(messages[-limit:])
                    return IntegrationResult(source="whatsapp", content=content, success=True)

                except Exception as e:
                    logger.error(f"WhatsApp read failed: {e}")
                    return IntegrationResult(source="whatsapp", content="", success=False, error=str(e))

        try:
            return self._run(_read())
        except Exception as e:
            return IntegrationResult(source="whatsapp", content="", success=False, error=str(e))

    # ── LMS ───────────────────────────────────────────────────────────────────

    def check_lms(self) -> IntegrationResult:
        """
        Log into LMS and retrieve today's classes and upcoming deadlines.
        Reads LMS_URL, LMS_USERNAME, LMS_PASSWORD from environment.
        """
        import os
        lms_url = os.getenv("LMS_URL", "")
        username = os.getenv("LMS_USERNAME", "")
        password = os.getenv("LMS_PASSWORD", "")

        if not lms_url:
            return IntegrationResult(
                source="lms",
                content="LMS_URL not set in .env file.",
                success=False,
                error="Missing LMS_URL"
            )

        async def _check():
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                try:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()
                    await page.goto(lms_url, timeout=30000)

                    # Generic login — works for most LMS platforms
                    if username and password:
                        user_field = await page.query_selector('input[type="email"], input[name="username"], input[id="username"]')
                        pass_field = await page.query_selector('input[type="password"]')
                        if user_field and pass_field:
                            await user_field.fill(username)
                            await pass_field.fill(password)
                            await page.keyboard.press("Enter")
                            await page.wait_for_load_state("networkidle", timeout=15000)

                    # Extract page text for AI to interpret
                    content = await page.inner_text("body")
                    await browser.close()

                    # Trim to relevant portion
                    lines = [l.strip() for l in content.split("\n") if l.strip()]
                    trimmed = "\n".join(lines[:80])
                    return IntegrationResult(source="lms", content=trimmed, success=True)

                except Exception as e:
                    logger.error(f"LMS check failed: {e}")
                    return IntegrationResult(source="lms", content="", success=False, error=str(e))

        try:
            return self._run(_check())
        except Exception as e:
            return IntegrationResult(source="lms", content="", success=False, error=str(e))

    # ── Web Search ────────────────────────────────────────────────────────────

    def search_web(self, query: str, max_results: int = 3) -> IntegrationResult:
        """
        DuckDuckGo search — no API key needed.
        Returns a plain text summary of top results.
        """
        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    title = r.get("title", "")
                    body = r.get("body", "")
                    url = r.get("href", "")
                    results.append(f"• {title}\n  {body[:200]}\n  {url}")

            if not results:
                return IntegrationResult(
                    source="web", content="No results found.", success=False
                )

            content = f"Web search results for '{query}':\n\n" + "\n\n".join(results)
            return IntegrationResult(source="web", content=content, success=True)

        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return IntegrationResult(source="web", content="", success=False, error=str(e))

    # ── Instagram ─────────────────────────────────────────────────────────────

    def analyze_instagram(self, url: str) -> IntegrationResult:
        """
        Open an Instagram post URL, extract caption and visible text.
        Pair with Eyes.describe_visually() for full image analysis.
        """
        async def _analyze():
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                try:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()

                    # Set user agent to avoid bot detection
                    await page.set_extra_http_headers({
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    })
                    await page.goto(url, timeout=30000)
                    await page.wait_for_timeout(2000)

                    # Extract post content
                    content_parts = []

                    # Caption
                    caption_el = await page.query_selector('meta[property="og:description"]')
                    if caption_el:
                        caption = await caption_el.get_attribute("content")
                        if caption:
                            content_parts.append(f"Caption: {caption}")

                    # Likes, comments visible text
                    body_text = await page.inner_text("main") if await page.query_selector("main") else ""
                    if body_text:
                        lines = [l.strip() for l in body_text.split("\n") if l.strip()]
                        content_parts.append("Visible text:\n" + "\n".join(lines[:20]))

                    await browser.close()
                    content = "\n\n".join(content_parts) or "Could not extract Instagram content."
                    return IntegrationResult(source="instagram", content=content, success=bool(content_parts))

                except Exception as e:
                    logger.error(f"Instagram analyze failed: {e}")
                    return IntegrationResult(source="instagram", content="", success=False, error=str(e))

        try:
            return self._run(_analyze())
        except Exception as e:
            return IntegrationResult(source="instagram", content="", success=False, error=str(e))


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    integrations = Integrations()

    print("Testing web search...")
    result = integrations.search_web("latest AI news today")
    print(f"Success: {result.success}")
    print(result.content[:300])
    print("\nIntegrations module: OK (web search tested)")
    print("WhatsApp and LMS require browser — test manually after setup.")
