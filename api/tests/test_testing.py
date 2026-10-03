from app.spec import BotSpec
from app.templates import load_template
from app.testing import KV, RecordCheck, SetupRun, TestScenario, TestStep, run_scenario, spec_diff


def test_runner_pass_and_fail_and_setup_capacity():
    spec = load_template("workshop")
    book = ["/start", "m:0", "s:thu1", "علی", "09121234567"]
    sc = TestScenario(
        name="ظرفیت تکمیل",
        setup=[SetupRun(times=12, steps=book)],
        steps=[TestStep(say="/start", reply_contains=[], reply_not_contains=[]),
               TestStep(say="m:0", reply_contains=["تکمیل"], reply_not_contains=[])],
        records=[RecordCheck(collection="booking", count=12, where=[KV(key="status", value="confirmed")])],
    )
    assert run_scenario(spec, sc)["passed"]
    bad = sc.model_copy(update={"records": [RecordCheck(collection="booking", count=13, where=[])]})
    r = run_scenario(spec, bad)
    assert not r["passed"] and "13" in r["failures"][0]


def test_spec_diff_detects_waitlist_toggle():
    old = load_template("workshop").model_dump()
    new = load_template("workshop").model_dump()
    new["blocks"][1]["waitlist"] = True
    d = spec_diff(old, new)
    assert any("waitlist" in x["path"] and x["after"] is True for x in d)
    assert spec_diff(old, old) == []
