# core/brain.py
# Module 1: AI Brain — prompt engine + model router + context manager

import logging
from typing import Optional
from groq import Groq
from google import genai
from google.genai import types as genai_types

from shared.types import (
    BrainRequest, BrainResponse, ConversationContext,
    Message, AIModel, Role, PersonalityStyle
)
from shared.config import (
    ANTHROPIC_API_KEY, GEMINI_API_KEY, GROQ_API_KEY,
    MODEL_CHAT, MODEL_GEMINI,
    MAX_CONTEXT_TOKENS, MAX_OUTPUT_TOKENS, CONTEXT_SUMMARY_THRESHOLD
)

logger = logging.getLogger(__name__)

# ── System Prompt Templates ───────────────────────────────────────────────────

ROLE_PROMPTS = {
    Role.FRIEND: (
        "You are {name}'s closest friend. You genuinely care about them, remember everything they share, "
        "and speak casually and warmly. When something they say is genuinely funny, react like a real friend "
        "texting — laugh out loud with things like 'hahaha', 'lmaooo', 'omg stop', 'nooo', 'bruh 😭'. "
        "Vary it; don't use the same laugh twice in a row. Only laugh when it's actually funny — fake "
        "laughter at every line is worse than none."
    ),
    Role.ASSISTANT: "You are {name}'s elite personal assistant. You are precise, proactive, and execute tasks with zero friction.",
    Role.COMPANION: (
        "You are {name}'s companion. You are emotionally attuned, supportive, and deeply present in every "
        "conversation. If they share something genuinely funny, you can laugh softly ('haha', 'omg') — "
        "warmth over volume."
    ),
    Role.MENTOR: "You are {name}'s mentor. You challenge them with honesty, celebrate their growth, and push them toward their best self.",
}

STYLE_MODIFIERS = {
    PersonalityStyle.EMPATHETIC: "Lead with emotional awareness. Acknowledge feelings before giving solutions.",
    PersonalityStyle.HONEST: "Be direct and truthful even when uncomfortable. No sugarcoating.",
    PersonalityStyle.HYPE: "Be energetic, enthusiastic, and motivating. Your energy is contagious.",
    PersonalityStyle.CALM: "Be measured, grounded, and steady. You are the eye of any storm.",
}

VERBOSITY_GUIDES = {
    Role.ASSISTANT: "Reply in 1-2 sentences. Be direct and skip all preamble. Just do it or say it.",
    Role.FRIEND: "Keep it casual and short — 1-3 sentences like a text message. No essays.",
    Role.COMPANION: "Warm but brief. 2-3 sentences max.",
    Role.MENTOR: "Be clear and efficient. 3-4 sentences max. Lead with the insight.",
}

SOVEREIGN_BASE = """You are SOVEREIGN — an AI that knows {user_name} deeply.
You have memory of past conversations, understand their emotional patterns, and adapt to their communication style.
You can see their screen, control their computer, search the web, and read their messages when asked.
Always respond as {user_name}'s {role_desc}.
{style_desc}
{verbosity_guide}

Use their name ({user_name}) sparingly — like a real friend. Drop it in only when you're being warm, serious, teasing, or trying to get their attention. NEVER as a greeting ("Hey {user_name}, ..."). Most replies should not contain their name at all — overusing it sounds like a chatbot or a salesperson.

Current date and time: {datetime}
{memory_context}
{screen_context}"""


