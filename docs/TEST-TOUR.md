# Botyar — Test Tour (learn the product by trying to break it)

Live site: https://botyar.liara.run · Shared bot on Bale and Telegram: **@botyar_ai_bot** · Sample files: `docs/samples/`

How to use this: go station by station. Each station says **what it is**, **how it works**, **what to do**, **what you
should see**, and **how to try to break it**. Write down anything that surprises you — a surprise is either a bug or a
gap in our explanation, and both are worth fixing.

---

## 0. The system in one minute

```
 Owner's browser ──► Static UI (Next.js) ──► FastAPI backend ──► Postgres (Liara)
                                                  │
              ┌───────────────────────────────────┤
              ▼                                   ▼
   BUILDER AGENT (LangGraph)               RUNTIME ENGINE (no AI)
   clarify → design → validate →           reads the bot's published BotSpec (JSON)
   write tests → run tests → repair →      and answers every customer message
   save a version                          deterministically
        │  uses only gpt-6-luna                   ▲
        ▼                                         │ webhook
   OpenAI API                 Bale and Telegram (customers, owner)
```

Three ideas to hold on to:

1. **The agent never writes code.** It writes a **BotSpec** (a JSON description built from a fixed set of blocks: message,
   form, booking, catalog_order, FAQ, contact, feedback, sub-menu, quiz, referral, anonymous chat, admin_notify, plus an
   optional forced channel join). A fixed engine executes it. That is why bots are safe, testable and diff-able.
2. **Customers never talk to an AI.** Their messages go to the deterministic engine. So a running bot costs no OpenAI
   money, cannot be prompt-injected, and behaves the same every time. AI is used only to *build and change* bots.
3. **Every version is tested before it can be published.** The agent writes test conversations, the engine runs them,
   failures go back to the agent for repair (max 3 rounds). Publishing is blocked while any test fails.

Where things live (for when you want to read the code):

| Part | File |
|---|---|
| BotSpec schema (all blocks) | `api/app/spec.py` |
| Runtime engine (all bot behaviour) | `api/app/engine.py` |
| Agent graph + prompts | `api/app/agent.py`, `api/app/prompts.py` |
| Test runner + spec diff | `api/app/testing.py` |
| LLM calls + cost log (Luna only) | `api/app/llm.py` |
| Bale + Telegram channel (webhooks, buttons, editing) | `api/app/bale.py`, `api/app/publish.py`, `api/app/telegram.py` |
| Outages (retries, queue, health, webhook refresh) | `api/app/resilience.py`, `outbox.py`, `webhooks.py` |
| Plans and limits | `api/app/billing.py` |
| Channels, groups, join gate, invite links, anonymous chat | `api/app/communities.py`, `gate.py`, `referral.py`, `anon.py` |
| Product catalog + imports | `api/app/catalog.py` |
| Exports (CSV/XLSX) | `api/app/export.py` |
| UI | `web/app/*`, `web/components/workspace/*` |

The full description of the system is in `docs/technical.md`; what must still be tried on real Bale/Telegram accounts is in `docs/real-bale-checklist.md`.

---

## Station 1 — Sign up / log in

**What it is:** username + password accounts (accounts made earlier with an email sign in with that email); a login token (JWT, 72 h) kept in the browser.
**Do:** register; log out; log in; try a wrong password; register the same username again (also in capitals); try usernames like `ab`, `1abc`, `علی` or `a b`; use a 5-character password.
**Expect:** Persian error messages; no crash.
**Break it:** register 9 accounts quickly from one network → the 9th is refused (limit: 8/hour/IP). Open
`/bots/` in a private window → sent to login. Edit the token in DevTools → sent to login.
**Why it works this way:** the sign-up limit stops someone from creating thousands of accounts to burn the OpenAI budget.

## Station 2 — Describe a bot, watch the agent

**What it is:** the core of the product. One message in, a tested bot out (typically 12–45 s, about $0.002).
**Do (vague request):** type `یه ربات برای باشگاهم می‌خوام` → the agent should ask up to 3 questions as cards.
Answer them → watch the live timeline (clarify → design → tests → run → repair → save).
**Do (complete request):** `برای آرایشگاه زنانه‌م ربات نوبت‌دهی می‌خوام. سه ساعت: ۱۰، ۱۲ و ۴، هر ساعت ۲ نفر. اسم و شماره بگیر و به من خبر بده.`
**Expect:** a bot with one booking block, 3 time slots, a notification block; 3 or so green tests; the cost shown at the top.
**Break it:**
- Ask for something unsupported: `رزرو با پرداخت آنلاین و یادآوری پیامکی` → it must say so in the assumptions and build the closest bot, not pretend.
- Gibberish, English, a 3000-character essay, empty-ish text.
- Press send twice quickly / use two tabs → second request is refused ("agent still working").
- **Refresh the page in the middle of a build** → the progress view should come back and finish by itself.
- Watch for a bot that *looks* fine but isn't what you asked for. That is the main weakness (see "Known gaps": the tests are written by the same agent).

