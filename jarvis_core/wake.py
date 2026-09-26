"""Wake-phrase and sleep-phrase detection (works on spoken transcripts and typed text).

Matches: "Jarvis", "Hi/Hey/Okay Jarvis", "Wake up Jarvis", "Jarvis, you there?",
plus fuzzy mis-hearings ("Jervis", "Gervais"...). The name may be followed by a command:
"Hey Jarvis, open Chrome" -> (True, "open Chrome").
"""
from __future__ import annotations

import difflib
import re

TOKEN = re.compile(r"[A-Za-z0-9'’]+")
IDLE_REMAINDERS = {"you there", "are you there", "are you awake", "wake up", "hello", "hi",
                   "hey", "sir", "there", "you up", "come in", "up", "are you up", "ready"}


def norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("'", "")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class WakeDetector:
    def __init__(self, cfg):
        w = cfg.get("wake")
        self.name = norm(cfg.get("assistant_name", "Jarvis"))
        self.aliases = {self.name} | {norm(a) for a in w.get("aliases", [])}
        self.fillers = {norm(f) for f in w.get("fillers", [])}
        self.threshold = float(w.get("fuzzy_threshold", 0.78))
        self.max_prefix = int(w.get("max_prefix_words", 3))
        self.sleep_phrases = {norm(p) for p in w.get("sleep_phrases", [])}
        self._trailing = {"sir", "please", "now", "thanks", "thank you", self.name, "ok", "okay"}

    def _is_name(self, tok: str) -> bool:
        if tok in self.aliases:
            return True
        return difflib.SequenceMatcher(None, tok, self.name).ratio() >= self.threshold

    def detect(self, text: str) -> tuple[bool, str]:
        """Return (wake_word_found, remaining_command_text)."""
        toks = list(TOKEN.finditer(text))
        for i, m in enumerate(toks[: self.max_prefix + 1]):
            t = norm(m.group())
            if self._is_name(t):
                rest = text[m.end():].lstrip(" ,.:;!?-\u2013\u2014")
                n = norm(rest)
                if n in IDLE_REMAINDERS:
                    return True, ""
                rest = re.sub(r"^(please[, ]+)", "", rest, flags=re.I)
                return True, rest.strip()
            if t not in self.fillers:
                break
        return False, text

    def is_sleep(self, text: str) -> bool:
        n = norm(text)
        words = n.split()
        while words and (words[-1] in self._trailing or " ".join(words[-2:]) in self._trailing):
            words = words[:-2] if " ".join(words[-2:]) in self._trailing else words[:-1]
        n = " ".join(words)
        if n in self.sleep_phrases:
            return True
        return any(" " in p and n.startswith(p + " ") for p in self.sleep_phrases)
