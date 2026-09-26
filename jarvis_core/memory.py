"""Session memory (rolling chat history) + persistent facts."""
from __future__ import annotations

import json
import logging
import time
from collections import deque

from .config import DATA_DIR

log = logging.getLogger("jarvis.memory")


class Memory:
    def __init__(self, cfg):
        self.cfg = cfg
        n = int(cfg.get("memory.max_turns", 12)) * 2
        self._hist: deque = deque(maxlen=n)
        self._facts_path = DATA_DIR / "memory.json"
        self._session_path = DATA_DIR / f"session-{time.strftime('%Y%m%d')}.jsonl"
        self.facts: list[str] = []
        try:
            if self._facts_path.exists():
                self.facts = json.loads(self._facts_path.read_text(encoding="utf-8")).get("facts", [])
        except Exception as e:  # corrupt file shouldn't stop us
            log.warning("Could not load memory: %s", e)

    def add(self, role: str, content: str) -> None:
        self._hist.append({"role": role, "content": content})
        if self.cfg.get("memory.save_sessions", True):
            try:
                with open(self._session_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"t": time.time(), "role": role, "content": content}) + "\n")
            except OSError:
                pass

    def history(self) -> list[dict]:
        return list(self._hist)

    def clear(self) -> None:
        self._hist.clear()

    def add_fact(self, fact: str) -> None:
        fact = fact.strip()
        if fact and fact not in self.facts:
            self.facts.append(fact)
            self._save()

    def remove_fact(self, needle: str) -> int:
        keep = [f for f in self.facts if needle.lower() not in f.lower()]
        removed = len(self.facts) - len(keep)
        self.facts = keep
        if removed:
            self._save()
        return removed

    def _save(self) -> None:
        self._facts_path.write_text(json.dumps({"facts": self.facts}, indent=2), encoding="utf-8")
