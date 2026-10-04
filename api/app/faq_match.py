"""FAQ matching: the decision policy plus a dependency-free lexical matcher (used by tests and as the degraded mode when
embeddings are unavailable). Thresholds for the EMBEDDING matcher come from scripts/eval_faq.py + scripts/faq_policy.py
(text-embedding-3-small with LLM-written variants, 90 valid + 36 off-topic Persian questions) and scripts/faq_robust.py, which repeats
the evaluation over 4 independent random draws of the variants: answer at >= 0.60 with a 0.09 margin over the runner-up, suggest the top 3
from 0.45. Measured over those draws: ~60% of valid questions answered at once, ~0.3% (worst draw 1.1%) answered wrongly, ~26% more get the
right question as a button; ~1.4% (worst 2.8%) of off-topic questions are answered. Small sample: treat as indicative, not guaranteed."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from .engine_text import fa_norm


@dataclass(frozen=True)
class Thresholds:
    answer: float
    margin: float
    suggest: float


EMBEDDING = Thresholds(answer=0.60, margin=0.09, suggest=0.45)
LEXICAL = Thresholds(answer=0.70, margin=0.10, suggest=0.40)


class MatcherUnavailable(Exception):
    """The matcher could not run (provider down / timeout); the engine falls back to the lexical matcher."""


class RateLimited(Exception):
    pass


class Matcher(Protocol):
    thresholds: Thresholds

    def rank(self, block_id: str, entries: list, query: str, cust: str | None) -> list[tuple[int, float]]:
        """All entry indexes with a score, best first."""


_STOP = {"و", "را", "به", "از", "در", "که", "با", "برای", "این", "آن", "یا", "هم", "می", "است", "هست", "رو", "چه", "چی", "آیا", "من", "شما", "ما", "یه", "یک", "تا", "بود", "کنید", "کنم", "دارید", "دارین", "داره"}
_TOKEN = re.compile(r"\w+", re.UNICODE)  # \w covers Persian letters and excludes punctuation such as ؟ ،


def tokens(text: str) -> set[str]:
    t = {w for w in _TOKEN.findall(fa_norm(text)) if w not in _STOP and len(w) > 1}
    return {re.sub(r"(ها|های|ی|ه)$", "", w) or w for w in t}  # crude Persian plural / ezafe stripping


class LexicalMatcher:
    """Dice coefficient over content words. Deterministic, free, no network."""
    thresholds = LEXICAL

    def rank(self, block_id, entries, query, cust=None):
        q = tokens(query)
        out = []
        for i, e in enumerate(entries):
            d = tokens(e.question)
            out.append((i, 2 * len(q & d) / (len(q) + len(d)) if q and d else 0.0))
        return sorted(out, key=lambda x: -x[1])


def decide(ranked: list[tuple[int, float]], th: Thresholds) -> tuple[str, list[int]]:
    """('answer', [i]) | ('suggest', [i, j, k]) | ('none', [])."""
    if not ranked:
        return "none", []
    top, second = ranked[0][1], (ranked[1][1] if len(ranked) > 1 else 0.0)
    if top >= th.answer and top - second >= th.margin:
        return "answer", [ranked[0][0]]
    if top >= th.suggest:
        return "suggest", [i for i, s in ranked[:3] if s >= th.suggest * 0.9]
    return "none", []
