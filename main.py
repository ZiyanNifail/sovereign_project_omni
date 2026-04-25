# main.py — SOVEREIGN OS Orchestrator

import asyncio, json, logging, sys, re
import websockets

from core.brain import Brain
from memory.memory import Memory
from vision.eyes import Eyes
from hands.hands import Hands
from voice.voice import Voice
from persona.persona import Persona
from shared.types import (
    BrainRequest, ConversationContext, OrchestratorRequest,
    OrchestratorResponse, OrbState, Role, PersonalityStyle
)
from shared.config import WS_HOST, WS_PORT, LOG_LEVEL, LOG_FILE, SOVEREIGN_USER_NAME

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("sovereign")


class SovereignOS:
    def __init__(self):
        logger.info("Booting SOVEREIGN OS...")
        self.brain = Brain()
        self.memory = Memory()
        self.eyes = Eyes()
        self.hands = Hands()
        self.voice = Voice()
        self.persona = Persona()
        self.context = ConversationContext()
        self.user_name = SOVEREIGN_USER_NAME
        cfg = self.persona.load_config(self.user_name)
        self.active_role = cfg.role
        self.active_style = cfg.style
        self._voice_loop_active = False
        logger.info(f"Ready — {self.user_name} | {self.active_role.value} | {self.active_style.value}")

    def _intent(self, text: str) -> str:
        t = text.lower()

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
        if any(w in t for w in ["whatsapp", "my messages", "my texts", "my chat"]):
            return "whatsapp"
        if any(w in t for w in ["lms", "my assignments", "my deadline", "check my class", "my class schedule"]):
            return "lms"
        if any(w in t for w in ["search for", "look up", "google this", "search the web", "find online"]):
            return "search"
        if re.search(r'\bwhat (is|are|was|were)\b', t) and any(w in t for w in ["search", "look up", "find"]):
            return "search"
        if any(w in t for w in ["instagram", "this post", "this ig"]):
            return "instagram"
        return "chat"

    async def process(self, req: OrchestratorRequest) -> OrchestratorResponse:
        intent = self._intent(req.raw_input)
        screen_ctx = None
        actions = []

        try:
            self.memory.log_message_style(req.raw_input)
            memory_ctx = self.memory.get_context_string(req.raw_input)

            if intent == "screen" or req.include_screen:
                r = self.eyes.see(question="What is on this screen right now? Be specific.")
                screen_ctx = r.description or r.raw_text
                actions.append("read_screen")

            elif intent == "control":
                snap = self.eyes.see()
                result = self.hands.do(req.raw_input, screen_context=snap.raw_text)
                actions.append(f"ran_{len(result.steps_executed)}_steps")
                if result.success:
                    await asyncio.sleep(1.5)
                    after = self.eyes.see()
                    screen_ctx = f"Done. Screen now shows: {after.raw_text[:250]}"
                else:
                    screen_ctx = f"Action failed: {result.error}"

            elif intent == "whatsapp":
                try:
                    from integrations.web import Integrations
                    r = Integrations().read_whatsapp()
                    screen_ctx = r.content if r.success else f"WhatsApp error: {r.error}"
                    actions.append("read_whatsapp")
                except Exception as e:
                    screen_ctx = f"WhatsApp unavailable: {e}"

            elif intent == "lms":
                try:
                    from integrations.web import Integrations
                    r = Integrations().check_lms()
                    screen_ctx = r.content if r.success else f"LMS error: {r.error}"
                    actions.append("check_lms")
                except Exception as e:
                    screen_ctx = f"LMS unavailable: {e}"

            elif intent == "search":
                try:
                    from integrations.web import Integrations
                    r = Integrations().search_web(req.raw_input)
                    screen_ctx = r.content if r.success else "Search failed"
                    actions.append("web_search")
                except Exception as e:
                    screen_ctx = f"Search unavailable: {e}"

            elif intent == "instagram":
                urls = re.findall(r'https?://\S+instagram\S+', req.raw_input)
                try:
                    from integrations.web import Integrations
                    if urls:
                        r = Integrations().analyze_instagram(urls[0])
                        screen_ctx = r.content if r.success else "Could not read post"
                    else:
                        snap = self.eyes.see(question="Describe this Instagram post in detail.")
                        screen_ctx = snap.description or snap.raw_text
                    actions.append("instagram")
                except Exception as e:
                    screen_ctx = f"Instagram unavailable: {e}"

            # ── Think ────────────────────────────────────────────────────────
            self.context = self.brain.add_message(self.context, "user", req.raw_input)
            resp = self.brain.think(BrainRequest(
                user_input=req.raw_input,
                context=self.context,
                role=self.active_role,
                style=self.active_style,
                screen_context=screen_ctx,
                memory_context=memory_ctx or None,
            ))

            if resp.success:
                self.context = self.brain.add_message(self.context, "assistant", resp.text)
                self.memory.add_memory(
                    f"User: '{req.raw_input[:80]}' → SOVEREIGN: '{resp.text[:80]}'",
                    category="conversation"
                )

            # ── Speak ────────────────────────────────────────────────────────
            audio = self.voice.speak(resp.text, block=False) if resp.success else None
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

    async def handle_client(self, websocket):
        logger.info(f"Client connected: {websocket.remote_address}")
        await websocket.send(json.dumps({
            "type": "ready", "orb_state": OrbState.IDLE.value,
            "message": f"SOVEREIGN OS online. Hello, {self.user_name}."
        }))
        try:
            async for raw in websocket:
                try:
                    data = json.loads(raw)
                    t = data.get("type", "message")

                    if t == "message":
                        await websocket.send(json.dumps({"type": "orb_state", "state": OrbState.THINKING.value}))
                        resp = await self.process(OrchestratorRequest(
                            raw_input=data.get("content", ""),
                            input_mode=data.get("mode", "text"),
                            include_screen=data.get("include_screen", False)
                        ))
                        await websocket.send(json.dumps({
                            "type": "response", "content": resp.text_response,
                            "orb_state": resp.orb_state.value,
                            "actions": resp.actions_taken, "success": resp.success
                        }))

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
                            await websocket.send(json.dumps({
                                "type": "response",
                                "content": resp.text_response,
                                "orb_state": resp.orb_state.value,
                                "actions": resp.actions_taken,
                                "success": resp.success,
                                "transcript": voice_result.transcript
                            }))
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
                await websocket.send(json.dumps({
                    "type": "response",
                    "content": resp.text_response,
                    "orb_state": resp.orb_state.value,
                    "actions": resp.actions_taken,
                    "success": resp.success,
                    "transcript": transcript
                }))

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
