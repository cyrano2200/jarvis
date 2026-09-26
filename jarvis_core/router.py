"""Fast, offline intent router. Handles common commands instantly with no LLM round-trip;
anything it doesn't recognise (or anything multi-step) goes to the LLM agent."""
from __future__ import annotations

import re
from typing import Callable, Optional

Route = tuple[str, dict]


def _clean(t: str) -> str:
    t = t.replace("’", "'").strip()
    t = re.sub(r"[.!?,]+$", "", t).strip()
    t = re.sub(r"^(please|could you|can you|would you|will you|jarvis)[, ]+", "", t, flags=re.I)
    t = re.sub(r"[, ]+(please|sir|jarvis|for me)$", "", t, flags=re.I)
    return t.strip()


R: list[tuple[re.Pattern, Callable[[re.Match], Route]]] = []


def rule(pattern: str):
    rx = re.compile(pattern, re.I)

    def deco(fn):
        R.append((rx, fn))
        return fn
    return deco


# ---- time / date
rule(r"^(?:what(?:'s| is)? (?:the )?)?(?:current )?time(?: is it)?(?: now| right now)?$|^what time is it")(
    lambda m: ("get_time", {}))
rule(r"^(?:what(?:'s| is)?(?: the)? |tell me the )?(?:today's )?(?:date|day)(?: is it| today)?$|^what day is it")(
    lambda m: ("get_date", {}))

# ---- schedule (before generic open/start rules)
rule(r"^(?:set|start|create) (?:a |an )?timer (?:for|of) (.+)$")(lambda m: ("set_timer", {"duration": m[1]}))
rule(r"^(?:set|start|create) (?:a |an )?(.+?) timer$")(lambda m: ("set_timer", {"duration": m[1]}))
rule(r"^timer (?:for )?(.+)$")(lambda m: ("set_timer", {"duration": m[1]}))
rule(r"^(?:set|create) (?:an? )?alarm (?:for|at) (.+)$")(lambda m: ("set_alarm", {"time": m[1]}))
rule(r"^wake me (?:up )?(?:at |in )(.+)$")(lambda m: ("set_alarm", {"time": m[1]}))
rule(r"^remind me ((?:in|at|tomorrow|tonight) .+?) to (.+)$")(
    lambda m: ("set_reminder", {"when": m[1], "text": m[2]}))
rule(r"^remind me (?:to )?(.+?) ((?:in|at|tomorrow|tonight) .+)$")(
    lambda m: ("set_reminder", {"text": m[1], "when": m[2]}))
rule(r"^cancel (?:all |my |the )?(timers?|alarms?|reminders?|everything)$")(
    lambda m: ("cancel_schedule", {"which": m[1]}))
rule(r"^(?:what(?:'s| are)?|list|show|any|do i have).*\b(reminders|alarms|timers|schedule)\b")(
    lambda m: ("list_schedule", {}))

# ---- volume / brightness / screen
rule(r"^(?:set )?(?:the )?volume (?:to |at )?(\d{1,3})(?: ?percent| ?%)?$")(
    lambda m: ("volume", {"action": "set", "level": int(m[1])}))
rule(r"^(?:turn up|raise|increase)(?: the)? volume$|^volume up$|^louder$")(lambda m: ("volume", {"action": "up"}))
rule(r"^(?:turn down|lower|decrease|reduce)(?: the)? volume$|^volume down$|^quieter$")(
    lambda m: ("volume", {"action": "down"}))
rule(r"^(?:mute|silence)(?: the)?(?: sound| volume| audio)?$")(lambda m: ("volume", {"action": "mute"}))
rule(r"^unmute(?: the)?(?: sound| volume| audio)?$")(lambda m: ("volume", {"action": "unmute"}))
rule(r"^what(?:'s| is)(?: the| my)? volume$")(lambda m: ("volume", {"action": "get"}))
rule(r"^(?:set )?(?:the )?brightness (?:to |at )?(\d{1,3})(?: ?percent| ?%)?$")(
    lambda m: ("brightness", {"action": "set", "level": int(m[1])}))
rule(r"^(?:brightness up|(?:turn up|raise|increase)(?: the)? brightness|brighten(?: the screen)?)$")(
    lambda m: ("brightness", {"action": "up"}))
rule(r"^(?:brightness down|(?:turn down|lower|decrease|reduce)(?: the)? brightness|dim(?: the screen)?)$")(
    lambda m: ("brightness", {"action": "down"}))
