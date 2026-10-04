"""Measure how well embeddings match informal Persian questions to FAQ entries (costs about 1-2 cents).

    cd api && set -a && . ./.env && set +a && PYTHONPATH=. .venv/bin/python scripts/eval_faq.py [model ...]

Strategies: q = the question only | qa = question + answer | var = question + LLM-written informal variants | var+qa.
Entry score = max cosine over the entry's documents. The test paraphrases (scripts/faq_eval_data.py) were written by hand and
are never shown to the model that writes the variants.
"""
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from openai import OpenAI
from pydantic import BaseModel

from scripts.faq_eval_data import SETS

client = OpenAI()
MODELS = sys.argv[1:] or ["text-embedding-3-small", "text-embedding-3-large"]
CACHE = os.path.join(tempfile.gettempdir(), "faq_variants.json")


class Variants(BaseModel):
    variants: list[str]


VARIANT_PROMPT = ("You help a Persian-speaking small business. Given one FAQ question and its answer, write 8 DIFFERENT ways real customers would ask the same "
                  "thing in informal chat Persian: short, colloquial, different words and word orders, some with spoken forms (e.g. «چنده», «میشه», «داره»). "
                  "Do not answer; do not repeat the original wording; do not ask about anything the answer does not cover.")


def variants_for(q, a):
    r = client.responses.parse(model="gpt-6-luna", instructions=VARIANT_PROMPT, input=f"سؤال: {q}\nپاسخ: {a}", text_format=Variants, reasoning={"effort": "none"}, max_output_tokens=800)
    return r.output_parsed.variants[:8]


def all_variants():
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    todo = [(q, a) for S in SETS.values() for q, a, _ in S["entries"] if q not in cache]
    with ThreadPoolExecutor(6) as ex:
        for (q, _), v in zip(todo, ex.map(lambda t: variants_for(*t), todo)):
            cache[q] = v
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False)
    return cache


def embed(model, texts):
    v = np.array([d.embedding for d in client.embeddings.create(model=model, input=texts).data], dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


VAR = all_variants()
if __name__ == "__main__":
    print("sample variants for", next(iter(VAR)), "->", VAR[next(iter(VAR))][:4])


def docs_for(strategy, q, a):
    if strategy == "q":
        return [q]
    if strategy == "qa":
        return [f"{q} {a}"]
    if strategy == "var":
        return [q, *VAR[q]]
    return [q, f"{q} {a}", *VAR[q]]  # var+qa


def evaluate(model, strategy):
    pos, neg, neg_top2 = [], [], []  # pos: (top1 score, correct top1?, correct in top3?, top2 score) ; neg: top1 score
    for S in SETS.values():
        flat, owner = [], []
        for i, (q, a, _) in enumerate(S["entries"]):
            for d in docs_for(strategy, q, a):
                flat.append(d)
                owner.append(i)
        D, owner = embed(model, flat), np.array(owner)
        n = len(S["entries"])

        def scores(Q):  # entry score = max over that entry's documents
            sim = Q @ D.T
            return np.stack([sim[:, owner == i].max(axis=1) for i in range(n)], axis=1)

        for i, (_, _, paras) in enumerate(S["entries"]):
            for row in scores(embed(model, paras)):
                order = np.argsort(-row)
                pos.append((row[order[0]], int(order[0]) == i, i in order[:3], row[order[1]]))
        for row in scores(embed(model, S["negatives"])):
            neg.append(row.max())
            neg_top2.append(np.sort(row)[-2])
    evaluate.neg_top2 = neg_top2
    return pos, neg


for model in (MODELS if __name__ == "__main__" else []):
    for strategy in ("q", "qa", "var", "var+qa"):
        pos, neg = evaluate(model, strategy)
        print(f"\n== {model} | {strategy:6} | top-1 {np.mean([p[1] for p in pos]):.1%} | top-3 {np.mean([p[2] for p in pos]):.1%} | n={len(pos)}+{len(neg)}neg")
        print("   thr  | AUTO-ANSWER: correct  wrong  neg-answered | SUGGEST (top-3 has it & score>=thr): hit   neg-shown")
        for thr in (0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
            ok = np.mean([p[1] and p[0] >= thr for p in pos]); bad = np.mean([(not p[1]) and p[0] >= thr for p in pos])
            na = np.mean([s >= thr for s in neg]); hit = np.mean([p[2] and p[0] >= thr for p in pos])
            print(f"   {thr:.2f} |              {ok:6.1%}  {bad:5.1%}  {na:6.1%}        |                                     {hit:6.1%}  {na:6.1%}")
