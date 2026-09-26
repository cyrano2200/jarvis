"""System control: time/date, apps & websites, volume, brightness, screenshots, lock, power, info."""
from __future__ import annotations

import datetime
import difflib
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import time
import webbrowser
from pathlib import Path

from . import tool

log = logging.getLogger("jarvis.apps")
OS = platform.system()  # "Windows" | "Linux" | "Darwin"

APPS = {
    "Windows": {
        "chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "firefox": "firefox",
        "notepad": "notepad", "calculator": "calc", "calc": "calc", "paint": "mspaint",
        "explorer": "explorer", "file explorer": "explorer", "files": "explorer",
        "cmd": "cmd", "command prompt": "cmd", "terminal": "wt", "powershell": "powershell",
        "task manager": "taskmgr", "settings": "ms-settings:", "vscode": "code",
        "vs code": "code", "visual studio code": "code", "code": "code", "spotify": "spotify",
        "word": "winword", "excel": "excel", "powerpoint": "powerpnt", "outlook": "outlook",
        "discord": "discord", "steam": "steam", "snipping tool": "snippingtool",
        "control panel": "control",
    },
    "Darwin": {
        "chrome": "Google Chrome", "safari": "Safari", "firefox": "Firefox", "terminal": "Terminal",
        "finder": "Finder", "calculator": "Calculator", "notes": "Notes", "spotify": "Spotify",
        "music": "Music", "vscode": "Visual Studio Code", "code": "Visual Studio Code",
        "settings": "System Settings", "mail": "Mail", "discord": "Discord",
    },
    "Linux": {
        "chrome": "google-chrome", "firefox": "firefox", "terminal": "x-terminal-emulator",
        "files": "xdg-open .", "calculator": "gnome-calculator", "vscode": "code", "code": "code",
        "spotify": "spotify", "discord": "discord", "settings": "gnome-control-center",
        "text editor": "gedit",
    },
}
# Process names to end when closing an app (substring match on lowercase process name).
PROC = {"chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "firefox": "firefox",
        "notepad": "notepad", "calculator": "calc", "spotify": "spotify", "discord": "discord",
        "vscode": "code", "vs code": "code", "code": "code", "word": "winword", "excel": "excel",
        "powerpoint": "powerpnt", "outlook": "outlook", "steam": "steam", "paint": "mspaint",
        "task manager": "taskmgr", "terminal": "windowsterminal"}
PROTECTED_PROCS = {"explorer.exe", "system", "svchost.exe", "csrss.exe", "winlogon.exe", "lsass.exe",
                   "wininit.exe", "services.exe", "smss.exe", "dwm.exe", "init", "systemd", "launchd",
                   "kernel_task", "python.exe", "pythonw.exe", "python", "python3"}
SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com",
    "gmail": "https://mail.google.com", "github": "https://github.com",
    "netflix": "https://www.netflix.com", "reddit": "https://www.reddit.com",
    "twitter": "https://x.com", "x": "https://x.com", "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com", "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai", "wikipedia": "https://www.wikipedia.org",
    "amazon": "https://www.amazon.com", "linkedin": "https://www.linkedin.com",
    "drive": "https://drive.google.com", "google drive": "https://drive.google.com",
    "calendar": "https://calendar.google.com", "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com", "twitch": "https://www.twitch.tv",
    "stack overflow": "https://stackoverflow.com", "news": "https://news.google.com",
}


def _run(cmd, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=kw.pop("timeout", 10), **kw)


# --------------------------------------------------------------------------- installed apps (Windows Start Menu + Store)
_APP_CACHE: dict = {"t": 0.0, "map": {}}


def _norm_app_name(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(r"[\._]+", " ", n)
    n = re.sub(r"\s+", " ", n)
    n = re.sub(r"\s*(x64|x86|64-bit|32-bit|preview|beta)$", "", n)
    return n.strip()


def _index_app(store: dict, name: str, spec: tuple) -> None:
    key = _norm_app_name(name)
    if not key or "uninstall" in key:
        return
    store.setdefault(key, spec)
    short = re.sub(r"\s+(app|desktop|microsoft)$", "", key).strip()
    if short and short != key:
        store.setdefault(short, spec)


def _scan_shortcuts(store: dict) -> None:
    roots = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("USERPROFILE", "")) / "Desktop",
        Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
    ]
    for root in roots:
        if not root.exists():
            continue
        try:
            for p in root.rglob("*"):
                if p.suffix.lower() in {".lnk", ".url", ".appref-ms"}:
                    _index_app(store, p.stem, ("lnk", str(p)))
        except OSError:
            continue


