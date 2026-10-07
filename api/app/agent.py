"""Botyar builder agent (LangGraph): clarify -> design -> validate -> write tests -> run -> repair -> save."""
from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import logging

from . import faq_index, llm, prompts
from .llm_schema import LLMBotSpec
from .models import Bot, BotVersion, BuilderMessage, BuilderRun, LlmCall, Product, VersionFixture, VersionTests
from .spec import BotSpec
from .testing import TestPlan, TestScenario, run_plan, spec_diff

log = logging.getLogger("botyar.agent")
MAX_DESIGN, MAX_REPAIR, MAX_CLARIFY_ROUNDS = 3, 3, 2


FAILED_MSG = ("متأسفانه این بار ساخت ربات به نتیجه نرسید. همان درخواست را دوباره بفرستید یا آن را ساده‌تر بنویسید؛ "
              "اگر باز هم تکرار شد، از بخش «پشتیبانی» برای تیم بات‌یار بنویسید.")


def _block_types() -> dict[str, str]:
    from .llm_schema import LLMBotSpec
    import typing
    union = typing.get_args(LLMBotSpec.model_fields["blocks"].annotation)[0]
    return {c.__name__: c.model_fields["type"].default for c in typing.get_args(union)}


def spec_errors(e: ValidationError) -> list[str]:
    """Validation errors as feedback for the next design attempt. A block is a union of types, so one wrong field in a
    booking also reports errors for EVERY other block type (MessageBlock.text required, …): only the errors of the
    type the block actually has are kept."""
    types = _block_types()
    out = []
    for x in e.errors():
        if x["type"] == "literal_error" and x["loc"] and x["loc"][-1] == "type":
            continue
        member = next((types[n] for seg in map(str, x["loc"]) for n in types if seg == n or seg.endswith(f", {n}]")), None)
        given = x["input"].get("type") if isinstance(x.get("input"), dict) else None
        if member and given and member != given:
            continue  # an error of a block type this block is not
        out.append(f"{'.'.join(map(str, x['loc']))}: {x['msg']}")
    return out[:15] or [str(e)[:500]]


DECLINE_MARK = "🚧 "  # starts a message that declines the request, or the line of a finished build listing what was left out


RESERVED_LABELS = {x.replace(" ", "") for x in ("ثبتهای من", "سفارشهای من", "نوبتهای من", "ثبتنامهای من", "کدهای تخفیف")}

KEPT_FIELDS = ("hours", "links", "contact", "location", "media", "variants")
REMOVAL_WORDS = ("حذف", "بردار", "پاک", "نمی‌خوام", "نمی‌خواهم", "نمیخوام", "نمی‌خواهیم", "دیگر نیاز", "نیازی ندارم", "جایگزین", "عوض", "تغییر بده")


def dropped_fields(old: dict, new: dict, request: str) -> list[str]:
    """What the new spec lost from blocks that existed before (a field that was filled and is now empty), unless the owner asked for removal or replacement."""
    if any(w in request for w in REMOVAL_WORDS):
        return []
    now = {b.get("id"): b for b in new.get("blocks", [])}
    out = []
    for b in old.get("blocks", []):
        n = now.get(b.get("id"))
        if not n or n.get("type") != b.get("type"):
            continue
        for k in KEPT_FIELDS:
            if b.get(k) and not n.get(k):
                out.append(f"block «{b['id']}» lost its {k}")
    return out


class ClarifyResult(BaseModel):
    ready: bool
    questions: list[str]
    assumptions: list[str]
    summary: str
    out_of_scope: str  # "" normally; otherwise a friendly Persian explanation when the MAIN purpose is impossible with our blocks


class RepairResult(BaseModel):
    spec: LLMBotSpec
    scenarios: list[TestScenario]
    explanation: str


class S(TypedDict, total=False):
    request: str
    history: str
    current: dict | None
    assumptions: list[str]
    summary: str
    spec: dict | None
    errors: list[str]
    design_attempts: int
    old_scenarios: list[dict]
    scenarios: list[dict]
    results: list[dict]
    repair_attempts: int
    outcome: str
    decline_message: str
    questions: list[str]
    version: int
    explanation: str
    fixture: list[dict]


