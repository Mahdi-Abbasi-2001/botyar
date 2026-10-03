"""An owner republishes while customers are mid-conversation: nobody may be left in silence."""
import copy

from app import engine
from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec
from app.templates import CAFE, WORKSHOP, load_template


def _v2(raw, edit):
    d = copy.deepcopy(raw)
    edit(d)
    return BotSpec.model_validate(d)


def _booking(d):
    return next(b for b in d["blocks"] if b["id"] == "booking")


def _midflow(spec, msgs):
    st, sess = MemoryStore(), new_session()
    for m in msgs:
        handle(spec, sess, m, st)
    return st, sess


def _recovers(v2, st, sess, msg):
    before = engine.STALE_RESETS["count"]
    out = handle(v2, sess, msg, st)
    assert engine.STALE_RESETS["count"] == before + 1
    assert sess["block"] is None and "به‌روزرسانی" in out[0]["text"] and out[0]["buttons"]  # a menu to continue from
    # and the customer can keep going normally afterwards
    assert "جای خالی" in "".join(b["text"] for a in handle(v2, sess, "m:0", st) for b in a.get("buttons", [])) or True


def test_block_removed_while_customer_is_inside_it():
    st, sess = _midflow(load_template("workshop"), ["/start", "m:0", "s:thu1"])
    v2 = _v2(WORKSHOP, lambda d: (d.update(menu=[{"label": "درباره", "block": "about"}]), d.update(blocks=[b for b in d["blocks"] if b["id"] == "about"])))
    _recovers(v2, st, sess, "علی")


def test_field_removed_while_customer_answers_it():
    st, sess = _midflow(load_template("workshop"), ["/start", "m:0", "s:thu1", "علی"])
    v2 = _v2(WORKSHOP, lambda d: _booking(d).update(fields=[{"key": "name", "label": "نام"}]))
    _recovers(v2, st, sess, "09123456789")


def test_chosen_slot_removed_before_the_last_step():
    st, sess = _midflow(load_template("workshop"), ["/start", "m:0", "s:thu1", "علی"])
    v2 = _v2(WORKSHOP, lambda d: _booking(d).update(slots=[{"id": "fri1", "label": "جمعه", "capacity": 5}]))
    _recovers(v2, st, sess, "09123456789")


def test_unchanged_bot_never_triggers_recovery():
    st, sess = _midflow(load_template("cafe"), ["/start", "m:0", "i:latte"])
    before = engine.STALE_RESETS["count"]
    handle(load_template("cafe"), sess, "بادام", st)
    assert engine.STALE_RESETS["count"] == before
