# Botyar (بات‌یار) — Business plan (DRAFT v1, 2026-10-05)

**Status of the numbers.** Everything below marked **[measured]** comes from our own product logs, **[sourced]** from a page we read (source URLs are given next to each number), **[proposed]** is our own proposal that has *not* been validated with customers, and **[blank]** is unknown and must be filled by the founder. Nothing is invented.

## 1. One-sentence pitch
Describe your Bale bot in Persian; an agent builds it, tests it before it goes live, publishes it, and keeps changing it when you ask — for a flat monthly price.

## 2. The problem
Small Iranian businesses (cafés, clinics, salons, gyms, shops, teachers) live on messengers, but a working bot today means either:
- **hiring a freelancer**: a basic Bale bot costs **2–8 million Toman**, a shop bot **12–30 million**, custom work from **30 million**; each extra feature (payment, booking, AI support) adds **1.5–7 million** [sourced: a public bot price guide, 1405; re-check before the pitch]; or
- **building it yourself** in an existing visual/no-code bot builder: powerful, but you must learn blocks and plugin syntax, and some meter the bill per feature per day plus per message, with a course session just on how to calculate it [sourced: the builders' own public documentation].
Both options are slow, and changes later (a new price, a new class time) need the same effort again.

## 3. The solution (what exists today, in production)
- **Agent builder**: Persian description → clarifying questions only when needed → bot spec → **automatic test scenarios run against the real engine** → repair loop (up to 3) → save. Measured cost **about $0.001–0.009 per build or change** [measured: `llm_calls` log, eval harness].
- **Deterministic runtime**: customers never talk to an LLM; the agent only writes a validated spec that an engine executes. Safe, cheap, testable, explainable.
- **Block types** (all in the spec language): messages (random variants, photo/file, map pin), forms, bookings (fixed slots with capacity and waitlist, weekly repeats with Jalali dates, **individual appointments from working hours and staff**, cancel and reschedule), orders and shops (catalog from CSV/Excel/paste/photo, stock, delivery fee, discount codes, **online payment inside Bale**), FAQ (retrieval only: answers are the owner's own sentences), quizzes, sub-menus, ratings, invite links, anonymous chat, "talk to the owner" inbox, owner notifications, optional forced channel join.
- **Owner panel**: records with cancel/status actions, inbox with replies delivered to the customer's chat, announcements (manual and scheduled, with `/stop` opt-out), customers list with Excel export, booking reminders, files tab, plan and usage page.
- **Channels**: Bale (shared bot with links/QR and a directory, or the owner's own bot token); Telegram via a relay outside Iran.
- **Community tools** (new, to be proven on real Bale): forced channel join, invite links with counting, anonymous chat with report/ban, post forwarding between channels, group moderation.
- **Reliability**: safe retries, a retry queue and a health banner when Bale or Telegram is unreachable (`docs/technical.md` §8).
- **Quality evidence**: 270+ automated tests, a committed agent regression harness (54 real-model cases), mutation checks for business rules, fuzzing of conversations.

## 4. Market
- Bale: **16.5 million monthly active users (May 2023, Iranian ICT ministry); 35 million+ registered** [sourced earlier in research; re-verify before the pitch].
- Number of small businesses using bots in Iran: **[blank — not found; do not guess]**. Proxy: established Iranian bot-builder companies already sell to this market with paid plans, i.e. demand is proven.
- Reachable first segment (our product fits today): appointment-based and order-based small businesses on Bale: clinics, salons, cafés, bakeries, classes, gyms, small shops. Count: **[blank]**.

## 5. Competition (public information, read 2026-10-05)
| | Botyar | Visual/no-code builders with usage billing | Flat-plan bot builders | Freelancers |
|---|---|---|---|---|
| How you build | **describe in Persian** | blocks, plugins, advanced scripting | button/menu configuration | brief + waiting |
| Tested before publish | **yes, automatic** | not seen in their documentation | not researched | manual, depends |
| Price model | flat monthly per plan [proposed] | per feature per day plus per message (about 20 Toman per "diamond", 3 Toman per "point", +10% VAT); their own sample bots work out to roughly 150–235k Toman/month [sourced: the builder's own price calculator, read 2026-10-05] | flat plans of 183k / 287k / 609k Toman/month, about 22–26% off when paid yearly [sourced: public price page, read 2026-10-05] | one-off 2–30M Toman |
| Channels | Bale, Telegram | many (Bale, Telegram, Eitaa, iGap, Rubika, Soroush, WhatsApp, SMS) | — | any |
| Breadth | focused: booking, orders, FAQ, forms, payments, community tools | very broad (shop, scheduled posts, group manager, API/AI, custom code) | — | unlimited |
Honest position: we do **not** win on breadth. We win on **time to a working, tested bot for a non-technical owner**, and on **predictable pricing**.

## 6. Business model [proposed, not validated]
Per-account monthly plans; every feature is in every plan, plans differ only in limits (enforced in the product, see `api/app/billing.py` and the public `/pricing` page):

| Plan | Price (Toman/month) | Bots / live | Active customers per live bot (30 days) | Agent requests (30 days) |
|---|---|---|---|---|
| Free | 0 | 3 / 1 | 100 | 30 |
| Basic | 149,000 | 3 / 1 | 500 | 100 |
| Pro | 349,000 | 10 / 3 | 3,000 | 300 |
| Agency | 1,490,000 | 50 / 10 | 3,000 | 1,500 |
Why these anchors: a usage-billed builder's own sample bots cost 150–235k Toman/month; a flat-plan builder starts at 183k; a freelancer's single basic bot costs 2–8M once — so ~150–350k/month is in-market and cheap next to a freelancer. **The founder must still validate the numbers with owners.**
In this demo build, upgrading is a **simulated payment**: the plan is activated immediately and the account page shows an invoice history marked «پرداخت آزمایشی» (no money moves, because there is no payment gateway yet). A switch (`BILLING_DEMO=false`) turns on the request-and-approve flow for a manual launch. Real subscription payment (e.g. ZarinPal) is **[blank — needs merchant onboarding]**.
Later options: annual discount (the flat-plan builders give about 22–26%), one-off "we build it for you" service, white-label for agencies. Not taking a cut of customers' payments: money goes to the owner's own Bale wallet by design.

## 7. Unit economics
Measured AI cost per request is $0.001–0.009 (median about $0.002). Worst-case AI cost per plan if the limit is fully used every month: Free 30 × $0.009 ≈ **$0.27**; Basic 100 × $0.009 ≈ **$0.90**; Pro 300 ≈ **$2.70**; Agency 1,500 ≈ **$13.50**. Customers chatting with bots cost **no AI**; the FAQ's embedding call is ≈ $0.0000003 per question [measured].
Not yet known: hosting cost per bot (Liara plan price **[blank]**), USD→Toman rate used for the plan **[blank]**, payment-gateway fees **[blank]**, support time. Gross margin therefore cannot be stated yet; the AI cost is a small fraction of any plausible price.

## 8. Go-to-market
1. **Demo video + live link** (this competition) and 3–5 pilot businesses (a clinic, a café, a salon) whose real feedback replaces the blanks above **[blank — founder]**.
2. Industry templates per vertical (café, clinic, salon, class) as one-click starting points.
3. Agencies/freelancers as resellers (Agency plan): they already sell bots for millions and can resell ours at a fraction of the effort.
4. Short "bot in 3 minutes" videos on Bale/Instagram; the shared-bot directory lists published businesses.

## 9. Roadmap
Done: see §3. Next (by value): subscription payments + invoices; more messengers (Eitaa, Rubika); template marketplace; analytics-driven suggestions ("40% leave at the phone-number step — shorten the form?"); mini-app admin panel; media forwarding between messengers. Deliberately not planned: free-form AI chat with customers (cost, safety).

## 10. Risks (honest)
- **Incumbent adds an AI front-end.** Answer: the tested deterministic engine, the owner dashboard, price predictability.
- **Platform dependency** (Bale/Telegram rules, network conditions in Iran). Answer: channel-neutral engine; Telegram already runs through a relay.
- **Single-instance deployment** (in-process locks) and **no password reset / data deletion yet** — must be fixed before real customers at scale.
- **Agent mistakes.** Mitigation: tests before publish, owner reviews, regression harness, honest "not supported" messages.
- **Unvalidated pricing and demand.** Mitigation: pilots in §8.

## 11. Team and ask
Solo founder: **[blank — founder to write]**. Use of funds if funded: **[blank]**.

## 12. What the founder still has to provide
Real prices after owner conversations; market numbers; hosting cost; team/ask text; screenshots from the live product and a phone test of payment, inbox and reminders for the pitch.
