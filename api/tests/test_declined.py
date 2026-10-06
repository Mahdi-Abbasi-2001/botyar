import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from sqlalchemy import select  # noqa: E402

from app import agent, llm  # noqa: E402
from app.agent import ClarifyResult  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Bot, BotVersion, BuilderMessage, BuilderRun, User  # noqa: E402


def test_impossible_request_is_declined_with_an_explanation_and_creates_nothing(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        u = User(username="d_x.com", password_hash="x")
        db.add(u)
        db.flush()
        bot = Bot(user_id=u.id, name="ربات جدید")
        db.add(bot)
        db.flush()
        run = BuilderRun(bot_id=bot.id, status="running", events=[], result={})
        db.add(run)
        db.commit()
        bot_id, run_id = bot.id, run.id

    explain = "تشخیص چهره از توانایی‌های بات‌یار نیست و آن را وانمود نمی‌کنم. اما می‌توانم ربات نوبت‌دهی، فرم ثبت‌نام یا سفارش بسازم."
    calls = []

    def fake_call(db, **kw):
        calls.append(kw["step"])
        return ClarifyResult(ready=False, questions=[], assumptions=[], summary="", out_of_scope=explain)

    monkeypatch.setattr(llm, "call", fake_call)
    agent.run_builder(run_id, bot_id, "یک ربات تشخیص چهره بساز")

    with SessionLocal() as db:
        run = db.get(BuilderRun, run_id)
        assert run.status == "declined" and run.result["message"] == explain
        assert not db.scalars(select(BotVersion).where(BotVersion.bot_id == bot_id)).first()  # nothing was built
        last = db.scalars(select(BuilderMessage).where(BuilderMessage.bot_id == bot_id).order_by(BuilderMessage.id.desc())).first()
        assert last.role == "assistant" and last.content == explain and not last.content.startswith("❓")  # a plain message, not question cards
    assert calls == ["clarify"]  # it stopped right after the first model call: no design/test spend
