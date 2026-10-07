"""Content behind a channel join: a message block with `join` is delivered only after «عضو شدم» finds the customer in every channel."""
from app.dates import TEST_NOW
from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec

SPEC = BotSpec.model_validate({
    "name": "x", "welcome": "سلام", "menu": [{"label": "دریافت فایل", "block": "gift"}, {"label": "درباره", "block": "about"}],
    "blocks": [{"type": "message", "id": "gift", "text": "این هم هدیه‌ی شما", "links": [{"label": "دانلود", "url": "https://x.y/f"}],
                "join": [{"channel": "@news_fa", "title": "اخبار"}, {"channel": "@tips_fa"}]},
               {"type": "message", "id": "about", "text": "درباره‌ی ما"}]})


class Store(MemoryStore):
    """Membership the test controls: channels the customer is in."""
    def __init__(self, inside=()):
        super().__init__()
        self.inside = set(inside)

    def member(self, channel, cust, session):
        return None if channel == "@unknown" else channel in self.inside


def run(text, s, st, clicked=False):
    return handle(SPEC, s, text, st, TEST_NOW, clicked=clicked)


def texts(out):
    return "\n".join(a.get("text", "") for a in out if a["type"] == "send")


def buttons(out):
    return [(b["text"], b["data"]) for a in out for b in a.get("buttons", [])]


def chat(prefix="bale"):
    s = new_session()
    s["cust"] = f"{prefix}:7"
    return s


def test_content_is_locked_until_every_channel_is_joined():
    s, st = chat(), Store()
    out = run("m:0", s, st)
    assert "هدیه" not in texts(out) and ("✅ عضو شدم، بررسی کن", "cj") in buttons(out)
    assert ("📢 اخبار", "url:https://ble.ir/news_fa") in buttons(out) and ("📢 @tips_fa", "url:https://ble.ir/tips_fa") in buttons(out)
    st.inside = {"@news_fa"}                               # joined only one
    out = run("cj", s, st, clicked=True)
    assert "هدیه" not in texts(out) and "@tips_fa" in texts(out) and "@news_fa" not in texts(out)
    st.inside = {"@news_fa", "@tips_fa"}
    out = run("cj", s, st, clicked=True)
    assert "این هم هدیه‌ی شما" in texts(out) and ("دانلود", "url:https://x.y/f") in buttons(out)
    assert s["block"] is None                               # back to the menu


def test_a_member_gets_the_content_at_once_and_telegram_links_use_t_me():
    s, st = chat(), Store({"@news_fa", "@tips_fa"})
    assert "این هم هدیه‌ی شما" in texts(run("m:0", s, st))
    s, st = chat("tg"), Store()
    assert ("📢 اخبار", "url:https://t.me/news_fa") in buttons(run("m:0", s, st))


def test_a_check_that_cannot_be_made_lets_the_customer_through():
    spec = BotSpec.model_validate({**SPEC.model_dump(), "blocks": [{**SPEC.model_dump()["blocks"][0], "join": [{"channel": "@unknown"}]}, SPEC.model_dump()["blocks"][1]]})
    s = chat()
    assert "هدیه" in texts(handle(spec, s, "m:0", Store(), TEST_NOW))


def test_a_deep_link_goes_straight_to_the_locked_content_and_other_blocks_stay_free():
    s, st = chat(), Store()
    out = run("go:gift", s, st)
    assert ("✅ عضو شدم، بررسی کن", "cj") in buttons(out)
    assert "درباره‌ی ما" in texts(run("m:1", chat(), Store()))


def test_the_simulator_and_agent_tests_unlock_after_pressing_check():
    s, st = chat(), MemoryStore()
    assert "هدیه" not in texts(run("m:0", s, st))
    assert "این هم هدیه‌ی شما" in texts(run("cj", s, st))
