"""The Jarvis runtime: wires speech, wake detection, router, brain and tools together."""
from __future__ import annotations

import logging
import queue
import re
import sys
import threading
import time

from . import persona, router, tools
from .brain import Brain
from .config import Config
from .memory import Memory
from .speech import Listener, Speaker
from .tools.timers import Scheduler
from .wake import WakeDetector, norm

log = logging.getLogger("jarvis")
YES = {"yes", "yeah", "yep", "yup", "sure", "confirm", "confirmed", "proceed", "affirmative",
       "absolutely", "correct", "go", "do", "please", "okay", "ok", "alright"}
NO = {"no", "nope", "nah", "cancel", "stop", "negative", "don't", "dont", "abort", "wait", "never"}
CHAIN = re.compile(r"\b(then|summari[sz]e|research|and save|after that|and then|find out|explain|"
                   r"compare|write|draft)\b", re.I)


class Jarvis:
    def __init__(self, cfg: Config, text_mode: bool = False, no_tts: bool = False):
        self.cfg = cfg
        self.text_mode = text_mode
        self.name = cfg.name
        self.inq: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.awake = False
        self.last_active = time.time()
        self.last_files: list = []
        self.memory = Memory(cfg)
        self.brain = Brain(cfg, self.memory)
        self.speaker = Speaker(cfg, enabled=not no_tts)
        self.wake = WakeDetector(cfg)
        self.scheduler = Scheduler(self._on_schedule)
        tools.load_all()
        self.listener: Listener | None = None
        self.face = None
        self.phone_httpd = None
        self._phone_lock = threading.Lock()
        self._phone_log: list[tuple[int, str]] = []
        self._phone_seq = 0
        try:
            from .face import Face
            self.face = Face(self)
        except Exception:
            log.exception("Face overlay failed to load")

    def phone_replies_since(self, since: int) -> tuple[list[str], int]:
        with self._phone_lock:
            msgs = [t for n, t in self._phone_log if n > since]
            return msgs, self._phone_seq

    # ------------------------------------------------------------------ output / input
    def say(self, text: str) -> None:
        log.info("JARVIS: %s", text)
        try:
            print(f"\nJARVIS: {text}", flush=True)
        except Exception:
            pass
        with self._phone_lock:
            self._phone_seq += 1
            self._phone_log.append((self._phone_seq, text))
            self._phone_log = self._phone_log[-80:]
        if self.face:
            self.face.set_mood("speak")
        self.speaker.say(text)
        if self.face:
            self.face.set_mood("listen" if self.awake else "sleep")

    def next_input(self, timeout: float) -> str | None:
        end = time.time() + timeout
        while time.time() < end and not self.stop_event.is_set():
            try:
                _, text = self.inq.get(timeout=0.3)
                return text.strip()
            except queue.Empty:
                continue
        return None

    def confirm(self, prompt: str) -> bool:
        """Ask a yes/no question by voice or keyboard. Any doubt means 'no'."""
        if not self.cfg.get("safety.confirm_destructive", True):
            return True
        self.say(prompt)
        for _ in range(2):
            reply = self.next_input(20)
            if reply is None:
                self.say("No answer, so I'll take that as a no.")
                return False
            hit, rest = self.wake.detect(reply)
            words = norm(rest if hit else reply).split()
            if words and words[0] in NO or "not" in words or "dont" in words:
                return False
            if words and words[0] in YES:
                return True
            self.say("A simple yes or no will do.")
        return False

    # ------------------------------------------------------------------ scheduler callback
    def _on_schedule(self, kind: str, text: str, late: float) -> None:
        n = self.name
        if kind == "timer":
            self.say(f"{n}, your {text} timer has finished.")
        elif kind == "alarm":
            for _ in range(2):
                self.say(f"{n}, your alarm is going off. {text if text != 'your alarm' else ''}")
        else:
            prefix = "A belated reminder" if late > 120 else "A reminder"
            self.say(f"{prefix}, {n}: {text}.")

    # ------------------------------------------------------------------ command handling
    def handle(self, text: str) -> None:
        self.last_active = time.time()
        if self.face:
            self.face.set_mood("think")
        try:
            use_llm_first = bool(CHAIN.search(text)) and self.brain.available()
            if not use_llm_first:
                r = router.route(text)
                if r:
                    name, args = r
                    log.info("Routed: %s %s", name, args)
                    result = tools.call(name, self, args)
                    self.memory.add("user", text)
                    self.memory.add("assistant", result)
                    self.say(result)
                    return
            if self.brain.available():
                self.say(self.brain.run(text, self))
            else:
                self.say(f"I'm afraid my language core is offline, {self.name}. Start Ollama or add an API "
                         "key and I'll be far more useful. Direct commands like 'open Chrome', "
                         "'set a timer' or 'system status' still work.")
        except Exception as e:
            log.exception("Command failed")
            self.say(f"Something has gone awry, {self.name}: {str(e)[:120]}")
        finally:
            if self.face:
                self.face.set_mood("listen" if self.awake else "sleep")

    def wake_up(self, quiet: bool = False) -> None:
        self.awake = True
        self.last_active = time.time()
        if self.face:
            self.face.set_mood("listen")
        if not quiet:
            self.say(persona.pick(persona.GREETINGS, self.name))

    def go_sleep(self) -> None:
        self.awake = False
        self.say(persona.pick(persona.SLEEP_LINES, self.name))
        if self.face:
            self.face.set_mood("sleep")

    # ------------------------------------------------------------------ main loop
    def _console_reader(self) -> None:
        while not self.stop_event.is_set():
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                return
            if line.strip():
                self.inq.put(("text", line))

    def start_inputs(self) -> None:
        if sys.stdin is not None and getattr(sys.stdin, "isatty", lambda: False)():
            threading.Thread(target=self._console_reader, daemon=True, name="console").start()
        if not self.text_mode:
            self.listener = Listener(self.cfg, self.inq, self.speaker)
            self.listener.start()

    def run(self) -> None:
        self.scheduler.start()
        if self.face:
            self.face.start()
        if self.cfg.get("phone.enabled", True):
            try:
                from . import phone_server
                self.phone_httpd = phone_server.start(self, int(self.cfg.get("phone.port", 8742)))
            except Exception:
                log.exception("Phone companion failed to start")
        self.start_inputs()
        llm = (f"Language core online via {self.brain.providers()[0]}." if self.brain.available()
               else "No language model detected, so I'm in basic command mode.")
        self.say(persona.STARTUP.format(n=self.name, llm=llm))
        print(f"(Say or type '{self.cfg.get('assistant_name')}' to wake me. Ctrl+C to quit.)")
        timeout = int(self.cfg.get("wake.awake_timeout_seconds", 0) or 0)
        while not self.stop_event.is_set():
            try:
                src, text = self.inq.get(timeout=0.5)
            except queue.Empty:
                if self.awake and timeout and time.time() - self.last_active > timeout:
                    self.awake = False
                    log.info("Auto-sleep after %ss idle", timeout)
                continue
            text = (text or "").strip()
            if not text:
                continue
            log.info("HEARD (%s): %s", src, text)
            print(f"\nYOU: {text}", flush=True)
            if src in ("cmd", "phone"):  # tray or iPhone: no wake word required
                self.awake = True
                self.handle(text)
                continue
            hit, rest = self.wake.detect(text)
            if not self.awake:
                if not hit:
                    continue
                self.wake_up(quiet=bool(rest))
                if rest:
                    self.handle(rest)
                continue
            if hit:
                text = rest
                if not text:
                    self.say(persona.pick(persona.ACK_ONLY, self.name))
                    continue
            if self.wake.is_sleep(text):
                self.go_sleep()
                continue
            self.handle(text)

    def shutdown(self) -> None:
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        self.scheduler.stop()
        if self.face:
            self.face.stop()
        if self.phone_httpd:
            try:
                self.phone_httpd.shutdown()
            except Exception:
                pass
        if self.listener:
            self.listener.stop_event.set()
        try:
            self.speaker.say(persona.SHUTDOWN.format(n=self.name))
        except Exception:
            pass
