"""File tools: search, open, rename, move, delete (destructive actions require confirmation)."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time
from pathlib import Path

from . import tool

OS = platform.system()
SKIP_DIRS = {"node_modules", ".git", "__pycache__", "$recycle.bin", "appdata", "site-packages", ".cache"}
PROTECTED = [Path(p) for p in (
    "C:/Windows", "C:/Program Files", "C:/Program Files (x86)", "C:/ProgramData",
    "/bin", "/sbin", "/usr", "/etc", "/boot", "/lib", "/var", "/System", "/Library", "/dev", "/proc")]


def _protected(p: Path) -> bool:
    p = p.resolve()
    if p == Path(p.anchor) or p == Path.home():
        return True
    for bad in PROTECTED:
        try:
            p.relative_to(bad.resolve())
            return True
        except (ValueError, OSError):
            continue
    return False


def _search(ctx, query: str, limit: int = 10, budget: float = 8.0) -> list[Path]:
    words = query.lower().split()
    roots = [Path(os.path.expanduser(r)) for r in ctx.cfg.get("paths.search_roots", [])]
    hits: list[Path] = []
    deadline = time.time() + budget
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith(".")]
            for name in files + dirs:
                low = name.lower()
                if all(w in low for w in words):
                    hits.append(Path(dirpath) / name)
                    if len(hits) >= limit:
                        return hits
            if time.time() > deadline:
                return hits
    return hits


def _resolve(ctx, query: str) -> tuple[Path | None, list[Path]]:
    p = Path(os.path.expanduser(query.strip().strip('"')))
    if p.exists():
        return p.resolve(), []
    hits = _search(ctx, query, limit=5)
    ctx.last_files = hits
    return (hits[0] if len(hits) == 1 else None), hits


def _ambiguous(ctx, query, hits) -> str:
    if not hits:
        return f"I couldn't find anything matching '{query}', {ctx.name}."
    names = "; ".join(h.name for h in hits[:4])
    return f"I found several matches, {ctx.name}: {names}. Please be more specific or give the full path."


@tool("find_files", "Search configured folders for files/folders whose name contains the words.",
      {"query": "words in the file name", "limit": "max results (default 8)"})
def find_files(ctx, query: str, limit: int = 8):
    hits = _search(ctx, query, int(limit))
    ctx.last_files = hits
    if not hits:
        return f"Nothing matching '{query}' turned up, {ctx.name}."
    return f"Found {len(hits)}: " + " | ".join(str(h) for h in hits)


@tool("open_file", "Open a file or folder with its default application.",
      {"path": "full path or descriptive name"})
def open_file(ctx, path: str):
    p, hits = _resolve(ctx, path)
    if not p:
        return _ambiguous(ctx, path, hits)
    if OS == "Windows":
        os.startfile(str(p))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["open" if OS == "Darwin" else "xdg-open", str(p)])
    return f"Opening {p.name}, {ctx.name}."


@tool("list_folder", "List the contents of a folder.", {"path": "folder path, e.g. ~/Downloads"})
def list_folder(ctx, path: str = "~/Downloads"):
    p = Path(os.path.expanduser(path))
    if not p.is_dir():
        return f"'{path}' is not a folder."
    items = sorted(p.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:15]
    return f"{p} contains {len(list(p.iterdir()))} items. Most recent: " + ", ".join(i.name for i in items)


@tool("rename_file", "Rename a file or folder (same directory).",
      {"path": "full path or name", "new_name": "new file name"})
def rename_file(ctx, path: str, new_name: str):
    p, hits = _resolve(ctx, path)
    if not p:
        return _ambiguous(ctx, path, hits)
    if _protected(p):
        return "That location is protected; I won't touch it."
    target = p.with_name(Path(new_name).name)
    if target.exists():
        return f"'{target.name}' already exists, {ctx.name}. I won't overwrite it."
    p.rename(target)
    return f"Renamed {p.name} to {target.name}, {ctx.name}."


@tool("move_file", "Move a file or folder into another folder.",
      {"path": "full path or name", "destination": "destination folder path"})
def move_file(ctx, path: str, destination: str):
    p, hits = _resolve(ctx, path)
    if not p:
        return _ambiguous(ctx, path, hits)
    dest = Path(os.path.expanduser(destination))
    if _protected(p) or _protected(dest):
        return "That location is protected; I won't touch it."
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / p.name
    if target.exists() and not ctx.confirm(f"{target.name} already exists there. Overwrite it, {ctx.name}?"):
        return "Understood. Nothing moved."
    shutil.move(str(p), str(target))
    return f"Moved {p.name} to {dest}, {ctx.name}."


@tool("delete_file", "Delete a file or folder (sent to Recycle Bin/Trash when possible). "
      "Always asks the user to confirm.", {"path": "full path or name"})
def delete_file(ctx, path: str):
    p, hits = _resolve(ctx, path)
    if not p:
        return _ambiguous(ctx, path, hits)
    if _protected(p):
        return "That location is protected; I won't delete it."
    kind = "folder" if p.is_dir() else "file"
    if not ctx.confirm(f"You'd like me to delete the {kind} {p.name}, {ctx.name}. Shall I proceed?"):
        return "Very good. Nothing has been deleted."
    try:
        from send2trash import send2trash
        send2trash(str(p))
        return f"{p.name} moved to the trash, {ctx.name}. Recoverable if you change your mind."
    except ImportError:
        if not ctx.confirm("Trash support isn't installed, so this deletion would be permanent. Still proceed?"):
            return "Cancelled."
        shutil.rmtree(p) if p.is_dir() else p.unlink()
        return f"{p.name} permanently deleted, {ctx.name}."
