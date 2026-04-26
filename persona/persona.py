# persona/persona.py
# Module 7: Persona — role/style management + face recognition database

import json
import logging
import numpy as np
from pathlib import Path
from typing import Optional, Dict, List

from shared.types import PersonaConfig, Role, PersonalityStyle
from shared.config import FACES_DIR, DATA_DIR

logger = logging.getLogger(__name__)

PERSONA_CONFIG_PATH = DATA_DIR / "persona.json"


class Persona:
    def __init__(self):
        self._face_encodings: Dict[str, np.ndarray] = {}
        self._face_recognizer = None
        self._config: Optional[PersonaConfig] = None
        self._load_face_db()
        logger.info("Persona initialized")

    # ── Config ────────────────────────────────────────────────────────────────

    def load_config(self, user_name: str) -> PersonaConfig:
        """Load persona config from disk or create default."""
        try:
            if PERSONA_CONFIG_PATH.exists():
                data = json.loads(PERSONA_CONFIG_PATH.read_text())
                saved_name = data.get("user_name", user_name)
                # Existing configs without the flag count as complete if they have a real name —
                # this preserves the setup state for users who already onboarded.
                setup_complete = data.get(
                    "setup_complete",
                    bool(saved_name) and saved_name.strip().lower() != "user"
                )
                self._config = PersonaConfig(
                    role=Role(data.get("role", "friend")),
                    style=PersonalityStyle(data.get("style", "empathetic")),
                    user_name=saved_name,
                    known_faces=data.get("known_faces", {}),
                    setup_complete=setup_complete,
                )
            else:
                self._config = PersonaConfig(
                    role=Role.FRIEND,
                    style=PersonalityStyle.EMPATHETIC,
                    user_name=user_name,
                    setup_complete=False,
                )
                self.save_config(self._config)
        except Exception as e:
            logger.error(f"load_config failed: {e}")
            self._config = PersonaConfig(
                role=Role.FRIEND, style=PersonalityStyle.EMPATHETIC,
                user_name=user_name, setup_complete=False,
            )
        return self._config

    def save_config(self, config: PersonaConfig):
        """Persist persona config to disk."""
        try:
            data = {
                "role": config.role.value,
                "style": config.style.value,
                "user_name": config.user_name,
                "known_faces": config.known_faces,
                "setup_complete": config.setup_complete,
            }
            PERSONA_CONFIG_PATH.write_text(json.dumps(data, indent=2))
            self._config = config
            logger.debug("Persona config saved")
        except Exception as e:
            logger.error(f"save_config failed: {e}")

    def set_user_name(self, name: str) -> bool:
        """Record the user's chosen name and mark onboarding complete."""
        clean = (name or "").strip()
        if not clean:
            return False
        if self._config:
            self._config.user_name = clean
            self._config.setup_complete = True
            self.save_config(self._config)
            logger.info(f"User name set to: {clean}")
        return True

    def set_role(self, role: Role):
        if self._config:
            self._config.role = role
            self.save_config(self._config)
        logger.info(f"Role set to: {role.value}")

    def set_style(self, style: PersonalityStyle):
        if self._config:
            self._config.style = style
            self.save_config(self._config)
        logger.info(f"Style set to: {style.value}")

    # ── Face Recognition ──────────────────────────────────────────────────────

    def _load_face_recognizer(self) -> bool:
        """Lazy load face_recognition library."""
        if self._face_recognizer is not None:
            return True
        try:
            import face_recognition
            self._face_recognizer = face_recognition
            return True
        except ImportError:
            logger.warning("face_recognition not installed. Run: pip install face-recognition")
            return False

    def _load_face_db(self):
        """Load all saved face encodings from disk."""
        try:
            for npy_file in FACES_DIR.glob("*.npy"):
                name = npy_file.stem
                encoding = np.load(str(npy_file))
                self._face_encodings[name] = encoding
            if self._face_encodings:
                logger.info(f"Loaded {len(self._face_encodings)} face encodings")
        except Exception as e:
            logger.error(f"_load_face_db failed: {e}")

    def add_face(self, image_path: str, name: str) -> bool:
        """
        Add a person to the face database.
        image_path: path to a clear photo of the person's face.
        name: their name (used as the identifier).
        """
        if not self._load_face_recognizer():
            return False
        try:
            fr = self._face_recognizer
            image = fr.load_image_file(image_path)
            encodings = fr.face_encodings(image)
            if not encodings:
                logger.warning(f"No face detected in: {image_path}")
                return False

            encoding = encodings[0]
            save_path = FACES_DIR / f"{name}.npy"
            np.save(str(save_path), encoding)
            self._face_encodings[name] = encoding

            # Update config
            if self._config:
                self._config.known_faces[image_path] = name
                self.save_config(self._config)

            logger.info(f"Face added: {name}")
            return True
        except Exception as e:
            logger.error(f"add_face failed: {e}")
            return False

    def recognize_face(self, image_path: str) -> Optional[str]:
        """
        Identify who is in a photo.
        Returns person's name or None if unknown.
        """
        if not self._load_face_recognizer() or not self._face_encodings:
            return None
        try:
            fr = self._face_recognizer
            image = fr.load_image_file(image_path)
            unknown_encodings = fr.face_encodings(image)

            if not unknown_encodings:
                return None

            known_encodings = list(self._face_encodings.values())
            known_names = list(self._face_encodings.keys())

            for unknown_enc in unknown_encodings:
                matches = fr.compare_faces(known_encodings, unknown_enc, tolerance=0.5)
                face_distances = fr.face_distance(known_encodings, unknown_enc)
                if any(matches):
                    best_idx = int(np.argmin(face_distances))
                    if matches[best_idx]:
                        name = known_names[best_idx]
                        logger.debug(f"Recognized: {name}")
                        return name
            return None
        except Exception as e:
            logger.error(f"recognize_face failed: {e}")
            return None

    def recognize_all_faces(self, image_path: str) -> List[str]:
        """Return names of ALL recognizable faces in an image."""
        if not self._load_face_recognizer() or not self._face_encodings:
            return []
        try:
            fr = self._face_recognizer
            image = fr.load_image_file(image_path)
            unknown_encodings = fr.face_encodings(image)
            known_encodings = list(self._face_encodings.values())
            known_names = list(self._face_encodings.keys())
            found = []
            for unknown_enc in unknown_encodings:
                matches = fr.compare_faces(known_encodings, unknown_enc, tolerance=0.5)
                distances = fr.face_distance(known_encodings, unknown_enc)
                if any(matches):
                    best_idx = int(np.argmin(distances))
                    if matches[best_idx]:
                        found.append(known_names[best_idx])
                    else:
                        found.append("unknown")
                else:
                    found.append("unknown")
            return found
        except Exception as e:
            logger.error(f"recognize_all_faces failed: {e}")
            return []

    def list_known_faces(self) -> Dict[str, str]:
        """Return all registered faces {name: encoding_path}."""
        return {name: str(FACES_DIR / f"{name}.npy") for name in self._face_encodings}


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    persona = Persona()
    config = persona.load_config("TestUser")
    print(f"Role: {config.role.value}, Style: {config.style.value}")

    persona.set_role(Role.ASSISTANT)
    persona.set_style(PersonalityStyle.HONEST)
    print(f"Updated role: {persona._config.role.value}")

    faces = persona.list_known_faces()
    print(f"Known faces: {len(faces)}")
    print("Persona module: OK")
