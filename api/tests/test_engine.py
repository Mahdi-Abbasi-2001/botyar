from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec
from app.templates import load_template


def say(spec, session, store, *texts):
    out = []
    for t in texts:
        out = handle(spec, session, t, store)
    return out


def texts(actions):
    return " | ".join(a["text"] for a in actions)


def book(spec, store, name, phone, slot="s:thu1"):
    s = new_session()
    return s, say(spec, s, store, "/start", "m:0", slot, name, phone)


def test_start_shows_menu():
    spec = load_template("workshop")
    out = handle(spec, new_session(), "/start", MemoryStore())
    assert spec.welcome in texts(out)
    assert len(out[-1]["buttons"]) == 2


def test_booking_confirms_and_notifies_admin():
    spec, store = load_template("workshop"), MemoryStore()
    _, out = book(spec, store, "علی", "۰۹۱۲۳۴۵۶۷۸۹")
    assert spec.block("booking").confirm_text in texts(out)
    assert any(a["type"] == "notify_admin" for a in out)
    assert store.rows["booking"][0]["phone"] == "09123456789"
    assert store.rows["booking"][0]["status"] == "confirmed"


def test_invalid_phone_rejected():
    spec, store = load_template("workshop"), MemoryStore()
    s = new_session()
    out = say(spec, s, store, "/start", "m:0", "s:thu1", "علی", "123")
    assert "معتبر نیست" in texts(out)
    assert "booking" not in store.rows


def test_full_slot_blocked_without_waitlist():
    spec, store = load_template("workshop"), MemoryStore()
    for i in range(12):
        book(spec, store, f"u{i}", f"0912000{i:04d}")
    s = new_session()
    out = say(spec, s, store, "/start", "m:0", "s:thu1")
    assert store.count("booking", slot="thu1", status="confirmed") == 12
    assert spec.block("booking").full_text in texts(out)
    assert s["data"].get("slot") is None  # user was not advanced into the form


def test_waitlist_after_change():
    data = load_template("workshop").model_dump()
    data["blocks"][1]["waitlist"] = True
    spec, store = BotSpec.model_validate(data), MemoryStore()
    for i in range(12):
        book(spec, store, f"u{i}", f"0912000{i:04d}")
    _, out = book(spec, store, "late", "09120009999")
    assert "لیست انتظار" in texts(out)
    assert store.count("booking", slot="thu1", status="waitlisted") == 1
    assert store.count("booking", slot="thu1", status="confirmed") == 12


def test_second_slot_still_open_when_first_full():
    spec, store = load_template("workshop"), MemoryStore()
    for i in range(12):
        book(spec, store, f"u{i}", f"0912000{i:04d}")
    _, out = book(spec, store, "x", "09121110000", slot="s:thu2")
    assert spec.block("booking").confirm_text in texts(out)


def test_cafe_order_with_option_and_min_total():
    spec, store = load_template("cafe"), MemoryStore()
    s = new_session()
    say(spec, s, store, "/start", "m:0", "i:espresso")
    out = say(spec, s, store, "checkout")  # 70,000 < min 100,000
    assert "حداقل" in texts(out)
    say(spec, s, store, "more", "i:latte", "بادام")
    say(spec, s, store, "checkout", "مریم", "09351234567")
    row = store.rows["order"][0]
    assert row["total"] == 165000
    assert row["items"][1]["options"] == {"شیر": "بادام"}


def test_cancel_returns_to_menu():
    spec, store = load_template("workshop"), MemoryStore()
    s = new_session()
    out = say(spec, s, store, "/start", "m:0", "انصراف")
    assert s["block"] is None and "انصراف" in texts(out)


def test_spec_rejects_dangling_menu_ref():
    data = load_template("cafe").model_dump()
    data["menu"][0]["block"] = "nope"
    try:
        BotSpec.model_validate(data)
        assert False
    except ValueError as e:
        assert "unknown block" in str(e)
