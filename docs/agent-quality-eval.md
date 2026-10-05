# Agent quality evaluation (2026-10-04)

Eight varied Persian requests, each sent as a single message to a fresh account on the local build against the real
`gpt-6-luna` API (the same code as production). If the agent asked questions, the follow-up was the fixed sentence
«بقیه‌ی جزئیات رو خودت تصمیم بگیر و بساز.» Measured: outcome, repair rounds, wall time, LLM cost (from the per-call log).

| Case | Built | Block chosen | Repairs | Tests | Time | Cost |
|---|---|---|---|---|---|---|
| Hair salon, 3 time slots | yes | booking | 0 | 3/3 | 19 s | $0.0010 |
| Restaurant, 5 dishes, bread choice, min order | yes | catalog_order (inline) | 2 | 3/3 | 43 s | $0.0034 |
| Language school, level choice | yes | form | 0 | 3/3 | 12 s | $0.0006 |
| Bookstore, thousands of titles, Excel later | yes (2 messages) | catalog_order (table) | 1 | 2/2 | 38 s | $0.0028 |
| Skin clinic, 2 slots + address/hours | yes | booking + message | 0 | 4/4 | 18 s | $0.0010 |
| Gym with online payment + SMS reminders (unsupported) | yes | booking | 1 | 3/3 | 28 s | $0.0017 |
| Phone repair request form | yes | form | 0 | 2/2 | 15 s | $0.0007 |
| Large café menu (25 items, categories) | yes | catalog_order (table) | 1 | 4/4 | 41 s | $0.0031 |

**Totals:** 8/8 built, 8/8 with all of the agent's own tests passing, 4/8 without any repair round, $0.0143 in total
(average $0.0018 per bot), 12–43 s per bot.

**Behaviour worth noting**
- Chose a database-backed table catalog by itself for the bookstore and the large café, and an inline menu for the 5-dish restaurant.
- For the unsupported request it said so in the assumptions («پرداخت آنلاین و یادآوری پیامکی پشتیبانی نمی‌شود») and built the closest supported bot.

**Limits of this measurement (be honest in the pitch)**
- Eight cases, one run each; the agent is non-deterministic, so numbers will vary run to run.
- The tests are written by the same agent that designs the bot. «All tests pass» proves the bot behaves as the agent
  understood the request, not that it matches what the owner meant. The simulator is where the owner confirms that.


---

# Regression harness (updated 2026-10-06)

The eight-case study above was the first measurement. Since then the evaluation became a committed harness,
`api/scripts/eval_agent.py`, with **54 real-model cases** (run it with name filters, e.g. `eval_agent.py quiz menu`). Each case sends one Persian
request to a fresh account on a throw-away database, answers clarifying questions with a fixed sentence, then checks *what was
built* (blocks, numbers copied exactly, honest «پشتیبانی نمی‌شود» notes), that the agent's own tests pass, cost ≤ $0.02 and time ≤ 150 s.

Case families: supported builds (slots, schedules, catalogs, orders, forms), weekly/appointment calendars, cancellation rules, FAQ (no
invented facts), contact, feedback, delivery fee and discount codes, online payment (and honest refusal for booking deposits), reminders,
order-edit not promised, random messages, personalised confirmations, sub-menus, quizzes (asks for the questions instead of inventing
answers), photos/files and map pins (never invents coordinates), forced channel join (asks for the channel), invite links, anonymous chat,
honest declines (face recognition, free-form AI chat, mobile app), and tiny odd requests (`scripts/odd_requests.py`).

Measured so far (honest summary):
- **Full run, 2026-10-05, 40 cases:** 36 passed on the first pass; the 4 failures were 3 transient provider errors (zero cost, zero tests) and 1 quality miss;
  all 4 passed when re-run individually. Total about $0.08 for the full run (average about $0.002 per case).
- **Cases added later** (random messages, placeholders, sub-menus, quizzes, files, join gate, referral, anonymous chat, odd requests) were run
  individually when added; they passed, and the prompt fixes they led to are in the repository.
- **Known non-determinism:** a few cases are flaky at about 1 in 4 (for example the «cancellation forbidden» wording and the first fix for
  «build the supported part of a tiny request», which went from about 3/4 to 5/5 after the second self-check was added). Rerunning a failing case once is part of the routine; a full run costs about $0.10 and is done once before each deploy.
- The agent still sometimes asks a needless second question for support-ticket style requests, and does not volunteer the «talk to the owner» block for them.