## Station 3 — The Tests tab (what "tested" really means)

**What it is:** each test is a scripted customer conversation + expectations (text the user sees, records created).
Open one and read the transcript. **Expect** to understand exactly what was checked.
**Ask yourself:** *would I have written this test?* Did it check capacity? invalid phone numbers? If a case you care
about is missing, tell the agent in the builder ("add a test for …") and see whether it does.

## Station 4 — The simulator ("امتحانش کن")

**What it is:** the same engine the real Bale bot uses, with a fake chat window. Sandbox data only (never touches live records).
**Do:** book a seat; give a bad phone (`123`) then a good one; type Persian digits (`۰۹۱۲۳۴۵۶۷۸۹`); type `انصراف` mid-flow;
fill a slot to capacity and try once more; press "restart".
**Expect:** slot counts show Persian digits («۱۰ جای خالی»); a full slot is marked and refused; the owner notification
appears as an amber bubble.
**Break it:** send `<script>alert(1)</script>`, a 2000-char message, emoji, `p:99999`, `n:-5`.

### Station 4b — Weekly classes and capacity that resets by itself (new)

**What it is:** a slot can be *weekly* («هر شنبه ساعت ۸ صبح»). The bot then offers the next two real dates with their Jalali dates and counts capacity **per date**, so the class is bookable again the week after it has happened. A slot for a specific date («فقط ۲۵ مهر») stays a one-off with lifetime capacity.
**Do:** describe `کلاس یوگا هر شنبه ساعت ۸ صبح ظرفیت ۱۰ نفر و پیلاتس هر سه‌شنبه ساعت ۶ عصر ظرفیت ۱۲ نفر`. In the simulator you should see buttons like «یوگا، شنبه ساعت ۸ صبح — ۱۴۰۵/۰۷/۱۸ (۱۰ جای خالی)» for two upcoming dates per class.
**Expect:** booking one date lowers only that date's count; the Structure tab shows «هر هفته · شنبه ساعت 08:00»; the Records tab groups bookings per date; exports have a date column.
**Migrate an old bot:** open a bot with lifetime slots and say `این سانس‌ها هر هفته تکرار می‌شوند؛ ظرفیت برای هر هفته جدا شمرده شود` → the diff should change only `weekday`/`time` on each slot. (Bookings made before the change have no date, so they stop counting — the capacity starts fresh.)
**Break it:** book at the very end of the day before a class; ask for «هر دو هفته یک‌بار» (not supported — the agent should say so honestly instead of faking it); mix a weekly class and a one-off event in one bot.

### Station 4b2 — Appointment calendars from working hours (new)

**What it is:** for salons, clinics, tutors, consultants. The owner gives working days and hours, how long one appointment takes, an optional lunch break and optional staff. The bot generates the bookable times; capacity is counted **per staff member, per date, per time**. (Fixed classes/events still use *slots*, above.)
**Do:** describe `آرایشگاه زنانه با دو آرایشگر سارا و مینا. شنبه تا چهارشنبه ۹ تا ۶، هر نوبت ۶۰ دقیقه، ساعت ۱ تا ۲ ناهار`. In the simulator you should be asked «با چه کسی؟», then see the next working days («یکشنبه ۱۴۰۵/۰۷/۱۲ (۸ نوبت خالی)»), then the times with the lunch hour missing.
**Expect:** a time you book disappears for that stylist but stays free for the other; times that already started are never offered; a long day pages its times (8 per page, edited in place); booking the same time from two phones leaves the second customer with "someone just took it" and the time list again.
**Break it:** book the last free time of a day (the day disappears); ask for 2 customers at once («ظرفیت ۲ نفر همزمان»); ask for appointments AND a group class in one bot (the agent should create two booking blocks).

### Station 4e — FAQ bot: customers ask in their own words (new)

