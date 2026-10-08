"""A pressed button answers by replacing its own message; typed text and multi-message replies stay new messages."""
from app.dates import TEST_NOW
from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec

SPEC = BotSpec.model_validate({
    "name": "x", "welcome": "سلام", "menu": [{"label": "رزرو", "block": "b"}, {"label": "درباره", "block": "m"}],
    "blocks": [{"type": "booking", "id": "b", "title": "رزرو نوبت", "allow_cancel": True, "slots": [{"id": "s", "label": "شنبه", "capacity": 1}]},
               {"type": "message", "id": "m", "title": "درباره", "text": "ما یک کافه‌ایم"}]})


def chat():
    s = new_session()
    s["cust"] = "bale:1"
    return s, MemoryStore()


def run(text, s, st, clicked):
    return handle(SPEC, s, text, st, TEST_NOW, clicked=clicked)


def edits(out):
    return [bool(a.get("edit")) for a in out if a["type"] == "send"]


def test_a_pressed_button_edits_a_single_reply():
    s, st = chat()
    run("/start", s, st, False)
    out = run("m:0", s, st, True)                      # the slot list replaces the menu
    assert len([a for a in out if a["type"] == "send"]) == 1 and edits(out) == [True]


def test_typed_text_is_always_a_new_message():
    s, st = chat()
    run("/start", s, st, False)
    assert not any(edits(run("m:0", s, st, False)))


def test_a_reply_made_of_several_messages_stays_new():
    s, st = chat()
    run("/start", s, st, False)
    run("m:0", s, st, True)
    out = run("s:s", s, st, True)                      # picking the slot: question about the name, no menu yet
    run("علی", s, st, False)
    out = run("09121234567", s, st, False)             # typed: the confirmation and the menu are new messages
    assert not any(edits(out)) and len([a for a in out if a["type"] == "send"]) >= 2


def test_back_to_menu_turns_the_screen_into_the_menu_in_place():
    s, st = chat()
    run("/start", s, st, False)
    run("m:0", s, st, True)
    out = run("/menu", s, st, True)
    sends = [a for a in out if a["type"] == "send"]
    assert len(sends) == 1 and sends[0].get("edit") is True and ("رزرو", "m:0") in [(b["text"], b["data"]) for b in sends[0]["buttons"]]
    assert s["block"] is None


def test_typed_menu_word_still_sends_welcome_and_menu():
    s, st = chat()
    out = run("/start", s, st, False)
    assert len([a for a in out if a["type"] == "send"]) == 2 and not any(edits(out))


def test_a_contact_card_is_part_of_the_reply_text_the_tests_read():
    from app import testing
    assert "۰۲۱۱۲۳۴۵۶۷۸" in testing._texts([{"type": "send", "text": "نشانی", "buttons": []}, {"type": "contact", "phone": "۰۲۱۱۲۳۴۵۶۷۸", "name": "کافه"}])


def test_dropped_fields_are_found_unless_the_owner_asked():
    from app.agent import dropped_fields
    old = {"blocks": [{"id": "info", "type": "message", "hours": [{"weekday": 0}], "links": [{"label": "a", "url": "https://x.y"}], "contact": None}]}
    new = {"blocks": [{"id": "info", "type": "message", "hours": [], "links": [], "contact": {"phone": "1", "name": "k"}}]}
    assert dropped_fields(old, new, "نشانی را هم اضافه کن") == ["block «info» lost its hours", "block «info» lost its links"]
    assert dropped_fields(old, new, "ساعت کاری را حذف کن") == []


def test_dropped_fields_are_copied_back():
    from app.agent import restore_dropped
    old = {"blocks": [{"id": "info", "type": "message", "media": "image", "hours": [{"weekday": 0}]}]}
    new = {"blocks": [{"id": "info", "type": "message", "media": None, "hours": [{"weekday": 0}], "location": {"latitude": 1, "longitude": 2}}], "name": "x"}
    fixed = restore_dropped(old, new, "موقعیت روی نقشه را اضافه کن")
    assert fixed["blocks"][0]["media"] == "image" and fixed["blocks"][0]["location"] == {"latitude": 1, "longitude": 2}
    assert restore_dropped(old, new, "عکس را حذف کن") is None


def test_a_booking_or_order_with_an_empty_question_list_still_asks_the_standard_contact_questions():
    from app.spec import BookingBlock, CatalogOrderBlock
    b = BookingBlock.model_validate({"type": "booking", "id": "b", "title": "x", "slots": [{"id": "s", "label": "l", "capacity": 1}], "fields": []})
    c = CatalogOrderBlock.model_validate({"type": "catalog_order", "id": "c", "title": "x", "items": [{"id": "a", "name": "n", "price": 1000}], "fields": []})
    assert len(b.fields) >= 1 and len(c.fields) >= 1
