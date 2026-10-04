# بات‌یار (Botyar)

**بگو چی می‌خوای، ربات رو می‌سازم.** صاحب کسب‌وکار ربات بله‌اش را به فارسی توضیح می‌دهد؛ ایجنت ابهام‌ها را می‌پرسد،
ربات را می‌سازد، خودش برایش تست می‌نویسد و اجرا می‌کند، نسخه‌ی تست‌شده را روی بله منتشر می‌کند، و هر تغییری که بعداً
خواسته شود را با نمایش تفاوت‌ها و اجرای دوباره‌ی همه‌ی تست‌ها اعمال می‌کند.

- نسخه‌ی آنلاین: https://botyar.liara.run
- ربات مشترک بله: `@botyar_ai_bot` (مشتری کد ۶حرفی ربات را می‌فرستد). همان ربات را می‌شود روی تلگرام هم منتشر کرد.
- راهنمای آزمودن قدم‌به‌قدم: [`docs/TEST-TOUR.md`](docs/TEST-TOUR.md)

مسئله‌ی انتخاب‌شده در رویداد BuildX: **۳ — سازنده و نگه‌دارنده‌ی ربات بله/تلگرام.**

---

## How it works

```
 Owner's browser ──► Static UI (Next.js export) ──► FastAPI ──► PostgreSQL
                                                     │
                     ┌───────────────────────────────┤
                     ▼                               ▼
          BUILDER AGENT (LangGraph)          RUNTIME ENGINE (no LLM)
          clarify → design → validate →      executes the published BotSpec and
          write tests → run tests →          answers every customer message
          repair (≤3) → save version         deterministically
                     │                               ▲
                     ▼                               │ webhooks
                OpenAI API                    Bale (customers + owner)
```

1. **The agent never writes code.** It writes a **BotSpec**: Pydantic-validated JSON assembled from a fixed set of
   blocks: message, form, booking (fixed or weekly slots, or appointment calendars from working hours), catalog order,
   FAQ, contact the owner, feedback, admin notify.
2. **Customers never talk to a language model.** A deterministic engine runs the spec, so a live bot behaves the same
   every time, can't be prompt-injected and costs almost nothing per message. (FAQ free-text questions use one small
   embeddings lookup against the owner's own sentences; answers are never generated.)
3. **Every version is tested before it can be published.** The agent writes test conversations, the engine runs them,
   failures go back to the agent for repair, and publishing stays locked while any test fails. A change request
   produces a readable diff and re-runs all earlier tests.

Models: `gpt-6-luna` for every agent step (owner decision, cost), `text-embedding-3-small` for FAQ matching. Every call
is logged with its token count and cost; the UI shows the cost per request and per bot.

## Repository layout

| Path | What |
|---|---|
| `api/app/spec.py` | BotSpec schema (the blocks and their validation) |
| `api/app/engine.py` | Runtime engine: all bot behaviour, shared by simulator, tests and Bale |
| `api/app/agent.py`, `api/app/prompts.py` | LangGraph builder agent and its prompts |
| `api/app/testing.py` | Test runner and spec diff |
| `api/app/llm.py` | The single LLM entry point (model, pricing, cost log) |
| `api/app/bale.py`, `api/app/publish.py` | Messenger glue shared by Bale and Telegram; Bale publishing and webhooks |
| `api/app/telegram.py`, `relay/` | Telegram channel and the Deno relay it goes through (Telegram is unreachable from Iran) |
| `api/app/catalog.py`, `api/app/export.py` | Product catalogs, CSV/Excel/paste/photo/PDF import, CSV/XLSX export |
| `api/app/faq_index.py`, `api/app/faq_match.py` | FAQ retrieval (embeddings) |
| `api/app/outreach.py`, `api/app/payments.py`, `api/app/records_ops.py` | Reminders, announcements, Bale invoices, owner actions on records |
| `api/tests/` | Backend tests (no network, no OpenAI) |
| `web/` | Next.js frontend (static export, Persian RTL) |
| `docs/` | Test tour, agent and FAQ evaluations, design brief, sample import files |
| `build.sh`, `deploy.sh` | Build the frontend into `api/static`; deploy to Liara |

## Run it locally

Requirements: Python 3.12+, Node 22+.

```bash
# backend
cd api
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cat > .env <<'EOF'
OPENAI_API_KEY=sk-...          # needed only for the builder agent, catalog photo import and FAQ matching
JWT_SECRET=change-me-to-a-long-random-string
EOF
.venv/bin/uvicorn app.main:app --port 8000
```

```bash
# frontend: build once and let the backend serve it on the same origin
./build.sh            # from the repo root; writes web/out into api/static
```

Open http://localhost:8000. Without `DATABASE_URL` the backend uses SQLite (`api/dev.db`). Without `PUBLIC_BASE_URL`
no Bale webhooks are registered, so publishing works only in the deployed app; the web simulator works everywhere.

For frontend work with hot reload, run `npm run dev` in `web/` with `NEXT_PUBLIC_API_BASE=http://localhost:8000`
(the backend allows `http://localhost:3000` by default).

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./dev.db` | PostgreSQL in production |
| `JWT_SECRET` | dev value | Signs login tokens; also derives the key that encrypts stored Bale tokens |
| `OPENAI_API_KEY` | – | Agent, vision import, FAQ embeddings |
| `BALE_SHARED_BOT_TOKEN` | – | Token of the shared @botyar_ai_bot |
| `PUBLIC_BASE_URL` | – | Public URL used to register Bale webhooks |
| `TELEGRAM_RELAY_URL`, `TELEGRAM_RELAY_KEY` | – | The Telegram relay outside Iran (see [`relay/README.md`](relay/README.md)); empty = Telegram off |
| `TELEGRAM_SHARED_BOT_TOKEN` | – | Optional shared Telegram bot (same codes as the shared Bale bot) |
| `CORS_ORIGINS` | `http://localhost:3000` | Only needed when the UI runs on another origin |

### Spending guards

40 agent runs per user per 24 h, 300 agent runs and 300 AI-assisted imports per 24 h across all users, 8 sign-ups per
IP per hour. A typical bot costs about $0.002 to build (`docs/agent-quality-eval.md`).

## Tests

```bash
cd api
OPENAI_API_KEY=sk-invalid DATABASE_URL=sqlite:///./test.db .venv/bin/python -m pytest -q
```

Setting an invalid key on purpose guarantees the suite cannot spend OpenAI credits. Agent quality is measured
separately against the real model; see `docs/agent-quality-eval.md` and `docs/faq-evaluation.md`.

## Deploy

`./deploy.sh` builds the frontend, sets the environment on the Liara app `botyar` from `api/.env`
(`PROD_DATABASE_URL`, `OPENAI_API_KEY`, `BALE_SHARED_BOT_TOKEN`, `JWT_SECRET`) and deploys the Docker image. It never
prints secrets.
