"""FAQ search index + the production matcher.

Build time (`ensure`, called when a version is saved or published): for every FAQ entry the LLM writes informal phrasings of the
question, and the question plus its phrasings are embedded and stored. Question time (`EmbeddingMatcher.rank`): ONE embedding call for
the customer's text, cosine similarity against the stored vectors, entry score = best of its phrasings. Nothing is ever generated for
the customer: the bot returns the owner's own answer text. See scripts/eval_faq.py for the measured accuracy."""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import llm
from .faq_match import EMBEDDING, MatcherUnavailable, RateLimited
from .models import FaqIndex, LlmCall
from .spec import BotSpec

log = logging.getLogger("botyar.faq")
EMBED_MODEL = "text-embedding-3-small"  # $0.02 per 1M tokens (developers.openai.com/api/docs/pricing, checked 2026-10-04)
EMBED_PRICE = 0.02 / 1e6
VARIANTS_PER_ENTRY = 8
QUERY_MAX_CHARS = 300
RATE_LIMIT, RATE_WINDOW = 30, 3600  # FAQ searches per customer per hour (each costs a fraction of a cent)


def entry_hash(e) -> str:
    alts = getattr(e, "alternates", None)  # only when set, so entries indexed before alternates existed keep their hash
    return hashlib.sha1((f"{e.question}\n{e.answer}" + (f"\n" + "\n".join(alts) if alts else "")).encode()).hexdigest()


def _embed(texts: list[str], timeout: float = 6.0) -> tuple[np.ndarray, int]:
    r = llm.client().with_options(timeout=timeout, max_retries=1).embeddings.create(model=EMBED_MODEL, input=texts)
    v = np.array([d.embedding for d in r.data], dtype=np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    return v, int(r.usage.total_tokens)


def _log(db: Session, bot_id: int, step: str, tokens: int, seconds: float):
    db.add(LlmCall(bot_id=bot_id, run_id=0, step=step, model=EMBED_MODEL, input_tokens=tokens, cached_tokens=0, output_tokens=0,
                   cost_usd=tokens * EMBED_PRICE, seconds=seconds))
    db.commit()


# ---------- build time ----------
class EntryVariants(BaseModel):
    index: int
    variants: list[str]


class VariantBatch(BaseModel):
    items: list[EntryVariants]


VARIANT_PROMPT = ("You help a Persian-speaking small business. For EACH FAQ entry (index, question, answer) write 8 DIFFERENT ways real customers would ask the "
                  "same thing in informal chat Persian: short, colloquial, different words and word orders, some in spoken forms (e.g. «چنده», «میشه», «داره»). "
                  "Do not answer, do not repeat the original wording, and do not ask about anything the answer does not cover. Return every index.")


def _variants(db: Session, bot_id: int, run_id: int, batch: list[tuple[int, object]]) -> dict[int, list[str]]:
    import json

    payload = json.dumps([{"index": i, "question": e.question, "answer": e.answer} for i, e in batch], ensure_ascii=False)
    try:
        out = llm.call(db, bot_id=bot_id, run_id=run_id, step="faq_variants", instructions=VARIANT_PROMPT, input=payload, schema=VariantBatch, effort="none", max_out=6000)
        return {it.index: [v.strip() for v in it.variants if v.strip()][:VARIANTS_PER_ENTRY] for it in out.items}
    except Exception:  # noqa: BLE001 - the question itself is still indexed; the next save/publish retries the variants
        log.exception("variant generation failed")
        return {}


def ensure(db: Session, bot_id: int, spec: BotSpec, run_id: int = 0) -> dict:
    """Bring the search index of every FAQ block in line with the spec. Cheap when nothing changed (hash comparison)."""
    stats = {"entries_indexed": 0, "entries_reused": 0}
    for b in spec.blocks:
        if b.type != "faq":
            continue
        want = {entry_hash(e): e for e in b.entries}
        have = {h for (h,) in db.execute(select(FaqIndex.entry_hash).where(FaqIndex.bot_id == bot_id, FaqIndex.block_id == b.id).distinct())}
        stale = have - set(want)
        if stale:
            db.execute(delete(FaqIndex).where(FaqIndex.bot_id == bot_id, FaqIndex.block_id == b.id, FaqIndex.entry_hash.in_(stale)))
        stats["entries_reused"] += len(have & set(want))
        todo = [(h, e) for h, e in want.items() if h not in have]
        for start in range(0, len(todo), 10):
            chunk = todo[start:start + 10]
            variants = _variants(db, bot_id, run_id, list(enumerate(e for _, e in chunk)))
            docs: list[tuple[str, str]] = []
            for pos, (h, e) in enumerate(chunk):
                seen = {e.question}
                docs.append((h, e.question))
                for v in [*getattr(e, "alternates", []), *variants.get(pos, [])]:  # the owner's own phrasings first
                    if v not in seen:
                        seen.add(v)
                        docs.append((h, v))
            t0 = time.time()
            vecs, tokens = _embed([d for _, d in docs], timeout=30)
            _log(db, bot_id, "faq_index", tokens, time.time() - t0)
            for (h, d), v in zip(docs, vecs):
                db.add(FaqIndex(bot_id=bot_id, block_id=b.id, entry_hash=h, doc=d, vector=v.astype(np.float16).tobytes()))
            stats["entries_indexed"] += len(chunk)
        db.commit()
    return stats


# ---------- question time ----------
_cache: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}
_hits: dict[str, list[float]] = {}
_lock = threading.Lock()


