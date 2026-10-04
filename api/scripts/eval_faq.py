"""Measure how well an embedding model matches informal Persian questions to FAQ entries (costs well under a cent).

    cd api && set -a && . ./.env && set +a && PYTHONPATH=. .venv/bin/python scripts/eval_faq.py [model ...]
"""
import sys

import numpy as np
from openai import OpenAI

from scripts.faq_eval_data import SETS

client = OpenAI()
MODELS = sys.argv[1:] or ["text-embedding-3-small", "text-embedding-3-large"]


def embed(model, texts):
    out = client.embeddings.create(model=model, input=texts)
    v = np.array([d.embedding for d in out.data], dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


for model in MODELS:
    for strategy in ("question", "question+answer"):
        pos, neg = [], []  # (top score, second score, correct?) ; (top score, second)
        for name, S in SETS.items():
            docs = [q if strategy == "question" else f"{q} {a}" for q, a, _ in S["entries"]]
            D = embed(model, docs)
            for idx, (_, _, paras) in enumerate(S["entries"]):
                Q = embed(model, paras)
                for row in Q @ D.T:
                    order = np.argsort(-row)
                    pos.append((row[order[0]], row[order[1]], int(order[0]) == idx))
            N = embed(model, S["negatives"])
            for row in N @ D.T:
                srt = np.sort(row)[::-1]
                neg.append((srt[0], srt[1], S["negatives"][0]))
        top1 = np.mean([p[2] for p in pos])
        print(f"\n== {model} | embed={strategy} | top-1 accuracy ignoring threshold: {top1:.1%} ({len(pos)} paraphrases, {len(neg)} negatives)")
        print("   thr  | answer-recall (correct & above) | wrong-answers | negatives wrongly answered")
        for thr in (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
            ok = np.mean([p[2] and p[0] >= thr for p in pos])
            wrong = np.mean([(not p[2]) and p[0] >= thr for p in pos])
            fa = np.mean([n[0] >= thr for n in neg])
            print(f"   {thr:.2f} | {ok:6.1%}                          | {wrong:6.1%}        | {fa:6.1%}")
