"""Deterministic checks that a designed spec still contains what the owner actually said. A model sometimes drops a given time or phone number,
changes «۴۵ دقیقه» into 30, turns «شنبه تا چهارشنبه» into four days, or leaves «اینجا وارد کنید» in a customer-facing text. These slips are cheap to
catch in code, and the agent gets the list back as validation errors for another attempt."""
from __future__ import annotations

import json
import re

from .engine_text import norm

WEEKDAYS = {"شنبه": 0, "یکشنبه": 1, "دوشنبه": 2, "سه‌شنبه": 3, "سه شنبه": 3, "چهارشنبه": 4, "چهار شنبه": 4, "پنجشنبه": 5, "پنج‌شنبه": 5, "پنج شنبه": 5, "جمعه": 6}
_DAY = "|".join(sorted((re.escape(k) for k in WEEKDAYS), key=len, reverse=True))
RANGE = re.compile(rf"({_DAY})\s*تا\s*({_DAY})")
PLACEHOLDER = re.compile(r"اینجا\s*(را\s*)?(وارد|بنویس|درج)|می‌توانید[^.\n]*(به‌روزرسانی|ویرایش|تغییر)|در\s+پنل|پیش\s+از\s+انتشار|جایگزین\s+کنید|تکمیل\s+می‌شود|ارائه\s+نشده|هنوز\s+(ثبت|وارد)\s+نشده")


def owner_text(history: str, request: str) -> str:
    """Only what the OWNER wrote (the conversation history marks speakers; the assistant's questions are not facts)."""
    chunks, mine = [], False
    for line in (history or "").splitlines():
        if line.startswith("OWNER:"):
            mine = True
            line = line[len("OWNER:"):]
        elif line.startswith("BOTYAR:"):
            mine = False
        if mine:
            chunks.append(line)
    chunks.append(request or "")
    return "\n".join(chunks)


def _squash(s: str) -> str:
    return re.sub(r"[\s\-‌‍]", "", norm(s)).lower()


def _weekdays(spec: dict) -> set[int]:
    out: set[int] = set()
    for b in spec.get("blocks", []):
        if b.get("type") != "booking":
            continue
        sch = b.get("schedule") or {}
        out |= {d["weekday"] for d in sch.get("days", [])}
        for h in sch.get("staff_hours", []):
            out |= {d["weekday"] for d in h.get("days", [])}
        out |= {s["weekday"] for s in b.get("slots", []) if s.get("weekday") is not None}
    return out


def problems(spec: dict, owner: str, assumptions: str = "") -> list[str]:
    """What is wrong with `spec` compared with what the owner said (empty list = nothing found)."""
    out: list[str] = []
    said = norm(owner)
    blob = norm(json.dumps(spec, ensure_ascii=False))
    flat = _squash(json.dumps(spec, ensure_ascii=False))

    # explicit clock times, dates, phone numbers, card numbers, @handles and links must appear somewhere in the bot
    for h, m in re.findall(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)", said):
        if f"{int(h):02d}:{m}" not in blob and f"{int(h)}:{m}" not in blob:
            out.append(f"the owner gave the time {int(h):02d}:{m} but it is nowhere in the bot (a slot/appointment `time`, hours, or a text)")
    for y, mo, d in re.findall(r"(?<!\d)(\d{4})/(\d{1,2})/(\d{1,2})(?!\d)", said):
        if f"{y}/{int(mo):02d}/{int(d):02d}" not in blob and f"{y}/{int(mo)}/{int(d)}" not in blob:
            out.append(f"the owner gave the date {y}/{mo}/{d} but it is nowhere in the bot")
    for ph in re.findall(r"(?<!\d)(0\d{2,3}[\s-]?\d{3}[\s-]?\d{4}|09\d{2}[\s-]?\d{3}[\s-]?\d{4})(?!\d)", said):
        if _squash(ph) not in flat:
            out.append(f"the owner gave the phone number {ph} but it is nowhere in the bot (use a message `contact` or its text)")
    for card in re.findall(r"(?<!\d)(\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})(?!\d)", said):
        if _squash(card) not in flat:
            out.append("the owner gave a 16-digit card number but it is not in the bot (`card_number`)")
    for h in set(re.findall(r"@[A-Za-z0-9_]{4,32}", said)):
        if h.lower() not in blob.lower():
            out.append(f"the owner gave {h} but it is nowhere in the bot")
    for url in set(re.findall(r"https?://[^\s،؛)»\"']+|(?<![\w/])(?:[a-z0-9-]+\.)+(?:com|ir|org|net|me|ly|app)/[A-Za-z0-9_./-]+", said, re.I)):
        core = re.sub(r"^https?://", "", url).rstrip("./").lower()
        if core not in blob.lower():
            out.append(f"the owner gave the link {url} but it is nowhere in the bot (a `links` button)")

    # appointment lengths said in minutes
    minutes = {int(x) for x in re.findall(r"(\d+)\s*دقیقه", said)}
    if minutes:
        for b in spec.get("blocks", []):
            sch = b.get("schedule") if b.get("type") == "booking" else None
            if not sch:
                continue
            lengths = [s["duration_minutes"] for s in sch.get("services", [])] or [sch["duration_minutes"]]
            for n in lengths:
                if n not in minutes:
                    out.append(f"the owner said appointments last {sorted(minutes)} minutes but the bot uses {n} (`duration_minutes`)")

    # «شنبه تا چهارشنبه» must cover every day in between
    have = _weekdays(spec)
    if have:
        for text in (said, norm(assumptions)):
            for a, b in RANGE.findall(text):
                lo, hi = sorted((WEEKDAYS[a], WEEKDAYS[b]))
                missing = [d for d in range(lo, hi + 1) if d not in have]
                if missing:
                    out.append(f"«{a} تا {b}» was said but weekday(s) {missing} are missing from the schedule (0=شنبه … 6=جمعه)")
                    break

    # a free-delivery threshold needs a delivery fee that can be free
    for b in spec.get("blocks", []):
        if b.get("type") == "catalog_order" and b.get("free_delivery_over", 0) > 0 and not b.get("delivery_fee") and not b.get("delivery_zones"):
            out.append("free_delivery_over is set but delivery_fee is 0: give delivery_fee an example amount (say in the assumptions that it is an example) or drop the threshold")

    # «please type the hours here» must never reach a customer
    visible = [spec.get("welcome", "")] + [b.get("text", "") for b in spec.get("blocks", []) if b.get("type") == "message"]
    if any(PLACEHOLDER.search(t or "") for t in visible):
        out.append("a customer-facing message contains an instruction like «اینجا وارد کنید»: leave that message/entry out and say in the assumptions which fact is missing")

    # a personality quiz cannot use the question bank, so `pick` must fit the questions written in the spec
    for b in spec.get("blocks", []):
        if b.get("type") == "quiz" and b.get("personality") and b.get("pick", 0) > len(b.get("questions", [])):
            out.append(f"personality quiz «{b.get('id')}»: pick={b['pick']} but only {len(b['questions'])} questions are written; write at least `pick` questions (the question bank is for right/wrong quizzes only)")
    return out
