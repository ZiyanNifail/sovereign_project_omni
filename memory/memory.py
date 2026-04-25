# memory/memory.py
# Module 2: Memory — SQLite (structured) + ChromaDB (vector) + sentiment + style profiling

import sqlite3
import json
import logging
import uuid
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from shared.types import MemoryEntry, UserProfile, Role, PersonalityStyle
from shared.config import (
    MEMORY_DB_PATH, CHROMA_DIR, MEMORY_COLLECTION,
    MAX_MEMORY_RESULTS, SENTIMENT_WINDOW
)

logger = logging.getLogger(__name__)


class Memory:
    def __init__(self):
        self._chroma = None
        self._embedder = None
        self._db = None
        self._setup_sqlite()
        logger.info("Memory initialized")

    # ── SQLite setup ──────────────────────────────────────────────────────────

    def _setup_sqlite(self):
        self._db = sqlite3.connect(str(MEMORY_DB_PATH), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        cur = self._db.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS user_profile (
                name TEXT PRIMARY KEY,
                role TEXT DEFAULT 'friend',
                style TEXT DEFAULT 'empathetic',
                sentiment_score REAL DEFAULT 0.5,
                avg_message_length INTEGER DEFAULT 50,
                emoji_frequency REAL DEFAULT 0.0,
                voice_model TEXT DEFAULT 'default',
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sentiment_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                score REAL,
                timestamp TEXT
            );
            CREATE TABLE IF NOT EXISTS message_style_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_length INTEGER,
                emoji_count INTEGER,
                has_punctuation INTEGER,
                timestamp TEXT
            );
            CREATE TABLE IF NOT EXISTS memories_meta (
                id TEXT PRIMARY KEY,
                content TEXT,
                category TEXT,
                timestamp TEXT
            );
        """)
        self._db.commit()

    # ── ChromaDB lazy load ─────────────────────────────────────────────────────

    def _load_chroma(self):
        if self._chroma is None:
            try:
                import chromadb
                from sentence_transformers import SentenceTransformer
                client = chromadb.PersistentClient(path=str(CHROMA_DIR))
                self._chroma = client.get_or_create_collection(MEMORY_COLLECTION)
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("ChromaDB + embedder loaded")
            except Exception as e:
                logger.error(f"ChromaDB load failed: {e}")

    # ── User Profile ──────────────────────────────────────────────────────────

    def save_user_profile(self, profile: UserProfile) -> bool:
        try:
            cur = self._db.cursor()
            cur.execute("""
                INSERT INTO user_profile VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(name) DO UPDATE SET
                    role=excluded.role, style=excluded.style,
                    sentiment_score=excluded.sentiment_score,
                    avg_message_length=excluded.avg_message_length,
                    emoji_frequency=excluded.emoji_frequency,
                    voice_model=excluded.voice_model
            """, (
                profile.name, profile.role.value, profile.style.value,
                profile.sentiment_score, profile.avg_message_length,
                profile.emoji_frequency, profile.voice_model,
                profile.created_at.isoformat()
            ))
            self._db.commit()
            return True
        except Exception as e:
            logger.error(f"save_user_profile failed: {e}")
            return False

    def load_user_profile(self, name: str) -> Optional[UserProfile]:
        try:
            cur = self._db.cursor()
            row = cur.execute("SELECT * FROM user_profile WHERE name=?", (name,)).fetchone()
            if not row:
                return None
            return UserProfile(
                name=row["name"],
                role=Role(row["role"]),
                style=PersonalityStyle(row["style"]),
                sentiment_score=row["sentiment_score"],
                avg_message_length=row["avg_message_length"],
                emoji_frequency=row["emoji_frequency"],
                voice_model=row["voice_model"],
            )
        except Exception as e:
            logger.error(f"load_user_profile failed: {e}")
            return None

    # ── Vector Memory ─────────────────────────────────────────────────────────

    def add_memory(self, content: str, category: str = "general") -> str:
        """Store a memory. Returns memory ID."""
        self._load_chroma()
        memory_id = str(uuid.uuid4())[:8]
        try:
            if self._chroma and self._embedder:
                embedding = self._embedder.encode(content).tolist()
                self._chroma.add(
                    ids=[memory_id],
                    documents=[content],
                    embeddings=[embedding],
                    metadatas=[{"category": category, "timestamp": datetime.now().isoformat()}]
                )
            # Always save to SQLite as backup
            cur = self._db.cursor()
            cur.execute(
                "INSERT INTO memories_meta VALUES (?,?,?,?)",
                (memory_id, content, category, datetime.now().isoformat())
            )
            self._db.commit()
            logger.debug(f"Memory stored [{category}]: {content[:60]}...")
            return memory_id
        except Exception as e:
            logger.error(f"add_memory failed: {e}")
            return ""

    def recall(self, query: str, n: int = MAX_MEMORY_RESULTS) -> List[MemoryEntry]:
        """Semantic search — find memories most relevant to the query."""
        self._load_chroma()
        try:
            if self._chroma and self._embedder:
                embedding = self._embedder.encode(query).tolist()
                results = self._chroma.query(
                    query_embeddings=[embedding],
                    n_results=min(n, self._chroma.count())
                )
                entries = []
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i]
                    entries.append(MemoryEntry(
                        id=results["ids"][0][i],
                        content=doc,
                        category=meta.get("category", "general"),
                        timestamp=datetime.fromisoformat(meta.get("timestamp", datetime.now().isoformat()))
                    ))
                return entries
        except Exception as e:
            logger.error(f"recall failed: {e}")

        # Fallback: SQLite keyword search
        try:
            cur = self._db.cursor()
            rows = cur.execute(
                "SELECT * FROM memories_meta WHERE content LIKE ? LIMIT ?",
                (f"%{query[:30]}%", n)
            ).fetchall()
            return [MemoryEntry(
                id=r["id"], content=r["content"],
                category=r["category"],
                timestamp=datetime.fromisoformat(r["timestamp"])
            ) for r in rows]
        except Exception as e:
            logger.error(f"SQLite recall fallback failed: {e}")
            return []

    def get_context_string(self, query: str) -> str:
        """Returns formatted memory string for injection into brain prompt."""
        memories = self.recall(query)
        if not memories:
            return ""
        lines = [f"- [{m.category}] {m.content}" for m in memories]
        return "\n".join(lines)

    # ── Sentiment Tracking ────────────────────────────────────────────────────

    def update_sentiment(self, score: float) -> float:
        """Log a sentiment score (0=negative, 1=positive). Returns rolling average."""
        try:
            cur = self._db.cursor()
            cur.execute(
                "INSERT INTO sentiment_log (score, timestamp) VALUES (?,?)",
                (max(0.0, min(1.0, score)), datetime.now().isoformat())
            )
            self._db.commit()
            rows = cur.execute(
                f"SELECT score FROM sentiment_log ORDER BY id DESC LIMIT {SENTIMENT_WINDOW}"
            ).fetchall()
            avg = sum(r["score"] for r in rows) / len(rows) if rows else 0.5
            logger.debug(f"Sentiment updated: {score:.2f}, avg={avg:.2f}")
            return avg
        except Exception as e:
            logger.error(f"update_sentiment failed: {e}")
            return 0.5

    # ── Message Style Profiling ───────────────────────────────────────────────

    def log_message_style(self, message: str):
        """Track message patterns to build texting style profile."""
        try:
            import re
            emoji_pattern = re.compile(
                "[\U00010000-\U0010ffff]", flags=re.UNICODE
            )
            emoji_count = len(emoji_pattern.findall(message))
            has_punct = 1 if any(c in message for c in ".!?") else 0
            cur = self._db.cursor()
            cur.execute(
                "INSERT INTO message_style_log (message_length, emoji_count, has_punctuation, timestamp) VALUES (?,?,?,?)",
                (len(message), emoji_count, has_punct, datetime.now().isoformat())
            )
            self._db.commit()
        except Exception as e:
            logger.error(f"log_message_style failed: {e}")

    def get_style_summary(self) -> dict:
        """Returns a summary of the user's messaging style."""
        try:
            cur = self._db.cursor()
            rows = cur.execute("SELECT * FROM message_style_log ORDER BY id DESC LIMIT 50").fetchall()
            if not rows:
                return {"avg_length": 50, "emoji_freq": 0.0, "punctuation_rate": 0.5}
            avg_len = sum(r["message_length"] for r in rows) / len(rows)
            emoji_freq = sum(r["emoji_count"] for r in rows) / len(rows)
            punct_rate = sum(r["has_punctuation"] for r in rows) / len(rows)
            return {"avg_length": round(avg_len), "emoji_freq": round(emoji_freq, 2), "punctuation_rate": round(punct_rate, 2)}
        except Exception as e:
            logger.error(f"get_style_summary failed: {e}")
            return {}


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.DEBUG)
    mem = Memory()

    # Test profile
    profile = UserProfile(name="TestUser")
    mem.save_user_profile(profile)
    loaded = mem.load_user_profile("TestUser")
    print(f"Profile: {loaded.name}, role={loaded.role.value}")

    # Test memory
    mid = mem.add_memory("User loves late night coding sessions and hates mornings.", "preference")
    mid2 = mem.add_memory("User is stressed about their Sunday deadline.", "sentiment")
    print(f"Stored memories: {mid}, {mid2}")

    # Test recall
    results = mem.recall("what does the user feel about time?")
    print(f"Recalled {len(results)} memories:")
    for r in results:
        print(f"  [{r.category}] {r.content}")

    # Test sentiment
    avg = mem.update_sentiment(0.3)
    print(f"Sentiment avg: {avg:.2f}")

    # Test style
    mem.log_message_style("yo bro what's up 😂")
    style = mem.get_style_summary()
    print(f"Style: {style}")

    print("Memory module: OK")