rule(r"\b(?:screenshot|screen shot|screen capture)\b")(lambda m: ("screenshot", {}))
rule(r"^lock (?:the |my )?(?:screen|computer|pc|workstation|laptop)$|^lock (?:it|up)$")(
    lambda m: ("lock_screen", {}))
rule(r"^(shut ?down|restart|reboot|sleep|hibernate)(?: the| my)?(?: computer| pc| laptop| machine| system)$")(
    lambda m: ("power", {"action": {"shutdown": "shutdown", "shut down": "shutdown", "reboot": "restart",
                                    "hibernate": "sleep"}.get(m[1].lower(), m[1].lower())}))

# ---- system info
rule(r"^(?:system (?:info|status|stats)|how(?:'s| is) (?:my|the) (?:pc|computer|system|machine)(?: doing)?)$")(
    lambda m: ("system_info", {"what": "all"}))
rule(r"^(?:what|how|check|show|tell).*\b(cpu|ram|memory|disk|storage|battery|network|internet|ip address)\b")(
    lambda m: ("system_info", {"what": m[1].lower().replace("ip address", "network")}))

# ---- media
rule(r"^(?:pause|resume|play|stop|continue)(?: the)?(?: music| song| track| media| video| playback)?$")(
    lambda m: ("media_control", {"action": "play_pause"}))
rule(r"^(?:next|skip)(?: the)?(?: track| song)?$")(lambda m: ("media_control", {"action": "next"}))
rule(r"^(?:previous|last|go back)(?: track| song)?$|^previous$")(lambda m: ("media_control", {"action": "previous"}))
rule(r"^play (.+?)(?: on (spotify|youtube))?$")(
    lambda m: ("play_music", {"query": m[1], "service": m[2] or "youtube"}))

# ---- notes / memory
rule(r"^(?:take|make|add|write)(?: a)? note(?: that|:)? (.+)$|^note (?:that )?(.+)$")(
    lambda m: ("add_note", {"text": m[1] or m[2]}))
rule(r"^(?:read|show|what are)(?: me)?(?: my)? notes$")(lambda m: ("list_notes", {}))
rule(r"^remember (?:that )?(.+)$")(lambda m: ("remember", {"fact": m[1]}))

# ---- weather / search / maps / mail
rule(r"\bweather\b(?:.*?\b(?:in|for|at)\s+([a-z .'-]+?))?(?: today| tomorrow| right now| now)?$")(
    lambda m: ("weather", {"city": m[1] or ""}))
rule(r"^(?:search(?: the web)?(?: for)?|google|look up|web search(?: for)?) (.+)$")(
    lambda m: ("web_search", {"query": m[1]}))
rule(r"^(?:where(?:'s| is)|find(?: the)? address (?:of |for )?|show(?: me)? (?:on )?(?:the )?map(?:s)?(?: for)?|directions? to) (.+)$")(
    lambda m: ("lookup_address", {"query": m[1], "open_map": True}))
rule(r"^(?:open (?:google )?maps|show (?:google )?maps)(?: for (.+))?$")(
    lambda m: ("open_maps", {"query": m[1] or ""}))
rule(r"^(?:where can i (?:get|buy|eat|find)|recommend) (.+)$")(
    lambda m: ("find_places", {"query": m[1]}))
rule(r"^(?:find|show)(?: me)? (?:nearby |a |some )?(restaurants?|cafes?|food|.+?)(?: near(?: me)?| nearby| around here)$")(
    lambda m: ("find_places", {"query": m[1]}))
rule(r"^(?:nearby|near me) (.+)$")(lambda m: ("find_places", {"query": m[1]}))
rule(r"^(?:send (?:an? )?email|email|compose (?:an? )?email)(?: to ([^\s]+))?(?: (?:about|saying|that|:)\s*(.+))?$")(
    lambda m: ("compose_email", {"to": m[1] or "", "subject": (m[2] or "")[:80], "body": m[2] or ""}))

# ---- open / close (last: broadest)
rule(r"^(?:open|launch|start|run) (.+)$")(lambda m: ("open", {"target": m[1]}))
rule(r"^(?:close|quit|exit|kill|terminate|shut ?down) (.+)$")(lambda m: ("close_app", {"name": m[1]}))
rule(r"^(?:list|what|which|show).*\bapps?\b")(lambda m: ("list_apps", {}))


def route(text: str) -> Optional[Route]:
    t = _clean(text)
    if not t:
        return None
    for rx, fn in R:
        m = rx.search(t)
        if m:
            return fn(m)
    return None
