"""Botyar builder agent (LangGraph): clarify -> design -> validate -> write tests -> run -> repair -> save."""
from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import llm, prompts
from .llm_schema import LLMBotSpec
from .models import Bot, BotVersion, BuilderMessage, BuilderRun, LlmCall, Product, VersionFixture, VersionTests
from .spec import BotSpec
from .testing import TestPlan, TestScenario, run_plan, spec_diff

MAX_DESIGN, MAX_REPAIR, MAX_CLARIFY_ROUNDS = 3, 3, 2


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

    def ask(self, step, instructions, payload: str, schema, effort="low"):
        return llm.call(self.db, bot_id=self.bot_id, run_id=self.run_id, step=step, instructions=instructions, input=payload, schema=schema, effort=effort)

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
        self.emit("در حال طراحی ساختار ربات…" if n == 1 else f"اصلاح ساختار ربات (تلاش {n})…")
        payload = (f"OWNER REQUEST / CONVERSATION:\n{s['history']}\n{s['request']}\n\nASSUMPTIONS:\n{json.dumps(s.get('assumptions', []), ensure_ascii=False)}\n\n"
                   f"CURRENT SPEC:\n{json.dumps(s['current'], ensure_ascii=False) if s.get('current') else 'none'}")
        if s.get("errors"):
            payload += f"\n\nYOUR PREVIOUS ATTEMPT WAS INVALID. Fix these validation errors:\n" + "\n".join(s["errors"])
        r: LLMBotSpec = self.ask("design", prompts.DESIGN, payload, LLMBotSpec, effort="low")
        try:
            spec = BotSpec.model_validate(r.model_dump())
            has_table = any(b.type == "catalog_order" and b.source == "table" for b in spec.blocks)
            fixture: list[dict] = []
            if has_table:
                fixture = s.get("fixture") or [p.model_dump() for p in r.sample_products]  # a frozen fixture survives changes
                if len(fixture) < 3:
                    raise ValueError("sample_products: a catalog_order with source 'table' needs 6-10 realistic sample products")
            return {"spec": spec.model_dump(), "errors": [], "design_attempts": n, "fixture": fixture}
        except ValidationError as e:
            errs = [f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()]
            return {"spec": None, "errors": errs, "design_attempts": n}
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
        plan: TestPlan = self.ask("tests", prompts.TESTS, payload, TestPlan, effort="none")
        return {"scenarios": [x.model_dump() for x in plan.scenarios]}

    def run_tests(self, s: S) -> dict:
        all_sc = [TestScenario.model_validate(x) for x in (s.get("old_scenarios", []) + s["scenarios"])]
        self.emit(f"اجرای {len(all_sc)} تست روی ربات…")
        results = run_plan(BotSpec.model_validate(s["spec"]), all_sc, s.get("fixture"))
        failed = sum(not r["passed"] for r in results)
        self.emit("همه تست‌ها موفق بود ✅" if not failed else f"{failed} تست ناموفق بود")
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
        self.emit(f"ایجنت در حال رفع خطاهای تست (دور {n})…")
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
        self.emit(f"نسخه {v} ذخیره شد ({passed}/{len(s['results'])} تست موفق)")
        return {"version": v, "outcome": "done"}

    def fail(self, s: S) -> dict:
        self.emit("طراحی معتبر ممکن نشد")
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
            db.add(BuilderMessage(bot_id=bot_id, role="assistant", content=msg))
            run.status, run.result = "declined", {"message": msg, "cost_usd": b.cost()}
        elif outcome == "done":
            res = final["results"]
            ok = sum(r["passed"] for r in res)
            msg = f"✅ نسخه {final['version']} آماده شد. {ok} از {len(res)} تست موفق بود."
            if ok < len(res):
                msg = f"⚠️ نسخه {final['version']} ساخته شد ولی {len(res) - ok} تست هنوز ناموفق است؛ نتایج را در بخش تست‌ها ببینید."
            if final.get("assumptions"):
                msg += "\nفرض‌ها: " + "؛ ".join(final["assumptions"])
            db.add(BuilderMessage(bot_id=bot_id, role="assistant", content=msg))
            run.status = "done"
            run.result = {"message": msg, "version": final["version"], "diff": spec_diff(last.spec if last else None, final["spec"]),
                          "tests": res, "cost_usd": b.cost()}
        else:
            msg = "متأسفانه نتوانستم ساختار معتبری بسازم. لطفاً درخواست را کمی ساده‌تر یا دقیق‌تر بنویسید."
            db.add(BuilderMessage(bot_id=bot_id, role="assistant", content=msg))
            run.status, run.result = "failed", {"message": msg, "cost_usd": b.cost()}
        db.commit()
    except Exception as e:  # never leave a run hanging
        db.rollback()
        run = db.get(BuilderRun, run_id)
        run.status, run.result = "failed", {"message": "خطای داخلی؛ دوباره تلاش کنید.", "error": f"{type(e).__name__}: {str(e)[:300]}"}
        db.commit()
    finally:
        db.close()
