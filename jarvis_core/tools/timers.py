"""Timers, alarms and reminders with a persistent background scheduler."""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import threading
import time
import uuid

from ..config import DATA_DIR
from . import tool

log = logging.getLogger("jarvis.timers")

WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
         "thirty": 30, "forty": 40, "forty five": 45, "fifty": 50, "sixty": 60, "half": 0.5,
         "quarter": 0.25}
UNITS = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600, "day": 86400}


def parse_duration(text: str) -> float | None:
    """'1 hour 30 minutes', 'ten minutes', 'half an hour', '90 seconds' -> seconds."""
    t = text.lower().replace("-", " ")
    if re.search(r"\bhalf an hour\b", t):
        return 1800.0
    total, found = 0.0, False
    pat = r"(\d+(?:\.\d+)?|forty five|" + "|".join(sorted(WORDS, key=len, reverse=True)) + \
          r")\s*(?:and a half\s*)?(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)\b"
    for m in re.finditer(pat, t):
        num = float(m.group(1)) if m.group(1)[0].isdigit() else WORDS[m.group(1)]
        unit = UNITS[m.group(2).rstrip("s")]
        total += num * unit
        if "and a half" in m.group(0):
            total += 0.5 * unit
        found = True
    if "half an hour" in t and not found:
        return 1800.0
    return total if found and total > 0 else None


def parse_when(text: str, now: dt.datetime | None = None) -> dt.datetime | None:
    """'in 20 minutes', 'at 7:30 pm', 'tomorrow at 9', 'tonight at 8' -> datetime."""
    now = now or dt.datetime.now()
    t = text.lower().strip()
    if re.match(r"^(in\s+)?(\d|an?\b|half|quarter|one|two|three|four|five|six|seven|eight|nine|ten|"
                r"twelve|fifteen|twenty|thirty)", t) and not re.match(r"^at\b", t):
        secs = parse_duration(t)
        if secs and (t.startswith("in") or "at" not in t.split()):
            return now + dt.timedelta(seconds=secs)
    day_offset = 1 if "tomorrow" in t else 0
    if "noon" in t:
        h, mi = 12, 0
    elif "midnight" in t:
        h, mi = 0, 0
    else:
        m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?", t)
        if not m:
            return None
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        ap = (m.group(3) or "").replace(".", "")
        if ap == "pm" and h < 12:
            h += 12
        elif ap == "am" and h == 12:
            h = 0
        elif not ap and ("tonight" in t or "evening" in t) and h < 12:
            h += 12
    if h > 23 or mi > 59:
        return None
    target = (now + dt.timedelta(days=day_offset)).replace(hour=h, minute=mi, second=0, microsecond=0)
    if target <= now and day_offset == 0:
        target += dt.timedelta(days=1)
    return target


def human_delta(secs: float) -> str:
    secs = int(round(secs))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} hour{'s' if h != 1 else ''}")
    if m:
        parts.append(f"{m} minute{'s' if m != 1 else ''}")
    if s and not h:
        parts.append(f"{s} second{'s' if s != 1 else ''}")
    return " ".join(parts) or "a moment"


class Scheduler(threading.Thread):
    """Fires timers/alarms/reminders by calling `notify(kind, text)`. Persists across restarts."""

    def __init__(self, notify):
        super().__init__(daemon=True, name="scheduler")
        self.notify = notify
        self.path = DATA_DIR / "schedule.json"
        self.items: list[dict] = []
        self._lock = threading.Lock()
        self._halt = threading.Event()
        try:
            if self.path.exists():
                self.items = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("Could not load schedule: %s", e)

    def _save(self):
        self.path.write_text(json.dumps(self.items, indent=1), encoding="utf-8")

    def add(self, kind: str, when: dt.datetime, text: str) -> dict:
        item = {"id": uuid.uuid4().hex[:6], "kind": kind, "when": when.isoformat(), "text": text}
        with self._lock:
            self.items.append(item)
            self._save()
        return item

    def list(self) -> list[dict]:
        with self._lock:
            return sorted(self.items, key=lambda i: i["when"])

    def cancel(self, which: str) -> int:
        which = which.lower()
        with self._lock:
            keep = [i for i in self.items if not (which in ("all", "everything", i["kind"], i["kind"] + "s")
                                                  or which == i["id"] or which in i["text"].lower())]
            n = len(self.items) - len(keep)
            self.items = keep
            self._save()
        return n

    def stop(self):
        self._halt.set()

    def run(self):
        while not self._halt.wait(1.0):
            now = dt.datetime.now()
            due = []
            with self._lock:
                for i in self.items:
                    if dt.datetime.fromisoformat(i["when"]) <= now:
                        due.append(i)
                if due:
                    self.items = [i for i in self.items if i not in due]
                    self._save()
            for i in due:
                late = (now - dt.datetime.fromisoformat(i["when"])).total_seconds()
                try:
                    self.notify(i["kind"], i["text"], late)
                except Exception:
                    log.exception("Notify failed")


# ------------------------------------------------------------------------------- tools
@tool("set_timer", "Start a countdown timer.",
      {"duration": "e.g. '10 minutes', '1 hour 30 minutes'", "label": "optional label"})
def set_timer(ctx, duration: str, label: str = ""):
    secs = parse_duration(str(duration))
    if not secs:
        return f"I couldn't work out that duration, {ctx.name}."
    ctx.scheduler.add("timer", dt.datetime.now() + dt.timedelta(seconds=secs), label or human_delta(secs))
    return f"Timer set for {human_delta(secs)}, {ctx.name}."


@tool("set_alarm", "Set an alarm for a clock time.",
      {"time": "e.g. '7:30 am', 'tomorrow at 6'", "label": "optional label"})
def set_alarm(ctx, time: str, label: str = ""):  # noqa: A002
    when = parse_when(str(time))
    if not when:
        return f"I couldn't understand that time, {ctx.name}."
    ctx.scheduler.add("alarm", when, label or "your alarm")
    return f"Alarm set for {when.strftime('%A at %I:%M %p').replace(' 0', ' ')}, {ctx.name}."


@tool("set_reminder", "Set a spoken reminder.",
      {"text": "what to remind about", "when": "e.g. 'in 20 minutes', 'at 5 pm', 'tomorrow at 9'"})
def set_reminder(ctx, text: str, when: str):
    w = parse_when(str(when))
    if not w:
        return f"I couldn't understand '{when}', {ctx.name}. Try 'in 20 minutes' or 'at 5 pm'."
    ctx.scheduler.add("reminder", w, text)
    return f"I'll remind you to {text} on {w.strftime('%A at %I:%M %p').replace(' 0', ' ')}, {ctx.name}."


@tool("list_schedule", "List active timers, alarms and reminders.")
def list_schedule(ctx):
    items = ctx.scheduler.list()
    if not items:
        return f"Your schedule is clear, {ctx.name}."
    now = dt.datetime.now()
    return "; ".join(f"{i['kind']} '{i['text']}' in {human_delta((dt.datetime.fromisoformat(i['when']) - now).total_seconds())}"
                     for i in items)


@tool("cancel_schedule", "Cancel timers/alarms/reminders.",
      {"which": "'all', 'timers', 'alarms', 'reminders', or words from the label"})
def cancel_schedule(ctx, which: str = "all"):
    n = ctx.scheduler.cancel(which)
    return f"Cancelled {n} item{'s' if n != 1 else ''}, {ctx.name}." if n else "Nothing matched."
