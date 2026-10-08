"""A build that can't produce a valid design must end with an answer in the chat (never a silent, finished-looking
timeline), and a model reply that doesn't fit the spec format is retried like any other invalid attempt."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from sqlalchemy import select  # noqa: E402

from app import agent, llm  # noqa: E402
from app.agent import ClarifyResult  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.llm_schema import LLMBotSpec  # noqa: E402
from app.models import Bot, BotVersion, BuilderMessage, BuilderRun, User  # noqa: E402


def setup_run():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        u = User(username="shop", password_hash="x")
        db.add(u)
        db.flush()
        bot = Bot(user_id=u.id, name="ربات جدید")
        db.add(bot)
        db.flush()
        run = BuilderRun(bot_id=bot.id, status="running", events=[], result={})
        db.add(run)
        db.commit()
        return bot.id, run.id


def ready(**_):
    return ClarifyResult(ready=True, questions=[], assumptions=[], summary="فروشگاه لباس", out_of_scope="", datasets=[])


def last_message(bot_id):
    with SessionLocal() as db:
        return db.scalars(select(BuilderMessage).where(BuilderMessage.bot_id == bot_id).order_by(BuilderMessage.id.desc())).first()


def test_a_reply_that_does_not_fit_the_format_is_retried_then_answered(monkeypatch):
    bot_id, run_id = setup_run()
    inputs = []

    def fake_call(db, **kw):
        if kw["step"] == "clarify":
            return ready()
        inputs.append(kw["input"])
        LLMBotSpec.model_validate({"name": "x", "blocks": [{"type": "catalog_order", "id": "o"}]})  # raises like the SDK's parse does

    monkeypatch.setattr(llm, "call", fake_call)
    agent.run_builder(run_id, bot_id, "یه ربات برای فروشگاه لباسم میخوام")

    assert len(inputs) == agent.MAX_DESIGN  # every attempt was used, not one crash on the second
    assert "YOUR PREVIOUS ATTEMPT WAS INVALID" in inputs[1]
    assert "MessageBlock.type" not in inputs[1]  # the union noise is not fed back
    with SessionLocal() as db:
        run = db.get(BuilderRun, run_id)
        assert run.status == "failed" and run.result["message"] == agent.FAILED_MSG
        assert not db.scalars(select(BotVersion).where(BotVersion.bot_id == bot_id)).first()
    assert last_message(bot_id).content == agent.FAILED_MSG and "«پشتیبانی»" in agent.FAILED_MSG


def test_an_unexpected_error_still_answers_the_owner_and_marks_the_timeline(monkeypatch):
    bot_id, run_id = setup_run()

    def fake_call(db, **kw):
        if kw["step"] == "clarify":
            return ready()
        raise ConnectionError("the model service dropped the connection")

    monkeypatch.setattr(llm, "call", fake_call)
    agent.run_builder(run_id, bot_id, "یه ربات برای فروشگاه لباسم میخوام")

    with SessionLocal() as db:
        run = db.get(BuilderRun, run_id)
        assert run.status == "failed" and run.result["message"] == agent.FAILED_MSG
        assert "ConnectionError" in run.result["error"]  # kept for us, not shown to the owner
        assert run.events[-1] == "ساخت ربات ناموفق بود"  # matches «ناموفق»: the timeline step turns red
    assert last_message(bot_id).content == agent.FAILED_MSG  # in the chat, so a page reload keeps it


def test_a_cut_off_test_plan_is_asked_again_once():
    from app.agent import Builder
    from app.testing import TestPlan
    bot_id, run_id = setup_run()
    calls = []

    def fake_call(db, **kw):
        calls.append((kw["step"], kw.get("max_out")))
        if len(calls) == 1:
            raise RuntimeError("tests: model returned no parsable output (status=incomplete)")
        return TestPlan(scenarios=[])

    import app.llm as llm_mod
    llm_mod_call = llm_mod.call
    try:
        llm_mod.call = fake_call
        with SessionLocal() as db:
            out = Builder(db, bot_id, run_id).write_tests({"spec": {"name": "x"}, "summary": "s"})
    finally:
        llm_mod.call = llm_mod_call
    assert out == {"scenarios": []} and calls == [("tests", 8000), ("tests", 16000)]
