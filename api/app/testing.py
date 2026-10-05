"""Test scenarios (LLM-written, strict-schema friendly) and a deterministic runner.
The runner executes scenarios against the real engine with an in-memory store; no LLM involved."""
from __future__ import annotations

from pydantic import BaseModel

from . import dates, engine
from .spec import BotSpec


class TestStep(BaseModel):
    say: str                       # what the user sends (text or a button's data value)
    reply_contains: list[str]      # substrings that must appear in the bot's replies to this step
    reply_not_contains: list[str]  # substrings that must NOT appear


class SetupRun(BaseModel):
    """Another user who runs these steps `times` times before the main scenario (e.g. fill all seats)."""
    times: int
    steps: list[str]               # raw user messages only


class KV(BaseModel):
    key: str
    value: str


class RecordCheck(BaseModel):
    collection: str                # block id the record is stored under
    count: int                     # how many records matching `where` must exist
    where: list[KV]                # record field == value (compared as strings)


class TestScenario(BaseModel):
    name: str
    setup: list[SetupRun]
    steps: list[TestStep]
    records: list[RecordCheck]


class TestPlan(BaseModel):
    scenarios: list[TestScenario]


def _texts(actions):
    """Everything a user would see: message text plus button labels."""
    parts = []
    for a in actions:
        if a["type"] == "media":
            parts.append("📎 " + ("عکس" if a["kind"] == "image" else "فایل"))
            continue
        if a["type"] == "location":
            parts.append(f"📍 {a['latitude']}, {a['longitude']}")
            continue
        parts.append(a["text"])
        parts.extend(b["text"] for b in a.get("buttons", []))
    return "\n".join(parts)


def _fresh_store(spec: BotSpec, catalog: list[dict] | None) -> engine.MemoryStore:
    store = engine.MemoryStore()
    for b in spec.blocks:
        if b.type == "catalog_order" and b.source == "table":
            store.load_catalog(b.id, [dict(p) for p in (catalog or [])])  # copy: stock is decremented per scenario
    return store


def run_scenario(spec: BotSpec, sc: TestScenario, catalog: list[dict] | None = None) -> dict:
    store = _fresh_store(spec, catalog)
    rng = engine.Cycle()  # random messages show variants in order, so tests are deterministic
    failures: list[str] = []
    transcript: list[dict] = []
    try:
        for s in sc.setup:
            for n in range(max(0, min(s.times, 60))):
                sess = engine.new_session()
                sess["cust"] = f"t:setup{n}"
                sess["pay_ok"] = sess["pay_sim"] = True
                for msg in s.steps:
                    engine.handle(spec, sess, msg, store, dates.TEST_NOW, rng=rng)
        sess = engine.new_session()
        sess["cust"] = "t:main"
        sess["pay_ok"] = sess["pay_sim"] = True
        for i, st in enumerate(sc.steps, 1):
            actions = engine.handle(spec, sess, st.say, store, dates.TEST_NOW, rng=rng)
            text = _texts(actions)
            transcript.append({"user": st.say, "bot": text})
            for needle in st.reply_contains:
                if needle not in text:
                    failures.append(f"مرحله {i}: انتظار می‌رفت پاسخ شامل «{needle}» باشد")
            for needle in st.reply_not_contains:
                if needle in text:
                    failures.append(f"مرحله {i}: پاسخ نباید شامل «{needle}» می‌بود")
        for rc in sc.records:
            n = sum(all(str(r.get(kv.key)) == kv.value for kv in rc.where) for r in store.rows.get(rc.collection, []))
            if n != rc.count:
                where = ", ".join(f"{kv.key}={kv.value}" for kv in rc.where)
                failures.append(f"ثبت‌ها: در «{rc.collection}» با شرط ({where}) تعداد {rc.count} انتظار می‌رفت ولی {n} بود")
    except Exception as e:  # engine crash is a failed test, not a server error
        failures.append(f"خطای اجرا: {type(e).__name__}: {e}")
    return {"name": sc.name, "passed": not failures, "failures": failures, "transcript": transcript}


def run_plan(spec: BotSpec, scenarios: list[TestScenario], catalog: list[dict] | None = None) -> list[dict]:
    return [run_scenario(spec, sc, catalog) for sc in scenarios]


def spec_diff(old: dict | None, new: dict) -> list[dict]:
    """Flat list of changes between two spec dicts (blocks matched by id)."""
    out: list[dict] = []

    def walk(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(set(a) | set(b)):
                walk(a.get(k), b.get(k), f"{path}.{k}" if path else k)
        elif isinstance(a, list) and isinstance(b, list) and a and isinstance(a[0], dict) and "id" in a[0]:
            am, bm = {x["id"]: x for x in a}, {x["id"]: x for x in b}
            for k in list(bm) + [k for k in am if k not in bm]:
                walk(am.get(k), bm.get(k), f"{path}[{k}]")
        elif a != b:
            out.append({"path": path, "before": a, "after": b})

    if old is None:
        return [{"path": "(جدید)", "before": None, "after": new.get("name")}]
    od = dict(old); nd = dict(new)
    od["blocks"] = [dict(b) for b in od.get("blocks", [])]
    nd["blocks"] = [dict(b) for b in nd.get("blocks", [])]
    # blocks list handled via id matching
    walk({"blocks": od.pop("blocks"), **od}, {"blocks": nd.pop("blocks"), **nd}, "")
    return out