def _rate_check(cust: str | None):
    key, now = cust or "anon", time.time()
    with _lock:
        hits = [t for t in _hits.get(key, []) if now - t < RATE_WINDOW]
        if len(hits) >= RATE_LIMIT:
            _hits[key] = hits
            raise RateLimited()
        _hits[key] = hits + [now]


class EmbeddingMatcher:
    thresholds = EMBEDDING

    def __init__(self, db: Session, bot_id: int):
        self.db, self.bot_id = db, bot_id

    def _matrix(self, block_id: str, entries: list):
        hashes = tuple(entry_hash(e) for e in entries)
        key = (self.bot_id, block_id, hashes)
        if key in _cache:
            return _cache[key]
        by_hash: dict[str, list[FaqIndex]] = {}
        for r in self.db.scalars(select(FaqIndex).where(FaqIndex.bot_id == self.bot_id, FaqIndex.block_id == block_id)):
            by_hash.setdefault(r.entry_hash, []).append(r)
        mats, owners = [], []
        for i, h in enumerate(hashes):
            if h not in by_hash:
                raise MatcherUnavailable(f"entry {i} is not indexed yet")
            for r in by_hash[h]:
                mats.append(np.frombuffer(r.vector, dtype=np.float16).astype(np.float32))
                owners.append(i)
        value = (np.stack(mats), np.array(owners))
        if len(_cache) > 200:
            _cache.pop(next(iter(_cache)))
        _cache[key] = value
        return value

    def rank(self, block_id, entries, query, cust=None):
        _rate_check(cust)
        mat, owners = self._matrix(block_id, entries)
        t0 = time.time()
        try:
            q, tokens = _embed([query.strip()[:QUERY_MAX_CHARS]])
        except Exception as e:  # noqa: BLE001 - provider down, timeout, key problem
            log.warning("query embedding failed: %s", e)
            raise MatcherUnavailable("embedding call failed")
        try:
            _log(self.db, self.bot_id, "faq_query", tokens, time.time() - t0)
        except Exception:  # noqa: BLE001 - never fail a customer's answer because cost logging failed
            self.db.rollback()
        sims = mat @ q[0]
        scores = [(i, float(sims[owners == i].max())) for i in range(len(entries))]
        return sorted(scores, key=lambda x: -x[1])


def matcher_for(db: Session, bot_id: int, spec: BotSpec):
    return EmbeddingMatcher(db, bot_id) if any(b.type == "faq" for b in spec.blocks) else None
