# integrations/web.py
# Module 6: Integrations — WhatsApp Web, LMS, DuckDuckGo search, Instagram, Spotify

import asyncio
import logging
import urllib.parse
from functools import partial
from typing import Optional

from shared.types import IntegrationResult
from shared.config import DATA_DIR

logger = logging.getLogger(__name__)

WHATSAPP_SESSION_DIR = DATA_DIR / "whatsapp_session"
WHATSAPP_SESSION_DIR.mkdir(parents=True, exist_ok=True)


class Integrations:
    def __init__(self):
        logger.info("Integrations initialized")

    async def _query_first(self, page, selectors: list):
        """Try CSS selectors in order; return first matching element or None."""
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    return el
            except Exception:
                continue
        return None

    # ── WhatsApp ──────────────────────────────────────────────────────────────

    async def read_whatsapp(self, contact: Optional[str] = None, limit: int = 20) -> IntegrationResult:
        """Open WhatsApp Web and read recent messages. QR scan required on first run."""
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            context = None
            try:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=str(WHATSAPP_SESSION_DIR),
                    headless=False,
                    args=["--no-sandbox"]
                )
                page = await context.new_page()
                await page.goto("https://web.whatsapp.com", timeout=60000)
                await page.wait_for_selector('[data-testid="chat-list"], canvas', timeout=60000)

                if await page.query_selector('canvas'):
                    logger.info("WhatsApp QR visible — waiting for user scan (120s)...")
                    await page.wait_for_selector('[data-testid="chat-list"]', timeout=120000)

                if contact:
                    search = await self._query_first(page, [
                        'div[contenteditable="true"][data-tab="3"]',
                        '[role="textbox"][title*="Search"]',
                        '[data-testid="chat-list-search"]',
                    ])
                    if search:
                        await search.click()
                        await search.fill(contact)
                        try:
                            await page.wait_for_selector('[role="listitem"]', timeout=5000)
                        except Exception:
                            pass
                        first = await self._query_first(page, [
                            '[role="listitem"]',
                            '[data-testid="cell-frame-container"]',
                        ])
                        if first:
                            await first.click()
                            await page.wait_for_timeout(1000)

                messages = []
                for el in (await page.query_selector_all('[data-testid="msg-container"]'))[-limit:]:
                    try:
                        text_el = await el.query_selector('[data-testid="msg-text"], span.selectable-text')
                        sender_el = await el.query_selector('[data-testid="msg-meta"] span, .copyable-text span')
                        if text_el:
                            text = await text_el.inner_text()
                            sender = await sender_el.inner_text() if sender_el else "unknown"
                            messages.append(f"{sender}: {text.strip()}")
                    except Exception:
                        continue

                if not messages:
                    return IntegrationResult(source="whatsapp", content="No messages found.", success=False)
                return IntegrationResult(source="whatsapp", content="\n".join(messages[-limit:]), success=True)

            except Exception as e:
                logger.error(f"WhatsApp read failed: {e}")
                return IntegrationResult(source="whatsapp", content="", success=False, error=str(e))
            finally:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass

    async def send_whatsapp(self, contact: str, message: str) -> IntegrationResult:
        """Send a WhatsApp message via WhatsApp Web using Playwright."""
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            context = None
            page = None
            try:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=str(WHATSAPP_SESSION_DIR),
                    headless=False,
                    args=["--no-sandbox"]
                )
                page = await context.new_page()
                await page.goto("https://web.whatsapp.com", timeout=60000)
                await page.wait_for_selector('[data-testid="chat-list"], canvas', timeout=60000)

                if await page.query_selector('canvas'):
                    logger.info("WhatsApp QR visible — waiting for scan (120s)...")
                    await page.wait_for_selector('[data-testid="chat-list"]', timeout=120000)

                search = await self._query_first(page, [
                    'div[contenteditable="true"][data-tab="3"]',
                    '[role="textbox"][title*="Search"]',
                    '[data-testid="chat-list-search"]',
                ])
                if not search:
                    return IntegrationResult(source="whatsapp", content="", success=False,
                                             error="Search box not found — is WhatsApp Web loaded?")

                await search.click()
                await search.fill(contact)
                try:
                    await page.wait_for_selector('[role="listitem"]', timeout=5000)
                except Exception:
                    return IntegrationResult(source="whatsapp", content="", success=False,
                                             error=f"Contact '{contact}' not found in WhatsApp")

                first = await self._query_first(page, [
                    '[role="listitem"]',
                    '[data-testid="cell-frame-container"]',
                ])
                if not first:
                    return IntegrationResult(source="whatsapp", content="", success=False,
                                             error=f"Contact '{contact}' not found in WhatsApp")
                await first.click()
                try:
                    await page.wait_for_selector('header', timeout=5000)
                except Exception:
                    pass

                compose = await self._query_first(page, [
                    'div[contenteditable="true"][data-tab="10"]',
                    'footer div[contenteditable="true"]',
                    '[data-testid="conversation-compose-box-input"]',
                ])
                if not compose:
                    return IntegrationResult(source="whatsapp", content="", success=False,
                                             error="Message input not found")

                await compose.click()
                await compose.type(message, delay=40)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(800)
                return IntegrationResult(
                    source="whatsapp",
                    content=f"Sent to {contact}: \"{message}\"",
                    success=True
                )

            except Exception as e:
                logger.error(f"WhatsApp send failed: {e}")
                try:
                    if page:
                        await page.screenshot(path=str(DATA_DIR / "whatsapp_debug.png"))
                        logger.info(f"Debug screenshot saved: {DATA_DIR / 'whatsapp_debug.png'}")
                except Exception:
                    pass
                return IntegrationResult(source="whatsapp", content="", success=False, error=str(e))
            finally:
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass

    # ── LMS ───────────────────────────────────────────────────────────────────

    async def check_lms(self) -> IntegrationResult:
        """Log into LMS and retrieve today's classes and upcoming deadlines."""
        import os
        lms_url = os.getenv("LMS_URL", "")
        username = os.getenv("LMS_USERNAME", "")
        password = os.getenv("LMS_PASSWORD", "")

        if not lms_url:
            return IntegrationResult(source="lms", content="LMS_URL not set in .env file.",
                                     success=False, error="Missing LMS_URL")

        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(lms_url, timeout=30000)

                if username and password:
                    user_field = await page.query_selector(
                        'input[type="email"], input[name="username"], input[id="username"]'
                    )
                    pass_field = await page.query_selector('input[type="password"]')
                    if user_field and pass_field:
                        await user_field.fill(username)
                        await pass_field.fill(password)
                        await page.keyboard.press("Enter")
                        await page.wait_for_load_state("networkidle", timeout=15000)

                content = await page.inner_text("body")
                await browser.close()
                lines = [l.strip() for l in content.split("\n") if l.strip()]
                return IntegrationResult(source="lms", content="\n".join(lines[:80]), success=True)

            except Exception as e:
                logger.error(f"LMS check failed: {e}")
                return IntegrationResult(source="lms", content="", success=False, error=str(e))

    # ── Web Search ────────────────────────────────────────────────────────────

    def _ddg_search(self, query: str, max_results: int) -> list:
        """Synchronous DuckDuckGo search — called via executor from async context."""
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                title = r.get("title", "")
                body = r.get("body", "")
                url = r.get("href", "")
                results.append(f"• {title}\n  {body[:200]}\n  {url}")
        return results

    async def search_web(self, query: str, max_results: int = 3) -> IntegrationResult:
        """DuckDuckGo search — no API key needed."""
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None, partial(self._ddg_search, query, max_results)
            )
            if not results:
                return IntegrationResult(source="web", content="No results found.", success=False)
            content = f"Web search results for '{query}':\n\n" + "\n\n".join(results)
            return IntegrationResult(source="web", content=content, success=True)
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return IntegrationResult(source="web", content="", success=False, error=str(e))

    # ── Instagram ─────────────────────────────────────────────────────────────

    async def analyze_instagram(self, url: str) -> IntegrationResult:
        """Open an Instagram post URL, extract caption and visible text."""
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_extra_http_headers({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                await page.goto(url, timeout=30000)
                await page.wait_for_timeout(2000)

                content_parts = []
                caption_el = await page.query_selector('meta[property="og:description"]')
                if caption_el:
                    caption = await caption_el.get_attribute("content")
                    if caption:
                        content_parts.append(f"Caption: {caption}")

                if await page.query_selector("main"):
                    body_text = await page.inner_text("main")
                    if body_text:
                        lines = [l.strip() for l in body_text.split("\n") if l.strip()]
                        content_parts.append("Visible text:\n" + "\n".join(lines[:20]))

                await browser.close()
                content = "\n\n".join(content_parts) or "Could not extract Instagram content."
                return IntegrationResult(source="instagram", content=content, success=bool(content_parts))

            except Exception as e:
                logger.error(f"Instagram analyze failed: {e}")
                return IntegrationResult(source="instagram", content="", success=False, error=str(e))

    # ── Spotify ───────────────────────────────────────────────────────────────

    async def play_spotify(self, query: str) -> IntegrationResult:
        """Open Spotify web player, search for query, and play the first track result."""
        from playwright.async_api import async_playwright
        encoded = urllib.parse.quote(query)
        search_url = f"https://open.spotify.com/search/{encoded}"

        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=False, args=["--no-sandbox"])
                page = await browser.new_page()
                await page.goto(search_url, timeout=30000)
                await page.wait_for_timeout(4000)

                play_btn = await self._query_first(page, [
                    '[data-testid="tracklist-row"]:first-child [data-testid="play-button"]',
                    'div[aria-rowindex="1"] button[aria-label*="Play"]',
                    'button[aria-label*="Play"]',
                ])
                if play_btn:
                    await play_btn.click()
                    await page.wait_for_timeout(2000)
                    return IntegrationResult(
                        source="spotify",
                        content=f"Playing '{query}' on Spotify web player.",
                        success=True
                    )
                return IntegrationResult(
                    source="spotify",
                    content=f"Opened Spotify for '{query}' — play button not found, try clicking manually.",
                    success=False,
                    error="Play button not found"
                )

            except Exception as e:
                logger.error(f"Spotify play failed: {e}")
                return IntegrationResult(source="spotify", content="", success=False, error=str(e))


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio
    import logging
    logging.basicConfig(level=logging.DEBUG)

    async def _test():
        integrations = Integrations()
        print("Testing web search...")
        result = await integrations.search_web("latest AI news today")
        print(f"Success: {result.success}")
        print(result.content[:300])
        print("\nIntegrations module: OK (web search tested)")
        print("WhatsApp, LMS, and Spotify require browser — test manually after setup.")

    asyncio.run(_test())
