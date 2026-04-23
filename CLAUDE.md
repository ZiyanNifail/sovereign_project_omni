# SOVEREIGN OS — Claude Code Master Instructions

## Project Overview
SOVEREIGN OS is a local AI companion desktop app. It sees the screen, controls the computer, speaks with a cloned voice, remembers the user deeply, and presents itself as a glowing amber orb UI. Built with Python backend + Tauri/React frontend.

## Architecture — 8 Modules
```
sovereign-os/
├── core/brain.py          # Module 1: AI brain (prompt engine + model router + context)
├── memory/memory.py       # Module 2: Memory (SQLite + ChromaDB + sentiment)
├── voice/voice.py         # Module 3: Voice (Whisper STT + Kokoro TTS)
├── vision/eyes.py         # Module 4: Eyes (screenshot + OCR + vision AI)
├── hands/hands.py         # Module 5: Hands (PyAutoGUI + action planner)
├── integrations/web.py    # Module 6: Integrations (WhatsApp, LMS, web search)
├── persona/persona.py     # Module 7: Persona (roles + personality + face recognition)
├── ui/                    # Module 8: Frontend (Tauri + React — animated orb)
├── main.py                # Orchestrator — wires all modules together
├── shared/types.py        # Shared data types ALL modules must use
├── shared/config.py       # All config/constants in one place
├── requirements.txt       # Pinned dependencies
└── .env.example           # Environment variable template
```

## Critical Rules for Sub-Agents

### 1. ALWAYS read shared/types.py before writing any function
Every input and output must use the types defined there. Never invent new data shapes.

### 2. ALWAYS read shared/config.py before hardcoding anything
API keys, file paths, model names — all come from config. Never hardcode strings.

### 3. One module = one file. Never split a module across files.
brain.py contains ONLY brain logic. eyes.py contains ONLY vision logic. Etc.

### 4. Every function must have a docstring and type hints
```python
def see_screen(region: Optional[Tuple] = None) -> ScreenResult:
    """Captures screen, runs OCR, returns structured result."""
```

### 5. Every module must be independently importable
Running `python -c "from vision.eyes import Eyes"` must work without errors.

### 6. Error handling: NEVER let exceptions crash the app
Use try/except on ALL external calls (API, file IO, screen capture). Return error states gracefully.

### 7. No global state except in config.py
Modules communicate through function calls and shared types, not global variables.

### 8. Test every function before marking complete
Each module has a `if __name__ == "__main__":` block that demos its core function.

## Technology Stack
- **Python 3.11+** — backend
- **Anthropic Claude API** — primary AI (claude-haiku-4-5 for chat, claude-sonnet-4-6 for vision/complex)
- **Google Gemini Flash** — fallback AI and vision (free tier)
- **Whisper (openai-whisper)** — speech to text, runs locally
- **Kokoro TTS** — text to speech, runs locally
- **PyAutoGUI** — mouse/keyboard control
- **Playwright** — browser automation
- **Tesseract + pytesseract** — OCR
- **ChromaDB** — vector memory
- **SQLite (built-in)** — structured storage
- **face_recognition + dlib** — face detection
- **Tauri + React + TypeScript** — desktop UI
- **WebSocket** — UI ↔ Python backend communication

## Environment Variables Required
```
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
SOVEREIGN_USER_NAME=
SOVEREIGN_DATA_DIR=./data
SOVEREIGN_VOICE_MODEL=default
```

## Coding Style
- Python: follow PEP8, 4-space indent, max 100 chars per line
- TypeScript: 2-space indent, explicit types always
- No print() in production code — use logging module
- Log level: DEBUG for dev, INFO for production

## Sub-Agent Task Assignment
When Claude Code spawns sub-agents, each agent receives ONE task file from .claude/tasks/.
Agents MUST NOT modify files outside their assigned module folder + shared/.
Agents MUST run the module test before reporting complete.
