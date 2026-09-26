"""Always-on-top Jarvis visor. Drawn from scratch; window stays put (drag to move)."""
from __future__ import annotations

import ctypes
import logging
import math
import threading
import time
from ctypes import wintypes

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageTk

log = logging.getLogger("jarvis.face")

CYAN = (0, 214, 255, 255)
CYAN_DIM = (0, 140, 180, 220)
WHITE = (230, 250, 255, 255)
KEY_HEX = "#FF00FF"


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER)]


def _hwnd(root) -> int:
    user32 = ctypes.windll.user32
    hwnd = int(root.winfo_id())
    root_hwnd = user32.GetAncestor(hwnd, 2)
    return root_hwnd or hwnd


def _enable_layered(hwnd: int) -> None:
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x80000
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)


def _paint_layered(hwnd: int, image: Image.Image) -> None:
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    w, h = image.size
    arr = np.array(image.convert("RGBA"))
    a = arr[:, :, 3:4].astype(np.float32) / 255.0
    arr = arr.copy()
    arr[:, :, :3] = (arr[:, :, :3].astype(np.float32) * a).astype(np.uint8)
    bgra = np.ascontiguousarray(arr[:, :, [2, 1, 0, 3]][::-1])
    raw = bgra.tobytes()

    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0
    bits = ctypes.c_void_p()
    hbmp = gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    if not hbmp or not bits:
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)
        return
    ctypes.memmove(bits, raw, len(raw))
    old = gdi32.SelectObject(hdc_mem, hbmp)
    blend = BLENDFUNCTION(0, 0, 255, 1)
    src = wintypes.POINT(0, 0)
    size = wintypes.SIZE(w, h)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    dst = wintypes.POINT(rect.left, rect.top)
    user32.UpdateLayeredWindow(
        hwnd, hdc_screen, ctypes.byref(dst), ctypes.byref(size),
        hdc_mem, ctypes.byref(src), 0, ctypes.byref(blend), 2,
    )
    gdi32.SelectObject(hdc_mem, old)
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)


def _col(rgb_a, scale: float, alpha: float | None = None):
    r, g, b, a = rgb_a
    aa = int((alpha if alpha is not None else a) * scale)
    return (int(r * min(1.0, scale + 0.15)), int(g * min(1.0, scale + 0.15)),
            int(b * min(1.0, scale + 0.15)), max(0, min(255, aa)))


def render_face(size: int, mood: str, t: float) -> Image.Image:
    """Sharp angular helmet, thin slit visor. Transparent outside the outline."""
    s = size * 3
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = s / 2, s / 2 + s * 0.02
    H = s * 0.46

    if mood == "speak":
        power = 1.0
        mouth = 0.5 + 0.5 * abs(math.sin(t * 16))
        eye_w = 1.05
        scan = None
    elif mood == "think":
        power, mouth, eye_w, scan = 0.9, 0.04, 0.9, None
    elif mood == "listen":
        power, mouth, eye_w = 0.85, 0.02, 1.0
        scan = (t * 0.85) % 1.0
    else:
        power, mouth, eye_w, scan = 0.45, 0.0, 0.55, None

    def C(col, a=None, p=power):
        return _col(col, p, a)

    lw = max(2, int(s * 0.014))
    crest = cy - H * 0.95
    brow = cy - H * 0.22
    chin = cy + H * 0.92
    # Faceted helmet silhouette (pointed crest, cut cheeks, sharp chin)
    helm = [
        (cx, crest),
        (cx + H * 0.18, cy - H * 0.72),
        (cx + H * 0.52, cy - H * 0.38),
        (cx + H * 0.58, brow),
        (cx + H * 0.50, cy + H * 0.18),
        (cx + H * 0.28, cy + H * 0.62),
        (cx, chin),
        (cx - H * 0.28, cy + H * 0.62),
        (cx - H * 0.50, cy + H * 0.18),
        (cx - H * 0.58, brow),
        (cx - H * 0.52, cy - H * 0.38),
        (cx - H * 0.18, cy - H * 0.72),
    ]
    d.polygon(helm, fill=(0, 18, 32, int(150 * power)), outline=C(CYAN), width=lw)
    # Crest ridge
    d.line((cx, crest + 4, cx, brow - 2), fill=C(CYAN), width=max(2, lw - 1))
    # Cheek cuts
    d.line((cx - H * 0.58, brow, cx - H * 0.22, cy + H * 0.08), fill=C(CYAN_DIM), width=2)
    d.line((cx + H * 0.58, brow, cx + H * 0.22, cy + H * 0.08), fill=C(CYAN_DIM), width=2)
    # Brow plate
    d.polygon(
        [(cx - H * 0.50, brow), (cx + H * 0.50, brow),
         (cx + H * 0.44, brow + H * 0.28), (cx - H * 0.44, brow + H * 0.28)],
        fill=(0, 8, 16, int(200 * power)), outline=C(CYAN), width=lw,
    )
    # Slit eyes — thin, slightly inward-angled, no rounding
    eh = max(2, int(H * 0.028 * (0.7 + 0.3 * eye_w)))
    ew = H * 0.20 * eye_w
    ey = brow + H * 0.14
    gap = H * 0.07
    for sign in (-1, 1):
        inner_x = cx + sign * gap
        outer_x = cx + sign * (gap + ew)
        y_outer = ey - eh * 0.55  # outer corners higher — hawk slit
        d.polygon(
            [
                (inner_x, ey - eh),
                (outer_x, y_outer - eh),
                (outer_x, y_outer + eh),
                (inner_x, ey + eh),
            ],
            fill=C(WHITE if mood == "speak" else CYAN),
        )

    if scan is not None:
        sy = brow + 4 + H * 0.26 * scan
        d.line((cx - H * 0.42, sy, cx + H * 0.42, sy),
               fill=(220, 255, 255, int(220 * power)), width=max(2, lw - 1))

    # Sharp mouth slit
    my = cy + H * 0.38
    if mouth < 0.25:
        d.line((cx - H * 0.12, my, cx + H * 0.12, my), fill=C(CYAN_DIM), width=lw)
        d.line((cx - H * 0.12, my, cx - H * 0.16, my + H * 0.04), fill=C(CYAN_DIM), width=2)
        d.line((cx + H * 0.12, my, cx + H * 0.16, my + H * 0.04), fill=C(CYAN_DIM), width=2)
    else:
        mh = H * 0.06 * mouth
        d.polygon(
            [(cx - H * 0.14, my), (cx + H * 0.14, my),
             (cx + H * 0.10, my + mh), (cx - H * 0.10, my + mh)],
            outline=C(CYAN), width=lw, fill=C(CYAN, int(80 + 120 * mouth)),
        )

    # Chin chevron
    d.polygon(
        [(cx, chin - H * 0.06), (cx - H * 0.10, chin - H * 0.22),
         (cx + H * 0.10, chin - H * 0.22)],
        outline=C(CYAN), width=2,
    )
    return im.resize((size, size), Image.Resampling.LANCZOS)


