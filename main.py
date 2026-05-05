# main.py — SOVEREIGN OS Orchestrator

import asyncio, json, logging, random, sys, re, time, threading
import websockets

from core.brain import Brain
from memory.memory import Memory
from vision.eyes import Eyes
from hands.hands import Hands
from voice.voice import Voice
from persona.persona import Persona
from integrations.web import Integrations
from shared.types import (
    BrainRequest, ConversationContext, OrchestratorRequest,
    OrchestratorResponse, OrbState, Role, PersonalityStyle
)
from shared.config import WS_HOST, WS_PORT, LOG_LEVEL, LOG_FILE, SOVEREIGN_USER_NAME, MODEL_CHAT, DATA_DIR, BASE_DIR

# How many hours of absence count as "long gap" — only then will SOVEREIGN reach out unprompted.
PROACTIVE_GAP_HOURS = 6
LAST_SEEN_FILE = DATA_DIR / "last_seen.json"


def _read_last_seen() -> float:
    """Returns Unix timestamp of last user activity, or 0 if never seen."""
    try:
        if LAST_SEEN_FILE.exists():
            return float(json.loads(LAST_SEEN_FILE.read_text()).get("ts", 0))
    except Exception:
        pass
    return 0.0


def _write_last_seen() -> None:
    try:
        LAST_SEEN_FILE.write_text(json.dumps({"ts": time.time()}))
    except Exception as e:
        logging.getLogger("sovereign").error(f"last_seen write failed: {e}")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)]
)
# Suppress noisy HuggingFace/httpx probe requests (harmless 404s for optional model files)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
logger = logging.getLogger("sovereign")


# ── Human-like texting helpers ────────────────────────────────────────────────

THINKING_FILLERS = [
    "hmm...", "okay so...", "wait...", "ohh", "let me think",
    "mm", "alright so", "ok ok",
]
REACTIVE_FILLERS = [
    "oof", "oh wow", "yeahhh", "for real?", "ngl",
    "okay hear me out", "wait actually",
]

def _chunk_response(text: str) -> list[str]:
    """Split a response into natural texting-style chunks."""
    text = text.strip()
    if not text:
        return []
    # Split into sentences
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if not sentences:
        return [text]

    chunks: list[str] = []
    i = 0
    while i < len(sentences):
        sent = sentences[i]
        # Long sentence — break at commas
        if len(sent) > 140:
            parts = [p.strip() for p in re.split(r'(?<=,)\s+', sent) if p.strip()]
            chunks.extend(parts if parts else [sent])
            i += 1
            continue
        # Two consecutive short sentences — group them sometimes
        if (i + 1 < len(sentences) and len(sent) < 35
                and len(sentences[i + 1]) < 35 and random.random() < 0.5):
            chunks.append(f"{sent} {sentences[i + 1]}")
            i += 2
            continue
        chunks.append(sent)
        i += 1
    return chunks


def _typing_delay(chunk: str) -> float:
    """Realistic typing pause for a chunk — ~45 chars/sec + jitter."""
    base = len(chunk) / 45.0
    jitter = random.uniform(0.25, 0.75)
    return min(2.4, max(0.45, base + jitter))


