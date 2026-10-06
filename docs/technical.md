# Botyar (بات‌یار) — Technical documentation

Version of 2026-10-06. Live: https://botyar.liara.run · Shared Bale bot: `@botyar_ai_bot`. This document describes what is in the repository; things that are built but not yet proven on a real messenger are marked **[unverified on a real messenger]** and listed in `docs/real-bale-checklist.md`.

## 1. What the system does

A business owner describes a chat bot in Persian. An agent builds it as a validated JSON description (a *BotSpec*), writes and runs tests for it, and — once all tests pass — the owner publishes it on Bale and/or Telegram. Customers then talk to a **deterministic engine** that executes the spec. The owner gets a panel (records, inbox, announcements, customers, files, channels) and can change the bot by describing the change; every change is diffed and re-tested.

Design principles (each is enforced in code, not just intended):
1. **The agent never writes code.** It produces a BotSpec (Pydantic models in `api/app/spec.py`); a fixed engine runs it.
2. **Customers never talk to a language model.** The runtime has no LLM call. (The only AI use at customer time is one embeddings lookup for FAQ free-text questions, which can only return the owner's own sentences, and it degrades to word matching if the provider is down.)
3. **A version cannot be published until every test passes.**
4. **Cheap by construction.** One LLM (`gpt-6-luna`) for all agent steps, effort tuned per step, cost logged per call; a typical build is about $0.002 [measured, `docs/agent-quality-eval.md`].
5. **Fail open for customers, closed for money.** Setup mistakes (join gate, wallet) never lock customers out; payments only count when the messenger confirms them.

## 2. Architecture

```
 Owner's browser ──► static Next.js UI ──► FastAPI (single instance) ──► PostgreSQL (SQLite in dev)
                                              │
        ┌─────────────────────────────────────┼──────────────────────────────┐
        ▼                                     ▼                              ▼
 BUILDER AGENT (LangGraph)            RUNTIME ENGINE (no LLM)        BACKGROUND JOBS (1 thread)
 clarify → design → validate →        engine.handle(spec, session,   reminders · scheduled announcements ·
 write tests → run tests →            text, store) → actions         unpaid-order expiry · anon-chat queue ·
 repair (≤3) → save version                    ▲                     outbox retries · webhook refresh
        │                                      │ webhook updates
        ▼                              ┌───────┴────────┐
   OpenAI API                     Bale Bot API    Telegram (through a Deno relay outside Iran)
```

| Layer | Technology |
|---|---|
| Frontend | Next.js (static export, Persian RTL, Vazirmatn), Tailwind 4; served by FastAPI from `api/static` (same origin) |
| Backend | Python, FastAPI, SQLAlchemy 2, Pydantic 2, httpx |
| Agent | LangGraph; OpenAI Responses API with strict structured outputs; model `gpt-6-luna` (only) |
| Embeddings | `text-embedding-3-small` (FAQ only) |
| Database | PostgreSQL on Liara (SQLite for development and tests) |
| Hosting | Liara (Docker), one app instance; Telegram relay on Deno Deploy |
| Messengers | Bale Bot API (`tapi.bale.ai`), Telegram Bot API via the relay |

## 3. Repository map

| File | Responsibility |
|---|---|
| `api/app/spec.py` | BotSpec: all block types, spec-level `gate`, validation (menu references, sub-menu cycles, placeholders) |
| `api/app/engine.py`, `engine_text.py` | Runtime: sessions, every block's conversation flow, cancellation/reschedule, payments state, quiz/anon/referral steps |
| `api/app/agent.py`, `prompts.py`, `llm.py`, `llm_schema.py`, `templates.py` | Builder agent, prompts (runtime semantics + design rules), the single LLM entry point, the LLM-facing schema |
| `api/app/testing.py` | Test scenarios, deterministic runner on a fixed clock, spec diff |
| `api/app/bale.py` | The channel layer shared by Bale and Telegram: webhook update processing, button rendering, delivery, customer sessions, payments hooks |
| `api/app/telegram.py`, `relay/` | Telegram publishing + the relay |
| `api/app/publish.py` | Bale publishing (shared link/QR, own token), directory listing, unpublish |
| `api/app/resilience.py`, `outbox.py`, `webhooks.py` | Outage handling: retries, health, queue, webhook refresh |
| `api/app/outreach.py` | Reminders, announcements (manual/scheduled), unpaid-order expiry, the background loop |
| `api/app/payments.py`, `billing.py` | Owner wallet token for Bale invoices; plans, limits, demo payments |
| `api/app/communities.py`, `gate.py`, `referral.py`, `anon.py` | Channel/group linking, post forwarding, group moderation, forced join, invite links, anonymous chat |
| `api/app/catalog.py`, `export.py`, `faq_index.py`, `faq_match.py`, `media.py`, `customers.py`, `records_ops.py` | Catalog import, exports, FAQ retrieval, files, customers list/bans, owner actions on records |
| `api/app/models.py`, `store.py`, `db.py`, `auth.py`, `config.py`, `dates.py` | Tables, record store, DB session, JWT auth, settings, Jalali dates and the fixed test clock |
| `web/app/*`, `web/components/workspace/*` | UI: landing, auth, bots, workspace tabs, pricing, account |
| `api/tests/` (41 files, 261 test functions) | Backend tests (no network, no OpenAI) |
| `api/scripts/` | Agent regression harness (`eval_agent.py`, 54 cases), `odd_requests.py`, FAQ evaluation scripts |

## 4. The BotSpec

```
BotSpec { name, welcome, menu[{label, block}], blocks[...], gate? }
```
Blocks (all validated by Pydantic; a menu entry points at any non-`admin_notify` block):

| Block | What the customer experiences | Notes |
|---|---|---|
| `message` | text; optional random `variants` (never the same twice in a row), a photo/file (`media`), a map pin (`location`) | files and pins are sent after the text; the owner uploads the real file in the Files tab |
| `form` | field-by-field questions (text, phone with Iranian-mobile check, number, choice) | `done_text` may contain `{field_key}` and `{id}` |
| `booking` | fixed slots with capacity and optional waitlist; weekly repeating slots with per-date capacity and Jalali dates; **appointments generated from working hours** (staff, duration, break, paged times); cancellation with deadline; **reschedule** | `reminder_hours`; waitlist promotion messages another customer |
| `catalog_order` | inline items or a database catalog (categories, search, paging, options, quantity, stock), cart, contact fields | `delivery_fee`, `free_delivery_over`, `discount_codes` (percent/amount, min total, max uses); `payment: online` (Bale invoice); cancel window; owner status flow new→preparing→ready→done |
| `faq` | pick a question or type one; the answer is the owner's own text; 3-tier confidence; unanswered questions are logged | embeddings; lexical fallback; 30 searches/customer/hour |
| `contact` | message to the owner; the owner replies from the panel and the reply arrives in the customer's chat | inbox with opaque thread ids |
| `feedback` | 1–5 stars + comment; max 5 per customer per day | panel shows the average |
| `menu` | a sub-menu (nestable, no loops, 1–10 items) | message items keep the customer inside the sub-menu |
| `quiz` | multiple choice with one correct answer, score at the end | results stored for the owner |
| `referral` | personal invite link, invite count, goal, the owner's own reward text | counts brand-new customers only |
| `anon_chat` | anonymous text chat between two customers | see §11 |
| `admin_notify` | (owner side) notifies the owner when the watched block completes | |
| spec-level `gate` | the customer must be a member of the owner's channel first | see §11 |

Validation rules worth knowing: block ids unique; menu targets exist; `admin_notify` watches an existing block; booking has `slots` XOR `schedule`; sub-menus may not form a cycle; placeholders in confirmation texts must name real fields (checked at build time so a literal `{typo}` never reaches a customer); discount codes are unique and have exactly one of percent/amount; the LLM-facing schema (`llm_schema.py`) mirrors this with plain unions because strict structured outputs reject `oneOf`.

## 5. The runtime engine

`engine.handle(spec, session, text, store, now=None, matcher=None, rng=None) -> list[action]`

- **Actions** are plain dicts: `send {text, buttons, edit}`, `notify_admin`, `notify_customer {cust, text, buttons?}`, `media`, `location`, `invoice`, and `anon_*` (find/relay/end/report). The channel layer turns them into messenger calls; the simulator and the test runner consume the same list. `edit: true` is set only on navigation replies (next page, category, time paging) and makes Bale edit the tapped message in place, falling back to a new message.
- **Sessions** are JSON (`block`, `step`, `data`, `cust`, plus adapter-set keys such as `ref`, `pay_ok`); they are deep-copied before use because in-place edits are invisible to SQLAlchemy change detection.
- **Button data** is ASCII and ≤64 bytes (longer values are mapped to `~n` tokens); display text gets Persian digits only at the channel layer, so tests and logic stay ASCII.
- **Stale-state recovery**: if the owner republishes while a customer is mid-flow and the saved state points at something that no longer exists, the engine resets that customer with an explanation instead of failing.
- **Determinism**: the clock is injectable; the agent's tests run on a fixed Saturday 2026-10-03 12:00 Tehran; random messages use a cycling generator in tests.
- **Owner-visible hidden fields**: `_cust` and `_at` identify the customer and time on records; they are stripped from API output and exports.

## 6. The builder agent

LangGraph: `clarify → design → validate → write_tests → run_tests → repair (≤3) → save`. Outcomes: `done`, `needs_input` (≤3 focused Persian questions), `failed`, `declined`.
- **clarify** decides whether to build, ask, or decline. Rules in the prompt: build the closest supported bot instead of declining when only part of a request is unsupported; decline only when nothing useful can be built; never invent business facts (prices, hours, coordinates, quiz answers, channel names); say unsupported parts with the words «پشتیبانی نمی‌شود».
- **design** returns the full spec via strict structured output; Pydantic errors go back to the model for another attempt (max 3).
- **write_tests** produces ≤4 scenarios (steps with expected/forbidden substrings, setup runs for capacity, record checks). Tests are LLM-written and executed by the deterministic runner (`testing.py`).
- **repair** decides whether the spec or the test is wrong and fixes it; publishing stays locked while any test fails.
- **Change requests** receive the current spec, produce a readable diff, and re-run old and new tests.
- **Cost control**: per-user 40 runs/day, global 300 runs/day, plan limit on agent requests per 30 days, every call logged in `llm_calls` with tokens and cost; the UI shows cost per request.
- **Interrupted runs** (server restart) are failed at startup or after 6 minutes so a bot is never locked.
- **Quality harness**: `api/scripts/eval_agent.py` runs 54 real-model cases (supported builds with content checks, honest declines, no-invention rules, regression cases for every past failure). It is run only for the affected cases after a prompt change and once in full before a deploy.

## 7. Messenger layer

`bale.Channel` abstracts a Telegram-style messenger; `CHANNELS = {bale, tg}`. A customer is identified by `bale:<chat id>` or `tg:<chat id>` everywhere (sessions, records, customers, referrals, anonymous chat), so a booking made on one messenger can notify a person on the other.

**Publishing**: *shared bot* (one bot for all businesses; each business has a link `…?start=CODE` and QR; people without a link see a directory of businesses; typed codes are not accepted) or *own token* (encrypted with a key derived from `JWT_SECRET`; webhook registered with a secret path). Telegram works the same way through the relay (`TELEGRAM_RELAY_URL/KEY`, optional `TELEGRAM_SHARED_BOT_TOKEN`).

**Update processing order** in `bale._process` (one place, so every rule applies to both messengers): dedupe by `update_id` → payments (pre-checkout/successful) → group/channel updates (§11) → private text/callback → `/admin` owner link → shared-bot linking and referral payload → load session → `/stop` `/resume` → welcome reset → forced-join check → banned-customer check → customer tracking and plan cap → referral conversion and per-customer data → engine → anonymous-chat actions → delivery (with outbox) → save session. A per-bot lock serialises bookings so capacity checks cannot race.

**Owner notifications**: the owner sends `/admin <code>` (code from the Publish tab) from their own chat; notifications then go there.

**Payments (Bale only)**: `catalog_order.payment = "online"` + the owner's wallet token → Bale invoice (amounts in rials = Toman×10). Order is `awaiting_payment` (stock reserved), pre-checkout validates owner/amount/status, `successful_payment` marks it paid and notifies the owner; unpaid orders are cancelled after 15 minutes; paid orders can be cancelled only by the owner (refund is outside the bot). On the shared bot only Bale's published test wallet token is accepted; real money requires the owner's own bot. Telegram has no payment provider serving Iran, so it has none.

## 8. Reliability and outages

`resilience.request()` wraps every Bot API call (Bale, the Telegram relay, file uploads):
- retries **only** what is safe: connection failures before anything is sent, `429` (waits the server's `retry_after`, capped at 5 s), `502/503/504`; 3 attempts with 0.5 s / 1.5 s backoff;
- classifies results: `TransientError` (nothing delivered), `UncertainError` (read timeout: the message may have been delivered, **never auto-retried**, so no duplicates), `BaleError` (the messenger said no: blocked bot, bad chat/token);
- keeps per-messenger health (`ok / degraded / down` after 3 consecutive failures) shown as a banner in the panel with queue counters.

`outbox`: plain text messages that hit a `TransientError` are stored (no token inside) and retried by the background job every minute with growing gaps (1, 2, 4, 8, 15 min), in order per chat, probing a still-down messenger only once per round; after 5 attempts or 30 minutes they are marked failed (counted in the panel); finished rows are purged after 3 days; at most 500 pending per bot. Queued: replies, owner notifications, announcements, reminders. Not queued: edits, files, invoices.

`webhooks.refresh()` re-registers the shared Bale and Telegram webhooks and (20 per round) the owners' own-token webhooks every 15 minutes; failures are counted, never raised. Publishing during an outage returns a clear 503 instead of "your token is invalid".

Background jobs run in one daemon thread (production only, i.e. when `PUBLIC_BASE_URL` is set), each job isolated so one failure cannot stop the others. Limitation: single instance (locks and the scheduler live in process).

## 9. Messaging to customers

- **Reminders**: `booking.reminder_hours` (1–72) sends one fixed-text message before a confirmed booking with a clock time; never repeated, never for bookings made inside the window.
- **Announcements**: the owner's text, to everyone who talked to the bot on the messengers it is published on and did not send `/stop`; max 3 per 24 h (manual and scheduled together); every message ends with the `/stop` hint.
- **Scheduled announcements**: once at a Tehran date/time (≤90 days ahead) or every day at HH:MM; max 5 active; a run that cannot be delivered is recorded and skipped.

## 10. Plans and limits

`billing.PLANS` (prices are *proposed*, not validated with owners):

| Plan | Toman/month | Bots / live | Active customers per live bot (30 days) | Agent requests (30 days) |
|---|---|---|---|---|
| Free | 0 | 3 / 1 | 100 | 30 |
| Basic | 149,000 | 3 / 1 | 500 | 100 |
| Pro | 349,000 | 10 / 3 | 3,000 | 300 |
| Agency | 1,490,000 | 50 / 10 | 3,000 | 1,500 |

All features are in all plans. Limits are enforced when creating a bot, publishing, calling the agent, and when a *new* customer arrives (existing customers are never cut off; the owner is told once a day). **Demo billing** (`BILLING_DEMO=true`, the default): upgrading simulates a successful payment, activates the plan at once and records a clearly labelled simulated payment; no money moves. `BILLING_DEMO=false` switches to request-and-approve by accounts listed in `ADMIN_USERNAMES`.

## 11. Community features (channels, groups, growth)

All need the bot to be inside the channel/group; the owner links a chat by posting `/link <one-time code>` there (code from the panel, valid 15 minutes, deleted by the bot at once). Only linked chats are ever acted on.

| Feature | Behaviour | Limits and risks |
|---|---|---|
| **Forced channel join** (`spec.gate`) | before anything else the bot asks the messenger whether the customer is a member (`getChatMember`); non-members get a join link + «عضو شدم» | the bot must be an **admin** of the channel; if the check fails the customer is let in and the owner warned once a day; the panel shows whether setup is correct; not applied in the simulator |
| **Referral links** | personal code `r…` → `…?start=<code>`; a brand-new customer arriving through it counts once for the referrer, who is told | self-invites and existing customers never count; the reward is the owner's own text (nothing paid automatically); leaderboard in the customers tab |
| **Anonymous chat** | pairs two waiting customers (even Bale + Telegram); relays text as «👤 …»; end / next / report | text only, ≤500 chars, 20 msgs/min; links, @ids and phone numbers are not relayed; a report stores the last 8 messages for the owner (cleared when a chat ends normally); owner can ban customers; waiting expires after 10 minutes. **The owner is responsible for moderation.** |
| **Post forwarding** | new posts of a linked channel are copied to other linked channels/groups (`copyMessage`) | bot admin in source and destination; rules that would create a loop are refused; Bale↔Telegram text only; **[unverified on a real messenger: whether Bale delivers channel posts to bots]** |
| **Group moderation** | delete messages with links/@ids, forwards or banned words; warnings; ban at N warnings; welcome message; admin commands `/ban` `/unban` `/warns` on replies | admins are never moderated; Bale documents delete (<48 h old), ban, unban but **no mute**; **[unverified on a real messenger: group message delivery on Bale]** |

## 12. Security

- **Auth**: username + password (hashed), JWT (72 h). Usernames are 3–32 characters (`a-z`, digits, `_`, `.`, starting with a letter), case-insensitive; stored in `users.username` (unique). There is no email column: on startup `app/migrate.py` moved older databases from `users.email` to `users.username` (copying each address, so accounts created before usernames sign in by typing their old email), then dropped `email`; the step is idempotent and was rehearsed on PostgreSQL 18; every `/api/bots/{id}/…` route checks ownership (an automated test enumerates all routes from the OpenAPI schema and checks that each one rejects anonymous calls and other users' ids).
- **Secrets**: bot tokens and wallet tokens are encrypted at rest; webhook URLs contain per-bot secrets; shared-bot webhook secret is derived from `JWT_SECRET`; nothing secret is returned by any endpoint (customers lists never include chat ids).
- **Abuse limits**: 8 sign-ups/IP/hour, agent run limits, per-customer FAQ/anon/feedback limits, announcement limits, upload limits (5 MB per file, 25 MB per bot, magic-byte checks for images, extension whitelist for documents), spreadsheet formula-injection neutralised in exports.
- **Customer isolation**: sessions are per bot and customer; owner actions on records verify the record belongs to the owner's bot; `pay:` test-payment buttons exist only in the simulator and tests.
- **Production hygiene**: API docs are disabled in production; webhooks acknowledge quickly and process in the background.

## 13. Testing

| Kind | What |
|---|---|
| Unit/engine | every block, appointments, weekly slots, cancellation/reschedule, catalog flows, discount/pricing, quiz, menus, placeholders |
| Property-style | `test_fuzz.py` drives random hostile conversations against specs and checks invariants (capacity never exceeded, stock never negative, state always storable) |
| Security | route-enumerating authorization matrix, robustness (bad JSON, fake images, oversize input) |
| Integration | Bale/Telegram flows against a fake messenger: shared-bot journey, directory, payments, inbox, announcements, referral, gate, anonymous chat (incl. Bale↔Telegram), linking/forwarding/moderation, outage scenarios (retry, outbox, health, webhook refresh) |
| Mutation checks | key rules were broken on purpose to confirm tests fail (done for cancellation and capacity logic) |
| Agent quality | `scripts/eval_agent.py` against the real model (see `docs/agent-quality-eval.md`) |

Run: `cd api && OPENAI_API_KEY=sk-invalid DATABASE_URL=sqlite:///./test.db .venv/bin/python -m pytest -q` (an invalid key guarantees no credits are spent). Last full run: **273 passed**. Tests do **not** prove behaviour on the real Bale/Telegram servers; that is what `docs/real-bale-checklist.md` is for.

## 14. API surface (70 operations)

Auth `POST /api/auth/register|login`, `GET /api/me`, `GET /api/health`, `GET /api/templates`. Plans `GET /api/plans` (public), `GET /api/me/plan`, `POST /api/me/upgrade`, `POST /api/me/plan/cancel`, admin `GET/POST /api/admin/upgrades…`.
Bots `GET/POST /api/bots`, `POST /api/bots/draft`, `GET /api/bots/{id}`, builder (`POST …/builder`, `GET …/builder/{active|messages|runs/{run}}`), `GET …/versions|tests|cost`, simulator (`POST …/simulate`, `…/simulate/reset`).
Publishing `…/publish|unpublish|publication|listing`, Telegram `…/telegram[/publish|/unpublish]`, wallet `…/payment`, webhooks `POST /api/hook/shared/{secret}`, `/api/hook/own/…`, `/api/tghook/…`.
Owner panel `…/records` (+`PATCH` cancel/status), `…/inbox` (+reply), `…/broadcasts`, `…/scheduled`, `…/customers` (+ban/unban), `…/referrals`, `…/media`, `…/catalog…`, `…/export/{products|records|customers}`, `…/chats`, `…/link-token`, `…/forwards`, `…/gate`, `…/delivery`.

## 15. Deployment and operations

- `./deploy.sh` builds the frontend into `api/static`, sets the environment on the Liara app from `api/.env` (never printing secrets) and deploys the Docker image. Liara allows 20 deployments per day.
- Environment: `DATABASE_URL`, `JWT_SECRET`, `OPENAI_API_KEY`, `BALE_SHARED_BOT_TOKEN`, `PUBLIC_BASE_URL`, `TELEGRAM_RELAY_URL`, `TELEGRAM_RELAY_KEY`, `TELEGRAM_SHARED_BOT_TOKEN`, `BILLING_DEMO`, `ADMIN_USERNAMES`, `CORS_ORIGINS` (see `README.md`).
- Telegram relay: `relay/main.ts` on Deno Deploy (`relay/README.md`).
- Cost evidence: per-call LLM log; UI shows cost per request and per bot.

## 16. Known limits (honest list)

1. **Single instance**: locks and the scheduler are in process; two instances would need database locks and a leader for background jobs.
2. **Unverified on real messengers**: channel post / group message delivery on Bale, multipart file upload format, invoice flow, deep-link payload with referral codes, join check on channels. Telegram paths are tested against a fake relay only.
3. **No password reset or account/data deletion** (accounts have no email to reset through).
4. **No monitoring/alerting or database backup policy** beyond Liara's defaults.
5. **Catalog** loads the whole product list per tap (fine for hundreds of items, untested at thousands); category lists are not paginated.
6. **Agent tests are written by the same agent** that designs the bot: «all tests pass» means the bot matches the agent's understanding; the simulator is where the owner confirms intent.
7. **Dates** are Gregorian in exports; Jalali in conversations.
8. **Plans**: prices are proposals; subscription payment is simulated (demo).
9. **Messages queued during an outage** are dropped after 30 minutes (deliberate: a very late confirmation confuses customers).
10. **Anonymous chat** keeps a short log only for reports; moderation of reports is the owner's job.
