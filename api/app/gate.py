"""Forced channel join: a customer must be a member of the owner's channel before the bot talks to them.

Membership is asked from the messenger itself (getChatMember), which only works when the bot is an ADMIN of the channel; the owner
does that step. A positive answer is remembered for a few hours. If the check cannot be made (bot not admin, wrong channel name,
messenger error) the customer is let in and the owner is told: a setup mistake must never lock customers out."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .spec import BotSpec

log = logging.getLogger("botyar.gate")
TTL = timedelta(hours=6)
MEMBER = {"member", "administrator", "creator", "owner"}
JOIN_HOST = {"bale": "https://ble.ir/", "tg": "https://t.me/"}


def join_url(spec: BotSpec, channel_name: str) -> str:
    g = spec.gate
    if g.join_url:
        return g.join_url
    if g.channel.startswith("@"):
        return JOIN_HOST.get(channel_name, "https://ble.ir/") + g.channel[1:]
    return ""


def prompt(spec: BotSpec, channel_name: str) -> dict:
    buttons = []
    url = join_url(spec, channel_name)
    if url:
        buttons.append({"text": "عضویت در کانال", "data": "url:" + url})
    buttons.append({"text": "✅ عضو شدم", "data": "gate:check"})
    return {"type": "send", "text": spec.gate.text, "buttons": buttons}


def verify(ch, token: str, spec: BotSpec, state: dict, chat_id: str, now: datetime | None = None) -> str:
    """"ok" (member, or the check could not be made), "blocked" (not a member)."""
    now = now or datetime.now(timezone.utc)
    seen = state.get("gate_ok")
    if seen:
        try:
            if now - datetime.fromisoformat(seen) < TTL:
                return "ok"
        except ValueError:
            pass
    try:
        user_id = int(chat_id)
    except ValueError:
        return "ok"
    try:
        res = ch.call(token, "getChatMember", {"chat_id": spec.gate.channel, "user_id": user_id})
        status = (res or {}).get("status", "")
    except Exception as e:  # noqa: BLE001
        log.warning("join check failed (%s): letting the customer in", e)
        state["gate_error"] = str(e)[:120]
        return "ok"
    state.pop("gate_error", None)
    if status in MEMBER:
        state["gate_ok"] = now.isoformat()
        return "ok"
    return "blocked"


def is_member(ch, token: str, channel: str, cust: str) -> bool | None:
    """True / False for one customer in one channel; None when it cannot be checked (the caller then lets the customer through)."""
    try:
        user_id = int(str(cust).split(":", 1)[1])
    except (IndexError, ValueError):
        return None
    try:
        res = ch.call(token, "getChatMember", {"chat_id": channel, "user_id": user_id})
    except Exception as e:  # noqa: BLE001
        log.warning("content join check failed for %s (%s): letting the customer through", channel, e)
        return None
    if not isinstance(res, dict):
        return None
    return res.get("status", "") in MEMBER


def setup_status(ch, token: str, spec: BotSpec) -> dict:
    """For the owner's panel: is the bot an admin of the channel (so that membership checks work)?"""
    if spec.gate is None:
        return {"configured": False}
    try:
        me = ch.call(token, "getMe", {})
        res = ch.call(token, "getChatMember", {"chat_id": spec.gate.channel, "user_id": me["id"]})
        status = (res or {}).get("status", "")
        return {"configured": True, "channel": spec.gate.channel, "ok": status in ("administrator", "creator", "owner"), "status": status}
    except Exception as e:  # noqa: BLE001
        return {"configured": True, "channel": spec.gate.channel, "ok": False, "status": "", "error": str(e)[:160]}
