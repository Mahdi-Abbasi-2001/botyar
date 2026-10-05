"""Talking to Bale and Telegram when they (or the network, or our Telegram relay) misbehave.

- request(): ONE place where every Bot API call goes through. It retries only what is safe to retry (connection failures before
  anything was sent, 429 with the server's own wait time, 502/503/504) and classifies the outcome:
    TransientError  - could not reach the messenger (safe to try again later, nothing was delivered)
    UncertainError  - the request may or may not have been processed (read timeout): NEVER auto-retried, so no duplicate messages
    BaleError       - the messenger answered "no" (blocked bot, unknown chat, bad token): retrying would not help
- health: per-messenger status that the panel shows («بله الان در دسترس نیست»)."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import httpx

log = logging.getLogger("botyar.resilience")
ATTEMPTS = 3
BACKOFF = (0.5, 1.5)   # seconds before attempt 2 and 3
MAX_RETRY_AFTER = 5    # never block a request thread longer than this for a 429
DOWN_AFTER = 3         # consecutive failures before a messenger is shown as down


class BaleError(Exception):
    pass


class TransientError(BaleError):
    """Unreachable / overloaded: nothing was delivered and trying again later is safe."""


class UncertainError(BaleError):
    """Timed out while waiting: the messenger may have processed it. Do not retry automatically."""


# ---------- health ----------
_lock = threading.Lock()
_state: dict[str, dict] = {}


def _entry(name: str) -> dict:
    return _state.setdefault(name, {"ok": 0, "last_ok": None, "last_fail": None, "failures": 0, "error": ""})


def record(name: str, ok: bool, error: str = ""):
    now = datetime.now(timezone.utc)
    with _lock:
        e = _entry(name)
        if ok:
            e["last_ok"], e["failures"], e["error"] = now, 0, ""
        else:
            e["last_fail"], e["failures"], e["error"] = now, e["failures"] + 1, error[:160]


def health(name: str) -> dict:
    with _lock:
        e = dict(_entry(name))
    status = "down" if e["failures"] >= DOWN_AFTER else ("degraded" if e["failures"] > 0 else ("ok" if e["last_ok"] else "unknown"))
    return {"messenger": name, "status": status, "failures": e["failures"], "error": e["error"],
            "last_ok": e["last_ok"].isoformat() if e["last_ok"] else None, "last_fail": e["last_fail"].isoformat() if e["last_fail"] else None}


def reset():
    with _lock:
        _state.clear()


# ---------- the request wrapper ----------
def _retry_after(r: httpx.Response, body: dict) -> float:
    try:
        return float((body.get("parameters") or {}).get("retry_after") or r.headers.get("retry-after") or 1)
    except (TypeError, ValueError):
        return 1.0


def request(name: str, send, sleep=time.sleep):
    """`send()` performs one HTTP request and returns the httpx response. Returns the Bot API `result`."""
    last: Exception | None = None
    waited = False  # a 429 already told us how long to wait: do not add the generic backoff on top
    for attempt in range(1, ATTEMPTS + 1):
        if attempt > 1 and not waited:
            sleep(BACKOFF[min(attempt - 2, len(BACKOFF) - 1)])
        waited = False
        try:
            r = send()
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as e:
            last = TransientError(f"cannot connect ({type(e).__name__})")
            continue
        except httpx.TimeoutException as e:  # read/write timeout: the request may have gone through
            record(name, False, f"timeout ({type(e).__name__})")
            raise UncertainError(f"timed out ({type(e).__name__})")
        except httpx.HTTPError as e:
            record(name, False, f"network error ({type(e).__name__})")
            raise UncertainError(f"network error ({type(e).__name__})")
        try:
            body = r.json()
        except Exception:  # noqa: BLE001
            body = {}
        if r.status_code == 429:
            last = TransientError("rate limited (429)")
            if attempt < ATTEMPTS:
                sleep(min(_retry_after(r, body), MAX_RETRY_AFTER))
                waited = True
            continue
        if r.status_code in (502, 503, 504):
            last = TransientError(f"messenger unavailable (HTTP {r.status_code})")
            continue
        if body.get("ok"):
            record(name, True)
            return body.get("result")
        record(name, True)  # the messenger answered: it is up, even though it said no
        raise BaleError(body.get("description") or f"HTTP {r.status_code}")
    record(name, False, str(last))
    raise last or TransientError("unreachable")
