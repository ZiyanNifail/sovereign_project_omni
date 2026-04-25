# shared/types.py
# THE CONTRACT — all modules import from here. Never redefine these elsewhere.

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


# ── Enums ────────────────────────────────────────────────────────────────────

class Role(Enum):
    FRIEND = "friend"
    ASSISTANT = "assistant"
    COMPANION = "companion"
    MENTOR = "mentor"

class PersonalityStyle(Enum):
    EMPATHETIC = "empathetic"
    HONEST = "honest"
    HYPE = "hype"
    CALM = "calm"

class AIModel(Enum):
    HAIKU = "claude-haiku-4-5-20251001"
    SONNET = "claude-sonnet-4-6"
    GEMINI = "gemini-2.0-flash"
    GROQ = "groq-llama"
    LOCAL = "llama3"

class OrbState(Enum):
    IDLE = "idle"        # floating gently
    LISTENING = "listening"  # pulsing
    THINKING = "thinking"    # spinning
    SPEAKING = "speaking"    # expanding/contracting with voice


# ── Core Data Types ───────────────────────────────────────────────────────────

@dataclass
class Message:
    role: str                    # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    tokens_used: int = 0

@dataclass
class ConversationContext:
    messages: List[Message] = field(default_factory=list)
    system_prompt: str = ""
    total_tokens: int = 0
    max_tokens: int = 4000       # trim when exceeded

@dataclass
class BrainRequest:
    user_input: str
    context: ConversationContext
    role: Role = Role.FRIEND
    style: PersonalityStyle = PersonalityStyle.EMPATHETIC
    screen_context: Optional[str] = None   # what the AI currently sees
    memory_context: Optional[str] = None   # relevant memories injected

@dataclass
class BrainResponse:
    text: str
    model_used: AIModel
    tokens_used: int
    success: bool
    error: Optional[str] = None

@dataclass
class ScreenResult:
    raw_text: str                # OCR output
    description: Optional[str]  # vision AI description (if used)
    screenshot_path: Optional[str] = None
    success: bool = True
    error: Optional[str] = None

@dataclass
class ActionStep:
    action: str                  # "click", "type", "open", "scroll", "wait"
    target: Optional[str] = None # app name, coordinates, text to type
    value: Optional[str] = None  # additional param

@dataclass
class HandsResult:
    steps_executed: List[ActionStep]
    success: bool
    error: Optional[str] = None

@dataclass
class VoiceResult:
    transcript: str              # what user said
    confidence: float
    success: bool
    error: Optional[str] = None

@dataclass
class MemoryEntry:
    id: Optional[str]
    content: str
    category: str                # "sentiment", "preference", "event", "person"
    timestamp: datetime = field(default_factory=datetime.now)
    embedding: Optional[List[float]] = None

@dataclass
class UserProfile:
    name: str
    role: Role = Role.FRIEND
    style: PersonalityStyle = PersonalityStyle.EMPATHETIC
    sentiment_score: float = 0.5    # 0=negative, 1=positive
    avg_message_length: int = 50
    emoji_frequency: float = 0.0
    voice_model: str = "default"
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class PersonaConfig:
    role: Role
    style: PersonalityStyle
    user_name: str
    known_faces: Dict[str, str] = field(default_factory=dict)  # path -> name

@dataclass
class IntegrationResult:
    source: str                  # "whatsapp", "lms", "web", "instagram"
    content: str
    success: bool
    error: Optional[str] = None

@dataclass
class OrchestratorRequest:
    raw_input: str               # what user said or typed
    input_mode: str = "text"     # "text" or "voice"
    include_screen: bool = False # whether to capture screen first

@dataclass
class OrchestratorResponse:
    text_response: str
    orb_state: OrbState
    audio_path: Optional[str] = None
    actions_taken: List[str] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None
