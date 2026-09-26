"""LAN web app for iPhone: add to Home Screen, talk to this PC's Jarvis."""
from __future__ import annotations

import json
import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("jarvis.phone")
HERE = Path(__file__).resolve().parent
HTML = HERE / "phone_page.html"
ICON = HERE / "assets" / "phone_icon.png"
MANIFEST = {
    "name": "Jarvis",
    "short_name": "Jarvis",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#031018",
    "theme_color": "#031018",
    "icons": [{"src": "/icon.png", "sizes": "180x180", "type": "image/png"}],
}


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _ensure_icon() -> None:
    if ICON.exists():
        return
    try:
        from .face import render_face
        ICON.parent.mkdir(parents=True, exist_ok=True)
        render_face(180, "listen", 0.4).save(ICON)
    except Exception as e:
        log.warning("Could not make phone icon: %s", e)


def start(app, port: int = 8742) -> ThreadingHTTPServer | None:
    _ensure_icon()
    html = HTML.read_bytes() if HTML.exists() else b"<h1>Jarvis</h1>"
    icon = ICON.read_bytes() if ICON.exists() else b""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            log.debug(fmt, *args)

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                return self._send(200, html, "text/html; charset=utf-8")
            if u.path == "/manifest.webmanifest":
                return self._send(200, json.dumps(MANIFEST).encode(), "application/manifest+json")
            if u.path == "/icon.png":
                return self._send(200, icon, "image/png")
            if u.path == "/api/replies":
                qs = parse_qs(u.query)
                since = int((qs.get("since") or ["0"])[0] or 0)
                msgs, nxt = app.phone_replies_since(since)
                body = json.dumps({"messages": msgs, "since": nxt}).encode()
                return self._send(200, body, "application/json")
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            try:
                data = json.loads(raw.decode() or "{}")
            except json.JSONDecodeError:
                data = {}
            if u.path == "/api/command":
                text = str(data.get("text") or "").strip()
                if text:
                    app.inq.put(("phone", text))
                return self._send(200, b'{"ok":true}', "application/json")
            self._send(404, b"not found", "text/plain")

    try:
        httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    except OSError as e:
        log.error("Phone server could not bind port %s: %s", port, e)
        return None
    threading.Thread(target=httpd.serve_forever, daemon=True, name="jarvis-phone").start()
    ip = lan_ip()
    url = f"http://{ip}:{port}/"
    log.info("iPhone companion: %s  (Safari → Share → Add to Home Screen)", url)
    try:
        print(f"\n iPhone: open {url} in Safari, then Share → Add to Home Screen.\n", flush=True)
    except Exception:
        pass
    return httpd
