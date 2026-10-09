# Botyar (بات‌یار) — Business plan (DRAFT v1, 2026-10-05)

**How to read the numbers.** Market figures and competitor prices come from public pages listed with their sources; AI costs are measured from our own product logs and tests; plan prices and the infrastructure estimate are proposals not yet validated with real customers. Where we could not find a number we say it is not known yet instead of guessing.

## 1. One-sentence pitch
Describe your Bale bot in Persian; an agent builds it, tests it before it goes live, publishes it, and keeps changing it when you ask — for a flat monthly price.

## 2. The problem
Small Iranian businesses (cafés, clinics, salons, gyms, shops, teachers) live on messengers, but a working bot today means either:
- **hiring a freelancer**: a basic Bale bot costs **2–8 million Toman**, a shop bot **12–30 million**, custom work from **30 million**; each extra feature (payment, booking, AI support) adds **1.5–7 million** (source: a public bot price guide, 1405); or
- **building it yourself** in an existing visual/no-code bot builder: powerful, but you must learn blocks and plugin syntax, and some meter the bill per feature per day plus per message, with a course session just on how to calculate it (source: the builders' own public documentation).
Both options are slow, and changes later (a new price, a new class time) need the same effort again.

## 3. The solution (what exists today, in production)
- **Agent builder**: Persian description → clarifying questions only when needed → bot spec → **automatic test scenarios run against the real engine** → repair loop (up to 3) → save. Measured cost **about $0.002–0.010 per build or change, typically $0.004** (measured from the `llm_calls` log and the eval harness).
- **AI where it builds, certainty where it serves**: the agent builds and changes the bot; the published bot says exactly what the owner approved (a validated spec run by an engine). Safe, cheap, testable, explainable.
- **Block types** (all in the spec language): messages (random variants, photo/file, map pin), forms, bookings (fixed slots with capacity and waitlist, weekly repeats with Jalali dates, **individual appointments from working hours and staff**, cancel and reschedule), orders and shops (catalog from CSV/Excel/paste/photo, stock, delivery fee, discount codes, **online payment inside Bale**), FAQ (retrieval only: answers are the owner's own sentences), quizzes, sub-menus, ratings, invite links, anonymous chat, "talk to the owner" inbox, owner notifications, optional forced channel join.
- **Owner panel**: records with cancel/status actions, inbox with replies delivered to the customer's chat, announcements (manual and scheduled, with `/stop` opt-out), customers list with Excel export, booking reminders, files tab, plan and usage page.
- **Channels**: Bale and Telegram. The shared bot `@botyar_ai_bot` exists on both (links/QR and a directory of businesses), or an owner can use their own bot token. Telegram runs through a relay outside Iran.
- **Community tools** (new, to be proven on real Bale): forced channel join, invite links with counting, anonymous chat with report/ban, post forwarding between channels, group moderation.
- **Reliability**: safe retries, a retry queue and a health banner when Bale or Telegram is unreachable (`docs/technical.md` §8).
- **Quality evidence**: 491 automated tests, a committed agent regression harness (68 real-model cases), mutation checks for business rules, fuzzing of conversations.

## 4. Market
- Bale: **28.7 million monthly active users and 16.2 million daily** (Iran's Information Technology Organization, published March 2026, covering the period to the end of the Iranian year 1404). The same report attributes part of the growth to the internet-outage periods, so we read the number as the current size of the market and not as a guaranteed trend.
- Number of small businesses using bots in Iran: not found, so we do not guess. Proxy: established Iranian bot-builder companies already sell to this market with paid plans, i.e. demand is proven.
- Reachable first segment (our product fits today): appointment-based and order-based small businesses on Bale: clinics, salons, cafés, bakeries, classes, gyms, small shops. Count: not known yet.

## 5. Competition and advantage (public information, read 2026-10-05)
| | Botyar | Visual/no-code builders with usage billing | Flat-plan bot builders | Freelancers |
|---|---|---|---|---|
| Build | **describe in Persian; the agent builds** | blocks, plugins, advanced scripting | button/menu configuration | brief + waiting |
| Change | **one sentence, a readable diff, all tests re-run** | edit blocks by hand | edit the menu by hand | a new order |
| Cost | **flat monthly plan from 299,000 Toman** (proposed) | per feature per day plus per message (about 20 Toman per "diamond", 3 Toman per "point", +10% VAT); their own sample bots work out to roughly 150–235k Toman/month (source: the builder's own price calculator, read 2026-10-05) | flat plans of 183k / 287k / 609k Toman/month, about 22–26% off when paid yearly (source: public price page, read 2026-10-05) | one-off 2–30M Toman |
| Channels | Bale, Telegram | many (Bale, Telegram, Eitaa, iGap, Rubika, Soroush, WhatsApp, SMS) | — | any |
| Breadth | focused: booking, orders, FAQ, forms, payments, community tools | very broad (shop, scheduled posts, group manager, API/AI, custom code) | — | unlimited |

**Our advantages**
- **Tested before publish:** every version is exercised with real conversations and is not published until all pass. The first two columns do not mention anything like it in their public information, and freelancers usually test by hand.
- **A runtime owners can trust:** the agent builds and changes the bot; the published bot says exactly what the owner approved, so it does not give a wrong price or hour and cannot be talked out of its rules.
- **Growth tools inside the product:** forced channel join, invite links, quizzes, anonymous chat and in-Bale payment.

**Our position.** We win on **time to a working, tested bot for a non-technical owner** and on **predictable cost**. Larger competitors are ahead on breadth of features and number of messengers, and we stay focused on purpose; Basic also costs more than the first two columns, and its advantage is a predictable bill and no freelancer fee for every change. Our defensibility is the work on the agent and the mandatory tests, not being a platform for its own sake.

## 6. Business model (proposed)
Per-account monthly plans; every feature is in every plan, plans differ only in limits (enforced in the product, see `api/app/billing.py` and the public `/pricing` page):

| Plan | Price (Toman/month) | Bots / live | Active customers per live bot (30 days) | Agent requests (30 days) |
|---|---|---|---|---|
| Free | 0 | 1 / 1 | 100 | 10 |
| Basic | 299,000 | 3 / 1 | 500 | 50 |
| Pro | 699,000 | 10 / 3 | 3,000 | 120 |
| Enterprise («سازمانی») | 2,990,000 | 50 / 10 | 3,000 | 500 |
Why these numbers: prices are set at about 270,000 Toman per USD, and each plan's request limit is chosen so that even if the limit is used in full every month the AI cost stays near 45% of the price (the costs are in dollars, the prices in Toman, so they need revisiting when the rate moves). For comparison: a usage-billed builder's own sample bots cost 150–235k Toman/month, a flat-plan builder starts at 183k, and a freelancer's single basic bot costs 2–8M once. Basic at 299k is above the first two and has to be justified by value (building and changing bots without a freelancer, automatic tests before publishing, the management panel). **The founder must still validate the numbers with owners.**
In this demo build, upgrading is a **simulated payment**: the plan is activated immediately and the account page shows an invoice history marked «پرداخت آزمایشی» (no money moves, because there is no payment gateway yet). A switch (`BILLING_DEMO=false`) turns on the request-and-approve flow for a manual launch. Real subscription payment (e.g. ZarinPal) is not done yet: it needs merchant onboarding.
Later options: annual discount (the flat-plan builders give about 22–26%), one-off "we build it for you" service, white-label for agencies. Not taking a cut of customers' payments: money goes to the owner's own Bale wallet by design.

## 7. Unit economics
Measured AI cost per request is $0.002–0.010 (typically about $0.004; re-measured on 9 October after the fidelity checks were added). Worst-case AI cost per plan if the limit is fully used every month, at $0.01 per request: Free 10 → **$0.10** (≈ 27k Toman); Basic 50 → **$0.50** (≈ 135k); Pro 120 → **$1.20** (≈ 324k); Enterprise 500 → **$5.00** (≈ 1.35M); each about 45% of the plan price. Customers chatting with bots cost **no AI**; the FAQ's embedding call is ≈ $0.0000003 per question.
Not yet known: hosting cost per account (estimated at about 5,000 Toman a month, roughly 1M Toman for a small instance ÷ about 200 accounts; no load test yet), the USD→Toman rate used for the plan, payment-gateway fees, support time. Gross margin therefore cannot be stated yet; the AI cost is a small fraction of any plausible price.

## 8. Go-to-market
1. **Demo video + live link** (this competition) and 3–5 pilot businesses (a clinic, a café, a salon) whose real feedback replaces the unknowns above.
2. Industry templates per vertical (café, clinic, salon, class) as one-click starting points.
3. Agencies/freelancers as resellers (Enterprise plan, «سازمانی»): they already sell bots for millions and can resell ours at a fraction of the effort.
4. Short "bot in 3 minutes" videos on Bale/Instagram; the shared-bot directory lists published businesses.

## 9. Roadmap
Done: see §3; the bots have also been tried to some extent on real Bale and Telegram. Next (by value): subscription payments + invoices; finishing the field tests on real Bale and Telegram for what has not been tried yet; more messengers (Eitaa, Rubika); template marketplace; analytics-driven suggestions ("40% leave at the phone-number step — shorten the form?"); mini-app admin panel; media forwarding between messengers. Deliberately not planned: free-form AI chat with customers (cost, safety).

## 10. Current risks (demo version)
- **Incumbent adds an AI front-end.** Answer: the tested deterministic engine, the owner dashboard, price predictability.
- **Platform dependency** (Bale/Telegram rules, network conditions in Iran). Answer: channel-neutral engine; Telegram already runs through a relay.
- **Single-instance deployment** (in-process locks) and **no password reset / data deletion yet** — must be fixed before real customers at scale.
- **Agent mistakes.** Mitigation: tests before publish, owner reviews, regression harness, honest "not supported" messages.
- **Unvalidated pricing and demand.** Mitigation: pilots in §8.

## 11. The founder and what we want
**Who I am.** Mahdi Abbasi, software engineer and the only member of the team. I built and maintain every technical part of Botyar:
- the builder agent and its automatic tests;
- the runtime engine and its blocks (booking, shop, forms, quizzes and more);
- the web interface for building, testing, publishing and managing;
- the Bale and Telegram integration, in-Bale payment and notifications;
- deployment and infrastructure.

Skills: Python, messenger bots and React. The product is online and usable today and I cover the technical side myself; the next technical work (multi-instance hosting, monitoring, password reset) is in the roadmap.

**What I lack.** Two things, both non-technical:
1. **An investor**, for pilots with 3–5 trades, the subscription payment gateway, training content and marketing. First-90-day goals: 3–5 pilots, at least 10 real customers per bot in the first week, and 50 paying accounts by the end of month three. The amount and terms will be set after the pilot results (not known yet).
2. **A sales partner**: someone with connections among small businesses (clinics, salons, cafés, schools, shops), trade unions or agencies who can sell Botyar and land the first pilots. Terms are agreed in conversation.

**Proposed use of funds:** (1) pilots and sales with 3–5 trades; (2) payment gateway and support; (3) multi-instance hosting and monitoring; (4) training content and video.

## 12. What the founder still has to provide
Real prices after owner conversations; a load test to confirm the infrastructure estimate; the investment amount, after the pilot results; screenshots from the live product and a phone test of payment, inbox and reminders for the pitch.
