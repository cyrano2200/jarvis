"""Configuration: built-in defaults -> config.yaml -> .env / environment variables."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"

DEFAULTS: dict[str, Any] = {
    "user_name": "Sir",
    "assistant_name": "Jarvis",
    "wake": {
        # Extra spellings / mis-hearings that should count as the assistant's name.
        "aliases": ["jarvis", "jarves", "jervis", "jarvas", "jarvus", "garvis", "gervis",
                    "gervais", "charvis", "jarvie", "travis"],
        # Words allowed BEFORE the name: "hi jarvis", "okay jarvis", "wake up jarvis"...
        "fillers": ["hi", "hey", "hay", "hello", "okay", "ok", "yo", "wake", "up", "a", "oh", "so"],
        "fuzzy_threshold": 0.78,
        "max_prefix_words": 3,
        "sleep_phrases": ["that's all", "thats all", "that is all", "sleep", "go to sleep",
                          "standby", "stand by", "dismissed", "go to standby"],
        # 0 = stay awake until told to sleep. Otherwise auto-sleep after N idle seconds.
        "awake_timeout_seconds": 0,
    },
    "speech": {
        "stt": {
            "engine": "whisper",       # whisper (offline, faster-whisper) | google (online)
            "whisper_model": "base.en",  # tiny.en, base.en, small.en, medium.en ...
            "device": "cpu",           # cpu | cuda
            "compute_type": "int8",
            "language": "en",
            "mic_index": None,         # run: python jarvis.py --list-mics
            "energy_threshold": None,  # None = auto-calibrate
            "pause_threshold": 0.8,
            "phrase_time_limit": 20,
        },
        "tts": {
            "engine": "edge",          # edge (neural, needs internet) | pyttsx3 (offline)
            "edge_voice": "en-GB-RyanNeural",
            "edge_rate": "+0%",
            "edge_pitch": "-4Hz",
            "edge_volume": "+0%",
            "pyttsx3_voice_hint": "british|george|hazel|daniel|uk",
            "pyttsx3_rate": 175,
        },
    },
    "llm": {
        # Tried in order; first reachable/configured one wins.
        "provider_order": ["ollama", "lmstudio", "groq", "openai", "anthropic"],
        "temperature": 0.4,
        "max_steps": 8,
        "timeout": 90,
        "ollama": {"base_url": "http://localhost:11434", "model": "llama3.1:8b"},
        "lmstudio": {"base_url": "http://localhost:1234/v1", "model": "local-model"},
        "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "api_key": ""},
        "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile",
                 "api_key": ""},
        "anthropic": {"model": "claude-sonnet-5", "api_key": ""},
    },
    "memory": {"max_turns": 12, "save_sessions": True},
    "paths": {
        "notes_dir": "~/Documents/Jarvis/Notes",
        "workspace_dir": "~/Documents/Jarvis/Workspace",
        "screenshots_dir": "~/Pictures/Jarvis",
        "search_roots": ["~/Documents", "~/Desktop", "~/Downloads", "~/Pictures"],
    },
    "apps": {},       # custom aliases, e.g. {"my editor": "C:/Tools/editor.exe"}
    "websites": {},   # custom, e.g. {"work": "https://intranet.example.com"}
    "weather": {"default_city": "", "units": "metric"},  # metric | imperial
    "location": {"default_area": ""},
    "email": {
        "smtp_host": "smtp.gmail.com", "smtp_port": 465, "username": "", "password": "",
        "from_addr": "", "contacts": {},   # {"mum": "mum@example.com"}
    },
    "telegram": {"bot_token": "", "chat_id": ""},
    "home_assistant": {"enabled": False, "url": "http://homeassistant.local:8123", "token": "",
                       "entities": {}},   # {"living room light": "light.living_room"}
    "mqtt": {"enabled": False, "host": "localhost", "port": 1883, "username": "", "password": "",
             "topics": {}},               # {"garage door": "home/garage/set"}
    "safety": {"confirm_destructive": True, "allow_dangerous_shell": False, "shell_timeout": 30},
    "face": {"enabled": True, "size": 140},
    "phone": {"enabled": True, "port": 8742},
}

ENV_MAP = {
    "OPENAI_API_KEY": ("llm", "openai", "api_key"),
    "GROQ_API_KEY": ("llm", "groq", "api_key"),
    "ANTHROPIC_API_KEY": ("llm", "anthropic", "api_key"),
    "EMAIL_PASSWORD": ("email", "password"),
    "HA_TOKEN": ("home_assistant", "token"),
    "TELEGRAM_BOT_TOKEN": ("telegram", "bot_token"),
    "MQTT_PASSWORD": ("mqtt", "password"),
    "JARVIS_USER_NAME": ("user_name",),
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    def __init__(self, path: str | os.PathLike | None = None):
        if load_dotenv:
            load_dotenv(ROOT / ".env")
        self.path = Path(path) if path else ROOT / "config.yaml"
        data: dict = {}
        if self.path.exists() and yaml:
            with open(self.path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        self.data = _merge(DEFAULTS, data)
        for env, keys in ENV_MAP.items():
            val = os.environ.get(env)
            if val:
                node = self.data
                for k in keys[:-1]:
                    node = node[k]
                node[keys[-1]] = val
        DATA_DIR.mkdir(exist_ok=True)
        LOG_DIR.mkdir(exist_ok=True)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def path_for(self, dotted: str) -> Path:
        """Return an expanded, existing directory for a paths.* entry."""
        p = Path(os.path.expanduser(str(self.get(dotted)))).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def name(self) -> str:
        return self.get("user_name", "Sir")
