"""Choose FAQ thresholds that are safe across DIFFERENT random draws of LLM-written variants (not one lucky draw)."""
import itertools
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from scripts import eval_faq as E
from scripts.faq_eval_data import SETS

DRAWS = int(sys.argv[1]) if len(sys.argv) > 1 else 4
MODEL = "text-embedding-3-small"


def one_draw():
    questions = [(q, a) for S in SETS.values() for q, a, _ in S["entries"]]
    with ThreadPoolExecutor(6) as ex:
        var = dict(zip([q for q, _ in questions], ex.map(lambda t: E.variants_for(*t), questions)))
    pos, neg = [], []  # (top, second, correct, in3) ; (top, second)
    for S in SETS.values():
        flat, owner = [], []
        for i, (q, a, _) in enumerate(S["entries"]):
            for d in [q, *var[q]]:
                flat.append(d)
                owner.append(i)
        D, owner, n = E.embed(MODEL, flat), np.array(owner), len(S["entries"])
        score = lambda Q: np.stack([(Q @ D.T)[:, owner == i].max(axis=1) for i in range(n)], axis=1)
        for i, (_, _, paras) in enumerate(S["entries"]):
            for row in score(E.embed(MODEL, paras)):
                o = np.argsort(-row)
                pos.append((row[o[0]], row[o[1]], int(o[0]) == i, i in o[:3]))
        for row in score(E.embed(MODEL, S["negatives"])):
            srt = np.sort(row)[::-1]
            neg.append((srt[0], srt[1]))
    return pos, neg


draws = [one_draw() for _ in range(DRAWS)]
print(f"{DRAWS} independent draws of LLM variants; {len(draws[0][0])} valid + {len(draws[0][1])} off-topic questions each\n")
print(" T_hi margin | valid answered-right (min/mean)   WRONG (mean/max)   | off-topic answered (mean/max)   | valid right-via-tap (mean)")
for t_hi, margin in itertools.product((0.55, 0.60, 0.65, 0.70), (0.03, 0.06, 0.09)):
    R, W, NA, TAP = [], [], [], []
    for pos, neg in draws:
        r = w = tap = 0
        for top, sec, ok, in3 in pos:
            if top >= t_hi and top - sec >= margin:
                r += ok
                w += not ok
            elif top >= 0.45 and in3:
                tap += 1
        n = len(pos)
        R.append(r / n); W.append(w / n); TAP.append(tap / n)
        NA.append(sum(1 for t, s in neg if t >= t_hi and t - s >= margin) / len(neg))
    print(f" {t_hi:.2f}  {margin:.2f}  |  {min(R):6.1%} / {np.mean(R):6.1%}                  {np.mean(W):5.1%} / {max(W):5.1%}      |  {np.mean(NA):5.1%} / {max(NA):5.1%}                   |  {np.mean(TAP):6.1%}")
