"""Terminal / PowerShell / cmd execution with layered safety.

1. DANGEROUS patterns are refused outright (unless safety.allow_dangerous_shell is true,
   in which case they still need confirmation).
2. Known read-only commands run without asking.
3. Everything else requires an explicit yes.
"""
from __future__ import annotations

import platform
import re
import subprocess

from . import tool

OS = platform.system()

DANGEROUS = [re.compile(p, re.I) for p in (
    r"\bformat\s+[a-z]:", r"\brm\s+-[a-z]*r[a-z]*\s+(/|~|\*|\$HOME)", r"\bdel\s+.*\s/[sfq]",
    r"\brd\s+/s", r"\brmdir\s+/s", r"remove-item.*-recurse", r"\bmkfs", r"\bdd\s+if=",
    r"\bshutdown\b", r"\breg\s+(delete|add)", r"\bdiskpart", r"\bcipher\s+/w", r":\(\)\s*\{",
    r"\bchmod\s+-R\s+7?77\s+/", r"\bbcdedit", r"\bnet\s+user", r"invoke-expression|\biex\b",
    r"(curl|wget|iwr|invoke-webrequest).*\|\s*(sh|bash|iex|powershell)", r"-enc(odedcommand)?\b",
    r"\bsudo\b", r"\bchown\s+-R", r">\s*/dev/sd", r"\btakeown\b", r"\bicacls\b.*\s/grant",
)]
SAFE_PREFIX = ("dir", "ls", "pwd", "cd", "echo", "whoami", "hostname", "ipconfig", "ifconfig", "ip a",
               "ping", "date", "time /t", "ver", "systeminfo", "tasklist", "uname", "df", "free", "uptime",
               "git status", "git log", "git branch", "git diff", "python --version", "pip --version",
               "pip list", "node --version", "get-date", "get-process", "get-childitem", "netstat",
               "nslookup", "tracert", "type ", "cat ", "where ", "which ")
CHAIN = re.compile(r"[;&|`$<>]|\n")


@tool("run_command", "Run a terminal command (cmd/bash by default, or PowerShell). Non-trivial commands "
      "require user confirmation; dangerous ones are refused.",
      {"command": "the command line", "shell": "auto | powershell (optional)"})
def run_command(ctx, command: str, shell: str = "auto"):
    command = command.strip()
    if not command:
        return "No command given."
    s = ctx.cfg.get("safety")
    if any(p.search(command) for p in DANGEROUS):
        if not s.get("allow_dangerous_shell"):
            return ("That command is on my danger list, so I've declined to run it. "
                    "It can be unlocked with safety.allow_dangerous_shell in config.yaml, at your own risk.")
        if not ctx.confirm(f"That command looks dangerous: {command[:100]}. Are you absolutely certain, {ctx.name}?"):
            return "Wise. Command cancelled."
    elif not (command.lower().startswith(SAFE_PREFIX) and not CHAIN.search(command)):
        if not ctx.confirm(f"I'm about to run: {command[:120]}. Shall I proceed, {ctx.name}?"):
            return "Understood. Command not executed."
    try:
        if shell == "powershell" and OS == "Windows":
            args, use_shell = ["powershell", "-NoProfile", "-Command", command], False
        else:
            args, use_shell = command, True
        r = subprocess.run(args, shell=use_shell, capture_output=True, text=True,
                           timeout=int(s.get("shell_timeout", 30)), errors="replace")
    except subprocess.TimeoutExpired:
        return "The command timed out and was abandoned."
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    text = out or err or "(no output)"
    return f"Exit code {r.returncode}. Output: {text[:1500]}"