**What it is:** a `faq` block answers common questions with the owner's EXACT text (nothing is generated). Customers tap a question, or type it in their own words; the bot finds the closest entry (embeddings), asks "did you mean…?" when unsure, and logs what it cannot answer for the owner.
**Do:** describe `ربات پرسش‌های متداول برای کلینیک: ساعت کاری شنبه تا چهارشنبه ۹ تا ۱۸، آدرس خیابان ولیعصر پلاک ۱۲، ویزیت ۲۵۰ هزار تومان، پارکینگ داریم`. In the simulator type: «کجا هستید؟», «چنده ویزیت؟», «جای پارک دارید؟» — then something unrelated: «قیمت طلا امروز چنده».
**Expect:** the first three return the owner's sentences; the last says it could not find an answer, offers the question list, and appears in the **ثبت‌ها** tab as «بدون پاسخ» with a «رسیدگی شد» button (and a notification on Bale if you linked `/admin`).
**Break it (important):** ask the agent for an FAQ and give it NO facts, then keep saying «خودت تصمیم بگیر». It must never invent hours/prices/addresses — it should ask, and when finally forced it writes «اطلاعات … هنوز ثبت نشده است». Also try questions in slang, with typos, in English, and very long text.
**Honest numbers:** see `docs/faq-evaluation.md` — about 63% answered at once, ~90% right within one tap, rare wrong answers (0–1% in our samples).

### Station 4f — Talk to the owner, ratings, rescheduling, reminders, announcements, delivery/discounts, payment (new)

Try each in a fresh bot (describe it to the agent in Persian, one sentence each). Prices/times below are just examples.