def _scan_start_apps(store: dict) -> None:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=40,
        )
        data = json.loads(r.stdout or "[]")
        if isinstance(data, dict):
            data = [data]
        for row in data or []:
            name, appid = row.get("Name") or "", row.get("AppID") or ""
            if name and appid:
                _index_app(store, name, ("appid", appid))
    except Exception as e:
        log.warning("Get-StartApps failed: %s", e)


def _windows_apps() -> dict:
    now = time.time()
    if _APP_CACHE["map"] and now - _APP_CACHE["t"] < 600:
        return _APP_CACHE["map"]
    store: dict = {}
    _scan_shortcuts(store)
    _scan_start_apps(store)
    _APP_CACHE["t"] = now
    _APP_CACHE["map"] = store
    log.info("Indexed %s installed apps", len(store))
    return store


def _score_app(query: str, name: str) -> float:
    if query == name:
        return 1.0
    if name.startswith(query) or query.startswith(name):
        return 0.92
    if query in name:
        return 0.84
    return difflib.SequenceMatcher(None, query, name).ratio()


def _resolve_installed(query: str) -> tuple[str, tuple] | None:
    if OS != "Windows":
        return None
    q = _norm_app_name(query)
    apps = _windows_apps()
    if q in apps:
        return q, apps[q]
    scored = []
    for name, spec in apps.items():
        s = _score_app(q, name)
        if s >= 0.72:
            scored.append((s, len(name), name, spec))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], x[1]))
    best = scored[0]
    if best[0] >= 0.72:
        return best[2], best[3]
    return None


def _launch_spec(spec: tuple) -> bool:
    kind, val = spec
    try:
        if kind == "lnk":
            os.startfile(val)  # type: ignore[attr-defined]
            return True
        if kind == "appid":
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{val}"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if kind == "uri":
            os.startfile(val)  # type: ignore[attr-defined]
            return True
        if kind == "cmd":
            return _launch_app(val)
    except Exception as e:
        log.warning("Launch failed (%s %s): %s", kind, val, e)
    return False


