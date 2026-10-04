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
