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
EKLAS_SESSION_DIR = DATA_DIR / "eklas_session"
EKLAS_SESSION_DIR.mkdir(parents=True, exist_ok=True)


class Integrations:
    def __init__(self):
        # WhatsApp browser kept alive for the app lifetime — never reopened between calls
        self._playwright = None
        self._wa_context = None
        self._wa_page = None
        # Eklas browser also kept alive — never close between calls
        self._eklas_context = None
        self._eklas_page = None
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

    # ── WhatsApp shared helpers ───────────────────────────────────────────────

    async def _ensure_playwright(self):
        """Lazily start the Playwright instance once per app lifetime."""
        if self._playwright is None:
            from playwright.async_api import async_playwright as _ap
            self._playwright = await _ap().__aenter__()
        return self._playwright

    async def _get_whatsapp_page(self):
        """Return an active WhatsApp Web page without opening a new browser window.

        Priority:
          1. Reuse the page we already have open (fastest — no new window).
          2. Attach to a Chrome/Edge already running with --remote-debugging-port
             on ports 9222-9225 (works with the user's own browser).
          3. Launch/reuse our own persistent Chromium context (opens once, stays open).
        """
        import socket as _sock

        # 1 — reuse what we already have
        if self._wa_page:
            try:
                if not self._wa_page.is_closed() and "whatsapp" in self._wa_page.url:
                    logger.info("Reusing existing WhatsApp page")
                    return self._wa_page
            except Exception:
                pass
            self._wa_page = None

        p = await self._ensure_playwright()

        # 2 — attach to an already-open Chrome/Edge via CDP (no new window at all)
        for port in (9222, 9223, 9224, 9225):
            try:
                s = _sock.socket()
                s.settimeout(0.3)
                reachable = s.connect_ex(("localhost", port)) == 0
                s.close()
                if not reachable:
                    continue
                browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
                for ctx in browser.contexts:
                    for pg in ctx.pages:
                        try:
                            if "web.whatsapp.com" in (pg.url or ""):
                                logger.info(f"Attached to existing Chrome WhatsApp tab (CDP :{port})")
                                self._wa_page = pg
                                return pg
                        except Exception:
                            continue
            except Exception:
                continue

        # 3 — our own persistent context (created once, never closed between calls)
        if self._wa_context is None:
            self._wa_context = await p.chromium.launch_persistent_context(
                user_data_dir=str(WHATSAPP_SESSION_DIR),
                headless=False,
                args=["--no-sandbox"],
            )
            logger.info("Launched persistent WhatsApp browser context")

        # Reuse any WhatsApp page already open inside our context
        for pg in self._wa_context.pages:
            try:
                if not pg.is_closed() and "whatsapp" in (pg.url or ""):
                    self._wa_page = pg
                    return pg
            except Exception:
                continue

        # Open a fresh page and navigate
        pg = await self._wa_context.new_page()
        await pg.goto("https://web.whatsapp.com", timeout=60000)
        self._wa_page = pg
        return pg

    async def _wa_wait_for_login(self, page):
        """Block until WhatsApp Web is logged in and the chat list is visible."""
        await page.wait_for_selector('[data-testid="chat-list"], canvas', timeout=60000)
        if await page.query_selector("canvas"):
            logger.info("WhatsApp QR visible — waiting for user scan (120 s)…")
            await page.wait_for_selector('[data-testid="chat-list"]', timeout=120000)

    async def _wa_open_chat(self, page, contact: str) -> bool:
        """Search for *contact* and open their conversation. Returns True on success."""
        search = await self._query_first(page, [
            'div[contenteditable="true"][data-tab="3"]',
            '[aria-label="Search input textbox"]',
            '[data-testid="chat-list-search"]',
            '[role="textbox"][title*="Search"]',
            'div[data-lexical-editor="true"]',
        ])
        if not search:
            logger.warning("WhatsApp: search box not found")
            return False

        # WhatsApp uses the Lexical editor framework — fill() doesn't update its
        # internal state. Use real keyboard events: select-all → delete → type.
        await search.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(contact, delay=30)

        # Wait for the contact list to populate
        try:
            await page.wait_for_selector(
                "[data-testid='cell-frame-container'], [role='listitem'], [role='option']",
                timeout=4000,
            )
        except Exception:
            await page.wait_for_timeout(2000)

        try:
            await page.screenshot(path=str(DATA_DIR / "wa_search.png"))
        except Exception:
            pass

        # ── Strategy 1: click row whose title matches the contact name ────────
        for sel in [f'[title="{contact}"]', f'span[title*="{contact}"]']:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.click()
                    await page.wait_for_timeout(1200)
                    if await page.query_selector(
                        "#main footer, #main [data-testid='conversation-panel-wrapper'], "
                        "#main [aria-placeholder='Type a message']"
                    ):
                        logger.info(f"Opened chat via title selector: {sel}")
                        return True
            except Exception:
                continue

        # ── Strategy 2: keyboard ArrowDown + Enter (version-agnostic) ────────
        try:
            await page.keyboard.press("ArrowDown")
            await page.wait_for_timeout(300)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(1500)
            if await page.query_selector(
                "#main footer, #main [data-testid='conversation-panel-wrapper'], "
                "#main [aria-placeholder='Type a message']"
            ):
                logger.info("Opened chat via keyboard navigation")
                return True
        except Exception:
            pass

        # ── Strategy 3: first result row (generic selectors) ─────────────────
        first = await self._query_first(page, [
            "[data-testid='cell-frame-container']",
            "[role='listitem']",
            "[role='option']",
        ])
        if first:
            await first.click()
            await page.wait_for_timeout(1500)
            logger.info("Opened chat via list-item selector")
            return True

        logger.warning(f"WhatsApp: could not open chat for '{contact}'")
        try:
            await page.screenshot(path=str(DATA_DIR / "wa_no_contact.png"))
        except Exception:
            pass
        return False

    async def _wa_read_messages(self, page, limit: int) -> list[str]:
        """Return the last *limit* messages from the currently open chat."""
        try:
            await page.wait_for_selector(
                "#main div.copyable-text[data-pre-plain-text], "
                "#main [data-testid='msg-container'], "
                "#main [data-id]",
                timeout=8000,
            )
        except Exception:
            pass

        messages: list[str] = []

        # Primary: data-pre-plain-text carries "[HH:MM, DD/MM/YYYY] Name: "
        for scope in ("#main div.copyable-text[data-pre-plain-text]",
                      "div.copyable-text[data-pre-plain-text]"):
            msg_els = await page.query_selector_all(scope)
            if msg_els:
                break
        for el in (msg_els or [])[-limit:]:
            try:
                pre = (await el.get_attribute("data-pre-plain-text") or "").rstrip()
                text_el = await el.query_selector(
                    "span.selectable-text, [data-testid='msg-text'], span[class*='text']"
                )
                text = (await (text_el or el).inner_text()).strip()
                if text:
                    messages.append(f"{pre} {text}" if pre else text)
            except Exception:
                continue

        if not messages:
            # Fallback: msg-container testid
            for scope in ("#main [data-testid='msg-container']", "[data-testid='msg-container']"):
                containers = await page.query_selector_all(scope)
                if containers:
                    break
            for el in (containers or [])[-limit:]:
                try:
                    text_el = await el.query_selector(
                        "[data-testid='msg-text'], span.selectable-text, span[class*='text']"
                    )
                    if text_el:
                        text = await text_el.inner_text()
                        pre_el = await el.query_selector("div.copyable-text[data-pre-plain-text]")
                        sender = (
                            (await pre_el.get_attribute("data-pre-plain-text") or "").rstrip()
                            if pre_el else ""
                        )
                        messages.append(f"{sender} {text.strip()}" if sender else text.strip())
                except Exception:
                    continue

        if not messages:
            # Last resort: grab all visible text blobs inside #main
            try:
                raw = await page.inner_text("#main")
                lines = [l.strip() for l in raw.split("\n") if l.strip() and len(l.strip()) > 1]
                messages = lines[-limit:] if lines else []
            except Exception:
                pass

        if not messages:
            try:
                await page.screenshot(path=str(DATA_DIR / "wa_no_messages.png"))
                logger.info(f"No-messages screenshot saved: {DATA_DIR / 'wa_no_messages.png'}")
            except Exception:
                pass

        return messages

    # ── WhatsApp public API ───────────────────────────────────────────────────

    async def read_whatsapp(self, contact: Optional[str] = None, limit: int = 20) -> IntegrationResult:
        """Read recent WhatsApp messages, optionally filtering to a specific contact."""
        try:
            page = await self._get_whatsapp_page()
            await self._wa_wait_for_login(page)

            if contact:
                opened = await self._wa_open_chat(page, contact)
                if not opened:
                    return IntegrationResult(
                        source="whatsapp", content="", success=False,
                        error=f"Could not open chat for '{contact}'"
                    )

            messages = await self._wa_read_messages(page, limit)
            if not messages:
                return IntegrationResult(source="whatsapp", content="No messages found.", success=False)
            return IntegrationResult(source="whatsapp", content="\n".join(messages), success=True)

        except Exception as e:
            logger.error(f"WhatsApp read failed: {e}")
            self._wa_page = None   # force a fresh page on next call
            return IntegrationResult(source="whatsapp", content="", success=False, error=str(e))

    async def send_whatsapp(self, contact: str, message: str) -> IntegrationResult:
        """Send a WhatsApp message via WhatsApp Web."""
        try:
            page = await self._get_whatsapp_page()
            await self._wa_wait_for_login(page)

            opened = await self._wa_open_chat(page, contact)
            if not opened:
                return IntegrationResult(source="whatsapp", content="", success=False,
                                         error=f"Contact '{contact}' not found in WhatsApp")

            compose = await self._query_first(page, [
                "[data-testid='conversation-compose-box-input']",
                "div[contenteditable='true'][data-tab='10']",
                "[aria-placeholder='Type a message']",
                "footer div[contenteditable='true']",
                "#main div[contenteditable='true']",
            ])
            if not compose:
                try:
                    await page.screenshot(path=str(DATA_DIR / "wa_compose_debug.png"))
                except Exception:
                    pass
                return IntegrationResult(source="whatsapp", content="", success=False,
                                         error="Message input not found")

            await compose.click()
            # Use keyboard.type for reliable input on Lexical-editor contenteditable
            await page.keyboard.type(message, delay=30)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(800)
            return IntegrationResult(
                source="whatsapp",
                content=f"Sent to {contact}: \"{message}\"",
                success=True,
            )

        except Exception as e:
            logger.error(f"WhatsApp send failed: {e}")
            self._wa_page = None
            return IntegrationResult(source="whatsapp", content="", success=False, error=str(e))

    # ── LMS (Eklas) ───────────────────────────────────────────────────────────

    async def _get_eklas_page(self, lms_url: str, username: str, password: str):
        """Return a logged-in Eklas page. Browser stays open between calls."""
        from urllib.parse import urlparse
        lms_host = urlparse(lms_url).netloc

        p = await self._ensure_playwright()

        # Reset stale context
        if self._eklas_context is not None:
            try:
                _ = self._eklas_context.pages  # probe — raises if context is dead
            except Exception:
                self._eklas_context = None
                self._eklas_page = None

        if self._eklas_context is None:
            self._eklas_context = await p.chromium.launch_persistent_context(
                user_data_dir=str(EKLAS_SESSION_DIR),
                headless=False,
                args=["--no-sandbox"],
            )
            logger.info("Launched persistent Eklas browser context")

        # Reuse only if already on the LMS domain (session preserved)
        if self._eklas_page:
            try:
                if not self._eklas_page.is_closed() and lms_host in (self._eklas_page.url or ""):
                    logger.info("Reusing existing Eklas page")
                    await self._eklas_page.bring_to_front()
                    return self._eklas_page
            except Exception:
                pass
            self._eklas_page = None

        # Reuse any existing page (even blank) — navigate it rather than closing
        # Closing all pages then creating a new one crashes Chromium with Protocol error
        page = None
        for pg in self._eklas_context.pages:
            try:
                if not pg.is_closed():
                    page = pg
                    break
            except Exception:
                continue
        if page is None:
            page = await self._eklas_context.new_page()

        await page.goto(lms_url, timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=15000)

        # Click Login button if visible
        login_btn = await self._query_first(page, [
            'a:has-text("Login")', 'button:has-text("Login")',
            'a:has-text("Log in")', 'button:has-text("Log in")',
            'a:has-text("Sign in")', '[class*="login"]:not(input)',
            '#login-link', 'a[href*="login"]',
        ])
        if login_btn:
            await login_btn.click()
            await page.wait_for_load_state("networkidle", timeout=10000)
            await page.wait_for_timeout(1000)

        if username and password:
            user_field = await self._query_first(page, [
                'input[name="username"]', 'input[id="username"]',
                'input[name="user"]', 'input[name="login"]',
                'input[type="text"]', 'input[type="email"]',
            ])
            pass_field = await page.query_selector('input[type="password"]')

            if user_field and pass_field:
                await user_field.fill(username)
                await pass_field.fill(password)
                submit = await self._query_first(page, [
                    'input[type="submit"]', 'button[type="submit"]',
                    'button:has-text("Log in")', 'button:has-text("Login")',
                    'button:has-text("Sign in")',
                ])
                if submit:
                    await submit.click()
                else:
                    await page.keyboard.press("Enter")
                await page.wait_for_load_state("networkidle", timeout=20000)
                logger.info("Eklas login submitted")
            else:
                logger.warning("Eklas: login fields not found — may already be logged in")
        else:
            logger.warning("Eklas: LMS_USERNAME or LMS_PASSWORD missing in .env")

        self._eklas_page = page
        return page

    async def check_lms(self) -> IntegrationResult:
        """Log into Eklas LMS and retrieve announcements, assignments, and schedule.
        The browser window stays open after each call."""
        import os
        lms_url = os.getenv("LMS_URL", "")
        username = os.getenv("LMS_USERNAME", "")
        password = os.getenv("LMS_PASSWORD", "")

        if not lms_url:
            return IntegrationResult(source="lms", content="LMS_URL not set in .env file.",
                                     success=False, error="Missing LMS_URL")
        try:
            page = await self._get_eklas_page(lms_url, username, password)
            content = await page.inner_text("body")
            lines = [l.strip() for l in content.split("\n") if l.strip()]
            return IntegrationResult(source="lms", content="\n".join(lines[:120]), success=True)
        except Exception as e:
            logger.error(f"LMS check failed: {e}")
            self._eklas_page = None   # force fresh page on next call
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
        """Play a track on the already-running Spotify desktop app.

        Strategy:
          1. Open the spotify:search: URI — focuses the desktop app and navigates
             to search results without opening any browser.
          2. Wait for results to render.
          3. Use OCR (Eyes module) to find the song title on screen and
             double-click it to begin playback.
          4. Fallback: press Enter, which plays the top result in Spotify's
             keyboard navigation model.
        """
        import subprocess, sys
        import pyautogui

        try:
            encoded = urllib.parse.quote(query)
            uri = f"spotify:search:{encoded}"

            # Invoke the Spotify URI handler — works whether Spotify is open or closed.
            if sys.platform == "win32":
                subprocess.Popen(f'start "" "{uri}"', shell=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", uri])
            else:
                subprocess.Popen(["xdg-open", uri])

            # Give Spotify time to come to the foreground and render results.
            await asyncio.sleep(3.5)

            # OCR-based double-click: find the song title on screen and play it.
            try:
                from vision.eyes import Eyes
                eyes = Eyes()
                # Try progressively shorter search terms in case OCR misses the full title.
                words = query.split()
                candidates = [query] + [" ".join(words[:n]) for n in range(len(words) - 1, 0, -1)]
                for term in candidates:
                    if len(term) < 3:
                        continue
                    coords = eyes.find_text(term)
                    if coords:
                        pyautogui.doubleClick(coords[0], coords[1])
                        await asyncio.sleep(1)
                        logger.info(f"Spotify: double-clicked '{term}' at {coords}")
                        return IntegrationResult(
                            source="spotify",
                            content=f"Now playing '{query}' on Spotify.",
                            success=True,
                        )
            except Exception as ocr_err:
                logger.warning(f"Spotify OCR click failed: {ocr_err}")

            # Fallback: Spotify keyboard model — after search loads, pressing Enter
            # starts the first result if the results pane has focus.
            try:
                pyautogui.press("enter")
                await asyncio.sleep(0.8)
            except Exception:
                pass

            return IntegrationResult(
                source="spotify",
                content=f"Searched Spotify for '{query}'. If it didn't auto-play, double-click the track.",
                success=True,
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
