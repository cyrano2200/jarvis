"""System-tray mode: Jarvis runs in a background thread; the tray icon owns the main thread."""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import threading

from .config import LOG_DIR

log = logging.getLogger("jarvis.tray")


def _icon_image():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), fill=(8, 20, 34, 255), outline=(0, 200, 255, 255), width=4)
    d.ellipse((20, 20, 44, 44), fill=(0, 200, 255, 255))
    d.ellipse((27, 27, 37, 37), fill=(220, 250, 255, 255))
    return img


def _ask_command(app) -> None:
    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        cmd = simpledialog.askstring("Jarvis", f"Your command, {app.name}?", parent=root)
        root.destroy()
        if cmd:
            app.inq.put(("cmd", cmd))
    except Exception as e:
        log.error("Command dialog failed: %s", e)


def _open_logs() -> None:
    if platform.system() == "Windows":
        os.startfile(str(LOG_DIR))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["open" if platform.system() == "Darwin" else "xdg-open", str(LOG_DIR)])


def run_tray(app) -> None:
    try:
        import pystray
        from pystray import MenuItem as Item
    except ImportError:
        print("pystray/Pillow not installed - running without tray.")
        app.run()
        return

    def on_quit(icon, item):
        app.shutdown()
        icon.stop()

    icon = pystray.Icon("jarvis", _icon_image(), "Jarvis", menu=pystray.Menu(
        Item("Wake Jarvis", lambda i, it: app.wake_up()),
        Item("Standby", lambda i, it: app.go_sleep()),
        Item("Type a command...", lambda i, it: threading.Thread(target=_ask_command, args=(app,), daemon=True).start()),
        Item("Open logs folder", lambda i, it: _open_logs()),
        Item("Quit", on_quit),
    ))
    threading.Thread(target=app.run, daemon=True, name="jarvis-main").start()
    icon.run()