class Builder:
    def __init__(self, db: Session, bot_id: int, run_id: int):
        self.db, self.bot_id, self.run_id = db, bot_id, run_id

    # ---- helpers ----
    def emit(self, text: str):
        run = self.db.get(BuilderRun, self.run_id)
        run.events = [*run.events, text]
        self.db.commit()

    def ask(self, step, instructions, payload: str, schema, effort="low", max_out: int = 8000):
        return llm.call(self.db, bot_id=self.bot_id, run_id=self.run_id, step=step, instructions=instructions, input=payload, schema=schema,
                        effort=effort, max_out=max_out)

    def cost(self) -> float:
        return float(self.db.scalar(select(func.coalesce(func.sum(LlmCall.cost_usd), 0.0)).where(LlmCall.run_id == self.run_id)))

    # ---- nodes ----
    def clarify(self, s: S) -> dict:
        self.emit("در حال بررسی درخواست شما…")
        rounds = self.db.scalar(select(func.count()).select_from(BuilderMessage).where(
            BuilderMessage.bot_id == self.bot_id, BuilderMessage.role == "assistant", BuilderMessage.content.like("❓%"))) or 0
        payload = f"CONVERSATION SO FAR:\n{s['history']}\n\nLATEST OWNER MESSAGE:\n{s['request']}\n\nCURRENT SPEC:\n{json.dumps(s['current'], ensure_ascii=False) if s.get('current') else 'none (new bot)'}"
        r: ClarifyResult = self.ask("clarify", prompts.CLARIFY, payload, ClarifyResult, effort="low")
        if r.out_of_scope.strip():
            return {"outcome": "declined", "decline_message": r.out_of_scope.strip()}
        if not r.ready and not s.get("current") and rounds < MAX_CLARIFY_ROUNDS and r.questions:
            return {"outcome": "needs_input", "questions": r.questions[:3]}
        return {"outcome": "build", "assumptions": r.assumptions, "summary": r.summary}

    def design(self, s: S) -> dict:
        n = s.get("design_attempts", 0) + 1
        self.emit("در حال طراحی ساختار ربات…" if n == 1 else f"در حال اصلاح ساختار ربات (تلاش {n})…")
        payload = (f"OWNER REQUEST / CONVERSATION:\n{s['history']}\n{s['request']}\n\nASSUMPTIONS:\n{json.dumps(s.get('assumptions', []), ensure_ascii=False)}\n\n"
                   f"CURRENT SPEC:\n{json.dumps(s['current'], ensure_ascii=False) if s.get('current') else 'none'}")
        if s.get("errors"):
            payload += f"\n\nYOUR PREVIOUS ATTEMPT WAS INVALID. Fix these validation errors:\n" + "\n".join(s["errors"])
            if n == MAX_DESIGN:  # last chance: a working bot without one detail beats no bot at all
                payload += ("\nTHIS IS THE LAST ATTEMPT. If a requested detail keeps causing these errors, leave that detail out "
                            "completely and keep everything else; the owner is told about it separately.")
        try:
            # the reply is parsed into LLMBotSpec as it arrives: a reply that doesn't fit is a failed attempt like any other
            r: LLMBotSpec = self.ask("design", prompts.DESIGN, payload, LLMBotSpec, effort="low")
        except ValidationError as e:
            log.warning("design attempt %s: reply did not fit LLMBotSpec: %s", n, spec_errors(e)[:5])
            return {"spec": None, "errors": spec_errors(e), "design_attempts": n}
        except RuntimeError as e:  # cut off before it was complete: another attempt, asked to be compact
            log.warning("design attempt %s: %s", n, e)
            return {"spec": None, "errors": ["your reply was cut off before it was complete: write a more compact spec (shorter texts, no unnecessary blocks)"],
                    "design_attempts": n}
        try:
            spec = BotSpec.model_validate(r.model_dump())
            if n == 1 and s.get("current"):  # a change request must not quietly lose what a block already had
                lost = dropped_fields(s["current"], spec.model_dump(), s["request"])
                if lost:
                    raise ValueError("you removed things the owner did not ask to remove: " + "; ".join(lost) + ". Put them back exactly as they were and apply only the requested change.")
            taken = [m.label for m in spec.menu if m.label.replace("\u200c", "").replace(" ", "") in RESERVED_LABELS]
            if taken:
                raise ValueError(f"menu item «{taken[0]}» is a name the engine already gives its own built-in button: remove that menu item (customers get it automatically when allow_cancel is true)")
            has_table = any(b.type == "catalog_order" and b.source == "table" for b in spec.blocks)
            fixture: list[dict] = []
            if has_table:
                fixture = s.get("fixture") or [p.model_dump() for p in r.sample_products]  # a frozen fixture survives changes
                if len(fixture) < 3:
                    raise ValueError("sample_products: a catalog_order with source 'table' needs 6-10 realistic sample products")
            return {"spec": spec.model_dump(), "errors": [], "design_attempts": n, "fixture": fixture}
        except ValidationError as e:
            return {"spec": None, "errors": spec_errors(e), "design_attempts": n}
        except ValueError as e:  # our own fixture rule (ValidationError is handled above)
            return {"spec": None, "errors": [str(e)], "design_attempts": n}

    def after_design(self, s: S) -> str:
        if s.get("spec"):
            return "tests"
        return "design" if s.get("design_attempts", 0) < MAX_DESIGN else "fail"

    def write_tests(self, s: S) -> dict:
        self.emit("در حال نوشتن سناریوهای تست…")
        payload = f"SPEC:\n{json.dumps(s['spec'], ensure_ascii=False)}\n\nWHAT THE OWNER ASKED FOR:\n{s['summary']}"
        if s.get("fixture"):
            payload += "\n\nFIXTURE PRODUCTS (ids are 1..N in this order):\n" + json.dumps([{"id": i, **p} for i, p in enumerate(s["fixture"], 1)], ensure_ascii=False)
        if s.get("current"):
            payload += "\n\n(This is a CHANGE request: write tests only for the new/changed behaviour.)"
        try:
            plan: TestPlan = self.ask("tests", prompts.TESTS, payload, TestPlan, effort="none")
        except RuntimeError as e:  # the reply was cut off (output limit): once more, with room and a reminder to be brief
            log.warning("tests: %s; retrying", e)
            plan = self.ask("tests", prompts.TESTS, payload + "\n\nKEEP IT SHORT: at most 3 scenarios of at most 8 steps each.", TestPlan,
                            effort="none", max_out=16000)
        return {"scenarios": [x.model_dump() for x in plan.scenarios]}

    def run_tests(self, s: S) -> dict:
        all_sc = [TestScenario.model_validate(x) for x in (s.get("old_scenarios", []) + s["scenarios"])]
        self.emit(f"در حال اجرای {len(all_sc)} تست روی ربات…")
        results = run_plan(BotSpec.model_validate(s["spec"]), all_sc, s.get("fixture"))
        failed = sum(not r["passed"] for r in results)
        self.emit("همه‌ی تست‌ها موفق بودند ✅" if not failed else f"{failed} تست ناموفق بود")
        for r in results:
            if not r["passed"]:
                self.emit(f"✗ {r['name']}: {r['failures'][0]}")
        return {"results": results, "scenarios": [x.model_dump() for x in all_sc], "old_scenarios": []}

    def after_tests(self, s: S) -> str:
        if all(r["passed"] for r in s["results"]):
            return "save"
        return "repair" if s.get("repair_attempts", 0) < MAX_REPAIR else "save"

    def repair(self, s: S) -> dict:
        n = s.get("repair_attempts", 0) + 1
        self.emit(f"در حال رفع خطاهای تست (دور {n})…")
        failing = [r for r in s["results"] if not r["passed"]]
        payload = (f"OWNER REQUEST SUMMARY: {s['summary']}\n\nCURRENT SPEC:\n{json.dumps(s['spec'], ensure_ascii=False)}\n\n"
                   f"{'FIXTURE PRODUCTS (ids 1..N, fixed): ' + json.dumps([{'id': i, **p} for i, p in enumerate(s['fixture'], 1)], ensure_ascii=False) + chr(10) + chr(10) if s.get('fixture') else ''}"
                   f"ALL SCENARIOS:\n{json.dumps(s['scenarios'], ensure_ascii=False)}\n\nFAILING RESULTS (with transcripts):\n{json.dumps(failing, ensure_ascii=False)}")
        r: RepairResult = self.ask("repair", prompts.REPAIR, payload, RepairResult, effort="low")
        try:
            spec = BotSpec.model_validate(r.spec.model_dump())
        except ValidationError:
            return {"repair_attempts": n}  # keep the old spec; loop will retry or give up
        return {"spec": spec.model_dump(), "scenarios": [x.model_dump() for x in r.scenarios], "repair_attempts": n, "explanation": r.explanation}

    def save(self, s: S) -> dict:
        last = self.db.scalars(select(BotVersion).where(BotVersion.bot_id == self.bot_id).order_by(BotVersion.version.desc())).first()
        v = (last.version if last else 0) + 1
        passed = sum(r["passed"] for r in s["results"])
        self.db.add(BotVersion(bot_id=self.bot_id, version=v, spec=s["spec"], note=s["summary"]))
        self.db.add(VersionTests(bot_id=self.bot_id, version=v, scenarios=s["scenarios"], results=s["results"]))
        fixture = s.get("fixture") or []
        if fixture:
            self.db.add(VersionFixture(bot_id=self.bot_id, version=v, catalog=fixture))
            for b in s["spec"]["blocks"]:  # first build of a table catalog: seed demo products so the bot is usable at once
                if b["type"] == "catalog_order" and b.get("source") == "table":
                    have = self.db.scalar(select(func.count()).select_from(Product).where(Product.bot_id == self.bot_id, Product.block_id == b["id"]))
                    if not have:
                        for i, p in enumerate(fixture):
                            self.db.add(Product(bot_id=self.bot_id, block_id=b["id"], name=p["name"], category=p["category"], price=p["price"], stock=p["stock"],
                                                options=[o for o in p["options"] if o["choices"]], description=p["description"], position=i, is_sample=True))
        bot = self.db.get(Bot, self.bot_id)
        bot.name = s["spec"]["name"]
        self.db.commit()
        if any(b["type"] == "faq" for b in s["spec"]["blocks"]):
            self.emit("در حال آماده‌سازی جست‌وجو در پرسش‌های متداول…")
            try:  # best effort: without an index the bot still works (word matching) and publishing retries it
                faq_index.ensure(self.db, self.bot_id, BotSpec.model_validate(s["spec"]), self.run_id)
            except Exception:  # noqa: BLE001
                self.db.rollback()
                log.exception("faq indexing failed")
        self.emit(f"نسخه‌ی {v} ذخیره شد ({passed} از {len(s['results'])} تست موفق)")
        return {"version": v, "outcome": "done"}

    def fail(self, s: S) -> dict:
        self.emit("ساخت طرح معتبر ممکن نشد")
        return {"outcome": "failed"}

    # ---- graph ----
    def graph(self):
        g = StateGraph(S)
        for name, fn in [("clarify", self.clarify), ("design", self.design), ("tests", self.write_tests), ("run", self.run_tests),
                         ("repair", self.repair), ("save", self.save), ("fail", self.fail)]:
            g.add_node(name, fn)
        g.set_entry_point("clarify")
        g.add_conditional_edges("clarify", lambda s: END if s["outcome"] in ("needs_input", "declined") else "design", {END: END, "design": "design"})
        g.add_conditional_edges("design", self.after_design, {"tests": "tests", "design": "design", "fail": "fail"})
        g.add_edge("tests", "run")
        g.add_conditional_edges("run", self.after_tests, {"save": "save", "repair": "repair"})
        g.add_edge("repair", "run")
        g.add_edge("save", END)
        g.add_edge("fail", END)
        return g.compile()


