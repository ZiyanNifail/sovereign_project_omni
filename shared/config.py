# shared/config.py
# All configuration. Import this everywhere. Never hardcode values in modules.

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = Path(os.getenv("SOVEREIGN_DATA_DIR", BASE_DIR / "data"))
MEMORY_DB_PATH = DATA_DIR / "memory.db"
CHROMA_DIR = DATA_DIR / "chroma"
VOICE_MODELS_DIR = DATA_DIR / "voice_models"
FACES_DIR = DATA_DIR / "faces"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
AUDIO_DIR = DATA_DIR / "audio"

# Create dirs on import
for d in [DATA_DIR, CHROMA_DIR, VOICE_MODELS_DIR, FACES_DIR, SCREENSHOTS_DIR, AUDIO_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── API Keys ──────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ── User ──────────────────────────────────────────────────────────────────────
SOVEREIGN_USER_NAME = os.getenv("SOVEREIGN_USER_NAME", "User")

# ── AI Models ─────────────────────────────────────────────────────────────────
MODEL_CHAT = "llama-3.3-70b-versatile"         # Groq — all AI tasks

# Token limits
MAX_CONTEXT_TOKENS = 4000       # trim history above this
MAX_OUTPUT_TOKENS = 1024        # cap response length
CONTEXT_SUMMARY_THRESHOLD = 20  # summarize after N messages

# ── Voice ─────────────────────────────────────────────────────────────────────
WHISPER_MODEL = "base"          # base=fast, small=better, medium=best
TTS_SPEED = 1.0
DEFAULT_VOICE = "am_adam"       # Kokoro male voice (am_adam / am_michael / bm_george)

# ── Vision ────────────────────────────────────────────────────────────────────
SCREENSHOT_FORMAT = "PNG"
OCR_LANGUAGE = "eng"
VISION_FALLBACK_THRESHOLD = 0.3  # use vision AI if OCR confidence < 30%
# Override via TESSERACT_PATH env var if Tesseract is installed elsewhere
TESSERACT_PATH = os.getenv("TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

# ── Screen Control ────────────────────────────────────────────────────────────
PYAUTOGUI_PAUSE = 0.3           # pause between actions (seconds)
PYAUTOGUI_FAILSAFE = True       # move mouse to corner to kill
ACTION_TIMEOUT = 10             # seconds to wait for action to complete

# ── Memory ────────────────────────────────────────────────────────────────────
MEMORY_COLLECTION = "sovereign_memory"
MAX_MEMORY_RESULTS = 5          # how many memories to inject per request
SENTIMENT_WINDOW = 10           # rolling window for sentiment average

# ── WebSocket ─────────────────────────────────────────────────────────────────
WS_HOST = "localhost"
WS_PORT = 8765

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = DATA_DIR / "sovereign.log"