1. **Talk to the owner.** «ربات فروشگاه گل که مشتری‌ها بتوانند برای من پیام بفرستند». In the simulator pick «پیام به مدیر», type a message → you get «پیام شما ارسال شد». Open the **پیام‌ها** tab (check «فقط آزمایشی») → reply. On Bale (after publishing): the reply arrives in the customer's chat as «✉️ پاسخ مدیر».
2. **Ratings.** «بخش ثبت نظر مشتری با ستاره ۱ تا ۵». Tap ⭐⭐⭐⭐, write a comment (or «رد کردن»). The structure tab shows the average; the same customer can rate at most 5 times a day.
3. **Reschedule.** In a bot with appointments: book, open «نوبت‌های من», pick the booking → «🔄 تغییر زمان», choose another time. The old place is freed only after the new one is confirmed; a full date is refused (you keep the old one).
4. **Reminders.** Ask for «۲۴ ساعت قبل از نوبت یادآوری بده». Can't be seen in the simulator (it needs a real clock and a Bale chat); check the booking card says «یادآوری ۲۴ ساعت قبل». The server sends one message per booking; a booking made inside the window gets none.
5. **Announcements.** Tab **اطلاعیه** (bot must be published): write text → preview → send. Customers who sent /stop are skipped; max 3 per day; every announcement ends with the /stop hint.
6. **Delivery fee + discount codes.** «هزینه ارسال ۳۰ هزار تومان، رایگان بالای ۲۰۰ هزار، کد YALDA ده درصد، حداکثر ۵ بار». At checkout the bot asks «کد تخفیف دارید؟»; try a wrong code, the right code in lowercase, and cancel an order to see the use come back.
7. **Online payment.** «سفارش را آنلاین پرداخت کنند». In the simulator, after the last question you get a bill and a «💳 پرداخت (آزمایشی)» button; the owner notification arrives only after paying; an unpaid order is cancelled after 15 minutes. In the **انتشار** tab save the wallet token `WALLET-TEST-1111111111111111` (Bale's published test token) to try a real invoice on the shared bot with no real money. Real money needs your OWN bot token + your own wallet token from @botfather.

### Station 4g — Plans, customers, files, map pins, scheduled announcements, sub-menus, quizzes (new)

1. **Pricing and limits.** Open `/pricing/` (also linked from the landing page and the bots header): four plans, prices marked «پیشنهادی». Open `/account/` (پلن و مصرف): usage meters for bots, live bots, agent requests (30 days) and active customers per live bot. On the free plan, try to create a 4th bot: you get a clear 402 message with «ارتقا». Press «پرداخت آزمایشی و فعال‌سازی»: the payment is simulated (no money moves), the plan activates at once, the limits change immediately and a «پرداخت آزمایشی» row appears in the payment history; «لغو اشتراک» returns to the free plan.
2. **Customers tab (مشتریان).** After a customer talks to a published bot: name, messenger, first message, last activity, message count, search, Excel/CSV export. The chat id is never shown.
3. **Photo/file.** Ask: «دکمه دریافت کاتالوگ که فایل PDF کاتالوگ رو بفرسته». A «فایل‌ها» tab appears: upload a PDF (≤5 MB). In the simulator the bubble shows «📎 فایل: name.pdf»; on Bale the real file arrives.
4. **Map pin.** Ask with coordinates: «دکمه آدرس که لوکیشن بفرسته. مختصات: 35.7219 و 51.3347». Without coordinates the agent must say it needs them (it never invents them).
5. **Scheduled announcements.** Tab «اطلاعیه» → «اطلاعیه‌ی زمان‌بندی‌شده»: once at a date/time or every day at HH:MM (Tehran). Counts toward the 3-per-day announcement limit.
6. **Sub-menus.** «دکمه محصولات که دو دکمه لپ‌تاپ و موبایل نشون بده، هرکدوم توضیح خودش را بگوید».
7. **Quiz.** Give the questions and correct answers yourself; the agent asks for them if you don't. A score appears at the end and each result is stored.
8. **Random message / personalised confirmation.** «با زدن دکمه، هر بار یک جمله انگیزشی تصادفی نشان بده» and «اسمم رو بپرس و بعدش با اسم خوش‌آمد بگو».

### Station 4h — Channels, groups, forced join, invite links, anonymous chat, outages (new)

All of these need a real messenger; use `docs/real-bale-checklist.md` (sections C–F) for the exact steps. In the web simulator you can only see how the blocks read:
1. **Forced join**: «مشتری‌ها باید اول عضو کانال @yourchannel بشن». The Structure tab shows a «عضویت اجباری» card; the «کانال و گروه» tab shows whether the bot is an admin of that channel. The simulator does not apply the gate.
2. **Invite friends**: the referral block shows «دعوت‌های موفق: ۰ از N» and a note that the real link exists only on Bale/Telegram.
3. **Anonymous chat**: the simulator explains that pairing needs two real customers.
4. **Channels and groups tab**: «دریافت کد اتصال» gives `/link CODE`; post forwarding and group moderation settings appear after a chat is linked.
5. **Outages**: if Bale/Telegram is unreachable the workspace shows an amber banner (messenger down, messages queued, messages lost in 24 h). Unreachable messenger → messages wait in a queue for up to 30 minutes.
6. **Plans (demo)**: `/pricing/` and `/account/` — upgrading simulates a payment and activates the plan at once.

### Station 4c — Customers cancelling («سفارش‌های من» / «نوبت‌های من») (new)

**What it is:** when a booking or order block allows it (the agent turns it on by default; say «مشتری نتونه لغو کنه» to turn it off), the bot's menu gets a built-in last button **«ثبت‌های من»**. The customer sees only their OWN active bookings/orders, taps one, confirms, and it is cancelled.
**Rules to check:** a cancelled booking frees its place; **the first person waiting for the SAME date is promoted and gets a message** (and the owner gets ❌ and ✅ notifications); a deadline («تا ۲۴ ساعت قبل») blocks late cancels; an order can only be cancelled for a short window after it is placed (default 30 min) and its stock goes back on the shelf; past classes are not listed.
**Do:** in the simulator book a one-seat class, then in the same bot from another session (or a second phone on Bale) join the waitlist; cancel the first booking; watch the second customer get the 🎉 message. In the simulator that message is shown as a dashed «📨 message to another customer» note.
**Break it:** press an old confirm button twice; cancel after the deadline; try to cancel with someone else's chat (impossible by design — ids from the button are re-checked against the customer's identity on the server).
**Not included:** *editing* a booking (the agent says so and offers cancel + rebook), refunds/payments, owner-side cancelling.

### Station 4d — The owner managing orders and bookings (new)

**What it is:** in the **ثبت‌ها** tab (preview data) and under **انتشار → ثبت‌های واقعی** (real customers) every open record has action buttons.
**Orders:** `new → preparing → ready → done`. The customer is messaged at «در حال آماده‌سازی» and «آماده»; closing an order sends nothing. **Once an order is preparing the customer can no longer cancel it** and sees its status under «ثبت‌های من».
**Cancelling (booking or order):** with an optional reason that is sent to the customer. Cancelling a confirmed booking frees the place and promotes the first person waiting for the same date; cancelling a table-catalog order puts the stock back.
**Do (needs two Bale accounts):** order from your phone, then in the app press «شروع آماده‌سازی» → your phone should receive a message. Then press «لغو» with a reason → the reason arrives, the stock goes back (check the products tab).
**Break it:** try to move a finished order again (refused), cancel twice (refused), correct a mistake by going backwards (allowed, but the customer is not messaged again), act on a record while a customer books at the same moment (they are serialised by a per-bot lock).
**Honest limits:** messages only reach customers who use the Bale bot (not simulator customers, and not customers who blocked the bot); records made before cancellation existed have no customer identity, so they can be cancelled but nobody can be messaged.

