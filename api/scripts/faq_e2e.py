"""End-to-end FAQ accuracy through the REAL pipeline (agent-side indexing with LLM variants + real embeddings + engine policy).

    cd api && set -a && . ./.env && set +a && PYTHONPATH=. .venv/bin/python -m scripts.faq_e2e
"""
import os
import tempfile
import time

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/faq.db"

from app import faq_index  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.engine import MemoryStore, handle, new_session  # noqa: E402
from app.models import Bot, User  # noqa: E402
from app.spec import BotSpec  # noqa: E402
from scripts.faq_eval_data import SETS  # noqa: E402

Base.metadata.create_all(engine)
tot = dict(right=0, wrong=0, sug_ok=0, sug_miss=0, nf=0, n=0, neg_ans=0, neg_sug=0, neg_clean=0, neg_n=0)
latencies = []
with SessionLocal() as db:
    u = User(email="e2e@example.com", password_hash="x")
    db.add(u)
    db.flush()
    for name, S in SETS.items():
        bot = Bot(user_id=u.id, name=name)
        db.add(bot)
        db.flush()
        entries = [{"question": q, "answer": a} for q, a, _ in S["entries"]]
        spec = BotSpec.model_validate({"name": name, "welcome": "سلام", "menu": [{"label": "سؤال", "block": "faq"}],
                                       "blocks": [{"type": "faq", "id": "faq", "title": "پرسش‌ها", "entries": entries}]})
        t0 = time.time()
        stats = faq_index.ensure(db, bot.id, spec)
        print(f"[{name}] indexed {stats} in {time.time() - t0:.1f}s", flush=True)
        matcher = faq_index.EmbeddingMatcher(db, bot.id)

        def ask(text):
            s = new_session()
            s["cust"] = f"e2e:{time.time_ns()}"
            handle(spec, s, "/start", MemoryStore(), matcher=matcher)
            handle(spec, s, "m:0", MemoryStore(), matcher=matcher)
            t = time.time()
            out = handle(spec, s, text, MemoryStore(), matcher=matcher)
            latencies.append(time.time() - t)
            return out

        for i, (q, a, paras) in enumerate(S["entries"]):
            for p in paras:
                out = ask(p)
                tot["n"] += 1
                first = out[0]
                if first["text"] == a:
                    tot["right"] += 1
                elif any(first["text"] == x[1] for x in [(None, ans) for _, ans, _ in S["entries"]]):
                    tot["wrong"] += 1
                elif first["text"].startswith("منظورتان"):
                    datas = [b["data"] for b in first["buttons"]]
                    tot["sug_ok" if f"fq:{i}" in datas else "sug_miss"] += 1
                else:
                    tot["nf"] += 1
        for n in S["negatives"]:
            out = ask(n)
            tot["neg_n"] += 1
            first = out[0]
            if any(first["text"] == ans for _, ans, _ in S["entries"]):
                tot["neg_ans"] += 1
            elif first["text"].startswith("منظورتان"):
                tot["neg_sug"] += 1
            else:
                tot["neg_clean"] += 1
n, m = tot["n"], tot["neg_n"]
print(f"\nVALID ({n}): answered right {tot['right']/n:.1%} | answered WRONG {tot['wrong']/n:.1%} | suggested incl. the right one {tot['sug_ok']/n:.1%} | suggested without it {tot['sug_miss']/n:.1%} | not found {tot['nf']/n:.1%}")
print(f"OFF-TOPIC ({m}): answered (bad) {tot['neg_ans']/m:.1%} | suggestions shown {tot['neg_sug']/m:.1%} | clean not-found {tot['neg_clean']/m:.1%}")
latencies.sort()
print(f"question latency: median {latencies[len(latencies)//2]*1000:.0f} ms, p90 {latencies[int(len(latencies)*.9)]*1000:.0f} ms")
from sqlalchemy import func, select  # noqa: E402
from app.models import LlmCall  # noqa: E402
with SessionLocal() as db:
    for step, c, cost in db.execute(select(LlmCall.step, func.count(), func.sum(LlmCall.cost_usd)).group_by(LlmCall.step)):
        print(f"  cost {step:14} calls={c:4} ${cost:.5f}")
