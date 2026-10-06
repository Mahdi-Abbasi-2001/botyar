"""FAQ block: retrieval-only answers, three-tier matching, unanswered questions, degraded mode, index and cost handling."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from app import faq_index, faq_match  # noqa: E402
from app.engine import MemoryStore, handle, new_session  # noqa: E402
from app.spec import BotSpec  # noqa: E402

ENTRIES = [
    {"question": "ساعت کاری کلینیک چیست؟", "answer": "شنبه تا چهارشنبه از ۹ صبح تا ۶ عصر."},
    {"question": "آدرس کلینیک کجاست؟", "answer": "خیابان ولیعصر، پلاک ۱۲."},
    {"question": "هزینه ویزیت چقدر است؟", "answer": "ویزیت اولیه ۲۵۰ هزار تومان است."},
    {"question": "پارکینگ دارید؟", "answer": "بله، پارکینگ اختصاصی داریم."},
]


def spec_with(entries=ENTRIES):
    return BotSpec.model_validate({
        "name": "کلینیک", "welcome": "سلام", "menu": [{"label": "سؤال دارید؟", "block": "faq"}],
        "blocks": [{"type": "faq", "id": "faq", "title": "پرسش‌های متداول", "entries": entries},
                   {"type": "admin_notify", "id": "n", "on": "faq", "text": "سؤال جدید"}]})


class Chat:
    def __init__(self, spec, store, cust="bale:1", matcher=None):
        self.spec, self.store, self.matcher, self.s = spec, store, matcher, new_session()
        self.s["cust"] = cust

    def say(self, *texts):
        out = None
        for t in texts:
            out = handle(self.spec, self.s, t, self.store, matcher=self.matcher)
        return out


def text(actions):
    return "\n".join([a["text"] for a in actions] + [b["text"] for a in actions for b in a.get("buttons", [])])


def datas(actions):
    return [b["data"] for a in actions for b in a.get("buttons", [])]


def test_a_short_faq_lists_its_questions_directly_and_a_tap_returns_the_exact_answer():
    out = Chat(spec_with(), MemoryStore()).say("/start", "m:0")
    assert datas(out) == ["fq:0", "fq:1", "fq:2", "fq:3", "/menu"]
    out = Chat(spec_with(), MemoryStore()).say("/start", "m:0", "fq:1")
    assert out[0]["text"] == ENTRIES[1]["answer"] and "fh1" in datas(out)


def test_a_long_faq_is_paged_with_in_place_navigation():
    entries = [{"question": f"سؤال شماره {i} درباره‌ی موضوع {i}", "answer": f"پاسخ {i}"} for i in range(1, 20)]
    c = Chat(spec_with(entries), MemoryStore())
    out = c.say("/start", "m:0")
    assert datas(out) == ["fl", "/menu"]
    out = c.say("fl")
    assert "صفحه 1 از 3" in text(out) and "fp:1" in datas(out) and datas(out).count("fq:0") == 1
    out = c.say("fp:1")
    assert out[0].get("edit") is True and "fq:8" in datas(out) and "fp:0" in datas(out) and "fp:2" in datas(out)
    assert c.say("fq:18")[0]["text"] == "پاسخ 19"


def test_typed_question_gets_the_owners_exact_text_not_a_generated_one():
    out = Chat(spec_with(), MemoryStore()).say("/start", "m:0", "ساعت کاری کلینیک چیست؟")
    assert out[0]["text"] == ENTRIES[0]["answer"]


def test_a_partial_match_offers_suggestions_and_choosing_none_logs_the_question():
    st = MemoryStore()
    c = Chat(spec_with(), st)
    out = c.say("/start", "m:0", "ساعت کاری؟")
    assert "منظورتان یکی از این سؤال" in text(out) and datas(out)[0] == "fq:0" and "fn" in datas(out)
    out = c.say("fn")
    assert "پیدا نکردم" in text(out) and st.rows["faq"][0]["question"] == "ساعت کاری؟" and st.rows["faq"][0]["status"] == "unanswered"
    assert any(a["type"] == "notify_admin" and "❓ سؤال بدون پاسخ" in a["text"] for a in out)


def test_unrelated_question_is_logged_once_and_the_owner_is_told_once():
    st = MemoryStore()
    c = Chat(spec_with(), st)
    out = c.say("/start", "m:0", "قیمت دلار امروز چنده")
    assert "پیدا نکردم" in text(out) and sum(a["type"] == "notify_admin" for a in out) == 1
    assert "fl" in datas(out)                                                  # a way out: browse the whole list
    out = c.say("قیمت دلار امروز چنده")                                       # the same customer repeating himself
    assert len(st.rows["faq"]) == 1 and not any(a["type"] == "notify_admin" for a in out)
    Chat(spec_with(), st, cust="bale:2").say("/start", "m:0", "قیمت دلار امروز چنده")
    assert len(st.rows["faq"]) == 2                                            # another customer's identical question is a new signal


def test_feedback_buttons():
    st = MemoryStore()
    c = Chat(spec_with(), st)
    c.say("/start", "m:0", "ساعت کاری کلینیک چیست؟")
    assert "خوشحالیم" in text(c.say("fh1")) and "faq" not in st.rows
    c.say("ساعت کاری کلینیک چیست؟")
    c.say("fh0")
    assert st.rows["faq"][0]["note"] == "پاسخ پیشنهادی کمک نکرد" and st.rows["faq"][0]["question"] == "ساعت کاری کلینیک چیست؟"


def test_forged_or_stale_buttons_are_not_logged_as_questions():
    st = MemoryStore()
    c = Chat(spec_with(), st)
    for junk in ("fq:99", "fp:9", "fh0", "fn", "fq:", "x"):
        c.say("/start", "m:0", junk)
    assert "faq" not in st.rows


def test_provider_outage_degrades_to_word_matching_instead_of_failing():
    class Down:
        thresholds = faq_match.EMBEDDING

        def rank(self, *a, **k):
            raise faq_match.MatcherUnavailable("provider down")

    out = Chat(spec_with(), MemoryStore(), matcher=Down()).say("/start", "m:0", "آدرس کلینیک کجاست؟")
    assert out[0]["text"] == ENTRIES[1]["answer"]


def test_rate_limited_customers_get_a_polite_message_and_no_record():
    class Busy:
        thresholds = faq_match.EMBEDDING

        def rank(self, *a, **k):
            raise faq_match.RateLimited()

    st = MemoryStore()
    out = Chat(spec_with(), st, matcher=Busy()).say("/start", "m:0", "ساعت کاری؟")
    assert "زیاد شده" in text(out) and "fl" in datas(out) and "faq" not in st.rows


def test_the_matcher_receives_the_customer_identity_and_a_capped_query():
    seen = {}

    class Spy:
        thresholds = faq_match.EMBEDDING

        def rank(self, block_id, entries, query, cust):
            seen.update(block=block_id, n=len(entries), query=query, cust=cust)
            return [(0, 0.1)]

    Chat(spec_with(), MemoryStore(), cust="bale:77", matcher=Spy()).say("/start", "m:0", "ک" * 900)
    assert seen["cust"] == "bale:77" and seen["block"] == "faq" and seen["n"] == 4 and len(seen["query"]) == 300


# ---------------- decision policy ----------------
@pytest.mark.parametrize("ranked,expect", [
    ([(2, 0.72), (0, 0.50)], ("answer", [2])),
    ([(2, 0.70), (0, 0.64)], ("suggest", [2, 0])),             # a 0.06 lead is too close to call: never gamble on a wrong answer
    ([(1, 0.52), (3, 0.47), (0, 0.46), (2, 0.2)], ("suggest", [1, 3, 0])),
    ([(0, 0.30), (1, 0.2)], ("none", [])),
    ([], ("none", [])),
])
def test_decision_policy(ranked, expect):
    assert faq_match.decide(ranked, faq_match.EMBEDDING) == expect


# ---------------- index + embedding matcher (no network: fake embeddings and fake variant writer) ----------------
def fake_vec(texts, dim=96):
    out = np.zeros((len(texts), dim), dtype=np.float32)
    for r, t in enumerate(texts):
        for w in faq_match.tokens(t):
            out[r, hash(w) % dim] += 1.0
    n = np.linalg.norm(out, axis=1, keepdims=True)
    n[n == 0] = 1
    return out / n


@pytest.fixture()
def indexed(monkeypatch):
    from app.db import Base, SessionLocal, engine
    from app.models import Bot, User

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    faq_index._cache.clear()
    faq_index._hits.clear()
    calls = {"embed": 0, "variants": 0}

    def fake_embed(texts, timeout=6.0):
        calls["embed"] += 1
        return fake_vec(texts), sum(len(t) for t in texts) // 4

    def fake_variants(db, bot_id, run_id, batch):
        calls["variants"] += 1
        return {i: [f"{e.question} لطفاً", f"میشه بگید {e.question}"] for i, e in batch}

    monkeypatch.setattr(faq_index, "_embed", fake_embed)
    monkeypatch.setattr(faq_index, "_variants", fake_variants)
    with SessionLocal() as db:
        u = User(username="f_x.com", password_hash="x")
        db.add(u)
        db.flush()
        bot = Bot(user_id=u.id, name="b")
        db.add(bot)
        db.commit()
        yield db, bot.id, calls


def test_ensure_indexes_reuses_unchanged_entries_and_reindexes_only_edits(indexed):
    from app.models import FaqIndex

    db, bot_id, calls = indexed
    stats = faq_index.ensure(db, bot_id, spec_with())
    assert stats == {"entries_indexed": 4, "entries_reused": 0} and db.query(FaqIndex).count() == 12   # question + 2 variants each
    before = dict(calls)
    assert faq_index.ensure(db, bot_id, spec_with())["entries_reused"] == 4 and calls == before          # nothing recomputed
    edited = [dict(ENTRIES[0], answer="تغییر کرد"), *ENTRIES[1:3]]                                         # one edited, one deleted
    stats = faq_index.ensure(db, bot_id, spec_with(edited))
    assert stats == {"entries_indexed": 1, "entries_reused": 2}
    assert db.query(FaqIndex).count() == 9                                                                # the deleted entry's rows are gone


def test_embedding_matcher_ranks_by_best_phrasing_and_the_cache_follows_edits(indexed):
    db, bot_id, calls = indexed
    spec = spec_with()
    faq_index.ensure(db, bot_id, spec)
    m = faq_index.EmbeddingMatcher(db, bot_id)
    ranked = m.rank("faq", spec.blocks[0].entries, "آدرس کلینیک کجاست", "bale:1")
    assert ranked[0][0] == 1 and ranked[0][1] > 0.9 and len(ranked) == 4
    n = calls["embed"]
    m.rank("faq", spec.blocks[0].entries, "پارکینگ", "bale:1")
    assert calls["embed"] == n + 1                                                                        # exactly ONE embedding call per question
    with pytest.raises(faq_match.MatcherUnavailable):                                                     # an unindexed entry => degrade, don't guess
        m.rank("faq", spec_with([*ENTRIES, {"question": "سؤال جدید و تازه", "answer": "ا"}]).blocks[0].entries, "x", "bale:1")


def test_per_customer_rate_limit(indexed, monkeypatch):
    db, bot_id, _ = indexed
    spec = spec_with()
    faq_index.ensure(db, bot_id, spec)
    monkeypatch.setattr(faq_index, "RATE_LIMIT", 3)
    m = faq_index.EmbeddingMatcher(db, bot_id)
    for _ in range(3):
        m.rank("faq", spec.blocks[0].entries, "ساعت", "bale:1")
    with pytest.raises(faq_match.RateLimited):
        m.rank("faq", spec.blocks[0].entries, "ساعت", "bale:1")
    m.rank("faq", spec.blocks[0].entries, "ساعت", "bale:2")                                               # someone else is unaffected


def test_embedding_provider_failure_becomes_matcher_unavailable_and_costs_are_logged(indexed, monkeypatch):
    from app.models import LlmCall

    db, bot_id, _ = indexed
    spec = spec_with()
    faq_index.ensure(db, bot_id, spec)
    m = faq_index.EmbeddingMatcher(db, bot_id)
    m.rank("faq", spec.blocks[0].entries, "ساعت کاری", "bale:1")
    steps = {r.step for r in db.query(LlmCall).filter(LlmCall.bot_id == bot_id)}
    assert {"faq_index", "faq_query"} <= steps and all(r.cost_usd >= 0 for r in db.query(LlmCall))

    def boom(*a, **k):
        raise TimeoutError("slow")

    monkeypatch.setattr(faq_index, "_embed", boom)
    with pytest.raises(faq_match.MatcherUnavailable):
        m.rank("faq", spec.blocks[0].entries, "ساعت کاری", "bale:9")