def _launch_app(cmd: str) -> bool:
    try:
        if OS == "Windows":
            if cmd.endswith(":") or ":" in cmd and not cmd[1:2] == ":":
                os.startfile(cmd)  # type: ignore[attr-defined]
                return True
            path = Path(cmd)
            if path.exists():
                os.startfile(str(path))  # type: ignore[attr-defined]
                return True
            # cmd's start uses the first quoted arg as a window title.
            r = subprocess.run(["cmd", "/c", "start", "", cmd], capture_output=True, timeout=8)
            return r.returncode == 0
        if OS == "Darwin":
            return _run(["open", "-a", cmd]).returncode == 0
        parts = cmd.split()
        if shutil.which(parts[0]):
            subprocess.Popen(parts, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except Exception:
        pass
    return False


# --------------------------------------------------------------------------- time & date
@tool("get_time", "Current local time.")
def get_time(ctx):
    return datetime.datetime.now().strftime("It is %I:%M %p").replace(" 0", " ") + f", {ctx.name}."


@tool("get_date", "Today's date and weekday.")
def get_date(ctx):
    d = datetime.datetime.now()
    return f"Today is {d.strftime('%A')}, {d.day} {d.strftime('%B %Y')}, {ctx.name}."


# --------------------------------------------------------------------------- apps / websites
@tool("open", "Open any installed PC application or a website by name.",
      {"target": "app or site name, or URL"})
def open_target(ctx, target: str):
    t = target.lower().strip().rstrip(".")
    t = re.sub(r"^(the |my )", "", t)
    extra_play = None
    m = re.match(r"^(.+?)\s+and\s+play(?:\s+(.+))?$", t)
    if m:
        t, extra_play = m.group(1).strip(), (m.group(2) or "music").strip()
    t = re.sub(r"\s+(please|for me)$", "", t)
    custom_apps = {k.lower(): v for k, v in (ctx.cfg.get("apps") or {}).items()}
    custom_sites = {k.lower(): v for k, v in (ctx.cfg.get("websites") or {}).items()}
    opened = None
    if t in custom_sites:
        webbrowser.open(custom_sites[t])
        opened = t
    if opened is None and t in SITES:
        webbrowser.open(SITES[t])
        opened = t
    if opened is None and (t.startswith("http") or re.fullmatch(r"[\w-]+(\.[\w-]+)+(/\S*)?", t)):
        webbrowser.open(t if t.startswith("http") else "https://" + t)
        opened = t
    if opened is None:
        cmd = custom_apps.get(t) or APPS.get(OS, {}).get(t)
        hit = _resolve_installed(t)
        if hit:
            name, spec = hit
            if _launch_spec(spec):
                opened = name
        if opened is None and cmd and _launch_app(cmd):
            opened = t
        if opened is None and t in ("spotify",):
            if _launch_app("spotify:") or _launch_spec(("uri", "spotify:")):
                opened = "spotify"
        if opened is None and _launch_app(cmd or t):
            opened = t
    if opened is None:
        return (f"I couldn't find an application or site called '{target}', {ctx.name}. "
                "Say 'list apps' if you want me to name what's installed.")
    if extra_play:
        try:
            from .media import play_music
            play_music(ctx, extra_play, "spotify" if "spotify" in opened else "youtube")
        except Exception:
            pass
    pretty = opened if opened != t else target
    return f"Opening {pretty}, {ctx.name}."


@tool("list_apps", "List installed applications Jarvis can open (optional filter).",
      {"filter": "optional name fragment, e.g. spotify"})
def list_apps(ctx, filter: str = ""):
    if OS != "Windows":
        names = sorted(APPS.get(OS, {}))
        return "I can open: " + ", ".join(names[:40]) + f", {ctx.name}."
    apps = _windows_apps()
    needle = _norm_app_name(filter or "")
    names = sorted({k for k in apps if not needle or needle in k})
    if not names:
        return f"Nothing installed matching '{filter}', {ctx.name}."
    shown = names[:25]
    more = f" …and {len(names) - 25} more" if len(names) > 25 else ""
    return f"Installed apps I can open: {', '.join(shown)}{more}."


@tool("close_app", "Close a running application by name.", {"name": "application name"})
def close_app(ctx, name: str):
    import psutil

    key = name.lower().strip()
    key = re.sub(r"^(the |my )", "", key)
    needle = PROC.get(key, key.replace(" ", ""))
    closed = 0
    for p in psutil.process_iter(["name"]):
        pname = (p.info["name"] or "").lower()
        if needle in pname and pname not in PROTECTED_PROCS and p.pid != os.getpid():
            try:
                p.terminate()
                closed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    if closed:
        return f"Closed {name}, {ctx.name}."
    return f"I couldn't find {name} running, {ctx.name}."


# --------------------------------------------------------------------------- volume
def _win_endpoint():
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    dev = AudioUtilities.GetSpeakers()
    if hasattr(dev, "EndpointVolume"):  # newer pycaw
        return dev.EndpointVolume
    iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


def get_volume() -> int | None:
    try:
        if OS == "Windows":
            return round(_win_endpoint().GetMasterVolumeLevelScalar() * 100)
        if OS == "Linux":
            m = re.search(r"(\d+)%", _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"]).stdout)
            return int(m.group(1)) if m else None
        if OS == "Darwin":
            return int(_run(["osascript", "-e", "output volume of (get volume settings)"]).stdout.strip())
    except Exception:
        return None
    return None


def set_volume(n: int) -> bool:
    n = max(0, min(100, int(n)))
    try:
        if OS == "Windows":
            _win_endpoint().SetMasterVolumeLevelScalar(n / 100, None)
            return True
        if OS == "Linux":
            return _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{n}%"]).returncode == 0
        if OS == "Darwin":
            return _run(["osascript", "-e", f"set volume output volume {n}"]).returncode == 0
    except Exception:
        return False
    return False


def _mute(flag: bool) -> bool:
    try:
        if OS == "Windows":
            _win_endpoint().SetMute(1 if flag else 0, None)
            return True
        if OS == "Linux":
            return _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if flag else "0"]).returncode == 0
        if OS == "Darwin":
            return _run(["osascript", "-e", f"set volume output muted {'true' if flag else 'false'}"]).returncode == 0
    except Exception:
        return False
    return False


@tool("volume", "Control system volume.",
      {"action": "up | down | set | mute | unmute | get", "level": "0-100, for 'set'"})
