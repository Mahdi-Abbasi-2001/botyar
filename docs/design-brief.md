# Botyar (بات‌یار) — Design Brief

## Product in one paragraph
Botyar lets a small-business owner in Iran **describe a chat bot in Persian**; an AI agent asks clarifying questions, builds the bot, writes and runs its own tests, and (soon) publishes it to the Bale messenger. Later the owner describes a change in plain words; the agent applies it, shows a diff, and re-runs all earlier tests. Tagline idea: «بگو چی می‌خوای، ربات رو می‌سازم.»
Competition judges score UI/UX out of 25 and will click through the live product: sign-up → build a bot → see it tested → try it → change it. The "agent at work" moments are what make the product feel alive; design them with care.

## Users
Café / workshop / clinic / gym owners. Non-technical, phone-first habits, Persian only, short attention. They should never see JSON, ids or jargon. Tone: warm, simple, confident ("یار" = companion).

## Hard constraints
- **Persian, RTL**, font Vazirmatn (self-hosted, already in the project). Persian digits for numbers in UI text where natural; keep button *data values* untouched.
- Tech: Next.js 16 static export + Tailwind CSS 4, served by the FastAPI backend (same origin). No server components with data fetching, no SSR. Auth token lives in localStorage.
- Responsive: must work on a phone (owners) and a laptop (judges).
- Keep every API call and its JSON shape (listed below). Redesign freely: layout, components, copy, motion, empty/loading/error states.
- Accessibility: contrast AA, focus states, buttons ≥ 44px on mobile.

## Screens (current routes)
1. **Landing `/`** — hero, how it works (4 steps), CTA to sign up. Needs: a short live-demo feel (e.g. an animated chat that shows a bot being built), trust line, pricing teaser optional.
2. **Auth `/login/`** — one screen, toggles register/login. Email + password only (no forgot-password). States: loading, wrong password (401 «ایمیل یا رمز عبور اشتباه است»), email taken (409).
3. **My bots `/bots/`** — primary CTA «ساخت ربات جدید با توضیح دادن»; secondary: start from 2 templates (workshop booking, café ordering); list of bots (name, version). Empty state for first-time users.
4. **Bot workspace `/bot/?id=N`** — the main screen. Two zones:
   - **Left/top: Chat simulator** (phone-like): messages from the bot, inline buttons under bot messages, text input, "restart" button; admin notifications appear as a distinct amber bubble «🔔 اعلان به مدیر». Visible only after the first version exists.
   - **Right/bottom: tabs**
     - **ساخت با ایجنت (Builder)** — chat with the agent. While the agent works (20–40 s) show **live progress steps** (events list, see below), failed tests in red then "fixing…", then success. Show per-request AI cost (tiny, e.g. $0.0012) as a subtle trust/transparency detail. Example prompts as chips for new users.
     - **ساختار (Structure)** — human-readable cards of the bot: welcome message, menu, each block (message / form / booking with slots+capacity / order with items+prices / admin-notify). Not JSON.
     - **تست‌ها (Tests)** — list of scenarios with ✓/✗, failure reasons, expandable transcript (user line ↔ bot line). This is the proof the bot works; make it feel like evidence, not a log dump.
     - **نسخه‌ها (Versions)** — timeline: version number, the request that created it, tests passed/total, and a **readable diff** (what changed: e.g. "لیست انتظار: غیرفعال ← فعال"). Currently shown as raw paths; needs a human-friendly rendering.
     - **ثبت‌ها (Records)** — table/cards of bookings/orders created in the simulator (and later from the real Bale bot).
     - Added since this brief was written (functional, not yet designed): **انتشار** (Bale/Telegram publishing, links/QR, wallet token for payments), **محصولات** (catalog import), **پیام‌ها** (inbox), **اطلاعیه** (announcements, scheduled announcements), **مشتریان** (list, search, export, referral leaderboard, ban), **فایل‌ها** (photos/files for message blocks), **کانال و گروه** (link code, forwarding rules, moderation settings, join-gate status), an amber **delivery banner** when a messenger is unreachable, and the pages **/pricing** (plans) and **/account** (usage meters, demo upgrade, payment history).
5. **(Next, design now so it fits) Publish screen** — connect to Bale: paste bot token OR use the shared Botyar bot with a short code; shows status and a link/QR. Plus a "live records" view with real users.

## Agent progress events (real strings the UI receives, in order)
«در حال بررسی درخواست شما…» → «در حال طراحی ساختار ربات…» → «در حال نوشتن سناریوهای تست…» → «اجرای N تست روی ربات…» → «K تست ناموفق بود» + «✗ <test name>: <reason>» → «ایجنت در حال رفع خطاهای تست (دور N)…» → «همه تست‌ها موفق بود ✅» → «نسخه V ذخیره شد (P/T تست موفق)».
Run statuses: `running`, `needs_input` (agent asked questions — they appear as an assistant message starting with ❓), `done`, `failed`.

## Real sample data (use for mockups)
- Bot: «ربات نوبت‌دهی کلینیک دندانپزشکی», version 2, tests 5/5, AI cost $0.0019 total.
- Owner request: «برای کلینیک دندانپزشکی‌ام ربات نوبت‌دهی می‌خوام. دو زمان دارم: شنبه ساعت ۹ صبح و دوشنبه ساعت ۵ عصر، ظرفیت هر کدوم ۸ نفر. نام و شماره موبایل بیمار رو بگیر و ثبت نوبت که شد به من اطلاع بده.»
- Change request: «وقتی ظرفیت یک زمان پر شد، بیمار بتونه تو لیست انتظار ثبت بشه»
- Test names: «ثبت موفق نوبت شنبه», «رد موبایل نامعتبر و ثبت پس از اصلاح», «ظرفیت تکمیل‌شده شنبه»
- Bot message example: «سلام! به کلینیک دندانپزشکی خوش آمدید.» with menu button «دریافت نوبت»; slot buttons «شنبه ساعت ۹ صبح (۸ جای خالی)».

## API (unchanged contract)
POST /api/auth/register|login {email,password} → {token}
GET /api/bots → [{id,name,version}] · POST /api/bots/draft · POST /api/bots {template}
GET /api/bots/{id} → {id,name,version,spec}
POST /api/bots/{id}/simulate {session_id,text} → {actions:[{type:"send",text,buttons:[{text,data}]}|{type:"notify_admin",text}]}
POST /api/bots/{id}/simulate/reset
POST /api/bots/{id}/builder {text} → {run_id} · GET /api/bots/{id}/builder/runs/{run} → {status,events[],result{message,version,diff[],tests[],cost_usd}}
GET /api/bots/{id}/builder/messages · /tests · /versions · /cost · /records?sandbox=true

## What success looks like
A judge with no context understands in 10 seconds what it does, builds a bot in under a minute without reading anything, trusts the result because the tests are visible, and is impressed by the change → diff → re-test loop.
