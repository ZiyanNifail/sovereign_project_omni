#!/bin/bash
# SOVEREIGN OS — macOS startup script

echo ""
echo "========================================="
echo "  SOVEREIGN OS — Starting"
echo "========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Kill any existing instance on port 8765
lsof -ti:8765 | xargs kill -9 2>/dev/null && echo "Killed existing backend on :8765" || true

# Start Python backend in background
echo "[1/2] Starting Python backend (ws://localhost:8765)..."
cd "$SCRIPT_DIR"
python3 main.py &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"

# Wait for backend to boot
sleep 3

# Start Vite frontend dev server in background
echo "[2/2] Starting UI dev server (http://localhost:5173)..."
cd "$SCRIPT_DIR/ui"
npm run dev &
FRONTEND_PID=$!
sleep 2

# Open browser
open "http://localhost:5173"

echo ""
echo "========================================="
echo "  SOVEREIGN OS is running"
echo "========================================="
echo "  Backend : ws://localhost:8765  (PID $BACKEND_PID)"
echo "  UI      : http://localhost:5173 (PID $FRONTEND_PID)"
echo ""
echo "  Press Ctrl+C to stop both."
echo "========================================="
echo ""

# Wait and clean up on exit
trap "echo ''; echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
