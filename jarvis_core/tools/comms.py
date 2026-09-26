"""Outbound messages: email (SMTP or Gmail compose) and Telegram. Sending asks for confirmation."""
from __future__ import annotations

import smtplib
import webbrowser
from email.message import EmailMessage
from urllib.parse import quote

import requests

from . import tool


def _resolve_addr(ctx, to: str) -> str:
    e = ctx.cfg.get("email") or {}
    contacts = {k.lower(): v for k, v in (e.get("contacts") or {}).items()}
    return contacts.get((to or "").lower().strip(), (to or "").strip())


def _open_gmail_compose(to: str, subject: str, body: str) -> None:
    url = ("https://mail.google.com/mail/?view=cm&fs=1"
           f"&to={quote(to)}&su={quote(subject or '')}&body={quote(body or '')}")
    webbrowser.open(url)


@tool("compose_email",
      "Open a Gmail compose window filled in (works without SMTP). Use when the user wants to send mail.",
      {"to": "address or contact name", "subject": "subject line", "body": "message body"})
def compose_email(ctx, to: str = "", subject: str = "", body: str = ""):
    addr = _resolve_addr(ctx, to)
    if addr and "@" not in addr:
        return f"I don't have an address for '{to}', {ctx.name}. Add it under email.contacts in config.yaml."
    if not ctx.confirm(f"I'll open Gmail to email {to or 'a new message'} with subject '{subject or '(none)'}'. Shall I, {ctx.name}?"):
        return "Understood. No email window opened."
    _open_gmail_compose(addr, subject, body)
    return f"Gmail compose is open, {ctx.name}. Review it and press Send."


@tool("send_email", "Send an email. Uses SMTP if configured, otherwise opens Gmail compose. Asks first.",
      {"to": "address or contact name from config", "subject": "subject line", "body": "message body"})
def send_email(ctx, to: str, subject: str, body: str):
    e = ctx.cfg.get("email") or {}
    addr = _resolve_addr(ctx, to)
    if addr and "@" not in addr:
        return f"I don't have an address for '{to}', {ctx.name}. Add it under email.contacts in config.yaml."
    if not (e.get("username") and e.get("password")):
        if not ctx.confirm(f"SMTP isn't set, so I'll open Gmail to email {to} about '{subject}'. Shall I, {ctx.name}?"):
            return "Understood. The email has not been sent."
        _open_gmail_compose(addr, subject, body)
        return (f"Gmail is open with the draft, {ctx.name}. Press Send there. "
                "For fully hands-free send, add email.username in config.yaml and EMAIL_PASSWORD in .env (Gmail app password).")
    if "@" not in addr:
        return f"I don't have an address for '{to}', {ctx.name}."
    if not ctx.confirm(f"I'll email {to} with the subject '{subject}'. Shall I send it, {ctx.name}?"):
        return "Understood. The email has not been sent."
    msg = EmailMessage()
    msg["From"] = e.get("from_addr") or e["username"]
    msg["To"], msg["Subject"] = addr, subject
    msg.set_content(body)
    port = int(e.get("smtp_port", 465))
    if port == 465:
        with smtplib.SMTP_SSL(e["smtp_host"], port, timeout=20) as s:
            s.login(e["username"], e["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(e["smtp_host"], port, timeout=20) as s:
            s.starttls()
            s.login(e["username"], e["password"])
            s.send_message(msg)
    return f"Email sent to {to}, {ctx.name}."


@tool("send_telegram", "Send a Telegram message to the configured chat (asks for confirmation).",
      {"message": "text to send"})
def send_telegram(ctx, message: str):
    t = ctx.cfg.get("telegram")
    if not (t.get("bot_token") and t.get("chat_id")):
        return "Telegram isn't configured. Set telegram.chat_id in config.yaml and TELEGRAM_BOT_TOKEN in .env."
    if not ctx.confirm(f"Send this Telegram message, {ctx.name}? '{message[:80]}'"):
        return "Message not sent."
    r = requests.post(f"https://api.telegram.org/bot{t['bot_token']}/sendMessage",
                      json={"chat_id": t["chat_id"], "text": message}, timeout=15)
    return f"Message delivered, {ctx.name}." if r.ok else f"Telegram refused it: {r.text[:120]}"