def volume(ctx, action: str = "get", level: int | None = None):
    action = action.lower()
    cur = get_volume()
    if action in ("mute", "unmute"):
        return (f"Muted, {ctx.name}." if action == "mute" else f"Sound restored, {ctx.name}.") \
            if _mute(action == "mute") else "I couldn't reach the audio controls."
    if action == "get":
        return f"Volume is at {cur} percent, {ctx.name}." if cur is not None else "I can't read the volume."
    if action == "set":
        target = int(level if level is not None else 50)
    else:
        step = int(level) if level else 10
        if cur is None:  # keyboard fallback
            import pyautogui
            for _ in range(max(1, step // 2)):
                pyautogui.press("volumeup" if action == "up" else "volumedown")
            return f"Adjusted the volume, {ctx.name}."
        target = cur + step if action == "up" else cur - step
    target = max(0, min(100, target))
    if set_volume(target):
        return f"Volume set to {target} percent, {ctx.name}."
    return "I couldn't adjust the volume on this system."


# --------------------------------------------------------------------------- brightness
@tool("brightness", "Control screen brightness.",
      {"action": "up | down | set | get", "level": "0-100"})
def brightness(ctx, action: str = "get", level: int | None = None):
    try:
        import screen_brightness_control as sbc
    except ImportError:
        return "Brightness control needs the 'screen-brightness-control' package."
    try:
        cur = sbc.get_brightness()[0]
        if action == "get":
            return f"Brightness is at {cur} percent, {ctx.name}."
        if action == "set":
            target = int(level if level is not None else 50)
        else:
            step = int(level) if level else 15
            target = cur + step if action == "up" else cur - step
        target = max(0, min(100, target))
        sbc.set_brightness(target)
        return f"Brightness set to {target} percent, {ctx.name}."
    except Exception as e:
        return f"This display doesn't allow software brightness control ({e})."


# --------------------------------------------------------------------------- screenshot / lock / power
@tool("screenshot", "Take a screenshot and save it to the screenshots folder.")
def screenshot(ctx):
    import pyautogui

    path = ctx.cfg.path_for("paths.screenshots_dir") / f"screenshot-{time.strftime('%Y%m%d-%H%M%S')}.png"
    pyautogui.screenshot().save(path)
    return f"Screenshot saved to {path}, {ctx.name}."


@tool("lock_screen", "Lock the computer.")
def lock_screen(ctx):
    if OS == "Windows":
        _run(["rundll32.exe", "user32.dll,LockWorkStation"])
    elif OS == "Darwin":
        _run(["pmset", "displaysleepnow"])
    else:
        if _run(["loginctl", "lock-session"]).returncode != 0:
            _run(["xdg-screensaver", "lock"])
    return f"Locking the workstation, {ctx.name}."


@tool("power", "Shut down, restart or sleep the computer (asks for confirmation).",
      {"action": "shutdown | restart | sleep"})
def power(ctx, action: str):
    action = action.lower()
    if action not in ("shutdown", "restart", "sleep"):
        return "Unknown power action."
    if not ctx.confirm(f"You'd like me to {action} the computer, {ctx.name}. Shall I proceed?"):
        return "Cancelled. Nothing has been changed."
    cmds = {
        "Windows": {"shutdown": "shutdown /s /t 5", "restart": "shutdown /r /t 5",
                    "sleep": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"},
        "Linux": {"shutdown": "systemctl poweroff", "restart": "systemctl reboot",
                  "sleep": "systemctl suspend"},
        "Darwin": {"shutdown": "osascript -e 'tell app \"System Events\" to shut down'",
                   "restart": "osascript -e 'tell app \"System Events\" to restart'",
                   "sleep": "pmset sleepnow"},
    }[OS]
    subprocess.Popen(cmds[action], shell=True)
    return f"Very well. {action.capitalize()} in progress."


# --------------------------------------------------------------------------- system info
def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "unavailable"


@tool("system_info", "CPU, RAM, disk, battery and network status.",
      {"what": "all | cpu | ram | disk | battery | network"})
def system_info(ctx, what: str = "all"):
    import psutil

    what = (what or "all").lower()
    what = {"memory": "ram", "storage": "disk", "internet": "network", "wifi": "network"}.get(what, what)
    parts = []
    if what in ("all", "cpu"):
        parts.append(f"CPU at {psutil.cpu_percent(interval=0.5):.0f} percent across "
                     f"{psutil.cpu_count()} threads")
    if what in ("all", "ram"):
        m = psutil.virtual_memory()
        parts.append(f"memory {m.percent:.0f} percent used, {m.available / 2**30:.1f} of "
                     f"{m.total / 2**30:.0f} gigabytes free")
    if what in ("all", "disk"):
        d = psutil.disk_usage(Path.home().anchor or "/")
        parts.append(f"disk {d.percent:.0f} percent full, {d.free / 2**30:.0f} gigabytes free")
    if what in ("all", "battery"):
        b = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        if b:
            parts.append(f"battery at {b.percent:.0f} percent, {'charging' if b.power_plugged else 'on battery'}")
        elif what == "battery":
            parts.append("no battery detected; you're on mains power")
    if what in ("all", "network"):
        io = psutil.net_io_counters()
        parts.append(f"network address {_local_ip()}, {io.bytes_recv / 2**20:.0f} megabytes received "
                     f"and {io.bytes_sent / 2**20:.0f} sent this session")
    return f"{ctx.name}, " + "; ".join(parts) + "."