class SovereignOS:
    def __init__(self):
        logger.info("Booting SOVEREIGN OS...")
        self.brain = Brain()
        self.memory = Memory()
        self.eyes = Eyes()
        self.hands = Hands()
        self.voice = Voice()
        self.persona = Persona()
        self.integrations = Integrations()
        self.context = ConversationContext()
        self.user_name = SOVEREIGN_USER_NAME
        cfg = self.persona.load_config(self.user_name)
        self.active_role = cfg.role
        self.active_style = cfg.style
        self._voice_loop_active = False
        self._greeted = False   # speak greeting only on the first client connection
        logger.info(f"Ready — {self.user_name} | {self.active_role.value} | {self.active_style.value}")
        threading.Thread(target=self._prewarm, daemon=True).start()

    def _prewarm(self):
        """Load heavy models in background so first user message is fast."""
        try:
            self.memory.prewarm()
            logger.info("Memory pre-warmed")
        except Exception as e:
            logger.warning(f"Memory prewarm failed: {e}")
        try:
            self.brain.prewarm()
            logger.info("Brain pre-warmed")
        except Exception as e:
            logger.warning(f"Brain prewarm failed: {e}")

    async def _describe_timetable(self, target_day: str = None) -> tuple[str, str | None]:
        """OCR the timetable image then ask Groq to extract the schedule for a given day."""
        import base64, io, os
        from datetime import datetime, timedelta
        import pytesseract
        from PIL import Image as _PIL
        from shared.config import TESSERACT_PATH

        timetable_path = BASE_DIR / "images" / "Timetable.jpg"
        if not timetable_path.exists():
            return "I couldn't find your timetable image in the images folder.", None

        with open(timetable_path, "rb") as f:
            img_bytes = f.read()
        data_url = f"data:image/jpeg;base64,{base64.b64encode(img_bytes).decode()}"

        if target_day is None:
            target_day = (datetime.now() + timedelta(days=1)).strftime("%A")

        def _ocr_then_parse():
            if TESSERACT_PATH and os.path.exists(TESSERACT_PATH):
                pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
            raw_text = pytesseract.image_to_string(_PIL.open(io.BytesIO(img_bytes)), lang="eng")
            resp = self.brain.groq.chat.completions.create(
                model=MODEL_CHAT,
                max_tokens=300,
                messages=[{"role": "user", "content": (
                    f"Here is OCR text from a university timetable:\n\n{raw_text}\n\n"
                    f"List all classes for {target_day} with their times and subject names. "
                    f"Bullet points, be concise. If none, say so."
                )}],
            )
            return resp.choices[0].message.content

        try:
            description = await asyncio.to_thread(_ocr_then_parse)
        except Exception as e:
            logger.error(f"Timetable read failed: {e}")
            description = f"Here's your timetable (couldn't parse {target_day} — see image above)."

        return description, data_url

    def _intent(self, text: str) -> str:
        t = text.lower()

        # Timetable queries — show image + vision-read schedule
        if any(w in t for w in ["timetable", "my timetable", "class tomorrow", "classes tomorrow",
                                 "class today", "classes today", "what class do i have",
                                 "what classes do i have", "show my schedule", "show timetable"]):
            return "timetable"

        # LMS check comes first so "open eklas" / "check eklas" don't fall into control
        if any(w in t for w in ["eklas", "lms", "learning system", "my assignments",
                                 "my deadline", "check my class", "my class schedule"]):
            return "lms"

        # Explicit computer-control phrases
        control_exact = [
            "launch ", "click on", "click the", "navigate to", "go to the website",
            "minimize ", "maximize ", "scroll down", "scroll up", "drag and drop",
            "right click", "alt tab", "alt-tab", "ctrl+", "ctrl-",
            "take a screenshot", "take screenshot", "download this", "download the",
            "install this", "install the", "write in the", "fill in the", "fill out",
            "run this", "run the", "run command", "run script",
        ]
        if any(w in t for w in control_exact):
            return "control"
        # "open X" — allow any target except filler words (catches "open youtube", "open chrome", etc.)
        if re.search(r'\bopen\s+(?!(?:up|about|minded|ended|source|ly|to|for|with|a\b|an\b|the\b))\S+', t):
            return "control"
        if re.search(r'\bpress\s+(ctrl|alt|shift|enter|tab|esc|f\d+|backspace|delete|space)\b', t):
            return "control"
        if re.search(r'\btype\s+["\']', t) or re.search(r'\btype\s+in\s+the\b', t):
            return "control"

        if any(w in t for w in ["what do you see", "look at my screen", "read my screen", "what's on my screen", "describe my screen"]):
            return "screen"
        # WhatsApp SEND — dedicated intent so Playwright handles it (not OCR/hands)
        if "whatsapp" in t and re.search(r'\b(send|message|text|tell|write|forward|reply)\b', t):
            return "whatsapp_send"
        # WhatsApp READ — generic whatsapp mention or "my messages/texts/chat"
        if any(w in t for w in ["whatsapp", "my messages", "my texts", "my chat"]):
            return "whatsapp"
        # (lms handled at top of function)
        if any(w in t for w in ["search for", "look up", "google this", "search the web", "find online"]):
            return "search"
        if re.search(r'\bwhat (is|are|was|were)\b', t) and any(w in t for w in ["search", "look up", "find"]):
            return "search"
        if any(w in t for w in ["instagram", "this post", "this ig"]):
            return "instagram"
        # Spotify — catches "play X on Spotify", "play X" (song/music context), "listen to X"
        if re.search(r'\b(play|listen to)\b', t) and any(
            w in t for w in ["spotify", "song", "music", "playlist", "album", "artist", "track"]
        ):
            return "spotify_play"
        if re.search(r'\b(play|listen to)\b.{0,40}\bspotify\b', t):
            return "spotify_play"
        return "chat"

    def _extract_whatsapp_params(self, instruction: str) -> tuple:
        """Use Groq to extract (contact, message) from a natural language WhatsApp send instruction."""
        try:
            resp = self.brain.groq.chat.completions.create(
                model=MODEL_CHAT,
                messages=[{"role": "user", "content":
                    f'From this instruction: "{instruction}"\n'
                    f'Return ONLY JSON: {{"contact": "name", "message": "text to send"}}'
                }],
                max_tokens=80,
            )
            raw = resp.choices[0].message.content.strip()
            start, end = raw.find("{"), raw.rfind("}") + 1
            data = json.loads(raw[start:end])
            return data.get("contact", "").strip(), data.get("message", "").strip()
        except Exception as e:
            logger.error(f"WhatsApp param extraction failed: {e}")
            return "", ""

    def _extract_whatsapp_contact(self, instruction: str) -> str:
        """Extract the contact name from a WhatsApp read instruction. Returns '' if none specified."""
        try:
            resp = self.brain.groq.chat.completions.create(
                model=MODEL_CHAT,
                messages=[{"role": "user", "content":
                    f'From: "{instruction}"\n'
                    f'Extract the WhatsApp contact name to look up. '
                    f'Return ONLY the name (e.g. "Fatiha"), or empty string if no specific contact.'
                }],
                max_tokens=20,
            )
            name = resp.choices[0].message.content.strip().strip('"\'')
            return "" if name.lower() in ("none", "empty", "no contact", "no specific contact", "") else name
        except Exception as e:
            logger.error(f"WhatsApp contact extraction failed: {e}")
            return ""

    async def process(self, req: OrchestratorRequest) -> OrchestratorResponse:
        intent = self._intent(req.raw_input)
        screen_ctx = None
        actions = []
        short_msg = len(req.raw_input.split()) < 6

        try:
            await asyncio.to_thread(self.memory.log_message_style, req.raw_input)
            memory_ctx = "" if short_msg else await asyncio.to_thread(
                self.memory.get_context_string, req.raw_input
            )

            if intent == "screen" or req.include_screen:
                r = await asyncio.to_thread(
                    lambda: self.eyes.see(question="What is on this screen right now? Be specific.")
                )
                screen_ctx = r.description or r.raw_text
                actions.append("read_screen")

            elif intent == "control":
                snap = await asyncio.to_thread(self.eyes.see)
                result = await asyncio.to_thread(self.hands.do, req.raw_input, snap.raw_text)
                actions.append(f"ran_{len(result.steps_executed)}_steps")
                if result.success:
                    await asyncio.sleep(1.5)
                    after = await asyncio.to_thread(self.eyes.see)
                    screen_ctx = f"Done. Screen now shows: {after.raw_text[:250]}"
                else:
                    screen_ctx = f"Action failed: {result.error}"

            elif intent == "whatsapp_send":
                contact, msg = await asyncio.to_thread(self._extract_whatsapp_params, req.raw_input)
                if not contact or not msg:
                    return OrchestratorResponse(
                        text_response="I couldn't figure out who to message or what to say. Try: \"send [message] to [name] on WhatsApp\".",
                        orb_state=OrbState.IDLE, success=False
                    )
                r = await self.integrations.send_whatsapp(contact, msg)
                if not r.success:
                    return OrchestratorResponse(
                        text_response=f"Couldn't send the message to {contact}: {r.error or 'WhatsApp failed to respond'}",
                        orb_state=OrbState.IDLE, success=False, error=r.error
                    )
                screen_ctx = f"WhatsApp message successfully sent to {contact}: \"{msg}\""
                actions.append("send_whatsapp")

            elif intent == "whatsapp":
                contact = await asyncio.to_thread(self._extract_whatsapp_contact, req.raw_input)
                r = await self.integrations.read_whatsapp(contact=contact or None)
                if not r.success:
                    return OrchestratorResponse(
                        text_response=f"I couldn't open WhatsApp: {r.error or 'no messages found'}. Make sure WhatsApp Web is set up (scan the QR code the first time).",
                        orb_state=OrbState.IDLE, success=False, error=r.error
                    )
                # Prefix forces the brain to report what's actually there, never hallucinate
                screen_ctx = (
                    "ACTUAL WhatsApp messages just retrieved — report these word for word. "
                    "DO NOT invent, paraphrase, or add any messages not shown here:\n\n"
                    + r.content
                )
                actions.append("read_whatsapp")

            elif intent == "timetable":
                from datetime import datetime, timedelta
                target_day = (datetime.now() + timedelta(days=1)).strftime("%A")
                # Check for "today" keywords
                t_lower = req.raw_input.lower()
                if any(w in t_lower for w in ["today", "right now", "this morning", "this afternoon"]):
                    target_day = datetime.now().strftime("%A")
                description, img_data = await self._describe_timetable(target_day)
                return OrchestratorResponse(
                    text_response=description,
                    image_data=img_data,
                    orb_state=OrbState.IDLE,
                    actions_taken=["timetable"],
                    success=True,
                )

            elif intent == "lms":
                r = await self.integrations.check_lms()
                if not r.success:
                    return OrchestratorResponse(
                        text_response=f"Couldn't load Eklas: {r.error or 'unknown error'}",
                        orb_state=OrbState.IDLE, success=False, error=r.error
                    )
                # Also append tomorrow's timetable so the brain can mention upcoming classes
                from datetime import datetime, timedelta
                tomorrow_day = (datetime.now() + timedelta(days=1)).strftime("%A")
                tt_desc, _ = await self._describe_timetable(tomorrow_day)
                screen_ctx = (
                    "ACTUAL content retrieved from Eklas LMS — summarise what's relevant "
                    "(assignments, deadlines, announcements, schedule). Report only what is shown:\n\n"
                    + r.content
                    + f"\n\n--- TOMORROW ({tomorrow_day}) FROM TIMETABLE ---\n{tt_desc}"
                )
                actions.append("check_lms")

            elif intent == "search":
                r = await self.integrations.search_web(req.raw_input)
                screen_ctx = r.content if r.success else "Search failed"
                actions.append("web_search")

            elif intent == "instagram":
                urls = re.findall(r'https?://\S+instagram\S+', req.raw_input)
                if urls:
                    r = await self.integrations.analyze_instagram(urls[0])
                    screen_ctx = r.content if r.success else "Could not read post"
                else:
                    snap = await asyncio.to_thread(
                        lambda: self.eyes.see(question="Describe this Instagram post in detail.")
                    )
                    screen_ctx = snap.description or snap.raw_text
                actions.append("instagram")

            elif intent == "spotify_play":
                query = re.sub(
                    r'\b(play|listen to|on spotify|spotify)\b', '',
                    req.raw_input, flags=re.IGNORECASE
                ).strip() or req.raw_input
                r = await self.integrations.play_spotify(query)
                screen_ctx = r.content if r.success else f"Spotify failed: {r.error}"
                actions.append("play_spotify")

            # ── Think ────────────────────────────────────────────────────────
            self.context = self.brain.add_message(self.context, "user", req.raw_input)
            resp = await asyncio.to_thread(self.brain.think, BrainRequest(
                user_input=req.raw_input,
                context=self.context,
                role=self.active_role,
                style=self.active_style,
                screen_context=screen_ctx,
                memory_context=memory_ctx or None,
                user_name=self.user_name,
            ))

            if resp.success:
                self.context = self.brain.add_message(self.context, "assistant", resp.text)
                if not short_msg:
                    await asyncio.to_thread(
                        self.memory.add_memory,
                        f"User: '{req.raw_input[:80]}' → SOVEREIGN: '{resp.text[:80]}'",
                        "conversation"
                    )

            # ── Speak ────────────────────────────────────────────────────────
            if resp.success:
                audio = await asyncio.to_thread(lambda: self.voice.speak(resp.text, block=False))
            else:
                audio = None
            if audio:
                actions.append("spoke")

            return OrchestratorResponse(
                text_response=resp.text,
                orb_state=OrbState.SPEAKING if audio else OrbState.IDLE,
                audio_path=str(audio) if audio else None,
                actions_taken=actions,
                success=resp.success,
                error=resp.error
            )

        except Exception as e:
            logger.error(f"process() crashed: {e}", exc_info=True)
            return OrchestratorResponse(
                text_response="Something went wrong on my end. I'm still here.",
                orb_state=OrbState.IDLE, success=False, error=str(e)
            )

    async def _send_proactive_message(self, websocket, gap_hours: float | None = None):
        """Generate and stream an unprompted check-in, like a friend who just thought of you."""
        try:
            from copy import deepcopy
            recent_mem = self.memory.get_context_string("recent yesterday today this week")

            # Time-aware framing — sounds different "next day" vs "after a week"
            if gap_hours is None:
                gap_phrase = ""
            elif gap_hours >= 24 * 7:
                gap_phrase = "It's been over a week since we last talked. "
            elif gap_hours >= 48:
                gap_phrase = "It's been a few days since we last talked. "
            elif gap_hours >= 20:
                gap_phrase = "It's the next day after our last conversation. "
            else:
                gap_phrase = "It's been several hours since we last talked. "

            cue = (
                f"{gap_phrase}Send one short, unprompted text — like a friend who's been "
                "thinking of me and finally has a moment to check in. "
                "Pick ONE: (a) ask a specific follow-up about something I shared last time, "
                "(b) casually check in on how I'm doing, or (c) reference a specific moment "
                "from your memory of me. 1 sentence, lowercase, texting voice. "
                "No 'hey there' / generic greetings — be natural like a real friend texting. "
                "If you have a specific memory to reference, prefer that — it's much warmer "
                "than a generic check-in."
            )

            # Use a deep-copied context so this internal cue never pollutes the real one
            temp_ctx = deepcopy(self.context)
            temp_ctx = self.brain.add_message(temp_ctx, "user", cue)

            resp = self.brain.think(BrainRequest(
                user_input=cue,
                context=temp_ctx,
                role=self.active_role,
                style=self.active_style,
                memory_context=recent_mem or None,
                user_name=self.user_name,
            ))

            if not (resp.success and resp.text and resp.text.strip()):
                return

            text = resp.text.strip()
            # Add only the assistant reply to the real context, not the cue
            self.context = self.brain.add_message(self.context, "assistant", text)
            self.memory.add_memory(
                f"SOVEREIGN reached out unprompted: '{text[:80]}'",
                category="proactive",
            )

            audio = self.voice.speak(text, block=False)
            mock = OrchestratorResponse(
                text_response=text,
                orb_state=OrbState.SPEAKING if audio else OrbState.IDLE,
                actions_taken=["proactive"],
                success=True,
            )
            await websocket.send(json.dumps({"type": "proactive"}))
            await self._stream_response(websocket, mock)
            logger.info(f"Proactive ping sent: {text[:80]}")
        except Exception as e:
            logger.error(f"Proactive send failed: {e}")

    async def _proactive_loop(self, websocket, state: dict):
        """Once per session: if user is returning after a long gap, send a 'welcome back' ping.
        No more frequent pinging — SOVEREIGN only reaches out when meaningful time has passed."""
        try:
            gap_seconds = state.get("gap_seconds_at_connect", 0.0)
            gap_hours = gap_seconds / 3600.0

            # Only fire if gap meets threshold (e.g. user came back the next day)
            if gap_hours < PROACTIVE_GAP_HOURS:
                logger.info(f"No welcome-back ping — gap was only {gap_hours:.1f}h")
                return

            # Brief settling delay so the connection is fully ready
            await asyncio.sleep(random.uniform(20, 45))

            if not state.get("enabled", True) or self.voice.is_speaking:
                return

            logger.info(f"Welcome-back ping after {gap_hours:.1f}h gap")
            await self._send_proactive_message(websocket, gap_hours=gap_hours)
            state["last_activity"] = asyncio.get_event_loop().time()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Proactive loop error: {e}")

    async def _stream_response(self, websocket, resp: OrchestratorResponse, transcript: str | None = None):
        """Send response as natural texting chunks with typing delays + occasional fillers."""
        # Errors / empty responses go through as a single message
        if not resp.success or not resp.text_response.strip():
            payload = {
                "type": "response",
                "content": resp.text_response,
                "orb_state": resp.orb_state.value,
                "actions": resp.actions_taken,
                "success": resp.success,
            }
            if transcript is not None:
                payload["transcript"] = transcript
            if resp.image_data:
                payload["image_data"] = resp.image_data
            await websocket.send(json.dumps(payload))
            return

        chunks = _chunk_response(resp.text_response)

        # ~25% of the time, prepend a thinking filler as its own bubble
        if chunks and random.random() < 0.25:
            filler = random.choice(THINKING_FILLERS)
            await websocket.send(json.dumps({"type": "typing"}))
            await asyncio.sleep(random.uniform(0.5, 1.1))
            await websocket.send(json.dumps({
                "type": "response_chunk",
                "content": filler,
                "is_final": False,
                "orb_state": OrbState.THINKING.value,
            }))
            await asyncio.sleep(random.uniform(0.35, 0.8))

        for i, chunk in enumerate(chunks):
            is_final = (i == len(chunks) - 1)
            await websocket.send(json.dumps({"type": "typing"}))
            await asyncio.sleep(_typing_delay(chunk))
            payload = {
                "type": "response_chunk",
                "content": chunk,
                "is_final": is_final,
                "orb_state": resp.orb_state.value if is_final else OrbState.THINKING.value,
            }
            if is_final:
                payload["actions"] = resp.actions_taken
                payload["success"] = resp.success
                if transcript is not None:
                    payload["transcript"] = transcript
                if resp.image_data:
                    payload["image_data"] = resp.image_data
            await websocket.send(json.dumps(payload))
            # Small breath between chunks (not after the last one)
            if not is_final:
                await asyncio.sleep(random.uniform(0.25, 0.55))

    async def handle_client(self, websocket):
        logger.info(f"Client connected: {websocket.remote_address}")

        # How long has the user been gone?
        last_seen = _read_last_seen()
        gap_seconds = (time.time() - last_seen) if last_seen else 0.0
        logger.info(f"Time since last seen: {gap_seconds / 3600:.2f}h")

        proactive_state = {
            "last_activity": asyncio.get_event_loop().time(),
            "enabled": True,
            "gap_seconds_at_connect": gap_seconds,
        }
        proactive_task = asyncio.create_task(self._proactive_loop(websocket, proactive_state))

        # First-run onboarding: ask the user to introduce themselves before anything else.
        if not self.persona._config or not self.persona._config.setup_complete:
            await websocket.send(json.dumps({
                "type": "needs_setup",
                "orb_state": OrbState.IDLE.value,
                "message": "Hi. I'm SOVEREIGN. What should I call you?",
            }))
        else:
            await websocket.send(json.dumps({
                "type": "ready", "orb_state": OrbState.IDLE.value,
                "message": "SOVEREIGN OS online.",
            }))
            # Speak the greeting once per session, right as the UI connects.
            if not self._greeted:
                self._greeted = True
                greeting = "Hello, sir."
                audio = await asyncio.to_thread(lambda: self.voice.speak(greeting, block=False))
                await websocket.send(json.dumps({
                    "type": "response_chunk",
                    "content": greeting,
                    "is_final": True,
                    "orb_state": OrbState.SPEAKING.value if audio else OrbState.IDLE.value,
                }))
        try:
            async for raw in websocket:
                try:
                    data = json.loads(raw)
                    t = data.get("type", "message")
                    proactive_state["last_activity"] = asyncio.get_event_loop().time()
                    # Persist last-seen on every real user input so next session's gap is accurate
                    if t in ("message", "voice_listen", "voice_loop_start"):
                        _write_last_seen()

                    if t == "message":
                        await websocket.send(json.dumps({"type": "orb_state", "state": OrbState.THINKING.value}))
                        resp = await self.process(OrchestratorRequest(
                            raw_input=data.get("content", ""),
                            input_mode=data.get("mode", "text"),
                            include_screen=data.get("include_screen", False)
                        ))
                        await self._stream_response(websocket, resp)

                    elif t == "set_name":
                        # First-run onboarding: user submits their name.
                        proposed = (data.get("name") or "").strip()
                        if not proposed:
                            await websocket.send(json.dumps({
                                "type": "error",
                                "message": "Name can't be empty — give me something to call you.",
                            }))
                        elif self.persona.set_user_name(proposed):
                            self.user_name = proposed
                            await websocket.send(json.dumps({
                                "type": "ready", "orb_state": OrbState.IDLE.value,
                                "message": f"got it. nice to meet you, {self.user_name}.",
                            }))
                            logger.info(f"Onboarding complete — user is {self.user_name}")
                        else:
                            await websocket.send(json.dumps({"type": "error", "message": "Could not save name."}))

                    elif t == "set_role":
                        self.active_role = Role(data.get("role", "friend"))
                        self.persona.set_role(self.active_role)
                        await websocket.send(json.dumps({"type": "ack", "message": f"Role → {self.active_role.value}"}))

                    elif t == "set_style":
                        self.active_style = PersonalityStyle(data.get("style", "empathetic"))
                        self.persona.set_style(self.active_style)
                        await websocket.send(json.dumps({"type": "ack", "message": f"Style → {self.active_style.value}"}))

                    elif t == "add_face":
                        ok = self.persona.add_face(data.get("image_path", ""), data.get("name", "unknown"))
                        await websocket.send(json.dumps({"type": "ack", "message": f"Face {'added' if ok else 'failed'}"}))

                    elif t == "voice_listen":
                        # One-shot: record mic → transcribe → process → respond
                        duration = int(data.get("duration", 5))
                        await websocket.send(json.dumps({"type": "orb_state", "state": OrbState.LISTENING.value}))
                        loop = asyncio.get_event_loop()
                        voice_result = await loop.run_in_executor(None, self.voice.listen, duration)
                        if voice_result.success and voice_result.transcript.strip():
                            await websocket.send(json.dumps({
                                "type": "voice_transcript",
                                "transcript": voice_result.transcript
                            }))
                            await websocket.send(json.dumps({"type": "orb_state", "state": OrbState.THINKING.value}))
                            resp = await self.process(OrchestratorRequest(
                                raw_input=voice_result.transcript,
                                input_mode="voice",
                                include_screen=data.get("include_screen", False)
                            ))
                            await self._stream_response(websocket, resp, transcript=voice_result.transcript)
                        else:
                            await websocket.send(json.dumps({
                                "type": "error",
                                "message": f"Nothing heard: {voice_result.error or 'empty transcript'}"
                            }))
                            await websocket.send(json.dumps({"type": "orb_state", "state": OrbState.IDLE.value}))

                    elif t == "voice_loop_start":
                        if not self._voice_loop_active:
                            self._voice_loop_active = True
                            asyncio.create_task(self._voice_loop(websocket))
                            await websocket.send(json.dumps({"type": "ack", "message": "Voice loop started — listening continuously"}))
                        else:
                            await websocket.send(json.dumps({"type": "ack", "message": "Voice loop already running"}))

                    elif t == "voice_loop_stop":
                        self._voice_loop_active = False
                        await websocket.send(json.dumps({"type": "ack", "message": "Voice loop stopped"}))

                    elif t == "proactive_toggle":
                        proactive_state["enabled"] = bool(data.get("enabled", True))
                        await websocket.send(json.dumps({
                            "type": "ack",
                            "message": f"Proactive {'on' if proactive_state['enabled'] else 'off'}"
                        }))

                    elif t == "proactive_now":
                        # Manual trigger — useful for demos
                        asyncio.create_task(self._send_proactive_message(websocket))

                    elif t == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))

                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    logger.error(f"Handler error: {e}")
                    await websocket.send(json.dumps({"type": "error", "message": str(e)}))

        except websockets.exceptions.ConnectionClosed:
            logger.info("Client disconnected")
        finally:
            self._voice_loop_active = False
            proactive_task.cancel()
            _write_last_seen()

    async def _voice_loop(self, websocket):
        """Continuously listen for voice input until voice_loop_stop is sent."""
        logger.info("Voice loop started")
        loop = asyncio.get_event_loop()
        while self._voice_loop_active:
            # Don't listen while SOVEREIGN is speaking
            if self.voice.is_speaking:
                await asyncio.sleep(0.3)
                continue
            try:
                await websocket.send(json.dumps({"type": "orb_state", "state": OrbState.LISTENING.value}))
                voice_result = await loop.run_in_executor(None, self.voice.listen, 5)

                if not self._voice_loop_active:
                    break

                transcript = voice_result.transcript.strip() if voice_result.success else ""
                if len(transcript) < 3:
                    # Skip noise / silence — stay in loop
                    continue

                await websocket.send(json.dumps({"type": "voice_transcript", "transcript": transcript}))
                await websocket.send(json.dumps({"type": "orb_state", "state": OrbState.THINKING.value}))

                resp = await self.process(OrchestratorRequest(
                    raw_input=transcript,
                    input_mode="voice"
                ))
                await self._stream_response(websocket, resp, transcript=transcript)

            except websockets.exceptions.ConnectionClosed:
                break
            except Exception as e:
                logger.error(f"Voice loop error: {e}")
                await asyncio.sleep(1)

        logger.info("Voice loop stopped")

    async def start(self):
        logger.info(f"WebSocket listening on ws://{WS_HOST}:{WS_PORT}")
        async with websockets.serve(self.handle_client, WS_HOST, WS_PORT):
            await asyncio.Future()


if __name__ == "__main__":
    s = SovereignOS()
    try:
        asyncio.run(s.start())
    except KeyboardInterrupt:
        logger.info("Shutdown.")