## Station 5 — Change request, versions, diff, regression

**What it is:** the "maintain" half of the product.
**Do:** after station 2 say `وقتی ظرفیت پر شد، لیست انتظار هم بذار`. Open **Versions**.
**Expect:** version 2 with a diff such as `waitlist: false → true`; old tests re-run as regression and still pass
(or the agent explains why one changed).
**Break it:** ask for two unrelated changes at once; ask to *remove* a feature; ask for a change that contradicts a test.
Check that nothing *else* changed in the diff — the agent regenerates the whole spec, so unintended edits are the risk.

## Station 6 — Publish to Bale (shared bot)

**What it is:** the **انتشار** tab. Shared mode = your bot lives inside @botyar_ai_bot; you get a link
(`ble.ir/botyar_ai_bot?start=<code>`) and a QR that open it directly (verified on Bale Web and the phone app). A customer
who opens @botyar_ai_bot without a link gets a paged **directory** of the businesses there (owners can hide theirs with
the «نمایش در فهرست» checkbox; the link keeps working). Typing a code as a message does nothing on purpose.
**Do:** publish → scan the QR with your phone → book a seat. Then `/switch` → the directory → pick your bot again. Then send `/admin <your admin code>` from your
own chat and book again from a second account/phone.
**Expect:** buttons appear as inline buttons; **"next page" edits the same message** (catalog bots); the owner gets a
🔔 notification with the customer's name and phone; the booking appears under *live records* in the app.
**Break it:** send a photo/sticker (→ polite "text only"); add the bot to a group (ignored); `/switch` to change bot;
republish a changed version **while a customer is mid-booking** → the customer gets "the bot was just updated, let's start over" and a menu (this used to be silence).

## Station 7 — Own bot token (NOT yet tested on real Bale)

**Do:** create a second bot with `@botfather` on Bale, paste its token in the publish tab.
**Expect:** the token is validated; the webhook is registered; your bot username appears; the bot answers.
**This is the biggest unverified feature — please test it and report exactly what you see.**

## Station 7b — Telegram, through the relay (new, NOT yet tested on real Telegram)

