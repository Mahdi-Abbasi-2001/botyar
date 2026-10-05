"""Webhooks can disappear (the messenger resets them after errors, a token is rotated, an outage clears them). Re-registering is
idempotent, so every few minutes we simply set them again: the shared bots and, in small rounds, the owners' own bots."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import bale, telegram
from .config import settings
from .models import Publication, TgPublication

log = logging.getLogger("botyar.webhooks")
OWN_PER_ROUND = 20
_cursor = {"bale": 0, "tg": 0}


def refresh(db: Session) -> dict:
    """Returns how many webhooks were (re)registered and how many calls failed."""
    ok = failed = 0
    if not settings.public_base_url:
        return {"ok": 0, "failed": 0}
    jobs = []
    if settings.bale_shared_bot_token:
        jobs.append(("bale", settings.bale_shared_bot_token, "setWebhook", {"url": f"{settings.public_base_url.rstrip('/')}/api/hook/shared/{bale.shared_hook_secret()}"}, bale.api_call))
    if settings.telegram_shared_bot_token and telegram.enabled():
        jobs.append(("tg", settings.telegram_shared_bot_token, "setWebhook", {"url": telegram.hook_url(f"shared/{telegram.shared_hook_secret()}"), "allowed_updates": telegram.ALLOWED_UPDATES}, telegram.api_call))
    for name, model, make in (
        ("bale", Publication, lambda p: {"url": f"{settings.public_base_url.rstrip('/')}/api/hook/own/{p.id}/{p.hook_secret}"}),
        ("tg", TgPublication, lambda p: {"url": telegram.hook_url(f"own/{p.id}/{p.hook_secret}"), "allowed_updates": telegram.ALLOWED_UPDATES}),
    ):
        if name == "tg" and not telegram.enabled():
            continue
        own = db.scalars(select(model).where(model.mode == "own").order_by(model.id)).all()
        if not own:
            continue
        start = _cursor[name] % len(own)
        batch = (own[start:] + own[:start])[:OWN_PER_ROUND]
        _cursor[name] = start + len(batch)
        call = bale.api_call if name == "bale" else telegram.api_call
        for p in batch:
            try:
                jobs.append((name, bale.decrypt(p.token_enc), "setWebhook", make(p), call))
            except Exception:  # noqa: BLE001
                failed += 1
    for name, token, method, payload, call in jobs:
        try:
            call(token, method, payload)
            ok += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            log.warning("webhook refresh failed on %s: %s", name, e)
    return {"ok": ok, "failed": failed}