def history_text(db: Session, bot_id: int, limit=12) -> str:
    rows = db.scalars(select(BuilderMessage).where(BuilderMessage.bot_id == bot_id).order_by(BuilderMessage.id.desc()).limit(limit)).all()
    return "\n".join(f"{'OWNER' if m.role == 'user' else 'BOTYAR'}: {m.content}" for m in reversed(rows))


def run_builder(run_id: int, bot_id: int, request: str):
    """Entry point executed in a background thread; owns its own DB session."""
    from .db import SessionLocal

    db = SessionLocal()
    try:
        b = Builder(db, bot_id, run_id)
        last = db.scalars(select(BotVersion).where(BotVersion.bot_id == bot_id).order_by(BotVersion.version.desc())).first()
        old_tests = db.scalars(select(VersionTests).where(VersionTests.bot_id == bot_id).order_by(VersionTests.version.desc())).first()
        hist = history_text(db, bot_id)
        db.add(BuilderMessage(bot_id=bot_id, role="user", content=request))
        db.commit()
        old_fix = db.scalars(select(VersionFixture).where(VersionFixture.bot_id == bot_id).order_by(VersionFixture.version.desc())).first()
        init: S = {"request": request, "history": hist, "current": last.spec if last else None,
                   "old_scenarios": old_tests.scenarios if (last and old_tests) else [],
                   "fixture": old_fix.catalog if (last and old_fix) else []}
        final: S = b.graph().invoke(init, {"recursion_limit": 40})
        run = db.get(BuilderRun, run_id)
        outcome = final.get("outcome")
        if outcome == "needs_input":
            msg = "❓ برای ساخت دقیق‌تر چند سؤال دارم:\n" + "\n".join(f"{i}. {q}" for i, q in enumerate(final["questions"], 1))
            db.add(BuilderMessage(bot_id=bot_id, role="assistant", content=msg))
            run.status, run.result = "needs_input", {"message": msg, "cost_usd": b.cost()}
        elif outcome == "declined":
            msg = final["decline_message"]
            # marked like the «❓» questions, so the workspace offers to send the request to the team (support tickets)
            db.add(BuilderMessage(bot_id=bot_id, role="assistant", content=DECLINE_MARK + msg))
            run.status, run.result = "declined", {"message": msg, "cost_usd": b.cost()}
        elif outcome == "done":
            res = final["results"]
            ok = sum(r["passed"] for r in res)
            msg = f"✅ نسخه {final['version']} آماده شد. {ok} از {len(res)} تست موفق بود."
            if ok < len(res):
                msg = f"⚠️ نسخه {final['version']} ساخته شد ولی {len(res) - ok} تست هنوز ناموفق است؛ نتایج را در بخش تست‌ها ببینید."
            missing = [a for a in final.get("assumptions") or [] if "پشتیبانی نمی‌شود" in a]
            others = [a for a in final.get("assumptions") or [] if a not in missing]
            if others:
                msg += "\nفرض‌ها:" + "".join(f"\n• {a.strip().rstrip('.؛')}" for a in others)
            if missing:  # its own marked line: the workspace offers to send it to the team as a ticket
                msg += "\n" + DECLINE_MARK + "؛ ".join(a.removeprefix("پشتیبانی نمی‌شود:").strip().rstrip(".؛") for a in missing)
            db.add(BuilderMessage(bot_id=bot_id, role="assistant", content=msg))
            run.status = "done"
            run.result = {"message": msg, "version": final["version"], "diff": spec_diff(last.spec if last else None, final["spec"]),
                          "tests": res, "cost_usd": b.cost()}
        else:
            db.add(BuilderMessage(bot_id=bot_id, role="assistant", content=FAILED_MSG))
            run.status, run.result = "failed", {"message": FAILED_MSG, "cost_usd": b.cost()}
        db.commit()
    except Exception as e:  # never leave a run hanging, and never leave the owner without an answer
        log.exception("builder run %s (bot %s) failed", run_id, bot_id)
        db.rollback()
        run = db.get(BuilderRun, run_id)
        run.events = [*run.events, "ساخت ربات ناموفق بود"]  # the timeline ends in red instead of looking finished
        # the page reloads the chat from the messages, so the answer must be one of them
        db.add(BuilderMessage(bot_id=bot_id, role="assistant", content=FAILED_MSG))
        run.status, run.result = "failed", {"message": FAILED_MSG, "error": f"{type(e).__name__}: {str(e)[:2000]}"}
        db.commit()
    finally:
        db.close()
