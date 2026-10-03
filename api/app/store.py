from sqlalchemy import select
from sqlalchemy.orm import Session

from . import engine
from .models import Product, Record


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

    # ---- product table (catalog_order with source="table") ----
    def _products(self, block_id):
        q = select(Product).where(Product.bot_id == self.bot_id, Product.block_id == block_id).order_by(Product.position, Product.id)
        return [self._dict(p) for p in self.db.scalars(q)]

    @staticmethod
    def _dict(p: Product) -> dict:
        return {"id": p.id, "name": p.name, "category": p.category, "price": p.price, "stock": p.stock,
                "options": p.options or [], "description": p.description}

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
