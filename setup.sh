#!/bin/bash
# SOVEREIGN OS — One-command setup
# Run this once: bash setup.sh

set -e
echo ""
echo "========================================="
echo "  SOVEREIGN OS — Setup"
echo "========================================="
echo ""

# ── Python check ──────────────────────────────────────────────────────────────
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "[1/7] Python: $python_version"
if [[ "$python_version" < "3.11" ]]; then
    echo "  ERROR: Python 3.11+ required. Please upgrade."
    exit 1
fi

# ── .env check ────────────────────────────────────────────────────────────────
echo "[2/7] Checking .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  Created .env from template."
    echo "  ACTION REQUIRED: Open .env and add your ANTHROPIC_API_KEY"
    echo "  Then re-run this script."
    exit 0
fi

# ── Python packages ───────────────────────────────────────────────────────────
echo "[3/7] Installing Python packages..."
pip install -r requirements.txt --quiet

# ── Playwright browsers ───────────────────────────────────────────────────────
echo "[4/7] Installing Playwright browser..."
playwright install chromium --quiet

# ── Kokoro TTS ────────────────────────────────────────────────────────────────
echo "[5/7] Installing Kokoro TTS..."
pip install kokoro-onnx --quiet || echo "  Kokoro install failed — pyttsx3 fallback will be used"

# ── Node + Tauri (UI) ─────────────────────────────────────────────────────────
echo "[6/7] Setting up UI..."
if command -v node &> /dev/null; then
    cd ui
    if [ ! -f package.json ]; then
        echo "  Initializing Tauri app..."
        npm create tauri-app@latest . -- --template react-ts --yes 2>/dev/null || true
    fi
    npm install --silent
    # Copy our orb component
    cp ../ui/src/SovereignOrb.tsx src/SovereignOrb.tsx 2>/dev/null || true
    cd ..
    echo "  UI ready"
else
    echo "  Node.js not found — install from https://nodejs.org then run: cd ui && npm install"
fi

# ── Verify imports ────────────────────────────────────────────────────────────
echo "[7/7] Verifying module imports..."
python3 -c "
import sys
errors = []
modules = [
    ('core.brain', 'Brain'),
    ('memory.memory', 'Memory'),
    ('vision.eyes', 'Eyes'),
    ('hands.hands', 'Hands'),
    ('voice.voice', 'Voice'),
    ('persona.persona', 'Persona'),
    ('shared.types', 'OrchestratorRequest'),
    ('shared.config', 'WS_PORT'),
]
for mod, cls in modules:
    try:
        m = __import__(mod, fromlist=[cls])
        getattr(m, cls)
        print(f'  OK  {mod}')
    except Exception as e:
        print(f'  FAIL {mod}: {e}')
        errors.append(mod)
if errors:
    print(f'\n  {len(errors)} module(s) failed. Check errors above.')
    sys.exit(1)
else:
    print('\n  All modules OK')
"

echo ""
echo "========================================="
echo "  SETUP COMPLETE"
echo "========================================="
echo ""
echo "  To run SOVEREIGN OS:"
echo ""
echo "  Terminal 1 (backend):"
echo "    python main.py"
echo ""
echo "  Terminal 2 (UI):"
echo "    cd ui && npm run tauri dev"
echo ""
echo "  First test — type in the UI:"
echo "    'Hello, who are you?'"
echo ""
