from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Record


class SqlStore:
    """engine.Store backed by the records table, scoped to one bot and one mode (sandbox/live)."""

    def __init__(self, db: Session, bot_id: int, sandbox: bool):
        self.db, self.bot_id, self.sandbox = db, bot_id, sandbox

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
