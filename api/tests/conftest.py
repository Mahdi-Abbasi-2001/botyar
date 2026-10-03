import pytest


@pytest.fixture(autouse=True)
def _relax_signup_limit(monkeypatch):
    """Tests register many users from one fake IP; only the dedicated limiter test uses a low limit."""
    from app import main
    from app.config import settings

    main._reg_hits.clear()
    monkeypatch.setattr(settings, "register_per_ip_hour", 10_000)
