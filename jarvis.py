#!/usr/bin/env python3
"""Jarvis - local voice assistant. Run `python jarvis.py --help` for options."""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys

if sys.stdout is None:  # pythonw.exe has no console
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from jarvis_core.config import Config  # noqa: E402
from jarvis_core.logger import setup_logging  # noqa: E402


def list_mics() -> None:
    import speech_recognition as sr

    for i, name in enumerate(sr.Microphone.list_microphone_names()):
        print(f"[{i}] {name}")
    print("\nSet speech.stt.mic_index in config.yaml to the number you want.")


def doctor(cfg: Config) -> None:
    print("Dependency check:")
    mods = {"speech_recognition": "SpeechRecognition (mic input)", "pyaudio": "PyAudio (mic driver)",
            "faster_whisper": "faster-whisper (offline STT)", "edge_tts": "edge-tts (neural voice)",
            "pygame": "pygame (audio playback)", "pyttsx3": "pyttsx3 (offline voice)",
            "psutil": "psutil", "pyautogui": "pyautogui", "requests": "requests", "yaml": "PyYAML",
            "bs4": "beautifulsoup4", "ddgs": "ddgs (web search)", "send2trash": "send2trash",
            "pystray": "pystray (tray)", "screen_brightness_control": "screen-brightness-control",
            "pycaw": "pycaw (Windows volume)"}
    for m, label in mods.items():
        ok = importlib.util.find_spec(m) is not None
        print(f"  [{'OK' if ok else '--'}] {label}")
    from jarvis_core.brain import Brain
    from jarvis_core.memory import Memory

    b = Brain(cfg, Memory(cfg))
    print("\nLLM providers ready:", b.providers() or "none (basic command mode only)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Jarvis local voice assistant")
    ap.add_argument("--config", help="path to config.yaml")
    ap.add_argument("--text", action="store_true", help="typed input only (no microphone)")
    ap.add_argument("--no-tts", action="store_true", help="don't speak aloud")
    ap.add_argument("--tray", action="store_true", help="run in the system tray")
    ap.add_argument("--debug", action="store_true", help="verbose logging")
    ap.add_argument("--list-mics", action="store_true", help="list microphones and exit")
    ap.add_argument("--check", action="store_true", help="check dependencies/LLM and exit")
    a = ap.parse_args()

    cfg = Config(a.config)
    setup_logging(a.debug)
    if a.list_mics:
        list_mics()
        return 0
    if a.check:
        doctor(cfg)
        return 0

    from jarvis_core.assistant import Jarvis

    app = Jarvis(cfg, text_mode=a.text, no_tts=a.no_tts)
    try:
        if a.tray:
            from jarvis_core.tray import run_tray
            run_tray(app)
        else:
            app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