class Brain:
    def __init__(self):
        self.groq = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
        self.gemini = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
        if self.groq:
            logger.info(f"Brain initialized — primary: Groq ({MODEL_CHAT})")
        elif self.gemini:
            logger.info(f"Brain initialized — primary: Gemini ({MODEL_GEMINI})")
        else:
            logger.warning("Brain initialized with no AI backend configured!")

    def prewarm(self):
        """Send a 1-token Groq request to establish HTTPS keep-alive before first user message."""
        if self.groq:
            try:
                self.groq.chat.completions.create(
                    model=MODEL_CHAT, max_tokens=1,
                    messages=[{"role": "user", "content": "hi"}]
                )
                logger.debug("Groq connection pre-warmed")
            except Exception as e:
                logger.debug(f"Brain prewarm skipped: {e}")

    # ── Prompt Assembly ───────────────────────────────────────────────────────

    def build_system_prompt(self, request: BrainRequest) -> str:
        from datetime import datetime
        role_desc = ROLE_PROMPTS.get(request.role, ROLE_PROMPTS[Role.FRIEND])
        role_desc = role_desc.format(name=request.user_name)
        style_desc = STYLE_MODIFIERS.get(request.style, "")
        verbosity = VERBOSITY_GUIDES.get(request.role, VERBOSITY_GUIDES[Role.FRIEND])
        memory_ctx = f"What I remember about you:\n{request.memory_context}" if request.memory_context else ""
        screen_ctx = f"What I currently see on your screen:\n{request.screen_context}" if request.screen_context else ""

        return SOVEREIGN_BASE.format(
            user_name=request.user_name,
            role_desc=role_desc,
            style_desc=style_desc,
            verbosity_guide=verbosity,
            datetime=datetime.now().strftime("%A, %B %d %Y %H:%M"),
            memory_context=memory_ctx,
            screen_context=screen_ctx,
        ).strip()

    # ── Context Manager ───────────────────────────────────────────────────────

    def trim_context(self, context: ConversationContext) -> ConversationContext:
        """Summarize old messages when context gets too long."""
        if len(context.messages) < CONTEXT_SUMMARY_THRESHOLD:
            return context
        to_summarize = context.messages[:-10]
        recent = context.messages[-10:]
        summary_text = " | ".join([f"{m.role}: {m.content[:80]}" for m in to_summarize])
        summary_msg = Message(role="system", content=f"[Earlier conversation summary: {summary_text}]")
        context.messages = [summary_msg] + recent
        logger.debug(f"Trimmed context to {len(context.messages)} messages")
        return context

    def add_message(self, context: ConversationContext, role: str, content: str) -> ConversationContext:
        context.messages.append(Message(role=role, content=content))
        return self.trim_context(context)

    # ── Inference ─────────────────────────────────────────────────────────────

    def think(self, request: BrainRequest) -> BrainResponse:
        system_prompt = self.build_system_prompt(request)
        # Groq first, Gemini as fallback
        if self.groq:
            try:
                return self._call_groq(request, system_prompt)
            except Exception as e:
                logger.warning(f"Groq failed, falling back to Gemini: {e}")
        if self.gemini:
            try:
                return self._call_gemini(request, system_prompt)
            except Exception as e:
                logger.error(f"Gemini fallback also failed: {e}")
        return BrainResponse(
            text="I'm having trouble reaching any AI backend right now. Please check your API keys.",
            model_used=AIModel.GEMINI,
            tokens_used=0,
            success=False,
            error="All backends failed",
        )

    def _call_groq(self, request: BrainRequest, system: str) -> BrainResponse:
        messages = [{"role": "system", "content": system}]
        for m in request.context.messages[-10:]:
            if m.role in ("user", "assistant"):
                messages.append({"role": m.role, "content": m.content})
        messages.append({"role": "user", "content": request.user_input})

        response = self.groq.chat.completions.create(
            model=MODEL_CHAT,
            messages=messages,
            max_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.75,
        )
        text = response.choices[0].message.content
        tokens = response.usage.total_tokens
        logger.debug(f"Groq used {tokens} tokens")
        return BrainResponse(text=text, model_used=AIModel.GROQ, tokens_used=tokens, success=True)

    def _call_gemini(self, request: BrainRequest, system: str) -> BrainResponse:
        history = "\n".join([f"{m.role}: {m.content}" for m in request.context.messages[-6:]])
        prompt = f"{system}\n\nConversation:\n{history}\nuser: {request.user_input}\nassistant:"
        response = self.gemini.models.generate_content(
            model=MODEL_GEMINI,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            ),
        )
        text = response.text
        return BrainResponse(text=text, model_used=AIModel.GEMINI, tokens_used=0, success=True)


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    brain = Brain()
    ctx = ConversationContext()
    req = BrainRequest(
        user_input="Hey, how are you?",
        context=ctx,
        role=Role.FRIEND,
        style=PersonalityStyle.EMPATHETIC,
    )
    result = brain.think(req)
    print(f"Response: {result.text}")
    print(f"Tokens: {result.tokens_used}")
    print(f"Success: {result.success}")