**What it is:** the same bot, also live on Telegram. Telegram is unreachable from Iranian servers (checked from the
Liara container), so every call goes through `relay/main.ts` on Deno Deploy. Setup: `relay/README.md`.
**Do:** after the relay is deployed and `./deploy.sh` has run with `TELEGRAM_RELAY_URL`, open **انتشار** → the
Telegram card → publish (shared bot, or your own token from Telegram's @BotFather). Open the `t.me/<bot>?start=<code>`
link on a phone with Telegram, book a seat, send `/admin <code>` from your own Telegram account.
**Expect:** the link opens your bot directly (a Telegram-only customer can also pick it from the shared bot's directory); the booking appears in the same records; the owner notification arrives
on Telegram; an announcement reaches customers on both messengers; no pay button on Telegram (payments are Bale only).
**Break it:** book the last seat on Bale and join the waitlist on Telegram, then cancel on Bale: the Telegram customer
must get the «freed place» message on Telegram. Stop the relay (or put a wrong `RELAY_KEY` on Deno): Bale must keep
working and the Telegram publish button must give a clear error instead of hanging.

## Station 8 — Shops with a catalog

**What it is:** when a store has many products, the agent uses a **database table** instead of putting products in the spec.
**Do:** describe a clothing shop (`فروشگاه پوشاک با چند صد لباس مردانه و زنانه، فایل اکسل رو بعدا آپلود می‌کنم`).
It builds a demo catalog of ~8 sample products so the bot works immediately. Open **محصولات** and import:
- `docs/samples/messy-store.csv` — title line above the header, prices in **rial**, code column, sizes/colors packed in cells.
- `docs/samples/tricky-paste.txt` — copy-paste it into the box: thousand-toman prices, a size *range* (`۴۰ تا ۴۴`), a row with no price, and a cell starting with `=` (spreadsheet formula injection).
- `docs/samples/price-list.jpg` — a photo of a price list (vision). **Review the preview carefully**: small text is sometimes misread.
**Expect:** a preview table before anything is saved; size ranges expanded to ۴۰، ۴۱، …؛ rows without price skipped with a warning; demo products replaced.
Then in the simulator: categories → 5 products per page → next/previous → pick a product → size → color → quantity → cart → checkout.
**Break it:** add the same limited-stock product twice (it must refuse beyond stock); order the last item from two phones at once; search with `ي`/`ی` variants.

## Station 9 — Records and exports

**Do:** open **ثبت‌ها** (sandbox) and the live records in **انتشار**; download Excel and CSV.
**Expect:** Persian headers; the phone number keeps its leading zero in Excel; order lines are readable; a customer name starting with `=` is neutralised.
**Round trip:** export products as CSV and import that same file again — it should work (that is your backup/restore).

## Station 10 — Try to break the security

You do not need special tools:
1. While logged in as user A, copy a bot URL (`/bot/?id=3`). Log in as user B and open it → "not found". (Automated: every route is checked.)
2. Open `https://botyar.liara.run/docs` → 404 (the API schema is not published).
3. In DevTools → Network, replay a request without the `Authorization` header → 401.
4. Look at `/api/hook/shared/anything` → 404. The real webhook URL contains a secret because Bale cannot sign requests.

---

## Bug log from the systematic hunt (all fixed, each has a regression test)

| # | Found by | Problem | Impact |
|---|---|---|---|
| 1 | random-conversation fuzzing | same limited-stock product added twice in one cart → stock went **negative** | overselling |
| 2 | scenario test | owner republishes while a customer is mid-flow → engine crashed on the old state | customer got **silence** |
| 3 | scenario test | an agent run killed by a restart stayed "running" → every new request answered "agent busy" | bot **permanently locked** |
| 4 | garbage uploads | fake image / empty PDF → HTTP 500 | confusing failure |
| 5 | oversized input | catalog commit accepted 5000-char names; Postgres would reject them (500) | failed import |
| 6 | malformed input | webhook with invalid JSON → 500 | noisy errors |
| 7 | review | `/docs` and the full API schema were public in production | needless exposure |
| 8 | manual check | refreshing mid-build lost the live progress | looked like the agent never answered |
| earlier | tests | chat state saved with a shallow copy → two consecutive option questions lost their place; Persian-digit sizes (`۴۲`) never matched their button | products with size+colour could not be ordered |

## Known gaps and improvement ideas (honest, roughly by value)

0. ~~Weekly capacity never reset~~ — **fixed**: weekly slots count per date (see Station 4b). Still open: "every other week", month-based schedules, and clearing old one-off bookings by hand.
1. ~~Customers can't cancel~~ — **done** (Station 4c). Customers can now *reschedule* a booking; editing the items of an order is still not supported (cancel and re-order). (Owner-side cancel and the order preparing status are done — Station 4d.)
2. **Self-graded tests.** The agent that designs the bot also writes its tests. Idea: show the owner a plain-language "what I understood" summary to confirm *before* building; add a second "reviewer" pass.
3. **Category lists aren't paginated** (a store with 40 categories shows 40 buttons; Bale's limit is unknown). Product lists reload the whole catalog per tap — fine for hundreds of items, untested for thousands.
4. **Single server instance.** The anti-double-booking lock and the background jobs live in memory, so we cannot run two instances without moving locks into the database. No uptime monitoring/alerts; database backup policy unverified.
5. **No password reset, account/data deletion.** (Out of competition scope, needed for a real product.)
6. **Dates are Gregorian in exports** (conversations use Jalali). Telegram exists (through a relay) but is tested against a fake relay only. One owner chat gets notifications per publication.
7. **Several things have only been tried partly on real messengers**: own-token mode, channel/group message delivery on Bale (post forwarding, moderation, channel linking), file upload format, invoices — see `docs/real-bale-checklist.md`.
8. **No owner analytics** (e.g. "40% of customers drop out at the phone-number step") — also a strong pitch point.
9. **Photo import can misread small text** (we saw a wrong size range). It always needs the owner's review; consider a second-pass check.
10. **Prices/totals in notifications** use the digits typed; consistent Persian/Latin policy is a product decision.
11. **Messenger outages** are now handled (retries, queue, health banner); queued messages are dropped after 30 minutes by design.
12. **Plans** are enforced but their prices are proposals and payment is simulated (demo).
