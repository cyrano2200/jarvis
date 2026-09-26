"""Media playback control and music launching."""
from __future__ import annotations

import os
import platform
import subprocess
import webbrowser
from urllib.parse import quote_plus

from . import tool

OS = platform.system()


def _mac_player(cmd: str) -> bool:
    for app in ("Spotify", "Music"):
        r = subprocess.run(["osascript", "-e", f'tell application "System Events" to (name of processes) contains "{app}"'],
                           capture_output=True, text=True)
        if "true" in r.stdout:
            subprocess.run(["osascript", "-e", f'tell application "{app}" to {cmd}'], capture_output=True)
            return True
    return False


@tool("media_control", "Control media playback.", {"action": "play_pause | next | previous | stop"})
def media_control(ctx, action: str = "play_pause"):
    action = action.lower().replace(" ", "_")
    keys = {"play_pause": "playpause", "next": "nexttrack", "previous": "prevtrack", "stop": "stop"}
    if action not in keys:
        return "Unknown media action."
    ok = False
    if OS == "Darwin":
        ok = _mac_player({"play_pause": "playpause", "next": "next track",
                          "previous": "previous track", "stop": "pause"}[action])
    else:
        if OS == "Linux":
            pc = {"play_pause": "play-pause", "next": "next", "previous": "previous", "stop": "stop"}[action]
            try:
                ok = subprocess.run(["playerctl", pc], capture_output=True).returncode == 0
            except FileNotFoundError:
                ok = False
        if not ok:
            import pyautogui
            pyautogui.press(keys[action])
            ok = True
    return f"Done, {ctx.name}." if ok else "I couldn't find a media player to control."


@tool("play_music", "Search for and play music/video on YouTube or Spotify.",
      {"query": "song, artist or playlist", "service": "youtube | spotify (default youtube)"})
def play_music(ctx, query: str, service: str = "youtube"):
    q = quote_plus(query)
    if service.lower() == "spotify":
        uri = f"spotify:search:{q}"
        if OS == "Windows":
            os.startfile(uri)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["open" if OS == "Darwin" else "xdg-open", uri])
        return f"Searching Spotify for {query}, {ctx.name}. You may need to press play."
    webbrowser.open(f"https://www.youtube.com/results?search_query={q}")
    return f"Pulling up {query} on YouTube, {ctx.name}."
