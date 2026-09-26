"""Speech input (faster-whisper offline / Google) and output (edge-tts / pyttsx3)."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import threading
import time

log = logging.getLogger("jarvis.speech")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

# Whisper tends to hallucinate these on silence/noise.
HALLUCINATIONS = {"you", "thank you", "thanks for watching", "bye", "thank you.", ".", "uh", "um",
                  "hmm", "thanks", "okay"}


def clean_for_speech(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"https?://\S+", "the link", text)
    text = re.sub(r"[*_`#>]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


class Speaker:
    """Blocking text-to-speech with an edge-tts primary and pyttsx3 fallback."""

    def __init__(self, cfg, enabled: bool = True):
        self.c = cfg.get("speech.tts")
        self.enabled = enabled
        self._lock = threading.Lock()
        self.busy = False
        self.last_activity = 0.0
        self._edge_ok = self.c.get("engine", "edge") == "edge"

    def say(self, text: str) -> None:
        text = clean_for_speech(text)
        if not text or not self.enabled:
            return
        with self._lock:
            self.busy = True
            self.last_activity = time.time()
            try:
                if self._edge_ok:
                    try:
                        self._edge(text)
                        return
                    except Exception as e:
                        log.warning("edge-tts failed (%s); falling back to pyttsx3", e)
                        self._edge_ok = False
                self._pyttsx3(text)
            except Exception as e:
                log.error("TTS failed: %s", e)
            finally:
                self.busy = False
                self.last_activity = time.time()

    # -- edge-tts ---------------------------------------------------------------------
    def _edge(self, text: str) -> None:
        import edge_tts

        fd, path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        try:
            async def gen():
                comm = edge_tts.Communicate(
                    text, self.c["edge_voice"], rate=self.c["edge_rate"],
                    pitch=self.c["edge_pitch"], volume=self.c["edge_volume"])
                await comm.save(path)

            asyncio.run(gen())
            self._play(path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    @staticmethod
    def _play(path: str) -> None:
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
        pygame.mixer.music.unload()

    # -- pyttsx3 (fully offline) --------------------------------------------------------
    def _pyttsx3(self, text: str) -> None:
        import pyttsx3

        engine = pyttsx3.init()  # fresh engine per call avoids known hangs on Windows
        engine.setProperty("rate", int(self.c.get("pyttsx3_rate", 175)))
        hint = re.compile(self.c.get("pyttsx3_voice_hint", "british|george"), re.I)
        for v in engine.getProperty("voices"):
            if hint.search(f"{v.name} {getattr(v, 'id', '')}"):
                engine.setProperty("voice", v.id)
                break
        engine.say(text)
        engine.runAndWait()
        engine.stop()


class Listener(threading.Thread):
    """Continuously transcribes microphone speech and pushes ('voice', text) into a queue."""

    def __init__(self, cfg, out_queue, speaker: Speaker):
        super().__init__(daemon=True, name="listener")
        self.c = cfg.get("speech.stt")
        self.q = out_queue
        self.speaker = speaker
        self.stop_event = threading.Event()
        self._whisper = None

    def _load_whisper(self):
        from faster_whisper import WhisperModel

        log.info("Loading Whisper model %s ...", self.c["whisper_model"])
        self._whisper = WhisperModel(self.c["whisper_model"], device=self.c["device"],
                                     compute_type=self.c["compute_type"])

    def transcribe(self, audio) -> str:
        engine = self.c.get("engine", "whisper")
        if engine == "whisper":
            try:
                import numpy as np

                if self._whisper is None:
                    self._load_whisper()
                raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
                arr = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
                segs, _ = self._whisper.transcribe(
                    arr, language=self.c.get("language", "en"), beam_size=1, vad_filter=True,
                    condition_on_previous_text=False, initial_prompt="Hey Jarvis.")
                text = " ".join(s.text.strip() for s in segs).strip()
                return "" if text.lower().strip(" .!") in HALLUCINATIONS else text
            except ImportError:
                log.warning("faster-whisper not installed; using Google STT")
                self.c["engine"] = "google"
            except Exception as e:
                log.error("Whisper failed: %s", e)
                return ""
        import speech_recognition as sr

        try:
            return sr.Recognizer().recognize_google(audio, language=self.c.get("language", "en"))
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            log.error("Google STT unavailable: %s", e)
            time.sleep(2)
            return ""

    def run(self) -> None:
        import speech_recognition as sr

        r = sr.Recognizer()
        r.pause_threshold = float(self.c.get("pause_threshold", 0.8))
        r.dynamic_energy_threshold = True
        if self.c.get("energy_threshold"):
            r.energy_threshold = float(self.c["energy_threshold"])
            r.dynamic_energy_threshold = False
        try:
            mic = sr.Microphone(device_index=self.c.get("mic_index"))
        except Exception as e:
            log.error("No microphone available: %s", e)
            print("!! No microphone found - falling back to typed input only.")
            return
        with mic as source:
            log.info("Calibrating for ambient noise...")
            r.adjust_for_ambient_noise(source, duration=1.0)
            log.info("Listening (energy threshold %.0f)", r.energy_threshold)
            while not self.stop_event.is_set():
                t0 = time.time()
                try:
                    audio = r.listen(source, timeout=1, phrase_time_limit=self.c.get("phrase_time_limit", 20))
                except sr.WaitTimeoutError:
                    continue
                except Exception as e:
                    log.error("Mic error: %s", e)
                    time.sleep(1)
                    continue
                # Discard anything captured while Jarvis was talking (avoids hearing himself).
                if self.speaker.busy or self.speaker.last_activity > t0:
                    continue
                try:
                    text = self.transcribe(audio)
                except Exception as e:
                    log.error("Transcription error: %s", e)
                    continue
                if text:
                    self.q.put(("voice", text))
