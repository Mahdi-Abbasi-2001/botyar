"""Message blocks with variants: random but never the same twice in a row; deterministic in the agent's tests."""
import random

from app.engine import Cycle, MemoryStore, handle, new_session
from app.spec import BotSpec
from app import testing

SPEC = BotSpec.model_validate({"name": "x", "welcome": "سلام", "menu": [{"label": "جمله انگیزشی", "block": "q"}, {"label": "درباره", "block": "a"}],
                               "blocks": [{"type": "message", "id": "q", "text": "الف", "variants": ["الف", "ب", "ج"]},
                                          {"type": "message", "id": "a", "text": "ثابت"}]})


def taps(n, rng=None):
    s, st, out = new_session(), MemoryStore(), []
    handle(SPEC, s, "/start", st, rng=rng)
    for _ in range(n):
        out.append(handle(SPEC, s, "m:0", st, rng=rng)[0]["text"])
    return out


def test_every_tap_shows_one_variant_and_never_the_same_twice_in_a_row():
    got = taps(200, random.Random(1))
    assert set(got) == {"الف", "ب", "ج"} and all(a != b for a, b in zip(got, got[1:]))


def test_real_random_source_works_without_an_injected_rng():
    assert set(taps(60)) <= {"الف", "ب", "ج"}


def test_cycle_is_deterministic_for_tests():
    assert taps(4, Cycle()) == ["الف", "ب", "ج", "الف"]


def test_a_plain_message_block_is_unchanged_and_two_customers_do_not_share_the_last_pick():
    s, st = new_session(), MemoryStore()
    handle(SPEC, s, "/start", st)
    assert handle(SPEC, s, "m:1", st)[0]["text"] == "ثابت"
    a, b = new_session(), new_session()
    r = random.Random(3)
    assert handle(SPEC, a, "m:0", st, rng=Cycle())[0]["text"] == "الف" and handle(SPEC, b, "m:0", st, rng=Cycle())[0]["text"] == "الف"


def test_agent_scenarios_see_the_variants_in_order():
    sc = testing.TestScenario(name="n", setup=[], records=[], steps=[
        testing.TestStep(say="/start", reply_contains=[], reply_not_contains=[]),
        testing.TestStep(say="m:0", reply_contains=["الف"], reply_not_contains=[]),
        testing.TestStep(say="m:0", reply_contains=["ب"], reply_not_contains=["الف"])])
    assert testing.run_scenario(SPEC, sc)["passed"]
