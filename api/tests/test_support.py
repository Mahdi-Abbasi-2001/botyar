"""Support tickets: owners write to the team (above all when the agent can't build what they asked for),
the team answers, and only the owner and the admins ever see a ticket."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import support  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def c(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "admin_usernames", "team")
    with TestClient(app) as client:
        yield client


def login(c, name):
    return {"Authorization": "Bearer " + c.post("/api/auth/register", json={"username": name, "password": "123456"}).json()["token"]}


def test_an_unsupported_request_becomes_a_ticket_the_team_answers(c):
    owner, team = login(c, "owner"), login(c, "team")
    bot = c.post("/api/bots", json={"template": "cafe"}, headers=owner).json()["id"]
    t = c.post("/api/tickets", json={"kind": "unsupported", "text": "یک ربات تشخیص چهره برای ورود کارکنان", "bot_id": bot,
                                     "context": "تشخیص چهره از توانایی‌های بات‌یار نیست."}, headers=owner).json()
    assert t["status"] == "open" and t["kind"] == "unsupported"
    # sent twice (double click, the builder card after a reload): still one ticket
    assert c.post("/api/tickets", json={"kind": "unsupported", "text": "یک ربات تشخیص چهره برای ورود کارکنان", "bot_id": bot}, headers=owner).json()["id"] == t["id"]

    assert c.get("/api/tickets/unread", headers=team).json()["admin_open"] == 1
    seen = c.get("/api/admin/tickets", headers=team).json()
    assert seen[0]["username"] == "owner" and seen[0]["bot_name"] and seen[0]["context"]
    assert c.post(f"/api/admin/tickets/{t['id']}", json={"reply": "در فهرست کارهای ماست؛ خبرتان می‌کنیم."}, headers=team).json()["status"] == "answered"

    assert c.get("/api/tickets/unread", headers=owner).json() == {"count": 1, "admin_open": None}
    mine = c.get("/api/tickets", headers=owner).json()
    assert mine[0]["reply"].startswith("در فهرست") and mine[0]["new_reply"] is True
    assert c.get("/api/tickets/unread", headers=owner).json()["count"] == 0  # opening «پشتیبانی» read it


def test_tickets_are_private_and_admin_routes_hidden(c):
    a, b = login(c, "a_user"), login(c, "b_user")
    other_bot = c.post("/api/bots", json={"template": "cafe"}, headers=b).json()["id"]
    assert c.post("/api/tickets", json={"kind": "problem", "text": "ربات من پاسخ نمی‌دهد", "bot_id": other_bot}, headers=a).status_code == 404
    c.post("/api/tickets", json={"kind": "question", "text": "چطور منو را عوض کنم؟"}, headers=b)
    assert c.get("/api/tickets", headers=a).json() == []
    assert c.get("/api/admin/tickets", headers=a).status_code == 404
    assert c.post("/api/admin/tickets/1", json={"reply": "x"}, headers=a).status_code == 404


def test_short_texts_and_floods_are_refused(c):
    h = login(c, "owner")
    assert c.post("/api/tickets", json={"kind": "idea", "text": "هی"}, headers=h).status_code == 422
    for i in range(support.PER_DAY):
        assert c.post("/api/tickets", json={"kind": "idea", "text": f"پیشنهاد شماره {i} برای بات‌یار"}, headers=h).status_code == 200
    r = c.post("/api/tickets", json={"kind": "idea", "text": "یک پیشنهاد دیگر برای بات‌یار"}, headers=h)
    assert r.status_code == 429 and "۲۴ ساعت" in r.json()["detail"]


def test_closing_without_a_reply_is_allowed_answering_empty_is_not(c):
    owner, team = login(c, "owner"), login(c, "team")
    t = c.post("/api/tickets", json={"kind": "question", "text": "پرداخت آنلاین در تلگرام هم هست؟"}, headers=owner).json()
    assert c.post(f"/api/admin/tickets/{t['id']}", json={"reply": " "}, headers=team).status_code == 422
    assert c.post(f"/api/admin/tickets/{t['id']}", json={"status": "closed"}, headers=team).json()["status"] == "closed"
    assert c.get("/api/tickets/unread", headers=owner).json()["count"] == 0  # closing alone is not a new reply
