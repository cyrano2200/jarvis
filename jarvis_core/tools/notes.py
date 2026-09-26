"""Notes, saving research to files, and long-term facts."""
from __future__ import annotations

import re
import time
from pathlib import Path

from . import tool


@tool("add_note", "Save a note (appended to today's notes file).", {"text": "note content"})
def add_note(ctx, text: str):
    d = ctx.cfg.path_for("paths.notes_dir")
    f = d / f"notes-{time.strftime('%Y-%m-%d')}.md"
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(f"- **{time.strftime('%H:%M')}** {text.strip()}\n")
    return f"Noted, {ctx.name}. Saved in {f.name}."


@tool("list_notes", "Read back recent notes.", {"days": "how many recent note files (default 2)"})
def list_notes(ctx, days: int = 2):
    d = ctx.cfg.path_for("paths.notes_dir")
    files = sorted(d.glob("notes-*.md"), reverse=True)[: int(days)]
    if not files:
        return f"You have no notes yet, {ctx.name}."
    return " ".join(f"[{f.stem[6:]}] " + f.read_text(encoding="utf-8").replace("**", "") for f in files)[:2500]


@tool("write_file", "Save text (e.g. research, summaries) to a new file in the Jarvis workspace folder.",
      {"filename": "file name like 'ai-report.md'", "content": "full text to save"})
def write_file(ctx, filename: str, content: str):
    d = ctx.cfg.path_for("paths.workspace_dir")
    name = re.sub(r"[^\w.\- ]", "_", Path(filename).name) or "jarvis-output.md"
    if "." not in name:
        name += ".md"
    target = d / name
    n = 1
    while target.exists():  # never overwrite
        target = d / f"{Path(name).stem}-{n}{Path(name).suffix}"
        n += 1
    target.write_text(content, encoding="utf-8")
    return f"Saved to {target}, {ctx.name}."


@tool("remember", "Store a lasting fact about the user or their preferences.", {"fact": "the fact"})
def remember(ctx, fact: str):
    ctx.memory.add_fact(fact)
    return f"I'll remember that, {ctx.name}."


@tool("recall", "List everything remembered about the user.")
def recall(ctx):
    return "; ".join(ctx.memory.facts) if ctx.memory.facts else "I have no stored facts yet."


@tool("forget", "Remove remembered facts containing some text.", {"text": "text to match"})
def forget(ctx, text: str):
    n = ctx.memory.remove_fact(text)
    return f"Forgotten {n} item{'s' if n != 1 else ''}, {ctx.name}."
