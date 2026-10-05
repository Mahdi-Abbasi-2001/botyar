import pytest


@pytest.fixture(autouse=True)
def _relax_signup_limit(monkeypatch):
    """Tests register many users from one fake IP; only the dedicated limiter test uses a low limit."""
    from app import main
    from app.config import settings

    main._reg_hits.clear()
    monkeypatch.setattr(settings, "register_per_ip_hour", 10_000)


@pytest.fixture(autouse=True)
def _no_background_scheduler(monkeypatch):
    """The reminder thread is a production-only background job; tests call outreach.due_reminders directly."""
    from app import outreach

    monkeypatch.setattr(outreach, "start_scheduler", lambda: None)


from app import billing as _billing  # noqa: E402

REAL_FREE = dict(_billing.PLANS["free"])  # the real free-plan limits (only tests/test_billing.py exercises them)


@pytest.fixture(autouse=True)
def _generous_free_plan(monkeypatch):
    """Most tests create many bots and customers under one account; they must not trip the free plan's limits."""
    monkeypatch.setitem(_billing.PLANS, "free", {**REAL_FREE, "bots": 10_000, "live_bots": 10_000, "customers": 100_000, "ai_requests": 100_000})


@pytest.fixture(autouse=True)
def _clean_process_state():
    """Module-level caches (update-id dedupe, notice dates, rate limits) must not leak from one test into the next."""
    from app import anon, bale, communities

    for d in (bale._seen, bale._cap_notice, bale._gate_notice, anon._hits, communities._admin_cache):
        d.clear()
    yield
