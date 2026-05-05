# clap_launcher.py — Launch SOVEREIGN OS by double-clapping your hands
#
# Usage:  python clap_launcher.py
#
# On double-clap → kills any stale backend → starts Python backend + Vite UI.

import socket
import sounddevice as sd
import numpy as np
import subprocess
import sys
import time
import threading
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
SAMPLE_RATE       = 44100
CHUNK_MS          = 40               # audio analysis window in milliseconds
CLAP_WINDOW_SEC   = 1.5              # max gap between clap 1 and clap 2
CLAP_DEBOUNCE_SEC = 0.18             # ignore echoes closer than this
AMBIENT_SECS      = 2.0              # how long to measure ambient noise at boot
CLAP_MULTIPLIER   = 7                # clap RMS must be N× louder than ambient

BASE_DIR = Path(__file__).resolve().parent
UI_DIR   = BASE_DIR / "ui"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _popen(cmd: str | list, **kw):
    """Fire-and-forget subprocess."""
    if isinstance(cmd, str):
        kw.setdefault("shell", True)
    kw.setdefault("cwd", str(BASE_DIR))
    return subprocess.Popen(cmd, **kw)


def kill_port(port: int):
    """Kill any process holding the given TCP port (Windows)."""
    subprocess.run(
        f'powershell -Command "Get-NetTCPConnection -LocalPort {port} '
        f'-ErrorAction SilentlyContinue | ForEach-Object '
        f'{{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"',
        shell=True, capture_output=True
    )


def calibrate(duration: float) -> float:
    """Record ambient noise and return average RMS."""
    print(f"  Calibrating — stay quiet for {duration:.0f}s...")
    frames = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                    channels=1, dtype="float32")
    sd.wait()
    rms = float(np.sqrt(np.mean(frames ** 2)))
    print(f"  Ambient RMS: {rms:.5f}")
    return rms


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> bool:
    """Block until host:port accepts connections or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def launch_all():
    """Start the backend and UI — nothing else."""
    print("\n  ██ Double clap confirmed — launching SOVEREIGN OS ██\n")

    # 1 ── Kill stale processes on both ports
    kill_port(8765)
    kill_port(5173)
    time.sleep(0.5)

    # 2 ── Python backend
    _popen(
        [sys.executable, str(BASE_DIR / "main.py")],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    print("  [1/2] Backend started  (ws://localhost:8765)")

    # 3 ── Install UI deps if node_modules is missing
    if not (UI_DIR / "node_modules").exists():
        print("  [2/2] Installing UI dependencies (first run)...")
        result = subprocess.run("npm install", cwd=str(UI_DIR), shell=True)
        if result.returncode != 0:
            print("  ERROR: npm install failed — check Node.js is installed.")
            return

    # 4 ── Vite UI dev server
    _popen("npm run dev", cwd=str(UI_DIR))
    print("  [2/2] Waiting for Vite (http://localhost:5173)...")

    # 5 ── Wait for Vite to be ready (browser not auto-opened — open manually when ready)
    if _wait_for_port("localhost", 5173, timeout=30.0):
        print("  UI ready         (http://localhost:5173) — open in browser when ready")
    else:
        print("  WARNING: Vite didn't start within 30s — open http://localhost:5173 manually")

    print("\n  SOVEREIGN OS is ready.\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 52)
    print("  SOVEREIGN OS — Clap Launcher")
    print("  Double-clap anywhere near your mic to launch.")
    print("=" * 52)
    print()

    ambient_rms = calibrate(AMBIENT_SECS)
    threshold   = max(ambient_rms * CLAP_MULTIPLIER, 0.015)
    print(f"  Threshold: {threshold:.5f}  |  Listening...\n")

    clap_times:  list[float] = []
    last_clap:   list[float] = [0.0]   # mutable for callback closure
    launched:    list[bool]  = [False]
    chunk_size = int(SAMPLE_RATE * CHUNK_MS / 1000)

    def callback(indata, frames, time_info, status):
        if launched[0]:
            return
        rms = float(np.sqrt(np.mean(indata ** 2)))
        now = time.time()

        if rms > threshold and (now - last_clap[0]) > CLAP_DEBOUNCE_SEC:
            last_clap[0] = now
            # Trim claps outside the detection window
            clap_times[:] = [t for t in clap_times if now - t <= CLAP_WINDOW_SEC]
            clap_times.append(now)
            n = len(clap_times)
            print(f"  Clap #{n}  (RMS {rms:.4f})", flush=True)

            if n >= 2:
                launched[0] = True
                threading.Thread(target=launch_all, daemon=False).start()

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                        blocksize=chunk_size, callback=callback):
        try:
            while not launched[0]:
                time.sleep(0.05)
            # Wait for launch_all thread to finish printing
            time.sleep(4)
        except KeyboardInterrupt:
            print("\n  Clap launcher stopped.")


if __name__ == "__main__":
    main()