class Face:
    def __init__(self, app):
        self.app = app
        self.cfg = app.cfg.get("face") or {}
        self._mood = "sleep"
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._root = None
        self._stop = threading.Event()
        self._layered = False

    def start(self) -> None:
        if not self.cfg.get("enabled", True):
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="jarvis-face")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        root = self._root
        if root is not None:
            try:
                root.after(0, root.destroy)
            except Exception:
                pass

    def set_mood(self, mood: str) -> None:
        with self._lock:
            self._mood = mood

    def _current_mood(self) -> str:
        speaker = getattr(self.app, "speaker", None)
        if speaker is not None and getattr(speaker, "busy", False):
            return "speak"
        with self._lock:
            return self._mood

    def _run(self) -> None:
        try:
            import tkinter as tk
        except Exception as e:
            log.error("Face UI needs tkinter: %s", e)
            return

        size = int(self.cfg.get("size", 140))
        root = tk.Tk()
        self._root = root
        root.title("Jarvis")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.wm_attributes("-toolwindow", True)
        except Exception:
            pass
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        parked = {
            "x": int(self.cfg.get("x", sw - size - 40)),
            "y": int(self.cfg.get("y", sh - size - 88)),
        }
        root.geometry(f"{size}x{size}+{parked['x']}+{parked['y']}")
        root.configure(bg="black")
        canvas = tk.Label(root, bg="black", bd=0, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        root.update_idletasks()

        hwnd = _hwnd(root)
        try:
            _enable_layered(hwnd)
            self._layered = True
        except Exception as e:
            log.warning("Layered window unavailable (%s); using colour-key", e)
            root.configure(bg=KEY_HEX)
            canvas.configure(bg=KEY_HEX)
            try:
                root.attributes("-transparentcolor", KEY_HEX)
            except Exception:
                pass

        drag = {"x": 0, "y": 0}
        t0 = time.time()
        hold = {"img": None}

        def start_drag(e):
            drag["x"], drag["y"] = e.x_root, e.y_root

        def on_drag(e):
            dx, dy = e.x_root - drag["x"], e.y_root - drag["y"]
            drag["x"], drag["y"] = e.x_root, e.y_root
            parked["x"] += dx
            parked["y"] += dy
            root.geometry(f"+{parked['x']}+{parked['y']}")

        def on_double(_e):
            if not self.app.awake:
                threading.Thread(target=self.app.wake_up, daemon=True).start()

        canvas.bind("<ButtonPress-1>", start_drag)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<Double-Button-1>", on_double)

        def frame():
            if self._stop.is_set():
                try:
                    root.destroy()
                except Exception:
                    pass
                return
            mood = self._current_mood()
            t = time.time() - t0
            rgba = render_face(size, mood, t)
            if self._layered:
                try:
                    _paint_layered(hwnd, rgba)
                except Exception as e:
                    log.error("Layered paint failed: %s", e)
                    self._layered = False
            if not self._layered:
                rgb = Image.new("RGB", (size, size), (255, 0, 255))
                rgb.paste(rgba.convert("RGB"), mask=rgba.split()[-1])
                photo = ImageTk.PhotoImage(rgb)
                hold["img"] = photo
                canvas.configure(image=photo)
            root.after(50, frame)

        frame()
        log.info("Face overlay online (custom visor, stable)")
        root.mainloop()
        self._root = None
