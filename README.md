# J.A.R.V.I.S. - your local voice assistant

Calm, dry-witted, slightly British, and unfailingly loyal. Wake him with **"Hey Jarvis"**, give commands by voice or keyboard, and he'll run your PC.

- **Offline-first:** speech recognition (faster-whisper), command routing and a local LLM (Ollama / LM Studio) all run on your machine. Cloud (Groq/OpenAI/Anthropic) is an optional fallback.
- **Safe by design:** deletions, shell commands, emails, and power actions always ask "yes/no" first. Dangerous commands are refused outright.
- **Modular:** `speech`, `brain`, `tools`, `memory`, `config` are separate modules; adding a skill is ~10 lines.

## Project layout

```
jarvis/
├── jarvis.py               # entry point (run this)
├── config.yaml             # all settings (wake words, voice, LLM, paths, integrations)
├── .env.example            # copy to .env for API keys/passwords
├── requirements.txt
├── setup.bat / setup.sh    # one-click install (Windows / Linux+macOS)
├── jarvis_core/
│   ├── assistant.py        # main loop: wake/sleep state, confirmations, scheduling
│   ├── wake.py             # wake-phrase + sleep-phrase detection (fuzzy)
│   ├── speech.py           # STT (faster-whisper/Google) and TTS (edge-tts/pyttsx3)
│   ├── brain.py            # LLM providers + multi-step tool-agent loop
│   ├── router.py           # instant offline command matching (no LLM needed)
│   ├── persona.py          # Jarvis personality + system prompt
│   ├── memory.py           # session memory + persistent facts
│   ├── config.py, logger.py, tray.py
│   └── tools/              # system, files, web, comms, media, shell, timers, notes, smarthome
├── data/                   # memory, reminders, session logs (created automatically)
└── logs/jarvis.log
```

## Installation - Windows (primary)

1. **Install Python 3.10-3.13** from python.org. Tick **"Add python.exe to PATH"**.
2. **Download/clone** this folder anywhere (e.g. `C:\Jarvis`).
3. **Double-click `setup.bat`.** It creates a virtual environment, installs everything, creates `.env`, `run_jarvis.bat`, and a **Jarvis desktop shortcut** (tray mode).
   - If PyAudio fails: `venv\Scripts\activate` then `pip install pipwin` and `pipwin install pyaudio`.
