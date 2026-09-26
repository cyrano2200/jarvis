"""Tool registry. Add a new capability by decorating a function with @tool(...) in any module
listed in MODULES (or add your own module to that list)."""
from __future__ import annotations

import importlib
import inspect
import logging
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger("jarvis.tools")
REGISTRY: dict[str, "Tool"] = {}
MODULES = ["system", "files", "web", "comms", "media", "shell", "timers", "notes", "smarthome", "places"]


@dataclass
class Tool:
    name: str
    description: str
    params: dict[str, str]
    fn: Callable


def tool(name: str, description: str, params: dict[str, str] | None = None):
    def deco(fn):
        REGISTRY[name] = Tool(name, description, params or {}, fn)
        return fn
    return deco


def load_all() -> None:
    for m in MODULES:
        try:
            importlib.import_module(f"{__name__}.{m}")
        except Exception as e:  # a broken optional module must not kill Jarvis
            log.error("Could not load tool module %s: %s", m, e)


def describe() -> str:
    lines = []
    for t in REGISTRY.values():
        p = ", ".join(f"{k}: {v}" for k, v in t.params.items())
        lines.append(f"- {t.name}({p}) - {t.description}")
    return "\n".join(lines)


def call(name: str, ctx, args: dict) -> str:
    t = REGISTRY.get(name)
    if not t:
        return f"Unknown tool '{name}'. Available: {', '.join(REGISTRY)}"
    accepted = set(inspect.signature(t.fn).parameters) - {"ctx"}
    clean = {k: v for k, v in (args or {}).items() if k in accepted}
    try:
        out = t.fn(ctx, **clean)
        return str(out) if out is not None else "Done."
    except TypeError as e:
        return f"Bad arguments for {name}: {e}"
    except Exception as e:
        log.exception("Tool %s crashed", name)
        return f"{name} failed: {e}"
