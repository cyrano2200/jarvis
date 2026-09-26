"""Optional smart-home control via Home Assistant REST API and MQTT."""
from __future__ import annotations

import requests

from . import tool

SERVICE = {"on": "turn_on", "off": "turn_off", "toggle": "toggle", "open": "open_cover",
           "close": "close_cover", "lock": "lock", "unlock": "unlock"}


def _entity(ctx, name: str) -> str:
    ents = {k.lower(): v for k, v in (ctx.cfg.get("home_assistant.entities") or {}).items()}
    return ents.get(name.lower().strip(), name.strip())


def _headers(ctx):
    return {"Authorization": f"Bearer {ctx.cfg.get('home_assistant.token')}",
            "Content-Type": "application/json"}


def _enabled(ctx) -> bool:
    ha = ctx.cfg.get("home_assistant")
    return bool(ha.get("enabled") and ha.get("token"))


@tool("home_control", "Control a smart-home device through Home Assistant (needs setup).",
      {"device": "friendly name from config or entity_id", "action": "on | off | toggle | open | close | lock | unlock | set",
       "value": "brightness percent (light) or temperature (climate), for 'set'"})
def home_control(ctx, device: str, action: str, value: float | None = None):
    if not _enabled(ctx):
        return "Home automation isn't configured. Enable home_assistant in config.yaml."
    eid = _entity(ctx, device)
    domain = eid.split(".")[0]
    base = ctx.cfg.get("home_assistant.url").rstrip("/")
    payload: dict = {"entity_id": eid}
    action = action.lower()
    if action == "set":
        if domain == "light":
            service, payload["brightness_pct"] = "turn_on", int(value or 100)
            domain = "light"
        elif domain == "climate":
            service, payload["temperature"] = "set_temperature", float(value or 21)
        else:
            return f"I don't know how to 'set' a {domain}."
    elif action in SERVICE:
        service = SERVICE[action]
        if domain not in ("cover",) and service.endswith("_cover"):
            service = "turn_on" if action == "open" else "turn_off"
    else:
        return f"Unsupported action '{action}'."
    r = requests.post(f"{base}/api/services/{domain}/{service}", json=payload,
                      headers=_headers(ctx), timeout=10)
    return f"Done, {ctx.name}. {device} {action}." if r.ok else f"Home Assistant said {r.status_code}: {r.text[:100]}"


@tool("home_state", "Read the state of a smart-home device.", {"device": "friendly name or entity_id"})
def home_state(ctx, device: str):
    if not _enabled(ctx):
        return "Home automation isn't configured."
    eid = _entity(ctx, device)
    base = ctx.cfg.get("home_assistant.url").rstrip("/")
    r = requests.get(f"{base}/api/states/{eid}", headers=_headers(ctx), timeout=10)
    if not r.ok:
        return f"I couldn't read {device} ({r.status_code})."
    j = r.json()
    return f"{device} is {j['state']}."


@tool("mqtt_publish", "Publish an MQTT message to a configured topic alias.",
      {"topic": "alias from config mqtt.topics (or a raw topic)", "payload": "message payload"})
def mqtt_publish(ctx, topic: str, payload: str):
    m = ctx.cfg.get("mqtt")
    if not m.get("enabled"):
        return "MQTT isn't enabled in config.yaml."
    try:
        import paho.mqtt.publish as publish
    except ImportError:
        return "Install paho-mqtt to use MQTT (pip install paho-mqtt)."
    t = {k.lower(): v for k, v in (m.get("topics") or {}).items()}.get(topic.lower(), topic)
    auth = {"username": m["username"], "password": m["password"]} if m.get("username") else None
    publish.single(t, payload, hostname=m["host"], port=int(m["port"]), auth=auth)
    return f"Message sent to {topic}, {ctx.name}."
