# voice/voice.py
# Module 3: Voice — Whisper STT + Kokoro TTS + voice profile manager

import logging
import tempfile
import threading
from pathlib import Path
from typing import Optional

from shared.types import VoiceResult
from shared.config import (
    WHISPER_MODEL, DEFAULT_VOICE, TTS_SPEED,
    VOICE_MODELS_DIR, AUDIO_DIR
)

logger = logging.getLogger(__name__)


class Voice:
    def __init__(self):
        self._whisper = None          # lazy load — heavy model
        self._kokoro = None           # lazy load
        self._current_voice = DEFAULT_VOICE
        self._is_speaking = False
        logger.info("Voice initialized (models load on first use)")

    # ── Lazy loaders ──────────────────────────────────────────────────────────

    def _load_whisper(self):
        if self._whisper is None:
            try:
                import whisper
                self._whisper = whisper.load_model(WHISPER_MODEL)
                logger.info(f"Whisper loaded: {WHISPER_MODEL}")
            except Exception as e:
                logger.error(f"Whisper load failed: {e}")

    def _load_kokoro(self):
        if self._kokoro is None:
            try:
                from kokoro_onnx import Kokoro
                from shared.config import DATA_DIR
                self._kokoro = Kokoro(
                    str(DATA_DIR / "kokoro-v1.0.onnx"),
                    str(DATA_DIR / "voices-v1.0.bin")
                )
                logger.info("Kokoro TTS loaded")
            except Exception as e:
                logger.error(f"Kokoro load failed: {e}. Install: pip install kokoro-onnx")

    # ── Speech to Text ────────────────────────────────────────────────────────

    def listen(self, duration: int = 5, audio_path: Optional[str] = None) -> VoiceResult:
        """
        Record from mic (duration seconds) then transcribe.
        Or transcribe an existing audio file if audio_path is given.
        """
        self._load_whisper()
        if not self._whisper:
            return VoiceResult(transcript="", confidence=0.0, success=False, error="Whisper not loaded")

        try:
            if audio_path:
                path = audio_path
            else:
                path = self._record(duration)
                if not path:
                    return VoiceResult(transcript="", confidence=0.0, success=False, error="Recording failed")

            result = self._whisper.transcribe(str(path))
            transcript = result["text"].strip()
            # Whisper doesn't give per-segment confidence easily — use segment avg
            segments = result.get("segments", [])
            if segments:
                avg_conf = sum(s.get("no_speech_prob", 0) for s in segments) / len(segments)
                confidence = 1.0 - avg_conf
            else:
                confidence = 0.9 if transcript else 0.0

            logger.debug(f"Transcribed: '{transcript}' (conf={confidence:.2f})")
            return VoiceResult(transcript=transcript, confidence=confidence, success=bool(transcript))

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return VoiceResult(transcript="", confidence=0.0, success=False, error=str(e))

    def _record(self, duration: int) -> Optional[Path]:
        """Record audio from microphone."""
        try:
            import sounddevice as sd
            import soundfile as sf
            import numpy as np

            sample_rate = 16000
            logger.debug(f"Recording for {duration}s...")
            audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate,
                           channels=1, dtype="float32")
            sd.wait()
            path = AUDIO_DIR / "input.wav"
            sf.write(str(path), audio, sample_rate)
            return path
        except Exception as e:
            logger.error(f"Recording failed: {e}")
            return None

    # ── Text to Speech ────────────────────────────────────────────────────────

    def speak(self, text: str, voice: Optional[str] = None, block: bool = False) -> Optional[Path]:
        """
        Convert text to speech using Kokoro. Returns path to audio file.
        block=True waits until playback finishes.
        """
        self._load_kokoro()
        if not self._kokoro:
            logger.warning("Kokoro not available — falling back to pyttsx3")
            return self._speak_fallback(text)

        try:
            v = voice or self._current_voice
            import numpy as np
            import soundfile as sf

            samples, sample_rate = self._kokoro.create(text, voice=v, speed=TTS_SPEED, lang="en-us")

            if samples is None or len(samples) == 0:
                return None

            path = AUDIO_DIR / "output.wav"
            sf.write(str(path), samples, sample_rate)

            if block:
                self._play_audio(path)
            else:
                threading.Thread(target=self._play_audio, args=(path,), daemon=True).start()

            self._is_speaking = True
            return path

        except Exception as e:
            logger.error(f"TTS failed: {e}")
            return self._speak_fallback(text)

    def _speak_fallback(self, text: str) -> None:
        """Last resort TTS using pyttsx3 (no quality but works offline)."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            logger.error(f"Fallback TTS also failed: {e}")
        return None

    def _play_audio(self, path: Path):
        try:
            import sounddevice as sd
            import soundfile as sf
            data, sr = sf.read(str(path))
            sd.play(data, sr)
            sd.wait()
            self._is_speaking = False
        except Exception as e:
            logger.error(f"Audio playback failed: {e}")
            self._is_speaking = False

    # ── Voice Profile Manager ─────────────────────────────────────────────────

    def set_voice(self, voice_name: str):
        """Switch to a different Kokoro voice preset."""
        self._current_voice = voice_name
        logger.info(f"Voice set to: {voice_name}")

    def list_voices(self) -> list:
        """Available Kokoro voice presets."""
        return [
            "af_heart", "af_bella", "af_nicole", "af_sky",
            "am_adam", "am_michael", "bf_emma", "bm_george"
        ]

    def clone_voice(self, audio_samples: list, name: str) -> bool:
        """
        Register a cloned voice using Coqui XTTS-v2.
        audio_samples: list of paths to WAV files of the target voice.
        """
        try:
            from TTS.api import TTS
            model_path = VOICE_MODELS_DIR / name
            model_path.mkdir(exist_ok=True)
            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
            # Coqui uses reference audio for zero-shot cloning
            # Store reference audio paths for later use
            import json, shutil
            refs = []
            for i, sample in enumerate(audio_samples):
                dest = model_path / f"ref_{i}.wav"
                shutil.copy(sample, dest)
                refs.append(str(dest))
            (model_path / "refs.json").write_text(json.dumps(refs))
            logger.info(f"Voice '{name}' cloned with {len(refs)} samples")
            return True
        except Exception as e:
            logger.error(f"Voice cloning failed: {e}")
            return False

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    voice = Voice()
    print("Available voices:", voice.list_voices())
    print("Speaking test...")
    voice.speak("Hello. I am SOVEREIGN. Your personal AI companion.", block=True)
    print("Done.")