4. **Pick a brain** (any one; you can skip this and use basic commands only):
   - **Local (recommended):** install [Ollama](https://ollama.com), then `ollama pull llama3.1:8b`. Nothing else to configure.
   - **LM Studio:** load a model, start its Local Server (port 1234).
   - **Cloud:** put a key in `.env` (`GROQ_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`).
5. **Check everything:** `venv\Scripts\python jarvis.py --check`
6. **Run:** double-click `run_jarvis.bat` (console) or the **Jarvis** desktop shortcut (silent, system tray).
   First launch downloads the Whisper speech model (~150 MB) once.

**Auto-start at login:** press `Win+R`, type `shell:startup`, drop a copy of the Jarvis shortcut in.

### Linux / macOS notes

Run `./setup.sh` (installs PortAudio, espeak-ng, playerctl, brightnessctl via apt/brew where possible), then `./run_jarvis.sh`.
- **Linux:** volume uses `pactl`; media keys use `playerctl`; brightness uses `screen-brightness-control` (may need `brightnessctl` permissions). Wayland limits `pyautogui` screenshots - use X11 or install `grim`.
- **macOS:** grant Terminal **Microphone** and **Accessibility** permissions. Brightness control isn't supported; media control targets Spotify/Music. Tray mode works.
- Global hotkeys/pywinauto-style window control are Windows-only and not used by default.

## Using Jarvis

**Wake:** "Jarvis", "Hi/Hey/Okay Jarvis", "Wake up Jarvis", "Jarvis, you there?" (typed or spoken, any case, tolerant of mis-hearings like "Jervis"). He replies ("Yes, Sir?") and stays awake, listening continuously.
**Sleep:** "That's all", "Sleep", "Go to sleep", "Standby".
**One-shot:** "Hey Jarvis, what's the weather in Paris?" works in a single breath.

| Category | Examples |
|---|---|
| Apps & sites | "Open Chrome", "Open YouTube", "Close Spotify" |
| System | "Volume to 30", "Mute", "Brightness up", "Take a screenshot", "Lock the computer", "System status", "How's my battery?" |
| Files | "Find my tax return", "Open the budget spreadsheet", "Rename X to Y", "Move X to Documents", "Delete old-draft.docx" *(asks first)* |
| Web | "Search for the best mirrorless cameras", "What's the weather?", "Read this page..." |
| Time | "What time is it?", "Set a timer for 10 minutes", "Alarm at 7:30 am", "Remind me to call Mum in 20 minutes" |
| Notes | "Take a note that the wifi password changed", "Read my notes", "Remember that I prefer dark mode" |
| Media | "Pause", "Next track", "Play Daft Punk on Spotify" |
| Comms | "Email Mum: I'll be late" *(confirms)*, "Send a Telegram message..." |
| Terminal | "Run ipconfig" (safe), "Run pip install requests" *(asks first)* |
| Smart home | "Turn off the living room light", "Set the bedroom light to 30" |
| Multi-step | "Research solid-state batteries, summarise it, and save it to a file" |

**Typing:** you can type commands in the console at any time (wake rules apply). In tray mode, right-click the icon → *Type a command...*.

**Flags:** `--text` (no mic), `--no-tts`, `--tray`, `--debug`, `--list-mics`, `--check`, `--config path`.

## Configuration

Everything lives in **`config.yaml`** (documented inline). Secrets go in **`.env`**.

| Setting | Where |
|---|---|
| Your name ("Sir", "Boss"...) | `user_name` |
| Wake word / aliases | `assistant_name`, `wake.aliases` |
| Voice, speed, pitch | `speech.tts.*` |
| Mic choice, accuracy, noise | `speech.stt.*` |
| Preferred LLM & order | `llm.provider_order`, `llm.<provider>.model` |
| API keys | `.env` |
| Folders Jarvis may search/write | `paths.*` |
| Email / Telegram / Home Assistant / MQTT | respective sections |

## How to customize

- **Change the voice:** set `speech.tts.edge_voice` (`en-GB-RyanNeural`, `en-GB-ThomasNeural`, `en-AU-WilliamNeural`; list all with `edge-tts --list-voices`). For fully offline use, set `engine: pyttsx3`.
- **New wake word:** set `assistant_name: Friday` (and add likely mis-hearings under `wake.aliases`).
- **Sharper hearing:** use `whisper_model: small.en`; on an NVIDIA GPU set `device: cuda`, `compute_type: float16`.
- **Personality:** edit `jarvis_core/persona.py` (greetings and the system prompt).
- **Add app shortcuts:** put `apps:` / `websites:` entries in `config.yaml`.
- **Add a new skill/tool:** in any file under `jarvis_core/tools/` (or a new module added to `MODULES` in `tools/__init__.py`):
  ```python
  from . import tool

  @tool("coin_flip", "Flip a coin.")
  def coin_flip(ctx):
      import random
      return f"{random.choice(['Heads', 'Tails'])}, {ctx.name}."
  ```
  The LLM discovers it automatically. For an instant offline trigger add one line to `router.py`:
  `rule(r"^flip a coin$")(lambda m: ("coin_flip", {}))`
- **Ask for confirmation** inside any tool: `if not ctx.confirm("Shall I proceed, Sir?"): return "Cancelled."`

## Security notes

- Destructive actions (delete, shell, email, Telegram, shutdown/restart/sleep) require an explicit yes. Unclear answers count as no.
- Deleting sends to Recycle Bin/Trash when `send2trash` is installed. System folders and your home folder are protected.
- Shell commands matching a danger list (`rm -rf`, `format`, `reg delete`, `sudo`, download-and-execute, encoded PowerShell...) are refused unless you set `safety.allow_dangerous_shell: true`.
- Web pages and tool outputs are given to the LLM as untrusted data, with instructions to ignore commands hidden in them.
- With `edge-tts` or Google STT, text/audio go to those services. Use `pyttsx3` + `whisper` for a fully offline setup. Keep `.env` private.

## Troubleshooting

| Problem | Fix |
|---|---|
| Never wakes | `python jarvis.py --list-mics`, set `mic_index`; lower `fuzzy_threshold`; try `whisper_model: small.en`. |
| Wakes on noise / hears himself | Raise `energy_threshold` (e.g. 1200); use headphones. |
| "Language core is offline" | Start Ollama (`ollama serve`) or add an API key; check with `--check`. |
| No voice | If offline, edge-tts falls back to pyttsx3 automatically; check `logs/jarvis.log`. |
| Volume fails on Windows | `pip install pycaw comtypes`. |
| Slow responses | Smaller model (`llama3.2:3b`), or use Groq for near-instant cloud replies. |

Logs: `logs/jarvis.log`. Conversation history: `data/session-*.jsonl`. Facts: `data/memory.json`.
