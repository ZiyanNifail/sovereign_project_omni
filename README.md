# SOVEREIGN OS

A local AI companion that sees your screen, controls your computer, speaks with a voice, and remembers you deeply. Runs as an animated amber orb on your desktop.

## Features

- **AI Brain** — Llama 3.3 70B via Groq (fast, free), Gemini as fallback
- **Screen Vision** — screenshots + OCR via Tesseract + vision AI fallback
- **Computer Control** — AI-planned mouse/keyboard actions via PyAutoGUI
- **Voice** — Whisper STT + Kokoro TTS (runs locally, no cloud)
- **Memory** — SQLite + ChromaDB vector store (remembers conversations)
- **Face Recognition** — dlib + face_recognition
- **Web Search** — DuckDuckGo, Playwright browser automation
- **UI** — Animated amber orb (React + Canvas)

## Requirements

- Windows 10/11
- Python 3.11+
- Node.js 18+
- Internet connection (for setup and AI API calls)

## Quick Start

### 1. Clone

```bash
git clone https://github.com/your-username/sovereign-os.git
cd sovereign-os
```

### 2. Get a free Groq API key

Go to **https://console.groq.com** → create an account → copy your API key.

### 3. Run setup

```
setup.bat
```

This installs everything automatically:
- All Python packages
- Tesseract OCR binary (via winget)
- CMake + Visual Studio Build Tools (for dlib)
- dlib + face_recognition (compiled from source)
- Kokoro TTS model files (~340 MB, downloaded once)
- Node.js UI dependencies
- Creates your `.env` file

> Setup takes ~10–15 minutes on first run (mostly VS Build Tools + dlib compilation).

### 4. Fill in `.env`

Setup opens `.env` automatically. At minimum set:

```env
GROQ_API_KEY=your_groq_key_here
SOVEREIGN_USER_NAME=YourName
```

### 5. Launch

```
start.bat
```

Opens the orb UI at **http://localhost:5173** and starts the WebSocket backend.

## Usage

Type commands naturally in the orb input:

| Intent | Example |
|--------|---------|
| Chat | `how are you?` |
| Open app | `open Chrome` |
| Go to URL | `navigate to youtube.com` |
| Type text | `type Hello World` |
| Keyboard | `press ctrl+c` |
| Read screen | `what do you see?` |
| Web search | `search for Python tutorials` |
| Scroll | `scroll down` |

## Architecture

```
sovereign-os/
├── core/brain.py        # AI brain (Groq primary, Gemini fallback)
├── memory/memory.py     # SQLite + ChromaDB vector memory
├── voice/voice.py       # Whisper STT + Kokoro TTS
├── vision/eyes.py       # Screenshot + OCR + vision AI
├── hands/hands.py       # AI action planner + PyAutoGUI executor
├── integrations/web.py  # Web search + browser automation
├── persona/persona.py   # Roles, personality, face recognition
├── ui/src/              # React orb UI
├── main.py              # WebSocket orchestrator
├── setup.bat            # One-click setup (Windows)
└── start.bat            # Launch script
```

## API Keys

| Key | Required | Free Tier | Link |
|-----|----------|-----------|------|
| `GROQ_API_KEY` | **Yes** | 14,400 req/day | https://console.groq.com |
| `GEMINI_API_KEY` | No | Limited | https://aistudio.google.com |
| `ANTHROPIC_API_KEY` | No | Paid only | https://console.anthropic.com |

## Stopping

Close the terminal windows running the backend and UI, or press Ctrl+C in each.
