from sqlalchemy import select
from sqlalchemy.orm import Session

from . import engine
from .models import QuizQuestionRow, Product, Record, TimeOff


class SqlStore:
    """engine.Store backed by the records table, scoped to one bot and one mode (sandbox/live)."""

    def __init__(self, db: Session, bot_id: int, sandbox: bool):
        self.db, self.bot_id, self.sandbox = db, bot_id, sandbox
        self.member_fn = None  # set by the channel (live chats only): (channel, cust) -> True / False / None

    def quiz_questions(self, block_id):
        q = select(QuizQuestionRow).where(QuizQuestionRow.bot_id == self.bot_id, QuizQuestionRow.block_id == block_id).order_by(QuizQuestionRow.position, QuizQuestionRow.id)
        return [{"question": r.question, "options": r.options, "correct": r.correct} for r in self.db.scalars(q)]

    def member(self, channel, cust, session):
        """Live chats ask the messenger; the simulator cannot join a channel, so the customer counts as a member after pressing «عضو شدم»."""
        if self.sandbox or self.member_fn is None:
            return bool((session.get("data") or {}).get("_pressed"))
        return self.member_fn(channel, cust)

    def _rows(self, collection):
        q = select(Record).where(Record.bot_id == self.bot_id, Record.collection == collection, Record.sandbox == self.sandbox)
        return self.db.scalars(q).all()

    def add(self, collection, data):
        r = Record(bot_id=self.bot_id, collection=collection, data=data, sandbox=self.sandbox)
        self.db.add(r)
        self.db.flush()
        return {"id": r.id, **data}

    def count(self, collection, **where):
        return sum(all(r.data.get(k) == v for k, v in where.items()) for r in self._rows(collection))

    def time_off(self, block_id):
        """Hours the owner closed (the same for the simulator and live customers)."""
        q = select(TimeOff).where(TimeOff.bot_id == self.bot_id, TimeOff.block_id == block_id)
        return [{"date": t.date, "start": t.start, "end": t.end, "staff": t.staff} for t in self.db.scalars(q)]

    # ---- product table (catalog_order with source="table") ----
    def _products(self, block_id):
        q = select(Product).where(Product.bot_id == self.bot_id, Product.block_id == block_id).order_by(Product.position, Product.id)
        return [self._dict(p) for p in self.db.scalars(q)]

    @staticmethod
    def _dict(p: Product) -> dict:
        return {"id": p.id, "name": p.name, "category": p.category, "price": p.price, "stock": p.stock,
                "options": p.options or [], "description": p.description, "photo": bool(p.has_photo)}

    def categories(self, block_id):
        return engine.catalog_categories(self._products(block_id))

    def products(self, block_id, category, query, offset, limit):
        rows = engine.catalog_filter(self._products(block_id), category, query)
        return rows[offset:offset + limit], len(rows)

    def product(self, block_id, pid):
        p = self.db.get(Product, pid)
        return self._dict(p) if p and p.bot_id == self.bot_id and p.block_id == block_id else None

    def reserve(self, block_id, lines):
        """All-or-nothing stock check. The sandbox checks but never decrements, so testing can't deplete live stock."""
        need = engine.total_per_product(lines)  # the same product on two cart lines must be checked as one quantity
        rows = {p.id: p for p in self.db.scalars(select(Product).where(Product.bot_id == self.bot_id, Product.block_id == block_id,
                                                                       Product.id.in_(list(need))))}
        failed = [pid for pid, qty in need.items() if pid not in rows or (rows[pid].stock is not None and rows[pid].stock < qty)]
        if not failed and not self.sandbox:
            for pid, qty in need.items():
                if rows[pid].stock is not None:
                    rows[pid].stock -= qty
            self.db.flush()
        return failed

    # ---- cancellation support ----
    def find(self, collection, **where):
        rows = [{"id": r.id, **r.data} for r in self._rows(collection)]
        return [r for r in rows if all(r.get(k) == v for k, v in where.items())]

    def update(self, collection, row_id, **fields):
        r = self.db.get(Record, row_id)
        if r and r.bot_id == self.bot_id and r.collection == collection and r.sandbox == self.sandbox:
            r.data = {**r.data, **fields}  # a NEW dict, so SQLAlchemy sees the change
            self.db.flush()

    def release(self, block_id, lines):
        """Give cancelled stock back. The sandbox never touched live stock, so it never gives any back either."""
        if self.sandbox:
            return
        need = engine.total_per_product(lines)
        for p in self.db.scalars(select(Product).where(Product.bot_id == self.bot_id, Product.block_id == block_id, Product.id.in_(list(need)))):
            if p.stock is not None:
                p.stock += need[p.id]
        self.db.flush()
