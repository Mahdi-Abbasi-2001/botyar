"""Evaluate the complete three-tier FAQ policy on the Persian set: answer / suggest top-3 / not found."""
import itertools
import sys

import numpy as np

from scripts import eval_faq as E

pos, neg = E.evaluate("text-embedding-3-small", "var")
nt2 = E.evaluate.neg_top2
print(f"{len(pos)} valid questions, {len(neg)} off-topic questions (text-embedding-3-small + LLM variants)\n")
print(" T_hi  margin T_lo |  VALID: answered-right  answered-WRONG  suggested-has-it  suggested-miss  not-found |  OFF-TOPIC: answered(bad)  suggestions-shown  clean-not-found")
for t_hi, margin, t_lo in itertools.product((0.55, 0.60, 0.65), (0.0, 0.03, 0.05), (0.40, 0.45, 0.50)):
    r = dict(right=0, wrong=0, sug_ok=0, sug_miss=0, nf=0)
    for top, correct, in3, second in pos:
        if top >= t_hi and top - second >= margin:
            r["right" if correct else "wrong"] += 1
        elif top >= t_lo:
            r["sug_ok" if in3 else "sug_miss"] += 1
        else:
            r["nf"] += 1
    a = sum(1 for t, s in zip(neg, nt2) if t >= t_hi and t - s >= margin)
    g = sum(1 for t, s in zip(neg, nt2) if not (t >= t_hi and t - s >= margin) and t >= t_lo)
    n = len(pos)
    print(f" {t_hi:.2f}  {margin:.2f}   {t_lo:.2f} |  {r['right']/n:6.1%}          {r['wrong']/n:6.1%}          {r['sug_ok']/n:6.1%}            {r['sug_miss']/n:6.1%}         {r['nf']/n:6.1%}   |  {a/len(neg):6.1%}                 {g/len(neg):6.1%}            {1-(a+g)/len(neg):6.1%}")
